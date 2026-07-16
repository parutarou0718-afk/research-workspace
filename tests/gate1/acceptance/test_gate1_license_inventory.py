from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APPROVED_PARSERS = frozenset({"python-docx", "pypdf", "python-pptx"})
PROHIBITED_PARSERS = frozenset({"pymupdf", "docling", "markitdown"})


def canonicalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def locked_packages() -> dict[str, dict[str, object]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        canonicalize_name(str(package["name"])): package
        for package in lock["package"]
        if canonicalize_name(str(package["name"])) != "research-workspace"
    }


def dependency_names(package: dict[str, object]) -> frozenset[str]:
    dependencies = package.get("dependencies", [])
    assert isinstance(dependencies, list)
    return frozenset(
        canonicalize_name(str(dependency["name"]))
        for dependency in dependencies
        if isinstance(dependency, dict) and "name" in dependency
    )


def parser_dependency_closure(packages: dict[str, dict[str, object]]) -> frozenset[str]:
    pending = list(APPROVED_PARSERS)
    closure: set[str] = set()
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        assert name in packages, f"approved parser distribution is not locked: {name}"
        closure.add(name)
        pending.extend(dependency_names(packages[name]) - closure)
    return frozenset(closure)


def test_approved_gate1_parser_distributions_are_locked_without_prohibited_parsers() -> None:
    packages = locked_packages()

    assert APPROVED_PARSERS <= set(packages)
    assert PROHIBITED_PARSERS.isdisjoint(packages)
    for name in APPROVED_PARSERS:
        assert packages[name].get("version")
        assert packages[name].get("source")


def test_gate1_parser_transitive_closure_has_exact_versions_and_sources() -> None:
    packages = locked_packages()
    closure = parser_dependency_closure(packages)

    assert APPROVED_PARSERS <= closure
    for name in closure:
        assert packages[name].get("version"), name
        source = packages[name].get("source")
        assert isinstance(source, dict) and source, name
