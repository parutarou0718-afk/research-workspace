from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config


def alembic_config(database_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


@pytest.fixture
def gate2_database_path(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    return workspace / "research_workspace.db"


@pytest.fixture
def monitoring_database(tmp_path: Path):
    from research_workspace import bootstrap
    from research_workspace.infrastructure.db.session import (
        create_engine_for_path,
        session_factory,
    )

    workspace = tmp_path / "workspace"
    bootstrap._ensure_data_layout(workspace)
    database = workspace / "research_workspace.db"
    bootstrap._run_migrations(database)
    engine = create_engine_for_path(database)
    state = SimpleNamespace(
        workspace=workspace,
        database=database,
        engine=engine,
        factory=session_factory(engine),
    )
    yield state
    engine.dispose()
