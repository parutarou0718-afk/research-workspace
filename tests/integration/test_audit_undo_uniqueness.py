from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from research_workspace.infrastructure.db.base import Base
from research_workspace.infrastructure.db.models import AuditLogModel


def test_undo_can_reference_original_only_once(engine, session):
    Base.metadata.create_all(engine)
    target_id = uuid4()
    original = AuditLogModel(id=uuid4(), actor_type="system", actor_id=None,
        action="relation.create", target_type="EntityRelation", target_id=target_id,
        before_json=None, after_json="{}", task_id=None, correlation_id=None,
        undo_token="undo-1", undo_of_audit_id=None,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    session.add(original); session.flush()
    first = AuditLogModel(id=uuid4(), actor_type="user", actor_id="local-user",
        action="audit.undo_applied", target_type="EntityRelation", target_id=target_id,
        before_json="{}", after_json=None, task_id=None, correlation_id=None,
        undo_token=None, undo_of_audit_id=original.id,
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc))
    session.add(first); session.flush()
    duplicate = AuditLogModel(id=uuid4(), actor_type="user", actor_id="local-user",
        action="audit.undo_applied", target_type="EntityRelation", target_id=target_id,
        before_json="{}", after_json=None, task_id=None, correlation_id=None,
        undo_token=None, undo_of_audit_id=original.id,
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc))
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.flush()
