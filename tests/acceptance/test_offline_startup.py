from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from research_workspace import bootstrap


def test_application_starts_with_network_disabled(isolated_app_dirs):
    assert hasattr(bootstrap, "bootstrap_application")
    result = bootstrap.bootstrap_application()

    assert result.ok is True
    assert result.window.objectName() == "mainWindow"
    assert result.error is None
    data_directory = Path(result.window.services.config.active_data_directory)
    assert (data_directory / "research_workspace.db").is_file()
    assert all((data_directory / name).is_dir() for name in ("logs", "derived", "exports", "backups"))


def test_bootstrap_result_is_frozen_and_has_exactly_one_presentation(isolated_app_dirs):
    assert hasattr(bootstrap, "BootstrapResult")
    assert hasattr(bootstrap, "bootstrap_application")
    result = bootstrap.bootstrap_application()

    assert isinstance(result, bootstrap.BootstrapResult)
    assert (result.window is None) != (result.error is None)
    with pytest.raises(FrozenInstanceError):
        result.ok = False
