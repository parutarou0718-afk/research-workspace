from datetime import datetime, timezone
from uuid import UUID, uuid5

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, func, inspect, select

from research_workspace.application.queries.get_overview import GetOverview
from research_workspace.infrastructure.db.models import (
    AuditLogModel,
    ConferenceModel,
    DomainEventModel,
    EvidenceRefModel,
    EntityRelationModel,
    GrantModel,
    IdeaModel,
    NoteModel,
    PaperModel,
    PaperVersionModel,
    RelationObservationModel,
    SourceDocumentModel,
    SubmissionModel,
    TaskAttemptModel,
    TaskEffectModel,
    TaskModel,
)
from research_workspace.infrastructure.db.repositories import SqlOverviewRepository
from research_workspace.infrastructure.db.seed import seed_foundation_data
from research_workspace.infrastructure.db.session import (
    create_engine_for_path,
    session_factory,
)


NAMESPACE = UUID("4c8c9a20-06a5-5c0d-9d8c-41aeeab7ef10")
FIXED_TIME = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _id(entity_type: str, stable_key: str):
    return uuid5(NAMESPACE, f"{entity_type}:{stable_key}")


def _migrate(database_path) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")


@pytest.fixture
def migrated_session(database_path):
    _migrate(database_path)
    engine = create_engine_for_path(database_path)
    factory = session_factory(engine)
    with factory() as session:
        yield session
    engine.dispose()


def test_fresh_directory_gets_schema_and_one_seed_dataset(database_path):
    _migrate(database_path)
    engine = create_engine_for_path(database_path)
    factory = session_factory(engine)
    with factory() as session:
        seed_foundation_data(session)

        papers = session.scalars(select(PaperModel).order_by(PaperModel.title)).all()
        ideas = session.scalars(select(IdeaModel).order_by(IdeaModel.title)).all()
        submissions = session.scalars(
            select(SubmissionModel).order_by(SubmissionModel.venue)
        ).all()
        conferences = session.scalars(
            select(ConferenceModel).order_by(ConferenceModel.name)
        ).all()
        grants = session.scalars(select(GrantModel)).all()

        assert inspect(engine).has_table("papers")
        assert {(row.id, row.title, row.status) for row in papers} == {
            (_id("Paper", "multimodal-alignment"), "多模态对齐方法研究", "revision"),
            (_id("Paper", "temporal-representation"), "时序表示学习综述", "active"),
            (_id("Paper", "research-llm"), "大模型在科研工作流中的应用", "active"),
        }
        assert {(row.id, row.title, row.content, row.status, row.origin_type) for row in ideas} == {
            (_id("Idea", "causal-alignment"), "跨模态因果对齐", "跨模态因果对齐", "unused", "manual"),
            (_id("Idea", "small-sample-eval"), "小样本稳健性评估", "小样本稳健性评估", "unused", "manual"),
            (_id("Idea", "review-response-map"), "审稿意见—证据映射", "审稿意见—证据映射", "unused", "manual"),
            (_id("Idea", "cross-paper-memory"), "跨论文研究记忆", "跨论文研究记忆", "unused", "manual"),
        }
        assert {
            (row.id, row.paper_id, row.venue, row.status, row.submitted_at, row.deadline_at)
            for row in submissions
        } == {
            (_id("Submission", "tpami-revision"), _id("Paper", "multimodal-alignment"), "IEEE TPAMI", "revision", datetime(2026, 6, 10, tzinfo=timezone.utc), datetime(2026, 7, 20, tzinfo=timezone.utc)),
            (_id("Submission", "neurips-ready"), _id("Paper", "temporal-representation"), "NeurIPS", "ready", None, datetime(2026, 7, 31, tzinfo=timezone.utc)),
            (_id("Submission", "acmmm-review"), _id("Paper", "research-llm"), "ACM MM", "external_review", datetime(2026, 6, 15, tzinfo=timezone.utc), None),
        }
        assert {
            (row.id, row.name, row.starts_at, row.ends_at, row.location, row.status)
            for row in conferences
        } == {
            (_id("Conference", "neurips-2026"), "NeurIPS 2026", datetime(2026, 7, 25, tzinfo=timezone.utc), datetime(2026, 7, 27, tzinfo=timezone.utc), "Tokyo", "planned"),
            (_id("Conference", "research-workflow-forum"), "科研工作流论坛", datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 18, tzinfo=timezone.utc), "Online", "planned"),
        }
        assert [
            (row.id, row.name, row.status, row.deadline_at, row.source_url)
            for row in grants
        ] == [
            (_id("Grant", "foundation-methods"), "基础研究方法专项", "watching", datetime(2026, 7, 30, tzinfo=timezone.utc), "https://example.invalid/grants/foundation-methods")
        ]
        for row in [*papers, *ideas, *submissions, *conferences, *grants]:
            assert row.created_at == FIXED_TIME
            assert row.updated_at == FIXED_TIME

        omitted_models = (
            PaperVersionModel, SourceDocumentModel, NoteModel, EvidenceRefModel,
            EntityRelationModel, RelationObservationModel, TaskModel,
            TaskAttemptModel, TaskEffectModel, AuditLogModel, DomainEventModel,
        )
        assert all(session.scalar(select(func.count(model.id))) == 0 for model in omitted_models)
    engine.dispose()


