from sqlalchemy import inspect

from research_workspace.infrastructure.db.base import Base
import research_workspace.infrastructure.db.models  # noqa: F401


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

EXPECTED_CHECKS = {
    "source_documents": {"original_read_only", "sha256_lower_hex", "size_bytes_nonnegative"},
    "papers": {"deleted_after_created", "status_enum", "title_length", "updated_after_created"},
    "paper_versions": {"parent_not_self"},
    "ideas": {"content_nonempty", "origin_enum", "status_enum", "title_length", "updated_after_created"},
    "notes": {"content_nonempty", "title_length", "updated_after_created"},
    "submissions": {"status_enum", "updated_after_created", "venue_nonempty"},
    "conferences": {"ends_after_starts", "name_nonempty", "status_enum", "updated_after_created"},
    "grants": {"name_nonempty", "status_enum", "updated_after_created"},
    "evidence_refs": {"char_range", "char_start_nonnegative", "entity_type_enum", "page_positive", "paragraph_id_lower_hex", "quote_hash_lower_hex", "slide_positive"},
    "entity_relations": {"actor_type_enum", "confidence_range", "confirmation_state_enum", "relation_type_enum", "source_type_enum", "target_type_enum", "updated_after_created"},
    "relation_observations": {"actor_type_enum", "ai_provider_model", "confidence_provenance", "confidence_range", "evidence_provenance", "provenance_type_enum", "task_actor_origin"},
    "audit_logs": {"actor_type_enum", "before_or_after", "target_type_enum"},
    "tasks": {"attempt_count_nonnegative", "lease_expiry_with_owner", "lease_generation_nonnegative", "max_attempts_range", "request_fingerprint_lower_hex", "status_enum", "task_type_enum"},
    "task_attempts": {"attempt_number_positive", "closed_attempt_result", "lease_generation_nonnegative", "status_enum"},
    "task_effects": {"committed_timestamp", "operation_key_lower_hex", "status_enum"},
    "domain_events": {"aggregate_type_enum", "event_type_enum"},
}

EXPECTED_FOREIGN_KEYS = {
    "source_documents": set(), "papers": {("current_version_id", "paper_versions", "SET NULL")},
    "paper_versions": {("paper_id", "papers", "RESTRICT"), ("source_document_id", "source_documents", "RESTRICT"), ("parent_version_id", "paper_versions", "RESTRICT")},
    "ideas": set(), "notes": {("source_document_id", "source_documents", "RESTRICT")},
    "submissions": {("paper_id", "papers", "RESTRICT"), ("active_version_id", "paper_versions", "RESTRICT")},
    "conferences": set(), "grants": set(),
    "evidence_refs": {("document_id", "source_documents", "RESTRICT"), ("version_id", "paper_versions", "RESTRICT")},
    "entity_relations": set(),
    "relation_observations": {("relation_id", "entity_relations", "RESTRICT"), ("origin_task_id", "tasks", "RESTRICT"), ("evidence_ref_id", "evidence_refs", "RESTRICT")},
    "audit_logs": {("task_id", "tasks", "RESTRICT"), ("undo_of_audit_id", "audit_logs", "RESTRICT")},
    "tasks": set(), "task_attempts": {("task_id", "tasks", "RESTRICT")},
    "task_effects": {("task_id", "tasks", "RESTRICT"), ("attempt_id", "task_attempts", "RESTRICT")},
    "domain_events": set(),
}

EXPECTED_UNIQUES = {
    "source_documents": set(), "papers": set(), "paper_versions": {("paper_id", "version_label")},
    "ideas": set(), "notes": set(), "submissions": set(), "conferences": set(), "grants": set(),
    "evidence_refs": set(),
    "entity_relations": {("relation_type", "source_type", "source_id", "target_type", "target_id")},
    "relation_observations": {("observation_key",)},
    "audit_logs": {("undo_token",), ("undo_of_audit_id",)},
    "tasks": {("idempotency_key",)}, "task_attempts": {("task_id", "attempt_number")},
    "task_effects": {("operation_key",)}, "domain_events": {("deduplication_key",)},
}

EXPECTED_INDEXES = {
    "source_documents": {("ix_source_documents_sha256", ("sha256",), False), ("ux_source_documents_path_nocase", ("path",), True)},
    "paper_versions": {("ux_paper_versions_one_current", ("paper_id",), True)},
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
        check_names = {item["name"].removeprefix(f"ck_{table}_") for item in inspector.get_check_constraints(table)}
        assert check_names == EXPECTED_CHECKS[table]
        foreign_keys = {(fk["constrained_columns"][0], fk["referred_table"], fk["options"].get("ondelete")) for fk in inspector.get_foreign_keys(table)}
        assert foreign_keys == EXPECTED_FOREIGN_KEYS[table]
        uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)}
        assert uniques == EXPECTED_UNIQUES[table]
        indexes = {(item["name"], tuple(item["column_names"]), bool(item["unique"])) for item in inspector.get_indexes(table)}
        assert indexes == EXPECTED_INDEXES.get(table, set())

    current_index = next(item for item in inspector.get_indexes("paper_versions") if item["name"] == "ux_paper_versions_one_current")
    assert str(current_index["dialect_options"]["sqlite_where"]) == "is_current = 1"
