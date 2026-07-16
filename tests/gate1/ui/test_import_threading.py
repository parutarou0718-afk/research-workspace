from pathlib import Path
import threading

from PySide6.QtWidgets import QLabel, QProgressBar


class _Handle:
    done = False
    status = "running"

    def cancel(self) -> None:
        pass


class _Pipeline:
    def __init__(self) -> None:
        self.handle = _Handle()

    def start(self, request):
        return self.handle


class _Services:
    def __init__(self) -> None:
        self.import_parse_pipeline = _Pipeline()

    def create_import_request(self, paths):
        return tuple(paths)


def test_operation_state_is_applied_only_on_qt_owner_thread(qtbot, tmp_path: Path) -> None:
    from research_workspace.presentation.dialogs.import_batch_dialog import ImportBatchDialog

    source = tmp_path / "paper.pdf"
    source.write_bytes(b"content")
    services = _Services()
    dialog = ImportBatchDialog(services=services, source_paths=(source,))
    qtbot.addWidget(dialog)
    dialog.start_import()

    failures: list[str] = []

    def background_update() -> None:
        try:
            dialog.refresh_operation_state()
        except RuntimeError as exc:
            failures.append(str(exc))

    thread = threading.Thread(target=background_update)
    thread.start()
    thread.join()
    assert failures == ["UI_UPDATE_OUTSIDE_QT_THREAD"]

    services.import_parse_pipeline.handle.done = True
    services.import_parse_pipeline.handle.status = "completed"
    dialog.refresh_operation_state()
    assert dialog.findChild(QProgressBar, "importProgressBar").value() == 100
    assert "完成" in dialog.findChild(QLabel, "progressStatusLabel").text()
