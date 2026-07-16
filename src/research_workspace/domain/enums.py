"""Closed values used by foundation domain records."""

from enum import Enum


class PaperStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    REVISION = "revision"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class IdeaStatus(str, Enum):
    UNUSED = "unused"
    USED = "used"
    PARKED = "parked"
    ARCHIVED = "archived"


class IdeaOriginType(str, Enum):
    MANUAL = "manual"
    DOCUMENT = "document"
    NOTE = "note"
    MEETING = "meeting"
    CHAT = "chat"
    BOOK = "book"
    PAPER = "paper"
    AI_CANDIDATE = "ai_candidate"


class SubmissionStatus(str, Enum):
    PREPARING = "preparing"
    READY = "ready"
    SUBMITTED = "submitted"
    EDITORIAL_REVIEW = "editorial_review"
    EXTERNAL_REVIEW = "external_review"
    REVISION = "revision"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NO_RESPONSE = "no_response"


class ConferenceStatus(str, Enum):
    PLANNED = "planned"
    REGISTERED = "registered"
    ATTENDING = "attending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GrantStatus(str, Enum):
    WATCHING = "watching"
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    AWARDED = "awarded"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class EvidenceTargetType(str, Enum):
    PAPER = "Paper"
    PAPER_VERSION = "PaperVersion"
    IDEA = "Idea"
    NOTE = "Note"
    SOURCE_DOCUMENT = "SourceDocument"
    SUBMISSION = "Submission"
    CONFERENCE = "Conference"
    GRANT = "Grant"
    ENTITY_RELATION = "EntityRelation"


class RelationEntityType(str, Enum):
    PAPER = "Paper"
    PAPER_VERSION = "PaperVersion"
    IDEA = "Idea"
    NOTE = "Note"
    SOURCE_DOCUMENT = "SourceDocument"
    SUBMISSION = "Submission"
    CONFERENCE = "Conference"
    GRANT = "Grant"
    EVIDENCE_REF = "EvidenceRef"


class RelationType(str, Enum):
    BELONGS_TO = "belongs_to"
    DERIVED_FROM = "derived_from"
    VERSION_OF = "version_of"
    USED_IN = "used_in"
    DELETED_FROM = "deleted_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    EXTENDS = "extends"
    RELATED_TO = "related_to"
    PRESENTED_AT = "presented_at"
    SUBMITTED_AS = "submitted_as"
    REVIEWED_BY = "reviewed_by"
    SUGGESTED_FOR = "suggested_for"
    SPLIT_FROM = "split_from"
    MERGED_FROM = "merged_from"


class ConfirmationState(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ActorType(str, Enum):
    USER = "user"
    SYSTEM = "system"
    TASK_EXECUTOR = "task_executor"
    AGENT = "agent"


class ProvenanceType(str, Enum):
    MANUAL = "manual"
    RULE = "rule"
    IMPORT = "import"
    AI = "ai"


class AuditTargetType(str, Enum):
    PAPER = "Paper"
    PAPER_VERSION = "PaperVersion"
    IDEA = "Idea"
    NOTE = "Note"
    SOURCE_DOCUMENT = "SourceDocument"
    SUBMISSION = "Submission"
    CONFERENCE = "Conference"
    GRANT = "Grant"
    EVIDENCE_REF = "EvidenceRef"
    ENTITY_RELATION = "EntityRelation"
    RELATION_OBSERVATION = "RelationObservation"
    TASK = "Task"


class EventAggregateType(str, Enum):
    PAPER = "Paper"
    PAPER_VERSION = "PaperVersion"
    IDEA = "Idea"
    SOURCE_DOCUMENT = "SourceDocument"
    SUBMISSION = "Submission"
    CONFERENCE = "Conference"
    GRANT = "Grant"
    TASK = "Task"
    AUDIT_LOG = "AuditLog"


class TaskType(str, Enum):
    IMPORT_DOCUMENT = "import_document"
    COMPARE_VERSIONS = "compare_versions"
    EXTRACT_IDEA_CANDIDATES = "extract_idea_candidates"
    RECOVER_PAPER_CONTEXT = "recover_paper_context"
    REFRESH_SUBMISSION_OVERVIEW = "refresh_submission_overview"
    SCHEDULED_INCREMENTAL_ORGANIZE = "scheduled_incremental_organize"
    EXPORT_DATA = "export_data"


class TaskEffectStatus(str, Enum):
    PREPARED = "prepared"
    COMMITTED = "committed"
    MANUAL_RECONCILIATION = "manual_reconciliation"


class EventType(str, Enum):
    DOCUMENT_IMPORTED = "document.imported"
    PAPER_CREATED = "paper.created"
    PAPER_VERSION_ADDED = "paper.version_added"
    PAPER_VERSION_RELATION_CORRECTED = "paper.version_relation_corrected"
    IDEA_CREATED = "idea.created"
    IDEA_CANDIDATE_EXTRACTED = "idea.candidate_extracted"
    IDEA_LINKED = "idea.linked"
    SUBMISSION_CREATED = "submission.created"
    SUBMISSION_STATUS_CHANGED = "submission.status_changed"
    CONTEXT_RECOVERED = "context.recovered"
    TASK_FAILED = "task.failed"
    AUDIT_UNDO_APPLIED = "audit.undo_applied"
    SOURCE_SNAPSHOT_IMPORTED = "source.snapshot_imported"
    SOURCE_SNAPSHOT_REUSED = "source.snapshot_reused"
    DOCUMENT_PARSE_SUCCEEDED = "document.parse_succeeded"
    DOCUMENT_PARSE_FAILED = "document.parse_failed"


class ImportItemState(str, Enum):
    PENDING = "pending"
    IMPORTED = "imported"
    DUPLICATE_CONTENT = "duplicate_content"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundOperationStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MANUAL_ATTENTION = "manual_attention"
