import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type { Project, Task } from "./api";

interface Source {
  title: string;
  description: string;
  acceptance_criteria: string;
}
interface Requirement extends Source {
  id: number;
  project_id: number;
  version: number;
  change_count: number;
  created_at: string;
  completed_at: string | null;
}
export interface Finding {
  category: string;
  field: keyof Source;
  quote: string;
  problem: string;
  question: string;
}
interface Decision {
  finding_index: number;
  decision: string;
  reason: string;
}
interface Review {
  id: number;
  status: string;
  error_code: string;
  model: string;
  provider: string;
  prompt_version: string;
  snapshot: Source & { version: number };
  stale: boolean;
  findings: Finding[];
  decisions: Decision[];
  created_at: string;
  duration_ms: number | null;
  usage: Record<string, number>;
}
interface History {
  requirement: Requirement;
  reviews: Review[];
  revisions: {
    id: number;
    version: number;
    reason: string;
    snapshot: Source;
  }[];
  tasks: Task[];
}
interface Connection {
  id: string;
  label: string;
  configured: boolean;
  model: string;
  destination: string;
}
interface TrialStatus {
  enabled: boolean;
  configured: boolean;
  model: string;
  destination: string;
  daily_limit: number;
}
interface TrialResult {
  findings: Finding[];
  model: string;
  prompt_version: string;
  duration_ms: number;
}

const blank: Source = { title: "", description: "", acceptance_criteria: "" };
export const demoSource: Source = {
  title: "运营上传活动名单",
  description: "运营可以上传活动名单，系统应快速处理，方便后续联系客户。",
  acceptance_criteria: "上传成功后可以查看结果。",
};
export const demoFindings: Finding[] = [
  {
    category: "acceptance",
    field: "description",
    quote: "快速处理",
    problem: "没有可验证的处理时间标准。",
    question: "在多大的名单规模下，期望多久返回处理结果？",
  },
  {
    category: "exception",
    field: "description",
    quote: "上传活动名单",
    problem: "未说明名单格式错误或重复记录的处理方式。",
    question:
      "发现格式错误或重复名单时，是拒绝整批、跳过记录，还是允许人工处理？",
  },
];
const categories: Record<string, string> = {
  ambiguity: "表达不清楚",
  acceptance: "验收标准",
  boundary: "使用范围",
  exception: "异常情况",
  conflict: "条件冲突",
};
const fields: Record<string, string> = {
  title: "需求名称",
  description: "需求描述",
  acceptance_criteria: "验收条件",
};
const errors: Record<string, string> = {
  timeout: "模型响应超时，可稍后重试",
  rate_limited: "模型服务额度或频率受限",
  authentication: "模型服务拒绝凭据，请联系维护者",
  invalid_schema: "模型结果结构不符合要求",
  ungrounded_quote: "模型引用未匹配原文",
  duplicate_finding: "模型返回重复问题",
  output_too_large: "模型结果超过长度限制",
  invalid_output: "模型输出格式或原文引用未通过校验",
  incomplete_output: "模型拒答或输出被截断",
  network: "暂时无法连接模型",
  provider_error: "模型服务返回错误",
  interrupted: "上次调用中断，结果未知；重试可能产生新调用",
  internal_error: "评估暂不可用",
};

export function Findings({ findings }: { findings: Finding[] }) {
  return (
    <>
      {findings.length === 0 && (
        <p>本次未提出问题，不代表需求一定完整，仍需人工检查。</p>
      )}
      {findings.map((f, i) => (
        <article className="review-finding" key={i}>
          <span className="badge">{categories[f.category] || f.category}</span>
          <p>
            原文 · {fields[f.field]}：<q>{f.quote}</q>
          </p>
          <strong>{f.problem}</strong>
          <p>需要你确认：{f.question}</p>
        </article>
      ))}
    </>
  );
}

