from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

PAGE_KEYS = (
    "overview",
    "papers",
    "ideas",
    "relations",
    "submissions",
    "conferences",
    "grants",
    "imports",
    "monitoring",
    "version_candidates",
    "settings",
)


def _button_name(key: str) -> str:
    return f"nav{''.join(part.title() for part in key.split('_'))}Button"


def test_every_navigation_destination_is_reachable(qtbot):
    from research_workspace.presentation import main_window

    assert hasattr(main_window, "MainWindow")
    MainWindow = main_window.MainWindow
    window = MainWindow(services=object())
    qtbot.addWidget(window)

    for key in PAGE_KEYS:
        button = window.findChild(QPushButton, _button_name(key))
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert window.page_stack.currentWidget() is window.pages[key].widget


def test_active_navigation_state_follows_page(qtbot):
    from research_workspace.presentation import main_window

    assert hasattr(main_window, "MainWindow")
    MainWindow = main_window.MainWindow
    window = MainWindow(services=object())
    qtbot.addWidget(window)

    for key in PAGE_KEYS:
        window.show_page(key)
        active = [button for button in window.navigation_buttons.values() if button.property("active")]
        assert active == [window.navigation_buttons[key]]
