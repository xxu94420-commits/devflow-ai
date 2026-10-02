from app import review_trial
from app.config import get_settings
from app.review_provider import ReviewFailure


def test_disabled_trial_preserves_readonly(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "read_only", True)
    monkeypatch.setattr(get_settings(), "public_review_enabled", False)
    assert client.post("/api/review/trial", json={}).status_code == 403


def test_public_trial_no_storage_budget_and_no_write_bypass(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "read_only", True)
    monkeypatch.setattr(settings, "public_review_enabled", True)
    monkeypatch.setattr(settings, "public_review_daily_limit", 1)
    monkeypatch.setattr(review_trial, "budget", review_trial.TrialBudget())
    monkeypatch.setattr(
        review_trial,
        "connection",
        lambda _: {
            "model": "fixture",
            "url": "https://provider.example/v1",
            "key": "fixture",
        },
    )
    monkeypatch.setattr(review_trial, "generate", lambda *_: ([], {}))
    data = {
        "title": "公开试用",
        "description": "synthetic requirement",
        "consent": True,
    }
    assert (
        client.post("/api/review/trial", json=data | {"consent": False}).status_code
        == 422
    )
    result = client.post("/api/review/trial", json=data)
    assert result.status_code == 200 and result.json()["stored"] is False
    assert client.get("/api/requirements?mode=live").json() == []
    assert client.post("/api/review/trial", json=data).status_code == 429
    for path in [
        "/api/requirements",
        "/api/requirements/1/reviews",
        "/api/tasks",
        "/api/ci/sync",
        "/api/review/trial/",
    ]:
        assert client.post(path, json=data).status_code == 403


def test_trial_failure_does_not_fake_success(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_review_enabled", True)
    monkeypatch.setattr(review_trial, "budget", review_trial.TrialBudget())
    monkeypatch.setattr(
        review_trial,
        "connection",
        lambda _: {
            "model": "fixture",
            "url": "https://provider.example/v1",
            "key": "fixture",
        },
    )

    def fail(*_):
        raise ReviewFailure("timeout")

    monkeypatch.setattr(review_trial, "generate", fail)
    response = client.post(
        "/api/review/trial",
        json={"title": "test", "description": "test", "consent": True},
    )
    assert response.status_code == 502
    assert not review_trial.budget.lock.locked()
