from sqlalchemy import select

from . import models as m
from .metrics import analyze

NAMES = {
    "project_count": "项目数量",
    "delivery_cycle": "需求平均交付周期",
    "issue_close_rate": "Issue关闭率",
    "pr_review_hours": "PR平均评审时长",
    "commit_frequency": "Commit频率",
    "test_pass_rate": "测试通过率",
    "first_test_pass_rate": "首次测试通过率",
    "defect_density": "缺陷密度",
    "defect_fix_hours": "缺陷修复周期",
    "rework_rate": "返工率",
    "ai_task_share": "AI辅助任务占比",
    "ai_acceptance_rate": "AI建议采纳率",
    "ai_avg_hours": "AI任务平均耗时",
    "non_ai_avg_hours": "非AI任务平均耗时",
    "ai_time_saving": "同类型任务时间节约率（观察值）",
    "change_cycle_correlation": "需求变更与交付周期相关系数",
}


def safe(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def report(db, mode, start, end, project_id=None):
    current = analyze(db, mode, start, end, project_id)
    previous = analyze(db, mode, start - (end - start), start, project_id)
    lines = [
        "# DevFlow AI 研发周期报告",
        "",
        f"数据来源：{current['data_label']}",
        f"范围：{start.isoformat()} ≤ UTC < {end.isoformat()}",
        "对比：前一等长时间窗口。差值为绝对差（百分比指标以百分点计）。",
        "",
        "| 指标 | 当前 | 前期 | 差值 | 当前样本 n | 限制 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key, metric in current["metrics"].items():
        old = previous["metrics"][key]["value"]
        value = metric["value"]
        delta = round(value - old, 3) if old is not None and value is not None else "—"
        lines.append(
            f"| {NAMES[key]} | {value if value is not None else '—'} {metric['unit']} | {old if old is not None else '—'} | {delta} | {metric['n']} | {metric['confidence']}；{metric['note']} |"
        )
    lines += ["", "## 规则提示（非统计异常检测）"]
    alerts = []
    for key, threshold, below, label in [
        ("test_pass_rate", 90, True, "测试通过率低于90%"),
        ("rework_rate", 20, False, "返工率高于20%"),
    ]:
        value = current["metrics"][key]["value"]
        if value is not None and (value < threshold if below else value > threshold):
            alerts.append(
                f"- {label}；需结合 n={current['metrics'][key]['n']} 核查案例，阈值为演示规则。"
            )
    lines += alerts or ["- 当前未触发预设规则；不代表不存在质量风险。"]
    lines += ["", "## 代表性案例（按返工次数降序，非随机抽样）"]
    query = (
        select(m.Task)
        .join(m.Project)
        .where(
            m.Project.mode == mode,
            m.Task.completed_at >= start,
            m.Task.completed_at < end,
        )
    )
    if project_id is not None:
        query = query.where(m.Task.project_id == project_id)
    cases = db.scalars(
        query.order_by(m.Task.rework_count.desc(), m.Task.id).limit(3)
    ).all()
    lines += [
        f"- Task #{t.id}：{safe(t.title)}；类型={t.task_type}；AI={t.uses_ai}；实际={t.actual_hours}h；返工={t.rework_count}次。"
        for t in cases
    ] or ["- 无已完成任务案例。"]
    lines += [
        "",
        "## 局限与下一步",
        *[f"- {x}" for x in current["warnings"]],
        "- 同类两组各n≥5才展示时间差；该门槛不代表统计显著性，未控制复杂度与经验。",
        "- GitHub导入可能被页数/请求预算截断，请核对项目详情中的覆盖范围。",
        "- 复盘行动：检查高返工任务，补录测试结果，下一周期统一耗时记录协议。",
    ]
    return {"markdown": "\n".join(lines), "current": current, "previous": previous}
