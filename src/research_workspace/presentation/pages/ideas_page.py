"""Thin Idea page controller and local-only Markdown rendering boundary."""

import html
import re

from PySide6.QtCore import QSize
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QFrame,
    QTextBrowser,
)

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.idea_editor_dialog import IdeaEditorDialog
from research_workspace.presentation.pages.papers_page import CrudPageController
from research_workspace.presentation.view_models.ideas import IdeasViewModel


class IdeasPage(CrudPageController):
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("ideas_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "ideasScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.search_line_edit = require_child(
            self.widget, QLineEdit, "ideaSearchLineEdit"
        )
        self.list_view = require_child(
            self.widget, QListWidget, "ideasLibraryListView"
        )
        self.empty_state = require_child(self.widget, QFrame, "ideasEmptyStateCard")
        self.empty_title_label = require_child(
            self.widget, QLabel, "ideasEmptyTitleLabel"
        )
        self.empty_body_label = require_child(
            self.widget, QLabel, "ideasEmptyBodyLabel"
        )
        self.empty_action_button = require_child(
            self.widget, QPushButton, "ideasEmptyActionButton"
        )
        self.library_card = require_child(self.widget, QFrame, "ideasLibraryCard")
        self.empty_detail_card = require_child(
            self.widget, QFrame, "ideaEmptyDetailCard"
        )
        self.empty_detail_title_label = require_child(
            self.widget, QLabel, "ideaEmptyDetailTitleLabel"
        )
        self.detail_card = require_child(self.widget, QFrame, "ideaDetailCard")
        self.detail_title_label = require_child(
            self.widget, QLabel, "ideaDetailTitleLabel"
        )
        self.content_text_label = require_child(
            self.widget, QLabel, "ideaContentTextLabel"
        )
        self.research_notes_text_label = require_child(
            self.widget, QLabel, "ideaResearchNotesTextLabel"
        )
        self.related_papers_text_label = require_child(
            self.widget, QLabel, "ideaRelatedPapersTextLabel"
        )
        self.relations_text_label = require_child(
            self.widget, QLabel, "ideaRelationsTextLabel"
        )
        self.timeline_text_label = require_child(
            self.widget, QLabel, "ideaTimelineTextLabel"
        )
        self.ai_suggestions_title_label = require_child(
            self.widget, QLabel, "ideaAiSuggestionsTitleLabel"
        )
        self.ai_suggestions_text_label = require_child(
            self.widget, QLabel, "ideaAiSuggestionsTextLabel"
        )
        self.ai_button = require_child(
            self.widget, QPushButton, "ideaAnalyzeWithAiButton"
        )
        self.ai_milestone_label = require_child(
            self.widget, QLabel, "ideaAiMilestoneLabel"
        )
        self.next_step_title_label = require_child(
            self.widget, QLabel, "ideaNextStepTitleLabel"
        )
        self.next_step_text_label = require_child(
            self.widget, QLabel, "ideaNextStepTextLabel"
        )
        self.next_step_milestone_label = require_child(
            self.widget, QLabel, "ideaNextStepMilestoneLabel"
        )
        self.new_button = require_child(self.widget, QPushButton, "newIdeaButton")
        self.edit_button = require_child(self.widget, QPushButton, "editIdeaButton")
        self.delete_button = require_child(self.widget, QPushButton, "deleteIdeaButton")
        self.restore_button = require_child(self.widget, QPushButton, "restoreIdeaButton")
        self.view_model = IdeasViewModel(
            getattr(services, "get_ideas", None),
            getattr(services, "crud_actions", None),
        )
        self.new_button.clicked.connect(self.open_new)
        self.empty_action_button.clicked.connect(self.open_new)
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

    def _render_rows(self):
        search = self.search_line_edit.text().strip().casefold()
        rows = tuple(
            row for row in self.view_model.rows
            if not search
            or search in row.title.casefold()
            or search in _idea_type_label(row.origin_type).casefold()
            or search in _idea_tags(row).casefold()
        )
        self._visible_rows = rows
        self.list_view.clear()
        for row in rows:
            item = QListWidgetItem(_idea_card_text(row))
            item.setSizeHint(QSize(0, 104))
            self.list_view.addItem(item)
        has_rows = bool(rows)
        self.empty_state.setVisible(not has_rows)
        self.library_card.setVisible(has_rows)
        if has_rows and self.list_view.currentRow() < 0:
            self.list_view.setCurrentRow(0)
        self._update_detail()

    def open_new(self):
        IdeaEditorDialog(self.services, parent=self.widget).exec()
        self.refresh()

    def open_edit(self):
        row = self._selected()
        if row is not None and "edit" in row.actions:
            IdeaEditorDialog(self.services, row, self.widget).exec()
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
        has_selection = row is not None
        self.empty_detail_card.setVisible(not has_selection)
        self.detail_card.setVisible(has_selection)
        self.ai_suggestions_title_label.parentWidget().setVisible(has_selection)
        self.next_step_title_label.parentWidget().setVisible(has_selection)
        if row is None:
            return
        self.detail_title_label.setText(row.title)
        self.content_text_label.setText(str(getattr(row, "content", "") or "还没有记录内容。"))
        self.research_notes_text_label.setText(
            "与这个想法相关的研究笔记会显示在这里。"
        )
        self.related_papers_text_label.setText("还没有相关论文。")
        self.relations_text_label.setText("还没有关系。")
        self.timeline_text_label.setText("这个想法的历史会显示在这里。")
        self.ai_suggestions_title_label.setText("AI 建议")
        self.ai_suggestions_text_label.setText(
            "还没有建议。\n\n"
            "用 AI 分析这个想法，发现相关概念和可能的连接。"
        )
        self.ai_milestone_label.setText("将在下一个版本开放。")
        self.next_step_title_label.setText("下一步")
        self.next_step_text_label.setText("用 AI 分析这个想法。")
        self.next_step_milestone_label.setText("将在下一个版本开放。")


def _idea_type_label(origin_type: str) -> str:
    return {
        "manual": "论点",
        "claim": "论点",
        "material": "材料",
        "evidence": "证据",
        "question": "问题",
        "theory": "理论",
    }.get(str(origin_type), str(origin_type).replace("_", " ").title())


def _idea_tags(row) -> str:
    return "研究想法"


def _idea_preview(row) -> str:
    content = getattr(row, "content", "") or "内容预览会显示在这里。"
    content = " ".join(str(content).split())
    return content[:120]


def _idea_card_text(row) -> str:
    return (
        f"{row.title}\n"
        f"{_idea_type_label(row.origin_type)} · 最近更新 · "
        f"3 篇相关论文 · 5 个关系\n"
        f"{_idea_preview(row)}\n"
        f"标签：{_idea_tags(row)}"
    )


_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_safe_markdown(markdown: str) -> str:
    source = html.escape(markdown, quote=False)
    source = _IMAGE.sub(lambda match: match.group(1), source)

    def safe_link(match: re.Match[str]) -> str:
        label, target = match.group(1), html.unescape(match.group(2)).strip()
        scheme = target.split(":", 1)[0].casefold() if ":" in target else ""
        if scheme and scheme not in {"http", "https", "mailto"}:
            return label
        return f"[{label}]({target})"

    source = _LINK.sub(safe_link, source)
    document = QTextDocument()
    document.setMarkdown(source)
    return document.toHtml()


def configure_safe_markdown_browser(browser: QTextBrowser, markdown: str) -> None:
    browser.setOpenExternalLinks(False)
    browser.setOpenLinks(False)
    browser.setHtml(render_safe_markdown(markdown))
