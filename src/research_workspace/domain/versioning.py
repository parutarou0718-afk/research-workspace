"""Closed Gate 2 deterministic candidate vocabulary."""

from enum import StrEnum


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
