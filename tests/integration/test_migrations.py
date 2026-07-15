from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from test_schema_contract import _assert_exact_constraints, _assert_exact_schema


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
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
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


def test_failed_migrated_database_fixture_rolls_back(database_path):
    command.upgrade(_config(database_path), "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        try:
            with engine.begin() as connection:
                values = {"id": "00000000-0000-0000-0000-000000000001", "path": "C:/same.pdf"}
                statement = text("""INSERT INTO source_documents
                    (id,path,sha256,mime_type,size_bytes,modified_at,imported_at,read_only)
                    VALUES (:id,:path,:sha,'application/pdf',1,'2026-06-01T00:00:00Z','2026-06-01T00:00:00Z',1)""")
                connection.execute(statement, values | {"sha": "a" * 64})
                connection.execute(statement, (values | {"id": "00000000-0000-0000-0000-000000000002", "sha": "b" * 64}))
        except IntegrityError:
            pass
        else:
            raise AssertionError("fixture was expected to violate the NOCASE path uniqueness rule")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM source_documents")) == 0
    finally:
        engine.dispose()
