from collections import Counter
from datetime import timedelta
from math import sqrt
from statistics import mean

from sqlalchemy import select

from . import models as m
from .schemas import TaskType


def average(values):
    return round(mean(values), 3) if values else None


def ratio(a, b):
    return round(a / b * 100, 2) if b else None


def metric(value, n, unit, note=""):
    return {
        "value": value,
        "n": n,
        "unit": unit,
        "confidence": "无样本" if n == 0 else "样本不足" if n < 5 else "仅描述性统计",
        "note": note,
    }


def analyze(db, mode, start, end, project_id=None):
    def within(value):
        return value is not None and start <= value < end

    projects = db.scalars(select(m.Project).where(m.Project.mode == mode)).all()
    if project_id is not None:
        projects = [p for p in projects if p.id == project_id]
    pids = [p.id for p in projects]

    def project_rows(cls):
        return list(db.scalars(select(cls).where(cls.project_id.in_(pids))))

    requirements = project_rows(m.Requirement)
    delivered = [r for r in requirements if within(r.completed_at)]
    issues = [i for i in project_rows(m.Issue) if within(i.created_at)]
    prs = project_rows(m.PullRequest)
    reviewed = [p for p in prs if within(p.first_review_at)]
    commits = [c for c in project_rows(m.Commit) if within(c.created_at)]
    all_tasks = project_rows(m.Task)
    tasks = [t for t in all_tasks if within(t.completed_at)]
    tids = [t.id for t in all_tasks]
    completed_ids = {t.id for t in tasks}

    def task_rows(cls):
        return list(db.scalars(select(cls).where(cls.task_id.in_(tids))))

    interactions = [i for i in task_rows(m.AIInteraction) if within(i.created_at)]
    all_tests = task_rows(m.TestResult)
    tests = [t for t in all_tests if within(t.created_at)]
    first_tests = {}
    for t in sorted(all_tests, key=lambda t: (t.created_at, t.id)):
        first_tests.setdefault(t.task_id, t)
    first = [t for t in first_tests.values() if within(t.created_at)]
    uncertain_first = {
        run.task_id
        for run in project_rows(m.CIRun)
        if run.task_id in first_tests
        and run.evidence_status != "available"
        and run.created_at <= first_tests[run.task_id].created_at
    }
    first = [test for test in first if test.task_id not in uncertain_first]
    all_defects = task_rows(m.Defect)
    defects = [d for d in all_defects if within(d.created_at)]
    cohort_defects = [
        d for d in all_defects if d.task_id in completed_ids and d.created_at < end
    ]
    fixed = [d for d in all_defects if within(d.resolved_at)]
    ai = [t.actual_hours for t in tasks if t.uses_ai and t.actual_hours is not None]
    human = [
        t.actual_hours for t in tasks if not t.uses_ai and t.actual_hours is not None
    ]
    type_analysis = []
    comparable = []
    for kind in TaskType:
        a = [t.actual_hours for t in tasks if t.task_type == kind and t.uses_ai]
        h = [t.actual_hours for t in tasks if t.task_type == kind and not t.uses_ai]
        a = [v for v in a if v is not None]
        h = [v for v in h if v is not None]
        eligible = len(a) >= 5 and len(h) >= 5 and mean(h) > 0
        saving = round((1 - mean(a) / mean(h)) * 100, 2) if eligible else None
        if eligible:
            comparable.append((len(a), mean(a), mean(h)))
        type_analysis.append(
            {
                "task_type": kind.value,
                "ai_n": len(a),
                "non_ai_n": len(h),
                "ai_hours": average(a),
                "non_ai_hours": average(h),
                "saving_pct": saving,
                "note": (
                    "观察性差异，非因果收益"
                    if eligible
                    else "每组至少5个完成任务才展示差异"
                ),
            }
        )
    saving = None
    if comparable:
        observed = sum(n * a for n, a, h in comparable)
        baseline = sum(n * h for n, a, h in comparable)
        saving = round((1 - observed / baseline) * 100, 2)
    days = (end - start).total_seconds() / 86400
    values = {
        "project_count": metric(len(projects), len(projects), "个"),
        "delivery_cycle": metric(
            average(
                [
                    (r.completed_at - r.created_at).total_seconds() / 86400
                    for r in delivered
                ]
            ),
            len(delivered),
            "天",
        ),
        "issue_close_rate": metric(
            ratio(
                sum(i.closed_at is not None and i.closed_at < end for i in issues),
                len(issues),
            ),
            len(issues),
            "%",
            "窗口创建 Issue 截至窗口末关闭比例",
        ),
        "pr_review_hours": metric(
            average(
                [
                    (p.first_review_at - p.created_at).total_seconds() / 3600
                    for p in reviewed
                ]
            ),
            len(reviewed),
            "小时",
            "创建到首次正式评审，不含普通评论",
        ),
        "commit_frequency": metric(
            round(len(commits) / days, 3),
            len(commits),
            "次/天",
            "默认分支及已导入 PR 提交按 SHA 去重",
        ),
        "test_pass_rate": metric(
            ratio(sum(t.passed for t in tests), sum(t.total for t in tests)),
            sum(t.total for t in tests),
            "%",
            "人工记录与已关联完整CI报告；JUnit跳过不进入分母",
        ),
        "first_test_pass_rate": metric(
            ratio(sum(t.passed == t.total for t in first), len(first)),
            len(first),
            "%",
            "最早可观测测试；更早CI证据缺失的任务不计入；非全量仓库历史",
        ),
        "defect_density": metric(
            round(len(cohort_defects) / len(tasks), 3) if tasks else None,
            len(tasks),
            "个/任务",
            "完成任务队列截至窗口末已发现缺陷",
        ),
        "defect_fix_hours": metric(
            average(
                [(d.resolved_at - d.created_at).total_seconds() / 3600 for d in fixed]
            ),
            len(fixed),
            "小时",
        ),
        "rework_rate": metric(
            ratio(sum(t.rework_count > 0 for t in tasks), len(tasks)), len(tasks), "%"
        ),
        "ai_task_share": metric(
            ratio(sum(t.uses_ai for t in tasks), len(tasks)), len(tasks), "%"
        ),
        "ai_acceptance_rate": metric(
            ratio(
                sum(i.accepted_count for i in interactions),
                sum(i.suggestion_count for i in interactions),
            ),
            sum(i.suggestion_count for i in interactions),
            "%",
        ),
        "ai_avg_hours": metric(average(ai), len(ai), "小时"),
        "non_ai_avg_hours": metric(average(human), len(human), "小时"),
        "ai_time_saving": metric(
            saving,
            sum(n for n, a, h in comparable),
            "%",
            "按任务类型匹配、以AI任务数加权；每组n≥5；非因果结论",
        ),
    }
    points = [
        {
            "id": r.id,
            "title": r.title,
            "changes": r.change_count,
            "days": round((r.completed_at - r.created_at).total_seconds() / 86400, 3),
        }
        for r in delivered
    ]
    corr = None
    if len(points) >= 5:
        xs, ys = [p["changes"] for p in points], [p["days"] for p in points]
        mx, my = mean(xs), mean(ys)
        denom = sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
        if denom:
            corr = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom, 3)
    values["change_cycle_correlation"] = metric(
        corr, len(points), "r", "Pearson相关；n<5或方差为0时不计算；相关不等于因果"
    )
    trend = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        stop = day + timedelta(days=1)
        trend.append(
            {
                "date": day.date().isoformat(),
                "commits": sum(day <= c.created_at < stop for c in commits),
                "issues": sum(day <= i.created_at < stop for i in issues),
                "prs": sum(
                    max(day, start) <= p.created_at < min(stop, end) for p in prs
                ),
                "tasks": sum(day <= t.completed_at < stop for t in tasks),
            }
        )
        day = stop
    return {
        "mode": mode,
        "data_label": "synthetic/demo data" if mode == "demo" else "GitHub + 人工记录",
        "start": start,
        "end": end,
        "metrics": values,
        "task_types": type_analysis,
        "change_cycle": points,
        "trend": trend,
        "task_distribution": dict(Counter(t.task_type for t in tasks)),
        "tool_distribution": dict(Counter(i.tool for i in interactions)),
        "stage_distribution": dict(Counter(i.stage for i in interactions)),
        "defects": len(defects),
        "reworks": sum(t.rework_count for t in tasks),
        "warnings": [
            "所有对比为观察性结果；任务复杂度、开发者经验和记录偏差未控制。",
            "当前缺陷/返工与历史状态可能补录；报告不是不可变审计快照。",
        ],
    }
