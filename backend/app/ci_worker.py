"""Optional single-process polling, independent of visitor write permissions."""

import asyncio
import logging

from sqlalchemy import select

from . import models as m
from .ci import sync_project
from .config import get_settings
from .db import SessionLocal
from .github import ImportFailure

logger = logging.getLogger(__name__)


def sync_cycle():
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(m.Project.id)
                .where(m.Project.mode == "live")
                .order_by(m.Project.id)
                .limit(3)
            )
        )
    for project_id in ids:
        with SessionLocal() as db:
            project = db.get(m.Project, project_id)
            try:
                sync_project(db, project, max_runs=3)
            except Exception as exc:
                db.rollback()
                project = db.get(m.Project, project_id)
                project.ci_sync_note = (
                    exc.message
                    if isinstance(exc, ImportFailure)
                    else "CI同步暂不可用；保留上次成功记录"
                )
                db.commit()
                # Only the type is logged; no HTTP exception URLs/tokens/bodies.
                logger.warning("CI sync failed (%s)", type(exc).__name__)


async def poll():
    while True:
        try:
            await asyncio.to_thread(sync_cycle)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("CI cycle unavailable (%s)", type(exc).__name__)
        await asyncio.sleep(get_settings().ci_sync_interval_seconds)
