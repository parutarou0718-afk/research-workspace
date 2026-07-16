from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlalchemy import select

from research_workspace.application.commands.import_documents import ImportDocumentsCommand
from research_workspace.application.services.import_orchestrator import public_import_outcome
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    ImportBatchModel,
    ImportItemModel,
)


def _batch_and_items(app, batch_id):
    with app.factory() as session:
        batch = session.get(ImportBatchModel, batch_id)
        operation = session.get(BackgroundOperationModel, batch.operation_id)
        items = session.scalars(
            select(ImportItemModel)
            .where(ImportItemModel.batch_id == batch_id)
            .order_by(ImportItemModel.created_at, ImportItemModel.id)
        ).all()
        return batch, operation, items


def test_partial_item_failure_preserves_success_and_truthful_batch(
    import_application, tmp_path: Path
) -> None:
    valid = tmp_path / "valid.pdf"
    valid.write_bytes(b"valid")
    missing = tmp_path / "missing.pdf"

    result = import_application.command.execute(import_application.request((valid, missing)))

    batch, operation, items = _batch_and_items(import_application, result.batch_id)
    assert batch.status == "completed_with_failures"
    assert operation.status == "completed"
    assert Counter(item.state for item in items) == {"imported": 1, "failed": 1}
    assert len(result.item_results) == 1
    assert len(result.failed_item_ids) == 1
    assert result.cancelled_item_ids == ()


def test_all_failed_batch_is_failed(import_application, tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"

    result = import_application.command.execute(import_application.request((missing,)))

    batch, operation, items = _batch_and_items(import_application, result.batch_id)
    assert batch.status == "failed"
    assert operation.status == "failed"
    assert items[0].state == "failed"
    assert items[0].error_code == "SOURCE_PATH_UNSAFE"


def test_cancellation_preserves_committed_items_and_marks_remaining(
    import_application, tmp_path: Path
) -> None:
    paths = tuple(tmp_path / f"item-{index}.pdf" for index in range(3))
    for index, path in enumerate(paths):
        path.write_bytes(f"content-{index}".encode())
    checks = 0

    def cancel_after_first() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    command = ImportDocumentsCommand(import_application.command.orchestrator, cancel_requested=cancel_after_first)
    result = command.execute(import_application.request(paths))

    batch, operation, items = _batch_and_items(import_application, result.batch_id)
    assert batch.status == "cancelled"
    assert operation.status == "cancelled"
    assert Counter(item.state for item in items) == {"imported": 1, "cancelled": 2}
    assert len(result.item_results) == 1
    assert result.failed_item_ids == ()
    assert len(result.cancelled_item_ids) == 2


def test_public_import_outcome_maps_only_terminal_public_facts() -> None:
    assert public_import_outcome("imported") == "imported"
    assert public_import_outcome("duplicate_content") == "imported"
    assert public_import_outcome("failed") == "failed"
    assert public_import_outcome("pending") is None
    assert public_import_outcome("cancelled") is None
