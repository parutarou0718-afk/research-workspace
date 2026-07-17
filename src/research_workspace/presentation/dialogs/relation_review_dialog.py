"""Designer-owned Gate 3 candidate and formal-relation review."""

import json
from uuid import UUID

from PySide6.QtWidgets import (
    QComboBox, QLabel, QLineEdit, QPushButton, QTextBrowser,
)

from research_workspace.presentation import load_ui_into, require_child
from research_workspace.presentation.dialogs.paper_editor_dialog import (
    ProtectedEditorDialog,
)


class RelationReviewDialog(ProtectedEditorDialog):
    def __init__(self, services, candidate, parent=None) -> None:
        super().__init__(parent)
        self.services, self.candidate = services, candidate
        load_ui_into("relation_review_dialog.ui", self)
        self.evidence = require_child(self, QTextBrowser, "candidateEvidenceText")
        self.paper_id = require_child(self, QLineEdit, "decisionPaperIdEdit")
        self.earlier_label = require_child(self, QLineEdit, "earlierVersionLabelEdit")
        self.later_label = require_child(self, QLineEdit, "laterVersionLabelEdit")
        self.memberships = require_child(self, QComboBox, "membershipCombo")
        self.context_id = require_child(self, QLineEdit, "contextParseEdit")
        self.relations = require_child(self, QComboBox, "formalRelationCombo")
        self.confirm_button = require_child(self, QPushButton, "confirmCandidateButton")
        self.reject_button = require_child(self, QPushButton, "rejectCandidateButton")
        self.reconsider_button = require_child(self, QPushButton, "reconsiderCandidateButton")
        self.set_current_button = require_child(self, QPushButton, "setCurrentVersionButton")
        self.change_context_button = require_child(self, QPushButton, "changeVersionContextButton")
        self.retract_version_button = require_child(self, QPushButton, "retractVersionButton")
        self.retract_relation_button = require_child(self, QPushButton, "retractRelationButton")
        close_button = require_child(self, QPushButton, "closeRelationReviewButton")
        recovery = require_child(self, QLabel, "relationRecoveryStatusLabel")
        error = require_child(self, QLabel, "relationErrorLabel")
        self._bind_operation_widgets(self.confirm_button, error)
        self.recovery_status_label = recovery
        self.bundle = services.decision_actions.review(candidate.candidate_id)
        self._load_bundle()
        self.confirm_button.clicked.connect(self.confirm)
        self.reject_button.clicked.connect(self.reject_candidate)
        self.reconsider_button.clicked.connect(self.reconsider)
        self.set_current_button.clicked.connect(self.set_current)
        self.change_context_button.clicked.connect(self.change_context)
        self.retract_version_button.clicked.connect(self.retract_version)
        self.retract_relation_button.clicked.connect(self.retract_relation)
        close_button.clicked.connect(self.reject)

    def _load_bundle(self) -> None:
        value = {
            "candidate_id": str(self.bundle.candidate_id),
            "detector": f"{self.bundle.detector_id} {self.bundle.detector_version}",
            "rule_id": self.bundle.rule_id,
            "earlier_snapshot_id": str(self.bundle.earlier_snapshot_id),
            "later_snapshot_id": str(self.bundle.later_snapshot_id),
            "direction_rationale": json.loads(self.bundle.direction_rationale),
            "signals": json.loads(self.bundle.signals),
        }
        self.evidence.setPlainText(json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True))
        self.memberships.addItems(map(str, self.bundle.existing_memberships))
        self.relations.addItems(map(str, self.bundle.existing_relation_ids))
        pending = self.candidate.status == "pending"
        rejected = self.candidate.status == "rejected"
        self.confirm_button.setEnabled(pending)
        self.reject_button.setEnabled(pending)
        self.reconsider_button.setEnabled(rejected)
        has_version = bool(self.memberships.count())
        has_relation = bool(self.relations.count())
        for button in (
            self.set_current_button, self.change_context_button,
            self.retract_version_button,
        ):
            button.setEnabled(has_version)
        self.retract_relation_button.setEnabled(has_relation)

    def _start(self, action, *values) -> None:
        self.recovery_status_label.setText("正在创建安全恢复点")
        self.confirm_button.setEnabled(False)
        try:
            handle = getattr(self.services.decision_actions, action)(*values)
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.confirm_button.setEnabled(True)
            return
        self._track(handle)

    def confirm(self) -> None:
        self._start(
            "confirm_candidate", self.candidate.candidate_id,
            UUID(self.paper_id.text()), self.earlier_label.text(),
            self.later_label.text(),
        )

    def reject_candidate(self) -> None:
        self._start("reject_candidate", self.candidate.candidate_id)

    def reconsider(self) -> None:
        self._start("reconsider_candidate", self.candidate.candidate_id)

    def _membership_id(self) -> UUID:
        return UUID(self.memberships.currentText())

    def set_current(self) -> None:
        self._start("set_current_version", self._membership_id())

    def change_context(self) -> None:
        value = self.context_id.text().strip()
        self._start(
            "change_version_context", self._membership_id(),
            UUID(value) if value else None,
        )

    def retract_version(self) -> None:
        self._start("retract_version", self._membership_id())

    def retract_relation(self) -> None:
        self._start("retract_relation", UUID(self.relations.currentText()))
