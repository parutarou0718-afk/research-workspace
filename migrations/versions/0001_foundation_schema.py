"""Create the immutable v0.1 foundation schema.

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


_TABLE_DDL = (
    """CREATE TABLE source_documents (
        id CHAR(36) NOT NULL, path TEXT COLLATE NOCASE NOT NULL, sha256 CHAR(64) NOT NULL,
        mime_type VARCHAR(255) NOT NULL, size_bytes INTEGER NOT NULL, modified_at TEXT NOT NULL,
        imported_at TEXT NOT NULL, read_only BOOLEAN DEFAULT 1 NOT NULL, missing_at TEXT,
        CONSTRAINT pk_source_documents PRIMARY KEY (id),
        CONSTRAINT ck_source_documents_size_bytes_nonnegative CHECK (size_bytes >= 0),
        CONSTRAINT ck_source_documents_sha256_lower_hex CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
        CONSTRAINT ck_source_documents_original_read_only CHECK (read_only = 1))""",
    """CREATE TABLE papers (
        id CHAR(36) NOT NULL, title VARCHAR(500) NOT NULL, status VARCHAR(64) DEFAULT 'active' NOT NULL,
        current_version_id CHAR(36), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,
        CONSTRAINT pk_papers PRIMARY KEY (id),
        CONSTRAINT ck_papers_title_length CHECK (length(trim(title)) BETWEEN 1 AND 500),
        CONSTRAINT ck_papers_status_enum CHECK (status IN ('active','paused','revision','submitted','completed','archived')),
        CONSTRAINT ck_papers_updated_after_created CHECK (updated_at >= created_at),
        CONSTRAINT ck_papers_deleted_after_created CHECK (deleted_at IS NULL OR deleted_at >= created_at),
        CONSTRAINT fk_papers_current_version_id_paper_versions FOREIGN KEY(current_version_id) REFERENCES paper_versions(id) ON DELETE SET NULL)""",
    """CREATE TABLE paper_versions (
        id CHAR(36) NOT NULL, paper_id CHAR(36) NOT NULL, source_document_id CHAR(36) NOT NULL,
        version_label VARCHAR(128) NOT NULL, parent_version_id CHAR(36), is_current BOOLEAN DEFAULT 0 NOT NULL,
        created_at TEXT NOT NULL, CONSTRAINT pk_paper_versions PRIMARY KEY (id),
        CONSTRAINT uq_paper_versions_paper_label UNIQUE (paper_id, version_label),
        CONSTRAINT ck_paper_versions_parent_not_self CHECK (parent_version_id IS NULL OR parent_version_id <> id),
        CONSTRAINT fk_paper_versions_paper_id_papers FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE RESTRICT,
        CONSTRAINT fk_paper_versions_source_document_id_source_documents FOREIGN KEY(source_document_id) REFERENCES source_documents(id) ON DELETE RESTRICT,
        CONSTRAINT fk_paper_versions_parent_version_id_paper_versions FOREIGN KEY(parent_version_id) REFERENCES paper_versions(id) ON DELETE RESTRICT)""",
    """CREATE TABLE ideas (
        id CHAR(36) NOT NULL, title VARCHAR(500) NOT NULL, content TEXT NOT NULL,
        status VARCHAR(64) DEFAULT 'unused' NOT NULL, origin_type VARCHAR(64) DEFAULT 'manual' NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT, CONSTRAINT pk_ideas PRIMARY KEY (id),
        CONSTRAINT ck_ideas_title_length CHECK (length(trim(title)) BETWEEN 1 AND 500),
        CONSTRAINT ck_ideas_content_nonempty CHECK (length(content) > 0),
        CONSTRAINT ck_ideas_status_enum CHECK (status IN ('unused','used','parked','archived')),
        CONSTRAINT ck_ideas_origin_enum CHECK (origin_type IN ('manual','document','note','meeting','chat','book','paper','ai_candidate')),
        CONSTRAINT ck_ideas_updated_after_created CHECK (updated_at >= created_at))""",
    """CREATE TABLE notes (
        id CHAR(36) NOT NULL, title VARCHAR(500) NOT NULL, content TEXT NOT NULL, source_document_id CHAR(36),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT, CONSTRAINT pk_notes PRIMARY KEY (id),
        CONSTRAINT ck_notes_title_length CHECK (length(trim(title)) BETWEEN 1 AND 500),
        CONSTRAINT ck_notes_content_nonempty CHECK (length(content) > 0),
        CONSTRAINT ck_notes_updated_after_created CHECK (updated_at >= created_at),
        CONSTRAINT fk_notes_source_document_id_source_documents FOREIGN KEY(source_document_id) REFERENCES source_documents(id) ON DELETE RESTRICT)""",
    """CREATE TABLE submissions (
        id CHAR(36) NOT NULL, paper_id CHAR(36) NOT NULL, venue VARCHAR(500) NOT NULL,
        status VARCHAR(64) DEFAULT 'preparing' NOT NULL, submitted_at TEXT, deadline_at TEXT, active_version_id CHAR(36),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT, CONSTRAINT pk_submissions PRIMARY KEY (id),
        CONSTRAINT ck_submissions_venue_nonempty CHECK (length(trim(venue)) > 0),
        CONSTRAINT ck_submissions_status_enum CHECK (status IN ('preparing','ready','submitted','editorial_review','external_review','revision','accepted','rejected','withdrawn','no_response')),
        CONSTRAINT fk_submissions_paper_id_papers FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE RESTRICT,
        CONSTRAINT fk_submissions_active_version_id_paper_versions FOREIGN KEY(active_version_id) REFERENCES paper_versions(id) ON DELETE RESTRICT)""",
    """CREATE TABLE conferences (
        id CHAR(36) NOT NULL, name VARCHAR(500) NOT NULL, starts_at TEXT, ends_at TEXT, location VARCHAR(500),
        status VARCHAR(64) DEFAULT 'planned' NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,
        CONSTRAINT pk_conferences PRIMARY KEY (id), CONSTRAINT ck_conferences_name_nonempty CHECK (length(trim(name)) > 0),
        CONSTRAINT ck_conferences_status_enum CHECK (status IN ('planned','registered','attending','completed','cancelled')),
        CONSTRAINT ck_conferences_ends_after_starts CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at))""",
    """CREATE TABLE grants (
        id CHAR(36) NOT NULL, name VARCHAR(500) NOT NULL, status VARCHAR(64) DEFAULT 'watching' NOT NULL,
        deadline_at TEXT, source_url TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,
        CONSTRAINT pk_grants PRIMARY KEY (id), CONSTRAINT ck_grants_name_nonempty CHECK (length(trim(name)) > 0),
        CONSTRAINT ck_grants_status_enum CHECK (status IN ('watching','preparing','submitted','awarded','rejected','archived')))""",
    """CREATE TABLE tasks (
        id CHAR(36) NOT NULL, task_type VARCHAR(64) NOT NULL, status VARCHAR(64) DEFAULT 'pending' NOT NULL,
        idempotency_key VARCHAR(255) NOT NULL, request_fingerprint CHAR(64) NOT NULL, payload_json TEXT NOT NULL,
        result_json TEXT, attempt_count INTEGER DEFAULT 0 NOT NULL, max_attempts INTEGER DEFAULT 3 NOT NULL,
        next_attempt_at TEXT, lease_owner VARCHAR(255), lease_expires_at TEXT, lease_generation INTEGER DEFAULT 0 NOT NULL,
        created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, CONSTRAINT pk_tasks PRIMARY KEY (id),
        CONSTRAINT uq_tasks_idempotency_key UNIQUE (idempotency_key),
        CONSTRAINT ck_tasks_task_type_enum CHECK (task_type IN ('import_document','compare_versions','extract_idea_candidates','recover_paper_context','refresh_submission_overview','scheduled_incremental_organize','export_data')),
        CONSTRAINT ck_tasks_status_enum CHECK (status IN ('pending','running','needs_confirmation','succeeded','failed','cancelled')),
        CONSTRAINT ck_tasks_request_fingerprint_lower_hex CHECK (length(request_fingerprint) = 64 AND request_fingerprint NOT GLOB '*[^0-9a-f]*'),
        CONSTRAINT ck_tasks_attempt_count_nonnegative CHECK (attempt_count >= 0),
        CONSTRAINT ck_tasks_max_attempts_range CHECK (max_attempts BETWEEN 1 AND 10),
        CONSTRAINT ck_tasks_lease_generation_nonnegative CHECK (lease_generation >= 0),
        CONSTRAINT ck_tasks_lease_expiry_with_owner CHECK (lease_owner IS NULL OR lease_expires_at IS NOT NULL))""",
    """CREATE TABLE evidence_refs (
        id CHAR(36) NOT NULL, entity_type VARCHAR(64) NOT NULL, entity_id CHAR(36) NOT NULL,
        document_id CHAR(36) NOT NULL, version_id CHAR(36), section VARCHAR(1000), page INTEGER, slide INTEGER,
        paragraph_id CHAR(64), char_start INTEGER, char_end INTEGER, locator_json TEXT NOT NULL,
        quote_hash CHAR(64) NOT NULL, created_at TEXT NOT NULL, CONSTRAINT pk_evidence_refs PRIMARY KEY (id),
        CONSTRAINT ck_evidence_refs_entity_type_enum CHECK (entity_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EntityRelation')),
        CONSTRAINT ck_evidence_refs_page_positive CHECK (page IS NULL OR page >= 1),
        CONSTRAINT ck_evidence_refs_slide_positive CHECK (slide IS NULL OR slide >= 1),
        CONSTRAINT ck_evidence_refs_char_start_nonnegative CHECK (char_start IS NULL OR char_start >= 0),
        CONSTRAINT ck_evidence_refs_char_range CHECK (char_end IS NULL OR (char_start IS NOT NULL AND char_end >= char_start)),
        CONSTRAINT ck_evidence_refs_paragraph_id_lower_hex CHECK (paragraph_id IS NULL OR (length(paragraph_id) = 64 AND paragraph_id NOT GLOB '*[^0-9a-f]*')),
        CONSTRAINT ck_evidence_refs_quote_hash_lower_hex CHECK (length(quote_hash) = 64 AND quote_hash NOT GLOB '*[^0-9a-f]*'),
        CONSTRAINT fk_evidence_refs_document_id_source_documents FOREIGN KEY(document_id) REFERENCES source_documents(id) ON DELETE RESTRICT,
        CONSTRAINT fk_evidence_refs_version_id_paper_versions FOREIGN KEY(version_id) REFERENCES paper_versions(id) ON DELETE RESTRICT)""",
    """CREATE TABLE entity_relations (
        id CHAR(36) NOT NULL, source_type VARCHAR(64) NOT NULL, source_id CHAR(36) NOT NULL,
        relation_type VARCHAR(64) NOT NULL, target_type VARCHAR(64) NOT NULL, target_id CHAR(36) NOT NULL,
        confidence NUMERIC(6,5), confirmation_state VARCHAR(64) DEFAULT 'candidate' NOT NULL,
        created_by_actor_type VARCHAR(64) NOT NULL, created_by_actor_id VARCHAR(255), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        CONSTRAINT pk_entity_relations PRIMARY KEY (id),
        CONSTRAINT uq_entity_relations_assertion UNIQUE (relation_type,source_type,source_id,target_type,target_id),
        CONSTRAINT ck_entity_relations_source_type_enum CHECK (source_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef')),
        CONSTRAINT ck_entity_relations_target_type_enum CHECK (target_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef')),
        CONSTRAINT ck_entity_relations_relation_type_enum CHECK (relation_type IN ('belongs_to','derived_from','version_of','used_in','deleted_from','supports','contradicts','extends','related_to','presented_at','submitted_as','reviewed_by','suggested_for','split_from','merged_from')),
        CONSTRAINT ck_entity_relations_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
        CONSTRAINT ck_entity_relations_confirmation_state_enum CHECK (confirmation_state IN ('candidate','confirmed','rejected')),
        CONSTRAINT ck_entity_relations_actor_type_enum CHECK (created_by_actor_type IN ('user','system','task_executor','agent')))""",
    """CREATE TABLE relation_observations (
        id CHAR(36) NOT NULL, relation_id CHAR(36) NOT NULL, observed_by_actor_type VARCHAR(64) NOT NULL,
        observed_by_actor_id VARCHAR(255), provenance_type VARCHAR(64) NOT NULL, confidence NUMERIC(6,5),
        origin_task_id CHAR(36), evidence_ref_id CHAR(36), provider_id VARCHAR(255), model_id VARCHAR(255),
        observed_at TEXT NOT NULL, observation_key VARCHAR(255) NOT NULL, CONSTRAINT pk_relation_observations PRIMARY KEY (id),
        CONSTRAINT uq_relation_observations_observation_key UNIQUE (observation_key),
        CONSTRAINT ck_relation_observations_actor_type_enum CHECK (observed_by_actor_type IN ('user','system','task_executor','agent')),
        CONSTRAINT ck_relation_observations_provenance_type_enum CHECK (provenance_type IN ('manual','rule','import','ai')),
        CONSTRAINT ck_relation_observations_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
        CONSTRAINT ck_relation_observations_confidence_provenance CHECK (provenance_type NOT IN ('import','ai') OR confidence IS NOT NULL),
        CONSTRAINT ck_relation_observations_task_actor_origin CHECK (observed_by_actor_type NOT IN ('task_executor','agent') OR origin_task_id IS NOT NULL),
        CONSTRAINT ck_relation_observations_evidence_provenance CHECK (provenance_type NOT IN ('import','ai') OR evidence_ref_id IS NOT NULL),
        CONSTRAINT ck_relation_observations_ai_provider_model CHECK (provenance_type <> 'ai' OR (provider_id IS NOT NULL AND model_id IS NOT NULL)),
        CONSTRAINT fk_relation_observations_relation_id_entity_relations FOREIGN KEY(relation_id) REFERENCES entity_relations(id) ON DELETE RESTRICT,
        CONSTRAINT fk_relation_observations_origin_task_id_tasks FOREIGN KEY(origin_task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
        CONSTRAINT fk_relation_observations_evidence_ref_id_evidence_refs FOREIGN KEY(evidence_ref_id) REFERENCES evidence_refs(id) ON DELETE RESTRICT)""",
    """CREATE TABLE audit_logs (
        id CHAR(36) NOT NULL, actor_type VARCHAR(64) NOT NULL, actor_id VARCHAR(255), action VARCHAR(255) NOT NULL,
        target_type VARCHAR(64) NOT NULL, target_id CHAR(36) NOT NULL, before_json TEXT, after_json TEXT,
        task_id CHAR(36), correlation_id CHAR(36), undo_token VARCHAR(255), undo_of_audit_id CHAR(36), created_at TEXT NOT NULL,
        CONSTRAINT pk_audit_logs PRIMARY KEY (id), CONSTRAINT uq_audit_logs_undo_token UNIQUE (undo_token),
        CONSTRAINT uq_audit_logs_undo_of_audit_id UNIQUE (undo_of_audit_id),
        CONSTRAINT ck_audit_logs_actor_type_enum CHECK (actor_type IN ('user','system','task_executor','agent')),
        CONSTRAINT ck_audit_logs_target_type_enum CHECK (target_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef','EntityRelation','RelationObservation','Task')),
        CONSTRAINT ck_audit_logs_before_or_after CHECK (before_json IS NOT NULL OR after_json IS NOT NULL),
        CONSTRAINT fk_audit_logs_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
        CONSTRAINT fk_audit_logs_undo_of_audit_id_audit_logs FOREIGN KEY(undo_of_audit_id) REFERENCES audit_logs(id) ON DELETE RESTRICT)""",
    """CREATE TABLE task_attempts (
        id CHAR(36) NOT NULL, task_id CHAR(36) NOT NULL, attempt_number INTEGER NOT NULL,
        lease_generation INTEGER NOT NULL, lease_owner VARCHAR(255) NOT NULL, status VARCHAR(64) DEFAULT 'running' NOT NULL,
        result_json TEXT, started_at TEXT NOT NULL, finished_at TEXT, CONSTRAINT pk_task_attempts PRIMARY KEY (id),
        CONSTRAINT uq_task_attempts_task_attempt UNIQUE (task_id,attempt_number),
        CONSTRAINT ck_task_attempts_attempt_number_positive CHECK (attempt_number >= 1),
        CONSTRAINT ck_task_attempts_lease_generation_nonnegative CHECK (lease_generation >= 0),
        CONSTRAINT ck_task_attempts_status_enum CHECK (status IN ('running','retry_scheduled','succeeded','failed','cancelled','needs_confirmation')),
        CONSTRAINT ck_task_attempts_closed_attempt_result CHECK ((status='running' AND finished_at IS NULL AND result_json IS NULL) OR (status<>'running' AND finished_at IS NOT NULL AND result_json IS NOT NULL)),
        CONSTRAINT fk_task_attempts_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE RESTRICT)""",
    """CREATE TABLE task_effects (
        id CHAR(36) NOT NULL, operation_key CHAR(64) NOT NULL, task_id CHAR(36) NOT NULL, attempt_id CHAR(36) NOT NULL,
        effect_type VARCHAR(255) NOT NULL, output_type VARCHAR(255) NOT NULL, output_identity VARCHAR(1000) NOT NULL,
        output_ref_json TEXT NOT NULL, status VARCHAR(64) NOT NULL, recovery_json TEXT, created_at TEXT NOT NULL, committed_at TEXT,
        CONSTRAINT pk_task_effects PRIMARY KEY (id), CONSTRAINT uq_task_effects_operation_key UNIQUE (operation_key),
        CONSTRAINT ck_task_effects_operation_key_lower_hex CHECK (length(operation_key)=64 AND operation_key NOT GLOB '*[^0-9a-f]*'),
        CONSTRAINT ck_task_effects_status_enum CHECK (status IN ('prepared','committed','manual_reconciliation')),
        CONSTRAINT ck_task_effects_committed_timestamp CHECK (status <> 'committed' OR committed_at IS NOT NULL),
        CONSTRAINT fk_task_effects_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
        CONSTRAINT fk_task_effects_attempt_id_task_attempts FOREIGN KEY(attempt_id) REFERENCES task_attempts(id) ON DELETE RESTRICT)""",
    """CREATE TABLE domain_events (
        id CHAR(36) NOT NULL, event_type VARCHAR(64) NOT NULL, aggregate_type VARCHAR(64) NOT NULL,
        aggregate_id CHAR(36) NOT NULL, payload_json TEXT NOT NULL, deduplication_key VARCHAR(255) NOT NULL,
        causation_id CHAR(36), correlation_id CHAR(36), created_at TEXT NOT NULL, processed_at TEXT,
        CONSTRAINT pk_domain_events PRIMARY KEY (id), CONSTRAINT uq_domain_events_deduplication_key UNIQUE (deduplication_key),
        CONSTRAINT ck_domain_events_event_type_enum CHECK (event_type IN ('document.imported','paper.created','paper.version_added','paper.version_relation_corrected','idea.created','idea.candidate_extracted','idea.linked','submission.created','submission.status_changed','context.recovered','task.failed','audit.undo_applied')),
        CONSTRAINT ck_domain_events_aggregate_type_enum CHECK (aggregate_type IN ('Paper','PaperVersion','Idea','SourceDocument','Submission','Conference','Grant','Task','AuditLog')))""",
)

_INDEX_DDL = (
    "CREATE INDEX ix_source_documents_sha256 ON source_documents (sha256)",
    "CREATE UNIQUE INDEX ux_source_documents_path_nocase ON source_documents (path)",
    "CREATE UNIQUE INDEX ux_paper_versions_one_current ON paper_versions (paper_id) WHERE is_current = 1",
)


def upgrade() -> None:
    for statement in (*_TABLE_DDL, *_INDEX_DDL):
        op.execute(statement)


def downgrade() -> None:
    for table_name in (
        "domain_events", "task_effects", "task_attempts", "audit_logs",
        "relation_observations", "entity_relations", "evidence_refs", "tasks",
        "grants", "conferences", "submissions", "notes", "ideas",
        "paper_versions", "papers", "source_documents",
    ):
        op.drop_table(table_name)
