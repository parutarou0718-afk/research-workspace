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
    components = tokens["components"]
    button = components["button"]
    card = components["card"]
    input_component = components["input"]
    badge = components["badge"]["variants"]
    typography = tokens["typography"]
    point_scale = typography["pointScale"]
    body_points = typography["body"] * point_scale
    title_points = typography["title"] * point_scale
    # Qt style sheets do not reliably apply comma-separated fallbacks on all
    # platforms/plugins. Keep the design-token stack in JSON, but choose the
    # Windows CJK-safe family for actual rendering so Chinese UI text never
    # degrades into tofu boxes.
    font_family = "'Microsoft YaHei UI'"
    return f"""
QWidget {{ color: {colors['textMain']}; font-family: {font_family}; font-size: {body_points:g}pt; }}
QWidget#overviewPage, QWidget#papersPage, QWidget#ideasPage,
QWidget#submissionsPage, QWidget#conferencesPage, QWidget#grantsPage,
QWidget#importsPage, QWidget#monitoringPage, QWidget#versionCandidatesPage,
QWidget#relationsPage, QWidget#settingsPage, QWidget#startupErrorPage,
QDialog#importBatchDialog {{ background: {colors['background']}; }}
QPushButton {{
  min-height: {button['height']}px;
  border: 1px solid #C7D7FE;
  border-radius: {button['radius']}px;
  padding: 0 14px;
  background: {colors['surface']};
  color: {colors['primaryHover']};
  font-weight: 500;
}}
QPushButton:hover {{
  background: {colors['primarySoft']};
  border-color: {colors['primary']};
}}
QPushButton:pressed {{
  background: #D8E4FF;
  border-color: {colors['primaryHover']};
  padding-top: 1px;
}}
QPushButton:disabled {{
  background: #F2F4F7;
  border-color: {colors['border']};
  color: {colors['textMuted']};
}}
QFrame[card="true"], QFrame[component="card"] {{
  background: {colors['surface']};
  border: {card['borderWidth']}px solid {colors['border']};
  border-radius: {card['radius']}px;
}}
QFrame[component="toolbar"] {{
  background: {colors['surface']};
  border: 1px solid {colors['border']};
  border-radius: {card['radius']}px;
}}
QFrame[component="emptyState"] {{
  background: {colors['surface']};
  border: 1px dashed {colors['border']};
  border-radius: {card['radius']}px;
}}
QPushButton[variant="primary"] {{
  min-height: {button['height']}px;
  border: 1px solid {button['variants']['primary']['border']};
  border-radius: {button['radius']}px;
  padding: 0 16px;
  background: {button['variants']['primary']['background']};
  color: {button['variants']['primary']['foreground']};
  font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
  background: {button['variants']['primary']['hover']};
  border-color: {button['variants']['primary']['hover']};
}}
QPushButton[variant="primary"]:pressed {{
  background: #2F5FD0;
  border-color: #2F5FD0;
  padding-top: 1px;
}}
QPushButton[variant="secondary"] {{
  min-height: {button['height']}px;
  border: 1px solid #C7D7FE;
  border-radius: {button['radius']}px;
  padding: 0 16px;
  background: {button['variants']['secondary']['background']};
  color: {colors['primaryHover']};
  font-weight: 500;
}}
QPushButton[variant="secondary"]:hover {{
  background: {colors['primarySoft']};
  border-color: {colors['primary']};
}}
QPushButton[variant="secondary"]:pressed {{
  background: #D8E4FF;
  border-color: {colors['primaryHover']};
  padding-top: 1px;
}}
QPushButton[variant="ghost"] {{
  min-height: {button['height']}px;
  border: 1px solid {button['variants']['ghost']['border']};
  border-radius: {button['radius']}px;
  padding: 0 12px;
  background: {button['variants']['ghost']['background']};
  color: {button['variants']['ghost']['foreground']};
}}
QPushButton[variant="ghost"]:hover {{
  background: {button['variants']['ghost']['hover']};
}}
QPushButton[variant="ghost"]:pressed {{
  background: {colors['primarySoft']};
  color: {colors['primaryHover']};
  padding-top: 1px;
}}
QPushButton[variant="danger"] {{
  min-height: {button['height']}px;
  border: 1px solid {button['variants']['danger']['border']};
  border-radius: {button['radius']}px;
  padding: 0 16px;
  background: {button['variants']['danger']['background']};
  color: {button['variants']['danger']['foreground']};
  font-weight: 600;
}}
QPushButton[variant="danger"]:hover {{
  background: {button['variants']['danger']['hover']};
  border-color: {button['variants']['danger']['hover']};
}}
QPushButton[variant="danger"]:pressed {{
  background: #991B1B;
  border-color: #991B1B;
  padding-top: 1px;
}}
QLineEdit[component="input"], QLineEdit[component="search"] {{
  min-height: {input_component['height']}px;
  border: 1px solid {colors['border']};
  border-radius: {input_component['radius']}px;
  padding: 0 14px;
  background: {colors['surface']};
  color: {colors['textMain']};
}}
QLineEdit[component="input"]:focus, QLineEdit[component="search"]:focus {{
  border: 1px solid {input_component['focusBorder']};
}}
QLabel[badge="draft"] {{ background: {badge['draft']['background']}; color: {badge['draft']['foreground']}; border-radius: 10px; padding: 3px 8px; }}
QLabel[badge="ready"] {{ background: {badge['ready']['background']}; color: {badge['ready']['foreground']}; border-radius: 10px; padding: 3px 8px; }}
QLabel[badge="review"] {{ background: {badge['review']['background']}; color: {badge['review']['foreground']}; border-radius: 10px; padding: 3px 8px; }}
QLabel[badge="revision"] {{ background: {badge['revision']['background']}; color: {badge['revision']['foreground']}; border-radius: 10px; padding: 3px 8px; }}
QLabel[badge="accepted"] {{ background: {badge['accepted']['background']}; color: {badge['accepted']['foreground']}; border-radius: 10px; padding: 3px 8px; }}
QLabel[badge="rejected"] {{ background: {badge['rejected']['background']}; color: {badge['rejected']['foreground']}; border-radius: 10px; padding: 3px 8px; }}
QLabel[badge="archived"] {{ background: {badge['archived']['background']}; color: {badge['archived']['foreground']}; border-radius: 10px; padding: 3px 8px; }}
QLabel[feedback="working"] {{ background: {colors['primarySoft']}; color: {colors['primaryHover']}; border-radius: 8px; padding: 4px 8px; }}
QLabel[feedback="success"] {{ background: #DCFCE7; color: {colors['success']}; border-radius: 8px; padding: 4px 8px; }}
QLabel[feedback="error"] {{ background: #FEE2E2; color: {colors['danger']}; border-radius: 8px; padding: 4px 8px; }}
QLabel#pageTitleLabel {{ font-size: {title_points:g}pt; font-weight: 700; }}
""".strip()


