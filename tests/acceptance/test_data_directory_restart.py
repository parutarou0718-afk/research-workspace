from research_workspace.application.ports.config_store import AppConfig
from research_workspace.application.services.change_data_directory import ChangeDataDirectory
from research_workspace.application.services.initialize_application import InitializeApplication
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore


def test_selected_directory_activates_after_restart_without_migrating_old_data(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    database = old / "research_workspace.db"
    database.write_bytes(b"original workspace")
    store = JsonConfigStore(tmp_path / "config" / "config.json")
    store.save(AppConfig("1.0", old.resolve(), None, "INFO"))

    switched = ChangeDataDirectory(store).execute(new)
    assert switched.ok is True
    assert switched.value.active_data_directory == old.resolve()
    assert switched.value.pending_data_directory == new.resolve()
    assert database.read_bytes() == b"original workspace"
    assert list(new.iterdir()) == []

    restarted = InitializeApplication(JsonConfigStore(store.path)).execute()
    assert restarted.ok is True
    assert restarted.value.config.active_data_directory == new.resolve()
    assert restarted.value.config.pending_data_directory is None
    assert database.read_bytes() == b"original workspace"
    assert list(new.iterdir()) == []
