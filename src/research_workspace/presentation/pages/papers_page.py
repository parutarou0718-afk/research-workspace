"""Thin Paper page controller."""

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QFrame

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.idea_editor_dialog import IdeaEditorDialog
from research_workspace.presentation.dialogs.paper_editor_dialog import PaperEditorDialog
from research_workspace.presentation.view_models.papers import PapersViewModel


class CrudPageController:
    def _require_ui_thread(self):
        if QThread.currentThread() is not self.widget.thread():
            raise RuntimeError("UI_UPDATE_OUTSIDE_QT_THREAD")

    def _selected(self):
        index = self.table.currentRow()
        return self.view_model.rows[index] if 0 <= index < len(self.view_model.rows) else None

    def _standard_actions(self):
        row = self._selected()
        actions = () if row is None else row.actions
        self.edit_button.setEnabled("edit" in actions)
        self.delete_button.setEnabled("soft_delete" in actions)
        self.restore_button.setEnabled("restore" in actions)


class PapersPage(CrudPageController):
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("papers_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "papersScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.search_line_edit = require_child(
            self.widget, QLineEdit, "paperSearchLineEdit"
        )
        self.list_view = require_child(self.widget, QListWidget, "papersListView")
        self.empty_state = require_child(self.widget, QFrame, "papersEmptyStateCard")
        self.empty_title_label = require_child(
            self.widget, QLabel, "papersEmptyTitleLabel"
        )
        self.empty_body_label = require_child(
            self.widget, QLabel, "papersEmptyBodyLabel"
        )
        self.empty_action_button = require_child(
            self.widget, QPushButton, "papersEmptyActionButton"
        )
        self.detail_card = require_child(self.widget, QFrame, "paperDetailCard")
        self.detail_title_label = require_child(
            self.widget, QLabel, "paperDetailTitleLabel"
        )
        self.status_badge_label = require_child(
            self.widget, QLabel, "paperStatusBadgeLabel"
        )
        self.metadata_text_label = require_child(
            self.widget, QLabel, "paperMetadataTextLabel"
        )
        self.abstract_text_label = require_child(
            self.widget, QLabel, "paperAbstractTextLabel"
        )
        self.research_notes_text_label = require_child(
            self.widget, QLabel, "paperResearchNotesTextLabel"
        )
        self.timeline_text_label = require_child(
            self.widget, QLabel, "paperTimelineTextLabel"
        )
        self.research_analysis_title_label = require_child(
            self.widget, QLabel, "paperResearchAnalysisTitleLabel"
        )
        self.research_analysis_text_label = require_child(
            self.widget, QLabel, "paperResearchAnalysisTextLabel"
        )
        self.analyze_with_ai_button = require_child(
            self.widget, QPushButton, "paperAnalyzeWithAiButton"
        )
        self.research_analysis_milestone_label = require_child(
            self.widget, QLabel, "paperResearchAnalysisMilestoneLabel"
        )
        self.next_step_title_label = require_child(
            self.widget, QLabel, "paperNextStepTitleLabel"
        )
        self.next_step_text_label = require_child(
            self.widget, QLabel, "paperNextStepTextLabel"
        )
        self.create_idea_button = require_child(
            self.widget, QPushButton, "paperCreateIdeaButton"
        )
        self.related_ideas_text_label = require_child(
            self.widget, QLabel, "paperRelatedIdeasTextLabel"
        )
        self.related_papers_text_label = require_child(
            self.widget, QLabel, "paperRelatedPapersTextLabel"
        )
        self.relations_text_label = require_child(
            self.widget, QLabel, "paperRelationsTextLabel"
        )
        self.new_button = require_child(self.widget, QPushButton, "newPaperButton")
        self.edit_button = require_child(self.widget, QPushButton, "editPaperButton")
        self.delete_button = require_child(self.widget, QPushButton, "deletePaperButton")
        self.restore_button = require_child(self.widget, QPushButton, "restorePaperButton")
        self.view_model = PapersViewModel(
            getattr(services, "get_papers", None),
            getattr(services, "crud_actions", None),
        )
        self.new_button.clicked.connect(self.open_new)
        self.empty_action_button.clicked.connect(self.open_new)
        self.create_idea_button.clicked.connect(self.open_new_idea)
        self.edit_button.clicked.connect(self.open_edit)
        self.delete_button.clicked.connect(self.delete_selected)
        self.restore_button.clicked.connect(self.restore_selected)
        self.list_view.itemSelectionChanged.connect(self._update_actions)
        self.search_line_edit.textChanged.connect(lambda _text: self._render_rows())
        self._visible_rows = ()
        self.refresh()

    def _selected(self):
        index = self.list_view.currentRow()
        return self._visible_rows[index] if 0 <= index < len(self._visible_rows) else None

    def refresh(self):
        self._require_ui_thread()
        self.view_model.refresh()
        self._render_rows()
        self._update_actions()
        return self.view_model.rows

    def _render_rows(self) -> None:
        search = self.search_line_edit.text().strip().casefold()
        rows = tuple(
            row
            for row in self.view_model.rows
            if not search
            or search in row.title.casefold()
            or search in str(row.status).casefold()
        )
        self._visible_rows = rows
        self.list_view.clear()
        for row in rows:
            item = QListWidgetItem(
                f"{row.title}\n{_status_label(row.status)} · Version {row.row_version}"
            )
            self.list_view.addItem(item)
        has_rows = bool(rows)
        self.empty_state.setVisible(not has_rows)
        self.detail_card.setVisible(has_rows)
        self.list_view.setVisible(has_rows)
        if has_rows and self.list_view.currentRow() < 0:
            self.list_view.setCurrentRow(0)
        self._update_detail()

    def open_new(self):
        PaperEditorDialog(self.services, parent=self.widget).exec()
        self.refresh()

    def open_new_idea(self):
        IdeaEditorDialog(self.services, parent=self.widget).exec()

    def open_edit(self):
        row = self._selected()
        if row is not None and "edit" in row.actions:
            PaperEditorDialog(self.services, row, self.widget).exec()
            self.refresh()

    def delete_selected(self):
        row = self._selected()
        if row is not None and "soft_delete" in row.actions:
            self.view_model.delete(row)
            self.refresh()

    def restore_selected(self):
        row = self._selected()
        if row is not None and "restore" in row.actions:
            self.view_model.restore(row)
            self.refresh()

    def _update_actions(self):
        row = self._selected()
        actions = () if row is None else row.actions
        self.edit_button.setEnabled("edit" in actions)
        self.delete_button.setEnabled("soft_delete" in actions)
        self.restore_button.setEnabled("restore" in actions)
        self._update_detail()

    def _update_detail(self) -> None:
        row = self._selected()
        if row is None:
            self.detail_title_label.setText("选择一篇论文")
            self.status_badge_label.setText("Draft")
            self.status_badge_label.setProperty("badge", "draft")
            self.metadata_text_label.setText("Year, authors and version metadata will appear here.")
            return
        self.detail_title_label.setText(row.title)
        self.status_badge_label.setText(_status_label(row.status))
        self.status_badge_label.setProperty("badge", _status_badge(row.status))
        self.status_badge_label.style().unpolish(self.status_badge_label)
        self.status_badge_label.style().polish(self.status_badge_label)
        self.metadata_text_label.setText(
            f"Status: {_status_label(row.status)} · Row version: {row.row_version} · Current version: {row.current_version_id or 'None'}"
        )
        self.abstract_text_label.setText("No abstract captured yet.")
        self.research_notes_text_label.setText("Notes linked to this paper will appear here.")
        self.timeline_text_label.setText("Creation, edits and decisions will appear here.")
        self.research_analysis_title_label.setText("Research Analysis")
        self.research_analysis_text_label.setText(
            "No analysis yet.\n\n"
            "Analyze this paper to generate:\n\n"
            "• Summary\n\n"
            "• Key claims\n\n"
            "• Suggested ideas"
        )
        self.research_analysis_milestone_label.setText(
            "Available in the next milestone."
        )
        self.next_step_title_label.setText("Next Step")
        self.next_step_text_label.setText("Capture an idea from this paper.")
        self.related_ideas_text_label.setText("No related ideas yet.")
        self.related_papers_text_label.setText("No related papers yet.")
        self.relations_text_label.setText("Known relations and evidence will appear here.")


def _status_label(status: str) -> str:
    return {
        "active": "Active",
        "draft": "Draft",
        "archived": "Archived",
        "deleted": "Archived",
        "accepted": "Accepted",
        "rejected": "Rejected",
        "revision": "Revision",
    }.get(str(status), str(status).replace("_", " ").title())


def _status_badge(status: str) -> str:
    return {
        "active": "ready",
        "draft": "draft",
        "archived": "archived",
        "deleted": "archived",
        "accepted": "accepted",
        "rejected": "rejected",
        "revision": "revision",
    }.get(str(status), "draft")
