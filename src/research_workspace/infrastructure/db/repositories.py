"""SQL implementations of foundation reads and Gate 1 coordinated writes."""

from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.ports.repositories import OverviewData
from research_workspace.infrastructure.db.models import (
    ConferenceModel,
    GrantModel,
    PaperModel,
    SubmissionModel,
    ImportItemModel,
    SourceObservationModel,
    SourceSnapshotModel,
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


class SqlGate1WriteRepository:
    """A session-bound adapter used only inside the write coordinator."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO:
        state = "duplicate_content" if result.duplicate_content else "imported"
        if not result.duplicate_content:
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

        observation = self._session.get(SourceObservationModel, result.source_observation_id)
        item = self._session.get(ImportItemModel, result.import_item_id)
        if observation is None or item is None:
            raise ValueError("IMPORT_REGISTRATION_PREREQUISITE_MISSING")
        observation.current_snapshot_id = result.snapshot_id
        observation.availability_status = "available"
        observation.last_seen_at = datetime.now(timezone.utc)
        observation.row_version += 1
        item.snapshot_id = result.snapshot_id
        item.state = state
        item.finished_at = datetime.now(timezone.utc)
        self._session.flush()
        return ImportCommitDTO(
            result.snapshot_id,
            result.source_observation_id,
            result.import_item_id,
            state,
        )
