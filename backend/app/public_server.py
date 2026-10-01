"""Rebuild disposable public demo data without copying a maintainer database."""

import os
import subprocess
import sys

import uvicorn

from .config import get_settings
from .db import SessionLocal
from .seed import seed

REPOSITORY = "xxu94420-commits/devflow-ai"


def import_public_repository():
    from .github import import_repository

    with SessionLocal() as db:
        import_repository(db, REPOSITORY, max_pages=1)


def prepare():
    settings = get_settings()
    if not settings.read_only:
        raise RuntimeError("Public demo startup requires READ_ONLY=true")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    with SessionLocal() as db:
        seed(db)
    if settings.demo_import_github:
        # Isolate network work and enforce a total startup budget. The import
        # transaction commits only when complete; termination leaves no half import.
        try:
            result = subprocess.run(
                [sys.executable, "-m", "app.public_server", "--import-only"],
                timeout=60,
                capture_output=True,
                check=False,
            )
            message = (
                "Public GitHub snapshot loaded."
                if result.returncode == 0
                else "Public GitHub import unavailable; Demo remains available."
            )
        except subprocess.TimeoutExpired:
            message = "Public GitHub import timed out; Demo remains available."
        # Never forward subprocess exceptions, responses, or credentials to logs.
        print(message, flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--import-only"]:
        import_public_repository()
    else:
        prepare()
        uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
