from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection

from test_schema_contract import (
    _assert_exact_constraints,
    _assert_exact_schema,
    _assert_source_document_path_uniqueness_is_nocase,
)


def _config(database_path):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_upgrade_head_creates_core_schema(database_path):
    command.upgrade(_config(database_path), "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        _assert_exact_schema(inspector)
        _assert_exact_constraints(inspector)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
    finally:
        engine.dispose()


def test_upgrade_head_is_repeatable(database_path):
    config = _config(database_path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        before = connection.execute(text("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name")).all()
    command.upgrade(config, "head")
    with engine.connect() as connection:
        after = connection.execute(text("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name")).all()
    engine.dispose()
    assert after == before


def test_migrated_schema_path_uniqueness_is_nocase(database_path):
    command.upgrade(_config(database_path), "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        _assert_source_document_path_uniqueness_is_nocase(engine)
    finally:
        engine.dispose()


def test_failed_migration_rolls_back_all_domain_ddl_and_clean_retry_succeeds(database_path, monkeypatch):
    original_execute = Connection.execute

    def fail_at_ideas(connection, statement, *args, **kwargs):
        if "CREATE TABLE ideas" in str(statement):
            raise RuntimeError("injected 0001 failure")
        return original_execute(connection, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "execute", fail_at_ideas)
    try:
        command.upgrade(_config(database_path), "head")
    except RuntimeError as exc:
        assert str(exc) == "injected 0001 failure"
    else:
        raise AssertionError("migration failure was not injected")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == set()
    engine.dispose()

    monkeypatch.setattr(Connection, "execute", original_execute)
    command.upgrade(_config(database_path), "head")
    retry_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    _assert_exact_schema(inspect(retry_engine))
    retry_engine.dispose()
