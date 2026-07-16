from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from research_workspace import bootstrap
from research_workspace.infrastructure.filesystem import atomic_files
from research_workspace.infrastructure.filesystem.atomic_files import (
    PromotionFailure,
    PromotionState,
    ensure_same_volume,
    fsync_file_and_parent,
    promote_no_replace,
    verify_promotion_outcome,
)
from research_workspace.infrastructure.filesystem.path_safety import SourceFailure
from research_workspace.infrastructure.filesystem.stability import stream_stable_copy


def staged_source(safe_source: Path, tmp_path: Path):
    return stream_stable_copy(safe_source, tmp_path / "staging" / "source.partial")


def test_stable_copy_streams_hashes_flushes_and_verifies(safe_source: Path, tmp_path: Path) -> None:
    staged = staged_source(safe_source, tmp_path)

    assert staged.staging_path.read_bytes() == safe_source.read_bytes()
    assert staged.sha256 == hashlib.sha256(safe_source.read_bytes()).hexdigest()
    assert staged.size_bytes == safe_source.stat().st_size
    assert staged.pre_stat == staged.post_stat


def test_file_and_supported_parent_directory_are_fsynced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"durable")
    real_fsync = os.fsync
    calls: list[int] = []

    def recording_fsync(fd: int) -> None:
        calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(atomic_files.os, "fsync", recording_fsync)
    monkeypatch.setattr(
        atomic_files,
        "_open_directory_for_flush",
        lambda path: os.open(target, os.O_RDWR),
    )
    result = fsync_file_and_parent(target)

    assert result.file_flushed is True
    assert len(calls) == 2
    assert result.directory_flush_supported is True
    assert result.directory_flushed is True


def test_unsupported_parent_directory_flush_is_reported_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"durable")
    monkeypatch.setattr(atomic_files, "_open_directory_for_flush", lambda path: (_ for _ in ()).throw(OSError("unsupported")))

    result = fsync_file_and_parent(target)

    assert result.file_flushed is True
    assert result.directory_flush_supported is False
    assert result.directory_flushed is False


def test_same_volume_is_required_before_promotion(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"
    monkeypatch.setattr(
        atomic_files,
        "_volume_identity",
        lambda path: "staging-volume" if path == staged.staging_path else "sources-volume",
    )

    with pytest.raises(PromotionFailure, match="SNAPSHOT_CROSS_VOLUME"):
        ensure_same_volume(staged.staging_path, final.parent)


def test_promotion_never_overwrites_existing_final(safe_source: Path, tmp_path: Path) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"
    final.parent.mkdir()
    final.write_bytes(b"existing")

    with pytest.raises(PromotionFailure, match="SNAPSHOT_TARGET_EXISTS"):
        promote_no_replace(staged, final)
    assert final.read_bytes() == b"existing"
    assert staged.staging_path.exists()


def test_successful_no_replace_promotion_removes_staging(safe_source: Path, tmp_path: Path) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"

    outcome = promote_no_replace(staged, final)

    assert outcome.state is PromotionState.COMPLETED
    assert final.read_bytes() == safe_source.read_bytes()
    assert not staged.staging_path.exists()


def test_exception_after_successful_promotion_is_verified_not_retried(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"

    def promote_then_raise(source: Path, destination: Path) -> None:
        os.rename(source, destination)
        raise OSError("outcome unknown")

    monkeypatch.setattr(atomic_files, "_promote_path_no_replace", promote_then_raise)
    outcome = promote_no_replace(staged, final)

    assert outcome.state is PromotionState.COMPLETED
    assert final.exists()
    assert not staged.staging_path.exists()


def test_unknown_promotion_with_both_matching_paths_requires_resume_verification(
    safe_source: Path, tmp_path: Path
) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"
    final.parent.mkdir()
    os.link(staged.staging_path, final)

    outcome = verify_promotion_outcome(staged, final)

    assert outcome.state is PromotionState.RESUME_VERIFICATION


def test_unknown_promotion_with_mismatched_final_requires_manual_attention(
    safe_source: Path, tmp_path: Path
) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"
    final.parent.mkdir()
    final.write_bytes(b"wrong content")

    outcome = verify_promotion_outcome(staged, final)

    assert outcome.state is PromotionState.MANUAL_ATTENTION_REQUIRED


def test_parent_identity_change_during_promotion_is_not_reported_completed(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"
    final.parent.mkdir()
    original = atomic_files._directory_identity(final.parent)
    calls = 0

    def changing_identity(path: Path):
        nonlocal calls
        calls += 1
        return original if calls == 1 else (original[0], original[1] + 1)

    monkeypatch.setattr(atomic_files, "_directory_identity", changing_identity)
    outcome = promote_no_replace(staged, final)

    assert outcome.state is PromotionState.MANUAL_ATTENTION_REQUIRED


def test_unknown_outcome_rejects_parent_that_became_reparse(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_source(safe_source, tmp_path)
    final = tmp_path / "sources" / "content"
    final.parent.mkdir()
    os.rename(staged.staging_path, final)
    monkeypatch.setattr(
        atomic_files,
        "reject_reparse_chain",
        lambda path: (_ for _ in ()).throw(SourceFailure("SOURCE_REPARSE_POINT")),
    )

    outcome = verify_promotion_outcome(staged, final)

    assert outcome.state is PromotionState.MANUAL_ATTENTION_REQUIRED


def test_bootstrap_creates_only_approved_data_directory_skeleton(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    bootstrap._ensure_data_layout(workspace)

    actual = {
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_dir()
    }
    assert actual == {
        "sources", "sources/sha256",
        "derived", "derived/parse",
        "staging", "staging/imports", "staging/parse", "staging/backup",
        "staging/export", "staging/restore",
        "recovery", "recovery/current", "recovery/previous",
        "exports", "backups", "logs",
    }
    assert not any(path.is_file() for path in workspace.rglob("*"))
