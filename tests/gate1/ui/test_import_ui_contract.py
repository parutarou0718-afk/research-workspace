from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton, QScrollArea, QWidget
import pytest


ROOT = Path(__file__).resolve().parents[3]
UI_DIR = ROOT / "src" / "research_workspace" / "presentation" / "ui"


def _names(filename: str) -> set[str]:
    root = ElementTree.parse(UI_DIR / filename).getroot()
    return {
        node.attrib["name"]
        for node in root.iter()
        if node.tag in {"widget", "layout", "spacer"} and "name" in node.attrib
    }


def test_import_page_and_dialog_are_designer_owned_with_semantic_objects() -> None:
    page = ElementTree.parse(UI_DIR / "imports_page.ui").getroot()
    dialog = ElementTree.parse(UI_DIR / "import_batch_dialog.ui").getroot()
    assert page.find("widget").attrib == {"class": "QWidget", "name": "importsPage"}
    assert dialog.find("widget").attrib == {
        "class": "QDialog",
        "name": "importBatchDialog",
    }
    assert {
        "importsScrollArea",
        "selectImportFilesButton",
        "recentImportsTable",
        "importStorageDisclosureLabel",
    } <= _names("imports_page.ui")
    assert {
        "immutableCopyDisclosureLabel",
        "estimatedStorageLabel",
        "estimateUncertaintyLabel",
        "importProgressBar",
        "startImportButton",
        "cancelImportButton",
        "closeDialogButton",
    } <= _names("import_batch_dialog.ui")

    for controller in (
        ROOT / "src/research_workspace/presentation/pages/imports_page.py",
        ROOT / "src/research_workspace/presentation/dialogs/import_batch_dialog.py",
    ):
        tree = ast.parse(controller.read_text(encoding="utf-8"))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not calls.intersection(
            {"QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout"}
        )


def test_import_page_scrolls_and_navigation_is_reachable(qtbot) -> None:
    from research_workspace.presentation.main_window import MainWindow

    window = MainWindow(services=object())
    qtbot.addWidget(window)
    button = window.findChild(QPushButton, "navImportsButton")
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert window.page_stack.currentWidget() is window.pages["imports"].widget
    scroll = window.pages["imports"].widget.findChild(QScrollArea, "importsScrollArea")
    assert scroll.widgetResizable()
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_import_ui_has_no_later_gate_or_ineffective_controls(qtbot, tmp_path: Path) -> None:
    from research_workspace.presentation.dialogs.import_batch_dialog import ImportBatchDialog
    from research_workspace.presentation.pages.imports_page import ImportsPage

    source = tmp_path / "paper.pdf"
    source.write_bytes(b"pdf")
    page = ImportsPage(services=object())
    dialog = ImportBatchDialog(services=object(), source_paths=(source,))
    qtbot.addWidget(page.widget)
    qtbot.addWidget(dialog)
    forbidden = {
        "password", "ocr", "watch", "monitor", "candidate", "confirm",
        "crud", "backup", "restore", "export",
    }
    for root in (page.widget, dialog):
        controls = root.findChildren(QWidget)
        interactive_text = " ".join(
            getattr(control, "text", lambda: "")()
            for control in controls
            if hasattr(control, "text")
        ).casefold()
        object_names = " ".join(control.objectName() for control in controls).casefold()
        assert not any(token in interactive_text or token in object_names for token in forbidden)
    assert isinstance(dialog, QDialog)


@pytest.mark.parametrize("scale", [1.25, 1.5])
def test_import_dialog_controls_are_reachable_at_windows_scaling(scale: float) -> None:
    probe = r'''
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication, QPushButton
from research_workspace.presentation.dialogs.import_batch_dialog import ImportBatchDialog
app = QApplication([])
dialog = ImportBatchDialog(services=object(), source_paths=(Path("sample.pdf"),))
dialog.show()
app.processEvents()
names = ("startImportButton", "cancelImportButton", "closeDialogButton")
buttons = [dialog.findChild(QPushButton, name) for name in names]
print(json.dumps({
    "scale": dialog.devicePixelRatioF(),
    "minimum": [dialog.minimumWidth(), dialog.minimumHeight()],
    "visible": all(button is not None and button.isVisibleTo(dialog) for button in buttons),
    "within": all(dialog.rect().contains(button.geometry()) for button in buttons),
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
        "minimum": [720, 560],
        "visible": True,
        "within": True,
    }
