from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

from PySide6.QtCore import Qt


ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "src/research_workspace/presentation/ui"


class _Candidates:
    def __init__(self, rows):
        self.rows = tuple(rows)

    def execute(self):
        return self.rows


class _Undo:
    def __init__(self, rows):
        self.rows = tuple(rows)

    def execute(self, *, as_of):
        assert as_of.tzinfo is not None
        return self.rows


class _Actions:
    def __init__(self, bundle):
        self.bundle = bundle
        self.calls = []

    def review(self, candidate_id):
        self.calls.append(("review", candidate_id))
        return self.bundle

    def reject_candidate(self, candidate_id):
        self.calls.append(("reject", candidate_id))

    def reconsider_candidate(self, candidate_id):
        self.calls.append(("reconsider", candidate_id))

    def undo(self, command_id):
        self.calls.append(("undo", command_id))


def _candidate(status="pending"):
    return SimpleNamespace(
        candidate_id=uuid4(), earlier_snapshot_id=uuid4(),
        later_snapshot_id=uuid4(), detector_id="detector",
        detector_version="1.0", rule_id="R1_SOURCE_CONTINUITY",
        rule_config_fingerprint="a" * 64,
        direction_rationale_json=b'{"basis":"time"}',
        signals_json=b'{"signal":true}',
        input_observation_ids_json=b"[]", status=status,
        superseded_by_candidate_id=None, row_version=1,
    )


def _bundle(candidate):
    return SimpleNamespace(
        candidate_id=candidate.candidate_id,
        candidate_row_version=candidate.row_version,
        detector_id=candidate.detector_id,
        detector_version=candidate.detector_version,
        rule_id=candidate.rule_id,
        rule_config_fingerprint=candidate.rule_config_fingerprint,
        earlier_snapshot_id=candidate.earlier_snapshot_id,
        later_snapshot_id=candidate.later_snapshot_id,
        direction_rationale=candidate.direction_rationale_json,
        signals=candidate.signals_json,
        input_observation_ids=(),
        existing_memberships=(),
        existing_relation_ids=(),
    )


def test_relation_review_layout_is_designer_owned_and_state_gated(qtbot) -> None:
    from research_workspace.presentation.dialogs.relation_review_dialog import (
        RelationReviewDialog,
    )

    candidate = _candidate()
    actions = _Actions(_bundle(candidate))
    services = SimpleNamespace(decision_actions=actions)
    dialog = RelationReviewDialog(services, candidate)
    qtbot.addWidget(dialog)
    assert dialog.bundle.candidate_id == candidate.candidate_id
    assert dialog.confirm_button.isEnabled()
    assert dialog.reject_button.isEnabled()
    assert not dialog.reconsider_button.isEnabled()
    tree = ElementTree.parse(UI / "relation_review_dialog.ui")
    names = {node.attrib["name"] for node in tree.iter() if "name" in node.attrib}
    assert {
        "relationReviewDialog", "candidateEvidenceText",
        "confirmCandidateButton", "rejectCandidateButton",
        "reconsiderCandidateButton",
    } <= names


def test_candidate_page_exposes_real_review_and_safe_undo_only(qtbot) -> None:
    from research_workspace.presentation.pages.version_candidates_page import (
        VersionCandidatesPage,
    )

    candidate = _candidate()
    undo = SimpleNamespace(
        command_id=uuid4(), command_type="paper.update",
        committed_at=datetime.now(timezone.utc), affected_entity_ids=(uuid4(),),
    )
    actions = _Actions(_bundle(candidate))
    services = SimpleNamespace(
        get_version_candidates=_Candidates((candidate,)),
        get_safe_undo=_Undo((undo,)),
        decision_actions=actions,
    )
    page = VersionCandidatesPage(services)
    qtbot.addWidget(page.widget)
    assert page.table.rowCount() == 1
    assert page.undo_table.rowCount() == 1
    page.table.selectRow(0)
    assert page.review_button.isEnabled()
    page.undo_table.selectRow(0)
    qtbot.mouseClick(page.undo_button, Qt.MouseButton.LeftButton)
    assert actions.calls[-1] == ("undo", undo.command_id)
    assert "撤销操作本身不能再次撤销" in page.undo_notice.text()

