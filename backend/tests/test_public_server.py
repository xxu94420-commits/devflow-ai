import subprocess

import pytest

from app import public_server
from app.config import get_settings


def test_public_bootstrap_refuses_writable_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "read_only", False)
    with pytest.raises(RuntimeError, match="READ_ONLY"):
        public_server.prepare()


@pytest.mark.parametrize("outcome", ["ok", "failure", "timeout"])
def test_demo_survives_bounded_github_import(client, monkeypatch, capsys, outcome):
    from app.db import get_db
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "read_only", True)
    monkeypatch.setattr(settings, "demo_import_github", True)
    session = next(app.dependency_overrides[get_db]())
    monkeypatch.setattr(public_server, "SessionLocal", lambda: session)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "--import-only" in command:
            assert kwargs["timeout"] == 60
            assert kwargs["capture_output"] is True
            if outcome == "timeout":
                raise subprocess.TimeoutExpired(command, 60, output="private-output")
            return subprocess.CompletedProcess(
                command, int(outcome == "failure"), stdout="private-output"
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(public_server.subprocess, "run", run)
    public_server.prepare()
    assert len(calls) == 2
    assert "private-output" not in capsys.readouterr().out
    assert len(client.get("/api/tasks?mode=demo").json()) == 42
    assert client.get("/api/projects?mode=live").json() == []
