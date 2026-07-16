"""Immutable presentation data for Gate 1 imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ParseDisplayState = Literal[
    "searchable", "zero_text", "parse_failed", "password_required"
]

_LOCALIZED_PARSE_STATUS: dict[ParseDisplayState, str] = {
    "searchable": "已导入，可检索文本",
    "zero_text": "已导入，无可提取文本，需要 OCR",
    "parse_failed": "已导入，解析失败",
    "password_required": "已导入，需要密码",
}


def localized_parse_status(state: str) -> str:
    try:
        return _LOCALIZED_PARSE_STATUS[state]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError("UNKNOWN_IMPORT_STATUS") from exc


@dataclass(frozen=True, slots=True)
class ImportRowViewModel:
    filename: str
    status: str


@dataclass(frozen=True, slots=True)
class ImportsViewModel:
    rows: tuple[ImportRowViewModel, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
