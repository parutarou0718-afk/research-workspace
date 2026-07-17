from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from research_workspace.application.dto.monitoring_dto import (
    CandidateDetectionResult,
    MonitoringRootPlan,
    RawFileEventDTO,
    ReconciliationPlan,
)
from research_workspace.domain.monitoring import (
    MonitoringRootStatus,
    PendingPathState,
    RawFileEventType,
    ReconciliationReason,
)
from research_workspace.domain.versioning import CandidateStatus, VersionRuleId


ROOT_ID = UUID("40000000-0000-0000-0000-000000000001")
OPERATION_ID = UUID("40000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def test_monitoring_and_candidate_state_registries_are_closed() -> None:
    assert MonitoringRootStatus("active") is MonitoringRootStatus.ACTIVE
    assert PendingPathState("unstable_source") is PendingPathState.UNSTABLE_SOURCE
    assert RawFileEventType("moved") is RawFileEventType.MOVED
    assert ReconciliationReason("overflow") is ReconciliationReason.OVERFLOW
    assert CandidateStatus("pending") is CandidateStatus.PENDING
    assert VersionRuleId("R5_ZERO_TEXT_LINEAGE") is VersionRuleId.R5_ZERO_TEXT_LINEAGE
    for enum_type, unknown in (
        (MonitoringRootStatus, "unknown"),
        (PendingPathState, "retry_forever"),
        (RawFileEventType, "opened"),
        (ReconciliationReason, "periodic"),
        (CandidateStatus, "accepted"),
        (VersionRuleId, "R6_GUESS"),
    ):
        with pytest.raises(ValueError):
            enum_type(unknown)


def test_monitoring_worker_dtos_are_deeply_immutable() -> None:
    plan = MonitoringRootPlan(
        ROOT_ID, Path("D:/Research"), True, 7, "a" * 64, b'{"quiet_window_seconds":2}'
    )
    event = RawFileEventDTO(
        UUID("40000000-0000-0000-0000-000000000003"),
        ROOT_ID,
        "watchdog",
        RawFileEventType.MODIFIED,
        Path("D:/Research/paper.pdf"),
        None,
        NOW,
        NOW,
        b'{"sequence":1}',
        None,
        "b" * 64,
    )
    reconciliation = ReconciliationPlan(
        OPERATION_ID,
        UUID("40000000-0000-0000-0000-000000000004"),
        ROOT_ID,
        ReconciliationReason.OVERFLOW,
        Path("D:/Research"),
        b'{"cursor":"paper.pdf"}',
        250,
    )
    candidate = CandidateDetectionResult(
        UUID("40000000-0000-0000-0000-000000000005"),
        UUID("40000000-0000-0000-0000-000000000006"),
        "deterministic-version-detector",
        "1.0",
        VersionRuleId.R1_SOURCE_CONTINUITY,
        "c" * 64,
        b'{"basis":"observation_order"}',
        b'{"R1_SOURCE_CONTINUITY":true}',
        [UUID("40000000-0000-0000-0000-000000000007")],
    )

    assert isinstance(plan.semantic_config_json, bytes)
    assert isinstance(event.raw_sequence_json, bytes)
    assert isinstance(reconciliation.checkpoint, bytes)
    assert candidate.input_observation_ids == (
        UUID("40000000-0000-0000-0000-000000000007"),
    )
    with pytest.raises(FrozenInstanceError):
        plan.watcher_generation = 8
    with pytest.raises(FrozenInstanceError):
        event.source_path = None
    with pytest.raises(FrozenInstanceError):
        candidate.signals = b"{}"
