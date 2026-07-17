from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_provider_ledger_appends_gate3_interfaces_without_rewriting_gate2_prefix() -> None:
    text = (ROOT / "contracts" / "provider_interfaces.md").read_text("utf-8")
    gate3 = text.split("## Gate 3 protected-write ports", 1)
    assert len(gate3) == 2
    appended = gate3[1]
    for interface in (
        "RawCommandEnvelope",
        "CommandPlan",
        "RecoveryPlan",
        "VerifiedRecoveryPoint",
        "DomainMutation",
        "DecisionReviewBundle",
        "SQLiteBackup",
    ):
        assert interface in appended


def test_gate3_provider_contract_exposes_no_framework_or_generic_runtime() -> None:
    text = (ROOT / "contracts" / "provider_interfaces.md").read_text("utf-8")
    appended = text.split("## Gate 3 protected-write ports", 1)[1]
    for forbidden in (
        "sqlalchemy.orm.Session",
        "QWidget",
        "Qt model",
        "socket.socket",
        "requests.",
        "httpx.",
        "GenericTask",
        "AgentRuntime",
    ):
        assert forbidden not in appended


def test_task6_adds_paper_without_later_gate3_commands() -> None:
    assert (
        ROOT / "src/research_workspace/application/ports/sqlite_backup.py"
    ).exists()
    assert (
        ROOT / "src/research_workspace/infrastructure/recovery/sqlite_recovery.py"
    ).exists()
    assert (
        ROOT / "src/research_workspace/application/services/command_dispatcher.py"
    ).exists()
    assert (
        ROOT / "src/research_workspace/application/commands/manage_paper.py"
    ).exists()
    assert not (
        ROOT / "src/research_workspace/application/commands/manage_idea.py"
    ).exists()
