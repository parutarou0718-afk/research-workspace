from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser

from research_workspace.presentation.pages.ideas_page import (
    configure_safe_markdown_browser,
    render_safe_markdown,
)


def test_renderer_preserves_markdown_semantics_but_blocks_active_content() -> None:
    rendered = render_safe_markdown(
        "# Heading\n<script>alert(1)</script>\n"
        "![remote](https://example.test/a.png)\n"
        "[bad](javascript:alert(1)) [data](data:text/html,x)\n"
        "[safe](https://example.test/page)"
    ).lower()
    assert "heading" in rendered
    assert "<script" not in rendered
    assert "<img" not in rendered
    assert "javascript:" not in rendered
    assert "data:text" not in rendered
    assert "https://example.test/page" in rendered


def test_browser_never_auto_opens_external_links(qtbot) -> None:
    browser = QTextBrowser()
    qtbot.addWidget(browser)
    configure_safe_markdown_browser(browser, "[safe](https://example.test/page)")
    assert browser.openExternalLinks() is False
    assert browser.openLinks() is False
