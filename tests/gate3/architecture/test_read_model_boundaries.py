from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
QUERY_ROOT = ROOT / "src/research_workspace/application/queries"


def test_gate3_queries_are_qt_free_and_do_not_mutate_or_repair() -> None:
    for name in (
        "get_papers.py",
        "get_ideas.py",
        "get_submissions.py",
        "get_version_candidates.py",
    ):
        source = (QUERY_ROOT / name).read_text("utf-8")
        assert "PySide6" not in source
        assert "QWidget" not in source
        assert ".commit(" not in source
        assert ".add(" not in source
        assert "repair" not in source.lower()


def test_read_models_are_deeply_immutable() -> None:
    from research_workspace.application.queries.get_papers import PaperReadModel

    view = PaperReadModel(
        __import__("uuid").uuid4(), "Paper", "active", None, None, 1,
        ("edit",),
    )
    with pytest.raises(FrozenInstanceError):
        view.title = "Changed"
    assert isinstance(view.actions, tuple)


def test_task14_preserves_read_models_without_gate3_ui() -> None:
    assert (ROOT / "tests/gate3/unit/test_gate3_read_models.py").exists()
    assert (
        ROOT / "tests/gate3/architecture/test_gate3_worker_boundaries.py"
    ).exists()
    assert not (
        ROOT / "src/research_workspace/presentation/dialogs/paper_editor_dialog.py"
    ).exists()
