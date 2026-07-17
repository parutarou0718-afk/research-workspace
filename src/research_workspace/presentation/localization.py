"""Small zh-CN friend build presentation text map.

This branch intentionally does not introduce a full i18n framework.  It is a
single-purpose, presentation-layer localization pass for the portable Chinese
build so the same frozen application logic can be used by a Chinese-speaking
friend.
"""

from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QTableWidget,
    QWidget,
)


TEXT = {
    "Research Workspace": "研究工作台",
    "Dashboard": "总览",
    "Papers": "论文",
    "Ideas": "想法",
    "Relations": "关系",
    "Submissions": "投稿",
    "Conferences": "会议",
    "Grants": "基金",
    "Import Sources": "导入资料",
    "Source Monitoring": "资料监控",
    "Version Candidates": "版本候选",
    "Settings": "设置",
    "Local workspace · Offline first": "本地工作区 · 离线优先",
    "Focus on the research work that matters next.": "聚焦下一步最重要的研究任务。",
    "Organize Now": "立即整理",
    "In Revision": "返修中",
    "Manuscripts that need follow-up.": "需要继续跟进的稿件。",
    "Ready to Submit": "待投稿",
    "Work prepared but not submitted yet.": "已经准备好但尚未投稿的工作。",
    "Upcoming Conferences": "会议临近",
    "Important conferences coming soon.": "即将到来的重要会议。",
    "Grant Deadlines": "基金 DDL",
    "Applications to prepare ahead of time.": "需要提前准备的申请。",
    "AI Suggestions": "AI 建议",
    "No suggestions yet.": "暂时没有建议。",
    "Import papers or capture research notes to see analysis here.": "导入论文或记录研究笔记后，这里会显示分析结果。",
    "View Suggestions": "查看建议",
    "Quick Capture": "快速记录",
    "Capture a research note": "记录一条研究笔记",
    "Claim": "论点",
    "Source Note": "材料",
    "Question": "问题",
    "Capture": "记录",
    "Submission Overview": "投稿概览",
    "Paper": "论文",
    "Venue": "期刊 / 会议",
    "Status": "状态",
    "Deadline": "截止时间",
    "Action": "操作",
    "Recent Activity": "最近动态",
    "This Week's Focus": "本周重点",
    "Manage papers, notes, relations, and future research analysis.": "管理论文、笔记、关系，以及之后的研究分析。",
    "+ Create Paper": "+ 新建论文",
    "Search papers, authors, or tags": "搜索论文、作者或标签",
    "Year": "年份",
    "Tags": "标签",
    "No papers yet.": "还没有论文。",
    "Import or create your first paper to start building your research workspace.": "导入或新建第一篇论文，开始搭建你的研究工作台。",
    "Create Paper": "新建论文",
    "Paper List": "论文列表",
    "Edit": "编辑",
    "Move to Trash": "移入回收站",
    "Restore": "恢复",
    "Select a paper": "选择一篇论文",
    "Draft": "草稿",
    "Metadata": "基本信息",
    "Year, authors and version metadata will appear here.": "年份、作者和状态信息会显示在这里。",
    "Abstract": "摘要",
    "No abstract captured yet.": "还没有记录摘要。",
    "Research Analysis": "研究分析",
    "No analysis yet.\n\nAnalyze this paper to generate:\n\n• Summary\n\n• Key Claims\n\n• Suggested Ideas": "还没有分析结果。\n\n用 AI 分析这篇论文，可生成：\n\n• 摘要\n\n• 关键观点\n\n• 建议想法",
    "Analyze with AI": "用 AI 分析",
    "Available in the next milestone.": "将在下一个版本开放。",
    "Next Step": "下一步",
    "Capture an idea from this paper.": "从这篇论文中记录一个想法。",
    "Create Idea": "创建想法",
    "Research Notes": "研究笔记",
    "Notes linked to this paper will appear here.": "与这篇论文相关的笔记会显示在这里。",
    "Timeline": "时间线",
    "Creation, edits and decisions will appear here.": "创建、编辑和决策记录会显示在这里。",
    "Related Ideas": "相关想法",
    "No related ideas yet.": "还没有相关想法。",
    "Related Papers": "相关论文",
    "No related papers yet.": "还没有相关论文。",
    "Known relations and evidence will appear here.": "已记录的关系和证据会显示在这里。",
    "Capture claims, evidence, questions and research fragments before they become papers.": "先把论点、材料、问题和研究片段收集起来，再慢慢长成论文。",
    "+ New Idea": "+ 新建想法",
    "Search title, type or tag": "搜索标题、类型或标签",
    "Type": "类型",
    "No ideas yet.": "还没有想法。",
    "Capture your first research idea.": "记录你的第一个研究想法。",
    "New Idea": "新建想法",
    "Idea Library": "想法库",
    "Idea Detail": "想法详情",
    "Choose an idea from the library to inspect its notes, relations and next step.": "从想法库中选择一个想法，查看内容、关系和下一步。",
    "Idea": "想法",
    "Content": "内容",
    "Research notes linked to this idea will appear here.": "与这个想法相关的研究笔记会显示在这里。",
    "No relations yet.": "还没有关系。",
    "Idea history will appear here.": "这个想法的历史会显示在这里。",
    "No suggestions yet.\n\nAnalyze this idea to discover related concepts and possible connections.": "还没有建议。\n\n用 AI 分析这个想法，发现相关概念和可能的连接。",
    "Analyze this idea with AI.": "用 AI 分析这个想法。",
    "Create Idea": "创建想法",
    "Idea title": "想法标题",
    "Idea content": "想法内容",
    "Save Idea": "保存想法",
    "Paper title": "论文标题",
    "Save Paper": "保存论文",
    "Cancel": "取消",
    "AI Settings": "AI 设置",
    "Provider": "服务商",
    "OpenAI Compatible": "OpenAI 兼容接口",
    "Base URL": "Base URL",
    "API Key": "API Key",
    "Enter API key": "输入 API Key",
    "Model": "模型",
    "Save Settings": "保存设置",
    "Test Connection": "测试连接",
    "Data Directory": "数据目录",
    "Choose where Research Workspace stores your local data. Existing data will not be moved or deleted automatically.": "选择研究工作台保存本地数据的位置。已有数据不会被自动移动或删除。",
    "Choose Data Directory": "选择数据目录",
    "Resolved Path": "实际路径",
    "No directory selected": "尚未选择目录",
    "Select a directory to inspect its workspace status.": "选择一个目录后，这里会显示工作区状态。",
    "Verify and Use on Restart": "验证并在重启后使用",
    "Restart Now": "立即重启",
    "Later": "稍后",
    "Coming Soon": "即将开放",
}

