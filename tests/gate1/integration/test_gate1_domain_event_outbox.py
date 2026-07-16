from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import event, func, select

from research_workspace.infrastructure.db.models import (
    DomainEventModel,
    ImportItemModel,
    SourceSnapshotModel,
)


def test_event_failure_rolls_back_registration_but_keeps_unregistered_file_for_retry(
    import_application, tmp_path: Path
) -> None:
    source = tmp_path / "external" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"registration must be atomic with event")

    def fail_event_insert(mapper, connection, target):
        raise RuntimeError("injected event insert failure")

    event.listen(DomainEventModel, "before_insert", fail_event_insert)
    try:
        first = import_application.command.execute(import_application.request((source,)))
    finally:
        event.remove(DomainEventModel, "before_insert", fail_event_insert)

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    final = import_application.workspace / "sources" / "sha256" / digest[:2] / digest / "content"
    assert final.exists()
    assert first.item_results == ()
    assert len(first.failed_item_ids) == 1
    with import_application.factory() as session:
        assert session.scalar(select(func.count(SourceSnapshotModel.id))) == 0
        assert session.scalar(select(func.count(DomainEventModel.id))) == 0
        failed_item = session.get(ImportItemModel, first.failed_item_ids[0])
        assert failed_item.state == "failed"
        assert failed_item.snapshot_id is None

    second = import_application.command.execute(import_application.request((source,)))
    assert second.item_results[0].state == "imported"
    with import_application.factory() as session:
        assert session.scalar(select(func.count(SourceSnapshotModel.id))) == 1
        assert session.scalar(select(func.count(DomainEventModel.id))) == 1
        assert session.scalar(select(DomainEventModel.event_type)) == "source.snapshot_imported"
    assert len(list((import_application.workspace / "sources" / "sha256").glob("*/*/content"))) == 1
