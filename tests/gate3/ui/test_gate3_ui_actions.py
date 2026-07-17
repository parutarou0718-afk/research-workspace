from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_gate3_decision_ui_has_no_future_or_direct_database_authority() -> None:
    paths = (
        ROOT / "src/research_workspace/presentation/pages/version_candidates_page.py",
        ROOT / "src/research_workspace/presentation/dialogs/relation_review_dialog.py",
    )
    combined = "\n".join(path.read_text("utf-8") for path in paths)
    for forbidden in (
        "sqlalchemy", "from sqlalchemy", " Session(", "repository",
        "infrastructure.db", "force undo", "redo", "permanent delete",
        "backup", "export", "ocr", "agent",
    ):
        assert forbidden.casefold() not in combined.casefold()


def test_bootstrap_composes_safe_undo_and_decision_actions() -> None:
    from research_workspace.bootstrap import ApplicationServices, _UndoDispatcher

    fields = ApplicationServices.__dataclass_fields__
    assert {"get_safe_undo", "decision_actions"} <= fields.keys()
    original = __import__("uuid").uuid4()

    class Delegate:
        def prepare(self, *args, **kwargs):
            return args, kwargs

    args, kwargs = _UndoDispatcher(Delegate(), original).prepare("request")
    assert args == ("request",)
    assert kwargs["undo_of_command_id"] == original


def test_task16_does_not_start_gate3_certification() -> None:
    assert not (
        ROOT / "tests/gate3/acceptance/test_gate3_checkpoint.py"
    ).exists()
