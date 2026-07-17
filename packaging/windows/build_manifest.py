from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MANIFEST_NAME = "BUILD-MANIFEST.json"
DIGEST_NAME = "BUILD-MANIFEST.sha256"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _role(relative_path: str) -> str:
    if relative_path == "app/ResearchWorkspace.exe":
        return "application_executable"
    if relative_path.startswith("app/contracts/"):
        return "runtime_contract"
    if relative_path.startswith("app/migrations/"):
        return "runtime_migration"
    if relative_path == "app/THIRD_PARTY_NOTICES.md":
        return "third_party_notices"
    return "runtime_dependency"


def write_manifest(
    package_root: Path,
    *,
    product_tag: str,
    product_commit: str,
    build_commit: str,
) -> Path:
    package_root = package_root.resolve()
    files = []
    for path in sorted(
        (
            item
            for item in package_root.rglob("*")
            if item.is_file()
            and item.name not in {MANIFEST_NAME, DIGEST_NAME}
        ),
        key=lambda item: item.relative_to(package_root).as_posix(),
    ):
        relative = path.relative_to(package_root).as_posix()
        files.append(
            {
                "path": relative,
                "role": _role(relative),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = {
        "schema_version": "1.0",
        "product": "Research Workspace",
        "product_tag": product_tag,
        "product_commit": product_commit,
        "build_commit": build_commit,
        "platform": "windows-x86_64",
        "format": "portable-onedir",
        "files": files,
    }
    raw = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    output = package_root / MANIFEST_NAME
    output.write_bytes(raw)
    (package_root / DIGEST_NAME).write_text(
        hashlib.sha256(raw).hexdigest() + "\n",
        encoding="ascii",
        newline="\n",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--product-tag", required=True)
    parser.add_argument("--product-commit", required=True)
    parser.add_argument("--build-commit", required=True)
    args = parser.parse_args()
    write_manifest(
        args.package_root,
        product_tag=args.product_tag,
        product_commit=args.product_commit,
        build_commit=args.build_commit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
