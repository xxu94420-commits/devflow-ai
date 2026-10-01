"""Versioned human review workflow; model output never edits requirements."""

import time
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .review_contract import PROMPT_VERSION, fingerprint, snapshot
from .review_provider import ReviewFailure, connection, connections, generate
from .schemas import Input, RequirementUpdate

router = APIRouter()


class ReviewRequest(Input):
    expected_version: int = Field(ge=1)
    provider: Literal["cloud", "ollama"]
    request_key: UUID
    consent: Literal[True]


class DecisionRequest(Input):
    decision: Literal["accepted", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


def require(db, cls, ident):
    value = db.get(cls, ident)
    if value is None:
        raise HTTPException(404, "记录不存在")
    return value


def row(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def save_revision(db, obj, reason):
    if not db.scalar(
        select(m.RequirementRevision.id).where(
            m.RequirementRevision.requirement_id == obj.id,
            m.RequirementRevision.version == obj.version,
        )
    ):
        db.add(
            m.RequirementRevision(
                requirement_id=obj.id,
                version=obj.version,
                snapshot=snapshot(obj),
                reason=reason,
            )
        )


def edit_requirement(db, obj, data: RequirementUpdate):
    if obj.project_id != data.project_id:
        raise HTTPException(422, "不能改变需求所属项目")
    if obj.version != data.expected_version:
        raise HTTPException(409, "需求已更新，请刷新后再编辑")
    save_revision(db, obj, "首次纳入版本记录；不推断此前历史")
    values = data.model_dump(exclude={"expected_version", "revision_reason"})
    values["version"] = obj.version + 1
    values["change_count"] = max(obj.change_count + 1, data.change_count)
    result = db.execute(
        update(m.Requirement)
        .where(
            m.Requirement.id == obj.id,
            m.Requirement.version == data.expected_version,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "需求已更新，请刷新后再编辑")
    db.refresh(obj)
    save_revision(db, obj, data.revision_reason)
    db.commit()
    return row(obj)


def review_row(db, obj, req):
    result = row(obj)
    result["stale"] = obj.snapshot["version"] != req.version
    result["decisions"] = [
        row(d)
        for d in db.scalars(
            select(m.ReviewDecision)
            .where(m.ReviewDecision.review_id == obj.id)
            .order_by(m.ReviewDecision.finding_index)
        )
    ]
    if obj.status == "pending" and obj.created_at < m.utcnow() - timedelta(minutes=5):
        result["status"] = "interrupted"
        result["error_code"] = "interrupted"
    return result


@router.get("/api/review/connections")
def list_connections():
    return {"connections": connections(), "prompt_version": PROMPT_VERSION}


@router.get("/api/requirements")
def list_requirements(
    mode: Literal["demo", "live"] = "demo",
    project_id: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(m.Requirement).join(m.Project).where(m.Project.mode == mode)
    if project_id is not None:
        query = query.where(m.Requirement.project_id == project_id)
    return [
        row(r)
        for r in db.scalars(
            query.order_by(m.Requirement.id.desc()).limit(limit).offset(offset)
        )
    ]


@router.get("/api/requirements/{ident}/reviews")
def history(ident: int, db: Session = Depends(get_db)):
    req = require(db, m.Requirement, ident)
    return {
        "requirement": row(req),
        "reviews": [
            review_row(db, r, req)
            for r in db.scalars(
                select(m.RequirementReview)
                .where(m.RequirementReview.requirement_id == ident)
                .order_by(m.RequirementReview.id.desc())
                .limit(50)
            )
        ],
        "revisions": [
            row(r)
            for r in db.scalars(
                select(m.RequirementRevision)
                .where(m.RequirementRevision.requirement_id == ident)
                .order_by(m.RequirementRevision.version.desc())
                .limit(50)
            )
        ],
        "tasks": [
            row(t)
            for t in db.scalars(select(m.Task).where(m.Task.requirement_id == ident))
        ],
    }


def start_review(ident, data, db):
    req = require(db, m.Requirement, ident)
    previous = db.scalar(
        select(m.RequirementReview).where(
            m.RequirementReview.request_key == str(data.request_key)
        )
    )
    if previous:
        if (
            previous.requirement_id != ident
            or previous.snapshot["version"] != data.expected_version
        ):
            raise HTTPException(409, "请求标识已用于其他需求或版本")
        return review_row(db, previous, req)
    if req.version != data.expected_version:
        raise HTTPException(409, "需求已更新，请刷新后再评估")
    try:
        config = connection(data.provider)
    except (ReviewFailure, ValueError):
        raise HTTPException(
            503, "尚未配置该模型连接，请由维护者设置服务端环境变量"
        ) from None
    recent = db.scalar(
        select(m.RequirementReview.id).where(
            m.RequirementReview.requirement_id == ident,
            m.RequirementReview.created_at > m.utcnow() - timedelta(seconds=100),
        )
    )
    if recent:
        raise HTTPException(429, "请稍后再评估，避免重复调用；可以先查看历史结果")
    source = snapshot(req)
    obj = m.RequirementReview(
        requirement_id=ident,
        request_key=str(data.request_key),
        snapshot=source,
        input_hash=fingerprint(source),
        prompt_version=PROMPT_VERSION,
        model=config["model"],
        provider=config["url"],
        status="pending",
    )
    db.add(obj)
    db.commit()  # Reserve idempotency key before any billable network request.
    started = time.monotonic()
    try:
        obj.findings, obj.usage = generate(source, config)
        obj.status = "succeeded"
    except ReviewFailure as exc:
        obj.status, obj.error_code = "failed", exc.code
    except Exception:
        obj.status, obj.error_code = "failed", "internal_error"
    obj.duration_ms = int((time.monotonic() - started) * 1000)
    obj.completed_at = m.utcnow()
    db.commit()
    db.refresh(req)
    return review_row(db, obj, req)


def decide(review_id, index, data, db):
    review = require(db, m.RequirementReview, review_id)
    req = require(db, m.Requirement, review.requirement_id)
    if review.status != "succeeded" or review.snapshot["version"] != req.version:
        raise HTTPException(409, "只能确认当前版本的成功评估；旧记录仅供回看")
    if index < 0 or index >= len(review.findings):
        raise HTTPException(404, "建议不存在")
    if not data.reason.strip():
        raise HTTPException(422, "请填写确认或驳回的原因")
    obj = m.ReviewDecision(
        review_id=review_id,
        finding_index=index,
        decision=data.decision,
        reason=data.reason.strip(),
    )
    db.add(obj)
    db.commit()  # Unique key makes each human decision immutable.
    return row(obj)
