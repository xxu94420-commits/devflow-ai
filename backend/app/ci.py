"""Pull bounded GitHub Actions evidence, preserving unknowns and run attempts."""

import time
from contextlib import nullcontext
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from . import models as m
from .config import get_settings
from .github import ImportFailure, request, timestamp, upsert
from .junit import MAX_ARCHIVE, EvidenceError, parse_bundle


def reconcile(db, run):
    """Only an explicit, unique task relationship can enter task metrics."""
    commit_tasks = db.scalars(
        select(m.Task.id)
        .join(m.TaskCommit, m.TaskCommit.task_id == m.Task.id)
        .join(m.Commit, m.Commit.id == m.TaskCommit.commit_id)
        .where(
            m.Task.project_id == run.project_id,
            m.Commit.project_id == run.project_id,
            m.Commit.sha == run.head_sha,
        )
    ).all()
    pr_tasks = db.scalars(
        select(m.Task.id)
        .join(m.TaskPR, m.TaskPR.task_id == m.Task.id)
        .join(m.PullRequest, m.PullRequest.id == m.TaskPR.pr_id)
        .where(
            m.Task.project_id == run.project_id,
            m.PullRequest.project_id == run.project_id,
            m.PullRequest.number.in_(run.pr_numbers),
        )
    ).all()
    candidates = sorted(set(commit_tasks) | set(pr_tasks))
    run.candidate_task_ids = candidates
    if run.association != "manual":
        run.task_id = candidates[0] if len(candidates) == 1 else None
        run.association = (
            "automatic"
            if len(candidates) == 1
            else ("ambiguous" if candidates else "unlinked")
        )
    previous = db.scalar(select(m.TestResult).where(m.TestResult.ci_run_id == run.id))
    total = sum(getattr(run, field) or 0 for field in ["passed", "failed", "errors"])
    eligible = (
        run.task_id is not None
        and run.evidence_status == "available"
        and run.status == "completed"
        and total > 0
    )
    if eligible:
        if previous is None:
            previous = m.TestResult(ci_run_id=run.id)
            db.add(previous)
        previous.task_id = run.task_id
        previous.name = f"GitHub Actions #{run.run_id} / attempt {run.attempt}"
        previous.passed, previous.total = run.passed, total
        previous.created_at = run.completed_at or run.created_at
    elif previous is not None:
        db.delete(previous)


def reconcile_project(db, project_id):
    for run in db.scalars(select(m.CIRun).where(m.CIRun.project_id == project_id)):
        reconcile(db, run)


def download_archive(client, prefix, artifact_id, download_client=None):
    # Never automatically forward the API's bearer token to a signed CDN URL.
    response = client.get(
        f"{prefix}/actions/artifacts/{artifact_id}/zip", follow_redirects=False
    )
    if response.status_code in (401, 403):
        raise EvidenceError("auth_required")
    if response.status_code in (404, 410):
        raise EvidenceError("expired")
    if response.status_code != 302:
        raise EvidenceError("download_failed")
    url = response.headers.get("location", "")
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not any(
            hostname.endswith(suffix)
            for suffix in (
                ".blob.core.windows.net",
                ".actions.githubusercontent.com",
                ".githubusercontent.com",
            )
        )
    ):
        raise EvidenceError("unsafe_redirect")
    context = (
        nullcontext(download_client) if download_client else httpx.Client(timeout=8)
    )
    with context as downloader:
        with downloader.stream("GET", url, follow_redirects=False) as archive:
            if archive.status_code != 200:
                raise EvidenceError("download_failed")
            chunks, length = [], 0
            for chunk in archive.iter_bytes():
                length += len(chunk)
                if length > MAX_ARCHIVE:
                    raise EvidenceError("archive_too_large")
                chunks.append(chunk)
            return b"".join(chunks)


