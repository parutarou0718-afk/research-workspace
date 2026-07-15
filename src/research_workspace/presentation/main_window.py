"""Designer-owned main-window shell and explicit navigation controller."""

from PySide6.QtWidgets import QMainWindow, QPushButton, QStackedWidget

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.pages.conferences_page import ConferencesPage
from research_workspace.presentation.pages.grants_page import GrantsPage
from research_workspace.presentation.pages.ideas_page import IdeasPage
from research_workspace.presentation.pages.overview_page import OverviewPage
from research_workspace.presentation.pages.papers_page import PapersPage
from research_workspace.presentation.pages.settings_page import SettingsPage
from research_workspace.presentation.pages.submissions_page import SubmissionsPage


PAGE_TYPES = {
    "overview": OverviewPage,
    "papers": PapersPage,
    "ideas": IdeasPage,
    "submissions": SubmissionsPage,
    "conferences": ConferencesPage,
    "grants": GrantsPage,
    "settings": SettingsPage,
}


class MainWindow(QMainWindow):
    def __init__(self, services):
        super().__init__()
        shell = load_ui_resource("main_window.ui")
        if not isinstance(shell, QMainWindow):
            raise RuntimeError("main_window.ui root must be a QMainWindow")
        self.setObjectName(shell.objectName())
        self.setWindowTitle(shell.windowTitle())
        self.setMinimumSize(shell.minimumSize())
        self.resize(shell.size())
        self.setCentralWidget(shell.takeCentralWidget())

        self.page_stack = require_child(self, QStackedWidget, "pageStack")
        self.pages = {key: page_type(services) for key, page_type in PAGE_TYPES.items()}
        self.navigation_buttons = {
            key: require_child(self, QPushButton, f"nav{key.title()}Button")
            for key in PAGE_TYPES
        }
        for key, page in self.pages.items():
            self.page_stack.addWidget(page.widget)
            self.navigation_buttons[key].clicked.connect(
                lambda checked=False, page_key=key: self.show_page(page_key)
            )
        self.show_page("overview")

    def show_page(self, page_key: str) -> None:
        if page_key not in self.pages:
            raise KeyError(page_key)
        self.page_stack.setCurrentWidget(self.pages[page_key].widget)
        for key, button in self.navigation_buttons.items():
            button.setProperty("active", key == page_key)
            button.style().unpolish(button)
            button.style().polish(button)