def test_seed_is_idempotent(migrated_session):
    seed_foundation_data(migrated_session)
    seed_foundation_data(migrated_session)

    assert migrated_session.scalar(select(func.count(PaperModel.id))) == 3
    assert migrated_session.scalar(select(func.count(IdeaModel.id))) == 4
    assert migrated_session.scalar(select(func.count(SubmissionModel.id))) == 3
    assert migrated_session.scalar(select(func.count(ConferenceModel.id))) == 2
    assert migrated_session.scalar(select(func.count(GrantModel.id))) == 1


def test_seed_completes_a_partially_preexisting_manifest(migrated_session):
    migrated_session.add(
        PaperModel(
            id=_id("Paper", "multimodal-alignment"),
            title="多模态对齐方法研究",
            status="revision",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
    )
    migrated_session.commit()

    seed_foundation_data(migrated_session)
    seed_foundation_data(migrated_session)

    assert migrated_session.scalar(select(func.count(PaperModel.id))) == 3
    assert migrated_session.scalar(select(func.count(IdeaModel.id))) == 4
    assert migrated_session.scalar(select(func.count(SubmissionModel.id))) == 3
    assert migrated_session.scalar(select(func.count(ConferenceModel.id))) == 2
    assert migrated_session.scalar(select(func.count(GrantModel.id))) == 1


def test_seed_succeeds_inside_caller_owned_transaction(migrated_session):
    with migrated_session.begin():
        migrated_session.add(
            NoteModel(
                id=_id("Note", "caller-work"),
                title="caller work",
                content="must remain in the outer transaction",
                created_at=FIXED_TIME,
                updated_at=FIXED_TIME,
            )
        )

        seed_foundation_data(migrated_session)

        assert migrated_session.scalar(select(func.count(PaperModel.id))) == 3
        assert migrated_session.scalar(select(func.count(NoteModel.id))) == 1


def test_seed_does_not_commit_caller_owned_transaction(migrated_session):
    outer = migrated_session.begin()
    migrated_session.add(
        NoteModel(
            id=_id("Note", "caller-rollback"),
            title="caller rollback",
            content="the caller owns commit and rollback",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
    )

    seed_foundation_data(migrated_session)
    outer.rollback()

    assert migrated_session.scalar(select(func.count(NoteModel.id))) == 0
    assert migrated_session.scalar(select(func.count(PaperModel.id))) == 0


def test_failed_seed_rolls_back_without_partial_rows(migrated_session):
    engine = migrated_session.get_bind()

    def fail_on_ideas(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO ideas"):
            raise RuntimeError("injected seed failure")

    event.listen(engine, "before_cursor_execute", fail_on_ideas)
    try:
        with pytest.raises(RuntimeError, match="injected seed failure"):
            seed_foundation_data(migrated_session)
    finally:
        event.remove(engine, "before_cursor_execute", fail_on_ideas)

    for model in (PaperModel, IdeaModel, SubmissionModel, ConferenceModel, GrantModel):
        assert migrated_session.scalar(select(func.count(model.id))) == 0


def test_failed_seed_inside_outer_transaction_preserves_unrelated_caller_work(
    migrated_session,
):
    engine = migrated_session.get_bind()
    outer = migrated_session.begin()
    migrated_session.add(
        NoteModel(
            id=_id("Note", "preserved-caller-work"),
            title="preserved caller work",
            content="must survive rollback to the seed savepoint",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
    )

    def fail_on_ideas(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO ideas"):
            raise RuntimeError("injected nested seed failure")

    event.listen(engine, "before_cursor_execute", fail_on_ideas)
    try:
        with pytest.raises(RuntimeError, match="injected nested seed failure"):
            seed_foundation_data(migrated_session)
    finally:
        event.remove(engine, "before_cursor_execute", fail_on_ideas)

    assert migrated_session.scalar(select(func.count(NoteModel.id))) == 1
    for model in (PaperModel, IdeaModel, SubmissionModel, ConferenceModel, GrantModel):
        assert migrated_session.scalar(select(func.count(model.id))) == 0

    outer.rollback()
    assert migrated_session.scalar(select(func.count(NoteModel.id))) == 0


def test_sql_overview_uses_seeded_repository_data(migrated_session):
    seed_foundation_data(migrated_session)

    view_model = GetOverview(SqlOverviewRepository(migrated_session)).execute()

    assert view_model.revision_count == 1
    assert view_model.ready_count == 1
    assert view_model.upcoming_conference_count == 2
    assert view_model.upcoming_grant_count == 1
    assert view_model.suggestions == ()
    assert len(view_model.submission_rows) == 3
    assert view_model.activities == ()
    assert view_model.focus_items == ()
    assert view_model.focus_progress == 0


def test_sql_overview_counts_and_rows_exclude_soft_deleted_parent_papers(
    migrated_session,
):
    seed_foundation_data(migrated_session)
    deleted_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for stable_key in ("multimodal-alignment", "temporal-representation"):
        paper = migrated_session.get(PaperModel, _id("Paper", stable_key))
        paper.deleted_at = deleted_at
    migrated_session.flush()

    view_model = GetOverview(SqlOverviewRepository(migrated_session)).execute()

    assert view_model.revision_count == 0
    assert view_model.ready_count == 0
    assert len(view_model.submission_rows) == 1
    assert "ACM MM" in view_model.submission_rows[0]
