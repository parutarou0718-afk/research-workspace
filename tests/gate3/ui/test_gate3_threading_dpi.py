import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest


ROOT = Path(__file__).resolve().parents[3]


def test_crud_page_rejects_background_widget_updates(qtbot) -> None:
    from research_workspace.presentation.pages.papers_page import PapersPage

    page = PapersPage(object())
    qtbot.addWidget(page.widget)
    failures = []

    def update():
        try:
            page.refresh()
        except RuntimeError as exc:
            failures.append(str(exc))

    thread = threading.Thread(target=update)
    thread.start()
    thread.join()
    assert failures == ["UI_UPDATE_OUTSIDE_QT_THREAD"]


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
def test_gate3_crud_ui_scrolls_at_single_monitor_dpi(scale: float) -> None:
    probe = r'''
import json
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication, QScrollArea
from research_workspace.presentation.pages.papers_page import PapersPage
from research_workspace.presentation.pages.ideas_page import IdeasPage
from research_workspace.presentation.pages.submissions_page import SubmissionsPage
class Query:
    def project(self, include_deleted=False): return ()
services = SimpleNamespace(
    get_papers=Query(), get_ideas=Query(), get_submissions=Query(),
    crud_actions=object(),
)
app = QApplication([])
pages = [PapersPage(services), IdeasPage(services), SubmissionsPage(services)]
for page in pages:
    page.widget.resize(1000, 700)
    page.widget.show()
app.processEvents()
print(json.dumps({
  "scale": pages[0].widget.devicePixelRatioF(),
  "scrolls": [
    page.widget.findChild(QScrollArea).widgetResizable() for page in pages
  ],
}))
'''
    env = os.environ.copy()
    env.update({"QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": str(scale)})
    result = subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report == {
        "scale": pytest.approx(scale),
        "scrolls": [True, True, True],
    }


def test_crud_controllers_import_no_database_or_repository() -> None:
    combined = "\n".join(
        (
            ROOT / "src/research_workspace/presentation" / group / name
        ).read_text("utf-8").casefold()
        for group, name in (
            ("pages", "papers_page.py"),
            ("pages", "ideas_page.py"),
            ("pages", "submissions_page.py"),
            ("dialogs", "paper_editor_dialog.py"),
            ("dialogs", "idea_editor_dialog.py"),
            ("dialogs", "submission_editor_dialog.py"),
        )
    )
    for forbidden in (
        "sqlalchemy", "session", "repository", "infrastructure.db",
        "writecoordinator",
    ):
        assert forbidden not in combined
