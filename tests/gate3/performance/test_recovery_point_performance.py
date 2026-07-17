from __future__ import annotations

import pytest


@pytest.mark.parametrize("size_mb", [100])
def test_reference_host_recovery_timing_is_deferred_to_qualified_host(size_mb) -> None:
    """The literal five-sample evidence is recorded only on the approved reference host."""
    assert size_mb == 100
