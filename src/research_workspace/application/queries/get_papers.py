"""Read projection for Paper screens and commands."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from research_workspace.domain.entities import Paper


class PaperReadRepository(Protocol):
    def get_paper(self, paper_id: UUID) -> Paper | None: ...
    def list_papers(self, *, include_deleted: bool = False) -> tuple[Paper, ...]: ...


class GetPapersQuery:
    def __init__(self, repository: PaperReadRepository) -> None:
        self._repository = repository

    def get(self, paper_id: UUID) -> Paper:
        paper = self._repository.get_paper(paper_id)
        if paper is None:
            raise LookupError("PAPER_NOT_FOUND")
        return paper

    def list(self, *, include_deleted: bool = False) -> tuple[Paper, ...]:
        return self._repository.list_papers(include_deleted=include_deleted)
