from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models as m
from app.db import Base, make_engine
from app.metrics import analyze


def test_first_test_outside_window_not_reclassified_and_weighted_rate(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'b.db'}")
    Base.metadata.create_all(engine)
    start, end = datetime(2026, 1, 2), datetime(2026, 1, 3)
    with Session(engine) as db:
        p = m.Project(name="p", repository="test/p", mode="live")
        db.add(p)
        db.flush()
        task = m.Task(
            project_id=p.id,
            title="t",
            task_type="功能开发",
            estimated_hours=1,
            actual_hours=2,
            uses_ai=False,
            created_at=start - timedelta(days=1),
            completed_at=start,
        )
        db.add(task)
        db.flush()
        db.add_all(
            [
                m.TestResult(
                    task_id=task.id,
                    name="first",
                    passed=0,
                    total=1,
                    created_at=start - timedelta(seconds=1),
                ),
                m.TestResult(
                    task_id=task.id, name="rerun", passed=3, total=4, created_at=start
                ),
                m.TestResult(
                    task_id=task.id, name="suite", passed=10, total=10, created_at=start
                ),
                m.TestResult(
                    task_id=task.id,
                    name="excluded end",
                    passed=0,
                    total=100,
                    created_at=end,
                ),
                m.Defect(task_id=task.id, title="excluded future", created_at=end),
            ]
        )
        db.flush()
        result = analyze(db, "live", start, end)["metrics"]
        assert result["first_test_pass_rate"]["value"] is None
        assert result["test_pass_rate"]["value"] == 92.86
        assert result["test_pass_rate"]["n"] == 14
        assert result["defect_density"]["value"] == 0
        assert result["non_ai_avg_hours"]["value"] == 2
    engine.dispose()


def test_full_update_links_and_foreign_keys(client):
    from app.db import get_db
    from app.main import app

    pid = client.post("/api/projects", json={"name": "p", "repository": "t/p"}).json()[
        "id"
    ]
    req = client.post(
        "/api/requirements", json={"project_id": pid, "title": "r"}
    ).json()
    dependency = app.dependency_overrides[get_db]()
    db = next(dependency)
    issue = m.Issue(project_id=pid, number=1, title="issue")
    commit = m.Commit(project_id=pid, sha="b" * 40)
    pr = m.PullRequest(project_id=pid, number=2, title="pr")
    db.add_all([issue, commit, pr])
    db.commit()
    ids = issue.id, commit.id, pr.id
    dependency.close()
    assert (
        client.put(f"/api/issues/{ids[0]}/requirement/{req['id']}").status_code == 200
    )
    body = {
        "project_id": pid,
        "requirement_id": req["id"],
        "issue_id": ids[0],
        "title": "task",
        "task_type": "功能开发",
        "estimated_hours": 2,
        "created_at": "2026-01-01T00:00:00Z",
    }
    task = client.post("/api/tasks", json=body).json()
    for _ in range(2):
        assert (
            client.put(
                f"/api/tasks/{task['id']}/links",
                json={"commit_ids": [ids[1]], "pr_ids": [ids[2]]},
            ).status_code
            == 200
        )
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert len(detail["commits"]) == len(detail["pull_requests"]) == 1
    assert detail["requirement"]["id"] == req["id"]
    assert (
        client.put(
            f"/api/tasks/{task['id']}",
            json={**body, "actual_hours": 1, "completed_at": "2026-01-02T00:00:00Z"},
        ).status_code
        == 200
    )
    defect = client.post(
        "/api/defects",
        json={
            "task_id": task["id"],
            "title": "d",
            "created_at": "2026-01-01T00:00:00Z",
        },
    ).json()
    assert (
        client.put(
            f"/api/defects/{defect['id']}",
            json={
                "task_id": task["id"],
                "title": "d",
                "created_at": defect["created_at"],
                "resolved_at": "2026-01-02T00:00:00Z",
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/requirements/{req['id']}",
            json={"project_id": pid, "title": "r2", "change_count": 2},
        ).status_code
        == 200
    )
