"""Root-scoped, explicitly invoked reconciliation pages."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat

import rfc8785

from research_workspace.application.dto.monitoring_dto import (
    ReconciliationFinding,
    ReconciliationObservation,
    ReconciliationPage,
    ReconciliationPlan,
)
from research_workspace.domain.monitoring import DEFAULT_MONITORING_CONFIG
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)


CancelCheck = Callable[[], bool]


class BoundedReconciler:
    """Enumerate at most one requested page without content reads or scheduling."""

    def scan_page(
        self,
        plan: ReconciliationPlan,
        known: Iterable[ReconciliationObservation],
        *,
        cancel_requested: CancelCheck | None = None,
    ) -> ReconciliationPage:
        cancelled = cancel_requested or (lambda: False)
        state = self._state(plan)
        observations = {item.normalized_path: item for item in known}
        findings: list[ReconciliationFinding] = []
        seen = 0

        while seen < plan.page_size and (state["current"] or state["directories"]):
            current = state["current"] or state["directories"].pop(0)
            state["current"] = current
            directory = plan.root_path if current == "." else plan.root_path / current
            after = state["after"]
            entries = sorted(
                os.scandir(directory), key=lambda item: (item.name.casefold(), item.name)
            )
            progressed = False
            for entry in entries:
                if after is not None and (
                    entry.name.casefold(), entry.name
                ) <= (after.casefold(), after):
                    continue
                if cancelled():
                    return ReconciliationPage(
                        self._checkpoint(state), seen, tuple(findings), False, True
                    )
                progressed = True
                state["after"] = entry.name
                path = Path(entry.path)
                details = path.stat(follow_symlinks=False)
                if entry.is_symlink() or self._is_reparse(details):
                    continue
                relative = path.relative_to(plan.root_path).as_posix()
                if stat.S_ISDIR(details.st_mode):
                    state["directories"].append(relative)
                    continue
                if (
                    not stat.S_ISREG(details.st_mode)
                    or path.suffix.casefold()
                    not in DEFAULT_MONITORING_CONFIG.allowed_extensions
                    or path.name.casefold() in DEFAULT_MONITORING_CONFIG.excluded_names
                ):
                    continue
                seen += 1
                finding = self._finding(path, details)
                if self._changed(observations.get(finding.normalized_path), finding):
                    findings.append(finding)
                if seen == plan.page_size:
                    break
            if seen == plan.page_size:
                break
            if not progressed or state["after"] == (entries[-1].name if entries else None):
                state["current"], state["after"] = None, None

        completed = state["current"] is None and not state["directories"]
        checkpoint = None if completed else self._checkpoint(state)
        return ReconciliationPage(checkpoint, seen, tuple(findings), completed)

    @staticmethod
    def _state(plan: ReconciliationPlan) -> dict[str, object]:
        if plan.checkpoint is None:
            return {"directories": ["."], "current": None, "after": None}
        value = json.loads(plan.checkpoint)
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("directories"), list)
            or any(not isinstance(item, str) for item in value["directories"])
            or value.get("current") is not None
            and not isinstance(value.get("current"), str)
            or value.get("after") is not None
            and not isinstance(value.get("after"), str)
        ):
            raise ValueError("RECONCILIATION_CHECKPOINT_INVALID")
        paths = [*value["directories"]]
        if value.get("current") is not None:
            paths.append(value["current"])
        if any(Path(item).is_absolute() or ".." in Path(item).parts for item in paths):
            raise ValueError("RECONCILIATION_CHECKPOINT_INVALID")
        return value

    @staticmethod
    def _checkpoint(state: dict[str, object]) -> bytes:
        return rfc8785.dumps(state)

    @staticmethod
    def _is_reparse(details: os.stat_result) -> bool:
        return bool(
            getattr(details, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )

    @staticmethod
    def _finding(path: Path, details: os.stat_result) -> ReconciliationFinding:
        return ReconciliationFinding(
            path,
            normalize_path_text(path),
            normalized_path_hash(path),
            details.st_size,
            datetime.fromtimestamp(details.st_mtime, timezone.utc),
            str(getattr(details, "st_ino", "")) or None,
            str(details.st_dev),
        )

    @staticmethod
    def _changed(
        known: ReconciliationObservation | None, current: ReconciliationFinding
    ) -> bool:
        if known is None:
            return True
        return (
            known.size_bytes != current.size_bytes
            or known.modified_at != current.modified_at
            or known.file_id_hint is not None
            and known.file_id_hint != current.file_id_hint
            or known.volume_serial_hint is not None
            and known.volume_serial_hint != current.volume_serial_hint
        )
