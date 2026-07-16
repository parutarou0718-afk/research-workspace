from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

PAGE_KEYS = (
    "overview",
    "papers",
    "ideas",
    "submissions",
    "imports",
    "conferences",
    "grants",
    "settings",
)


def test_every_navigation_destination_is_reachable(qtbot):
    from research_workspace.presentation import main_window

    assert hasattr(main_window, "MainWindow")
    MainWindow = main_window.MainWindow
    window = MainWindow(services=object())
    qtbot.addWidget(window)

    for key in PAGE_KEYS:
        button = window.findChild(QPushButton, f"nav{key.title()}Button")
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
