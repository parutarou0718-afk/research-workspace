"""Overview page controller."""

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
)

from research_workspace.presentation import load_ui_resource, require_child


class OverviewPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("overview_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "overviewScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.revision_count_label = require_child(self.widget, QLabel, "revisionCountLabel")
        self.revision_help_label = require_child(self.widget, QLabel, "revisionHelpLabel")
        self.ready_count_label = require_child(self.widget, QLabel, "readyCountLabel")
        self.ready_help_label = require_child(self.widget, QLabel, "readyHelpLabel")
        self.upcoming_conference_count_label = require_child(
            self.widget, QLabel, "upcomingConferenceCountLabel"
        )
        self.upcoming_grant_count_label = require_child(
            self.widget, QLabel, "upcomingGrantCountLabel"
        )
        self.conference_help_label = require_child(
            self.widget, QLabel, "conferenceHelpLabel"
        )
        self.grant_help_label = require_child(self.widget, QLabel, "grantHelpLabel")
        self.suggestions_list = require_child(self.widget, QListWidget, "suggestionsListView")
        self.submission_table = require_child(
            self.widget, QTableWidget, "submissionOverviewTable"
        )
        self.activities_list = require_child(self.widget, QListWidget, "activitiesListView")
        self.focus_items_list = require_child(self.widget, QListWidget, "focusItemsListView")
        self.focus_progress = require_child(self.widget, QProgressBar, "focusProgressBar")
        self.organize_button = require_child(self.widget, QPushButton, "organizeNowButton")
        self.view_all_suggestions_button = require_child(
            self.widget, QPushButton, "viewAllSuggestionsButton"
        )
        self.quick_idea_line_edit = require_child(
            self.widget, QLineEdit, "quickIdeaLineEdit"
        )
        self.save_idea_button = require_child(self.widget, QPushButton, "saveIdeaButton")
        self.idea_argument_button = require_child(
            self.widget, QPushButton, "ideaArgumentCategoryButton"
        )
        self.idea_material_button = require_child(
            self.widget, QPushButton, "ideaMaterialCategoryButton"
        )
        self.idea_question_button = require_child(
            self.widget, QPushButton, "ideaQuestionCategoryButton"
        )
