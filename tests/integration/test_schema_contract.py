from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import get_type_hints

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session

from research_workspace.infrastructure.db.base import Base, UTCDateTime
import research_workspace.infrastructure.db.models  # noqa: F401
from research_workspace.infrastructure.db.models import EntityRelationModel, RelationObservationModel, SourceDocumentModel


EXPECTED_SCHEMA = {
    "source_documents": {
        "id": ("CHAR(36)", False), "path": ("TEXT", False),
        "sha256": ("CHAR(64)", False), "mime_type": ("VARCHAR(255)", False),
        "size_bytes": ("INTEGER", False), "modified_at": ("TEXT", False),
        "imported_at": ("TEXT", False), "read_only": ("BOOLEAN", False),
        "missing_at": ("TEXT", True),
    },
    "papers": {
        "id": ("CHAR(36)", False), "title": ("VARCHAR(500)", False),
        "status": ("VARCHAR(64)", False), "current_version_id": ("CHAR(36)", True),
        "created_at": ("TEXT", False), "updated_at": ("TEXT", False),
        "deleted_at": ("TEXT", True),
    },
    "paper_versions": {
        "id": ("CHAR(36)", False), "paper_id": ("CHAR(36)", False),
        "source_document_id": ("CHAR(36)", False),
        "version_label": ("VARCHAR(128)", False), "parent_version_id": ("CHAR(36)", True),
        "is_current": ("BOOLEAN", False), "created_at": ("TEXT", False),
    },
    "ideas": {
        "id": ("CHAR(36)", False), "title": ("VARCHAR(500)", False),
        "content": ("TEXT", False), "status": ("VARCHAR(64)", False),
        "origin_type": ("VARCHAR(64)", False), "created_at": ("TEXT", False),
        "updated_at": ("TEXT", False), "deleted_at": ("TEXT", True),
    },
    "notes": {
        "id": ("CHAR(36)", False), "title": ("VARCHAR(500)", False),
        "content": ("TEXT", False), "source_document_id": ("CHAR(36)", True),
        "created_at": ("TEXT", False), "updated_at": ("TEXT", False),
        "deleted_at": ("TEXT", True),
    },
    "submissions": {
        "id": ("CHAR(36)", False), "paper_id": ("CHAR(36)", False),
        "venue": ("VARCHAR(500)", False), "status": ("VARCHAR(64)", False),
        "submitted_at": ("TEXT", True), "deadline_at": ("TEXT", True),
        "active_version_id": ("CHAR(36)", True), "created_at": ("TEXT", False),
        "updated_at": ("TEXT", False), "deleted_at": ("TEXT", True),
    },
    "conferences": {
        "id": ("CHAR(36)", False), "name": ("VARCHAR(500)", False),
        "starts_at": ("TEXT", True), "ends_at": ("TEXT", True),
        "location": ("VARCHAR(500)", True), "status": ("VARCHAR(64)", False),
        "created_at": ("TEXT", False), "updated_at": ("TEXT", False),
        "deleted_at": ("TEXT", True),
    },
    "grants": {
        "id": ("CHAR(36)", False), "name": ("VARCHAR(500)", False),
        "status": ("VARCHAR(64)", False), "deadline_at": ("TEXT", True),
        "source_url": ("TEXT", True), "created_at": ("TEXT", False),
        "updated_at": ("TEXT", False), "deleted_at": ("TEXT", True),
    },
    "evidence_refs": {
        "id": ("CHAR(36)", False), "entity_type": ("VARCHAR(64)", False),
        "entity_id": ("CHAR(36)", False), "document_id": ("CHAR(36)", False),
        "version_id": ("CHAR(36)", True), "section": ("VARCHAR(1000)", True),
        "page": ("INTEGER", True), "slide": ("INTEGER", True),
        "paragraph_id": ("CHAR(64)", True), "char_start": ("INTEGER", True),
        "char_end": ("INTEGER", True), "locator_json": ("TEXT", False),
        "quote_hash": ("CHAR(64)", False), "created_at": ("TEXT", False),
    },
    "entity_relations": {
        "id": ("CHAR(36)", False), "source_type": ("VARCHAR(64)", False),
        "source_id": ("CHAR(36)", False), "relation_type": ("VARCHAR(64)", False),
        "target_type": ("VARCHAR(64)", False), "target_id": ("CHAR(36)", False),
        "confidence": ("NUMERIC(6, 5)", True), "confirmation_state": ("VARCHAR(64)", False),
        "created_by_actor_type": ("VARCHAR(64)", False),
        "created_by_actor_id": ("VARCHAR(255)", True),
        "created_at": ("TEXT", False), "updated_at": ("TEXT", False),
    },
    "relation_observations": {
        "id": ("CHAR(36)", False), "relation_id": ("CHAR(36)", False),
        "observed_by_actor_type": ("VARCHAR(64)", False),
        "observed_by_actor_id": ("VARCHAR(255)", True),
        "provenance_type": ("VARCHAR(64)", False), "confidence": ("NUMERIC(6, 5)", True),
        "origin_task_id": ("CHAR(36)", True), "evidence_ref_id": ("CHAR(36)", True),
        "provider_id": ("VARCHAR(255)", True), "model_id": ("VARCHAR(255)", True),
        "observed_at": ("TEXT", False), "observation_key": ("VARCHAR(255)", False),
    },
    "audit_logs": {
        "id": ("CHAR(36)", False), "actor_type": ("VARCHAR(64)", False),
        "actor_id": ("VARCHAR(255)", True), "action": ("VARCHAR(255)", False),
        "target_type": ("VARCHAR(64)", False), "target_id": ("CHAR(36)", False),
        "before_json": ("TEXT", True), "after_json": ("TEXT", True),
        "task_id": ("CHAR(36)", True), "correlation_id": ("CHAR(36)", True),
        "undo_token": ("VARCHAR(255)", True), "undo_of_audit_id": ("CHAR(36)", True),
        "created_at": ("TEXT", False),
    },
    "tasks": {
        "id": ("CHAR(36)", False), "task_type": ("VARCHAR(64)", False),
        "status": ("VARCHAR(64)", False), "idempotency_key": ("VARCHAR(255)", False),
        "request_fingerprint": ("CHAR(64)", False), "payload_json": ("TEXT", False),
        "result_json": ("TEXT", True), "attempt_count": ("INTEGER", False),
        "max_attempts": ("INTEGER", False), "next_attempt_at": ("TEXT", True),
        "lease_owner": ("VARCHAR(255)", True), "lease_expires_at": ("TEXT", True),
        "lease_generation": ("INTEGER", False), "created_at": ("TEXT", False),
        "started_at": ("TEXT", True), "finished_at": ("TEXT", True),
    },
    "task_attempts": {
        "id": ("CHAR(36)", False), "task_id": ("CHAR(36)", False),
        "attempt_number": ("INTEGER", False), "lease_generation": ("INTEGER", False),
        "lease_owner": ("VARCHAR(255)", False), "status": ("VARCHAR(64)", False),
        "result_json": ("TEXT", True), "started_at": ("TEXT", False),
        "finished_at": ("TEXT", True),
    },
    "task_effects": {
        "id": ("CHAR(36)", False), "operation_key": ("CHAR(64)", False),
        "task_id": ("CHAR(36)", False), "attempt_id": ("CHAR(36)", False),
        "effect_type": ("VARCHAR(255)", False), "output_type": ("VARCHAR(255)", False),
        "output_identity": ("VARCHAR(1000)", False), "output_ref_json": ("TEXT", False),
        "status": ("VARCHAR(64)", False), "recovery_json": ("TEXT", True),
        "created_at": ("TEXT", False), "committed_at": ("TEXT", True),
    },
    "domain_events": {
        "id": ("CHAR(36)", False), "event_type": ("VARCHAR(64)", False),
        "aggregate_type": ("VARCHAR(64)", False), "aggregate_id": ("CHAR(36)", False),
        "payload_json": ("TEXT", False), "deduplication_key": ("VARCHAR(255)", False),
        "causation_id": ("CHAR(36)", True), "correlation_id": ("CHAR(36)", True),
        "created_at": ("TEXT", False), "processed_at": ("TEXT", True),
    },
}

