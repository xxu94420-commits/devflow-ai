from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    repository: Mapped[str] = mapped_column(String(300), unique=True)
    description: Mapped[str] = mapped_column(default="")
    mode: Mapped[str] = mapped_column(String(10), default="live")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime)
    import_note: Mapped[str] = mapped_column(default="")


class Requirement(Base):
    __tablename__ = "requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(default="")
    change_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("project_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    requirement_id: Mapped[int | None] = mapped_column(ForeignKey("requirements.id"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(200), default="")
    labels: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(20), default="open")
    url: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    requirement_id: Mapped[int | None] = mapped_column(ForeignKey("requirements.id"))
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(default="")
    task_type: Mapped[str] = mapped_column(String(40))
    estimated_hours: Mapped[float] = mapped_column(Float)
    actual_hours: Mapped[float | None] = mapped_column(Float)
    uses_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    rework_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class AIInteraction(Base):
    __tablename__ = "ai_interactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    tool: Mapped[str] = mapped_column(String(100))
    stage: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(500))
    prompt_summary: Mapped[str] = mapped_column(String(1000))
    suggestion_summary: Mapped[str] = mapped_column(String(1000), default="")
    prompt_count: Mapped[int] = mapped_column(default=1)
    suggestion_count: Mapped[int] = mapped_column(default=1)
    accepted_count: Mapped[int] = mapped_column(default=0)
    human_modification_count: Mapped[int] = mapped_column(default=0)
    modification_notes: Mapped[str] = mapped_column(String(1000), default="")
    estimated_before_hours: Mapped[float] = mapped_column(Float)
    actual_hours: Mapped[float] = mapped_column(Float)
    quality_result: Mapped[str] = mapped_column(String(500), default="未评估")
    notes: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("project_id", "sha"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    sha: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(default="")
    author: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("project_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(200), default="")
    labels: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(20), default="open")
    url: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    first_review_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime)


class TaskCommit(Base):
    __tablename__ = "task_commits"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    commit_id: Mapped[int] = mapped_column(ForeignKey("commits.id"), primary_key=True)


class TaskPR(Base):
    __tablename__ = "task_prs"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), primary_key=True)


class PRCommit(Base):
    __tablename__ = "pr_commits"
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), primary_key=True)
    commit_id: Mapped[int] = mapped_column(ForeignKey("commits.id"), primary_key=True)


class PRIssue(Base):
    __tablename__ = "pr_issues"
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), primary_key=True)


class TestResult(Base):
    __tablename__ = "test_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    passed: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Defect(Base):
    __tablename__ = "defects"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class Retrospective(Base):
    __tablename__ = "retrospectives"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    summary: Mapped[str] = mapped_column(String(2000))
    action_item: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
