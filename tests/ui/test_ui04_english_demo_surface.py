import re
from types import SimpleNamespace
from uuid import uuid4

from PySide6.QtWidgets import QWidget

from research_workspace.presentation.dialogs.idea_editor_dialog import IdeaEditorDialog
from research_workspace.presentation.dialogs.paper_editor_dialog import PaperEditorDialog
from research_workspace.presentation import load_ui_resource
from research_workspace.presentation.pages.ideas_page import IdeasPage
from research_workspace.presentation.pages.overview_page import SUBMISSION_STATUS_TEXT
from research_workspace.presentation.pages.papers_page import PapersPage


FORBIDDEN_TEXT = re.compile(
    r"[\u4e00-\u9fff]|"
    r"譁|蜈|蠅|蟇|隶|謳|郛|遘|諱|豁|螳|咲|蛻|騾|遽|"
    r"Row version|Current version|Markdown content|repository|database",
    re.IGNORECASE,
)


def _visible_widget_text(root) -> str:
    texts = []
    for widget in (root, *root.findChildren(QWidget)):
        for getter in ("text", "windowTitle", "placeholderText"):
            method = getattr(widget, getter, None)
            if callable(method):
                value = method()
                if value:
                    texts.append(str(value))
    return "\n".join(texts)


def test_demo_flow_loaded_ui_is_zh_cn_friend_surface(qtbot):
    widgets = [
        load_ui_resource("main_window.ui"),
        load_ui_resource("overview_page.ui"),
        load_ui_resource("papers_page.ui"),
        load_ui_resource("paper_editor_dialog.ui"),
        load_ui_resource("ideas_page.ui"),
        load_ui_resource("idea_editor_dialog.ui"),
        load_ui_resource("settings_page.ui"),
    ]
    for widget in widgets:
        qtbot.addWidget(widget)

    joined = "\n".join(_visible_widget_text(widget) for widget in widgets)

    assert not re.search(
        r"Dashboard|Papers|Create Paper|Research Analysis|Analyze with AI|"
        r"Idea Library|Idea Detail|Save Idea|Next Step",
        joined,
    )
    for term in (
        "研究工作台",
        "总览",
        "论文",
        "论文列表",
        "新建论文",
        "研究分析",
        "摘要",
        "关键观点",
        "建议想法",
        "创建想法",
        "保存想法",
        "想法库",
        "想法详情",
        "下一步",
        "用 AI 分析",
        "AI 设置",
    ):
        assert term in joined


class Query:
    def __init__(self, rows=()):
        self.rows = tuple(rows)

    def project(self, *, include_deleted=False):
        return self.rows


class Actions:
    def delete_paper(self, paper_id): ...
    def restore_paper(self, paper_id): ...
    def delete_idea(self, idea_id): ...
    def restore_idea(self, idea_id): ...


def paper_row():
    return SimpleNamespace(
        id=uuid4(),
        title="Transformer Survey",
        status="active",
        current_version_id=None,
        row_version=1,
        actions=("edit", "soft_delete"),
        updated_at="2026-07-18T10:00:00Z",
    )


def idea_row():
    return SimpleNamespace(
        id=uuid4(),
        title="Resultative Complement Theory",
        content="A compact research idea.",
        origin_type="claim",
        status="unused",
        row_version=1,
        actions=("edit", "soft_delete"),
        updated_at="2026-07-18T10:00:00Z",
    )


def test_demo_flow_runtime_text_is_zh_cn_friend(qtbot):
    services = SimpleNamespace(
        get_papers=Query((paper_row(),)),
        get_ideas=Query((idea_row(),)),
        crud_actions=Actions(),
    )
    paper_page = PapersPage(services)
    idea_page = IdeasPage(services)
    paper_dialog = PaperEditorDialog(services)
    idea_dialog = IdeaEditorDialog(services)
    for widget in (paper_page.widget, idea_page.widget, paper_dialog, idea_dialog):
        qtbot.addWidget(widget)

    paper_page.list_view.setCurrentRow(0)
    idea_page.list_view.setCurrentRow(0)
    paper_page._update_actions()
    idea_page._update_actions()

    runtime_text = "\n".join(
        (
            paper_page.metadata_text_label.text(),
            paper_page.research_analysis_text_label.text(),
            idea_page.ai_suggestions_text_label.text(),
            paper_dialog.windowTitle(),
            paper_dialog.recovery_status_label.text(),
            idea_dialog.windowTitle(),
            idea_dialog.recovery_status_label.text(),
            *SUBMISSION_STATUS_TEXT.values(),
        )
    )

    assert not re.search(
        r"Authors not added|Year not added|No analysis yet|No suggestions yet|"
        r"Create Paper|Create Idea|Save Idea",
        runtime_text,
    )
    assert "作者未填写" in paper_page.metadata_text_label.text()
    assert "年份未填写" in paper_page.metadata_text_label.text()
