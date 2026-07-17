import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from research_workspace.application.services.candidate_detection import (
    CandidateInput,
    PaperMembership,
    detect_candidate,
    jaccard_similarity,
    text_fingerprint,
)
from research_workspace.domain.versioning import VersionRuleId


FIXTURE = Path(__file__).parents[1] / "fixtures" / "candidate_cases.json"
NOW = datetime(2026, 7, 17, 22, tzinfo=timezone.utc)


class Memberships:
    def __init__(self, values=()):
        self.values = tuple(values)
        self.calls = []

    def active_memberships(self, snapshot_id):
        self.calls.append(snapshot_id)
        return tuple(item for item in self.values if item.snapshot_id == snapshot_id)


def _base(**changes):
    first, second = uuid4(), uuid4()
    value = CandidateInput(
        snapshot_a_id=first,
        snapshot_b_id=second,
        snapshot_a_sha256="a" * 64,
        snapshot_b_sha256="b" * 64,
        snapshot_a_mime_type="application/pdf",
        snapshot_b_mime_type="application/pdf",
        observation_ids=(uuid4(), uuid4()),
        first_seen_a=NOW,
        first_seen_b=NOW + timedelta(seconds=1),
        modified_at_a=NOW,
        modified_at_b=NOW + timedelta(seconds=2),
        filename_a="unrelated-a.pdf",
        filename_b="unrelated-b.pdf",
        title_a="Title A",
        title_b="Title B",
        text_a=None,
        text_b=None,
        zero_text_a=False,
        zero_text_b=False,
        parent_path_hash_a="1" * 64,
        parent_path_hash_b="2" * 64,
        source_continuity=(),
        replace_continuity=(),
        common_source_observation=False,
    )
    return replace(value, **changes)


def _primary(value, memberships=Memberships()):
    result = detect_candidate(value, memberships)
    return None if result is None else result.rule_id


def test_fixture_registers_the_closed_rule_and_rejection_cases() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "1.0"
    assert [item["name"] for item in fixture["cases"]] == [
        "source_continuity", "replace_continuity", "paper_title_time",
        "name_title_text", "zero_text_lineage", "same_hash", "mtime_only",
        "same_paper_only", "ambiguous_direction", "conflicting_continuity",
    ]


def test_r1_and_r2_require_verified_directed_continuity() -> None:
    value = _base()
    assert _primary(
        replace(value, source_continuity=((value.snapshot_a_id, value.snapshot_b_id),))
    ) is VersionRuleId.R1_SOURCE_CONTINUITY
    assert _primary(
        replace(value, replace_continuity=((value.snapshot_a_id, value.snapshot_b_id),))
    ) is VersionRuleId.R2_REPLACE_CONTINUITY


def test_supported_mime_change_is_explanation_not_exclusion() -> None:
    value = _base(
        snapshot_b_mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )
    )
    value = replace(
        value,
        source_continuity=((value.snapshot_a_id, value.snapshot_b_id),),
    )
    result = detect_candidate(value, Memberships())
    assert result.rule_id is VersionRuleId.R1_SOURCE_CONTINUITY
    assert json.loads(result.signals)["mime_type_changed"] is True


def test_r3_consumes_authoritative_membership_title_and_clear_order() -> None:
    value = _base(title_a=" Same\tTitle ", title_b="same title")
    paper = uuid4()
    memberships = Memberships(
        (
            PaperMembership(value.snapshot_a_id, paper, 1),
            PaperMembership(value.snapshot_b_id, paper, 2),
        )
    )
    assert _primary(value, memberships) is VersionRuleId.R3_PAPER_TITLE_TIME
    assert memberships.calls == [value.snapshot_a_id, value.snapshot_b_id]
    assert _primary(value, Memberships()) is None


def test_r4_uses_exact_lineage_title_and_deterministic_text_threshold() -> None:
    text = "same research sentence " * 20
    value = _base(
        filename_a="paper_draft.pdf", filename_b="paper_rev2.pdf",
        title_a="Paper", title_b=" paper ", text_a=text, text_b=text,
    )
    assert _primary(value) is VersionRuleId.R4_NAME_TITLE_TEXT
    assert text_fingerprint("x" * 199) is None
    fingerprint = text_fingerprint("x" * 200)
    assert fingerprint == tuple(sorted(fingerprint))
    assert jaccard_similarity(fingerprint, fingerprint) == 1.0
    assert jaccard_similarity(
        text_fingerprint("x" * 200), text_fingerprint("y" * 200)
    ) == 0.0


def test_same_hash_mtime_only_same_paper_only_and_conflict_are_rejected() -> None:
    value = _base()
    assert detect_candidate(
        replace(value, snapshot_b_sha256=value.snapshot_a_sha256), Memberships()
    ) is None
    assert detect_candidate(
        replace(value, first_seen_b=value.first_seen_a), Memberships()
    ) is None
    paper = uuid4()
    memberships = Memberships(
        (
            PaperMembership(value.snapshot_a_id, paper, 1),
            PaperMembership(value.snapshot_b_id, paper, 2),
        )
    )
    assert detect_candidate(
        replace(value, first_seen_b=value.first_seen_a), memberships
    ) is None
    assert detect_candidate(
        replace(
            value,
            source_continuity=(
                (value.snapshot_a_id, value.snapshot_b_id),
                (value.snapshot_b_id, value.snapshot_a_id),
            ),
        ),
        Memberships(),
    ) is None


def test_multiple_matches_aggregate_with_fixed_primary_precedence() -> None:
    text = "same research sentence " * 20
    value = _base(
        filename_a="paper_draft.pdf", filename_b="paper_rev2.pdf",
        title_a="Paper", title_b="paper", text_a=text, text_b=text,
    )
    value = replace(
        value,
        source_continuity=((value.snapshot_a_id, value.snapshot_b_id),),
        replace_continuity=((value.snapshot_a_id, value.snapshot_b_id),),
    )
    paper = uuid4()
    result = detect_candidate(
        value,
        Memberships(
            (
                PaperMembership(value.snapshot_a_id, paper, 1),
                PaperMembership(value.snapshot_b_id, paper, 2),
            )
        ),
    )
    assert result.rule_id is VersionRuleId.R1_SOURCE_CONTINUITY
    signals = json.loads(result.signals)
    assert signals["matched_rules"] == [
        "R1_SOURCE_CONTINUITY",
        "R2_REPLACE_CONTINUITY",
        "R3_PAPER_TITLE_TIME",
        "R4_NAME_TITLE_TEXT",
    ]


def test_lower_priority_conflicting_signal_is_recorded_as_non_triggering() -> None:
    value = _base()
    value = replace(
        value,
        source_continuity=((value.snapshot_a_id, value.snapshot_b_id),),
        replace_continuity=(
            (value.snapshot_a_id, value.snapshot_b_id),
            (value.snapshot_b_id, value.snapshot_a_id),
        ),
    )
    result = detect_candidate(value, Memberships())
    signals = json.loads(result.signals)
    assert result.rule_id is VersionRuleId.R1_SOURCE_CONTINUITY
    assert signals["rule_results"]["R2_REPLACE_CONTINUITY"] is False
