import { useEffect, useState } from "react";
import { api, display } from "./api";
import type { CIRun, Task } from "./api";

export const evidenceLabels: Record<string, string> = {
  available: "报告完整",
  partial: "报告不完整",
  missing: "没有报告",
  expired: "报告已过期",
  auth_required: "需要报告读取权限",
  pending: "运行中",
  invalid: "报告不可用",
};
const associationLabels: Record<string, string> = {
  automatic: "自动关联",
  manual: "人工确认",
  unlinked: "尚未关联",
  ambiguous: "关联有歧义",
};
function RunCard({
  run,
  tasks,
  readOnly,
  onChange,
  onOpenTask,
}: {
  run: CIRun;
  tasks: Task[];
  readOnly: boolean;
  onChange: () => void;
  onOpenTask: (id: number) => void;
}) {
  const [selected, setSelected] = useState(String(run.task_id ?? ""));
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function associate() {
    setBusy(true);
    setError("");
    try {
      await api(
        `/ci/runs/${run.id}/task`,
        { task_id: selected ? Number(selected) : null },
        "PUT",
      );
      onChange();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="ci-run">
      <div className="panel-title">
        <a href={run.url} target="_blank" rel="noreferrer">
          {run.name} · #{run.run_id} / attempt {run.attempt} ↗
        </a>
        <span className="tag">{run.conclusion ?? run.status}</span>
      </div>
      <p className="muted">
        {run.branch} · {run.event} · SHA {run.head_sha.slice(0, 12)}
        {run.pr_numbers.length > 0 &&
          ` · PR ${run.pr_numbers.map((n) => `#${n}`).join(", ")}`}
      </p>
      <div className="repo-stats">
        <span>
          {evidenceLabels[run.evidence_status] ?? run.evidence_status}
        </span>
        <span>通过 {display(run.passed)}</span>
        <span>失败 {display(run.failed)}</span>
        <span>错误 {display(run.errors)}</span>
        <span>跳过 {display(run.skipped)}</span>
      </div>
      <p>
        {associationLabels[run.association]}
        {run.task_id && (
          <button
            className="text-button"
            onClick={() => onOpenTask(run.task_id!)}
          >
            {" "}
            · Task #{run.task_id}
          </button>
        )}
        {run.association === "ambiguous" &&
          ` · 候选任务 ${run.candidate_task_ids.join(", ")}`}
      </p>
      <p className="warning-text">{run.note}</p>
      <p className="muted">
        运行时间 {run.created_at} · 最近采集 {run.synced_at}（UTC）
      </p>
      <details>
        <summary>查看测试套件与作业证据</summary>
        {run.reports.map((report) => (
          <p key={report.name}>
            {report.name}：通过 {report.passed} / 失败 {report.failed} / 错误{" "}
            {report.errors} / 跳过 {report.skipped}
          </p>
        ))}
        {run.jobs.map((job) => (
          <p key={job.id}>
            {job.name} · {job.conclusion ?? job.status}
          </p>
        ))}
        {run.digest && <p className="muted ci-digest">归档校验 {run.digest}</p>}
      </details>
      {!readOnly && (
        <div className="table-actions">
          <select
            aria-label={`为运行 ${run.run_id} attempt ${run.attempt} 指定任务`}
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">恢复自动匹配</option>
            {tasks
              .filter((task) => task.project_id === run.project_id)
              .map((task) => (
                <option key={task.id} value={task.id}>
                  #{task.id} {task.title}
                </option>
              ))}
          </select>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void associate()}
          >
            确认关联
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </article>
  );
}

export function CISection({
  projectId,
  runs: supplied,
  readOnly,
  tasks,
  onOpenTask,
  onChanged,
}: {
  projectId: number;
  runs?: CIRun[];
  readOnly: boolean;
  tasks: Task[];
  onOpenTask: (id: number) => void;
  onChanged: () => void;
}) {
  const [runs, setRuns] = useState<CIRun[]>(supplied ?? []),
    [version, setVersion] = useState(0);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<{
    poll_interval_seconds: number;
    artifact_access_configured: boolean;
  } | null>(null);
  useEffect(() => {
    let active = true;
    setError("");
    setLoading(true);
    Promise.all([
      supplied
        ? Promise.resolve(supplied)
        : api<CIRun[]>(
            `/ci/runs?mode=live&project_id=${projectId}&limit=10&offset=${offset}`,
          ),
      api<{
        poll_interval_seconds: number;
        artifact_access_configured: boolean;
      }>("/ci/status"),
    ])
      .then(([rows, capabilities]) => {
        if (active) {
          setRuns(rows);
          setStatus(capabilities);
        }
      })
      .catch((error) => {
        if (active) setError(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, supplied, version, offset]);
  function changed() {
    setVersion((value) => value + 1);
    onChanged();
  }
  async function sync() {
    setBusy(true);
    setError("");
    try {
      await api("/ci/sync", { project_id: projectId, max_runs: 3 });
      changed();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <div className="panel-title">
        <h3>自动测试证据</h3>
        {!readOnly && !supplied && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void sync()}
          >
            {busy ? "正在采集…" : "同步最近 CI"}
          </button>
        )}
      </div>
      <p className="muted">
        {status?.poll_interval_seconds
          ? `后台每 ${status.poll_interval_seconds / 60} 分钟采集`
          : "后台轮询未启用"}{" "}
        · 工作流结论与测试用例计数分开显示。
      </p>
      {status && !status.artifact_access_configured && (
        <p className="warning-text">
          未配置服务端 Actions
          读取权限：可查看公开运行状态；新报告无法下载，已采集的计数保留。
        </p>
      )}
      <p className="footnote">
        仅完整、已关联任务的报告进入任务测试指标；跳过不计通过。仓库级失败不自动生成任务缺陷。
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loading ? (
        <p>正在读取CI记录…</p>
      ) : runs.length ? (
        runs.map((run) => (
          <RunCard
            key={`${run.id}-${run.task_id}`}
            run={run}
            tasks={tasks}
            readOnly={readOnly}
            onChange={changed}
            onOpenTask={onOpenTask}
          />
        ))
      ) : (
        <p className="empty">
          尚无自动测试证据。等待服务端采集或在本地同步；未关联的运行显示在项目详情。
        </p>
      )}
      {!supplied && (
        <div className="table-actions">
          <button
            className="secondary"
            disabled={offset === 0 || loading}
            onClick={() => setOffset((n) => Math.max(0, n - 10))}
          >
            上一页
          </button>
          <span>第 {offset / 10 + 1} 页</span>
          <button
            className="secondary"
            disabled={runs.length < 10 || loading}
            onClick={() => setOffset((n) => n + 10)}
          >
            下一页
          </button>
        </div>
      )}
    </section>
  );
}