EXPECTED_DEFAULTS = {
    "source_documents": {"read_only": "1"}, "papers": {"status": "'active'"},
    "paper_versions": {"is_current": "0"},
    "ideas": {"status": "'unused'", "origin_type": "'manual'"},
    "notes": {}, "submissions": {"status": "'preparing'"},
    "conferences": {"status": "'planned'"}, "grants": {"status": "'watching'"},
    "evidence_refs": {}, "entity_relations": {"confirmation_state": "'candidate'"},
    "relation_observations": {}, "audit_logs": {},
    "tasks": {"status": "'pending'", "attempt_count": "0", "max_attempts": "3", "lease_generation": "0"},
    "task_attempts": {"status": "'running'"}, "task_effects": {}, "domain_events": {},
}

EXPECTED_PRIMARY_KEYS = {
    "source_documents": ("pk_source_documents", ("id",)), "papers": ("pk_papers", ("id",)),
    "paper_versions": ("pk_paper_versions", ("id",)), "ideas": ("pk_ideas", ("id",)),
    "notes": ("pk_notes", ("id",)), "submissions": ("pk_submissions", ("id",)),
    "conferences": ("pk_conferences", ("id",)), "grants": ("pk_grants", ("id",)),
    "evidence_refs": ("pk_evidence_refs", ("id",)), "entity_relations": ("pk_entity_relations", ("id",)),
    "relation_observations": ("pk_relation_observations", ("id",)), "audit_logs": ("pk_audit_logs", ("id",)),
    "tasks": ("pk_tasks", ("id",)), "task_attempts": ("pk_task_attempts", ("id",)),
    "task_effects": ("pk_task_effects", ("id",)), "domain_events": ("pk_domain_events", ("id",)),
}

