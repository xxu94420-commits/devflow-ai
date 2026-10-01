import hmac
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .config import get_settings
from .db import get_db
from .metrics import analyze

app = FastAPI(title="DevFlow AI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never reflect input: invalid summaries may contain secrets.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ]
        },
    )


@app.exception_handler(IntegrityError)
async def duplicate_error(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "记录重复或关联不存在"})


def write_access(x_api_key: str = Header(default="")):
    expected = get_settings().devflow_api_key
    if expected and not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(401, "写入需要有效 X-API-Key")


def row(obj):
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def require(db, cls, ident):
    value = db.get(cls, ident)
    if value is None:
        raise HTTPException(404, f"{cls.__name__} 不存在")
    return value


def store(db, cls, data):
    obj = cls(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return row(obj)


def validate_task(db, data):
    require(db, m.Project, data.project_id)
    for cls, ident in [(m.Requirement, data.requirement_id), (m.Issue, data.issue_id)]:
        if ident is not None and require(db, cls, ident).project_id != data.project_id:
            raise HTTPException(422, "关联实体必须属于同一个项目")
    if data.issue_id and data.requirement_id:
        issue = require(db, m.Issue, data.issue_id)
        if issue.requirement_id not in (None, data.requirement_id):
            raise HTTPException(422, "Issue 与任务的需求归属不一致")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(m.Project.id).limit(1))
    return {"status": "ok"}


@app.get("/api/task-types")
def task_types():
    return [t.value for t in s.TaskType]


@app.post("/api/demo/seed", dependencies=[Depends(write_access)])
def demo_seed(db: Session = Depends(get_db)):
    from .seed import seed

    return seed(db)


@app.get("/api/projects")
def projects(mode: Literal["live", "demo"] = "demo", db: Session = Depends(get_db)):
    return [row(p) for p in db.scalars(select(m.Project).where(m.Project.mode == mode))]


@app.post("/api/projects", dependencies=[Depends(write_access)], status_code=201)
def create_project(data: s.ProjectIn, db: Session = Depends(get_db)):
    return store(db, m.Project, data)


@app.get("/api/projects/{project_id}")
def project_detail(project_id: int, db: Session = Depends(get_db)):
    p = require(db, m.Project, project_id)
    result = row(p)
    for name, cls in [
        ("issues", m.Issue),
        ("commits", m.Commit),
        ("pull_requests", m.PullRequest),
        ("requirements", m.Requirement),
    ]:
        result[name] = [
            row(x) for x in db.scalars(select(cls).where(cls.project_id == p.id))
        ]
    return result


@app.post("/api/requirements", dependencies=[Depends(write_access)], status_code=201)
def create_requirement(data: s.RequirementIn, db: Session = Depends(get_db)):
    require(db, m.Project, data.project_id)
    return store(db, m.Requirement, data)


@app.put("/api/requirements/{ident}", dependencies=[Depends(write_access)])
def update_requirement(
    ident: int, data: s.RequirementIn, db: Session = Depends(get_db)
):
    obj = require(db, m.Requirement, ident)
    if data.project_id != obj.project_id:
        raise HTTPException(422, "不能改变需求的项目")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    db.commit()
    return row(obj)


@app.put(
    "/api/issues/{issue_id}/requirement/{requirement_id}",
    dependencies=[Depends(write_access)],
)
def link_requirement(issue_id: int, requirement_id: int, db: Session = Depends(get_db)):
    issue = require(db, m.Issue, issue_id)
    req = require(db, m.Requirement, requirement_id)
    if issue.project_id != req.project_id:
        raise HTTPException(422, "关联实体必须属于同一个项目")
    linked = db.scalars(select(m.Task).where(m.Task.issue_id == issue_id)).all()
    if any(t.requirement_id not in (None, req.id) for t in linked):
        raise HTTPException(422, "现有任务关联了其他需求")
    issue.requirement_id = req.id
    db.commit()
    return row(issue)


