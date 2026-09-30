"""Bounded GitHub REST import; no inferred AI usage and no persisted secrets."""

import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from . import models as m
from .config import get_settings


class ImportFailure(Exception):
    def __init__(self, message, status=502):
        self.message, self.status = message, status


def timestamp(value):
    if not value:
        return None
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )


def request(client, path, params=None):
    for attempt in range(3):
        try:
            response = client.get(path, params=params)
        except httpx.RequestError:
            if attempt == 2:
                raise ImportFailure(
                    "GitHub 网络连接失败；未保存本轮数据，请稍后重试"
                ) from None
            time.sleep(0.15 * (attempt + 1))
            continue
        if response.status_code in (403, 429):
            reset = response.headers.get("x-ratelimit-reset", "unknown")
            raise ImportFailure(
                f"GitHub 限流或权限不足；稍后重试，配额重置 Unix 时间：{reset}", 429
            )
        if response.status_code == 404:
            raise ImportFailure("找不到公开仓库或缺少访问权限", 404)
        if response.status_code == 401:
            raise ImportFailure("GitHub Token 无效，请检查服务端环境变量", 401)
        if response.status_code == 409 and path.endswith("/commits"):
            return response, []  # Empty Git repository.
        if response.status_code >= 500 and attempt < 2:
            time.sleep(0.15 * (attempt + 1))
            continue
        if response.is_error:
            raise ImportFailure(
                f"GitHub 请求失败（HTTP {response.status_code}）；未保存本轮数据"
            )
        return response, response.json()
    raise ImportFailure("GitHub 请求失败")


def pages(client, path, limit, params=None):
    records = []
    truncated = False
    for page in range(1, limit + 1):
        response, data = request(
            client, path, {**(params or {}), "per_page": 100, "page": page}
        )
        records.extend(data)
        has_next = 'rel="next"' in response.headers.get("link", "")
        if not has_next:
            break
        if page == limit:
            truncated = True
    return records, truncated


def upsert(db, cls, keys, values):
    obj = db.scalar(select(cls).filter_by(**keys))
    if obj is None:
        obj = cls(**keys, **values)
        db.add(obj)
    else:
        for key, value in values.items():
            setattr(obj, key, value)
    db.flush()
    return obj


def import_repository(db, repository, max_pages=2, client=None):
    if client is None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = get_settings().github_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=20,
            follow_redirects=False,
        ) as connection:
            return import_repository(db, repository, max_pages, connection)
    prefix = f"/repos/{repository}"
    try:
        _, info = request(client, prefix)
        if info.get("private"):
            raise ImportFailure("本平台仅导入公开仓库", 422)
        repository = info["full_name"].lower()
        prefix = f"/repos/{info['full_name']}"
        existing = db.scalar(
            select(m.Project).where(m.Project.repository == repository)
        )
        if existing and existing.mode != "live":
            raise ImportFailure("仓库标识已被演示项目使用", 409)
        project = upsert(
            db,
            m.Project,
            {"repository": repository},
            {
                "name": info["name"],
                "description": info.get("description") or "",
                "mode": "live",
            },
        )
        issue_data, issue_cut = pages(
            client,
            prefix + "/issues",
            max_pages,
            {"state": "all", "sort": "created", "direction": "desc"},
        )
        pr_data, pr_cut = pages(
            client,
            prefix + "/pulls",
            max_pages,
            {"state": "all", "sort": "created", "direction": "desc"},
        )
        commit_data, commit_cut = pages(client, prefix + "/commits", max_pages)
        warnings = []
        for label, cut in [
            ("Issue", issue_cut),
            ("PR", pr_cut),
            ("Commit", commit_cut),
        ]:
            if cut:
                warnings.append(f"{label} 达到页数上限，非全量")
        issue_map = {}
        for value in issue_data:
            if "pull_request" in value:
                continue
            obj = upsert(
                db,
                m.Issue,
                {"project_id": project.id, "number": value["number"]},
                {
                    "title": value["title"],
                    "author": (value.get("user") or {}).get("login", ""),
                    "labels": [x["name"] for x in value.get("labels", [])],
                    "state": value["state"],
                    "url": value.get("html_url", ""),
                    "created_at": timestamp(value["created_at"]),
                    "closed_at": timestamp(value.get("closed_at")),
                },
            )
            issue_map[obj.number] = obj.id

        def save_commit(value):
            meta = value["commit"]
            return upsert(
                db,
                m.Commit,
                {"project_id": project.id, "sha": value["sha"]},
                {
                    "message": meta["message"],
                    "author": (value.get("author") or {}).get("login")
                    or (meta.get("author") or {}).get("name", ""),
                    "url": value.get("html_url", ""),
                    "created_at": timestamp(meta["committer"]["date"]),
                },
            )

        seen = set()
        for value in commit_data:
            seen.add(save_commit(value).sha)
        # A request budget keeps synchronous import bounded for public anonymous users.
        detailed = pr_data[:20]
        if len(pr_data) > 20:
            warnings.append("仅前20个 PR 获取评审和提交关系；其余 PR 的评审时间未知")
        for value in pr_data:
            first_review = None
            changes = None
            if value in detailed:
                reviews, cut = pages(
                    client, f"{prefix}/pulls/{value['number']}/reviews", max_pages
                )
                submitted = [
                    timestamp(x["submitted_at"])
                    for x in reviews
                    if x.get("submitted_at") and x.get("state") != "PENDING"
                ]
                first_review = min(submitted) if submitted else None
                changes, changes_cut = pages(
                    client, f"{prefix}/pulls/{value['number']}/commits", max_pages
                )
                if cut or changes_cut:
                    warnings.append(f"PR #{value['number']} 的评审或提交关系未完整采集")
            fields = {
                "title": value["title"],
                "author": (value.get("user") or {}).get("login", ""),
                "labels": [x["name"] for x in value.get("labels", [])],
                "state": value["state"],
                "url": value.get("html_url", ""),
                "created_at": timestamp(value["created_at"]),
                "closed_at": timestamp(value.get("closed_at")),
                "merged_at": timestamp(value.get("merged_at")),
            }
            if value in detailed:
                fields["first_review_at"] = first_review
            pr = upsert(
                db,
                m.PullRequest,
                {"project_id": project.id, "number": value["number"]},
                fields,
            )
            for change in changes or []:
                commit = save_commit(change)
                seen.add(commit.sha)
                if db.get(m.PRCommit, (pr.id, commit.id)) is None:
                    db.add(m.PRCommit(pr_id=pr.id, commit_id=commit.id))
            # Explicit local closing syntax is a textual reference,
            # not a verified closure event.
            refs = re.findall(
                r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b",
                value.get("body") or "",
                re.I,
            )
            for number in refs:
                ident = issue_map.get(int(number))
                if ident and db.get(m.PRIssue, (pr.id, ident)) is None:
                    db.add(m.PRIssue(pr_id=pr.id, issue_id=ident))
        project.imported_at = m.utcnow()
        project.import_note = (
            "; ".join(warnings)
            or "所请求列表分页已完成；Commit含默认分支及采集到的PR提交；"
            "不是所有分支历史"
        )
        db.commit()
        return {
            "project_id": project.id,
            "issues": len(issue_map),
            "pull_requests": len(pr_data),
            "commits": len(seen),
            "warnings": warnings,
            "coverage": project.import_note,
        }
    except Exception:
        db.rollback()
        raise