EXPECTED_FOREIGN_KEY_DETAILS = {
    "source_documents": set(), "ideas": set(), "conferences": set(), "grants": set(),
    "entity_relations": set(), "tasks": set(), "domain_events": set(),
    "papers": {("fk_papers_current_version_id_paper_versions", ("current_version_id",), "paper_versions", ("id",), "SET NULL")},
    "paper_versions": {("fk_paper_versions_paper_id_papers", ("paper_id",), "papers", ("id",), "RESTRICT"), ("fk_paper_versions_source_document_id_source_documents", ("source_document_id",), "source_documents", ("id",), "RESTRICT"), ("fk_paper_versions_parent_version_id_paper_versions", ("parent_version_id",), "paper_versions", ("id",), "RESTRICT")},
    "notes": {("fk_notes_source_document_id_source_documents", ("source_document_id",), "source_documents", ("id",), "RESTRICT")},
    "submissions": {("fk_submissions_paper_id_papers", ("paper_id",), "papers", ("id",), "RESTRICT"), ("fk_submissions_active_version_id_paper_versions", ("active_version_id",), "paper_versions", ("id",), "RESTRICT")},
    "evidence_refs": {("fk_evidence_refs_document_id_source_documents", ("document_id",), "source_documents", ("id",), "RESTRICT"), ("fk_evidence_refs_version_id_paper_versions", ("version_id",), "paper_versions", ("id",), "RESTRICT")},
    "relation_observations": {("fk_relation_observations_relation_id_entity_relations", ("relation_id",), "entity_relations", ("id",), "RESTRICT"), ("fk_relation_observations_origin_task_id_tasks", ("origin_task_id",), "tasks", ("id",), "RESTRICT"), ("fk_relation_observations_evidence_ref_id_evidence_refs", ("evidence_ref_id",), "evidence_refs", ("id",), "RESTRICT")},
    "audit_logs": {("fk_audit_logs_task_id_tasks", ("task_id",), "tasks", ("id",), "RESTRICT"), ("fk_audit_logs_undo_of_audit_id_audit_logs", ("undo_of_audit_id",), "audit_logs", ("id",), "RESTRICT")},
    "task_attempts": {("fk_task_attempts_task_id_tasks", ("task_id",), "tasks", ("id",), "RESTRICT")},
    "task_effects": {("fk_task_effects_task_id_tasks", ("task_id",), "tasks", ("id",), "RESTRICT"), ("fk_task_effects_attempt_id_task_attempts", ("attempt_id",), "task_attempts", ("id",), "RESTRICT")},
}

