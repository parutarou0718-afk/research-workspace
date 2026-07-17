from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from research_workspace.application.services import candidate_detection
from research_workspace.application.services.candidate_detection import (
    CandidateInput,
    PaperMembership,
    detect_candidate,
)
from research_workspace.domain.versioning import VersionRuleId


class Memberships:
    def __init__(self, values=()):
        self.values = tuple(values)

    def active_memberships(self, snapshot_id):
        return tuple(item for item in self.values if item.snapshot_id == snapshot_id)


def _base(**changes):
    first, second = uuid4(), uuid4()
    now = datetime(2026, 7, 17, 22, tzinfo=timezone.utc)
    value = CandidateInput(
        first, second, "a" * 64, "b" * 64, "application/pdf",
        "application/pdf", (uuid4(), uuid4()), now,
        now + timedelta(seconds=1), now, now, "a.pdf", "b.pdf", "A", "B",
        None, None, False, False, "1" * 64, "2" * 64, (), (), False,
    )
    return replace(value, **changes)


def test_r5_uses_membership_lineage_tokens_and_observation_order_without_text(
    monkeypatch,
) -> None:
    value = _base(
        filename_a="paper_draft.pdf",
        filename_b="paper_final.pdf",
        title_a="Scan A",
        title_b="Scan B",
        zero_text_a=True,
        zero_text_b=True,
        parent_path_hash_b="1" * 64,
    )
    paper = uuid4()
    memberships = Memberships(
        (
            PaperMembership(value.snapshot_a_id, paper, 1),
            PaperMembership(value.snapshot_b_id, paper, 2),
        )
    )
    monkeypatch.setattr(
        candidate_detection,
        "text_fingerprint",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("zero-text candidates must not call similarity")
        ),
    )
    result = detect_candidate(value, memberships)
    assert result.rule_id is VersionRuleId.R5_ZERO_TEXT_LINEAGE


def test_r5_without_authoritative_membership_or_order_returns_no_candidate() -> None:
    value = _base(
        filename_a="paper_draft.pdf",
        filename_b="paper_final.pdf",
        zero_text_a=True,
        zero_text_b=True,
        parent_path_hash_b="1" * 64,
    )
    assert detect_candidate(value, Memberships()) is None
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
