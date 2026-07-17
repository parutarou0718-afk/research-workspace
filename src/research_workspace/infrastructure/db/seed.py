"""Transactional deterministic seed data for the foundation release."""

from datetime import datetime, timezone
import logging
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    ConferenceModel,
    GrantModel,
    IdeaModel,
    PaperModel,
    SubmissionModel,
)


SEED_MANIFEST_ID = "research-workspace-foundation-seed-v1"
SEED_NAMESPACE = UUID("4c8c9a20-06a5-5c0d-9d8c-41aeeab7ef10")
SEED_TIMESTAMP = datetime(2026, 6, 1, tzinfo=timezone.utc)

_LOGGER = logging.getLogger(__name__)


def _seed_id(entity_type: str, stable_key: str):
    return uuid5(SEED_NAMESPACE, f"{entity_type}:{stable_key}")


def seed_foundation_data(session: Session) -> None:
    """Insert the exact fixed manifest once, atomically, without audit rows."""

    with session.get_bind().connect() as connection:
        adoption_command_id = connection.scalar(
            select(ApplicationCommandModel.id).where(
                ApplicationCommandModel.command_type == "system.migration_adopt_v01",
                ApplicationCommandModel.status == "committed",
            )
        )
    if adoption_command_id is None:
        raise RuntimeError("0004 migration adoption command is required before seeding")
    command_fields = {
        "row_version": 1,
        "created_by_command_id": adoption_command_id,
        "updated_by_command_id": adoption_command_id,
    }
    papers = (
        PaperModel(id=_seed_id("Paper", "multimodal-alignment"), title="多模态对齐方法研究", status="revision", created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP, **command_fields),
        PaperModel(id=_seed_id("Paper", "temporal-representation"), title="时序表示学习综述", status="active", created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP, **command_fields),
        PaperModel(id=_seed_id("Paper", "research-llm"), title="大模型在科研工作流中的应用", status="active", created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP, **command_fields),
    )
    ideas = tuple(
        IdeaModel(
            id=_seed_id("Idea", key), title=text, content=text,
            status="unused", origin_type="manual",
            created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP,
            **command_fields,
        )
        for key, text in (
            ("causal-alignment", "跨模态因果对齐"),
            ("small-sample-eval", "小样本稳健性评估"),
            ("review-response-map", "审稿意见—证据映射"),
            ("cross-paper-memory", "跨论文研究记忆"),
        )
    )
    submissions = (
        SubmissionModel(
            id=_seed_id("Submission", "tpami-revision"),
            paper_id=_seed_id("Paper", "multimodal-alignment"), venue="IEEE TPAMI",
            status="revision", submitted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            deadline_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP,
            **command_fields,
        ),
        SubmissionModel(
            id=_seed_id("Submission", "neurips-ready"),
            paper_id=_seed_id("Paper", "temporal-representation"), venue="NeurIPS",
            status="ready", deadline_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
            created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP,
            **command_fields,
        ),
        SubmissionModel(
            id=_seed_id("Submission", "acmmm-review"),
            paper_id=_seed_id("Paper", "research-llm"), venue="ACM MM",
            status="external_review", submitted_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP,
            **command_fields,
        ),
    )
    conferences = (
        ConferenceModel(
            id=_seed_id("Conference", "neurips-2026"), name="NeurIPS 2026",
            starts_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            ends_at=datetime(2026, 7, 27, tzinfo=timezone.utc), location="Tokyo",
            status="planned", created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP,
        ),
        ConferenceModel(
            id=_seed_id("Conference", "research-workflow-forum"), name="科研工作流论坛",
            starts_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
            ends_at=datetime(2026, 7, 18, tzinfo=timezone.utc), location="Online",
            status="planned", created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP,
        ),
    )
    grants = (
        GrantModel(
            id=_seed_id("Grant", "foundation-methods"), name="基础研究方法专项",
            status="watching", deadline_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            source_url="https://example.invalid/grants/foundation-methods",
            created_at=SEED_TIMESTAMP, updated_at=SEED_TIMESTAMP,
        ),
    )

    if session.in_transaction():
        connection = session.connection()
        if (
            connection.dialect.name == "sqlite"
            and not connection.connection.driver_connection.in_transaction
        ):
            connection.exec_driver_sql("BEGIN")
        transaction = session.begin_nested()
    else:
        transaction = session.begin()
    with transaction:
        for model, records in (
            (PaperModel, papers),
            (IdeaModel, ideas),
            (SubmissionModel, submissions),
            (ConferenceModel, conferences),
            (GrantModel, grants),
        ):
            ids = tuple(record.id for record in records)
            existing_ids = set(session.scalars(select(model.id).where(model.id.in_(ids))))
            session.add_all(record for record in records if record.id not in existing_ids)
        session.flush()

    _LOGGER.info("Foundation seed manifest initialized: %s", SEED_MANIFEST_ID)
