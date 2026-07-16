import json
import hashlib
import importlib.metadata
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.markers import Marker


ROOT = Path(__file__).resolve().parents[2]
PERMISSIVE_TOKENS = {"MIT", "BSD", "Apache", "ISC", "PSF", "Python Software Foundation"}
DENIED_TOKENS = {"GPL", "AGPL", "UNKNOWN"}
LGPL_ALLOWLIST = {"PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6"}
ROOT_DISTRIBUTION = "research-workspace"
LOCK_SHA256 = "2dcb4d6b779367523362865978adedc030004373bc8ae7994fd57be2edef5522"
EXACT_BUILD_TOOL_EXCEPTIONS = {
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
EXACT_TEST_TOOL_APPROVALS = {
    "pywinauto": {
        "version": "0.6.9",
        "lock_sha256": LOCK_SHA256,
        "license_sha256": "18a999a95b7b23d86c410b4534e44d69f6d8ce13c3a53719b06ab895d8a2e73a",
        "license_expression": "BSD-3-Clause",
        "role": "test_only",
    }
}
RUNTIME_BUNDLE_PROHIBITED_DISTRIBUTIONS = frozenset(
    {
        "pyinstaller",
        "pyinstaller-hooks-contrib-standard-hooks",
        "pywinauto",
        "comtypes",
        "pywin32",
    }
)
RUNTIME_BUNDLE_INVENTORY_STATUS = "DEFERRED_TO_PACKAGING_TASK_3"
LOCK_ONLY_LICENSE_ROWS = {
    "macholib": {
        "Name": "macholib",
        "Version": "1.16.4",
        "License": "MIT License",
        "LicenseSHA256": "47082ab2bc0184123ec9f10fdf80c70723ee68f07d44382e17615c2a6ba70b09",
        "URL": "http://github.com/ronaldoussoren/macholib",
    },
    "python-xlib": {
        "Name": "python-xlib",
        "Version": "0.33",
        "License": "GNU Lesser General Public License v2 or later (LGPLv2+)",
        "LicenseSHA256": "3bb6f6bec94b99e2927a8880bf49c401f5e8f48a20ddea96310860264cae20b0",
        "URL": "https://github.com/python-xlib/python-xlib",
    },
}
LICENSE_FILE_BY_DISTRIBUTION = {
    "pyinstaller": "licenses/COPYING.txt",
    "pyinstaller-hooks-contrib": "licenses/LICENSE",
    "pywinauto": "LICENSE",
}


def canonicalize_name(name):
    return re.sub(r"[-_.]+", "-", name).casefold()


def locked_third_party_distributions():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        canonicalize_name(package["name"]): package
        for package in lock["package"]
        if canonicalize_name(package["name"]) != ROOT_DISTRIBUTION
    }


def uv_lock_sha256():
    return hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()


def universal_lock_inventory():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {
        canonicalize_name(package["name"]): package
        for package in lock["package"]
        if canonicalize_name(package["name"]) != ROOT_DISTRIBUTION
    }
    markers = {name: set() for name in packages}
    for package in lock["package"]:
        for dependency in package.get("dependencies", []):
            name = canonicalize_name(dependency["name"])
            if name not in markers:
                continue
            marker = dependency.get("marker")
            if marker:
                markers[name].add(marker)
            else:
                markers[name].add("unconditional")
    return {
        name: {
            "version": package["version"],
            "source": package.get("source"),
            "markers": tuple(sorted(markers[name] - {"unconditional"}))
            if "unconditional" not in markers[name]
            else tuple(),
        }
        for name, package in packages.items()
    }


def effective_dependency_closure(roots, target_environment):
    packages = locked_third_party_distributions()
    pending = [canonicalize_name(name) for name in roots]
    closure = set()
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        if name not in packages:
            raise AssertionError(f"locked dependency is missing: {name}")
        closure.add(name)
        for dependency in packages[name].get("dependencies", []):
            marker = dependency.get("marker")
            if marker and not Marker(marker).evaluate(environment=target_environment):
                continue
            pending.append(canonicalize_name(dependency["name"]))
    return frozenset(closure)