def refresh_style(widget: QWidget) -> None:
    """Re-polish one widget after dynamic Qt properties change."""

    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def set_feedback(widget: QWidget, state: str | None, text: str | None = None) -> None:
    """Set a visible interaction feedback state on a QLabel-like widget."""

    if text is not None and hasattr(widget, "setText"):
        widget.setText(text)
    widget.setProperty("feedback", state or "")
    refresh_style(widget)


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


class _ExistingRootLoader(QUiLoader):
    def __init__(self, root: QWidget) -> None:
        super().__init__()
        self._root = root

    def createWidget(self, class_name, parent=None, name=""):
        if parent is None:
            self._root.setObjectName(name)
            return self._root
        return super().createWidget(class_name, parent, name)


def load_ui_into(filename: str, root: QWidget) -> None:
    """Populate an existing root widget from a Designer-owned layout."""

    path = files("research_workspace.presentation").joinpath("ui", filename)
    ui_file = QFile(str(path))
    if not ui_file.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(f"Unable to open UI resource: {filename}")
    try:
        loaded = _ExistingRootLoader(root).load(ui_file)
    finally:
        ui_file.close()
    if loaded is not root:
        raise RuntimeError(f"Unable to populate UI resource: {filename}")
    root.setStyleSheet(f"{root.styleSheet()}\n{_token_stylesheet()}")
