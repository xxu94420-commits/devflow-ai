import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { CISection } from "./CISection";
import type { CIRun } from "./api";

const run: CIRun = {
  id: 1,
  project_id: 1,
  run_id: 123,
  attempt: 2,
  name: "fixture",
  head_sha: "a".repeat(40),
  branch: "test",
  event: "push",
  status: "completed",
  conclusion: "success",
  url: "https://github.com/example/test/actions/runs/123",
  pr_numbers: [],
  created_at: "2026-10-01",
  synced_at: "2026-10-01",
  task_id: null,
  association: "unlinked",
  candidate_task_ids: [],
  evidence_status: "auth_required",
  note: "报告未知",
  digest: "",
  passed: null,
  failed: null,
  errors: null,
  skipped: null,
  jobs: [],
  reports: [],
};

function render(readOnly: boolean, evidence = run) {
  return renderToStaticMarkup(
    <CISection
      projectId={1}
      runs={[evidence]}
      readOnly={readOnly}
      tasks={[]}
      onOpenTask={() => {}}
      onChanged={() => {}}
    />,
  );
}

it("does not expose write controls on the public evidence view", () => {
  const html = render(true);
  expect(html).not.toContain("确认关联");
  expect(html).not.toContain("同步最近 CI");
  expect(html).toContain("attempt 2");
});

it("does not convert workflow success into passing test counts", () => {
  const html = render(true);
  expect(html).toContain("需要报告读取权限");
  expect(html).toContain("通过 —");
  expect(html).not.toContain("通过 0");
});

it("allows local attribution and distinguishes an observed zero from missing", () => {
  const html = render(false, {
    ...run,
    passed: 0,
    failed: 2,
    evidence_status: "available",
  });
  expect(html).toContain("确认关联");
  expect(html).toContain("通过 0");
  expect(html).toContain("失败 2");
});
