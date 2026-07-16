"""Stable streamed copying without changing the external source."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import os
from pathlib import Path

from research_workspace.domain.import_model import FileStat, StagedSource
from research_workspace.infrastructure.filesystem.atomic_files import fsync_parent_directory
from research_workspace.infrastructure.filesystem.path_safety import (
    SourceFailure,
    _windows_final_path_from_handle,
    normalize_path_text,
    reject_reparse_chain,
)


def _to_file_stat(details: os.stat_result) -> FileStat:
    inode = getattr(details, "st_ino", None)
    device = getattr(details, "st_dev", None)
    return FileStat(
        size_bytes=details.st_size,
        modified_time_ns=details.st_mtime_ns,
        file_id_hint=str(inode) if inode not in {None, 0} else None,
        volume_serial_hint=str(device) if device is not None else None,
    )


def _stat_path(path: Path) -> FileStat:
    return _to_file_stat(os.stat(path, follow_symlinks=False))


def _parent_identity(path: Path) -> tuple[int, int]:
    details = os.stat(path, follow_symlinks=False)
    return (details.st_dev, details.st_ino)


def _opened_final_path(stream, expected: Path) -> Path:
    if os.name == "nt":
        import msvcrt

        return _windows_final_path_from_handle(msvcrt.get_osfhandle(stream.fileno()))
    return expected.resolve(strict=True)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_identity(pre: FileStat, opened: FileStat, post: FileStat) -> bool:
    if pre.size_bytes != opened.size_bytes or pre.modified_time_ns != opened.modified_time_ns:
        return False
    if post.size_bytes != opened.size_bytes or post.modified_time_ns != opened.modified_time_ns:
        return False
    if opened.file_id_hint is not None:
        return pre.file_id_hint == opened.file_id_hint == post.file_id_hint
    return True


def _cleanup_partial_staging(staging: Path) -> None:
    try:
        staging.unlink(missing_ok=True)
    except OSError:
        # The operation remains failed and this file stays explicitly incomplete;
        # no caller receives a StagedSource that could be promoted or registered.
        pass


def stream_stable_copy(
    source: Path,
    staging: Path,
    *,
    chunk_size: int = 1024 * 1024,
    after_chunk: Callable[[], None] | None = None,
) -> StagedSource:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    reject_reparse_chain(source)
    staging.parent.mkdir(parents=True, exist_ok=True)
    if staging.exists() or staging.is_symlink():
        raise SourceFailure("STAGING_TARGET_EXISTS")

    created_staging = False
    try:
        pre_stat = _stat_path(source)
        parent_before = _parent_identity(source.parent)
        digest = hashlib.sha256()
        copied_size = 0
        with source.open("rb") as source_stream:
            if normalize_path_text(_opened_final_path(source_stream, source)) != normalize_path_text(source):
                raise SourceFailure("SOURCE_PATH_UNSAFE")
            opened_stat = _to_file_stat(os.fstat(source_stream.fileno()))
            if not _stable_identity(pre_stat, opened_stat, opened_stat):
                raise SourceFailure("SOURCE_CHANGED_DURING_IMPORT")
            with staging.open("xb") as staged_stream:
                created_staging = True
                while chunk := source_stream.read(chunk_size):
                    staged_stream.write(chunk)
                    digest.update(chunk)
                    copied_size += len(chunk)
                    if after_chunk is not None:
                        after_chunk()
                staged_stream.flush()
                os.fsync(staged_stream.fileno())
            opened_after = _to_file_stat(os.fstat(source_stream.fileno()))
        fsync_parent_directory(staging.parent)
        post_stat = _stat_path(source)
        parent_after = _parent_identity(source.parent)
        if parent_before != parent_after or not _stable_identity(pre_stat, opened_after, post_stat):
            raise SourceFailure("SOURCE_CHANGED_DURING_IMPORT")

        copied_sha256 = digest.hexdigest()
        if staging.stat().st_size != copied_size or sha256_file(staging) != copied_sha256:
            raise SourceFailure("SNAPSHOT_HASH_MISMATCH")
        if opened_after.file_id_hint is None and sha256_file(source) != copied_sha256:
            raise SourceFailure("SOURCE_CHANGED_DURING_IMPORT")
        return StagedSource(source, staging, copied_sha256, copied_size, pre_stat, post_stat)
    except SourceFailure:
        if created_staging:
            _cleanup_partial_staging(staging)
        raise
    except (OSError, PermissionError) as exc:
        if created_staging:
            _cleanup_partial_staging(staging)
        raise SourceFailure("SOURCE_BUSY") from exc
