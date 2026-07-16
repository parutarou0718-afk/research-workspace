from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton


def test_batch_dialog_discloses_immutable_copy_and_storage(qtbot, tmp_path: Path) -> None:
    from research_workspace.presentation.dialogs.import_batch_dialog import ImportBatchDialog

    first = tmp_path / "first.pdf"
    second = tmp_path / "second.docx"
    first.write_bytes(b"a" * 1024)
    second.write_bytes(b"b" * 2048)
    dialog = ImportBatchDialog(services=object(), source_paths=(first, second))
    qtbot.addWidget(dialog)

    immutable = dialog.findChild(QLabel, "immutableCopyDisclosureLabel").text()
    estimate = dialog.findChild(QLabel, "estimatedStorageLabel").text()
    uncertainty = dialog.findChild(QLabel, "estimateUncertaintyLabel").text()
    assert "本地不可变副本" in immutable
    assert "3.0 KiB" in estimate
    assert "预计新增空间" in estimate
    assert "核验内容哈希" in uncertainty
    assert dialog.findChild(QPushButton, "startImportButton").isEnabled()


class _Handle:
    done = False
    status = "running"

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _Pipeline:
    def __init__(self) -> None:
        self.calls = []
        self.handle = _Handle()

    def start(self, request):
        self.calls.append(request)
        return self.handle


class _Services:
    def __init__(self) -> None:
        self.import_parse_pipeline = _Pipeline()

    def create_import_request(self, paths):
        return tuple(paths)


def test_running_dialog_prevents_duplicate_submission_and_supports_cancel(
    qtbot, tmp_path: Path
) -> None:
    from research_workspace.presentation.dialogs.import_batch_dialog import ImportBatchDialog

    source = tmp_path / "paper.pdf"
    source.write_bytes(b"content")
    services = _Services()
    dialog = ImportBatchDialog(services=services, source_paths=(source,))
    qtbot.addWidget(dialog)
    start = dialog.findChild(QPushButton, "startImportButton")
    cancel = dialog.findChild(QPushButton, "cancelImportButton")

    qtbot.mouseClick(start, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(start, Qt.MouseButton.LeftButton)
    assert len(services.import_parse_pipeline.calls) == 1
    assert not start.isEnabled()
    assert cancel.isEnabled()

    qtbot.mouseClick(cancel, Qt.MouseButton.LeftButton)
    assert services.import_parse_pipeline.handle.cancelled
    assert not cancel.isEnabled()


def test_running_dialog_cannot_be_dismissed_without_safe_cancellation(
    qtbot, tmp_path: Path
) -> None:
    from research_workspace.presentation.dialogs.import_batch_dialog import ImportBatchDialog

    source = tmp_path / "paper.pdf"
    source.write_bytes(b"content")
    dialog = ImportBatchDialog(services=_Services(), source_paths=(source,))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.start_import()

    dialog.reject()

    assert dialog.isVisible()
