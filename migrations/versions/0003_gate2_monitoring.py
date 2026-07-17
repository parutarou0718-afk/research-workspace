"""Add Gate 2 monitoring and deterministic version-candidate persistence.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import context, op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _execute_all(statements: tuple[str, ...]) -> None:
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    _execute_all(_GATE2_DDL)
    if context.config.attributes.get("inject_0003_failure_after") == "gate2_tables":
        raise RuntimeError("injected 0003 failure after gate2 tables")
    op.execute(
        """ALTER TABLE source_observations
        ADD COLUMN monitoring_root_id CHAR(36)
        REFERENCES monitoring_roots(id) ON DELETE RESTRICT"""
    )
    op.execute(
        """ALTER TABLE source_observation_events
        ADD COLUMN raw_file_event_id CHAR(36)
        REFERENCES raw_file_events(id) ON DELETE RESTRICT"""
    )


def downgrade() -> None:
    op.drop_column("source_observation_events", "raw_file_event_id")
    op.drop_column("source_observations", "monitoring_root_id")
    _execute_all(
        (
            "DROP TABLE paper_version_candidates",
            "DROP TABLE reconciliation_runs",
            "DROP TABLE raw_event_pending_links",
            "DROP TABLE pending_path_checks",
            "DROP TABLE raw_file_events",
            "DROP TABLE monitoring_roots",
        )
    )


_GATE2_DDL = (
    """
    CREATE TABLE monitoring_roots (
        id CHAR(36) PRIMARY KEY NOT NULL,
        original_path TEXT NOT NULL,
        normalized_path TEXT COLLATE NOCASE NOT NULL,
        normalized_path_hash CHAR(64) NOT NULL,
        status VARCHAR(64) NOT NULL,
        recursive BOOLEAN NOT NULL DEFAULT 1,
        config_json TEXT NOT NULL,
        config_fingerprint CHAR(64) NOT NULL,
        watcher_generation INTEGER NOT NULL DEFAULT 0,
        last_event_at TEXT,
        last_reconciled_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        removed_at TEXT,
        CONSTRAINT uq_monitoring_roots_normalized_path UNIQUE (normalized_path),
        CONSTRAINT ck_monitoring_roots_path_hash CHECK (
            length(normalized_path_hash)=64
            AND normalized_path_hash NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_monitoring_roots_config_hash CHECK (
            length(config_fingerprint)=64
            AND config_fingerprint NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_monitoring_roots_status CHECK (
            status IN ('active','paused','disconnected','degraded',
                       'overflow_reconciling','error')
        ),
        CONSTRAINT ck_monitoring_roots_recursive CHECK (recursive=1),
        CONSTRAINT ck_monitoring_roots_generation CHECK (watcher_generation>=0)
    )
    """,
    """
    CREATE TABLE raw_file_events (
        id CHAR(36) PRIMARY KEY NOT NULL,
        monitoring_root_id CHAR(36) NOT NULL
            REFERENCES monitoring_roots(id) ON DELETE RESTRICT,
        provider VARCHAR(128) NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        source_path TEXT,
        destination_path TEXT,
        source_path_hash CHAR(64),
        destination_path_hash CHAR(64),
        observed_at TEXT NOT NULL,
        ingested_at TEXT NOT NULL,
        raw_sequence_json TEXT,
        correlation_hint VARCHAR(255),
        deduplication_key CHAR(64) NOT NULL,
        CONSTRAINT uq_raw_file_events_deduplication UNIQUE (deduplication_key),
        CONSTRAINT ck_raw_file_events_type CHECK (
            event_type IN ('created','modified','moved','deleted','overflow','root_state')
        ),
        CONSTRAINT ck_raw_file_events_source_hash CHECK (
            source_path_hash IS NULL OR (
                length(source_path_hash)=64
                AND source_path_hash NOT GLOB '*[^0-9a-f]*'
            )
        ),
        CONSTRAINT ck_raw_file_events_destination_hash CHECK (
            destination_path_hash IS NULL OR (
                length(destination_path_hash)=64
                AND destination_path_hash NOT GLOB '*[^0-9a-f]*'
            )
        ),
        CONSTRAINT ck_raw_file_events_dedup_hash CHECK (
            length(deduplication_key)=64
            AND deduplication_key NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_raw_file_events_move_destination CHECK (
            event_type <> 'moved' OR destination_path IS NOT NULL
        )
    )
    """,
    "CREATE INDEX ix_raw_file_events_root_observed ON raw_file_events (monitoring_root_id, observed_at)",
    "CREATE INDEX ix_raw_file_events_source_hash_observed ON raw_file_events (source_path_hash, observed_at)",
    "CREATE INDEX ix_raw_file_events_correlation_hint ON raw_file_events (correlation_hint)",
    """
    CREATE TABLE pending_path_checks (
        id CHAR(36) PRIMARY KEY NOT NULL,
        monitoring_root_id CHAR(36) NOT NULL
            REFERENCES monitoring_roots(id) ON DELETE RESTRICT,
        normalized_path TEXT COLLATE NOCASE NOT NULL,
        normalized_path_hash CHAR(64) NOT NULL,
        first_event_at TEXT NOT NULL,
        last_event_at TEXT NOT NULL,
        merged_event_types_json TEXT NOT NULL,
        state VARCHAR(64) NOT NULL,
        stability_attempt_count INTEGER NOT NULL DEFAULT 0,
        next_check_at TEXT,
        last_failure_code VARCHAR(128),
        source_observation_id CHAR(36)
            REFERENCES source_observations(id) ON DELETE RESTRICT,
        row_version INTEGER NOT NULL DEFAULT 1,
        CONSTRAINT uq_pending_path_checks_root_path
            UNIQUE (monitoring_root_id, normalized_path),
        CONSTRAINT ck_pending_path_checks_hash CHECK (
            length(normalized_path_hash)=64
            AND normalized_path_hash NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_pending_path_checks_state CHECK (
            state IN ('detected','debouncing','waiting_for_stability','importing',
                      'imported','duplicate_content','safe_failure','unstable_source')
        ),
        CONSTRAINT ck_pending_path_checks_attempts CHECK (stability_attempt_count>=0),
        CONSTRAINT ck_pending_path_checks_version CHECK (row_version>=1),
        CONSTRAINT ck_pending_path_checks_times CHECK (last_event_at>=first_event_at)
    )
    """,
    "CREATE INDEX ix_pending_path_checks_path_hash ON pending_path_checks (normalized_path_hash)",
    "CREATE INDEX ix_pending_path_checks_state_due ON pending_path_checks (state, next_check_at)",
    """
    CREATE TABLE raw_event_pending_links (
        raw_file_event_id CHAR(36) NOT NULL
            REFERENCES raw_file_events(id) ON DELETE RESTRICT,
        pending_path_check_id CHAR(36) NOT NULL
            REFERENCES pending_path_checks(id) ON DELETE RESTRICT,
        linked_at TEXT NOT NULL,
        PRIMARY KEY (raw_file_event_id, pending_path_check_id)
    )
    """,
    """
    CREATE TABLE reconciliation_runs (
        id CHAR(36) PRIMARY KEY NOT NULL,
        monitoring_root_id CHAR(36) NOT NULL
            REFERENCES monitoring_roots(id) ON DELETE RESTRICT,
        operation_id CHAR(36) NOT NULL
            REFERENCES background_operations(id) ON DELETE RESTRICT,
        reason VARCHAR(64) NOT NULL,
        status VARCHAR(64) NOT NULL,
        checkpoint_json TEXT,
        items_seen INTEGER NOT NULL DEFAULT 0,
        items_estimated INTEGER,
        items_suspected_changed INTEGER NOT NULL DEFAULT 0,
        started_at TEXT,
        finished_at TEXT,
        CONSTRAINT uq_reconciliation_runs_operation UNIQUE (operation_id),
        CONSTRAINT ck_reconciliation_runs_reason CHECK (
            reason IN ('baseline','disconnect','overflow','unclean_shutdown','user_verify')
        ),
        CONSTRAINT ck_reconciliation_runs_status CHECK (
            status IN ('planned','running','paused','completed','failed','cancelled')
        ),
        CONSTRAINT ck_reconciliation_runs_counts CHECK (
            items_seen>=0
            AND items_suspected_changed>=0
            AND (items_estimated IS NULL OR items_estimated>=items_seen)
        )
    )
    """,
    """
    CREATE TABLE paper_version_candidates (
        id CHAR(36) PRIMARY KEY NOT NULL,
        earlier_snapshot_id CHAR(36) NOT NULL
            REFERENCES source_snapshots(id) ON DELETE RESTRICT,
        later_snapshot_id CHAR(36) NOT NULL
            REFERENCES source_snapshots(id) ON DELETE RESTRICT,
        detector_id VARCHAR(255) NOT NULL,
        detector_version VARCHAR(128) NOT NULL,
        rule_id VARCHAR(32) NOT NULL,
        rule_config_fingerprint CHAR(64) NOT NULL,
        direction_rationale_json TEXT NOT NULL,
        signals_json TEXT NOT NULL,
        input_observation_ids_json TEXT NOT NULL,
        status VARCHAR(64) NOT NULL DEFAULT 'pending',
        superseded_by_candidate_id CHAR(36)
            REFERENCES paper_version_candidates(id) ON DELETE RESTRICT,
        row_version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        decided_at TEXT,
        CONSTRAINT uq_paper_version_candidates_identity UNIQUE (earlier_snapshot_id, later_snapshot_id, detector_id, detector_version, rule_config_fingerprint),
        CONSTRAINT ck_paper_version_candidates_distinct CHECK (
            earlier_snapshot_id<>later_snapshot_id
        ),
        CONSTRAINT ck_paper_version_candidates_detector CHECK (
            length(trim(detector_id))>0 AND length(trim(detector_version))>0
        ),
        CONSTRAINT ck_paper_version_candidates_rule CHECK (
            rule_id IN (
                'R1_SOURCE_CONTINUITY',
                'R2_REPLACE_CONTINUITY',
                'R3_PAPER_TITLE_TIME',
                'R4_NAME_TITLE_TEXT',
                'R5_ZERO_TEXT_LINEAGE'
            )
        ),
        CONSTRAINT ck_paper_version_candidates_hash CHECK (
            length(rule_config_fingerprint)=64
            AND rule_config_fingerprint NOT GLOB '*[^0-9a-f]*'
        ),
        CONSTRAINT ck_paper_version_candidates_status CHECK (
            status IN ('pending','confirmed','rejected','superseded')
        ),
        CONSTRAINT ck_paper_version_candidates_supersession CHECK (
            (status='superseded' AND superseded_by_candidate_id IS NOT NULL)
            OR (status<>'superseded' AND superseded_by_candidate_id IS NULL)
        ),
        CONSTRAINT ck_paper_version_candidates_decision_time CHECK (
            (status IN ('confirmed','rejected') AND decided_at IS NOT NULL)
            OR (status NOT IN ('confirmed','rejected') AND decided_at IS NULL)
        ),
        CONSTRAINT ck_paper_version_candidates_version CHECK (row_version>=1)
    )
    """,
    "CREATE INDEX ix_paper_version_candidates_earlier ON paper_version_candidates (earlier_snapshot_id)",
    "CREATE INDEX ix_paper_version_candidates_later ON paper_version_candidates (later_snapshot_id)",
)
