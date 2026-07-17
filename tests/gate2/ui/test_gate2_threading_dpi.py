import ast
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from xml.etree import ElementTree

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
import pytest


ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "src" / "research_workspace" / "presentation" / "ui"


def test_gate2_pages_are_designer_owned_and_navigable(qtbot) -> None:
    for filename, root_name in (
        ("monitoring_page.ui", "monitoringPage"),
        ("version_candidates_page.ui", "versionCandidatesPage"),
    ):
        root = ElementTree.parse(UI / filename).getroot()
        assert root.find("widget").attrib["name"] == root_name
    for controller in (
        ROOT / "src/research_workspace/presentation/pages/monitoring_page.py",
        ROOT
        / "src/research_workspace/presentation/pages/version_candidates_page.py",
    ):
        calls = {
            node.func.id
            for node in ast.walk(ast.parse(controller.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not calls & {"QVBoxLayout", "QHBoxLayout", "QGridLayout"}

    from research_workspace.presentation.main_window import MainWindow

    window = MainWindow(services=object())
    qtbot.addWidget(window)
    for key in ("monitoring", "version_candidates"):
        button = window.navigation_buttons[key]
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert window.page_stack.currentWidget() is window.pages[key].widget


def test_controllers_receive_composed_services_without_database_or_watcher_access() -> None:
    from research_workspace import bootstrap
    from research_workspace.presentation.pages import (
        monitoring_page,
        version_candidates_page,
    )

    controller_source = "\n".join(
        inspect.getsource(module)
        for module in (monitoring_page, version_candidates_page)
    ).casefold()
    for forbidden in (
        "sqlalchemy",
        "repository",
        "infrastructure.db",
        "watchdog",
        "writecoordinator",
    ):
        assert forbidden not in controller_source
    trees = (
        ast.parse(inspect.getsource(monitoring_page)),
        ast.parse(inspect.getsource(version_candidates_page)),
    )
    assert not any(
        isinstance(node, (ast.Name, ast.Attribute))
        and (getattr(node, "id", None) == "Session" or getattr(node, "attr", None) == "Session")
        for tree in trees
        for node in ast.walk(tree)
    )
    annotations = bootstrap.ApplicationServices.__annotations__
    assert {
        "get_monitoring",
        "get_version_candidates",
        "monitoring_actions",
    } <= set(annotations)


def test_ui_update_rejects_background_thread(qtbot) -> None:
    from research_workspace.presentation.pages.monitoring_page import MonitoringPage

    page = MonitoringPage(services=object())
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


@pytest.mark.parametrize("scale", [1.25, 1.5])
def test_gate2_pages_fit_single_monitor_scaling(scale: float) -> None:
    probe = r'''
import json
from PySide6.QtWidgets import QApplication, QScrollArea
from research_workspace.presentation.pages.monitoring_page import MonitoringPage
from research_workspace.presentation.pages.version_candidates_page import VersionCandidatesPage
app = QApplication([])
pages = [MonitoringPage(object()), VersionCandidatesPage(object())]
for page in pages:
    page.widget.resize(1000, 700)
    page.widget.show()
app.processEvents()
print(json.dumps({
  "scale": pages[0].widget.devicePixelRatioF(),
  "scrolls": [
    bool(page.widget.findChild(QScrollArea)) and
    page.widget.findChild(QScrollArea).widgetResizable()
    for page in pages
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
    assert report == {"scale": pytest.approx(scale), "scrolls": [True, True]}