EXPECTED_UNIQUE_DETAILS = {
    "source_documents": set(), "papers": set(), "ideas": set(), "notes": set(),
    "submissions": set(), "conferences": set(), "grants": set(), "evidence_refs": set(),
    "paper_versions": {("uq_paper_versions_paper_label", ("paper_id", "version_label"))},
    "entity_relations": {("uq_entity_relations_assertion", ("relation_type", "source_type", "source_id", "target_type", "target_id"))},
    "relation_observations": {("uq_relation_observations_observation_key", ("observation_key",))},
    "audit_logs": {("uq_audit_logs_undo_token", ("undo_token",)), ("uq_audit_logs_undo_of_audit_id", ("undo_of_audit_id",))},
    "tasks": {("uq_tasks_idempotency_key", ("idempotency_key",))},
    "task_attempts": {("uq_task_attempts_task_attempt", ("task_id", "attempt_number"))},
    "task_effects": {("uq_task_effects_operation_key", ("operation_key",))},
    "domain_events": {("uq_domain_events_deduplication_key", ("deduplication_key",))},
}

EXPECTED_INDEX_DETAILS = {
    "papers": set(), "ideas": set(), "notes": set(), "submissions": set(),
    "conferences": set(), "grants": set(), "evidence_refs": set(), "entity_relations": set(),
    "relation_observations": set(), "audit_logs": set(), "tasks": set(),
    "task_attempts": set(), "task_effects": set(), "domain_events": set(),
    "source_documents": {("ix_source_documents_sha256", ("sha256",), False, None), ("ux_source_documents_path_nocase", ("path",), True, None)},
    "paper_versions": {("ux_paper_versions_one_current", ("paper_id",), True, "is_current=1")},
}

