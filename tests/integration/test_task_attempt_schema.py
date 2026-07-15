from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from research_workspace.infrastructure.db.base import Base
from research_workspace.infrastructure.db.models import TaskAttemptModel, TaskModel


def _task():
    return TaskModel(id=uuid4(), task_type="import_document", status="pending",
        idempotency_key="one", request_fingerprint="a" * 64, payload_json="{}",
        result_json=None, attempt_count=0, max_attempts=3, next_attempt_at=None,
        lease_owner=None, lease_expires_at=None, lease_generation=0,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc), started_at=None, finished_at=None)


def test_attempt_number_is_unique_per_task(engine, session):
    Base.metadata.create_all(engine)
    task = _task(); session.add(task); session.flush()
    values = dict(task_id=task.id, attempt_number=1, lease_generation=1,
        lease_owner="executor", status="running", result_json=None,
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc), finished_at=None)
    session.add(TaskAttemptModel(id=uuid4(), **values)); session.flush()
    session.add(TaskAttemptModel(id=uuid4(), **values))
    with pytest.raises(IntegrityError): session.flush()


def test_closed_attempt_requires_finished_at(engine, session):
    Base.metadata.create_all(engine)
    task = _task(); session.add(task); session.flush()
    session.add(TaskAttemptModel(id=uuid4(), task_id=task.id, attempt_number=1,
        lease_generation=1, lease_owner="executor", status="succeeded", result_json="{}",
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc), finished_at=None))
    with pytest.raises(IntegrityError): session.flush()
