import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

from PySide6.QtCore import Qt


ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "src/research_workspace/presentation/ui"


class _Actions:
    def __init__(self):
        self.calls = []

    def create_paper(self, title, status):
        self.calls.append(("create_paper", title, status))

    def create_idea(self, title, content, status):
        self.calls.append(("create_idea", title, content, status))

    def create_submission(self, paper_id, venue, status):
        self.calls.append(("create_submission", paper_id, venue, status))


class _Query:
    def __init__(self, rows=()):
        self.rows = tuple(rows)

    def project(self, *, include_deleted=False):
        return self.rows


def _services():
    return SimpleNamespace(
        crud_actions=_Actions(),
        get_papers=_Query(),
        get_ideas=_Query(),
        get_submissions=_Query(),
    )


def test_editor_layouts_are_designer_owned_with_semantic_controls() -> None:
    contracts = {
        "paper_editor_dialog.ui": {
            "paperEditorDialog", "paperTitleEdit", "paperStatusCombo",
            "savePaperButton", "paperRecoveryStatusLabel",
        },
        "idea_editor_dialog.ui": {
            "ideaEditorDialog", "ideaTitleEdit", "ideaContentEdit",
            "ideaStatusCombo", "saveIdeaButton", "ideaRecoveryStatusLabel",
        },
        "submission_editor_dialog.ui": {
            "submissionEditorDialog", "submissionPaperIdEdit",
            "submissionVenueEdit", "submissionStatusCombo",
            "saveSubmissionButton", "submissionRecoveryStatusLabel",
        },
    }
    for filename, required in contracts.items():
        tree = ElementTree.parse(UI / filename)
        names = {
            element.attrib["name"]
            for element in tree.iter()
            if "name" in element.attrib
        }
        assert required <= names
    for filename in (
        "paper_editor_dialog.py",
        "idea_editor_dialog.py",
        "submission_editor_dialog.py",
    ):
        source = (
            ROOT / "src/research_workspace/presentation/dialogs" / filename
        ).read_text("utf-8")
        calls = {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not calls & {"QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout"}


def test_paper_idea_submission_dialogs_call_only_approved_actions(qtbot) -> None:
    from research_workspace.presentation.dialogs.paper_editor_dialog import (
        PaperEditorDialog,
    )
    from research_workspace.presentation.dialogs.idea_editor_dialog import (
        IdeaEditorDialog,
    )
    from research_workspace.presentation.dialogs.submission_editor_dialog import (
        SubmissionEditorDialog,
    )

    services = _services()
    paper = PaperEditorDialog(services)
    idea = IdeaEditorDialog(services)
    submission = SubmissionEditorDialog(services)
    for dialog in (paper, idea, submission):
        qtbot.addWidget(dialog)

    paper.title_edit.setText(" Paper ")
    qtbot.mouseClick(paper.save_button, Qt.MouseButton.LeftButton)
    idea.title_edit.setText("Idea")
    idea.content_edit.setPlainText("Markdown")
    qtbot.mouseClick(idea.save_button, Qt.MouseButton.LeftButton)
    submission.paper_id_edit.setText(str(uuid4()))
    submission.venue_edit.setText("Venue")
    qtbot.mouseClick(submission.save_button, Qt.MouseButton.LeftButton)

    assert [call[0] for call in services.crud_actions.calls] == [
        "create_paper", "create_idea", "create_submission",
    ]
    assert paper.recovery_status_label.text() == "正在准备安全恢复点…"


def test_crud_pages_are_real_lists_without_future_controls(qtbot) -> None:
    from research_workspace.presentation.pages.papers_page import PapersPage
    from research_workspace.presentation.pages.ideas_page import IdeasPage
    from research_workspace.presentation.pages.submissions_page import SubmissionsPage

    services = _services()
    paper_page = PapersPage(services)
    idea_page = IdeasPage(services)
    submission_page = SubmissionsPage(services)
    pages = (paper_page, idea_page, submission_page)
    for page in pages:
        qtbot.addWidget(page.widget)
        page.refresh()
        assert page.new_button.isVisible() is False or page.new_button.text()
    assert paper_page.list_view.count() == 0
    assert idea_page.list_view.count() == 0
    assert submission_page.table.rowCount() == 0
    combined = " ".join(
        (UI / name).read_text("utf-8").casefold()
        for name in ("papers_page.ui", "ideas_page.ui", "submissions_page.ui")
    )
    for forbidden in (
        "confirm", "reject", "undo", "redo", "backup", "export",
        "ocr", "agent", "repair", "permanent",
    ):
        assert forbidden not in combined


def test_bootstrap_composes_real_crud_queries_and_actions() -> None:
    from research_workspace.bootstrap import ApplicationServices

    fields = ApplicationServices.__dataclass_fields__
    assert {"get_papers", "get_ideas", "get_submissions", "crud_actions"} <= fields.keys()
    for filename in ("papers_page.py", "ideas_page.py", "submissions_page.py"):
        source = (
            ROOT / "src/research_workspace/presentation/pages" / filename
        ).read_text("utf-8")
        assert "infrastructure.db" not in source
        assert "sqlalchemy" not in source.casefold()
