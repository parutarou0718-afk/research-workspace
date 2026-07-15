"""Presentation-layer helpers for loading Designer-owned widgets."""

from importlib.resources import files

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget


def load_ui_resource(filename: str) -> QWidget:
    """Load one runtime Designer file without generating Python UI code."""
    path = files("research_workspace.presentation").joinpath("ui", filename)
    ui_file = QFile(str(path))
    if not ui_file.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(f"Unable to open UI resource: {filename}")
    try:
        widget = QUiLoader().load(ui_file)
    finally:
        ui_file.close()
    if widget is None:
        raise RuntimeError(f"Unable to load UI resource: {filename}")
    return widget


def require_child(root: QWidget, widget_type: type[QWidget], object_name: str):
    """Return a required Designer child or fail at controller construction."""
    child = root.findChild(widget_type, object_name)
    if child is None:
        raise RuntimeError(f"Missing required widget: {object_name}")
    return child