PLACEHOLDERS = {
    "Search papers, authors, or tags": "搜索论文、作者或标签",
    "Search title, type or tag": "搜索标题、类型或标签",
    "Capture a research note": "记录一条研究笔记",
    "Enter API key": "输入 API Key",
    "No directory selected": "尚未选择目录",
}

ERROR_TEXT = {
    "Unsupported AI provider": "不支持的 AI 服务商。",
    "AI base URL is required": "请填写 Base URL。",
    "AI API key is required": "请填写 API Key。",
    "AI model is required": "请填写模型名称。",
    "AI settings file has an unsupported shape": "AI 设置文件格式不受支持。",
    "Unsupported AI settings schema version": "AI 设置版本不受支持。",
    "AI is not configured.": "AI 尚未配置。",
    "AI analysis failed.": "AI 分析失败。",
    "The provider returned an invalid response.": "AI 返回的结果格式无效。",
    "The provider returned an empty summary.": "AI 没有返回摘要。",
    "The provider returned no key claims.": "AI 没有返回关键观点。",
    "The provider returned no suggested ideas.": "AI 没有返回建议想法。",
}


def zh(text: str) -> str:
    """Return the Chinese friend-build display text for a known English string."""

    return TEXT.get(text, text)


def zh_error(text: str) -> str:
    """Translate a small set of user-visible validation/provider messages."""

    return ERROR_TEXT.get(text, text)


def apply_zh_cn_friend_surface(root: QWidget) -> None:
    """Translate loaded Designer-owned widgets without touching business logic."""

    candidates = [root, *root.findChildren(QWidget)]
    for widget in candidates:
        if isinstance(widget, (QMainWindow, QDialog)) and widget.windowTitle():
            widget.setWindowTitle(zh(widget.windowTitle()))
        if isinstance(widget, (QLabel, QAbstractButton)) and widget.text():
            widget.setText(zh(widget.text()))
        if isinstance(widget, QLineEdit) and widget.placeholderText():
            widget.setPlaceholderText(PLACEHOLDERS.get(widget.placeholderText(), widget.placeholderText()))
        if isinstance(widget, QComboBox):
            for index in range(widget.count()):
                widget.setItemText(index, zh(widget.itemText(index)))
        if isinstance(widget, QTableWidget):
            for index in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(index)
                if item is not None:
                    item.setText(zh(item.text()))
