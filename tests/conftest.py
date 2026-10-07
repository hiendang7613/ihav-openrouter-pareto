from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixture_build  # noqa: E402  (also puts the plugin core on sys.path)
from ihav_openrouter_pareto.build import build  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """One read-only capture and build of the real 2026-10-07 fixtures, shared by tests that only read it."""
    space, capture_id = fixture_build.make_capture(tmp_path_factory.mktemp("project"))
    return space, capture_id, build(space, capture_id)


@pytest.fixture(scope="session")
def report(built):
    import json

    return json.loads(Path(built[2]["json"]).read_text(encoding="utf-8"))
