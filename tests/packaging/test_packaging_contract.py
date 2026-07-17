from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packaging" / "windows" / "research_workspace.spec"
BUILD_SCRIPT = ROOT / "packaging" / "windows" / "build_portable.ps1"
MANIFEST_SCRIPT = ROOT / "packaging" / "windows" / "build_manifest.py"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing packaging contract: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _manifest_module():
    spec = importlib.util.spec_from_file_location(
        "portable_build_manifest", MANIFEST_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_spec_is_windowed_onedir_without_upx_or_test_driver_collection() -> None:
    text = _text(SPEC)

    assert "app.py" in text
    assert 'name="ResearchWorkspace"' in text
    assert "console=False" in text
    assert "upx=False" in text
    assert 'contents_directory="src"' in text
    assert "COLLECT(" in text
    assert "collect_all(" not in text
    assert '"pywinauto"' in text
    assert '"comtypes"' in text
    assert "excludes=" in text


def test_spec_collects_only_approved_runtime_resources() -> None:
    text = _text(SPEC)

    assert "research_workspace/presentation/ui" in text
    assert "RW_PORTABLE_ICON" in text
    assert '"logging.config"' in text
    assert "RW_DIAGNOSTIC" not in text
    assert "tests/gate1/fixtures" not in text
    assert "network" not in text.casefold()


def test_build_script_is_external_clean_and_gate3_exact() -> None:
    text = _text(BUILD_SCRIPT)

    assert "v0.2-personal" in text
    assert "fe8e38bfa88a1a7c7282d46fbd42e9da97af2c43" in text
    assert "0004_gate3_protected_crud.py" in text
    assert "status --porcelain" in text
    assert "Resolve-Path" in text
    assert "Compress-Archive" in text
    assert "BUILD-MANIFEST.json" in text
    assert "THIRD_PARTY_NOTICES.md" in text
    assert "pywinauto" not in text.casefold()


def test_manifest_uses_only_relative_paths_and_stable_file_facts(tmp_path) -> None:
    package = tmp_path / "package"
    app = package / "app"
    app.mkdir(parents=True)
    (app / "ResearchWorkspace.exe").write_bytes(b"portable")
    (app / "src").mkdir()
    (app / "src" / "runtime.bin").write_bytes(b"runtime")

    module = _manifest_module()
    output = module.write_manifest(
        package,
        product_tag="v0.2-personal",
        product_commit="fe8e38bfa88a1a7c7282d46fbd42e9da97af2c43",
        build_commit="1" * 40,
    )

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert manifest["product_tag"] == "v0.2-personal"
    assert manifest["product_commit"] == (
        "fe8e38bfa88a1a7c7282d46fbd42e9da97af2c43"
    )
    assert [item["path"] for item in manifest["files"]] == [
        "app/ResearchWorkspace.exe",
        "app/src/runtime.bin",
    ]
    assert all(not Path(item["path"]).is_absolute() for item in manifest["files"])
    assert (package / "BUILD-MANIFEST.sha256").is_file()