EXPECTED_CHECK_SQL = {
    "source_documents": {"original_read_only": "read_only=1", "sha256_lower_hex": "length(sha256)=64ANDsha256NOTGLOB'*[^0-9a-f]*'", "size_bytes_nonnegative": "size_bytes>=0"},
    "papers": {"deleted_after_created": "deleted_atISNULLORdeleted_at>=created_at", "status_enum": "statusIN('active','paused','revision','submitted','completed','archived')", "title_length": "length(trim(title))BETWEEN1AND500", "updated_after_created": "updated_at>=created_at"},
    "paper_versions": {"parent_not_self": "parent_version_idISNULLORparent_version_id<>id"},
    "ideas": {"content_nonempty": "length(content)>0", "origin_enum": "origin_typeIN('manual','document','note','meeting','chat','book','paper','ai_candidate')", "status_enum": "statusIN('unused','used','parked','archived')", "title_length": "length(trim(title))BETWEEN1AND500", "updated_after_created": "updated_at>=created_at"},
    "notes": {"content_nonempty": "length(content)>0", "title_length": "length(trim(title))BETWEEN1AND500", "updated_after_created": "updated_at>=created_at"},
    "submissions": {"status_enum": "statusIN('preparing','ready','submitted','editorial_review','external_review','revision','accepted','rejected','withdrawn','no_response')", "venue_nonempty": "length(trim(venue))>0"},
    "conferences": {"ends_after_starts": "ends_atISNULLORstarts_atISNULLORends_at>=starts_at", "name_nonempty": "length(trim(name))>0", "status_enum": "statusIN('planned','registered','attending','completed','cancelled')"},
    "grants": {"name_nonempty": "length(trim(name))>0", "status_enum": "statusIN('watching','preparing','submitted','awarded','rejected','archived')"},
    "evidence_refs": {"char_range": "char_endISNULLOR(char_startISNOTNULLANDchar_end>=char_start)", "char_start_nonnegative": "char_startISNULLORchar_start>=0", "entity_type_enum": "entity_typeIN('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EntityRelation')", "page_positive": "pageISNULLORpage>=1", "paragraph_id_lower_hex": "paragraph_idISNULLOR(length(paragraph_id)=64ANDparagraph_idNOTGLOB'*[^0-9a-f]*')", "quote_hash_lower_hex": "length(quote_hash)=64ANDquote_hashNOTGLOB'*[^0-9a-f]*'", "slide_positive": "slideISNULLORslide>=1"},
    "entity_relations": {"actor_type_enum": "created_by_actor_typeIN('user','system','task_executor','agent')", "confidence_range": "confidenceISNULLOR(confidence>=0ANDconfidence<=1)", "confirmation_state_enum": "confirmation_stateIN('candidate','confirmed','rejected')", "relation_type_enum": "relation_typeIN('belongs_to','derived_from','version_of','used_in','deleted_from','supports','contradicts','extends','related_to','presented_at','submitted_as','reviewed_by','suggested_for','split_from','merged_from')", "source_type_enum": "source_typeIN('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef')", "target_type_enum": "target_typeIN('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef')"},
    "relation_observations": {"actor_type_enum": "observed_by_actor_typeIN('user','system','task_executor','agent')", "ai_provider_model": "provenance_type<>'ai'OR(provider_idISNOTNULLANDmodel_idISNOTNULL)", "confidence_provenance": "provenance_typeNOTIN('import','ai')ORconfidenceISNOTNULL", "confidence_range": "confidenceISNULLOR(confidence>=0ANDconfidence<=1)", "evidence_provenance": "provenance_typeNOTIN('import','ai')ORevidence_ref_idISNOTNULL", "provenance_type_enum": "provenance_typeIN('manual','rule','import','ai')", "task_actor_origin": "observed_by_actor_typeNOTIN('task_executor','agent')ORorigin_task_idISNOTNULL"},
    "audit_logs": {"actor_type_enum": "actor_typeIN('user','system','task_executor','agent')", "before_or_after": "before_jsonISNOTNULLORafter_jsonISNOTNULL", "target_type_enum": "target_typeIN('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef','EntityRelation','RelationObservation','Task')"},
    "tasks": {"attempt_count_nonnegative": "attempt_count>=0", "lease_expiry_with_owner": "lease_ownerISNULLORlease_expires_atISNOTNULL", "lease_generation_nonnegative": "lease_generation>=0", "max_attempts_range": "max_attemptsBETWEEN1AND10", "request_fingerprint_lower_hex": "length(request_fingerprint)=64ANDrequest_fingerprintNOTGLOB'*[^0-9a-f]*'", "status_enum": "statusIN('pending','running','needs_confirmation','succeeded','failed','cancelled')", "task_type_enum": "task_typeIN('import_document','compare_versions','extract_idea_candidates','recover_paper_context','refresh_submission_overview','scheduled_incremental_organize','export_data')"},
    "task_attempts": {"attempt_number_positive": "attempt_number>=1", "closed_attempt_result": "(status='running'ANDfinished_atISNULLANDresult_jsonISNULL)OR(status<>'running'ANDfinished_atISNOTNULLANDresult_jsonISNOTNULL)", "lease_generation_nonnegative": "lease_generation>=0", "status_enum": "statusIN('running','retry_scheduled','succeeded','failed','cancelled','needs_confirmation')"},
    "task_effects": {"committed_timestamp": "status<>'committed'ORcommitted_atISNOTNULL", "operation_key_lower_hex": "length(operation_key)=64ANDoperation_keyNOTGLOB'*[^0-9a-f]*'", "status_enum": "statusIN('prepared','committed','manual_reconciliation')"},
    "domain_events": {"aggregate_type_enum": "aggregate_typeIN('Paper','PaperVersion','Idea','SourceDocument','Submission','Conference','Grant','Task','AuditLog')", "event_type_enum": "event_typeIN('document.imported','paper.created','paper.version_added','paper.version_relation_corrected','idea.created','idea.candidate_extracted','idea.linked','submission.created','submission.status_changed','context.recovered','task.failed','audit.undo_applied')"},
}


def test_core_metadata_has_exact_columns(engine):
    Base.metadata.create_all(engine)
    _assert_exact_schema(inspect(engine))


def _assert_exact_schema(inspector):
    assert set(inspector.get_table_names()) - {"alembic_version"} == set(EXPECTED_SCHEMA)
    for table, expected in EXPECTED_SCHEMA.items():
        actual = {
            col["name"]: (str(col["type"]), col["nullable"])
            for col in inspector.get_columns(table)
        }
        assert actual == expected


def test_relation_assertion_is_unique(engine):
    Base.metadata.create_all(engine)
    uniques = inspect(engine).get_unique_constraints("entity_relations")
    assert {tuple(item["column_names"]) for item in uniques} >= {
        ("relation_type", "source_type", "source_id", "target_type", "target_id"),
    }


