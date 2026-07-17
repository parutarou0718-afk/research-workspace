"""SQL implementations of foundation reads and Gate 1 coordinated writes."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import rfc8785
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.monitoring_dto import MonitoringRootRecord
from research_workspace.application.dto.parsing_dto import (
    ParseAttemptSeed,
    ParseFailureDTO,
    ParseSuccessDTO,
    PreparedParseAttempt,
)
from research_workspace.application.ports.repositories import OverviewData
from research_workspace.domain.parsing import ParseArtifactIdentity
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    ConferenceModel,
    GrantModel,
    PaperModel,
    PaperVersionModel,
    PaperVersionCandidateModel,
    EntityRelationModel,
    EvidenceRefModel,
    IdeaModel,
    SubmissionModel,
    ImportItemModel,
    MonitoringRootModel,
    ParseArtifactModel,
    ParseAttemptModel,
    ParsedBlockModel,
    SourceObservationModel,
    SourceDocumentModel,
    SourceSnapshotModel,
)
from research_workspace.domain.monitoring import MonitoringRootStatus
from research_workspace.domain.entities import Idea, Paper, Submission
from research_workspace.domain.enums import (
    IdeaOriginType,
    IdeaStatus,
    PaperStatus,
    SubmissionStatus,
)
from research_workspace.application.services.command_dispatcher import DomainMutation
from research_workspace.application.commands.manage_submission import (
    is_submission_transition_allowed,
)
from research_workspace.application.services.relation_graph import (
    VersionEdge,
    create_successor_relation,
)
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    RecoveryPointModel,
    RecoverySlotModel,
    WorkspaceMetadataModel,
)


class SqlOverviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_overview(self) -> OverviewData:
        revision_count = self._submission_count("revision")
        ready_count = self._submission_count("ready")
        upcoming_conference_count = self._session.scalar(
            select(func.count(ConferenceModel.id)).where(
                ConferenceModel.deleted_at.is_(None),
                ConferenceModel.starts_at.is_not(None),
                ConferenceModel.status.in_(("planned", "registered", "attending")),
            )
        ) or 0
        upcoming_grant_count = self._session.scalar(
            select(func.count(GrantModel.id)).where(
                GrantModel.deleted_at.is_(None),
                GrantModel.deadline_at.is_not(None),
                GrantModel.status.in_(("watching", "preparing")),
            )
        ) or 0

        submission_records = self._session.execute(
            select(
                PaperModel.title,
                SubmissionModel.venue,
                SubmissionModel.status,
                SubmissionModel.deadline_at,
            )
            .join(PaperModel, PaperModel.id == SubmissionModel.paper_id)
            .where(
                SubmissionModel.deleted_at.is_(None),
                PaperModel.deleted_at.is_(None),
            )
            .order_by(SubmissionModel.deadline_at.is_(None), SubmissionModel.deadline_at, SubmissionModel.venue)
        ).all()
        submission_rows = tuple(
            " | ".join(
                (
                    title,
                    venue,
                    status,
                    deadline.isoformat().replace("+00:00", "Z") if deadline else "",
                )
            )
            for title, venue, status, deadline in submission_records
        )

        return OverviewData(
            revision_count=revision_count,
            ready_count=ready_count,
            upcoming_conference_count=upcoming_conference_count,
            upcoming_grant_count=upcoming_grant_count,
            suggestions=(),
            submission_rows=submission_rows,
            activities=(),
            focus_items=(),
            focus_progress=0,
        )

    def _submission_count(self, status: str) -> int:
        return self._session.scalar(
            select(func.count(SubmissionModel.id))
            .join(PaperModel, PaperModel.id == SubmissionModel.paper_id)
            .where(
                SubmissionModel.deleted_at.is_(None),
                SubmissionModel.status == status,
                PaperModel.deleted_at.is_(None),
            )
        ) or 0


class SqlMonitoringRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _record(model: MonitoringRootModel) -> MonitoringRootRecord:
        return MonitoringRootRecord(
            model.id,
            Path(model.original_path),
            model.normalized_path,
            model.normalized_path_hash,
            MonitoringRootStatus(model.status),
            model.config_fingerprint,
            model.watcher_generation,
            model.created_at,
            model.updated_at,
            model.removed_at,
        )

    def list_roots(self) -> tuple[MonitoringRootRecord, ...]:
        roots = self._session.scalars(
            select(MonitoringRootModel).order_by(MonitoringRootModel.normalized_path)
        ).all()
        return tuple(self._record(root) for root in roots)

    def get_root(self, monitoring_root_id: UUID) -> MonitoringRootRecord | None:
        root = self._session.get(MonitoringRootModel, monitoring_root_id)
        return None if root is None else self._record(root)

    def find_active_root_by_path(self, normalized_path: str) -> MonitoringRootRecord | None:
        root = self._session.scalar(
            select(MonitoringRootModel).where(
                MonitoringRootModel.normalized_path == normalized_path,
                MonitoringRootModel.removed_at.is_(None),
            )
        )
        return None if root is None else self._record(root)


class SqlRecoveryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def next_generation(self) -> int:
        return int(
            self._session.scalar(select(func.max(RecoveryPointModel.promoted_generation)))
            or 0
        ) + 1

    def activate(self, point: VerifiedRecoveryPoint) -> None:
        command = self._session.get(ApplicationCommandModel, point.command_id)
        if command is None or command.status != "running" or command.recovery_point_id is not None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        workspace_id = self._session.scalar(select(WorkspaceMetadataModel.workspace_id))
        if workspace_id is None:
            raise ValueError("WORKSPACE_METADATA_MISSING")
        slots = {
            slot.slot_name: slot
            for slot in self._session.scalars(
                select(RecoverySlotModel).where(RecoverySlotModel.workspace_id == workspace_id)
            )
        }
        previous = slots.get("previous")
        current = slots.get("current")
        if previous is not None:
            old_point = self._session.get(RecoveryPointModel, previous.recovery_point_id)
            if old_point is not None:
                old_point.physical_state = "superseded"
            self._session.delete(previous)
        if current is not None:
            current_point = self._session.get(RecoveryPointModel, current.recovery_point_id)
            if current_point is not None:
                current_point.physical_state = "active_previous"
            self._session.delete(current)
        self._session.flush()
        manifest = __import__("json").loads(point.manifest_bytes)
        promoted_at = datetime.now(timezone.utc)
        model = RecoveryPointModel(
            id=point.recovery_point_id,
            command_id=point.command_id,
            status="promoted",
            promoted_generation=point.generation,
            physical_state="active_current",
            database_sha256=point.database_sha256,
            schema_revision=manifest["schema_revision"],
            snapshot_count=point.snapshot_count,
            snapshot_manifest_hash=point.snapshot_manifest_hash,
            manifest_json=point.manifest_bytes.decode("utf-8"),
            created_at=promoted_at,
            verified_at=promoted_at,
            promoted_at=promoted_at,
        )
        self._session.add(model)
        # Break the reciprocal command/recovery FK cycle explicitly: the
        # recovery row must exist before the command can point back to it.
        self._session.flush()
        if current is not None:
            self._session.add(
                RecoverySlotModel(
                    workspace_id=workspace_id,
                    slot_name="previous",
                    recovery_point_id=current.recovery_point_id,
                    generation=current.generation,
                    updated_at=promoted_at,
                )
            )
        self._session.add(
            RecoverySlotModel(
                workspace_id=workspace_id,
                slot_name="current",
                recovery_point_id=point.recovery_point_id,
                generation=point.generation,
                updated_at=promoted_at,
            )
        )
        command.recovery_point_id = point.recovery_point_id


class SqlPaperReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _record(row: PaperModel) -> Paper:
        return Paper(
            row.id, row.title, PaperStatus(row.status), row.current_version_id,
            row.created_at, row.updated_at, row.deleted_at, row.row_version,
            row.created_by_command_id, row.updated_by_command_id,
            row.deleted_by_command_id,
        )

    def get_paper(self, paper_id: UUID) -> Paper | None:
        row = self._session.get(PaperModel, paper_id)
        return None if row is None else self._record(row)

    def list_papers(self, *, include_deleted: bool = False) -> tuple[Paper, ...]:
        statement = select(PaperModel)
        if not include_deleted:
            statement = statement.where(PaperModel.deleted_at.is_(None))
        rows = self._session.scalars(statement.order_by(PaperModel.title, PaperModel.id)).all()
        return tuple(self._record(row) for row in rows)


class SqlIdeaReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _record(row: IdeaModel) -> Idea:
        return Idea(
            row.id, row.title, row.content, IdeaStatus(row.status),
            IdeaOriginType(row.origin_type), row.created_at, row.updated_at,
            row.deleted_at, row.row_version, row.created_by_command_id,
            row.updated_by_command_id, row.deleted_by_command_id,
        )

    def get_idea(self, idea_id: UUID) -> Idea | None:
        row = self._session.get(IdeaModel, idea_id)
        return None if row is None else self._record(row)

    def list_ideas(self, *, include_deleted: bool = False) -> tuple[Idea, ...]:
        statement = select(IdeaModel)
        if not include_deleted:
            statement = statement.where(IdeaModel.deleted_at.is_(None))
        rows = self._session.scalars(statement.order_by(IdeaModel.title, IdeaModel.id)).all()
        return tuple(self._record(row) for row in rows)


class SqlSubmissionReadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _record(row: SubmissionModel) -> Submission:
        return Submission(
            row.id,
            row.paper_id,
            row.venue,
            SubmissionStatus(row.status),
            row.submitted_at,
            row.deadline_at,
            row.active_version_id,
            row.created_at,
            row.updated_at,
            row.deleted_at,
            row.row_version,
            row.created_by_command_id,
            row.updated_by_command_id,
            row.deleted_by_command_id,
        )

    def get_submission(self, submission_id: UUID) -> Submission | None:
        row = self._session.get(SubmissionModel, submission_id)
        return None if row is None else self._record(row)

    def list_submissions(
        self, *, include_deleted: bool = False
    ) -> tuple[Submission, ...]:
        statement = select(SubmissionModel)
        if not include_deleted:
            statement = statement.where(SubmissionModel.deleted_at.is_(None))
        rows = self._session.scalars(
            statement.order_by(SubmissionModel.venue, SubmissionModel.id)
        ).all()
        return tuple(self._record(row) for row in rows)


class SqlGate1WriteRepository:
    """A session-bound adapter used only inside the write coordinator."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def apply_mutation(self, mutation: DomainMutation, command_id: UUID) -> None:
        if mutation.entity_type == "PaperVersionCandidate":
            self._apply_candidate_decision(mutation, command_id)
            return
        if mutation.entity_type == "PaperVersion":
            self._apply_paper_version(mutation, command_id)
            return
        if mutation.entity_type == "EntityRelation":
            self._apply_version_relation(mutation, command_id)
            return
        if mutation.entity_type == "Submission":
            self._apply_submission(mutation, command_id)
            return
        if mutation.entity_type == "Idea":
            self._apply_idea(mutation, command_id)
            return
        if mutation.entity_type != "Paper":
            raise ValueError("COMMAND_VALIDATION_FAILED")
        after = __import__("json").loads(mutation.after_snapshot) if mutation.after_snapshot else None
        if after is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        fields = after["fields"]
        now = datetime.now(timezone.utc)
        if mutation.operation == "create":
            self._session.add(
                PaperModel(
                    id=mutation.entity_id,
                    title=fields["title"],
                    status=fields["status"],
                    current_version_id=None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                    row_version=1,
                    created_by_command_id=command_id,
                    updated_by_command_id=command_id,
                    deleted_by_command_id=None,
                )
            )
            self._session.flush()
            return
        paper = self._session.get(PaperModel, mutation.entity_id)
        if paper is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if mutation.operation == "soft_delete":
            active_submissions = self._session.scalar(
                select(func.count(SubmissionModel.id)).where(
                    SubmissionModel.paper_id == paper.id,
                    SubmissionModel.deleted_at.is_(None),
                )
            )
            active_relations = self._session.scalar(
                select(func.count(EntityRelationModel.id)).where(
                    EntityRelationModel.lifecycle_state == "active",
                    or_(
                        (EntityRelationModel.source_type == "Paper")
                        & (EntityRelationModel.source_id == paper.id),
                        (EntityRelationModel.target_type == "Paper")
                        & (EntityRelationModel.target_id == paper.id),
                    ),
                )
            )
            evidence = self._session.scalar(
                select(func.count(EvidenceRefModel.id)).where(
                    EvidenceRefModel.entity_type == "Paper",
                    EvidenceRefModel.entity_id == paper.id,
                )
            )
            if active_submissions or active_relations or evidence or paper.current_version_id:
                raise ValueError("DELETE_DEPENDENCY_CONFLICT")
        current_version_id = fields["current_version_id"]
        if current_version_id is not None:
            version = self._session.get(PaperVersionModel, UUID(current_version_id))
            if (
                version is None
                or version.paper_id != paper.id
                or version.lifecycle_state != "active"
            ):
                raise ValueError("INVALID_VERSION_ASSIGNMENT")
        values = {
            "title": fields["title"],
            "status": fields["status"],
            "current_version_id": UUID(current_version_id) if current_version_id else None,
            "deleted_at": datetime.fromisoformat(fields["deleted_at"].replace("Z", "+00:00"))
            if fields["deleted_at"]
            else None,
            "deleted_by_command_id": command_id if fields["deleted_at"] else None,
            "updated_by_command_id": command_id,
            "updated_at": now,
            "row_version": mutation.expected_row_version + 1,
        }
        result = self._session.execute(
            update(PaperModel)
            .where(
                PaperModel.id == mutation.entity_id,
                PaperModel.row_version == mutation.expected_row_version,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise ValueError("CONCURRENT_MODIFICATION")

    def _apply_paper_version(
        self, mutation: DomainMutation, command_id: UUID
    ) -> None:
        after = self._mutation_fields(mutation)
        paper_id = UUID(after["paper_id"])
        snapshot_id = UUID(after["source_snapshot_id"])
        context_id = (
            UUID(after["context_parse_artifact_id"])
            if after["context_parse_artifact_id"] else None
        )
        paper = self._session.get(PaperModel, paper_id)
        snapshot = self._session.get(SourceSnapshotModel, snapshot_id)
        if paper is None or paper.deleted_at is not None or snapshot is None:
            raise ValueError("INVALID_VERSION_ASSIGNMENT")
        if context_id is not None:
            artifact = self._session.get(ParseArtifactModel, context_id)
            if (
                artifact is None or artifact.source_snapshot_id != snapshot_id
                or artifact.status != "succeeded"
            ):
                raise ValueError("INVALID_VERSION_ASSIGNMENT")
        now = datetime.now(timezone.utc)
        retracted_at = self._parsed_time(after["retracted_at"])
        if mutation.operation == "confirm":
            self._session.add(PaperVersionModel(
                id=mutation.entity_id, paper_id=paper_id,
                source_snapshot_id=snapshot_id,
                context_parse_artifact_id=context_id,
                version_label=after["version_label"],
                normalized_version_label=after["normalized_version_label"],
                lifecycle_state="active", row_version=1, created_at=now,
                confirmed_by_command_id=command_id, updated_at=now,
                updated_by_command_id=command_id, retracted_at=None,
                retracted_by_command_id=None,
            ))
            self._session.flush()
            return
        version = self._session.get(PaperVersionModel, mutation.entity_id)
        if version is None:
            raise ValueError("INVALID_VERSION_ASSIGNMENT")
        if mutation.operation == "retract":
            active_edges = self._active_version_edge_count(version.id)
            active_submissions = self._session.scalar(
                select(func.count(SubmissionModel.id)).where(
                    SubmissionModel.deleted_at.is_(None),
                    SubmissionModel.active_version_id == version.id,
                )
            )
            if (
                paper.current_version_id == version.id
                or active_edges or active_submissions
            ):
                raise ValueError("VERSION_RETRACTION_DEPENDENCY_CONFLICT")
        result = self._session.execute(
            update(PaperVersionModel).where(
                PaperVersionModel.id == version.id,
                PaperVersionModel.row_version == mutation.expected_row_version,
            ).values(
                context_parse_artifact_id=context_id,
                lifecycle_state=after["lifecycle_state"],
                row_version=mutation.expected_row_version + 1,
                updated_at=now, updated_by_command_id=command_id,
                retracted_at=retracted_at,
                retracted_by_command_id=command_id if retracted_at else None,
            )
        )
        if result.rowcount != 1:
            raise ValueError("CONCURRENT_MODIFICATION")

    def _apply_version_relation(
        self, mutation: DomainMutation, command_id: UUID
    ) -> None:
        fields = self._mutation_fields(mutation)
        if (
            fields["relation_type"] != "version_successor_of"
            or fields["source_type"] != "PaperVersion"
            or fields["target_type"] != "PaperVersion"
        ):
            raise ValueError("INVALID_VERSION_RELATION_ENDPOINT")
        if mutation.operation == "retract":
            relation = self._session.get(EntityRelationModel, mutation.entity_id)
            if (
                relation is None or relation.lifecycle_state != "active"
                or relation.row_version != mutation.expected_row_version
            ):
                raise ValueError("RELATION_STATE_CHANGED")
            replacement_id = fields.get("superseded_by_relation_id")
            if replacement_id:
                replacement = self._session.get(
                    EntityRelationModel, UUID(replacement_id)
                )
                if replacement is None or replacement.lifecycle_state != "active":
                    raise ValueError("RELATION_STATE_CHANGED")
            relation.lifecycle_state = fields["lifecycle_state"]
            relation.superseded_by_relation_id = (
                UUID(replacement_id) if replacement_id else None
            )
            relation.row_version += 1
            relation.updated_at = datetime.now(timezone.utc)
            relation.retracted_at = datetime.now(timezone.utc)
            relation.retracted_by_command_id = command_id
            self._session.flush()
            return
        later = self._session.get(PaperVersionModel, UUID(fields["source_id"]))
        earlier = self._session.get(PaperVersionModel, UUID(fields["target_id"]))
        if later is None or earlier is None:
            raise ValueError("INVALID_VERSION_RELATION_ENDPOINT")
        rows = self._session.scalars(
            select(EntityRelationModel).where(
                EntityRelationModel.relation_type == "version_successor_of",
                EntityRelationModel.lifecycle_state == "active",
                EntityRelationModel.source_type == "PaperVersion",
                EntityRelationModel.source_id.in_(
                    select(PaperVersionModel.id).where(
                        PaperVersionModel.paper_id == later.paper_id
                    )
                ),
            )
        ).all()
        edges = tuple(
            VersionEdge(row.id, later.paper_id, row.source_id, row.target_id)
            for row in rows
        )
        create_successor_relation(
            command_id,
            self._version_record(later),
            self._version_record(earlier),
            edges,
            mutation.entity_id,
            datetime.now(timezone.utc),
        )
        now = datetime.now(timezone.utc)
        self._session.add(EntityRelationModel(
            id=mutation.entity_id, source_type="PaperVersion",
            source_id=later.id, relation_type="version_successor_of",
            target_type="PaperVersion", target_id=earlier.id, confidence=None,
            confirmation_state="confirmed", lifecycle_state="active",
            superseded_by_relation_id=None, created_by_actor_type="user",
            created_by_actor_id=None, created_by_command_id=command_id,
            row_version=1, created_at=now, updated_at=now,
            retracted_at=None, retracted_by_command_id=None,
        ))
        self._session.flush()

    def _apply_candidate_decision(
        self, mutation: DomainMutation, command_id: UUID
    ) -> None:
        fields = self._mutation_fields(mutation)
        candidate = self._session.get(
            PaperVersionCandidateModel, mutation.entity_id
        )
        if (
            candidate is None
            or candidate.row_version != mutation.expected_row_version
        ):
            raise ValueError("CANDIDATE_STATE_CHANGED")
        target = fields["status"]
        allowed = {
            ("pending", "confirmed"),
            ("pending", "rejected"),
            ("rejected", "pending"),
        }
        if (candidate.status, target) not in allowed:
            raise ValueError("CANDIDATE_STATE_CHANGED")
        candidate.status = target
        candidate.row_version += 1
        candidate.decided_at = (
            datetime.now(timezone.utc)
            if target in {"confirmed", "rejected"} else None
        )
        candidate.decided_by_command_id = (
            command_id if target in {"confirmed", "rejected"} else None
        )
        self._session.flush()

    @staticmethod
    def _mutation_fields(mutation: DomainMutation) -> dict[str, object]:
        if mutation.after_snapshot is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        return __import__("json").loads(mutation.after_snapshot)["fields"]

    def _active_version_edge_count(self, version_id: UUID) -> int:
        return int(self._session.scalar(
            select(func.count(EntityRelationModel.id)).where(
                EntityRelationModel.relation_type == "version_successor_of",
                EntityRelationModel.lifecycle_state == "active",
                or_(
                    EntityRelationModel.source_id == version_id,
                    EntityRelationModel.target_id == version_id,
                ),
            )
        ) or 0)

    @staticmethod
    def _version_record(row: PaperVersionModel):
        from research_workspace.domain.versioning import PaperVersionRecord
        return PaperVersionRecord(
            row.id, row.paper_id, row.source_snapshot_id,
            row.context_parse_artifact_id, row.version_label,
            row.normalized_version_label, row.lifecycle_state, row.row_version,
            row.created_at, row.confirmed_by_command_id, row.updated_at,
            row.updated_by_command_id, row.retracted_at,
            row.retracted_by_command_id,
        )

    def _apply_submission(
        self, mutation: DomainMutation, command_id: UUID
    ) -> None:
        after = (
            __import__("json").loads(mutation.after_snapshot)
            if mutation.after_snapshot
            else None
        )
        if after is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        fields = after["fields"]
        paper_id = UUID(fields["paper_id"])
        paper = self._session.get(PaperModel, paper_id)
        if paper is None or paper.deleted_at is not None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        version_id = (
            UUID(fields["active_version_id"])
            if fields["active_version_id"]
            else None
        )
        if version_id is not None:
            version = self._session.get(PaperVersionModel, version_id)
            if (
                version is None
                or version.paper_id != paper_id
                or version.lifecycle_state != "active"
            ):
                raise ValueError("INVALID_VERSION_ASSIGNMENT")
        now = datetime.now(timezone.utc)
        submitted_at = self._parsed_time(fields["submitted_at"])
        deadline_at = self._parsed_time(fields["deadline_at"])
        deleted_at = self._parsed_time(fields["deleted_at"])
        target_status = SubmissionStatus(fields["status"])
        pre_submission = {
            SubmissionStatus.PREPARING,
            SubmissionStatus.READY,
        }
        if (
            (target_status in pre_submission and submitted_at is not None)
            or (
                target_status not in pre_submission
                and (submitted_at is None or version_id is None)
            )
        ):
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if mutation.operation == "create":
            self._session.add(
                SubmissionModel(
                    id=mutation.entity_id,
                    paper_id=paper_id,
                    venue=fields["venue"],
                    status=fields["status"],
                    submitted_at=submitted_at,
                    deadline_at=deadline_at,
                    active_version_id=version_id,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                    row_version=1,
                    created_by_command_id=command_id,
                    updated_by_command_id=command_id,
                    deleted_by_command_id=None,
                )
            )
            self._session.flush()
            return
        submission = self._session.get(SubmissionModel, mutation.entity_id)
        if submission is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if mutation.operation != "reassign_paper" and paper_id != submission.paper_id:
            raise ValueError("SUBMISSION_REASSIGNMENT_CONFLICT")
        if submission.submitted_at is not None and submitted_at != submission.submitted_at:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if mutation.operation == "transition" and not is_submission_transition_allowed(
            SubmissionStatus(submission.status), target_status
        ):
            raise ValueError("INVALID_SUBMISSION_TRANSITION")
        if mutation.operation == "reassign_paper":
            relations = self._active_relation_count("Submission", submission.id)
            evidence = self._session.scalar(
                select(func.count(EvidenceRefModel.id)).where(
                    EvidenceRefModel.entity_type == "Submission",
                    EvidenceRefModel.entity_id == submission.id,
                )
            )
            if (
                submission.status not in {"preparing", "ready"}
                or submission.active_version_id is not None
                or relations
                or evidence
            ):
                raise ValueError("SUBMISSION_REASSIGNMENT_CONFLICT")
        result = self._session.execute(
            update(SubmissionModel)
            .where(
                SubmissionModel.id == mutation.entity_id,
                SubmissionModel.row_version == mutation.expected_row_version,
            )
            .values(
                paper_id=paper_id,
                venue=fields["venue"],
                status=fields["status"],
                submitted_at=submitted_at,
                deadline_at=deadline_at,
                active_version_id=version_id,
                deleted_at=deleted_at,
                deleted_by_command_id=command_id if deleted_at else None,
                updated_by_command_id=command_id,
                updated_at=now,
                row_version=mutation.expected_row_version + 1,
            )
        )
        if result.rowcount != 1:
            raise ValueError("CONCURRENT_MODIFICATION")

    @staticmethod
    def _parsed_time(value: str | None) -> datetime | None:
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            if value
            else None
        )

    def _active_relation_count(self, entity_type: str, entity_id: UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count(EntityRelationModel.id)).where(
                    EntityRelationModel.lifecycle_state == "active",
                    or_(
                        (EntityRelationModel.source_type == entity_type)
                        & (EntityRelationModel.source_id == entity_id),
                        (EntityRelationModel.target_type == entity_type)
                        & (EntityRelationModel.target_id == entity_id),
                    ),
                )
            )
            or 0
        )

    def _apply_idea(self, mutation: DomainMutation, command_id: UUID) -> None:
        after = __import__("json").loads(mutation.after_snapshot) if mutation.after_snapshot else None
        if after is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        fields = after["fields"]
        if fields["origin_type"] != "manual":
            raise ValueError("COMMAND_VALIDATION_FAILED")
        now = datetime.now(timezone.utc)
        if mutation.operation == "create":
            self._session.add(
                IdeaModel(
                    id=mutation.entity_id, title=fields["title"], content=fields["content"],
                    status=fields["status"], origin_type="manual", created_at=now,
                    updated_at=now, deleted_at=None, row_version=1,
                    created_by_command_id=command_id, updated_by_command_id=command_id,
                    deleted_by_command_id=None,
                )
            )
            self._session.flush()
            return
        idea = self._session.get(IdeaModel, mutation.entity_id)
        if idea is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if mutation.operation == "soft_delete":
            relations = self._session.scalar(
                select(func.count(EntityRelationModel.id)).where(
                    EntityRelationModel.lifecycle_state == "active",
                    or_(
                        (EntityRelationModel.source_type == "Idea")
                        & (EntityRelationModel.source_id == idea.id),
                        (EntityRelationModel.target_type == "Idea")
                        & (EntityRelationModel.target_id == idea.id),
                    ),
                )
            )
            evidence = self._session.scalar(
                select(func.count(EvidenceRefModel.id)).where(
                    EvidenceRefModel.entity_type == "Idea",
                    EvidenceRefModel.entity_id == idea.id,
                )
            )
            if relations or evidence:
                raise ValueError("DELETE_DEPENDENCY_CONFLICT")
        deleted_at = (
            datetime.fromisoformat(fields["deleted_at"].replace("Z", "+00:00"))
            if fields["deleted_at"] else None
        )
        result = self._session.execute(
            update(IdeaModel)
            .where(
                IdeaModel.id == mutation.entity_id,
                IdeaModel.row_version == mutation.expected_row_version,
            )
            .values(
                title=fields["title"], content=fields["content"], status=fields["status"],
                origin_type="manual", deleted_at=deleted_at,
                deleted_by_command_id=command_id if deleted_at else None,
                updated_by_command_id=command_id, updated_at=now,
                row_version=mutation.expected_row_version + 1,
            )
        )
        if result.rowcount != 1:
            raise ValueError("CONCURRENT_MODIFICATION")

    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO:
        existing = self._session.scalar(
            select(SourceSnapshotModel).where(SourceSnapshotModel.sha256 == result.sha256)
        )
        if existing is None:
            snapshot_id = result.snapshot_id
            state = "imported"
            self._session.add(
                SourceSnapshotModel(
                    id=result.snapshot_id,
                    sha256=result.sha256,
                    size_bytes=result.size_bytes,
                    mime_type=result.mime_type,
                    storage_relative_path=result.storage_relative_path,
                    created_at=datetime.now(timezone.utc),
                    created_by_operation_id=result.operation_id,
                )
            )
        else:
            if (
                existing.size_bytes != result.size_bytes
                or existing.storage_relative_path != result.storage_relative_path
            ):
                raise ValueError("SNAPSHOT_HASH_MISMATCH")
            snapshot_id = existing.id
            state = "duplicate_content"

        observation = self._session.get(SourceObservationModel, result.source_observation_id)
        item = self._session.get(ImportItemModel, result.import_item_id)
        if observation is None or item is None:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        observation.current_snapshot_id = snapshot_id
        observation.availability_status = "available"
        observation.last_seen_at = datetime.now(timezone.utc)
        observation.row_version += 1
        item.snapshot_id = snapshot_id
        item.state = state
        item.finished_at = datetime.now(timezone.utc)
        self._session.flush()
        return ImportCommitDTO(
            snapshot_id,
            result.source_observation_id,
            result.import_item_id,
            state,
        )

    def start_parse_attempt(
        self, seed: ParseAttemptSeed, identity: ParseArtifactIdentity
    ) -> PreparedParseAttempt:
        operation = self._session.get(BackgroundOperationModel, seed.operation_id)
        snapshot = self._session.get(SourceSnapshotModel, seed.source_snapshot_id)
        if operation is None or snapshot is None or operation.status != "running":
            raise ValueError("COMMAND_VALIDATION_FAILED")
        artifact = self._session.scalar(
            select(ParseArtifactModel).where(
                ParseArtifactModel.source_snapshot_id == identity.source_snapshot_id,
                ParseArtifactModel.parser_id == identity.parser_id,
                ParseArtifactModel.parser_version == identity.parser_version,
                ParseArtifactModel.config_fingerprint == identity.config_fingerprint,
                ParseArtifactModel.contract_version == identity.contract_version,
            )
        )
        now = datetime.now(timezone.utc)
        if artifact is None:
            artifact = ParseArtifactModel(
                id=seed.parse_artifact_id,
                source_snapshot_id=identity.source_snapshot_id,
                parser_id=identity.parser_id,
                parser_version=identity.parser_version,
                config_fingerprint=identity.config_fingerprint,
                contract_version=identity.contract_version,
                status="running",
                successful_attempt_id=None,
                output_sha256=None,
                derived_file_sha256=None,
                derived_relative_path=None,
                created_at=now,
                updated_at=now,
            )
            self._session.add(artifact)
            self._session.flush()
        elif artifact.status == "succeeded" or artifact.successful_attempt_id is not None:
            raise ValueError("PARSE_ALREADY_SUCCEEDED")
        else:
            artifact.status = "running"
            artifact.updated_at = now

        latest = self._session.scalar(
            select(func.max(ParseAttemptModel.attempt_number)).where(
                ParseAttemptModel.parse_artifact_id == artifact.id
            )
        )
        attempt_number = int(latest or 0) + 1
        self._session.add(
            ParseAttemptModel(
                id=seed.parse_attempt_id,
                parse_artifact_id=artifact.id,
                attempt_number=attempt_number,
                status="running",
                executor_version=seed.executor_version,
                started_at=now,
                finished_at=None,
                error_code=None,
                warnings_json="[]",
                output_sha256=None,
                derived_file_sha256=None,
                diagnostic_summary_json=None,
            )
        )
        self._session.flush()
        return PreparedParseAttempt(
            seed.operation_id,
            artifact.id,
            seed.parse_attempt_id,
            artifact.source_snapshot_id,
            artifact.config_fingerprint,
            attempt_number,
        )

    def register_parse_failure(
        self, result: ParseFailureDTO
    ) -> tuple[ParseArtifactModel, ParseAttemptModel]:
        artifact, attempt = self._open_attempt(result.parse_artifact_id, result.parse_attempt_id)
        now = datetime.now(timezone.utc)
        attempt.status = "failed"
        attempt.error_code = result.error_code
        attempt.warnings_json = rfc8785.dumps(sorted(set(result.warning_codes))).decode("utf-8")
        attempt.finished_at = now
        artifact.status = "failed"
        artifact.updated_at = now
        self._session.flush()
        return artifact, attempt

    def register_parse_success(
        self, result: ParseSuccessDTO, parsed_document: dict[str, object]
    ) -> tuple[ParseArtifactModel, ParseAttemptModel, SourceDocumentModel]:
        artifact, attempt = self._open_attempt(result.parse_artifact_id, result.parse_attempt_id)
        if artifact.successful_attempt_id is not None:
            raise ValueError("PARSE_ALREADY_SUCCEEDED")
        now = datetime.now(timezone.utc)
        warnings = parsed_document["warnings"]
        blocks = parsed_document["blocks"]
        metadata = parsed_document["metadata"]
        document = SourceDocumentModel(
            id=uuid4(),
            parse_artifact_id=artifact.id,
            title=parsed_document["title"],
            metadata_json=rfc8785.dumps(metadata).decode("utf-8"),
            language=metadata["language"],
            block_count=len(blocks),
            warnings_json=rfc8785.dumps(warnings).decode("utf-8"),
            created_at=now,
        )
        self._session.add(document)
        self._session.flush()
        for block in blocks:
            self._session.add(
                ParsedBlockModel(
                    id=block["block_id"],
                    parse_artifact_id=artifact.id,
                    source_document_id=document.id,
                    block_index=block["block_index"],
                    kind=block["kind"],
                    text=block["text"],
                    locator_json=rfc8785.dumps(block["locator"]).decode("utf-8"),
                    metadata_json=rfc8785.dumps(block["metadata"]).decode("utf-8"),
                    text_sha256=hashlib.sha256(block["text"].encode("utf-8")).hexdigest(),
                )
            )
        attempt.status = "succeeded"
        attempt.finished_at = now
        attempt.error_code = None
        attempt.warnings_json = rfc8785.dumps(
            sorted({warning["code"] for warning in warnings})
        ).decode("utf-8")
        attempt.output_sha256 = result.output_sha256
        attempt.derived_file_sha256 = result.derived_file_sha256
        artifact.status = "succeeded"
        artifact.successful_attempt_id = attempt.id
        artifact.output_sha256 = result.output_sha256
        artifact.derived_file_sha256 = result.derived_file_sha256
        artifact.derived_relative_path = result.derived_relative_path
        artifact.updated_at = now
        self._session.flush()
        return artifact, attempt, document

    def _open_attempt(
        self, artifact_id, attempt_id
    ) -> tuple[ParseArtifactModel, ParseAttemptModel]:
        artifact = self._session.get(ParseArtifactModel, artifact_id)
        attempt = self._session.get(ParseAttemptModel, attempt_id)
        if (
            artifact is None
            or attempt is None
            or attempt.parse_artifact_id != artifact.id
            or attempt.status != "running"
            or artifact.status != "running"
        ):
            raise ValueError("COMMAND_VALIDATION_FAILED")
        return artifact, attempt