def windows_target_environment():
    return {
        "python_version": "3.12",
        "python_full_version": "3.12.0",
        "implementation_name": "cpython",
        "platform_python_implementation": "CPython",
        "sys_platform": "win32",
        "os_name": "nt",
        "platform_system": "Windows",
        "platform_machine": "AMD64",
    }


def windows_effective_lock_names():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    root = next(
        package
        for package in lock["package"]
        if canonicalize_name(package["name"]) == ROOT_DISTRIBUTION
    )
    roots = [dependency["name"] for dependency in root.get("dependencies", [])]
    return effective_dependency_closure(roots, windows_target_environment())


def complete_inventory_rows(pip_license_rows, locked_distributions):
    rows_by_name = {
        canonicalize_name(row["Name"]): row
        for row in pip_license_rows
        if canonicalize_name(row["Name"]) != ROOT_DISTRIBUTION
    }
    for name, package in locked_distributions.items():
        if name in rows_by_name:
            continue
        if name in LOCK_ONLY_LICENSE_ROWS:
            rows_by_name[name] = LOCK_ONLY_LICENSE_ROWS[name]
            continue
        metadata = importlib.metadata.metadata(package["name"])
        rows_by_name[name] = {
            "Name": metadata["Name"],
            "Version": importlib.metadata.version(package["name"]),
            "License": metadata.get("License-Expression") or metadata.get("License") or "UNKNOWN",
        }
    return list(rows_by_name.values())


def distribution_license_sha256(name):
    distribution = importlib.metadata.distribution(name)
    relative_path = LICENSE_FILE_BY_DISTRIBUTION[canonicalize_name(name)].casefold()
    matching = [
        path
        for path in distribution.files or ()
        if str(path).replace("\\", "/").casefold().endswith(relative_path)
    ]
    assert len(matching) == 1, (name, matching)
    path = Path(distribution.locate_file(matching[0]))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reviewed_build_tool_violations(rows, lock_sha256):
    violations = []
    seen = set()
    for row in rows:
        name = canonicalize_name(row["Name"])
        seen.add(name)
        approved = EXACT_BUILD_TOOL_EXCEPTIONS.get(name)
        if approved is None:
            violations.append((name, row.get("Version"), "BUILD_TOOL_NOT_APPROVED"))
            continue
        observed = {
            "version": row.get("Version"),
            "lock_sha256": lock_sha256,
            "license_sha256": row.get("LicenseSHA256"),
            "role": row.get("Role"),
        }
        expected = {key: approved[key] for key in observed}
        if observed != expected:
            violations.append((name, row.get("Version"), "BUILD_TOOL_FACT_MISMATCH"))
    for missing in set(EXACT_BUILD_TOOL_EXCEPTIONS) - seen:
        violations.append((missing, None, "BUILD_TOOL_MISSING"))
    return violations


def commercial_policy_violations(rows, permissive_tokens, lgpl_allowlist, denied_tokens):
    violations = []
    for row in rows:
        name = row["Name"]
        license_text = (row.get("License") or "UNKNOWN").strip()
        if name in lgpl_allowlist and "LGPL" in license_text:
            continue
        has_gpl = "AGPL" in license_text.upper() or re.search(r"(?<!L)GPL", license_text.upper())
        if has_gpl or license_text.upper() in denied_tokens:
            violations.append((name, row["Version"], license_text))
        elif any(token.casefold() in license_text.casefold() for token in permissive_tokens):
            continue
        else:
            violations.append((name, row["Version"], f"UNREVIEWED: {license_text}"))
    return violations


