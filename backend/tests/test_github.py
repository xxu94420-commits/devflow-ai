import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.db import Base, make_engine
from app.github import ImportFailure, import_repository


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'import.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def mock_data(request):
    path = request.url.path
    if path == "/repos/test/repo":
        return httpx.Response(
            200, json={"name": "repo", "full_name": "test/repo", "private": False}
        )
    issue = {
        "number": 1,
        "title": "issue",
        "state": "closed",
        "created_at": "2026-01-01T00:00:00Z",
        "closed_at": "2026-01-03T00:00:00Z",
        "user": {"login": "tester"},
        "labels": [{"name": "bug"}],
    }
    commit = {
        "sha": "a" * 40,
        "commit": {
            "message": "fix",
            "committer": {"date": "2026-01-02T00:00:00Z"},
            "author": {"name": "tester"},
        },
    }
    if path.endswith("/issues"):
        return httpx.Response(
            200, json=[issue, {**issue, "number": 2, "pull_request": {}}]
        )
    if path.endswith("/pulls"):
        return httpx.Response(200, json=[{**issue, "number": 2, "body": "Fixes #1"}])
    if path.endswith("/reviews"):
        return httpx.Response(
            200, json=[{"submitted_at": "2026-01-02T00:00:00Z", "state": "APPROVED"}]
        )
    if path.endswith("/commits"):
        return httpx.Response(200, json=[commit])
    raise AssertionError(path)


def test_import_idempotence_relations_and_formal_review(db):
    with httpx.Client(transport=httpx.MockTransport(mock_data)) as client:
        for _ in range(2):
            result = import_repository(db, "test/repo", client=client)
            assert result["issues"] == 1
    for cls in [m.Project, m.Issue, m.Commit, m.PullRequest, m.PRCommit, m.PRIssue]:
        assert db.scalar(select(func.count()).select_from(cls)) == 1
    assert db.scalar(select(m.PullRequest)).first_review_at.day == 2
    assert db.scalar(select(m.Project)).mode == "live"
    assert db.scalar(select(func.count()).select_from(m.Task)) == 0


@pytest.mark.parametrize("status", [403, 429, 404, 401, 500])
def test_import_failure_rolls_back_all_data(db, status):
    def handler(req):
        return (
            mock_data(req)
            if req.url.path == "/repos/test/repo"
            else httpx.Response(status)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ImportFailure):
            import_repository(db, "test/repo", client=client)
    assert db.scalar(select(func.count()).select_from(m.Project)) == 0


def test_network_failure_and_no_secret_message(db):
    def handler(req):
        raise httpx.ConnectError("private debug secret", request=req)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ImportFailure) as exc:
            import_repository(db, "test/repo", client=client)
        assert "secret" not in str(exc.value.message)


def test_pagination_warns_when_capped(db):
    def handler(req):
        response = mock_data(req)
        if req.url.path.endswith("/issues"):
            response.headers["link"] = '<https://api.github.com/next>; rel="next"'
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = import_repository(db, "test/repo", max_pages=1, client=client)
    assert any("非全量" in warning for warning in result["warnings"])


def test_import_endpoint_validates_and_maps_failures(client, monkeypatch):
    from app import github

    def failed(*args, **kwargs):
        raise ImportFailure("limited", 429)

    monkeypatch.setattr(github, "import_repository", failed)
    assert (
        client.post(
            "/api/github/import", json={"repository": "https://evil.test"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/github/import", json={"repository": "test/repo"}).status_code
        == 429
    )
