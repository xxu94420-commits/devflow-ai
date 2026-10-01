const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
let writeKey = '';
export function setWriteKey(value: string) { writeKey = value; }
export async function api<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  const response = await fetch(`${BASE}/api${path}`, {
    method: body === undefined ? 'GET' : method,
    headers: {'Content-Type': 'application/json', ...(writeKey ? {'X-API-Key': writeKey} : {})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({detail: '服务暂不可用'}));
    throw new Error(typeof error.detail === 'string' ? error.detail : '输入校验失败，请检查必填项、时间与计数');
  }
  return response.json();
}
export interface Metric {value: number | null; n: number; unit: string; confidence: string; note: string}
export interface Project {id: number; name: string; repository: string; description: string; mode: string; imported_at: string | null; import_note: string}
export interface Task {id: number; project_id: number; requirement_id: number | null; issue_id: number | null; title: string; description: string; task_type: string; estimated_hours: number; actual_hours: number | null; uses_ai: boolean; rework_count: number; created_at: string; completed_at: string | null}
export interface Analysis {data_label: string; metrics: Record<string, Metric>; trend: {date: string; commits: number; issues: number; prs: number; tasks: number}[]; task_distribution: Record<string, number>; tool_distribution: Record<string, number>; stage_distribution: Record<string, number>; task_types: {task_type: string; ai_n: number; non_ai_n: number; ai_hours: number | null; non_ai_hours: number | null; saving_pct: number | null; note: string}[]; change_cycle: {changes: number; days: number}[]; warnings: string[]; defects: number; reworks: number}
export interface Entity {id: number; title?: string; number?: number; sha?: string; message?: string; state?: string; author?: string; labels?: string[]; created_at: string; completed_at?: string; url?: string}
export interface ProjectDetail extends Project {issues: Entity[]; commits: Entity[]; pull_requests: Entity[]; requirements: Entity[]}
export interface Detail extends Task {timeline: {id: number; kind: string; title: string; at: string}[]; ai_summary: {tools: string[]; stages: string[]; prompt_count: number; accepted_count: number; human_modification_count: number}; first_test_passed: boolean | null; defect_count: number; requirement: Entity | null; issue: Entity | null; commits: Entity[]; pull_requests: Entity[]; interactions: {id: number; tool: string; purpose: string; prompt_summary: string; suggestion_summary: string; accepted_count: number; suggestion_count: number; modification_notes: string; quality_result: string}[]}
export const types = ['需求理解','架构设计','功能开发','测试生成','Bug定位','代码重构','文档编写'];
export const names: Record<string,string> = {project_count:'项目数量',delivery_cycle:'需求平均交付周期',issue_close_rate:'Issue 关闭率',pr_review_hours:'PR 平均评审时长',commit_frequency:'Commit 频率',test_pass_rate:'测试通过率',first_test_pass_rate:'首次测试通过率',defect_density:'缺陷密度',defect_fix_hours:'缺陷修复周期',rework_rate:'返工率',ai_task_share:'AI 辅助任务占比',ai_acceptance_rate:'AI 建议采纳率',ai_avg_hours:'AI 任务平均耗时',non_ai_avg_hours:'非 AI 任务平均耗时',ai_time_saving:'同类任务时间差',change_cycle_correlation:'变更次数 / 周期相关性'};
export function display(value: number | null | undefined) { return value == null ? '—' : Number(value.toFixed(2)).toLocaleString('zh-CN'); }
