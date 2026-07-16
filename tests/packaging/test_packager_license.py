from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGING_DIRECT = frozenset({"pyinstaller", "pywinauto"})
LOCK_SHA256 = "2dcb4d6b779367523362865978adedc030004373bc8ae7994fd57be2edef5522"
WINDOWS_EFFECTIVE_CLOSURE = frozenset(
    {
        "altgraph",
        "comtypes",
        "packaging",
        "pefile",
        "pyinstaller",
        "pyinstaller-hooks-contrib",
        "pywin32",
        "pywin32-ctypes",
        "pywinauto",
        "setuptools",
        "six",
    }
)


def _license_policy_module():
    path = ROOT / "tests" / "acceptance" / "test_license_policy.py"
    spec = importlib.util.spec_from_file_location("commercial_license_policy", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonicalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _locked_packages() -> dict[str, dict[str, object]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        _canonicalize(str(package["name"])): package
        for package in lock["package"]
        if _canonicalize(str(package["name"])) != "research-workspace"
    }


def _dependency_names(package: dict[str, object]) -> frozenset[str]:
    dependencies = package.get("dependencies", [])
    assert isinstance(dependencies, list)
    return frozenset(
        _canonicalize(str(dependency["name"]))
        for dependency in dependencies
        if isinstance(dependency, dict) and "name" in dependency
    )


def _packaging_closure(packages: dict[str, dict[str, object]]) -> frozenset[str]:
    pending = list(PACKAGING_DIRECT)
    closure: set[str] = set()
    while pending:
        name = pending.pop()
        assert name in packages, f"approved packaging distribution is not locked: {name}"
        if name in closure:
            continue
        closure.add(name)
        pending.extend(_dependency_names(packages[name]) - closure)
    return frozenset(closure)


def test_packager_and_smoke_driver_are_dev_only_and_exactly_locked() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = {_canonicalize(requirement.split(">", 1)[0]) for requirement in pyproject["project"]["dependencies"]}
    development = {
        _canonicalize(requirement.split(">", 1)[0])
        for requirement in pyproject["dependency-groups"]["dev"]
    }
    packages = _locked_packages()

    assert PACKAGING_DIRECT.isdisjoint(runtime)
    assert PACKAGING_DIRECT <= development
    assert PACKAGING_DIRECT <= set(packages)
    for name in _packaging_closure(packages):
        assert packages[name].get("version"), name
        assert packages[name].get("source"), name


def test_packaging_closure_is_complete_in_third_party_notices() -> None:
    packages = _locked_packages()
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    canonical_notices = _canonicalize(notices)

    for name in _packaging_closure(packages):
        assert name in canonical_notices, name
        assert str(packages[name]["version"]) in notices, name


def test_universal_and_windows_effective_inventories_are_distinct() -> None:
    policy = _license_policy_module()
    universal = policy.universal_lock_inventory()
    windows = policy.effective_dependency_closure(
        roots=PACKAGING_DIRECT,
        target_environment={
            "python_version": "3.12",
            "python_full_version": "3.12.0",
            "implementation_name": "cpython",
            "platform_python_implementation": "CPython",
            "sys_platform": "win32",
            "os_name": "nt",
            "platform_system": "Windows",
            "platform_machine": "AMD64",
        },
    )

    assert set(universal) == set(_locked_packages())
    assert universal["macholib"]["markers"] == ("sys_platform == 'darwin'",)
    assert universal["python-xlib"]["markers"] == ("sys_platform == 'linux'",)
    assert windows == WINDOWS_EFFECTIVE_CLOSURE
    assert "macholib" not in windows
    assert "python-xlib" not in windows


def test_build_tool_exceptions_are_bound_to_exact_lock_version_role_and_license_hash() -> None:
    policy = _license_policy_module()
    exceptions = policy.EXACT_BUILD_TOOL_EXCEPTIONS

    assert policy.uv_lock_sha256() == LOCK_SHA256
    assert exceptions == {
        "pyinstaller": {
            "version": "6.21.0",
            "lock_sha256": LOCK_SHA256,
            "license_sha256": "dcf75fdb959db1e3b41c0f8505069d2ece781b5ec6b3d0a4d30975cfc6580245",
            "license_expression": "GPL-2.0-or-later WITH Bootloader-exception",
            "role": "build_tool",
        },
        "pyinstaller-hooks-contrib": {
            "version": "2026.6",
            "lock_sha256": LOCK_SHA256,
            "license_sha256": "91d0baaff00773038e72c0a1fc9d5d2d38706b7a2b9c04f34296608f931b9cd0",
            "license_expression": "GPL-2.0-or-later",
            "role": "build_standard_hooks_only",
            "distributed_runtime_hook_license": "Apache-2.0",
        },
    }


def test_exact_build_tool_policy_passes_only_the_approved_facts() -> None:
    policy = _license_policy_module()
    rows = [
        {
            "Name": "pyinstaller",
            "Version": "6.21.0",
            "License": "GNU General Public License v2 (GPLv2)",
            "LicenseSHA256": "dcf75fdb959db1e3b41c0f8505069d2ece781b5ec6b3d0a4d30975cfc6580245",
            "Role": "build_tool",
        },
        {
            "Name": "pyinstaller-hooks-contrib",
            "Version": "2026.6",
            "License": "Apache Software License; GNU General Public License v2 (GPLv2)",
            "LicenseSHA256": "91d0baaff00773038e72c0a1fc9d5d2d38706b7a2b9c04f34296608f931b9cd0",
            "Role": "build_standard_hooks_only",
        },
    ]

    assert policy.reviewed_build_tool_violations(rows, LOCK_SHA256) == []
    for field, replacement in (
        ("Name", "other"),
        ("Version", "0"),
        ("LicenseSHA256", "0" * 64),
        ("Role", "runtime"),
    ):
        changed = [dict(row) for row in rows]
        changed[0][field] = replacement
        assert policy.reviewed_build_tool_violations(changed, LOCK_SHA256)
    assert policy.reviewed_build_tool_violations(rows, "0" * 64)


def test_test_driver_is_exactly_test_only_and_runtime_bundle_policy_is_deferred() -> None:
    policy = _license_policy_module()

    assert policy.EXACT_TEST_TOOL_APPROVALS == {
        "pywinauto": {
            "version": "0.6.9",
            "lock_sha256": LOCK_SHA256,
            "license_sha256": "18a999a95b7b23d86c410b4534e44d69f6d8ce13c3a53719b06ab895d8a2e73a",
            "license_expression": "BSD-3-Clause",
            "role": "test_only",
        }
    }
    assert policy.RUNTIME_BUNDLE_PROHIBITED_DISTRIBUTIONS == frozenset(
        {
            "pyinstaller",
            "pyinstaller-hooks-contrib-standard-hooks",
            "pywinauto",
            "comtypes",
            "pywin32",
        }
    )
    assert policy.RUNTIME_BUNDLE_INVENTORY_STATUS == "DEFERRED_TO_PACKAGING_TASK_3"


def test_notices_record_three_inventory_roles_without_claiming_a_runtime_bundle() -> None:
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert f"uv.lock SHA-256: `{LOCK_SHA256}`" in notices
    assert "## A. Universal lock inventory" in notices
    assert "## B. Windows effective build closure" in notices
    assert "## C. Runtime bundle inventory" in notices
    assert "DEFERRED_TO_PACKAGING_TASK_3" in notices
    assert "macholib | 1.16.4 | macOS only" in notices
    assert "python-xlib | 0.33 | Linux only" in notices
    assert "pyinstaller-hooks-contrib | 2026.6 | build standard hooks only" in notices
    assert "pywinauto | 0.6.9 | test only" in notices
