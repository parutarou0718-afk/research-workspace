"""Read projection for Idea commands and pages."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from research_workspace.domain.entities import Idea


class IdeaReadRepository(Protocol):
    def get_idea(self, idea_id: UUID) -> Idea | None: ...
    def list_ideas(self, *, include_deleted: bool = False) -> tuple[Idea, ...]: ...


@dataclass(frozen=True, slots=True)
class IdeaReadModel:
    id: UUID
    title: str
    content: str
    status: str
    origin_type: str
    deleted_at: datetime | None
    row_version: int
    actions: tuple[str, ...]


def project_idea(idea: Idea) -> IdeaReadModel:
    actions = (
        ("restore",)
        if idea.deleted_at is not None
        else ("edit", "soft_delete")
    )
    return IdeaReadModel(
        idea.id, idea.title, idea.content, idea.status.value,
        idea.origin_type.value, idea.deleted_at, idea.row_version, actions,
    )


class GetIdeasQuery:
    def __init__(self, repository: IdeaReadRepository) -> None:
        self._repository = repository

    def get(self, idea_id: UUID) -> Idea:
        idea = self._repository.get_idea(idea_id)
        if idea is None:
            raise LookupError("IDEA_NOT_FOUND")
        return idea

    def list(self, *, include_deleted: bool = False) -> tuple[Idea, ...]:
        return self._repository.list_ideas(include_deleted=include_deleted)

    def project(self, *, include_deleted: bool = False) -> tuple[IdeaReadModel, ...]:
        return tuple(
            project_idea(idea)
            for idea in self._repository.list_ideas(
                include_deleted=include_deleted
            )
        )
