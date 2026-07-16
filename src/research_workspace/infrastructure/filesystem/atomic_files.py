"""Durable flush and no-replace same-volume promotion primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import stat

from research_workspace.domain.import_model import StagedSource
from research_workspace.infrastructure.filesystem.path_safety import SourceFailure, reject_reparse_chain


class PromotionFailure(RuntimeError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


class PromotionState(str, Enum):
    COMPLETED = "completed"
    RESUME_VERIFICATION = "resume_verification"
    SAFE_CLEANUP = "safe_cleanup"
    MANUAL_ATTENTION_REQUIRED = "manual_attention_required"


@dataclass(frozen=True)
class FlushResult:
    file_flushed: bool
    directory_flush_supported: bool
    directory_flushed: bool


@dataclass(frozen=True)
class PromotionOutcome:
    state: PromotionState
    final_path: Path
    staging_exists: bool
    final_exists: bool


def _open_directory_for_flush(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    return os.open(path, flags)


def fsync_parent_directory(path: Path) -> bool:
    try:
        descriptor = _open_directory_for_flush(path)
    except OSError:
        return False
    try:
        os.fsync(descriptor)
    except OSError:
        return False
    finally:
        os.close(descriptor)
    return True


def fsync_file_and_parent(path: Path) -> FlushResult:
    # Windows requires a writable descriptor for FlushFileBuffers/os.fsync.
    # r+b does not truncate or change the committed bytes.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())
    directory_flushed = fsync_parent_directory(path.parent)
    return FlushResult(True, directory_flushed, directory_flushed)


def _volume_identity(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_dev


def _directory_identity(path: Path) -> tuple[int, int]:
    details = os.stat(path, follow_symlinks=False)
    return (details.st_dev, details.st_ino)


def ensure_same_volume(staging: Path, final_parent: Path) -> None:
    if _volume_identity(staging) != _volume_identity(final_parent):
        raise PromotionFailure("SNAPSHOT_CROSS_VOLUME")


def _promote_path_no_replace(staging: Path, final: Path) -> None:
    if os.name == "nt":
        os.rename(staging, final)
        return
    os.link(staging, final)
    os.unlink(staging)


def _ordinary_matching_file(path: Path, staged: StagedSource) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if not stat.S_ISREG(details.st_mode) or path.is_symlink() or attributes & reparse_flag:
        return False
    if details.st_size != staged.size_bytes:
        return False
    from research_workspace.infrastructure.filesystem.stability import sha256_file

    return sha256_file(path) == staged.sha256


def verify_promotion_outcome(staged: StagedSource, final: Path) -> PromotionOutcome:
    try:
        reject_reparse_chain(final.parent)
    except SourceFailure:
        return PromotionOutcome(
            PromotionState.MANUAL_ATTENTION_REQUIRED,
            final,
            staged.staging_path.exists(),
            final.exists(),
        )
    staging_exists = staged.staging_path.exists()
    final_exists = final.exists()
    final_matches = final_exists and _ordinary_matching_file(final, staged)
    staging_matches = staging_exists and _ordinary_matching_file(staged.staging_path, staged)

    if final_matches and not staging_exists:
        state = PromotionState.COMPLETED
    elif final_matches and staging_matches:
        state = PromotionState.RESUME_VERIFICATION
    elif not final_exists and staging_matches:
        state = PromotionState.SAFE_CLEANUP
    else:
        state = PromotionState.MANUAL_ATTENTION_REQUIRED
    return PromotionOutcome(state, final, staging_exists, final_exists)


def promote_no_replace(staged: StagedSource, final: Path) -> PromotionOutcome:
    reject_reparse_chain(staged.staging_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    reject_reparse_chain(final.parent)
    parent_identity = _directory_identity(final.parent)
    ensure_same_volume(staged.staging_path, final.parent)
    if final.exists() or final.is_symlink():
        raise PromotionFailure("SNAPSHOT_TARGET_EXISTS")
    if not _ordinary_matching_file(staged.staging_path, staged):
        raise PromotionFailure("SNAPSHOT_HASH_MISMATCH")

    try:
        _promote_path_no_replace(staged.staging_path, final)
    except FileExistsError as exc:
        raise PromotionFailure("SNAPSHOT_TARGET_EXISTS") from exc
    except OSError:
        outcome = verify_promotion_outcome(staged, final)
    else:
        fsync_parent_directory(final.parent)
        outcome = verify_promotion_outcome(staged, final)
    try:
        parent_unchanged = _directory_identity(final.parent) == parent_identity
    except OSError:
        parent_unchanged = False
    if not parent_unchanged:
        return PromotionOutcome(
            PromotionState.MANUAL_ATTENTION_REQUIRED,
            final,
            staged.staging_path.exists(),
            final.exists(),
        )
    return outcome
