"""Pure validation and normalization rules for foundation relations."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from enum import Enum
from typing import TypeAlias
from urllib.parse import urlsplit

from research_workspace.domain.enums import (
    ActorType,
    ConfirmationState,
    ProvenanceType,
    RelationEntityType,
    RelationType,
    SubmissionStatus,
)


RelationKey: TypeAlias = tuple[str, str, str, str, str]

_SYMMETRIC = frozenset({"contradicts", "related_to"})
_RELATION_TYPES = frozenset(item.value for item in RelationType) | {
    "version_successor_of"
}
_ENTITY_TYPES = frozenset(item.value for item in RelationEntityType)
_ACTOR_TYPES = frozenset(item.value for item in ActorType)
_PROVENANCE_TYPES = frozenset(item.value for item in ProvenanceType)
_CONFIRMATION_STATES = frozenset(item.value for item in ConfirmationState)
_SUBMISSION_STATES = frozenset(item.value for item in SubmissionStatus)
_ALLOWED_ENDPOINTS: dict[str, frozenset[tuple[str, str]]] = {
    "belongs_to": frozenset({("Note", "Paper"), ("SourceDocument", "Paper"), ("Submission", "Paper")}),
    "derived_from": frozenset(
        (source, target)
        for source in ("Idea", "Note", "PaperVersion")
        for target in ("SourceDocument", "Idea", "Note")
    ),
    "version_of": frozenset({("PaperVersion", "Paper")}),
    "used_in": frozenset({("Idea", "Paper"), ("Idea", "PaperVersion")}),
    "deleted_from": frozenset({("Idea", "PaperVersion")}),
    "supports": frozenset(
        (source, target)
        for source in ("Idea", "Note", "SourceDocument", "EvidenceRef")
        for target in ("Paper", "Idea", "Note", "Submission")
    ),
    "contradicts": frozenset(
        (source, target)
        for source in ("Idea", "Note", "SourceDocument")
        for target in ("Idea", "Note", "SourceDocument")
    ),
    "extends": frozenset({("Paper", "Paper"), ("Idea", "Idea"), ("Note", "Note")}),
    "related_to": frozenset(
        (source, target)
        for source in ("Paper", "PaperVersion", "Idea", "Note", "SourceDocument", "Submission", "Conference", "Grant", "EvidenceRef")
        for target in ("Paper", "PaperVersion", "Idea", "Note", "SourceDocument", "Submission", "Conference", "Grant", "EvidenceRef")
    ),
    "presented_at": frozenset({("Paper", "Conference"), ("PaperVersion", "Conference")}),
    "submitted_as": frozenset({("PaperVersion", "Submission")}),
    "reviewed_by": frozenset({("Submission", "SourceDocument")}),
    "suggested_for": frozenset({("Idea", "Paper")}),
    "split_from": frozenset({("Paper", "Paper")}),
    "merged_from": frozenset({("Paper", "Paper")}),
    "version_successor_of": frozenset({("PaperVersion", "PaperVersion")}),
}


def _value(value: str | Enum) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def normalize_relation_endpoints(
    relation_type: str | Enum,
    source_type: str | Enum,
    source_id: str,
    target_type: str | Enum,
    target_id: str,
) -> tuple[str, str, str, str]:
    """Canonicalize symmetric endpoints while retaining directed semantic order."""

    relation = _value(relation_type)
    source_value = _value(source_type)
    target_value = _value(target_type)
    _require_known_relation_identity(relation, source_value, target_value)
    source = (source_value, source_id)
    target = (target_value, target_id)
    if relation in _SYMMETRIC and target < source:
        source, target = target, source
    return source[0], source[1], target[0], target[1]


def relation_key(
    relation_type: str | Enum,
    source_type: str | Enum,
    source_id: str,
    target_type: str | Enum,
    target_id: str,
) -> RelationKey:
    relation = _value(relation_type)
    endpoints = normalize_relation_endpoints(
        relation, source_type, source_id, target_type, target_id
    )
    return relation, *endpoints


def validate_relation_endpoints(
    relation_type: str | Enum,
    source_type: str | Enum,
    source_id: str,
    target_type: str | Enum,
    target_id: str,
) -> tuple[str, ...]:
    relation = _value(relation_type)
    source = _value(source_type)
    target = _value(target_type)
    if relation not in _RELATION_TYPES:
        return (f"unknown relation type: {relation}",)
    if source not in _ENTITY_TYPES:
        return (f"unknown relation entity type: {source}",)
    if target not in _ENTITY_TYPES:
        return (f"unknown relation entity type: {target}",)
    if source == target and source_id == target_id:
        return ("relation cannot target itself",)
    if (source, target) not in _ALLOWED_ENDPOINTS.get(relation, frozenset()):
        return (f"{source} -> {target} is not allowed for {relation}",)
    return ()


def validate_confirmation_transition(
    actor_type: str | Enum,
    old_state: str | Enum | None,
    new_state: str | Enum,
    *,
    provenance_type: str | Enum = "manual",
    reconsider: bool = False,
) -> tuple[str, ...]:
    actor = _value(actor_type)
    old = None if old_state is None else _value(old_state)
    new = _value(new_state)
    provenance = _value(provenance_type)

    if actor not in _ACTOR_TYPES:
        return (f"unknown actor type: {actor}",)
    if old is not None and old not in _CONFIRMATION_STATES:
        return (f"unknown confirmation state: {old}",)
    if new not in _CONFIRMATION_STATES:
        return (f"unknown confirmation state: {new}",)
    if provenance not in _PROVENANCE_TYPES:
        return (f"unknown provenance type: {provenance}",)

    if old is None:
        if new == "candidate":
            return ()
        if new == "rejected":
            return ("relation cannot be created as rejected",)
        if actor != "user":
            return (f"{actor}-created relation must start as candidate",)
        if provenance in {"rule", "import", "ai"}:
            return (f"{provenance}-created relation must start as candidate",)
        return ()
    if old == new:
        return ()
    if old == "candidate" and new in {"confirmed", "rejected"} and actor != "user":
        return ("only a user may confirm or reject a candidate relation",)
    if old == "confirmed":
        if new == "candidate":
            return ("confirmed relation cannot return to candidate",)
        if new == "rejected" and actor != "user":
            return ("only a user may retract a confirmed relation",)
        return ()
    if old == "rejected":
        if new == "confirmed":
            return ("rejected relation cannot transition directly to confirmed",)
        if actor != "user" or not reconsider:
            return ("rejected relation requires explicit reconsideration",)
    return ()


def validate_relation_provenance(
    provenance_type: str | Enum,
    *,
    actor_type: str | Enum = "user",
    confidence: float | Decimal | None = None,
    origin_task_id: str | None = None,
    evidence_ref_id: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> tuple[str, ...]:
    provenance = _value(provenance_type)
    actor = _value(actor_type)
    if provenance not in _PROVENANCE_TYPES:
        return (f"unknown provenance type: {provenance}",)
    if actor not in _ACTOR_TYPES:
        return (f"unknown actor type: {actor}",)
    errors: list[str] = []
    if provenance in {"import", "ai"}:
        for value, field in (
            (confidence, "confidence"),
            (origin_task_id, "origin_task_id"),
            (evidence_ref_id, "evidence_ref_id"),
        ):
            if value is None:
                errors.append(f"{field} is required for {provenance} provenance")
    elif actor in {"task_executor", "agent"} and origin_task_id is None:
        errors.append(f"origin_task_id is required for {actor} observation")
    if provenance == "ai":
        if provider_id is None:
            errors.append("provider_id is required for ai provenance")
        if model_id is None:
            errors.append("model_id is required for ai provenance")
    return tuple(errors)


_SUBMITTED_STATES = frozenset(
    {"submitted", "editorial_review", "external_review", "revision", "accepted", "rejected", "no_response"}
)


def validate_submission_timing(
    status: str | Enum, submitted_at: object | None
) -> tuple[str, ...]:
    state = _value(status)
    if state not in _SUBMISSION_STATES:
        return (f"unknown submission status: {state}",)
    if state in _SUBMITTED_STATES and submitted_at is None:
        return (f"submitted_at is required for {state}",)
    return ()


def validate_grant_source_url(source_url: str | None) -> tuple[str, ...]:
    if source_url is None:
        return ()
    parsed = urlsplit(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ("source_url must be an absolute http or https URL",)
    return ()


def validate_current_version_ownership(
    paper_id: str,
    current_version_id: str | None,
    *,
    version_resolved: bool | None = None,
    version_id: str | None = None,
    version_paper_id: str | None = None,
    version_is_current: bool | None = None,
) -> tuple[str, ...]:
    if current_version_id is None:
        return ()
    if version_resolved is not True:
        return ("current version could not be resolved",)
    errors: list[str] = []
    if version_id != current_version_id:
        errors.append("resolved current version does not match current_version_id")
    if version_paper_id != paper_id:
        errors.append("current version must belong to the paper")
    if version_is_current is not True:
        errors.append("current version must have is_current=true")
    return tuple(errors)


def validate_parent_version_ownership(
    paper_id: str,
    parent_version_id: str | None,
    *,
    parent_resolved: bool | None = None,
    parent_id: str | None = None,
    parent_paper_id: str | None = None,
) -> tuple[str, ...]:
    if parent_version_id is None:
        return ()
    if parent_resolved is not True:
        return ("parent version could not be resolved",)
    if parent_id != parent_version_id:
        return ("resolved parent version does not match parent_version_id",)
    if parent_paper_id != paper_id:
        return ("parent version must belong to the same paper",)
    return ()


def validate_submission_version_ownership(
    submission_paper_id: str,
    active_version_id: str | None,
    *,
    version_resolved: bool | None = None,
    version_id: str | None = None,
    version_paper_id: str | None = None,
) -> tuple[str, ...]:
    if active_version_id is None:
        return ()
    if version_resolved is not True:
        return ("active submission version could not be resolved",)
    if version_id != active_version_id:
        return ("resolved active version does not match active_version_id",)
    if version_paper_id != submission_paper_id:
        return ("active submission version must belong to the submission paper",)
    return ()


def _require_known_relation_identity(
    relation_type: str, source_type: str, target_type: str
) -> None:
    if relation_type not in _RELATION_TYPES:
        raise ValueError(f"unknown relation type: {relation_type}")
    for entity_type in (source_type, target_type):
        if entity_type not in _ENTITY_TYPES:
            raise ValueError(f"unknown relation entity type: {entity_type}")


def validate_observation_key(
    observation_key: str, existing_keys: Iterable[str]
) -> tuple[str, ...]:
    if observation_key in existing_keys:
        return ("observation_key must be unique",)
    return ()


def cached_relation_confidence(
    current: float | Decimal | None, observed: float | Decimal | None
) -> float | Decimal | None:
    if current is None:
        return observed
    if observed is None:
        return current
    return max(current, observed)


def would_create_relation_cycle(
    existing_edges: Iterable[RelationKey], proposed_edge: RelationKey
) -> bool:
    relation, source_type, source_id, target_type, target_id = proposed_edge
    _require_known_relation_identity(relation, source_type, target_type)
    if relation in {"split_from", "merged_from"}:
        relevant = {"split_from", "merged_from"}
    elif relation == "extends":
        relevant = {"extends"}
    else:
        return False

    graph: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for edge in (*tuple(existing_edges), proposed_edge):
        edge_relation, edge_source_type, edge_source_id, edge_target_type, edge_target_id = edge
        if edge_relation not in relevant:
            continue
        if relation == "extends" and (
            edge_source_type != source_type or edge_target_type != source_type
        ):
            continue
        graph.setdefault((edge_source_type, edge_source_id), set()).add(
            (edge_target_type, edge_target_id)
        )

    start = (target_type, target_id)
    wanted = (source_type, source_id)
    pending = [start]
    seen: set[tuple[str, str]] = set()
    while pending:
        node = pending.pop()
        if node == wanted:
            return True
        if node in seen:
            continue
        seen.add(node)
        pending.extend(graph.get(node, ()))
    return False
