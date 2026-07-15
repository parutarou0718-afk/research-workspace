"""Presentation-layer helpers for loading Designer-owned widgets."""

import json
from importlib.resources import files

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget


def _token_stylesheet() -> str:
    token_path = files("research_workspace.presentation").joinpath(
        "ui", "design_tokens.json"
    )
    tokens = json.loads(token_path.read_text(encoding="utf-8"))
    colors = tokens["colors"]
    radius = tokens["radius"]
    typography = tokens["typography"]
    point_scale = typography["pointScale"]
    body_points = typography["body"] * point_scale
    title_points = typography["title"] * point_scale
    font_family = typography["fontFamily"].split(",", maxsplit=1)[0]
    return f"""
QWidget {{ color: {colors['textMain']}; font-family: '{font_family}'; font-size: {body_points:g}pt; }}
QWidget#overviewPage, QWidget#papersPage, QWidget#ideasPage,
QWidget#submissionsPage, QWidget#conferencesPage, QWidget#grantsPage,
QWidget#settingsPage, QWidget#startupErrorPage {{ background: {colors['background']}; }}
QFrame[card="true"] {{ background: {colors['surface']}; border: 1px solid {colors['border']}; border-radius: {radius['card']}px; }}
QLabel#pageTitleLabel {{ font-size: {title_points:g}pt; font-weight: 700; }}
""".strip()


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
    widget.setStyleSheet(f"{widget.styleSheet()}\n{_token_stylesheet()}")
    return widget


def require_child(root: QWidget, widget_type: type[QWidget], object_name: str):
    """Return a required Designer child or fail at controller construction."""
    child = root.findChild(widget_type, object_name)
    if child is None:
        raise RuntimeError(f"Missing required widget: {object_name}")
    return child
