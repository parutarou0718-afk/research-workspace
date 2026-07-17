from pathlib import Path

import pytest

from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore
from research_workspace.infrastructure.workers.operation_worker import OperationWorker


@pytest.mark.usefixtures("socket_disabled")
def test_gate2_worker_construction_and_local_ports_need_no_network(
    tmp_path: Path, socket_disabled
) -> None:
    worker = OperationWorker(SnapshotStore(tmp_path / "workspace"), {})

    assert worker is not None
    with pytest.raises(Exception):
        import socket

        socket.socket()