@app.get("/api/tasks")
def tasks(
    mode: Literal["live", "demo"] = "demo",
    project_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = select(m.Task).join(m.Project).where(m.Project.mode == mode)
    if project_id is not None:
        query = query.where(m.Task.project_id == project_id)
    return [row(t) for t in db.scalars(query.order_by(m.Task.created_at.desc()))]


@app.post("/api/tasks", dependencies=[Depends(write_access)], status_code=201)
def create_task(data: s.TaskIn, db: Session = Depends(get_db)):
    validate_task(db, data)
    return store(db, m.Task, data)


@app.put("/api/tasks/{task_id}", dependencies=[Depends(write_access)])
def update_task(task_id: int, data: s.TaskIn, db: Session = Depends(get_db)):
    obj = require(db, m.Task, task_id)
    validate_task(db, data)
    if data.project_id != obj.project_id:
        raise HTTPException(422, "不能移动已有任务到其他项目")
    if not data.uses_ai and db.scalar(
        select(m.AIInteraction.id).where(m.AIInteraction.task_id == task_id).limit(1)
    ):
        raise HTTPException(422, "已有 AI 记录的任务必须保留 AI 标记")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    db.commit()
    return row(obj)


@app.post("/api/interactions", dependencies=[Depends(write_access)], status_code=201)
def create_interaction(data: s.InteractionIn, db: Session = Depends(get_db)):
    task = require(db, m.Task, data.task_id)
    task.uses_ai = True
    return store(db, m.AIInteraction, data)


@app.post("/api/tests", dependencies=[Depends(write_access)], status_code=201)
def create_test(data: s.TestIn, db: Session = Depends(get_db)):
    require(db, m.Task, data.task_id)
    return store(db, m.TestResult, data)


@app.post("/api/defects", dependencies=[Depends(write_access)], status_code=201)
def create_defect(data: s.DefectIn, db: Session = Depends(get_db)):
    require(db, m.Task, data.task_id)
    return store(db, m.Defect, data)


@app.put("/api/defects/{ident}", dependencies=[Depends(write_access)])
def update_defect(ident: int, data: s.DefectIn, db: Session = Depends(get_db)):
    obj = require(db, m.Defect, ident)
    if obj.task_id != data.task_id:
        raise HTTPException(422, "不能移动缺陷到其他任务")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    db.commit()
    return row(obj)


@app.post("/api/retrospectives", dependencies=[Depends(write_access)], status_code=201)
def create_retro(data: s.RetroIn, db: Session = Depends(get_db)):
    require(db, m.Task, data.task_id)
    return store(db, m.Retrospective, data)


@app.put("/api/tasks/{task_id}/links", dependencies=[Depends(write_access)])
def task_links(task_id: int, data: s.LinksIn, db: Session = Depends(get_db)):
    task = require(db, m.Task, task_id)
    for ids, cls, link_cls, column in [
        (data.commit_ids, m.Commit, m.TaskCommit, "commit_id"),
        (data.pr_ids, m.PullRequest, m.TaskPR, "pr_id"),
    ]:
        for ident in set(ids):
            if require(db, cls, ident).project_id != task.project_id:
                raise HTTPException(422, "关联实体必须属于同一个项目")
            if db.get(link_cls, (task_id, ident)) is None:
                db.add(link_cls(task_id=task_id, **{column: ident}))
    db.commit()
    return {"status": "linked"}


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: int, db: Session = Depends(get_db)):
    task = require(db, m.Task, task_id)
    result = row(task)
    timeline = []

    def event(kind, obj, title, at=None):
        timeline.append(
            {"kind": kind, "id": obj.id, "title": title, "at": at or obj.created_at}
        )

    event("task", task, task.title)
    issue = db.get(m.Issue, task.issue_id) if task.issue_id else None
    req_id = task.requirement_id or (issue.requirement_id if issue else None)
    req = db.get(m.Requirement, req_id) if req_id else None
    result["requirement"] = row(req) if req else None
    result["issue"] = row(issue) if issue else None
    if req:
        event("requirement", req, req.title)
    if issue:
        event("issue", issue, issue.title)
    for key, cls in [
        ("interactions", m.AIInteraction),
        ("tests", m.TestResult),
        ("defects", m.Defect),
        ("retrospectives", m.Retrospective),
    ]:
        records = list(db.scalars(select(cls).where(cls.task_id == task_id)))
        result[key] = [row(x) for x in records]
        for x in records:
            title = (
                getattr(x, "title", None)
                or getattr(x, "name", None)
                or getattr(x, "purpose", None)
                or getattr(x, "summary", "")
            )
            event(key, x, title)
            if isinstance(x, m.Defect) and x.resolved_at:
                event("defect_resolved", x, x.title, x.resolved_at)
    for key, cls, link, foreign in [
        ("commits", m.Commit, m.TaskCommit, m.TaskCommit.commit_id),
        ("pull_requests", m.PullRequest, m.TaskPR, m.TaskPR.pr_id),
    ]:
        records = db.scalars(
            select(cls).join(link, cls.id == foreign).where(link.task_id == task_id)
        ).all()
        result[key] = [row(x) for x in records]
        for x in records:
            event(key, x, getattr(x, "title", None) or x.message)
    if task.completed_at:
        event("completed", task, "任务完成", task.completed_at)
    result["timeline"] = sorted(timeline, key=lambda e: (e["at"], e["id"]))
    result["ai_summary"] = {
        "tools": sorted({i["tool"] for i in result["interactions"]}),
        "stages": sorted({i["stage"] for i in result["interactions"]}),
        **{
            k: sum(i[k] for i in result["interactions"])
            for k in ["prompt_count", "accepted_count", "human_modification_count"]
        },
    }
    tests = sorted(result["tests"], key=lambda x: (x["created_at"], x["id"]))
    result["first_test_passed"] = (
        tests[0]["passed"] == tests[0]["total"] if tests else None
    )
    result["defect_count"] = len(result["defects"])
    return result


