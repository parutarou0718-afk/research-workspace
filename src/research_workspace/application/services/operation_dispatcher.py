"""Small outer dispatch boundary that authorizes before invoking a handler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from research_workspace.application.services.authorization import (
    AuthorizationFailure,
    AuthorizationRequest,
    authorize_request,
)
from research_workspace.domain.capabilities import PermissionContext

T = TypeVar("T")


@dataclass(frozen=True)
class DispatchResult(Generic[T]):
    value: T | None
    permission_context: PermissionContext | None
    error_code: str | None


class OperationDispatcher:
    def dispatch(
        self,
        request: AuthorizationRequest,
        handler: Callable[[PermissionContext], T],
    ) -> DispatchResult[T]:
        try:
            permission_context = authorize_request(request)
        except AuthorizationFailure as failure:
            return DispatchResult(None, None, failure.error_code)
        return DispatchResult(handler(permission_context), permission_context, None)

    def dispatch_context(
        self,
        context: PermissionContext,
        handler: Callable[[PermissionContext], T],
    ) -> DispatchResult[T]:
        raise ValueError("PermissionContext is not a reusable credential")
