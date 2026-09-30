import re
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import utcnow

Text = Annotated[str, Field(min_length=1, max_length=200)]
Hours = Annotated[float, Field(ge=0, le=100000, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0, le=1000000)]


class TaskType(str, Enum):
    understanding = "需求理解"
    architecture = "架构设计"
    feature = "功能开发"
    testing = "测试生成"
    debugging = "Bug定位"
    refactoring = "代码重构"
    documentation = "文档编写"


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def dates(self):
        for key in type(self).model_fields:
            value = getattr(self, key)
            if isinstance(value, datetime) and value.tzinfo:
                setattr(self, key, value.astimezone(timezone.utc).replace(tzinfo=None))
        start = getattr(self, "created_at", None)
        for key in ("completed_at", "closed_at", "resolved_at", "first_review_at"):
            end = getattr(self, key, None)
            if start and end and end < start:
                raise ValueError(f"{key} cannot precede created_at")
        return self


class ProjectIn(Input):
    name: Text
    repository: Annotated[str, Field(pattern=r"^[\w.-]+/[\w.-]+$", max_length=300)]
    description: str = Field(default="", max_length=2000)
    mode: Literal["live", "demo"] = "live"


class RequirementIn(Input):
    project_id: int
    title: Text
    description: str = Field(default="", max_length=2000)
    change_count: Count = 0
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class TaskIn(Input):
    project_id: int
    requirement_id: int | None = None
    issue_id: int | None = None
    title: Text
    description: str = Field(default="", max_length=2000)
    task_type: TaskType
    estimated_hours: Hours
    actual_hours: Hours | None = None
    uses_ai: bool = False
    rework_count: Count = 0
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def completed_has_time(self):
        if self.completed_at and self.actual_hours is None:
            raise ValueError("Completed tasks require actual_hours")
        return self


class InteractionIn(Input):
    task_id: int
    tool: Text
    stage: TaskType
    purpose: str = Field(min_length=1, max_length=500)
    prompt_summary: str = Field(min_length=1, max_length=1000)
    suggestion_summary: str = Field(default="", max_length=1000)
    prompt_count: Annotated[int, Field(ge=1, le=100000)] = 1
    suggestion_count: Count = 1
    accepted_count: Count = 0
    human_modification_count: Count = 0
    modification_notes: str = Field(default="", max_length=1000)
    estimated_before_hours: Hours
    actual_hours: Hours
    quality_result: str = Field(default="未评估", max_length=500)
    notes: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def safe_summary(self):
        if self.accepted_count > self.suggestion_count:
            raise ValueError("accepted_count exceeds suggestion_count")
        text = " ".join(v for v in self.model_dump().values() if isinstance(v, str))
        if re.search(
            r"(gh[pousr]_[A-Za-z0-9]{15,}|github_pat_|sk-[A-Za-z0-9]{15,}|"
            r"-----BEGIN .*PRIVATE KEY|Bearer\s+[A-Za-z0-9._-]{15,})",
            text,
        ):
            raise ValueError("Possible secret detected. Submit redacted summaries only")
        return self


class TestIn(Input):
    task_id: int
    name: Text
    passed: Count
    total: Annotated[int, Field(ge=1, le=1000000)]
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def valid_counts(self):
        if self.passed > self.total:
            raise ValueError("passed exceeds total")
        return self


class DefectIn(Input):
    task_id: int
    title: Text
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None


class RetroIn(Input):
    task_id: int
    summary: str = Field(min_length=1, max_length=2000)
    action_item: str = Field(min_length=1, max_length=1000)
    created_at: datetime = Field(default_factory=utcnow)


class LinksIn(Input):
    commit_ids: list[int] = Field(default_factory=list, max_length=200)
    pr_ids: list[int] = Field(default_factory=list, max_length=200)


class ImportIn(Input):
    repository: Annotated[str, Field(pattern=r"^[\w.-]+/[\w.-]+$", max_length=300)]
    max_pages: Annotated[int, Field(ge=1, le=10)] = 2
