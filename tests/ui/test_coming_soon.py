import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QScrollBar,
    QSlider,
    QWidget,
)

@pytest.mark.parametrize(
    "module_name,class_name,title",
    [
        ("conferences_page", "ConferencesPage", "会议"),
        ("grants_page", "GrantsPage", "基金"),
    ],
)
def test_conference_and_grant_are_noninteractive_coming_soon_pages(
    qapp, module_name, class_name, title
):
    from importlib import import_module

    module = import_module(f"research_workspace.presentation.pages.{module_name}")
    assert hasattr(module, class_name)
    controller_type = getattr(module, class_name)
    controller = controller_type(services=object())
    labels = [label.text() for label in controller.widget.findChildren(QLabel)]
    assert title in labels
    assert "Coming Soon" in labels
    interactive_types = (
        QAbstractButton,
        QAbstractItemView,
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QSlider,
    )
    assert not any(
        control.isEnabled()
        for control_type in interactive_types
        for control in controller.widget.findChildren(control_type)
    )
    assert all(
        isinstance(widget, (QLabel, QScrollArea, QScrollBar))
        or type(widget) is QWidget
        for widget in controller.widget.findChildren(QWidget)
    )