def test_group_two_foreign_keys(engine):
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    actual = {
        (table, tuple(fk["constrained_columns"]), fk["referred_table"], fk["options"].get("ondelete"))
        for table in ("evidence_refs", "relation_observations", "audit_logs")
        for fk in inspector.get_foreign_keys(table)
    }
    assert actual == {
        ("evidence_refs", ("document_id",), "source_documents", "RESTRICT"),
        ("evidence_refs", ("version_id",), "paper_versions", "RESTRICT"),
        ("relation_observations", ("relation_id",), "entity_relations", "RESTRICT"),
        ("relation_observations", ("evidence_ref_id",), "evidence_refs", "RESTRICT"),
        ("audit_logs", ("undo_of_audit_id",), "audit_logs", "RESTRICT"),
        ("relation_observations", ("origin_task_id",), "tasks", "RESTRICT"),
        ("audit_logs", ("task_id",), "tasks", "RESTRICT"),
    }


def test_defaults_checks_foreign_keys_uniques_and_indexes_are_exact(engine):
    Base.metadata.create_all(engine)
    _assert_exact_constraints(inspect(engine))


def _assert_exact_constraints(inspector):
    for table in EXPECTED_SCHEMA:
        defaults = {col["name"]: str(col["default"]) for col in inspector.get_columns(table) if col["default"] is not None}
        assert defaults == EXPECTED_DEFAULTS[table]
        primary_key = inspector.get_pk_constraint(table)
        assert (primary_key["name"], tuple(primary_key["constrained_columns"])) == EXPECTED_PRIMARY_KEYS[table]
        checks = {item["name"].removeprefix(f"ck_{table}_"): "".join(item["sqltext"].split()) for item in inspector.get_check_constraints(table)}
        assert checks == EXPECTED_CHECK_SQL[table]
        foreign_keys = {(fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]), fk["options"].get("ondelete")) for fk in inspector.get_foreign_keys(table)}
        assert foreign_keys == EXPECTED_FOREIGN_KEY_DETAILS[table]
        uniques = {(item["name"], tuple(item["column_names"])) for item in inspector.get_unique_constraints(table)}
        assert uniques == EXPECTED_UNIQUE_DETAILS[table]
        indexes = {(item["name"], tuple(item["column_names"]), bool(item["unique"]), "".join(str(item.get("dialect_options", {}).get("sqlite_where")).split()) if item.get("dialect_options", {}).get("sqlite_where") is not None else None) for item in inspector.get_indexes(table)}
        assert indexes == EXPECTED_INDEX_DETAILS[table]


def test_source_document_path_uniqueness_is_nocase(engine):
    Base.metadata.create_all(engine)
    _assert_source_document_path_uniqueness_is_nocase(engine)


def _assert_source_document_path_uniqueness_is_nocase(engine):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    common = dict(sha256="a" * 64, mime_type="application/pdf", size_bytes=1,
        modified_at=now, imported_at=now, read_only=True, missing_at=None)
    with Session(engine) as session:
        session.add(SourceDocumentModel(id="00000000-0000-0000-0000-000000000001", path="C:/Research/Paper.PDF", **common))
        session.flush()
        session.add(SourceDocumentModel(id="00000000-0000-0000-0000-000000000002", path="c:/research/paper.pdf", **common))
        with pytest.raises(IntegrityError):
            session.flush()


def test_utc_datetime_rejects_noncanonical_values():
    storage = UTCDateTime()
    with pytest.raises(ValueError):
        storage.process_bind_param("2026-06-01T00:00:00+00:00", None)
    with pytest.raises(ValueError):
        storage.process_bind_param("not-a-timestamp", None)
    with pytest.raises(ValueError):
        storage.process_bind_param(datetime(2026, 6, 1, tzinfo=timezone(timedelta(hours=9))), None)
    assert storage.process_bind_param("2026-06-01T00:00:00Z", None) == "2026-06-01T00:00:00Z"


@pytest.mark.parametrize("value", [
    "2026-W23-1T00:00:00Z",
    "2026-06-01T00:00Z",
    "2026-06-01X00:00:00Z",
])
def test_utc_datetime_rejects_noncanonical_rfc3339_shapes(value):
    with pytest.raises(ValueError):
        UTCDateTime().process_bind_param(value, None)


def test_utc_datetime_accepts_fractional_seconds():
    value = "2026-06-01T00:00:00.123456Z"
    assert UTCDateTime().process_bind_param(value, None) == value


def test_confidence_mappings_use_decimal_annotations():
    assert get_type_hints(EntityRelationModel, include_extras=True)["confidence"] == Mapped[Decimal | None]
    assert get_type_hints(RelationObservationModel, include_extras=True)["confidence"] == Mapped[Decimal | None]
