"""Deterministic candidate identity helpers; rule evaluation is added separately."""

from __future__ import annotations

import hashlib
from types import MappingProxyType
from collections.abc import Mapping
from dataclasses import dataclass
import re
import unicodedata

import rfc8785


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
