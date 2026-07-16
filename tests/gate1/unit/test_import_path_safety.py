from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import unicodedata
from uuid import UUID

import pytest

from research_workspace.domain.capabilities import PathScope
from research_workspace.infrastructure.filesystem import path_safety
from research_workspace.infrastructure.filesystem.path_safety import (
    SourceFailure,
    normalize_path_text,
    normalized_path_hash,
    resolve_safe_external_source,
)


ROOT_ID = UUID("50000000-0000-0000-0000-000000000001")


def scope_for(path: Path, *, recursive: bool = False) -> PathScope:
    return PathScope(
        "import_source",
        normalized_path_hash(path),
        ROOT_ID,
        "copy",
        recursive,
    )


def test_recursive_scope_uses_resolved_ancestor_identity_not_string_prefix(tmp_path: Path) -> None:
    allowed = tmp_path / "Research"
    source = allowed / "papers" / "draft.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"approved")
    sibling = tmp_path / "Research-Other" / "draft.pdf"
    sibling.parent.mkdir()
    sibling.write_bytes(b"not approved")
    scope = scope_for(allowed, recursive=True)

    assert resolve_safe_external_source(source, scope, tmp_path / "workspace") == source.resolve()
    with pytest.raises(SourceFailure, match="SOURCE_PATH_UNSAFE"):
        resolve_safe_external_source(sibling, scope, tmp_path / "workspace")


@pytest.mark.parametrize(
    "internal", ["sources", "derived", "staging", "recovery", "exports", "backups"]
)
def test_workspace_internal_roots_are_rejected(tmp_path: Path, internal: str) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / internal / "x.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"internal")

    with pytest.raises(SourceFailure, match="SOURCE_PATH_UNSAFE"):
        resolve_safe_external_source(source, scope_for(source), workspace)


def test_symlink_source_is_rejected_before_final_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.pdf"
    target.write_bytes(b"target")
    link = tmp_path / "linked.pdf"
    try:
        link.symlink_to(target)
    except OSError:
        link.write_bytes(b"simulated-link-entry")
        monkeypatch.setattr(path_safety, "_has_reparse_attribute", lambda path: path == link)

    with pytest.raises(SourceFailure, match="SOURCE_REPARSE_POINT"):
        resolve_safe_external_source(link, scope_for(link), tmp_path / "workspace")


def test_windows_junction_or_reparse_attribute_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "junction-target"
    target.mkdir()
    (target / "child.pdf").write_bytes(b"content")
    junction = tmp_path / "junction"
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        check=False,
    ).returncode == 0
    if os.name == "nt":
        assert created, "Windows junction fixture must be real"
    if created:
        source = junction / "child.pdf"
    else:
        source = tmp_path / "simulated-junction-child.pdf"
        source.write_bytes(b"content")
        monkeypatch.setattr(path_safety, "_has_reparse_attribute", lambda path: path == source)

    with pytest.raises(SourceFailure, match="SOURCE_REPARSE_POINT"):
        resolve_safe_external_source(source, scope_for(source), tmp_path / "workspace")


def test_normalized_path_identity_is_nfc_and_case_insensitive() -> None:
    composed = "C:\\Research\\R\u00e9sum\u00e9.pdf"
    decomposed = unicodedata.normalize("NFD", composed).upper()

    assert normalize_path_text(composed) == normalize_path_text(decomposed)
    assert hashlib.sha256(normalize_path_text(composed).encode("utf-8")).hexdigest() == hashlib.sha256(
        normalize_path_text(decomposed).encode("utf-8")
    ).hexdigest()


def test_authorization_uses_final_resolved_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = tmp_path / "approved.pdf"
    approved.write_bytes(b"approved")
    redirected = tmp_path / "outside" / "redirected.pdf"
    redirected.parent.mkdir()
    redirected.write_bytes(b"redirected")
    scope = scope_for(approved)
    monkeypatch.setattr(path_safety, "_resolve_final_path", lambda path: redirected.resolve())

    with pytest.raises(SourceFailure, match="SOURCE_PATH_UNSAFE"):
        resolve_safe_external_source(approved, scope, tmp_path / "workspace")
