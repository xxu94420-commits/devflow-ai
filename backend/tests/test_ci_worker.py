import asyncio

import pytest
from pydantic import ValidationError

from app import ci_worker
from app.config import Settings, get_settings


def test_polling_runs_immediately_then_waits_even_in_readonly(monkeypatch):
    calls = []
    monkeypatch.setattr(get_settings(), "read_only", True)
    monkeypatch.setattr(get_settings(), "ci_sync_interval_seconds", 3600)
    monkeypatch.setattr(ci_worker, "sync_cycle", lambda: calls.append("sync"))

    async def wait(seconds):
        calls.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(ci_worker.asyncio, "sleep", wait)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ci_worker.poll())
    assert calls == ["sync", 3600]


def test_short_polling_interval_is_rejected():
    with pytest.raises(ValidationError):
        Settings(ci_sync_interval_seconds=1, _env_file=None)


def test_ci_routes_validate_pagination_and_demo_sync(client):
    result = client.post("/api/demo/seed").json()
    assert (
        client.post(
            "/api/ci/sync", json={"project_id": result["project_id"]}
        ).status_code
        == 422
    )
    assert client.get("/api/ci/runs?limit=101").status_code == 422
    assert client.get("/api/ci/runs?offset=-1").status_code == 422
    assert client.get("/api/ci/status").json()["poll_interval_seconds"] == 0
