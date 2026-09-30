"""Deterministic synthetic data, isolated from imported repositories."""

from datetime import timedelta

from sqlalchemy import select

from . import models as m
from .db import SessionLocal
from .schemas import TaskType


def seed(db):
    existing = db.scalar(
        select(m.Project).where(m.Project.repository == "synthetic/devflow-demo")
    )
    if existing:
        return {
            "project_id": existing.id,
            "created": False,
            "label": "synthetic/demo data",
        }
    now = m.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    project = m.Project(
        name="DevFlow 示例研发空间",
        repository="synthetic/devflow-demo",
        description="synthetic/demo data — 非真实企业业务数据",
        mode="demo",
    )
    db.add(project)
    db.flush()
    kinds = [t.value for t in TaskType]
    for i in range(42):
        created = now - timedelta(days=28 - i % 21)
        completed = created + timedelta(days=1 + i % 4)
        kind = kinds[i % 7]
        ai = i % 2 == 0
        req = m.Requirement(
            project_id=project.id,
            title=f"示例需求 {i+1}：{kind}",
            description="synthetic/demo data",
            change_count=i % 4,
            created_at=created - timedelta(days=2),
            completed_at=completed,
        )
        db.add(req)
        db.flush()
        issue = m.Issue(
            project_id=project.id,
            requirement_id=req.id,
            number=i + 1,
            title=req.title,
            author="demo-developer",
            labels=[kind, "synthetic"],
            state="closed" if i % 5 else "open",
            created_at=created,
            closed_at=completed if i % 5 else None,
        )
        db.add(issue)
        db.flush()
        task = m.Task(
            project_id=project.id,
            requirement_id=req.id,
            issue_id=issue.id,
            title=f"{kind} · 示例迭代 {i+1:02}",
            description="synthetic/demo data；用于验证链路和页面布局",
            task_type=kind,
            estimated_hours=4 + i % 3,
            actual_hours=2.5 + i % 5 + (1 if ai and i % 3 == 0 else 0),
            uses_ai=ai,
            rework_count=1 if i % 4 == 0 else 0,
            created_at=created,
            completed_at=completed,
        )
        db.add(task)
        db.flush()
        if ai:
            db.add(
                m.AIInteraction(
                    task_id=task.id,
                    tool=["Codex", "Copilot", "其他工具"][i % 3],
                    stage=kind,
                    purpose="synthetic/demo data：生成实现建议",
                    prompt_summary="脱敏摘要：请求边界条件建议",
                    suggestion_summary="给出候选实现与测试思路",
                    prompt_count=2,
                    suggestion_count=3,
                    accepted_count=1 + i % 3,
                    human_modification_count=i % 2,
                    modification_notes="示例：调整校验逻辑",
                    estimated_before_hours=5,
                    actual_hours=task.actual_hours,
                    quality_result="测试后评估",
                    created_at=created + timedelta(hours=1),
                )
            )
        commit = m.Commit(
            project_id=project.id,
            sha=f"{i+1:040x}",
            message=f"demo: {kind}",
            author="demo-developer",
            created_at=created + timedelta(hours=3),
        )
        pr = m.PullRequest(
            project_id=project.id,
            number=i + 1,
            title=f"示例 PR：{kind}",
            author="demo-developer",
            labels=["synthetic"],
            state="closed",
            created_at=created + timedelta(hours=4),
            first_review_at=created + timedelta(hours=6 + i % 6),
            merged_at=completed,
            closed_at=completed,
        )
        db.add_all([commit, pr])
        db.flush()
        db.add_all(
            [
                m.TaskCommit(task_id=task.id, commit_id=commit.id),
                m.TaskPR(task_id=task.id, pr_id=pr.id),
                m.PRIssue(pr_id=pr.id, issue_id=issue.id),
                m.PRCommit(pr_id=pr.id, commit_id=commit.id),
                m.TestResult(
                    task_id=task.id,
                    name="单元测试（synthetic）",
                    total=10,
                    passed=8 if i % 4 == 0 else 10,
                    created_at=created + timedelta(hours=8),
                ),
                m.Retrospective(
                    task_id=task.id,
                    summary="synthetic/demo data：边界测试应前置",
                    action_item="下轮先写验收条件",
                    created_at=completed,
                ),
            ]
        )
        if i % 4 == 0:
            db.add(
                m.Defect(
                    task_id=task.id,
                    title="示例边界条件缺陷",
                    severity="medium",
                    created_at=created + timedelta(hours=9),
                    resolved_at=completed,
                )
            )
            db.add(
                m.TestResult(
                    task_id=task.id,
                    name="修复后回归（synthetic）",
                    total=10,
                    passed=10,
                    created_at=completed,
                )
            )
    db.commit()
    return {"project_id": project.id, "created": True, "label": "synthetic/demo data"}


if __name__ == "__main__":
    with SessionLocal() as db:
        print(seed(db))
