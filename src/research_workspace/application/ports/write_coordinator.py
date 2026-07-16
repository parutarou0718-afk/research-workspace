"""Framework-free persistent-write boundary."""

from typing import Protocol

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.parsing_dto import ParseFailureDTO, ParseSuccessDTO


class WriteCoordinator(Protocol):
    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO: ...

    def register_parse_success(self, result: ParseSuccessDTO) -> None: ...

    def register_parse_failure(self, result: ParseFailureDTO) -> None: ...
