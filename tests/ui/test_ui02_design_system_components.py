import json
from pathlib import Path


UI_DIR = (
    Path(__file__).parents[2]
    / "src"
    / "research_workspace"
    / "presentation"
    / "ui"
)


def test_ui02_shared_component_tokens_are_declared():
    tokens = json.loads((UI_DIR / "design_tokens.json").read_text(encoding="utf-8"))

    assert tokens["components"]["button"]["height"] == 40
    assert set(tokens["components"]["button"]["variants"]) == {
        "primary",
        "secondary",
        "ghost",
        "danger",
    }
    assert tokens["components"]["card"] == {
        "radius": 16,
        "padding": 20,
        "borderWidth": 1,
        "shadow": "0 1px 3px rgba(16,24,40,0.06)",
    }
    assert tokens["components"]["input"] == {
        "height": 40,
        "radius": 10,
        "focusBorder": "#4F7DFF",
    }
    assert set(tokens["components"]["badge"]["variants"]) >= {
        "draft",
        "ready",
        "review",
        "revision",
        "accepted",
        "rejected",
        "archived",
    }


def test_ui02_central_stylesheet_exposes_shared_component_selectors():
    from research_workspace.presentation import _token_stylesheet

    stylesheet = _token_stylesheet()
    required_selectors = (
        'QPushButton[variant="primary"]',
        'QPushButton[variant="secondary"]',
        'QPushButton[variant="ghost"]',
        'QPushButton[variant="danger"]',
        'QFrame[component="card"]',
        'QFrame[component="toolbar"]',
        'QFrame[component="emptyState"]',
        'QLineEdit[component="input"]',
        'QLineEdit[component="search"]',
        'QLabel[badge="draft"]',
        'QLabel[badge="revision"]',
        'QLabel[badge="accepted"]',
        'QLabel[badge="rejected"]',
    )
    for selector in required_selectors:
        assert selector in stylesheet


def test_ui02_design_system_document_is_component_contract():
    doc = (Path(__file__).parents[2] / "docs" / "design" / "design-system.md").read_text(
        encoding="utf-8"
    )
    for heading in (
        "### Button",
        "### Card",
        "### Input",
        "### Badge",
        "### Empty State",
        "### Icons",
    ):
        assert heading in doc
    assert "Research Workspace first, AI second" in doc
