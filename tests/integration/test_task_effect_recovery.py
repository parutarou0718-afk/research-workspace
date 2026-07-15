from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from research_workspace.infrastructure.db.base import Base
from research_workspace.infrastructure.db.models import TaskAttemptModel, TaskEffectModel, TaskModel


def test_operation_key_is_unique(engine, session):
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    task = TaskModel(id=uuid4(), task_type="export_data", status="running", idempotency_key="k",
        request_fingerprint="a" * 64, payload_json="{}", result_json=None, attempt_count=1,
        max_attempts=3, next_attempt_at=None, lease_owner="e", lease_expires_at=now,
        lease_generation=1, created_at=now, started_at=now, finished_at=None)
    attempt = TaskAttemptModel(id=uuid4(), task_id=task.id, attempt_number=1,
        lease_generation=1, lease_owner="e", status="running", result_json=None,
        started_at=now, finished_at=None)
    session.add(task); session.flush(); session.add(attempt); session.flush()
    values = dict(operation_key="b" * 64, task_id=task.id, attempt_id=attempt.id,
        effect_type="filesystem", output_type="export", output_identity="report",
        output_ref_json="{}", status="prepared", recovery_json="{}", created_at=now,
        committed_at=None)
    session.add(TaskEffectModel(id=uuid4(), **values)); session.flush()
    session.add(TaskEffectModel(id=uuid4(), **values))
    with pytest.raises(IntegrityError): session.flush()


def test_committed_effect_requires_committed_at(engine, session):
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    task = TaskModel(id=uuid4(), task_type="export_data", status="running", idempotency_key="k2",
        request_fingerprint="a" * 64, payload_json="{}", result_json=None, attempt_count=1,
        max_attempts=3, next_attempt_at=None, lease_owner="e", lease_expires_at=now,
        lease_generation=1, created_at=now, started_at=now, finished_at=None)
    attempt = TaskAttemptModel(id=uuid4(), task_id=task.id, attempt_number=1,
        lease_generation=1, lease_owner="e", status="running", result_json=None,
        started_at=now, finished_at=None)
    session.add(task); session.flush(); session.add(attempt); session.flush()
    session.add(TaskEffectModel(id=uuid4(), operation_key="c" * 64, task_id=task.id,
        attempt_id=attempt.id, effect_type="db", output_type="Idea", output_identity="x",
        output_ref_json="{}", status="committed", recovery_json=None, created_at=now,
        committed_at=None))
    with pytest.raises(IntegrityError): session.flush()
