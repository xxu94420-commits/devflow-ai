import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { Findings, RequirementReview } from "./RequirementReview";

it("public review fails closed and labels static examples", () => {
  const html = renderToStaticMarkup(
    <RequirementReview
      readOnly
      mode="live"
      projectId=""
      projects={[]}
      onTask={() => {}}
    />,
  );
  expect(html).toContain("synthetic/demo data");
  expect(html).toContain("未调用模型");
  expect(html).toContain("尚未连接模型");
  expect(html).not.toMatch(/<button[^>]*>保存需求<\/button>/);
  expect(html).not.toContain("创建关联开发任务");
  expect(html).toContain("不写入项目数据库");
});
it("escapes model text and does not treat no findings as certification", () => {
  expect(renderToStaticMarkup(<Findings findings={[]} />)).toContain(
    "不代表需求一定完整",
  );
  const html = renderToStaticMarkup(
    <Findings
      findings={[
        {
          category: "ambiguity",
          field: "description",
          quote: "<script>alert(1)</script>",
          problem: "fixture",
          question: "fixture",
        },
      ]}
    />,
  );
  expect(html).not.toContain("<script>");
  expect(html).toContain("&lt;script&gt;");
});
