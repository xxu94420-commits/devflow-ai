# 真实AI Coding开发案例

以下是2026-09-30本次开发中实际发生的案例，证据来自本仓库提交、测试输出及真实Issue/PR。不是demo数据库，也不是虚构企业故事。AI承担编码和测试操作，用户提供目标、流程约束和语义反馈。**没有可核实的人类手动改码次数或非AI对照工时，因此不报告人工修正次数、节约率或性能提升。**

## 1. 从指标需求到关系模型

- 需求：把Requirement、Issue、Task、AIInteraction和质量结果串联，不能只有Commit计数。
- AI产出：SQLAlchemy关系模型、7种任务类型、独立指标函数、ADR 001。
- 关键取舍：同类两组各n≥5才显示观察耗时差；缺失值保持null，不当0。
- 验证：首轮4项Pytest通过；Ruff/Black发现导入与排版问题后单独修复。
- 证据：[Issue #1](https://github.com/xxu94420-commits/devflow-ai/issues/1)，提交ffdb61f、cb3d7ad。
- 复盘：数据库设计和分母口径应先于图表，漂亮的百分比不能代替样本。

## 2. 迁移脚手架失败与修复

- 需求：运行时使用显式Alembic迁移，可升级和降级。
- AI初次实现遗漏`migrations/versions`目录，自动生成迁移报FileNotFoundError。
- 修正：创建目录、生成固定版本的显式建表脚本，验证upgrade → check → downgrade → upgrade。
- 验证：API阶段10项测试通过；没有绕过迁移改用运行时create_all。
- 证据：[Issue #2](https://github.com/xxu94420-commits/devflow-ai/issues/2)、[PR #3](https://github.com/xxu94420-commits/devflow-ai/pull/3)，提交630bd7c。
- 复盘：AI生成的工程脚手架不能假设“目录会自动存在”；需要实际执行迁移。此处是AI自查修复，不能描述为人类改码。

## 3. GitHub导入测试自身配置错误

- 需求：重复导入不重复，失败整轮回滚，公开仓库无需Token。
- 首次结果：14 passed / 7 failed；MockTransport客户端未配置base_url，相对路径触发unknown url type，测试未到业务断言。
- 修正：保持生产逻辑不变，为测试客户端提供真实API域名的模拟base_url；保留失败提交c9ed125，再提交105fb3d修复。
- 验证：21 passed，覆盖限流、网络错误、401/404/500、分页截断、幂等和PR关系。
- 证据：[Issue #5](https://github.com/xxu94420-commits/devflow-ai/issues/5)、[PR #7](https://github.com/xxu94420-commits/devflow-ai/pull/7)。
- 复盘：测试代码也需要调试；“生成了测试”不等于“已证明实现正确”。

## 4. 前端构建环境与包体积

- 需求：真实可运行React看板，支持表单和无样本状态。
- 问题：pnpm要求批准esbuild构建脚本；Windows沙箱阻止esbuild读取配置父目录。
- 处理：配置明确的esbuild allowBuilds，按环境规则申请执行权限；TypeScript/ESLint/Vitest与生产构建实际执行通过。
- 后续优化：初始ECharts完整导入约1MB，改为只注册所需图表和组件；保留后续构建结果，不编造加载时间提升。
- 证据：[Issue #4](https://github.com/xxu94420-commits/devflow-ai/issues/4)、[PR #6](https://github.com/xxu94420-commits/devflow-ai/pull/6)，提交e1e6e0b。
- 复盘：区分代码错误和环境权限限制，不能将提升权限当成业务修复。

## 5. 用户反馈纠正产品语义

- 情境：用户看到Live项目中的mbrset，询问毕业论文仓库为什么在此出现。
- 原因：最初需求指定优先接入此公开仓库，初始界面未充分解释其角色。
- 处理：明确论文仓库只是外部读取验证样本，DevFlow AI自身仓库才是开发过程案例；在界面来源说明与文档中补充。
- 实测：论文仓库首次导入3个Commit、0个Issue、0个PR；DevFlow首次自身导入5个Issue、3个PR、6个Commit。这些是该时点采集数量，会随后续开发变化。
- 人工贡献：用户提出语义疑问与流程要求，促使AI修改产品说明；没有证据表明用户手动修改了代码。
- 复盘：数据是真实的，也需要解释为什么出现在产品里；零Issue/PR不能当作采集失败或用模拟数据补齐。
