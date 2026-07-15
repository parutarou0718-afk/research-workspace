from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from research_workspace.infrastructure.db.base import Base
from research_workspace.infrastructure.db.models import EntityRelationModel, RelationObservationModel


def test_observation_key_is_append_only_idempotency_key(engine, session):
    Base.metadata.create_all(engine)
    relation = EntityRelationModel(id=uuid4(), source_type="Idea", source_id=uuid4(),
        relation_type="supports", target_type="Paper", target_id=uuid4(), confidence=None,
        confirmation_state="candidate", created_by_actor_type="user", created_by_actor_id="u",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    session.add(relation); session.flush()
    values = dict(observed_by_actor_type="user", observed_by_actor_id="u",
        provenance_type="manual", confidence=None, origin_task_id=None,
        evidence_ref_id=None, provider_id=None, model_id=None,
        observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc), observation_key="same")
    session.add(RelationObservationModel(id=uuid4(), relation_id=relation.id, **values)); session.flush()
    session.add(RelationObservationModel(id=uuid4(), relation_id=relation.id, **values))
    with pytest.raises(IntegrityError):
        session.flush()
