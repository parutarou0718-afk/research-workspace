"""Final-path authorization and link/reparse rejection."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import unicodedata

from research_workspace.domain.capabilities import PathScope


class SourceFailure(RuntimeError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


def normalize_path_text(path: str | os.PathLike[str]) -> str:
    absolute = os.path.abspath(os.path.normpath(os.fspath(path)))
    return unicodedata.normalize("NFC", os.path.normcase(absolute)).casefold()


def _strip_windows_extended_prefix(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def _windows_final_path_from_handle(handle: int) -> Path:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_final_path(handle, buffer, len(buffer), 0)
    if length == 0 or length >= len(buffer):
        raise OSError(ctypes.get_last_error(), "cannot resolve final Windows path")
    return Path(_strip_windows_extended_prefix(buffer.value))


def _resolve_final_path(path: Path) -> Path:
    if os.name != "nt":
        return path.resolve(strict=True)

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x02000000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise OSError(ctypes.get_last_error(), "cannot open path for final resolution")
    try:
        return _windows_final_path_from_handle(handle)
    finally:
        kernel32.CloseHandle(handle)


def normalized_path_hash(path: str | os.PathLike[str]) -> str:
    candidate = Path(path).expanduser()
    try:
        candidate = _resolve_final_path(candidate)
    except OSError:
        candidate = candidate.resolve(strict=False)
    return hashlib.sha256(normalize_path_text(candidate).encode("utf-8")).hexdigest()


def _has_reparse_attribute(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _lexical_components(path: Path) -> tuple[Path, ...]:
    absolute = Path(os.path.abspath(path.expanduser()))
    components: list[Path] = []
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        components.append(current)
    return tuple(components)


def reject_reparse_chain(path: Path) -> None:
    for component in _lexical_components(path):
        if component.exists() or component.is_symlink():
            if _has_reparse_attribute(component):
                raise SourceFailure("SOURCE_REPARSE_POINT")


def _identity_parts(path: Path) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in path.parts)


def _is_within(candidate: Path, root: Path) -> bool:
    candidate_parts = _identity_parts(candidate)
    root_parts = _identity_parts(root)
    return len(candidate_parts) >= len(root_parts) and candidate_parts[: len(root_parts)] == root_parts


def _scope_allows(candidate: Path, scope: PathScope) -> bool:
    if scope.scope_type != "import_source" or scope.access_mode not in {"read", "copy"}:
        return False
    if not scope.recursive:
        return normalized_path_hash(candidate) == scope.normalized_path_hash
    return any(
        normalized_path_hash(parent) == scope.normalized_path_hash
        for parent in (candidate, *candidate.parents)
    )


def resolve_safe_external_source(
    source: Path,
    allowed_scope: PathScope,
    workspace_root: Path,
) -> Path:
    lexical_source = Path(os.path.abspath(source.expanduser()))
    reject_reparse_chain(lexical_source)
    try:
        final_source = _resolve_final_path(lexical_source)
    except (OSError, RuntimeError) as exc:
        raise SourceFailure("SOURCE_PATH_UNSAFE") from exc
    if not final_source.is_file() or _has_reparse_attribute(final_source):
        raise SourceFailure("SOURCE_PATH_UNSAFE")

    final_workspace = workspace_root.expanduser().resolve(strict=False)
    if _is_within(final_source, final_workspace):
        raise SourceFailure("SOURCE_PATH_UNSAFE")
    if not _scope_allows(final_source, allowed_scope):
        raise SourceFailure("SOURCE_PATH_UNSAFE")
    return final_source
