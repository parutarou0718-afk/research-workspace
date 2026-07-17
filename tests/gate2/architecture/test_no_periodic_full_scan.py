from pathlib import Path

import research_workspace
from research_workspace.infrastructure.monitoring import reconciliation


def test_reconciliation_has_no_timer_thread_or_periodic_healthy_scheduler() -> None:
    source = Path(reconciliation.__file__).read_text(encoding="utf-8")
    assert "threading" not in source
    assert "Timer(" not in source
    assert "while True" not in source
    production_root = Path(research_workspace.__file__).parent
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in production_root.rglob("*.py")
    )
    assert "schedule_periodic_reconciliation" not in production
    assert "reconciliation_interval" not in production
    assert "periodic_full_scan" not in production
