import json
import importlib.metadata
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PERMISSIVE_TOKENS = {"MIT", "BSD", "Apache", "ISC", "PSF", "Python Software Foundation"}
DENIED_TOKENS = {"GPL", "AGPL", "UNKNOWN"}
LGPL_ALLOWLIST = {"PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6"}
ROOT_DISTRIBUTION = "research-workspace"


def canonicalize_name(name):
    return re.sub(r"[-_.]+", "-", name).casefold()


def locked_third_party_distributions():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        canonicalize_name(package["name"]): package
        for package in lock["package"]
        if canonicalize_name(package["name"]) != ROOT_DISTRIBUTION
    }


def complete_inventory_rows(pip_license_rows, locked_distributions):
    rows_by_name = {
        canonicalize_name(row["Name"]): row
        for row in pip_license_rows
        if canonicalize_name(row["Name"]) != ROOT_DISTRIBUTION
    }
    for name, package in locked_distributions.items():
        if name in rows_by_name:
            continue
        metadata = importlib.metadata.metadata(package["name"])
        rows_by_name[name] = {
            "Name": metadata["Name"],
            "Version": importlib.metadata.version(package["name"]),
            "License": metadata.get("License-Expression") or metadata.get("License") or "UNKNOWN",
        }
    return list(rows_by_name.values())


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
    violations = commercial_policy_violations(
        rows,
        permissive_tokens=PERMISSIVE_TOKENS,
        lgpl_allowlist=LGPL_ALLOWLIST,
        denied_tokens=DENIED_TOKENS,
    )
    assert violations == []
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
    assert "Only Overview is backed by the application query and seeded local data." in readme
    assert "Papers, Ideas, and Submissions are foundation placeholders." in readme
