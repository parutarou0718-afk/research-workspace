"""Gate 1 import page controller."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QScrollArea, QTableWidget

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.import_batch_dialog import ImportBatchDialog
from research_workspace.presentation.view_models.imports import ImportsViewModel


class ImportsPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("imports_page.ui")
        self.scroll_area = require_child(
            self.widget, QScrollArea, "importsScrollArea"
        )
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.select_button = require_child(
            self.widget, QPushButton, "selectImportFilesButton"
        )
        self.imports_table = require_child(
            self.widget, QTableWidget, "recentImportsTable"
        )
        self.select_button.clicked.connect(self.select_files)
        self.refresh()

    def select_files(self) -> None:
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self.widget,
            "选择研究文件",
            "",
            "研究文件 (*.docx *.pdf *.pptx)",
        )
        if not paths:
            return
        dialog = ImportBatchDialog(
            services=self.services,
            source_paths=tuple(paths),
            parent=self.widget,
        )
        dialog.exec()
        self.refresh()

    def refresh(self) -> None:
        query = getattr(self.services, "get_imports", None)
        view_model = query.execute() if query is not None else ImportsViewModel(())
        self.render(view_model)

    def render(self, view_model: ImportsViewModel) -> None:
        self.imports_table.setRowCount(len(view_model.rows))
        from PySide6.QtWidgets import QTableWidgetItem

        for row_index, row in enumerate(view_model.rows):
            self.imports_table.setItem(row_index, 0, QTableWidgetItem(row.filename))
            self.imports_table.setItem(row_index, 1, QTableWidgetItem(row.status))
