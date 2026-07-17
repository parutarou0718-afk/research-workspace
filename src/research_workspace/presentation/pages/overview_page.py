"""Overview page controller."""

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidgetItem,
    QTableWidget,
)

from research_workspace.presentation import load_ui_resource, require_child


SUBMISSION_STATUS_TEXT = {
    "preparing": "Preparing",
    "ready": "Ready",
    "submitted": "Submitted",
    "editorial_review": "Editorial Review",
    "external_review": "External Review",
    "revision": "Revision",
    "accepted": "Accepted",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
    "no_response": "No Response",
}


def _human_date(value: str) -> str:
    return value.removesuffix("Z")[:10] if value else ""


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
        self.suggestions_empty_title = require_child(
            self.widget, QLabel, "suggestionsEmptyTitleLabel"
        )
        self.suggestions_empty_body = require_child(
            self.widget, QLabel, "suggestionsEmptyBodyLabel"
        )
        self.submission_table = require_child(
            self.widget, QTableWidget, "submissionOverviewTable"
        )
        self.submission_table.setShowGrid(False)
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
        query = getattr(services, "get_overview", None)
        if query is not None:
            self.render(query.execute())

    def render(self, view_model) -> None:
        self.revision_count_label.setText(str(view_model.revision_count))
        self.ready_count_label.setText(str(view_model.ready_count))
        self.upcoming_conference_count_label.setText(
            str(view_model.upcoming_conference_count)
        )
        self.upcoming_grant_count_label.setText(str(view_model.upcoming_grant_count))

        self.suggestions_list.clear()
        self.suggestions_list.addItems(view_model.suggestions)
        has_suggestions = bool(view_model.suggestions)
        self.suggestions_list.setVisible(has_suggestions)
        self.suggestions_empty_title.setVisible(not has_suggestions)
        self.suggestions_empty_body.setVisible(not has_suggestions)

        for widget, values in (
            (self.activities_list, view_model.activities),
            (self.focus_items_list, view_model.focus_items),
        ):
            widget.clear()
            widget.addItems(values)

        self.submission_table.setRowCount(len(view_model.submission_rows))
        for row_index, row_value in enumerate(view_model.submission_rows):
            columns = row_value.split(" | ")
            for column_index in range(self.submission_table.columnCount()):
                value = columns[column_index] if column_index < len(columns) else ""
                if column_index == 2:
                    value = SUBMISSION_STATUS_TEXT.get(value, value)
                elif column_index == 3:
                    value = _human_date(value)
                self.submission_table.setItem(
                    row_index, column_index, QTableWidgetItem(value)
                )
            self.submission_table.setRowHeight(row_index, 44)
        self.focus_progress.setValue(view_model.focus_progress)
