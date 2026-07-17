from types import SimpleNamespace
from uuid import uuid4

from PySide6.QtWidgets import QAbstractButton, QTableWidget, QWidget

from research_workspace.application.queries.get_version_candidates import (
    VersionCandidateRecord,
)


class Query:
    def __init__(self, rows):
        self.rows = rows

    def execute(self):
        return self.rows


def _candidate(marker: int = 1):
    return VersionCandidateRecord(
        uuid4(),
        uuid4(),
        uuid4(),
        "paper-version-detector",
        "1.0",
        "R1_SOURCE_CONTINUITY",
        "a" * 64,
        b'{"basis":"source_continuity"}',
        f'{{"revision":{marker}}}'.encode(),
        b"[]",
        "pending",
        None,
        marker,
    )


def test_candidate_page_is_read_only_and_shows_explanation(qtbot) -> None:
    from research_workspace.presentation.pages.version_candidates_page import (
        VersionCandidatesPage,
    )

    candidate = _candidate()
    page = VersionCandidatesPage(
        SimpleNamespace(get_version_candidates=Query((candidate,)))
    )
    qtbot.addWidget(page.widget)
    table = page.widget.findChild(QTableWidget, "versionCandidatesTable")

    assert table.rowCount() == 1
    assert "R1_SOURCE_CONTINUITY" in table.item(0, 3).text()
    assert "paper-version-detector" in table.item(0, 5).text()
    assert [
        button
        for button in page.widget.findChildren(QAbstractButton)
        if not button.objectName().startswith("qt_")
    ] == []
    names = " ".join(
        child.objectName().casefold() for child in page.widget.findChildren(QWidget)
    )
    assert not any(
        token in names
        for token in ("confirm", "reject", "merge", "edit", "delete", "membership")
    )


def test_candidate_unread_is_session_scoped_and_refresh_safe(qtbot) -> None:
    from research_workspace.presentation.pages.version_candidates_page import (
        VersionCandidatesPage,
    )

    candidate = _candidate()
    query = Query((candidate,))
    page = VersionCandidatesPage(SimpleNamespace(get_version_candidates=query))
    qtbot.addWidget(page.widget)
    table = page.widget.findChild(QTableWidget, "versionCandidatesTable")
    assert table.item(0, 6).text() == "未读"

    page.refresh()
    assert table.item(0, 6).text() == "未读"
    page.open_selected_item(0, 0)
    assert table.item(0, 6).text() == "已读"

    query.rows = (
        VersionCandidateRecord(
            candidate.candidate_id,
            candidate.earlier_snapshot_id,
            candidate.later_snapshot_id,
            candidate.detector_id,
            candidate.detector_version,
            candidate.rule_id,
            candidate.rule_config_fingerprint,
            candidate.direction_rationale_json,
            b'{"revision":2}',
            candidate.input_observation_ids_json,
            candidate.status,
            candidate.superseded_by_candidate_id,
            2,
        ),
    )
    page.refresh()
    assert table.item(0, 6).text() == "未读"
