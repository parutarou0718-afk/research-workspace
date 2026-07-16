from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from research_workspace.infrastructure.db.models import (
    DomainEventModel,
    ImportItemModel,
    SourceObservationModel,
    SourceSnapshotModel,
)


def test_same_hash_reuses_physical_snapshot_and_preserves_observations(
    import_application, tmp_path: Path
) -> None:
    first_path = tmp_path / "external-a" / "Draft.pdf"
    second_path = tmp_path / "external-b" / "Renamed Draft.pdf"
    first_path.parent.mkdir()
    second_path.parent.mkdir()
    content = b"one immutable paper version"
    first_path.write_bytes(content)
    second_path.write_bytes(content)

    result = import_application.command.execute(
        import_application.request((first_path, second_path))
    )

    assert [item.state for item in result.item_results] == ["imported", "duplicate_content"]
    assert result.item_results[0].snapshot_id == result.item_results[1].snapshot_id
    with import_application.factory() as session:
        assert session.scalar(select(func.count(SourceSnapshotModel.id))) == 1
        observations = session.scalars(
            select(SourceObservationModel).order_by(SourceObservationModel.original_filename)
        ).all()
        assert {Path(row.original_path) for row in observations} == {
            first_path.resolve(), second_path.resolve()
        }
        assert {row.original_filename for row in observations} == {"Draft.pdf", "Renamed Draft.pdf"}
        assert session.scalar(select(func.count(ImportItemModel.id))) == 2
        events = session.scalars(select(DomainEventModel).order_by(DomainEventModel.created_at)).all()
        assert [event.event_type for event in events] == [
            "source.snapshot_imported", "source.snapshot_reused"
        ]
        for event in events:
            assert set(json.loads(event.payload_json)) == {
                "snapshot_id", "source_observation_id", "import_item_id", "sha256", "size_bytes"
            }
            assert str(first_path) not in event.payload_json
            assert str(second_path) not in event.payload_json

    snapshot_files = list((import_application.workspace / "sources" / "sha256").glob("*/*/content"))
    assert len(snapshot_files) == 1
    assert snapshot_files[0].read_bytes() == content
