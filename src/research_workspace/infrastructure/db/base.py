"""Shared SQLAlchemy metadata and SQLite storage types."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import MetaData, Text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import CHAR, TypeDecorator


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UUIDText(TypeDecorator[UUID]):
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value: UUID | str | None, dialect):
        if value is None:
            return None
        return str(UUID(str(value)))

    def process_result_value(self, value: str | None, dialect):
        return UUID(value) if value is not None else None


class UTCDateTime(TypeDecorator[datetime]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: datetime | str | None, dialect):
        if value is None:
            return value
        if isinstance(value, str):
            if not value.endswith("Z"):
                raise ValueError("timestamps must be canonical UTC values ending in Z")
            try:
                parsed = datetime.fromisoformat(value[:-1] + "+00:00")
            except ValueError as exc:
                raise ValueError("timestamps must be valid RFC 3339 values") from exc
            if parsed.utcoffset() != timedelta(0):
                raise ValueError("timestamps must be UTC")
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamps must already be UTC")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def process_result_value(self, value: str | None, dialect):
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
