"""Ideas page controller and local-only Markdown rendering boundary."""

import html
import re

from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QLabel, QScrollArea, QTextBrowser

from research_workspace.presentation import load_ui_resource, require_child


class IdeasPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("ideas_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "ideasScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")


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
