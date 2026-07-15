"""Structured success/failure result shared by application services."""

from dataclasses import dataclass
from typing import Generic, TypeVar

from research_workspace.shared.errors import AppError


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Result(Generic[T]):
    ok: bool
    value: T | None = None
    error: AppError | None = None

    def __post_init__(self) -> None:
        if self.ok == (self.error is not None):
            raise ValueError("A result must contain either a value or an error")

    @classmethod
    def success(cls, value: T | None = None) -> "Result[T]":
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, error: AppError) -> "Result[T]":
        return cls(ok=False, error=error)
