"""Public stateless trial. Never writes visitor text or findings to the database."""

import threading
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from .config import get_settings
from .review_contract import PROMPT_VERSION
from .review_provider import ReviewFailure, connection, generate
from .schemas import Input


class TrialInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    acceptance_criteria: str = Field(default="", max_length=1000)
    consent: Literal[True]


class TrialBudget:
    """Single-process abuse guard, not a persistent monetary spending limit."""

    def __init__(self):
        self.lock = threading.Lock()
        self.day = ""
        self.count = 0
        self.last = 0.0

    def acquire(self, limit):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(429, "已有评估正在处理，请稍后再试")
        day = datetime.now(timezone.utc).date().isoformat()
        if day != self.day:
            self.day, self.count = day, 0
        if self.count >= limit or time.monotonic() - self.last < 15:
            self.lock.release()
            raise HTTPException(429, "试用频率或当日额度已达上限，请稍后重试或查看示例")
        self.count += 1
        self.last = time.monotonic()


budget = TrialBudget()


def status():
    enabled = get_settings().public_review_enabled
    try:
        config = connection("cloud")
        ready = True
    except (ReviewFailure, ValueError):
        config, ready = {}, False
    return {
        "enabled": enabled,
        "configured": ready,
        "model": config.get("model", ""),
        "destination": config.get("url", ""),
        "daily_limit": get_settings().public_review_daily_limit,
        "prompt_version": PROMPT_VERSION,
    }


def evaluate(data):
    if not get_settings().public_review_enabled:
        raise HTTPException(403, "公网AI试用尚未开启")
    try:
        config = connection("cloud")
    except (ReviewFailure, ValueError):
        raise HTTPException(503, "尚未连接模型；可以先查看明确标注的离线示例") from None
    budget.acquire(get_settings().public_review_daily_limit)
    started = time.monotonic()
    try:
        source = data.model_dump(exclude={"consent"}) | {"version": 1}
        findings, usage = generate(source, config)
        return {
            "status": "succeeded",
            "findings": findings,
            "usage": usage,
            "model": config["model"],
            "provider": config["url"],
            "prompt_version": PROMPT_VERSION,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "stored": False,
        }
    except ReviewFailure as exc:
        raise HTTPException(
            502, f"模型评估未完成（{exc.code}）；未生成替代结果"
        ) from None
    except Exception:
        raise HTTPException(502, "模型评估暂不可用；未生成替代结果") from None
    finally:
        budget.lock.release()
