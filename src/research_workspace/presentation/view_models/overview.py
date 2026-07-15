"""Immutable presentation data for the Overview page."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OverviewViewModel:
    revision_count: int
    ready_count: int
    upcoming_conference_count: int
    upcoming_grant_count: int
    suggestions: tuple[str, ...]
    submission_rows: tuple[str, ...]
    activities: tuple[str, ...]
    focus_items: tuple[str, ...]
    focus_progress: int

    def __post_init__(self) -> None:
        for field_name in (
            "suggestions",
            "submission_rows",
            "activities",
            "focus_items",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
