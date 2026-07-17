"""Non-blocking watchdog callback adapter.

Callbacks translate provider notifications into immutable DTOs and enqueue them.
They do not perform persistence, content reads, imports, or domain transitions.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from queue import Empty, SimpleQueue
from typing import Callable
from uuid import UUID, uuid4

import rfc8785
from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileMovedEvent
from watchdog.observers import Observer

from research_workspace.application.dto.monitoring_dto import (
    MonitoringRootPlan,
    RawFileEventDTO,
)
from research_workspace.domain.monitoring import RawFileEventType


Clock = Callable[[], datetime]


class _RawEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        plan: MonitoringRootPlan,
        enqueue: Callable[[RawFileEventDTO], None],
        clock: Clock,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._enqueue = enqueue
        self._clock = clock

    def on_created(self, event: FileSystemEvent) -> None:
        self._record(RawFileEventType.CREATED, event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._record(RawFileEventType.MODIFIED, event)

    def on_moved(self, event: FileMovedEvent) -> None:
        self._record(RawFileEventType.MOVED, event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._record(RawFileEventType.DELETED, event)

    def _record(self, event_type: RawFileEventType, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        observed_at = self._clock()
        source = Path(event.src_path)
        destination = (
            Path(event.dest_path)
            if event_type is RawFileEventType.MOVED and isinstance(event, FileMovedEvent)
            else None
        )
        sequence = rfc8785.dumps({"is_synthetic": bool(event.is_synthetic)})
        framed = rfc8785.dumps(
            {
                "monitoring_root_id": str(self._plan.monitoring_root_id),
                "watcher_generation": self._plan.watcher_generation,
                "event_type": event_type.value,
                "source_path": str(source),
                "destination_path": str(destination) if destination is not None else None,
                "observed_at": observed_at.isoformat(),
                "raw_sequence": sequence.decode("utf-8"),
            }
        )
        self._enqueue(
            RawFileEventDTO(
                uuid4(),
                self._plan.monitoring_root_id,
                "watchdog",
                event_type,
                source,
                destination,
                observed_at,
                observed_at,
                sequence,
                None,
                hashlib.sha256(framed).hexdigest(),
            )
        )


class WatchdogObserver:
    """Own provider observers while exposing only immutable queued events."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._events: SimpleQueue[RawFileEventDTO] = SimpleQueue()
        self._observers: dict[UUID, Observer] = {}

    def _make_handler(self, plan: MonitoringRootPlan) -> FileSystemEventHandler:
        return _RawEventHandler(plan, self._events.put, self._clock)

    def start(self, plan: MonitoringRootPlan) -> None:
        if plan.monitoring_root_id in self._observers:
            raise ValueError("MONITOR_ROOT_STATE_CHANGED")
        observer = Observer()
        observer.schedule(self._make_handler(plan), str(plan.root_path), recursive=True)
        observer.start()
        self._observers[plan.monitoring_root_id] = observer

    def stop(self, monitoring_root_id: UUID) -> None:
        observer = self._observers.get(monitoring_root_id)
        if observer is not None:
            observer.stop()

    def join(self, monitoring_root_id: UUID, timeout_seconds: float) -> bool:
        observer = self._observers.get(monitoring_root_id)
        if observer is None:
            return True
        observer.join(timeout_seconds)
        stopped = not observer.is_alive()
        if stopped:
            self._observers.pop(monitoring_root_id, None)
        return stopped

    def drain_events(self, limit: int | None = None) -> tuple[RawFileEventDTO, ...]:
        drained: list[RawFileEventDTO] = []
        while limit is None or len(drained) < limit:
            try:
                drained.append(self._events.get_nowait())
            except Empty:
                break
        return tuple(drained)