function SourceFields({
  value,
  onChange,
  disabled = false,
}: {
  value: Source;
  onChange: (s: Source) => void;
  disabled?: boolean;
}) {
  return (
    <div className="review-fields">
      {(Object.keys(blank) as (keyof Source)[]).map((k) => (
        <label className="field" key={k}>
          <span>
            {fields[k]}
            {k === "acceptance_criteria" && "（怎样才算做好，可暂留空）"}
          </span>
          {k === "title" ? (
            <input
              required
              maxLength={200}
              disabled={disabled}
              value={value[k]}
              onChange={(e) => onChange({ ...value, [k]: e.target.value })}
            />
          ) : (
            <textarea
              required={k === "description"}
              maxLength={k === "acceptance_criteria" ? 1000 : 2000}
              disabled={disabled}
              rows={4}
              value={value[k]}
              onChange={(e) => onChange({ ...value, [k]: e.target.value })}
            />
          )}
        </label>
      ))}
    </div>
  );
}

function DecisionForm({
  disabled,
  onSave,
}: {
  disabled: boolean;
  onSave: (decision: string, reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  return (
    <div className="review-decision">
      <label className="field">
        <span>确认理由（例如：需要补充文件大小限制）</span>
        <input
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={disabled}
        />
      </label>
      <button
        className="secondary"
        disabled={disabled || !reason.trim()}
        onClick={() => void onSave("accepted", reason)}
      >
        采纳这个问题
      </button>
      <button
        className="secondary"
        disabled={disabled || !reason.trim()}
        onClick={() => void onSave("rejected", reason)}
      >
        驳回并记录理由
      </button>
    </div>
  );
}

export function RequirementReview({
  readOnly,
  mode,
  projectId,
  projects,
  onTask,
}: {
  readOnly: boolean;
  mode: string;
  projectId: string;
  projects: Project[];
  onTask: (id: number) => void;
}) {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [history, setHistory] = useState<History | null>(null);
  const [source, setSource] = useState<Source>(blank);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [provider, setProvider] = useState("");
  const [trialStatus, setTrialStatus] = useState<TrialStatus | null>(null);
  const [trialSource, setTrialSource] = useState<Source>(demoSource);
  const [trialResult, setTrialResult] = useState<TrialResult | null>(null);
  const [trialInput, setTrialInput] = useState<Source | null>(null);
  const [consent, setConsent] = useState(false);
  const [trialConsent, setTrialConsent] = useState(false);
  const [selectedProject, setSelectedProject] = useState(
    projectId || String(projects[0]?.id || ""),
  );
  const [revisionReason, setRevisionReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [hours, setHours] = useState("1");
  const [trialDecisions, setTrialDecisions] = useState<Record<number, string>>(
    {},
  );
  const listPath = `/requirements?mode=${mode}${projectId ? `&project_id=${projectId}` : ""}`;
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Requirement[]>(listPath),
      api<{ connections: Connection[] }>("/review/connections"),
      api<TrialStatus>("/review/trial"),
    ])
      .then(([r, c, t]) => {
        if (active) {
          setRequirements(r);
          setConnections(c.connections);
          setTrialStatus(t);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [listPath]);
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }
  async function load(id: number) {
    const h = await api<History>(`/requirements/${id}/reviews`);
    setHistory(h);
    setSource(h.requirement);
    setRevisionReason("");
    setTaskTitle(h.requirement.title);
    setConsent(false);
  }
  const selectedConnection = connections.find((c) => c.id === provider);
  const dirty =
    history &&
    (Object.keys(blank) as (keyof Source)[]).some(
      (k) => source[k] !== history.requirement[k],
    );
  async function save(e: FormEvent) {
    e.preventDefault();
    await perform(async () => {
      const body = {
        title: source.title,
        description: source.description,
        acceptance_criteria: source.acceptance_criteria,
      };
      const result = history
        ? await api<Requirement>(
            `/requirements/${history.requirement.id}`,
            {
              ...body,
              project_id: history.requirement.project_id,
              change_count: history.requirement.change_count,
              created_at: history.requirement.created_at,
              completed_at: history.requirement.completed_at,
              expected_version: history.requirement.version,
              revision_reason: revisionReason,
            },
            "PUT",
          )
        : await api<Requirement>("/requirements", {
            ...body,
            project_id: Number(selectedProject),
          });
      setRequirements(await api<Requirement[]>(listPath));
      await load(result.id);
      setNotice("需求已保存。内容修改后需要重新评估。");
    });
  }
  return (
    <div className="review-workspace">
      <section className="panel">
        <h3>先把需求说清楚，再交给开发</h3>
        <p>
          写下你想解决的问题 → AI指出需要澄清的地方 → 你决定采纳或驳回 →
          修改并保存需求 → 关联开发任务。
        </p>
        <p className="muted">
          采纳表示认可这个问题，不代表需求已经修好。AI不会自动修改正文，也不提供未经验证的“质量分数”。本页不使用顶部日期筛选。
        </p>
      </section>
      <section className="panel">
        <h3>看一个例子 · synthetic/demo data</h3>
        <p>
          以下内容由项目开发阶段人工编写，用来解释界面，未调用模型，不作为AI效果评测。
        </p>
        <blockquote>{demoSource.description}</blockquote>
        <Findings findings={demoFindings} />
      </section>
      {readOnly ? (
        <section className="panel">
          <h3>在线试用需求评估</h3>
          <p>
            结果仅在当前页面显示，不写入项目数据库；刷新后不会保留。本平台不保存访客输入，所选云端模型服务会接收输入并按其政策处理。请只使用公开或脱敏文本。
          </p>
          <p className="muted">
            全站试用上限 {trialStatus?.daily_limit ?? "—"}{" "}
            次/UTC日/进程，至少间隔15秒、一次只处理一个请求；服务重启会重置此保护，以供应商账户额度为最终限制。
          </p>
          <label className="field">
            <span>模型连接</span>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                setTrialConsent(false);
              }}
              disabled={busy}
            >
              <option value="">尚未连接模型</option>
              <option
                value="cloud"
                disabled={!trialStatus?.enabled || !trialStatus?.configured}
              >
                {trialStatus?.model || "Groq 云端模型"}{" "}
                {trialStatus?.enabled && trialStatus?.configured
                  ? "（已配置，调用时检查可用性）"
                  : "（待维护者配置）"}
              </option>
            </select>
          </label>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void perform(async () => {
                setTrialResult(null);
                setTrialDecisions({});
                const input = { ...trialSource };
                const result = await api<TrialResult>("/review/trial", {
                  ...input,
                  consent: trialConsent,
                });
                setTrialInput(input);
                setTrialResult(result);
              });
            }}
          >
            <SourceFields
              value={trialSource}
              onChange={setTrialSource}
              disabled={busy}
            />
            <label className="review-consent">
              <input
                type="checkbox"
                checked={trialConsent}
                disabled={busy || !provider}
                onChange={(e) => setTrialConsent(e.target.checked)}
              />
              我确认文本已脱敏，并同意将以上三项内容发送至{" "}
              {trialStatus?.destination || "尚未配置的服务"} 进行评估。
            </label>
            <button
              className="primary"
              disabled={
                busy || !provider || !trialConsent || !trialStatus?.enabled
              }
            >
              {" "}
              {busy ? "评估中，请勿重复提交…" : "开始真实AI评估"}
            </button>
          </form>
          {trialResult && (
            <div>
              <h4>本次真实模型返回 · {trialResult.model}</h4>
              <p>
                Prompt {trialResult.prompt_version} · {trialResult.duration_ms}{" "}
                ms（仅本次调用耗时）
              </p>
              <details>
                <summary>查看本次输入快照</summary>
                <pre className="report">
                  {JSON.stringify(trialInput, null, 2)}
                </pre>
              </details>
              <Findings findings={trialResult.findings} />
              {trialResult.findings.map((_, i) => (
                <div key={i}>
                  <p>
                    第 {i + 1} 条：{trialDecisions[i] || "待你判断"}
                    （仅本页记录）
                  </p>
                  {!trialDecisions[i] && (
                    <DecisionForm
                      disabled={busy}
                      onSave={async (d, r) => {
                        setTrialDecisions((v) => ({
                          ...v,
                          [i]: `${d === "accepted" ? "采纳" : "驳回"}：${r}`,
                        }));
                      }}
                    />
                  )}
                </div>
              ))}
              <p>
                根据确认的问题修改上方文字后，可以再次评估。公网试用不创建开发任务；保存历史和任务关联在本地工作空间完成。
              </p>
            </div>
          )}
        </section>
      ) : (
        <>
          <section className="panel">
            <h3>选择需求或新建</h3>
            <p className="muted">
              当前模式：{mode === "demo" ? "模拟演示" : "真实记录"} ·
              最近50条需求。模型只接收选中需求的三项文本，不会自动读取整个仓库。
            </p>
            <select
              aria-label="选择需求"
              disabled={busy}
              value={history?.requirement.id || ""}
              onChange={(e) => {
                if (e.target.value)
                  void perform(() => load(Number(e.target.value)));
                else {
                  setHistory(null);
                  setSource(blank);
                  setConsent(false);
                }
              }}
            >
              <option value="">新建需求</option>
              {requirements.map((r) => (
                <option value={r.id} key={r.id}>
                  {r.title} · v{r.version}
                </option>
              ))}
            </select>
            <form onSubmit={save}>
              {!history && (
                <label className="field">
                  <span>所属项目</span>
                  <select
                    required
                    value={selectedProject}
                    disabled={busy}
                    onChange={(e) => setSelectedProject(e.target.value)}
                  >
                    <option value="">请选择项目</option>
                    {projects.map((p) => (
                      <option value={p.id} key={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <SourceFields
                value={source}
                onChange={(v) => {
                  setSource(v);
                  setConsent(false);
                }}
                disabled={busy}
              />
              {history && (
                <label className="field">
                  <span>修改原因</span>
                  <input
                    required
                    value={revisionReason}
                    maxLength={500}
                    onChange={(e) => setRevisionReason(e.target.value)}
                    disabled={busy}
                  />
                </label>
              )}
              <button
                className="primary"
                disabled={
                  busy ||
                  (!history && !selectedProject) ||
                  (!!history && !dirty)
                }
              >
                {history ? "保存为新版本" : "保存需求"}
              </button>
            </form>
          </section>
          {history && (
            <>
              <section className="panel">
                <h3>评估已保存的需求 · v{history.requirement.version}</h3>
                {dirty && (
                  <p className="warning">你有未保存的修改，请先保存再评估。</p>
                )}
                <label className="field">
                  <span>模型连接</span>
                  <select
                    disabled={busy}
                    value={provider}
                    onChange={(e) => {
                      setProvider(e.target.value);
                      setConsent(false);
                    }}
                  >
                    <option value="">尚未连接模型</option>
                    {connections.map((c) => (
                      <option key={c.id} value={c.id} disabled={!c.configured}>
                        {c.label} · {c.configured ? c.model : "待配置"}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="review-consent">
                  <input
                    type="checkbox"
                    checked={consent}
                    disabled={busy || !provider || !!dirty}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  我已检查文本，不含密钥或隐私信息；同意发送需求名称、描述和验收条件至{" "}
                  {selectedConnection?.destination || "所选服务"}。
                </label>
                <button
                  className="primary"
                  disabled={busy || !provider || !consent || !!dirty}
                  onClick={() =>
                    void perform(async () => {
                      await api(
                        `/requirements/${history.requirement.id}/reviews`,
                        {
                          expected_version: history.requirement.version,
                          provider,
                          request_key: crypto.randomUUID(),
                          consent,
                        },
                      );
                      await load(history.requirement.id);
                    })
                  }
                >
                  {busy ? "评估中…" : "发送并评估"}
                </button>
                <button
                  className="secondary"
                  disabled={busy || !!dirty}
                  onClick={() =>
                    void perform(() => load(history.requirement.id))
                  }
                >
                  刷新历史
                </button>
                <p className="muted">
                  失败也会保留状态；超时重试可能产生新的模型调用。最多展示最近50次评估和50个版本。
                </p>
                {history.reviews.length === 0 && (
                  <p>尚无评估记录。未配置模型时仍可编辑需求和关联任务。</p>
                )}
                {history.reviews.map((r) => (
                  <article className="review-history" key={r.id}>
                    <h4>
                      需求 v{r.snapshot.version} · {r.model} ·{" "}
                      {r.stale ? "旧版本，仅供回看" : "当前版本"}
                    </h4>
                    <p>
                      {r.created_at} UTC · {r.prompt_version} ·{" "}
                      {r.status === "succeeded"
                        ? "已完成，待人工判断"
                        : errors[r.error_code] ||
                          (r.status === "failed"
                            ? `模型评估失败（${r.error_code}）`
                            : "处理中，可稍后刷新历史")}
                    </p>
                    <details>
                      <summary>输入快照与调用证据</summary>
                      <pre className="report">
                        {JSON.stringify(
                          {
                            input: r.snapshot,
                            provider: r.provider,
                            duration_ms: r.duration_ms,
                            usage: r.usage,
                          },
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                    {r.status === "succeeded" && (
                      <>
                        <Findings findings={r.findings} />
                        {r.findings.map((_, i) => {
                          const d = r.decisions.find(
                            (d) => d.finding_index === i,
                          );
                          return (
                            <div key={i}>
                              <p>
                                第 {i + 1} 条：
                                {d
                                  ? `${d.decision === "accepted" ? "已采纳" : "已驳回"} · ${d.reason}`
                                  : "尚未确认"}
                              </p>
                              {!d && !r.stale && (
                                <DecisionForm
                                  disabled={busy || !!dirty}
                                  onSave={(decision, reason) =>
                                    perform(async () => {
                                      await api(
                                        `/requirement-reviews/${r.id}/findings/${i}/decision`,
                                        { decision, reason },
                                      );
                                      await load(history.requirement.id);
                                    })
                                  }
                                />
                              )}
                            </div>
                          );
                        })}
                      </>
                    )}
                  </article>
                ))}
              </section>
              <section className="panel">
                <h3>需求版本历史</h3>
                {history.revisions.length === 0 && (
                  <p>尚未修改；首次修改时保留当前版本快照。</p>
                )}
                {history.revisions.map((r) => (
                  <details key={r.id}>
                    <summary>
                      v{r.version} · {r.reason}
                    </summary>
                    <pre className="report">
                      {JSON.stringify(r.snapshot, null, 2)}
                    </pre>
                  </details>
                ))}
              </section>
              <section className="panel">
                <h3>把需求交给开发</h3>
                <p>
                  下面创建的任务会关联当前需求。现有任务也可在“任务与协作链路”中选择该需求。
                </p>
                {history.tasks.map((t) => (
                  <p key={t.id}>
                    <button
                      className="link-button"
                      onClick={() => onTask(t.id)}
                    >
                      {t.title}
                    </button>
                  </p>
                ))}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void perform(async () => {
                      const task = await api<Task>("/tasks", {
                        project_id: history.requirement.project_id,
                        requirement_id: history.requirement.id,
                        title: taskTitle,
                        task_type: "功能开发",
                        estimated_hours: Number(hours),
                      });
                      await load(history.requirement.id);
                      setNotice(
                        `已创建关联任务 #${task.id}，预计耗时仅为计划估算。`,
                      );
                    });
                  }}
                >
                  <label className="field">
                    <span>任务名称</span>
                    <input
                      required
                      maxLength={200}
                      value={taskTitle}
                      disabled={busy}
                      onChange={(e) => setTaskTitle(e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>预计工时（小时，仅为计划）</span>
                    <input
                      required
                      type="number"
                      min="0"
                      max="100000"
                      step="0.5"
                      value={hours}
                      disabled={busy}
                      onChange={(e) => setHours(e.target.value)}
                    />
                  </label>
                  <button className="primary" disabled={busy || !!dirty}>
                    创建关联开发任务
                  </button>
                </form>
              </section>
            </>
          )}
        </>
      )}
      {error && (
        <div role="alert" className="warning">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="notice">
          {notice}
        </div>
      )}
    </div>
  );
}
