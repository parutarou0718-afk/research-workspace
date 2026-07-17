"""Protected PaperVersion membership and per-Paper DAG plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import rfc8785

from research_workspace.application.services.command_dispatcher import DomainMutation
from research_workspace.domain.versioning import (
    PaperVersionRecord,
    clean_version_label,
    normalize_version_label,
)


class VersionGraphError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParseContextRef:
    id: UUID
    source_snapshot_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class RetractionDependencies:
    is_current: bool = False
    active_submissions: int = 0
    active_edges: int = 0

    @property
    def any(self) -> bool:
        return self.is_current or bool(self.active_submissions or self.active_edges)


@dataclass(frozen=True, slots=True)
class VersionEdge:
    id: UUID
    paper_id: UUID
    later_version_id: UUID
    earlier_version_id: UUID


def resolve_membership(
    versions: tuple[PaperVersionRecord, ...],
    paper_id: UUID,
    source_snapshot_id: UUID,
) -> tuple[PaperVersionRecord | None, tuple[str, ...]]:
    same_snapshot = tuple(
        version for version in versions
        if version.source_snapshot_id == source_snapshot_id
    )
    for version in same_snapshot:
        if version.paper_id == paper_id:
            return version, ()
    warnings = (
        ("SNAPSHOT_ALREADY_USED_BY_ANOTHER_PAPER",) if same_snapshot else ()
    )
    return None, warnings


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _version_snapshot(
    version_id: UUID, row_version: int, paper_id: UUID, snapshot_id: UUID,
    context_id: UUID | None, label: str, normalized: str, lifecycle: str,
    retracted_at: datetime | None,
) -> bytes:
    return rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "PaperVersion",
        "entity_id": str(version_id), "row_version": row_version,
        "fields": {
            "paper_id": str(paper_id), "source_snapshot_id": str(snapshot_id),
            "context_parse_artifact_id": str(context_id) if context_id else None,
            "version_label": label, "normalized_version_label": normalized,
            "lifecycle_state": lifecycle, "retracted_at": _iso(retracted_at),
        },
    })


def _version_event(
    version_id: UUID, paper_id: UUID, snapshot_id: UUID, row_version: int,
    old_context: UUID | None, new_context: UUID | None,
) -> bytes:
    return rfc8785.dumps({
        "paper_version_id": str(version_id), "paper_id": str(paper_id),
        "source_snapshot_id": str(snapshot_id), "row_version": row_version,
        "old_context_parse_artifact_id": str(old_context) if old_context else None,
        "new_context_parse_artifact_id": str(new_context) if new_context else None,
    })


def create_version_membership(
    command_id: UUID, version_id: UUID, paper_id: UUID, source_snapshot_id: UUID,
    version_label: str, context: ParseContextRef | None, now: datetime,
) -> DomainMutation:
    del command_id, now
    if context is not None and (
        context.source_snapshot_id != source_snapshot_id
        or context.status != "succeeded"
    ):
        raise VersionGraphError("INVALID_VERSION_ASSIGNMENT")
    display = clean_version_label(version_label)
    normalized = normalize_version_label(display)
    context_id = context.id if context else None
    after = _version_snapshot(
        version_id, 1, paper_id, source_snapshot_id, context_id, display,
        normalized, "active", None,
    )
    return DomainMutation(
        "PaperVersion", version_id, "confirm", None, None, after,
        ("context_parse_artifact_id", "lifecycle_state", "paper_id",
         "source_snapshot_id", "version_label"),
        "paper_version.confirmed",
        _version_event(
            version_id, paper_id, source_snapshot_id, 1, None, context_id
        ),
    )


def change_version_context(
    version: PaperVersionRecord, command_id: UUID,
    context: ParseContextRef | None, now: datetime,
) -> DomainMutation:
    del command_id, now
    if version.lifecycle_state != "active":
        raise VersionGraphError("INVALID_VERSION_ASSIGNMENT")
    if context is not None and (
        context.source_snapshot_id != version.source_snapshot_id
        or context.status != "succeeded"
    ):
        raise VersionGraphError("INVALID_VERSION_ASSIGNMENT")
    context_id = context.id if context else None
    if context_id == version.context_parse_artifact_id:
        raise VersionGraphError("COMMAND_VALIDATION_FAILED")
    return _version_change(
        version, "update", context_id, "active", None,
        ("context_parse_artifact_id",), "paper_version.context_parse_changed",
    )


def retract_version_membership(
    version: PaperVersionRecord, command_id: UUID, now: datetime,
    dependencies: RetractionDependencies,
) -> DomainMutation:
    del command_id
    if version.lifecycle_state != "active":
        raise VersionGraphError("COMMAND_VALIDATION_FAILED")
    if dependencies.any:
        raise VersionGraphError("VERSION_RETRACTION_DEPENDENCY_CONFLICT")
    return _version_change(
        version, "retract", version.context_parse_artifact_id, "retracted", now,
        ("lifecycle_state", "retracted_at"), "paper_version.retracted",
    )


def _version_change(
    version: PaperVersionRecord, operation: str, context_id: UUID | None,
    lifecycle: str, retracted_at: datetime | None, changed: tuple[str, ...],
    event_type: str,
) -> DomainMutation:
    before = _version_snapshot(
        version.id, version.row_version, version.paper_id,
        version.source_snapshot_id, version.context_parse_artifact_id,
        version.version_label, version.normalized_version_label,
        version.lifecycle_state, version.retracted_at,
    )
    row_version = version.row_version + 1
    after = _version_snapshot(
        version.id, row_version, version.paper_id, version.source_snapshot_id,
        context_id, version.version_label, version.normalized_version_label,
        lifecycle, retracted_at,
    )
    return DomainMutation(
        "PaperVersion", version.id, operation, version.row_version, before, after,
        tuple(sorted(changed)), event_type,
        _version_event(
            version.id, version.paper_id, version.source_snapshot_id, row_version,
            version.context_parse_artifact_id, context_id,
        ),
    )


def create_successor_relation(
    command_id: UUID, later: PaperVersionRecord, earlier: PaperVersionRecord,
    active_edges: tuple[VersionEdge, ...], relation_id: UUID, now: datetime,
) -> DomainMutation:
    del command_id, now
    if later.id == earlier.id:
        raise VersionGraphError("VERSION_RELATION_SELF_LINK")
    if (
        later.paper_id != earlier.paper_id
        or later.lifecycle_state != "active"
        or earlier.lifecycle_state != "active"
    ):
        raise VersionGraphError("INVALID_VERSION_RELATION_ENDPOINT")
    if any(
        edge.later_version_id == later.id
        and edge.earlier_version_id == earlier.id
        for edge in active_edges
    ):
        raise VersionGraphError("VERSION_RELATION_DUPLICATE")
    if any(edge.paper_id != later.paper_id for edge in active_edges):
        raise VersionGraphError("INVALID_VERSION_RELATION_ENDPOINT")
    if _reachable(earlier.id, later.id, active_edges):
        raise VersionGraphError("VERSION_GRAPH_CYCLE")
    after = rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "EntityRelation",
        "entity_id": str(relation_id), "row_version": 1,
        "fields": {
            "relation_type": "version_successor_of",
            "source_type": "PaperVersion", "source_id": str(later.id),
            "target_type": "PaperVersion", "target_id": str(earlier.id),
            "confirmation_state": "confirmed", "lifecycle_state": "active",
        },
    })
    event = rfc8785.dumps({
        "relation_id": str(relation_id),
        "later_paper_version_id": str(later.id),
        "earlier_paper_version_id": str(earlier.id), "row_version": 1,
    })
    return DomainMutation(
        "EntityRelation", relation_id, "create", None, None, after,
        ("confirmation_state", "lifecycle_state", "relation_type",
         "source_id", "target_id"),
        "paper_version_relation.created", event,
    )


def _reachable(
    start: UUID, target: UUID, edges: tuple[VersionEdge, ...]
) -> bool:
    adjacency: dict[UUID, set[UUID]] = {}
    for edge in edges:
        adjacency.setdefault(edge.later_version_id, set()).add(
            edge.earlier_version_id
        )
    pending, seen = [start], set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(adjacency.get(current, ()))
    return False
