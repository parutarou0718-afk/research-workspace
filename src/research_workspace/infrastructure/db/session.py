"""SQLite engine/session construction and migration safety images."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class MigrationSafetyImage:
    """Verified internal backup created immediately before a schema migration."""

    batch_id: UUID
    database_path: Path
    database_sha256: str
    source_revision: str


def create_migration_safety_image(
    database_path: Path | str,
    *,
    batch_id: UUID,
    source_revision: str,
) -> MigrationSafetyImage:
    """Create and verify a SQLite Online Backup image outside the DB transaction.

    This is internal migration safety data. It is deliberately not registered as
    a user backup or a recovery point.
    """

    source_path = Path(database_path).resolve()
    backup_directory = source_path.parent / "staging" / "backup" / str(batch_id)
    backup_directory.mkdir(parents=True, exist_ok=False)
    backup_path = backup_directory / "workspace.db"

    with sqlite3.connect(source_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
        target.commit()
    _fsync_file(backup_path)

    with sqlite3.connect(backup_path) as verified:
        integrity = verified.execute("PRAGMA integrity_check").fetchone()[0]
        revision_row = verified.execute("SELECT version_num FROM alembic_version").fetchone()
    if integrity != "ok" or revision_row is None or revision_row[0] != "0001":
        raise RuntimeError("pre-migration SQLite backup verification failed")

    database_sha256 = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    verification = {
        "package_type": "internal_migration_safety_image",
        "batch_id": str(batch_id),
        "source_revision": source_revision,
        "database_sha256": database_sha256,
        "integrity_check": "ok",
    }
    verification_path = backup_directory / "verification.json"
    staging_path = backup_directory / "verification.json.tmp"
    staging_path.write_text(
        json.dumps(verification, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    _fsync_file(staging_path)
    os.replace(staging_path, verification_path)
    _fsync_file(verification_path)

    return MigrationSafetyImage(batch_id, backup_path, database_sha256, source_revision)


def _fsync_file(path: Path) -> None:
    # Windows rejects fsync on a descriptor opened read-only. ``r+b`` does not
    # mutate the file; it gives the descriptor the flush capability fsync needs.
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def create_engine_for_path(path: Path | str) -> Engine:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
