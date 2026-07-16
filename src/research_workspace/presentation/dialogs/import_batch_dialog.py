"""Gate 1 import batch disclosure and progress dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton

from research_workspace.presentation import load_ui_into, require_child


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KiB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MiB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GiB"


class ImportBatchDialog(QDialog):
    def __init__(self, services, source_paths, parent=None):
        super().__init__(parent)
        self.services = services
        self.source_paths = tuple(Path(path) for path in source_paths)
        self._operation_handle = None
        load_ui_into("import_batch_dialog.ui", self)
        self.immutable_label = require_child(
            self, QLabel, "immutableCopyDisclosureLabel"
        )
        self.estimated_storage_label = require_child(
            self, QLabel, "estimatedStorageLabel"
        )
        self.uncertainty_label = require_child(
            self, QLabel, "estimateUncertaintyLabel"
        )
        self.progress_status_label = require_child(
            self, QLabel, "progressStatusLabel"
        )
        self.progress_bar = require_child(self, QProgressBar, "importProgressBar")
        self.start_button = require_child(self, QPushButton, "startImportButton")
        self.cancel_button = require_child(self, QPushButton, "cancelImportButton")
        self.close_button = require_child(self, QPushButton, "closeDialogButton")
        self.start_button.clicked.connect(self.start_import)
        self.cancel_button.clicked.connect(self.cancel_import)
        self.close_button.clicked.connect(self.reject)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self.refresh_operation_state)
        self._render_estimate()

    def reject(self) -> None:
        if self._operation_handle is not None and not self._operation_handle.done:
            return
        super().reject()

    def _render_estimate(self) -> None:
        total = 0
        for path in self.source_paths:
            try:
                total += path.stat().st_size
            except OSError:
                pass
        self.estimated_storage_label.setText(
            f"已选择 {len(self.source_paths)} 个文件；文件总量 {_format_bytes(total)}；"
            "预计新增空间将在内容核验后确定。"
        )
        self.start_button.setEnabled(bool(self.source_paths))

    def start_import(self) -> None:
        if self._operation_handle is not None or not self.start_button.isEnabled():
            return
        pipeline = getattr(self.services, "import_parse_pipeline", None)
        request_factory = getattr(self.services, "create_import_request", None)
        if pipeline is None or request_factory is None:
            self.progress_status_label.setText("当前环境无法启动导入。")
            return
        try:
            request = request_factory(self.source_paths)
            self._operation_handle = pipeline.start(request)
        except Exception:
            self.progress_status_label.setText("导入未启动，现有资料未发生变化。")
            return
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.close_button.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.progress_status_label.setText("正在创建本地不可变副本并解析…")
        self._poll_timer.start()

    def cancel_import(self) -> None:
        if self._operation_handle is None or self._operation_handle.done:
            return
        self._operation_handle.cancel()
        self.cancel_button.setEnabled(False)
        self.progress_status_label.setText("正在安全取消…")

    def refresh_operation_state(self) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("UI_UPDATE_OUTSIDE_QT_THREAD")
        handle = self._operation_handle
        if handle is None or not handle.done:
            return
        self._poll_timer.stop()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        labels = {
            "completed": "导入与解析已完成。",
            "completed_with_failures": "导入完成，部分文件处理失败。",
            "failed": "导入失败，现有资料未发生变化。",
            "cancelled": "导入已取消。",
        }
        self.progress_status_label.setText(
            labels.get(handle.status, "导入已安全结束。")
        )
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)