def window(start: datetime | None = None, end: datetime | None = None):
    end = end or m.utcnow()
    start = start or end - timedelta(days=30)
    start = (
        start.astimezone(timezone.utc).replace(tzinfo=None) if start.tzinfo else start
    )
    end = end.astimezone(timezone.utc).replace(tzinfo=None) if end.tzinfo else end
    if not start < end or end - start > timedelta(days=366):
        raise HTTPException(422, "时间范围须大于0且不超过366天；结束时间不包含在窗口内")
    return start, end


@app.get("/api/metrics")
def metrics(
    mode: Literal["live", "demo"] = "demo",
    project_id: int | None = None,
    dates: tuple = Depends(window),
    db: Session = Depends(get_db),
):
    return analyze(db, mode, *dates, project_id)


@app.post("/api/github/import", dependencies=[Depends(write_access)])
def github_import(data: s.ImportIn, db: Session = Depends(get_db)):
    from .github import ImportFailure, import_repository

    try:
        return import_repository(db, data.repository, data.max_pages)
    except ImportFailure as exc:
        raise HTTPException(exc.status, exc.message) from None


@app.get("/api/reports")
def get_report(
    mode: Literal["live", "demo"] = "demo",
    project_id: int | None = None,
    dates: tuple = Depends(window),
    db: Session = Depends(get_db),
):
    from .reports import report

    return report(db, mode, *dates, project_id)


@app.get("/api/reports/download")
def download_report(
    mode: Literal["live", "demo"] = "demo",
    project_id: int | None = None,
    dates: tuple = Depends(window),
    db: Session = Depends(get_db),
):
    from .reports import report

    markdown = report(db, mode, *dates, project_id)["markdown"]
    filename = f"devflow-{mode}-{dates[0].date().isoformat()}.md"
    return Response(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
