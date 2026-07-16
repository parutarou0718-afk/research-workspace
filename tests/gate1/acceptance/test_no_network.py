from __future__ import annotations

import inspect

import pytest

from research_workspace.infrastructure.workers import operation_worker
from research_workspace.infrastructure.parsers import docx_parser, pdf_parser, pptx_parser


@pytest.mark.usefixtures("socket_disabled")
def test_gate1_worker_and_all_parsers_have_no_network_execution_surface() -> None:
    source = "\n".join(
        inspect.getsource(module)
        for module in (operation_worker, docx_parser, pdf_parser, pptx_parser)
    ).lower()
    for forbidden in (
        "socket.",
        "requests.",
        "httpx.",
        "urllib.request",
        "aiohttp",
        "cloud",
    ):
        assert forbidden not in source


@pytest.mark.usefixtures("socket_disabled")
def test_socket_disabled_fixture_rejects_outbound_socket(socket_disabled) -> None:
    import socket

    with pytest.raises(Exception):
        socket.socket()
