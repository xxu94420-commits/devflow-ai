"""Opt-in maintainer check against this repository's real GitHub evidence.

Uses Git Credential Manager only in memory. Creates a separate local database,
never alters the public deployment, and never invents measured development time.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = "sqlite:///./data/ci-verification.db"
os.environ["CI_SYNC_INTERVAL_SECONDS"] = "0"
credential = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    text=True,
    capture_output=True,
    check=True,
    cwd=ROOT,
)
fields = dict(
    line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line
)
os.environ["GITHUB_TOKEN"] = fields["password"]
os.chdir(ROOT / "backend")
sys.path.insert(0, str(ROOT / "backend"))
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

from sqlalchemy import select  # noqa: E402

from app import models as m  # noqa: E402
from app.ci import reconcile, sync_project  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.github import import_repository  # noqa: E402

with SessionLocal() as db:
    imported = import_repository(db, "xxu94420-commits/devflow-ai", max_pages=1)
    project = db.get(m.Project, imported["project_id"])
    sync_project(db, project, max_runs=3)
    complete = db.scalars(
        select(m.CIRun)
        .where(m.CIRun.project_id == project.id, m.CIRun.evidence_status == "available")
        .order_by(m.CIRun.created_at.desc())
    ).all()
    if not complete:
        states = db.scalars(select(m.CIRun.evidence_status)).all()
        raise SystemExit(f"No complete JUnit evidence yet; states={states}")
    run = complete[0]
    task = db.scalar(
        select(m.Task).where(m.Task.title == "自动测试数据链路开发（Issue #12）")
    )
    if task is None:
        issue = db.scalar(
            select(m.Issue).where(
                m.Issue.project_id == project.id, m.Issue.number == 12
            )
        )
        task = m.Task(
            project_id=project.id,
            issue_id=issue.id if issue else None,
            title="自动测试数据链路开发（Issue #12）",
            task_type="功能开发",
            description="本次真实开发任务；4小时为记录时的计划估算，非实测。实际耗时和完成时间留空。",
            estimated_hours=4,
            uses_ai=True,
        )
        db.add(task)
        db.flush()
    # Explicit maintainer attribution of this observed implementation run.
    # Do not guess unknown tasks or attribute every repository run to this task.
    run.task_id, run.association = task.id, "manual"
    reconcile(db, run)
    db.commit()
    before = db.scalars(
        select(m.TestResult).where(m.TestResult.ci_run_id == run.id)
    ).all()
    sync_project(db, project, max_runs=3)
    after = db.scalars(
        select(m.TestResult).where(m.TestResult.ci_run_id == run.id)
    ).all()
    assert len(before) == len(after) == 1
    assert after[0].passed == run.passed
    assert after[0].total == run.passed + run.failed + run.errors
    print(f"PASS real run={run.run_id} attempt={run.attempt} task={task.id}")
    print(
        f"JUnit passed={run.passed} failed={run.failed} errors={run.errors} skipped={run.skipped}"
    )
    print(f"Digest={run.digest}; repeat sync retains one TestResult")
