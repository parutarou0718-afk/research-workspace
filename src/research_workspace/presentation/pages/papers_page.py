"""Thin Paper page controller."""

from PySide6.QtCore import QTimer, QSize, QThread
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from research_workspace.application.ports.ai_provider import (
    AIProviderError,
    PaperAnalysis,
    PaperAnalysisRequest,
    SuggestedIdea,
)
from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.idea_editor_dialog import IdeaEditorDialog
from research_workspace.presentation.dialogs.paper_editor_dialog import PaperEditorDialog
from research_workspace.presentation.localization import zh_error
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
        self.list_card = require_child(self.widget, QFrame, "papersListCard")
        self.workspace_layout = self.widget.findChild(
            QHBoxLayout, "papersWorkspaceHorizontalLayout"
        )
        if self.workspace_layout is None:
            raise RuntimeError("Missing required layout: papersWorkspaceHorizontalLayout")
        self.workspace_layout.setStretch(0, 4)
        self.workspace_layout.setStretch(1, 7)
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
        self.research_analysis_layout = self.widget.findChild(
            QVBoxLayout, "paperResearchAnalysisVerticalLayout"
        )
        if self.research_analysis_layout is None:
            raise RuntimeError(
                "Missing required layout: paperResearchAnalysisVerticalLayout"
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
        self.analyze_with_ai_button.clicked.connect(self._handle_ai_button)
        self.edit_button.clicked.connect(self.open_edit)
        self.delete_button.clicked.connect(self.delete_selected)
        self.restore_button.clicked.connect(self.restore_selected)
        self.list_view.itemSelectionChanged.connect(self._update_actions)
        self.search_line_edit.textChanged.connect(lambda _text: self._render_rows())
        self._visible_rows = ()
        self._ai_handle = None
        self.suggestion_buttons = []
        self._ai_poll_timer = QTimer(self.widget)
        self._ai_poll_timer.setInterval(50)
        self._ai_poll_timer.timeout.connect(self._poll_ai_analysis)
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
                f"{row.title}\n"
                f"作者未填写 | 年份未填写\n"
                f"状态：{_status_label(row.status)}"
            )
            item.setSizeHint(QSize(0, 92))
            self.list_view.addItem(item)
        has_rows = bool(rows)
        self.empty_state.setVisible(not has_rows)
        self.list_card.setVisible(has_rows)
        self.detail_card.setVisible(has_rows)
        self.list_view.setVisible(has_rows)
        self.edit_button.setVisible(has_rows)
        self.delete_button.setVisible(has_rows)
        self.restore_button.setVisible(has_rows)
        if has_rows and self.list_view.currentRow() < 0:
            self.list_view.setCurrentRow(0)
        self._update_detail()

    def open_new(self):
        PaperEditorDialog(self.services, parent=self.widget).exec()
        self.refresh()

    def open_new_idea(self):
        IdeaEditorDialog(self.services, parent=self.widget).exec()

    def _open_suggested_idea(self, suggestion: SuggestedIdea) -> None:
        IdeaEditorDialog(
            self.services,
            parent=self.widget,
            initial_title=suggestion.title,
            initial_content=suggestion.content,
        ).exec()

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
            self.status_badge_label.setText("草稿")
            self.status_badge_label.setProperty("badge", "draft")
            self.metadata_text_label.setText(
                "年份、作者和状态信息会显示在这里。"
            )
            return
        self.detail_title_label.setText(row.title)
        self.status_badge_label.setText(_status_label(row.status))
        self.status_badge_label.setProperty("badge", _status_badge(row.status))
        self.status_badge_label.style().unpolish(self.status_badge_label)
        self.status_badge_label.style().polish(self.status_badge_label)
        self.metadata_text_label.setText(
            f"状态：{_status_label(row.status)}\n"
            "作者未填写\n"
            "年份未填写"
        )
        self.abstract_text_label.setText("还没有记录摘要。")
        self.research_notes_text_label.setText("与这篇论文相关的笔记会显示在这里。")
        self.timeline_text_label.setText("创建、编辑和决策记录会显示在这里。")
        self.research_analysis_title_label.setText("研究分析")
        self._render_ai_ready_state()
        self.next_step_title_label.setText("下一步")
        self.next_step_text_label.setText("从这篇论文中记录一个想法。")
        self.related_ideas_text_label.setText("还没有相关想法。")
        self.related_papers_text_label.setText("还没有相关论文。")
        self.relations_text_label.setText("已记录的关系和证据会显示在这里。")

    def _ai_service(self):
        return getattr(self.services, "paper_ai_analysis", None)

    def _ai_is_configured(self) -> bool:
        service = self._ai_service()
        is_configured = getattr(service, "is_configured", None)
        return bool(is_configured()) if is_configured is not None else False

    def _render_ai_ready_state(self) -> None:
        self._clear_suggestion_buttons()
        self.analyze_with_ai_button.setEnabled(True)
        if not self._ai_is_configured():
            self.research_analysis_text_label.setText("AI 尚未配置。")
            self.analyze_with_ai_button.setText("打开 AI 设置")
            self.research_analysis_milestone_label.setText(
                "请先在设置中填写 AI 接口信息。"
            )
            return
        self.research_analysis_text_label.setText(
            "还没有分析结果。\n"
            "用 AI 分析这篇论文，可生成：\n"
            "• 摘要\n"
            "• 关键观点\n"
            "• 建议想法"
        )
        self.analyze_with_ai_button.setText("用 AI 分析")
        self.research_analysis_milestone_label.clear()

    def _handle_ai_button(self) -> None:
        if not self._ai_is_configured():
            show_page = getattr(self.widget.window(), "show_page", None)
            if show_page is not None:
                show_page("settings")
            return
        self._start_ai_analysis()

    def _paper_analysis_request(self) -> PaperAnalysisRequest | None:
        row = self._selected()
        if row is None:
            return None
        return PaperAnalysisRequest(
            title=row.title,
            authors="",
            year="",
            abstract=self.abstract_text_label.text(),
            research_notes=self.research_notes_text_label.text(),
        )

    def _start_ai_analysis(self) -> None:
        request = self._paper_analysis_request()
        service = self._ai_service()
        analyze_async = getattr(service, "analyze_async", None)
        if request is None or analyze_async is None:
            return
        self._clear_suggestion_buttons()
        self.research_analysis_text_label.setText("正在分析论文…")
        self.research_analysis_milestone_label.clear()
        self.analyze_with_ai_button.setEnabled(False)
        self._ai_handle = analyze_async(request)
        self._ai_poll_timer.start()

    def _poll_ai_analysis(self) -> None:
        handle = self._ai_handle
        if handle is None or not handle.done:
            return
        self._ai_poll_timer.stop()
        self.analyze_with_ai_button.setEnabled(True)
        error = handle.error
        if error is not None:
            self._render_ai_failure(getattr(error, "message", str(error)))
            return
        try:
            self._render_ai_success(handle.result)
        except AIProviderError as exc:
            self._render_ai_failure(exc.message)

    def _render_ai_failure(self, message: str) -> None:
        self._clear_suggestion_buttons()
        self.research_analysis_text_label.setText(zh_error(message))
        self.analyze_with_ai_button.setText("重试")
        self.research_analysis_milestone_label.clear()

    def _render_ai_success(self, analysis: PaperAnalysis) -> None:
        self._clear_suggestion_buttons()
        claims = "\n".join(f"• {claim}" for claim in analysis.key_claims)
        ideas = "\n".join(f"• {idea.title}" for idea in analysis.suggested_ideas)
        self.research_analysis_text_label.setText(
            f"摘要\n{analysis.summary}\n\n"
            f"关键观点\n{claims}\n\n"
            f"建议想法\n{ideas}"
        )
        self.analyze_with_ai_button.setText("用 AI 分析")
        self.research_analysis_milestone_label.clear()
        insert_at = self.research_analysis_layout.indexOf(
            self.research_analysis_milestone_label
        )
        for suggestion in analysis.suggested_ideas:
            button = QPushButton("创建想法", self.widget)
            button.setProperty("variant", "primary")
            button.clicked.connect(
                lambda checked=False, idea=suggestion: self._open_suggested_idea(idea)
            )
            self.research_analysis_layout.insertWidget(insert_at, button)
            self.suggestion_buttons.append(button)
            insert_at += 1

    def _clear_suggestion_buttons(self) -> None:
        for button in self.suggestion_buttons:
            self.research_analysis_layout.removeWidget(button)
            button.deleteLater()
        self.suggestion_buttons = []


def _status_label(status: str) -> str:
    return {
        "active": "进行中",
        "draft": "草稿",
        "archived": "已归档",
        "deleted": "已归档",
        "accepted": "已接受",
        "rejected": "已拒绝",
        "revision": "返修中",
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
