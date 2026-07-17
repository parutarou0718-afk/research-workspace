"""Read projection for Paper screens and commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from research_workspace.domain.entities import Paper


class PaperReadRepository(Protocol):
    def get_paper(self, paper_id: UUID) -> Paper | None: ...
    def list_papers(self, *, include_deleted: bool = False) -> tuple[Paper, ...]: ...


@dataclass(frozen=True, slots=True)
class PaperReadModel:
    id: UUID
    title: str
    status: str
    current_version_id: UUID | None
    deleted_at: datetime | None
    row_version: int
    actions: tuple[str, ...]


def project_paper(paper: Paper) -> PaperReadModel:
    actions = (
        ("restore",)
        if paper.deleted_at is not None
        else ("edit", "soft_delete", "set_current_version")
    )
    return PaperReadModel(
        paper.id, paper.title, paper.status.value, paper.current_version_id,
        paper.deleted_at, paper.row_version, actions,
    )


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

    def project(self, *, include_deleted: bool = False) -> tuple[PaperReadModel, ...]:
        return tuple(
            project_paper(paper)
            for paper in self._repository.list_papers(
                include_deleted=include_deleted
            )
        )
