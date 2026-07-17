"""Closed Gate 2 deterministic candidate vocabulary."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
import unicodedata
from uuid import UUID


class CandidateStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class VersionRuleId(StrEnum):
    R1_SOURCE_CONTINUITY = "R1_SOURCE_CONTINUITY"
    R2_REPLACE_CONTINUITY = "R2_REPLACE_CONTINUITY"
    R3_PAPER_TITLE_TIME = "R3_PAPER_TITLE_TIME"
    R4_NAME_TITLE_TEXT = "R4_NAME_TITLE_TEXT"
    R5_ZERO_TEXT_LINEAGE = "R5_ZERO_TEXT_LINEAGE"


class VersioningError(ValueError):
    pass


def clean_version_label(label: str) -> str:
    display = unicodedata.normalize("NFC", label).strip()
    if not 1 <= len(display) <= 200:
        raise VersioningError("INVALID_VERSION_LABEL")
    return display


def normalize_version_label(label: str) -> str:
    display = clean_version_label(label)
    return re.sub(r"\s+", " ", display).casefold()


@dataclass(frozen=True, slots=True)
class PaperVersionRecord:
    id: UUID
    paper_id: UUID
    source_snapshot_id: UUID
    context_parse_artifact_id: UUID | None
    version_label: str
    normalized_version_label: str
    lifecycle_state: str
    row_version: int
    created_at: datetime
    confirmed_by_command_id: UUID
    updated_at: datetime
    updated_by_command_id: UUID
    retracted_at: datetime | None
    retracted_by_command_id: UUID | None
