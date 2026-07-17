from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_gate3_worker_owns_no_database_ui_domain_write_or_network_authority() -> None:
    source = (
        ROOT / "src/research_workspace/infrastructure/workers/operation_worker.py"
    ).read_text("utf-8")
    for forbidden in (
        "sqlalchemy",
        "Session",
        "Repository",
        "QWidget",
        "DomainMutation",
        "DomainEvent",
        "socket",
        "requests",
        "httpx",
    ):
        assert forbidden not in source


def test_gate3_extends_feature_worker_without_generic_runtime() -> None:
    source = (
        ROOT / "src/research_workspace/infrastructure/workers/operation_worker.py"
    ).read_text("utf-8")
    assert "RecoveryWorkPlan" in source
    for forbidden in ("DecisionWorker", "TaskExecutor", "AgentRuntime", "lease"):
        assert forbidden not in source


def test_task14_does_not_create_gate3_ui() -> None:
    assert (
        ROOT / "tests/gate3/architecture/test_gate3_worker_boundaries.py"
    ).exists()
    assert not (
        ROOT / "src/research_workspace/presentation/dialogs/paper_editor_dialog.py"
    ).exists()

