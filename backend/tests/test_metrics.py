from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app import models as m
from app.db import Base, make_engine
from app.metrics import analyze
from app.schemas import InteractionIn, TaskIn


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_empty_is_unknown_not_zero_improvement(db):
    result = analyze(db, "live", datetime(2026, 1, 1), datetime(2026, 2, 1))
    assert result["metrics"]["ai_time_saving"]["value"] is None
    assert result["metrics"]["test_pass_rate"]["value"] is None


def test_small_samples_and_mode_isolation(db):
    project = m.Project(name="demo", repository="demo/test", mode="demo")
    db.add(project)
    db.flush()
    start = datetime(2026, 1, 1)
    for ai, hours in [(True, 2), (False, 4)]:
        db.add(
            m.Task(
                project_id=project.id,
                title="task",
                task_type="功能开发",
                uses_ai=ai,
                estimated_hours=4,
                actual_hours=hours,
                created_at=start,
                completed_at=start + timedelta(days=1),
            )
        )
    db.flush()
    result = analyze(db, "demo", start, start + timedelta(days=30))
    assert result["metrics"]["ai_task_share"]["value"] == 50
    assert result["metrics"]["ai_time_saving"]["value"] is None
    assert (
        analyze(db, "live", start, start + timedelta(days=30))["metrics"][
            "project_count"
        ]["value"]
        == 0
    )


def test_matched_types_not_global_average(db):
    p = m.Project(name="p", repository="demo/p", mode="demo")
    db.add(p)
    db.flush()
    start = datetime(2026, 1, 1)
    for ai, hours in [(True, 2), (False, 4)]:
        for _ in range(5):
            db.add(
                m.Task(
                    project_id=p.id,
                    title="task",
                    task_type="功能开发",
                    estimated_hours=4,
                    actual_hours=hours,
                    uses_ai=ai,
                    created_at=start,
                    completed_at=start + timedelta(days=1),
                )
            )
    db.flush()
    result = analyze(db, "demo", start, start + timedelta(days=30))
    assert result["metrics"]["ai_time_saving"]["value"] == 50
    assert result["task_types"][2]["ai_n"] == 5


def test_validation_secret_and_impossible_counts():
    values = dict(
        task_id=1,
        tool="Codex",
        stage="功能开发",
        purpose="test",
        prompt_summary="summary",
        estimated_before_hours=1,
        actual_hours=1,
    )
    with pytest.raises(ValueError, match="accepted_count"):
        InteractionIn(**values, accepted_count=2)
    values["prompt_summary"] = "ghp_" + "a" * 25
    with pytest.raises(ValueError, match="secret"):
        InteractionIn(**values)
    with pytest.raises(ValueError, match="actual_hours"):
        TaskIn(
            project_id=1,
            title="x",
            task_type="功能开发",
            estimated_hours=1,
            created_at=datetime(2026, 1, 1),
            completed_at=datetime(2026, 1, 2),
        )
