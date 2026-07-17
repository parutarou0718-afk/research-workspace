"""SQL implementations of foundation reads and Gate 1 coordinated writes."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import rfc8785
from sqlalchemy import func, select
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


class SqlGate1WriteRepository:
    """A session-bound adapter used only inside the write coordinator."""

    def __init__(self, session: Session) -> None:
        self._session = session

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
