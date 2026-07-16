"""Immutable deterministic operation vocabulary for Gate 1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from research_workspace.domain.capabilities import PermissionContext


def freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


@dataclass(frozen=True)
class OperationWorkPlan:
    operation_id: UUID
    operation_type: Literal["snapshot_import", "document_parse", "maintenance_verify"]
    work_plan_fingerprint: str
    permission_context: PermissionContext


@dataclass(frozen=True)
class OperationOutcome:
    operation_id: UUID
    status: Literal["completed", "failed", "cancelled", "manual_attention"]
    error_code: str | None
