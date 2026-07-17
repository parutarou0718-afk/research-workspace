"""Read projection for Idea commands and pages."""

from typing import Protocol
from uuid import UUID

from research_workspace.domain.entities import Idea


class IdeaReadRepository(Protocol):
    def get_idea(self, idea_id: UUID) -> Idea | None: ...
    def list_ideas(self, *, include_deleted: bool = False) -> tuple[Idea, ...]: ...


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
