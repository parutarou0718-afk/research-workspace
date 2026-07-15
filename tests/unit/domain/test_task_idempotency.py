"""Pure idempotency and file-effect recovery policy tests."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from research_workspace.domain.tasks import (
    FileEffectRecoveryAction,
    decide_file_effect_recovery,
    task_effect_operation_key,
    task_request_fingerprint,
)


def test_fingerprint_ignores_transport_fields_and_input_order(valid_task):
    task_contract = deepcopy(valid_task)
    task_contract["input_refs"] = [
        {"ref_type": "Z", "ref_id": "2"},
        {"ref_type": "A", "ref_id": "1"},
    ]
    replay = deepcopy(task_contract)
    replay["task_id"] = str(uuid4())
    replay["created_at"] = "2026-07-17T00:00:00Z"
    replay["correlation_id"] = str(uuid4())
    replay["idempotency_key"] = "another-transport-key"
    replay["input_refs"] = list(reversed(replay["input_refs"]))

    assert task_request_fingerprint(replay) == task_request_fingerprint(task_contract)
    assert task_request_fingerprint(task_contract) == (
        "edbac725cc4f59d747d43d3754b95fd7e0e1c624a20e65c0c6ea5c9a77ad3724"
    )


def test_fingerprint_keeps_semantic_fields(valid_task):
    changed = deepcopy(valid_task)
    changed["options"]["dry_run"] = True

    assert task_request_fingerprint(changed) != task_request_fingerprint(valid_task)


def test_fingerprint_does_not_mutate_the_request(valid_task):
    original = deepcopy(valid_task)

    task_request_fingerprint(valid_task)

    assert valid_task == original


def test_effect_operation_key_uses_exact_canonical_identity():
    assert task_effect_operation_key(
        task_id="123e4567-e89b-12d3-a456-426614174000",
        executor_id="executor-a",
        effect_type="file.write",
        output_type="export",
        output_identity="report.pdf",
    ) == "c1719f8dab7d028e717161b17262e6b51ead9f844a62207952738641fb8e1059"


def test_committed_file_effect_returns_existing_output():
    decision = decide_file_effect_recovery(
        committed=True,
        staging_exists=False,
        staging_sha256=None,
        final_exists=False,
        final_sha256=None,
        expected_sha256="a" * 64,
    )

    assert decision.action is FileEffectRecoveryAction.RETURN_COMMITTED
    assert decision.retryable is False


def test_prepared_effect_with_verified_final_is_committed():
    decision = decide_file_effect_recovery(
        committed=False,
        staging_exists=True,
        staging_sha256="b" * 64,
        final_exists=True,
        final_sha256="a" * 64,
        expected_sha256="a" * 64,
    )

    assert decision.action is FileEffectRecoveryAction.COMMIT_FINAL


def test_prepared_effect_with_verified_staging_is_promoted():
    decision = decide_file_effect_recovery(
        committed=False,
        staging_exists=True,
        staging_sha256="a" * 64,
        final_exists=False,
        final_sha256=None,
        expected_sha256="a" * 64,
    )

    assert decision.action is FileEffectRecoveryAction.PROMOTE_STAGING


def test_prepared_effect_without_a_verified_file_is_retryable():
    decision = decide_file_effect_recovery(
        committed=False,
        staging_exists=True,
        staging_sha256="b" * 64,
        final_exists=True,
        final_sha256="c" * 64,
        expected_sha256="a" * 64,
    )

    assert decision.action is FileEffectRecoveryAction.RETRYABLE_ERROR
    assert decision.retryable is True