def test_commercial_policy_fails_closed_for_denied_and_unreviewed_metadata():
    denied_rows = [
        {"Name": "empty", "Version": "1", "License": ""},
        {"Name": "unknown", "Version": "1", "License": "UNKNOWN"},
        {"Name": "unreviewed", "Version": "1", "License": "MPL-2.0"},
        {"Name": "gpl", "Version": "1", "License": "GPL-3.0-only"},
        {"Name": "agpl", "Version": "1", "License": "AGPL-3.0-only"},
        {"Name": "mixed", "Version": "1", "License": "MIT AND GPL-3.0-only"},
        {"Name": "other-lgpl", "Version": "1", "License": "LGPL-3.0-only"},
    ]
    violations = commercial_policy_violations(
        denied_rows,
        permissive_tokens=PERMISSIVE_TOKENS,
        lgpl_allowlist=LGPL_ALLOWLIST,
        denied_tokens=DENIED_TOKENS,
    )
    assert {name for name, _, _ in violations} == {row["Name"] for row in denied_rows}
    assert commercial_policy_violations(
        [{"Name": "PySide6", "Version": "1", "License": "LGPL-3.0-only"}],
        permissive_tokens=PERMISSIVE_TOKENS,
        lgpl_allowlist=LGPL_ALLOWLIST,
        denied_tokens=DENIED_TOKENS,
    ) == []


def test_locked_dependencies_have_reviewed_commercial_licenses():
    pip_license_rows = json.loads(subprocess.check_output([
        sys.executable, "-m", "piplicenses", "--format=json", "--with-license-file"
    ]))
    locked_distributions = locked_third_party_distributions()
    assert "fqdn" not in locked_distributions
    assert "rfc3987" not in locked_distributions
    rows = complete_inventory_rows(pip_license_rows, locked_distributions)
    assert {canonicalize_name(row["Name"]) for row in rows} == set(locked_distributions)
    for row in rows:
        locked = locked_distributions[canonicalize_name(row["Name"])]
        assert row["Version"] == locked["version"]
    windows_effective = windows_effective_lock_names()
    assert "macholib" not in windows_effective
    assert "python-xlib" not in windows_effective
    generic_rows = [
        row
        for row in rows
        if canonicalize_name(row["Name"]) in windows_effective
        and canonicalize_name(row["Name"]) not in EXACT_BUILD_TOOL_EXCEPTIONS
    ]
    violations = commercial_policy_violations(
        generic_rows,
        permissive_tokens=PERMISSIVE_TOKENS,
        lgpl_allowlist=LGPL_ALLOWLIST,
        denied_tokens=DENIED_TOKENS,
    )
    assert violations == []
    rows_by_name = {canonicalize_name(row["Name"]): row for row in rows}
    build_rows = []
    for name, approval in EXACT_BUILD_TOOL_EXCEPTIONS.items():
        row = dict(rows_by_name[name])
        row["LicenseSHA256"] = distribution_license_sha256(name)
        row["Role"] = approval["role"]
        build_rows.append(row)
    assert reviewed_build_tool_violations(build_rows, uv_lock_sha256()) == []
    pywinauto = EXACT_TEST_TOOL_APPROVALS["pywinauto"]
    assert rows_by_name["pywinauto"]["Version"] == pywinauto["version"]
    assert distribution_license_sha256("pywinauto") == pywinauto["license_sha256"]
    assert uv_lock_sha256() == pywinauto["lock_sha256"]
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "uv run pip-licenses --format=markdown --with-urls --with-license-file" in notices
    assert not re.search(r"^\|\s*research-workspace\s*\|", notices, re.IGNORECASE | re.MULTILINE)
    assert str(ROOT).casefold() not in notices.casefold()
    assert ".venv" not in notices.casefold()
    notices_casefolded = notices.casefold()
    for name, package in locked_distributions.items():
        assert name in canonicalize_name(notices_casefolded)
        assert package["version"] in notices
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Overview and Imports are backed by application queries." in readme
    assert "creates local immutable snapshots" in readme
    assert "Papers, Ideas, and Submissions are foundation placeholders." in readme