def collect_evidence(db, run, client, prefix, fetch, download_client=None):
    # Completed immutable artifacts already parsed need no repeat download, even
    # after GitHub expires the archive. Keep digest, attribution and counts.
    if run.digest and run.evidence_status == "available":
        return
    if run.status != "completed":
        run.evidence_status, run.note = "pending", "工作流尚未结束，计数未定"
        return
    name = f"devflow-junit-{run.attempt}"
    data = fetch(
        f"{prefix}/actions/runs/{run.run_id}/artifacts", {"per_page": 100, "name": name}
    )
    artifacts = [a for a in data.get("artifacts", []) if a["name"] == name]
    if len(artifacts) != 1:
        run.evidence_status, run.note = "missing", "未找到唯一的本次attempt报告"
        return
    artifact = artifacts[0]
    run.artifact_id = artifact["id"]
    if artifact.get("expired"):
        run.evidence_status, run.note = "expired", "报告已过期，用例数量未知"
        return
    if not client.headers.get("Authorization"):
        run.evidence_status, run.note = (
            "auth_required",
            "下载JUnit需要服务端Actions读取权限",
        )
        return
    if artifact.get("workflow_run", {}).get("head_sha", run.head_sha) != run.head_sha:
        run.evidence_status, run.note = "invalid", "报告SHA与运行不一致"
        return
    try:
        if artifact.get("size_in_bytes", 0) > MAX_ARCHIVE:
            raise EvidenceError("archive_too_large")
        content = download_archive(client, prefix, artifact["id"], download_client)
        result = parse_bundle(content)
        if artifact.get("digest") and artifact["digest"] != result["digest"]:
            raise EvidenceError("digest_mismatch")
        for key in ["passed", "failed", "errors", "skipped", "reports", "digest"]:
            setattr(run, key, result[key])
        run.evidence_status = "available" if result["complete"] else "partial"
        run.note = (
            "完整JUnit；跳过不计通过；运行成功不等于全部测试通过"
            if result["complete"]
            else "报告不完整，已知计数不进入任务指标"
        )
    except (EvidenceError, httpx.RequestError) as exc:
        state = str(exc) if isinstance(exc, EvidenceError) else "download_failed"
        run.evidence_status = (
            state if state in ("auth_required", "expired") else "invalid"
        )
        run.note = "报告不可用或校验失败；未推断任何用例结果"


def sync_project(db, project, max_runs=3, client=None, download_client=None):
    if project.mode != "live":
        raise ImportFailure("仅Live项目可同步GitHub Actions", 422)
    headers = {"Accept": "application/vnd.github+json"}
    if get_settings().github_token:
        headers["Authorization"] = f"Bearer {get_settings().github_token}"
    context = (
        nullcontext(client)
        if client
        else httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=8,
            follow_redirects=False,
        )
    )
    prefix = f"/repos/{project.repository}"
    try:
        with context as api:
            deadline, calls = time.monotonic() + 45, 0

            def fetch(path, params=None):
                nonlocal calls
                calls += 1
                if calls > 40 or time.monotonic() > deadline:
                    raise ImportFailure(
                        "CI同步达到请求/时间预算，请减少单次运行数量", 503
                    )
                return request(api, path, params)[1]

            if fetch(prefix).get("private", True):
                raise ImportFailure("仅允许读取公开仓库", 422)
            listing = fetch(prefix + "/actions/runs", {"per_page": max_runs})
            seen = 0
            for current in listing.get("workflow_runs", [])[:max_runs]:
                latest = int(current.get("run_attempt", 1))
                # Backfill at most two previous attempts; no claim of all history.
                for attempt in range(max(1, latest - 2), latest + 1):
                    raw = (
                        current
                        if attempt == latest
                        else fetch(
                            f"{prefix}/actions/runs/{current['id']}/attempts/{attempt}"
                        )
                    )
                    run = upsert(
                        db,
                        m.CIRun,
                        {
                            "project_id": project.id,
                            "run_id": raw["id"],
                            "attempt": attempt,
                        },
                        {
                            "name": (raw.get("name") or "workflow")[:200],
                            "head_sha": raw["head_sha"],
                            "branch": raw.get("head_branch") or "",
                            "event": raw.get("event", ""),
                            "status": raw["status"],
                            "conclusion": raw.get("conclusion"),
                            "url": f"https://github.com/{project.repository}/actions/runs/{raw['id']}/attempts/{attempt}",
                            "pr_numbers": [
                                p["number"] for p in raw.get("pull_requests", [])
                            ],
                            "created_at": timestamp(
                                raw.get("run_started_at") or raw["created_at"]
                            ),
                            "synced_at": m.utcnow(),
                        },
                    )
                    jobs = fetch(
                        f"{prefix}/actions/runs/{run.run_id}/attempts/{attempt}/jobs",
                        {"per_page": 100},
                    )
                    run.jobs = [
                        {
                            k: j.get(k)
                            for k in [
                                "id",
                                "name",
                                "status",
                                "conclusion",
                                "started_at",
                                "completed_at",
                            ]
                        }
                        for j in jobs.get("jobs", [])
                    ]
                    completed = [
                        timestamp(j["completed_at"])
                        for j in run.jobs
                        if j.get("completed_at")
                    ]
                    run.completed_at = (
                        max(completed)
                        if completed and run.status == "completed"
                        else None
                    )
                    collect_evidence(db, run, api, prefix, fetch, download_client)
                    if jobs.get("total_count", 0) > 100:
                        run.note += "；作业列表超过100，展示截断"
                    reconcile(db, run)
                    seen += 1
            project.ci_synced_at = m.utcnow()
            project.ci_sync_note = (
                f"本轮读取最近{max_runs}个运行中的{seen}次attempt；"
                "每run最多回溯3次attempt，每次最多100个job；非全量历史。"
            )
            db.commit()
            return {"runs": seen, "note": project.ci_sync_note}
    except Exception:
        db.rollback()
        raise
