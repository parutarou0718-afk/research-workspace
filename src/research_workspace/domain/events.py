"""Future-compatible domain-event contract boundary."""

from collections.abc import Mapping
from typing import TypeAlias


DomainEvent: TypeAlias = Mapping[str, object]
