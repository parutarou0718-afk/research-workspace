from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOTS = frozenset({"watchdog"})


def _canonicalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _license_policy_module():
    path = ROOT / "tests" / "acceptance" / "test_license_policy.py"
    spec = importlib.util.spec_from_file_location("commercial_license_policy", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _monitoring_closure(packages: dict[str, dict[str, object]]) -> frozenset[str]:
    pending = list(MONITORING_ROOTS)
    closure: set[str] = set()
    while pending:
        name = pending.pop()
        assert name in packages, f"approved monitoring distribution is not locked: {name}"
        if name in closure:
            continue
        closure.add(name)
        pending.extend(_dependency_names(packages[name]) - closure)
    return frozenset(closure)


def test_watchdog_is_a_runtime_dependency_with_an_exact_locked_closure() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = {
        _canonicalize(requirement.split(">", 1)[0])
        for requirement in pyproject["project"]["dependencies"]
    }
    packages = _locked_packages()

    assert MONITORING_ROOTS <= runtime
    closure = _monitoring_closure(packages)
    assert MONITORING_ROOTS <= closure
    for name in closure:
        assert packages[name].get("version"), name
        source = packages[name].get("source")
        assert isinstance(source, dict) and source, name


def test_watchdog_approval_is_bound_to_lock_version_source_and_license_hash() -> None:
    policy = _license_policy_module()
    approval = policy.EXACT_GATE2_RUNTIME_APPROVALS["watchdog"]
    package = _locked_packages()["watchdog"]

    assert approval["version"] == package["version"]
    assert approval["lock_sha256"] == policy.uv_lock_sha256()
    assert approval["role"] == "gate2_runtime_monitor"
    assert approval["license_expression"] == "Apache-2.0"
    assert approval["license_sha256"] == policy.distribution_license_sha256("watchdog")
    assert package["source"] == {"registry": "https://pypi.org/simple"}


def test_watchdog_closure_is_complete_in_notices() -> None:
    packages = _locked_packages()
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    canonical_notices = _canonicalize(notices)

    for name in _monitoring_closure(packages):
        assert name in canonical_notices, name
        assert str(packages[name]["version"]) in notices, name
    assert "Gate 2 runtime monitoring closure" in notices
