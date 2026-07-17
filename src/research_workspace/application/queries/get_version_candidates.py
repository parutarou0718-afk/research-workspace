"""Read-only immutable PaperVersionCandidate projection."""

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Protocol
from uuid import UUID

from sqlalchemy import select

from research_workspace.infrastructure.db.models import PaperVersionCandidateModel
from research_workspace.application.commands.undo_command import (
    UndoError,
    UndoPreflight,
    plan_compensating_undo,
)


@dataclass(frozen=True, slots=True)
class VersionCandidateRecord:
    candidate_id: UUID
    earlier_snapshot_id: UUID
    later_snapshot_id: UUID
    detector_id: str
    detector_version: str
    rule_id: str
    rule_config_fingerprint: str
    direction_rationale_json: bytes
    signals_json: bytes
    input_observation_ids_json: bytes
    status: str
    superseded_by_candidate_id: UUID | None
    row_version: int


@dataclass(frozen=True, slots=True)
class DecisionReviewBundle:
    candidate_id: UUID
    candidate_row_version: int
    detector_id: str
    detector_version: str
    rule_id: str
    rule_config_fingerprint: str
    earlier_snapshot_id: UUID
    later_snapshot_id: UUID
    direction_rationale: bytes
    signals: bytes
    input_observation_ids: tuple[UUID, ...]
    existing_memberships: tuple[UUID, ...]
    existing_relation_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class UndoHistoryRecord:
    command_id: UUID
    command_type: str
    actor_type: str
    committed_at: datetime
    preflight: UndoPreflight


@dataclass(frozen=True, slots=True)
class SafeUndoItem:
    command_id: UUID
    command_type: str
    committed_at: datetime
    affected_entity_ids: tuple[UUID, ...]
    action: str = "undo"


class UndoHistoryRepository(Protocol):
    def list_undo_history(self) -> tuple[UndoHistoryRecord, ...]: ...


class GetSafeUndoQuery:
    def __init__(self, repository: UndoHistoryRepository) -> None:
        self._repository = repository

    def execute(self, *, as_of: datetime) -> tuple[SafeUndoItem, ...]:
        result: list[SafeUndoItem] = []
        for record in self._repository.list_undo_history():
            if record.actor_type != "user":
                continue
            try:
                plan_compensating_undo(
                    record.command_id, UUID(int=0), as_of, record.preflight
                )
            except UndoError:
                continue
            result.append(
                SafeUndoItem(
                    record.command_id,
                    record.command_type,
                    record.committed_at,
                    tuple(change.entity_id for change in record.preflight.changes),
                )
            )
        return tuple(
            sorted(
                result,
                key=lambda item: (item.committed_at, item.command_id),
                reverse=True,
            )
        )


def build_decision_review_bundle(
    candidate: VersionCandidateRecord,
    existing_memberships: tuple[UUID, ...],
    existing_relation_ids: tuple[UUID, ...],
) -> DecisionReviewBundle:
    observations = tuple(
        UUID(value) for value in json.loads(candidate.input_observation_ids_json)
    )
    return DecisionReviewBundle(
        candidate.candidate_id, candidate.row_version, candidate.detector_id,
        candidate.detector_version, candidate.rule_id,
        candidate.rule_config_fingerprint, candidate.earlier_snapshot_id,
        candidate.later_snapshot_id, bytes(candidate.direction_rationale_json),
        bytes(candidate.signals_json), observations,
        tuple(existing_memberships), tuple(existing_relation_ids),
    )


class GetVersionCandidates:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def execute(self) -> tuple[VersionCandidateRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(PaperVersionCandidateModel).order_by(
                    PaperVersionCandidateModel.created_at,
                    PaperVersionCandidateModel.detector_version,
                    PaperVersionCandidateModel.id,
                )
            ).all()
            return tuple(
                VersionCandidateRecord(
                    model.id,
                    model.earlier_snapshot_id,
                    model.later_snapshot_id,
                    model.detector_id,
                    model.detector_version,
                    model.rule_id,
                    model.rule_config_fingerprint,
                    model.direction_rationale_json.encode("utf-8"),
                    model.signals_json.encode("utf-8"),
                    model.input_observation_ids_json.encode("utf-8"),
                    model.status,
                    model.superseded_by_candidate_id,
                    model.row_version,
                )
                for model in models
            )
