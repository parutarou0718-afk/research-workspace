from pathlib import Path

import pytest
from sqlalchemy import inspect

from research_workspace.infrastructure.db.session import (
    create_engine_for_path,
    session_factory,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "workspace.db"


@pytest.fixture
def engine(database_path: Path):
    engine = create_engine_for_path(database_path)
    yield engine
    engine.dispose()


@pytest.fixture
def sqlite_inspector(engine):
    return inspect(engine)


@pytest.fixture
def session(engine):
    factory = session_factory(engine)
    with factory() as session:
        yield session
        session.rollback()
