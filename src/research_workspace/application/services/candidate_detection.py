"""Deterministic candidate identity helpers; rule evaluation is added separately."""

from __future__ import annotations

import hashlib
from types import MappingProxyType
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Protocol
import unicodedata
from uuid import UUID

import rfc8785

from research_workspace.application.dto.monitoring_dto import CandidateDetectionResult
from research_workspace.domain.versioning import VersionRuleId


_VERSION_TOKENS = (
    "draft",
    "final",
    "rev",
    "revision",
    "v",
    "version",
    "初稿",
    "终稿",
    "最终",
    "修订稿",
)
DEFAULT_CANDIDATE_RULE_CONFIG = MappingProxyType(
    {
        "candidate_window": 5,
        "continuity_neighbors": 2,
        "paper_neighbors": 5,
        "filename_neighbors": 5,
        "minimum_text_codepoints": 200,
        "gram_codepoints": 13,
        "maximum_fingerprint_values": 2048,
        "text_similarity_threshold": 0.8,
        "version_tokens": _VERSION_TOKENS,
    }
)
_SEPARATOR_RUN = re.compile(r"[\s_.-]+", re.UNICODE)
_VERSION_SUFFIX = re.compile(
    r"(?:^| )(" + "|".join(
        sorted((re.escape(token) for token in _VERSION_TOKENS), key=len, reverse=True)
    ) + r")(\d*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class FilenameLineage:
    lineage_key: str
    version_token: str | None


@dataclass(frozen=True, slots=True)
class PaperMembership:
    snapshot_id: UUID
    paper_id: UUID
    import_order: int


class PaperMembershipPort(Protocol):
    def active_memberships(
        self, snapshot_id: UUID
    ) -> tuple[PaperMembership, ...]: ...


class NoPaperMemberships:
    def active_memberships(self, snapshot_id: UUID) -> tuple[PaperMembership, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class CandidateInput:
    snapshot_a_id: UUID
    snapshot_b_id: UUID
    snapshot_a_sha256: str
    snapshot_b_sha256: str
    snapshot_a_mime_type: str
    snapshot_b_mime_type: str
    observation_ids: tuple[UUID, ...]
    first_seen_a: datetime
    first_seen_b: datetime
    modified_at_a: datetime
    modified_at_b: datetime
    filename_a: str
    filename_b: str
    title_a: str
    title_b: str
    text_a: str | None
    text_b: str | None
    zero_text_a: bool
    zero_text_b: bool
    parent_path_hash_a: str | None
    parent_path_hash_b: str | None
    source_continuity: tuple[tuple[UUID, UUID], ...]
    replace_continuity: tuple[tuple[UUID, UUID], ...]
    common_source_observation: bool

    def __post_init__(self) -> None:
        observations = tuple(self.observation_ids)
        source = tuple(tuple(item) for item in self.source_continuity)
        replacement = tuple(tuple(item) for item in self.replace_continuity)
        if (
            self.snapshot_a_id == self.snapshot_b_id
            or len(observations) != len(set(observations))
        ):
            raise ValueError("CANDIDATE_INPUT_INVALID")
        object.__setattr__(self, "observation_ids", observations)
        object.__setattr__(self, "source_continuity", source)
        object.__setattr__(self, "replace_continuity", replacement)


@dataclass(frozen=True, slots=True)
class _Direction:
    earlier: UUID
    later: UUID
    basis: str


def normalize_candidate_title(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    return " ".join(normalized.split()).casefold()


def normalize_filename_lineage(filename: str) -> FilenameLineage:
    name = unicodedata.normalize("NFC", filename).strip()
    if "." in name:
        name = name.rsplit(".", 1)[0]
    normalized = _SEPARATOR_RUN.sub(" ", normalize_candidate_title(name)).strip()
    match = _VERSION_SUFFIX.search(normalized)
    if match is None:
        return FilenameLineage(normalized, None)
    token = f"{match.group(1).casefold()}{match.group(2)}"
    lineage = normalized[: match.start()].strip()
    return FilenameLineage(lineage, token)


def rule_config_fingerprint(overrides: Mapping[str, object]) -> str:
    unknown = set(overrides) - set(DEFAULT_CANDIDATE_RULE_CONFIG)
    if unknown:
        raise ValueError("CANDIDATE_RULE_CONFIG_INVALID")
    expanded = dict(DEFAULT_CANDIDATE_RULE_CONFIG)
    expanded.update(overrides)
    payload = {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in expanded.items()
    }
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def text_fingerprint(text: str) -> tuple[int, ...] | None:
    normalized = normalize_candidate_title(text)
    minimum = int(DEFAULT_CANDIDATE_RULE_CONFIG["minimum_text_codepoints"])
    gram_size = int(DEFAULT_CANDIDATE_RULE_CONFIG["gram_codepoints"])
    if len(normalized) < minimum:
        return None
    values = {
        int.from_bytes(
            hashlib.sha256(
                normalized[index : index + gram_size].encode("utf-8")
            ).digest()[:8],
            "big",
        )
        for index in range(len(normalized) - gram_size + 1)
    }
    maximum = int(DEFAULT_CANDIDATE_RULE_CONFIG["maximum_fingerprint_values"])
    return tuple(sorted(values)[:maximum])


def jaccard_similarity(
    first: tuple[int, ...] | None, second: tuple[int, ...] | None
) -> float | None:
    if first is None or second is None:
        return None
    left, right = set(first), set(second)
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def detect_candidate(
    value: CandidateInput,
    memberships: PaperMembershipPort | None = None,
    *,
    config: Mapping[str, object] | None = None,
) -> CandidateDetectionResult | None:
    if (
        value.snapshot_a_sha256 == value.snapshot_b_sha256
        or not _supported_mime(value.snapshot_a_mime_type)
        or not _supported_mime(value.snapshot_b_mime_type)
    ):
        return None
    membership_port = memberships or NoPaperMemberships()
    first_memberships = membership_port.active_memberships(value.snapshot_a_id)
    second_memberships = membership_port.active_memberships(value.snapshot_b_id)
    common = _common_memberships(first_memberships, second_memberships)
    filename_a = normalize_filename_lineage(value.filename_a)
    filename_b = normalize_filename_lineage(value.filename_b)
    direction = _determine_direction(value, common, filename_a, filename_b)
    if direction is None:
        return None

    title_a = normalize_candidate_title(value.title_a)
    title_b = normalize_candidate_title(value.title_b)
    title_match = bool(title_a) and title_a == title_b
    lineage_match = bool(filename_a.lineage_key) and (
        filename_a.lineage_key == filename_b.lineage_key
    )
    text_similarity = None
    if (
        not value.zero_text_a
        and not value.zero_text_b
        and value.text_a is not None
        and value.text_b is not None
        and lineage_match
        and title_match
    ):
        text_similarity = jaccard_similarity(
            text_fingerprint(value.text_a), text_fingerprint(value.text_b)
        )
    token_direction = _token_direction(
        value, filename_a.version_token, filename_b.version_token
    )
    path_lineage = (
        value.parent_path_hash_a is not None
        and value.parent_path_hash_a == value.parent_path_hash_b
    )
    rule_results = {
        VersionRuleId.R1_SOURCE_CONTINUITY: _evidence_matches(
            value, value.source_continuity
        ),
        VersionRuleId.R2_REPLACE_CONTINUITY: _evidence_matches(
            value, value.replace_continuity
        ),
        VersionRuleId.R3_PAPER_TITLE_TIME: bool(common) and title_match,
        VersionRuleId.R4_NAME_TITLE_TEXT: (
            lineage_match
            and title_match
            and text_similarity is not None
            and text_similarity
            >= float(DEFAULT_CANDIDATE_RULE_CONFIG["text_similarity_threshold"])
        ),
        VersionRuleId.R5_ZERO_TEXT_LINEAGE: (
            value.zero_text_a
            and value.zero_text_b
            and bool(common)
            and (value.common_source_observation or path_lineage)
            and lineage_match
            and token_direction is not None
            and (token_direction.earlier, token_direction.later)
            == (direction.earlier, direction.later)
            and direction.basis
            in {"source_continuity", "replace_continuity", "first_observed"}
        ),
    }
    matched = tuple(rule for rule in VersionRuleId if rule_results[rule])
    if not matched:
        return None
    signals = {
        "matched_rules": [rule.value for rule in matched],
        "rule_results": {
            rule.value: rule_results[rule] for rule in VersionRuleId
        },
        "normalized_filename_before": (
            filename_a.lineage_key
            if direction.earlier == value.snapshot_a_id
            else filename_b.lineage_key
        ),
        "normalized_filename_after": (
            filename_b.lineage_key
            if direction.later == value.snapshot_b_id
            else filename_a.lineage_key
        ),
        "normalized_title_match": title_match,
        "path_lineage_match": path_lineage,
        "same_paper": bool(common),
        "mime_type_changed": (
            value.snapshot_a_mime_type != value.snapshot_b_mime_type
        ),
        "text_fingerprint": {
            "method": "sha256-13gram-lowest-2048-64bit",
            "similarity": text_similarity,
        },
        "direction_basis": direction.basis,
    }
    rationale = {
        "basis": direction.basis,
        "earlier_snapshot_id": str(direction.earlier),
        "later_snapshot_id": str(direction.later),
    }
    return CandidateDetectionResult(
        direction.earlier,
        direction.later,
        "paper-version-detector",
        "1.0",
        matched[0],
        rule_config_fingerprint(config or {}),
        rfc8785.dumps(rationale),
        rfc8785.dumps(signals),
        tuple(sorted(value.observation_ids, key=str)),
    )


def _supported_mime(value: str) -> bool:
    return value in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }


def _common_memberships(
    first: tuple[PaperMembership, ...], second: tuple[PaperMembership, ...]
) -> tuple[tuple[PaperMembership, PaperMembership], ...]:
    return tuple(
        (left, right)
        for left in first
        for right in second
        if left.paper_id == right.paper_id
    )


def _determine_direction(
    value: CandidateInput,
    common: tuple[tuple[PaperMembership, PaperMembership], ...],
    filename_a: FilenameLineage,
    filename_b: FilenameLineage,
) -> _Direction | None:
    for basis, pairs in (
        ("source_continuity", value.source_continuity),
        ("replace_continuity", value.replace_continuity),
    ):
        direction, conflicted = _direction_from_pairs(value, pairs, basis)
        if conflicted:
            return None
        if direction is not None:
            return direction
    if value.first_seen_a != value.first_seen_b:
        return _ordered(
            value,
            value.first_seen_a < value.first_seen_b,
            "first_observed",
        )
    paper_pairs = tuple(
        (
            left.snapshot_id if left.import_order < right.import_order else right.snapshot_id,
            right.snapshot_id if left.import_order < right.import_order else left.snapshot_id,
        )
        for left, right in common
        if left.import_order != right.import_order
    )
    direction, conflicted = _direction_from_pairs(value, paper_pairs, "paper_import")
    if conflicted:
        return None
    if direction is not None:
        return direction
    return _token_direction(value, filename_a.version_token, filename_b.version_token)


def _direction_from_pairs(
    value: CandidateInput,
    pairs: tuple[tuple[UUID, UUID], ...],
    basis: str,
) -> tuple[_Direction | None, bool]:
    valid = {
        pair
        for pair in pairs
        if set(pair) == {value.snapshot_a_id, value.snapshot_b_id}
        and pair[0] != pair[1]
    }
    if len(valid) > 1 or len(valid) != len(set(pairs)):
        return None, True
    if not valid:
        return None, bool(pairs)
    earlier, later = next(iter(valid))
    return _Direction(earlier, later, basis), False


def _evidence_matches(
    value: CandidateInput, pairs: tuple[tuple[UUID, UUID], ...]
) -> bool:
    direction, conflicted = _direction_from_pairs(value, pairs, "signal")
    return direction is not None and not conflicted


def _ordered(value: CandidateInput, a_first: bool, basis: str) -> _Direction:
    return _Direction(
        value.snapshot_a_id if a_first else value.snapshot_b_id,
        value.snapshot_b_id if a_first else value.snapshot_a_id,
        basis,
    )


def _token_direction(
    value: CandidateInput, token_a: str | None, token_b: str | None
) -> _Direction | None:
    first = _token_parts(token_a)
    second = _token_parts(token_b)
    if first is None or second is None or first == second:
        return None
    stage_a, family_a, number_a = first
    stage_b, family_b, number_b = second
    if stage_a != stage_b:
        return _ordered(value, stage_a < stage_b, "filename_version")
    if (
        stage_a == 1
        and family_a == family_b
        and number_a is not None
        and number_b is not None
        and number_a != number_b
    ):
        return _ordered(value, number_a < number_b, "filename_version")
    return None


def _token_parts(token: str | None) -> tuple[int, str, int | None] | None:
    if token is None:
        return None
    match = re.fullmatch(
        "(" + "|".join(
            sorted((re.escape(item) for item in _VERSION_TOKENS), key=len, reverse=True)
        ) + r")(\d*)",
        token,
        re.IGNORECASE,
    )
    if match is None:
        return None
    family = match.group(1).casefold()
    number = int(match.group(2)) if match.group(2) else None
    if family in {"draft", "初稿"}:
        stage = 0
    elif family in {"final", "终稿", "最终"}:
        stage = 2
    else:
        stage = 1
    return stage, family, number
