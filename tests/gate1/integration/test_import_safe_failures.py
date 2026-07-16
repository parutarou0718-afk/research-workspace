from __future__ import annotations

from pathlib import Path

import pytest

from research_workspace.infrastructure.filesystem import stability
from research_workspace.infrastructure.filesystem.path_safety import SourceFailure
from research_workspace.infrastructure.filesystem.stability import stream_stable_copy


def test_source_change_during_copy_commits_nothing(
    safe_source: Path, tmp_path: Path, mutate_after_first_chunk
) -> None:
    staging = tmp_path / "staging" / "source.partial"

    with pytest.raises(SourceFailure, match="SOURCE_CHANGED_DURING_IMPORT"):
        stream_stable_copy(
            safe_source,
            staging,
            chunk_size=32,
            after_chunk=mutate_after_first_chunk(safe_source),
        )

    assert not staging.exists()


def test_busy_or_read_failure_removes_partial_staging(safe_source: Path, tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "source.partial"

    def fail_after_chunk() -> None:
        raise PermissionError("sharing violation")

    with pytest.raises(SourceFailure, match="SOURCE_BUSY"):
        stream_stable_copy(safe_source, staging, chunk_size=32, after_chunk=fail_after_chunk)
    assert not staging.exists()


def test_staging_hash_mismatch_is_safe_failure(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging" / "source.partial"
    monkeypatch.setattr(stability, "sha256_file", lambda path: "0" * 64)

    with pytest.raises(SourceFailure, match="SNAPSHOT_HASH_MISMATCH"):
        stream_stable_copy(safe_source, staging)
    assert not staging.exists()


def test_existing_partial_staging_is_not_overwritten(safe_source: Path, tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "source.partial"
    staging.parent.mkdir()
    staging.write_bytes(b"unknown-existing-partial")

    with pytest.raises(SourceFailure, match="STAGING_TARGET_EXISTS"):
        stream_stable_copy(safe_source, staging)
    assert staging.read_bytes() == b"unknown-existing-partial"


def test_cleanup_failure_preserves_stable_error_and_incomplete_visibility(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging" / "source.partial"
    real_unlink = Path.unlink

    def deny_staging_cleanup(path: Path, *args, **kwargs):
        if path == staging:
            raise PermissionError("staging cleanup temporarily blocked")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_staging_cleanup)

    def fail_after_chunk() -> None:
        raise PermissionError("source sharing violation")

    with pytest.raises(SourceFailure, match="SOURCE_BUSY"):
        stream_stable_copy(safe_source, staging, chunk_size=32, after_chunk=fail_after_chunk)
    assert staging.exists()
    assert staging.suffix == ".partial"


def test_parent_identity_change_during_copy_is_rejected(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging" / "source.partial"
    original = stability._parent_identity(safe_source.parent)
    calls = 0

    def changing_parent(path: Path):
        nonlocal calls
        calls += 1
        return original if calls == 1 else (original[0], original[1] + 1)

    monkeypatch.setattr(stability, "_parent_identity", changing_parent)
    with pytest.raises(SourceFailure, match="SOURCE_CHANGED_DURING_IMPORT"):
        stream_stable_copy(safe_source, staging)
    assert not staging.exists()


def test_open_handle_final_path_redirection_is_rejected(
    safe_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging" / "source.partial"
    redirected = tmp_path / "outside" / "paper.pdf"
    redirected.parent.mkdir()
    redirected.write_bytes(safe_source.read_bytes())
    monkeypatch.setattr(stability, "_opened_final_path", lambda stream, expected: redirected)

    with pytest.raises(SourceFailure, match="SOURCE_PATH_UNSAFE"):
        stream_stable_copy(safe_source, staging)
    assert not staging.exists()
