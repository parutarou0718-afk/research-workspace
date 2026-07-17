"""Candidate decisions and immutable formal-relation lifecycle plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import rfc8785

from research_workspace.application.queries.get_version_candidates import (
    VersionCandidateRecord,
)
from research_workspace.application.services.command_dispatcher import DomainMutation
from research_workspace.application.services.relation_graph import (
    VersionEdge,
    create_successor_relation,
    create_version_membership,
    resolve_membership,
)
from research_workspace.domain.versioning import (
    PaperVersionRecord,
    clean_version_label,
    normalize_version_label,
)


class CandidateDecisionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RelationLifecycleRecord:
    id: UUID
    relation_type: str
    source_type: str
    source_id: UUID
    target_type: str
    target_id: UUID
    lifecycle_state: str
    row_version: int


def _candidate_snapshot(
    candidate: VersionCandidateRecord, status: str, row_version: int
) -> bytes:
    return rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "PaperVersionCandidate",
        "entity_id": str(candidate.candidate_id), "row_version": row_version,
        "fields": {
            "status": status,
            "superseded_by_candidate_id": (
                str(candidate.superseded_by_candidate_id)
                if candidate.superseded_by_candidate_id else None
            ),
        },
    })


def _candidate_decision(
    candidate: VersionCandidateRecord, status: str, operation: str
) -> DomainMutation:
    version = candidate.row_version + 1
    event = rfc8785.dumps({
        "candidate_id": str(candidate.candidate_id),
        "old_status": candidate.status, "new_status": status,
        "row_version": version, "replacement_candidate_id": None,
    })
    suffix = {
        "confirm": "confirmed",
        "reject": "rejected",
        "reconsider": "reconsidered",
    }[operation]
    return DomainMutation(
        "PaperVersionCandidate", candidate.candidate_id, operation,
        candidate.row_version,
        _candidate_snapshot(candidate, candidate.status, candidate.row_version),
        _candidate_snapshot(candidate, status, version), ("status",),
        f"paper_version_candidate.{suffix}",
        event,
    )


def reject_candidate(
    candidate: VersionCandidateRecord, command_id: UUID, now: datetime
) -> DomainMutation:
    del command_id, now
    if candidate.status != "pending":
        raise CandidateDecisionError("CANDIDATE_STATE_CHANGED")
    return _candidate_decision(candidate, "rejected", "reject")


def reconsider_candidate(
    candidate: VersionCandidateRecord, command_id: UUID, now: datetime
) -> DomainMutation:
    del command_id, now
    if candidate.status != "rejected":
        raise CandidateDecisionError("CANDIDATE_STATE_CHANGED")
    return _candidate_decision(candidate, "pending", "reconsider")


def confirm_candidate(
    candidate: VersionCandidateRecord, command_id: UUID, paper_id: UUID,
    earlier_label: str, later_label: str,
    existing_versions: tuple[PaperVersionRecord, ...],
    active_edges: tuple[VersionEdge, ...], earlier_version_id: UUID,
    later_version_id: UUID, relation_id: UUID, now: datetime,
) -> tuple[DomainMutation, ...]:
    if candidate.status != "pending":
        raise CandidateDecisionError("CANDIDATE_STATE_CHANGED")
    mutations: list[DomainMutation] = []
    earlier, _ = resolve_membership(
        existing_versions, paper_id, candidate.earlier_snapshot_id
    )
    later, _ = resolve_membership(
        existing_versions, paper_id, candidate.later_snapshot_id
    )
    if earlier is None:
        mutations.append(create_version_membership(
            command_id, earlier_version_id, paper_id,
            candidate.earlier_snapshot_id, earlier_label, None, now,
        ))
        earlier = _new_record(
            earlier_version_id, paper_id, candidate.earlier_snapshot_id,
            earlier_label, command_id, now,
        )
    if later is None:
        mutations.append(create_version_membership(
            command_id, later_version_id, paper_id,
            candidate.later_snapshot_id, later_label, None, now,
        ))
        later = _new_record(
            later_version_id, paper_id, candidate.later_snapshot_id,
            later_label, command_id, now,
        )
    mutations.append(create_successor_relation(
        command_id, later, earlier, active_edges, relation_id, now
    ))
    mutations.append(_candidate_decision(candidate, "confirmed", "confirm"))
    return tuple(mutations)


def _new_record(
    version_id: UUID, paper_id: UUID, snapshot_id: UUID, label: str,
    command_id: UUID, now: datetime,
) -> PaperVersionRecord:
    display = clean_version_label(label)
    return PaperVersionRecord(
        version_id, paper_id, snapshot_id, None, display,
        normalize_version_label(display), "active", 1, now, command_id,
        now, command_id, None, None,
    )


def _relation_snapshot(
    relation: RelationLifecycleRecord, lifecycle: str, version: int,
    superseded_by: UUID | None = None,
) -> bytes:
    return rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "EntityRelation",
        "entity_id": str(relation.id), "row_version": version,
        "fields": {
            "relation_type": relation.relation_type,
            "source_type": relation.source_type,
            "source_id": str(relation.source_id),
            "target_type": relation.target_type,
            "target_id": str(relation.target_id),
            "confirmation_state": "confirmed", "lifecycle_state": lifecycle,
            "superseded_by_relation_id": (
                str(superseded_by) if superseded_by else None
            ),
        },
    })


def retract_relation(
    relation: RelationLifecycleRecord, command_id: UUID, now: datetime
) -> DomainMutation:
    del command_id, now
    if relation.lifecycle_state != "active":
        raise CandidateDecisionError("RELATION_STATE_CHANGED")
    return _relation_change(relation, "retracted", None, "relation.retracted")


def supersede_relation(
    relation: RelationLifecycleRecord, replacement: RelationLifecycleRecord,
    command_id: UUID, now: datetime,
) -> DomainMutation:
    del command_id, now
    if (
        relation.id == replacement.id or relation.lifecycle_state != "active"
        or replacement.lifecycle_state != "active"
        or relation.relation_type != replacement.relation_type
        or relation.source_type != replacement.source_type
        or relation.target_type != replacement.target_type
    ):
        raise CandidateDecisionError("RELATION_STATE_CHANGED")
    return _relation_change(
        relation, "superseded", replacement.id, "relation.superseded"
    )


def _relation_change(
    relation: RelationLifecycleRecord, lifecycle: str,
    replacement_id: UUID | None, event_type: str,
) -> DomainMutation:
    version = relation.row_version + 1
    before = _relation_snapshot(
        relation, relation.lifecycle_state, relation.row_version
    )
    after = _relation_snapshot(relation, lifecycle, version, replacement_id)
    event = rfc8785.dumps({
        "relation_id": str(relation.id), "relation_type": relation.relation_type,
        "old_state": relation.lifecycle_state, "new_state": lifecycle,
        "row_version": version,
    })
    return DomainMutation(
        "EntityRelation", relation.id, "retract", relation.row_version,
        before, after, ("lifecycle_state",), event_type, event,
    )
