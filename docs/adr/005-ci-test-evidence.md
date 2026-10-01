# ADR 005：运行状态与测试证据分离

关联 Issue #12。CI运行按(project_id, GitHub run_id, attempt)唯一，重跑不覆盖首次执行。作业状态不等于用例统计；只有实际JUnit testcase被计数，跳过不计通过，错误与断言失败分开。ZIP有字节/解压/条目上限，禁止目录、实体/DTD和额外文件，不保存XML正文、日志或签名下载URL。

工作流上传单个 `devflow-junit-{attempt}` artifact，manifest列出预期报告。前后端报告缺少任一项时状态partial，不进入任务指标。全部报告可解析、已完成且至少一条执行用例时，才允许生成TestResult。total=passed+failed+errors，skipped单列。完整运行即使结论failure也应保留真实计数。

任务关联只采用平台已有TaskCommit对应的精确head_sha，或TaskPR对应GitHub运行的PR编号。唯一候选自动关联，多候选显示ambiguous，无候选unlinked；人工指定必须属于同项目。一个运行只归属一个任务，避免同一次全仓库测试被复制到多个任务放大分母。关联是观察证据，不证明该任务造成全部失败。

项目CI列表展示尚未归属的证据；任务指标仅纳入已归属、完整运行。首次通过率按该任务最早观测测试记录，不声称仓库历史首次测试。人工测试记录和自动结果可能包含同次执行，用户应避免重复录入。不同run_id的push/PR是两次真实执行，不按SHA折叠。

同步为有预算的轮询，默认关闭；显式设置周期后服务端定期拉取，每轮只处理有限项目/最新运行。保留未覆盖历史与限流提示。不引入Webhook入口，不取消公网HTTP只读保护；后台采集属于服务自身的受控数据更新。Token仅从服务端环境变量读取，下载跳转使用无Authorization的独立客户端。
