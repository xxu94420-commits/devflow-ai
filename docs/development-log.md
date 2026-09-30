# 实际开发记录

此文件只记录本次开发实际发生的行为，不把 demo 数据当开发证据。

## 阶段 1：关系模型和指标内核（2026-09-30）

- 检查目录：空 Git 仓库，无提交、无远程地址。
- 使用内置 Python 3.12 和 pnpm；系统没有 Docker 命令。
- 设计 Requirement 至 Retrospective 关系模型，完成指标内核和第一批离线测试。
- GitHub 连接器可识别账号，但仓库列表为空。等待用户指定目标仓库；未创建远程 Issue、PR 或声称已上传。
- ADR 001 记录样本门槛与同类型比较的理由。

测试结果在实际执行后补充，不提前声明通过。

## 阶段 1 验证

- Pytest 首次 4 passed；Ruff 发现未使用导入/长行，Black发现格式差异，修复提交 cb3d7ad。
- 用户创建并提供远程仓库后，推送 codex/domain-metrics。Issue #1 如实注明创建晚于首个本地提交。
- GitHub连接器写入403；本机Git凭据正常推送，使用内存凭据调用GitHub API成功创建Issue #1/#2。

## 阶段 2：API MVP

- 10 passed，Ruff/Black通过（有上游 Starlette/AnyIO 弃用警告）。
- 初次 Alembic 自动生成因 versions 目录缺失失败；创建目录后生成显式迁移，upgrade → check → downgrade → upgrade通过。
- 添加42个明确标记的synthetic/demo任务，仅用于演示，不用于开发效率证明。

## 阶段 3：前端看板

- TypeScript、ESLint通过，Vitest 3 passed，Vite生产构建成功。
- 首次pnpm安装因esbuild脚本未批准返回非零，添加明确allowBuilds配置。
- Vite/esbuild在Windows沙箱内读取父目录被拒，获授权后运行通过；不把环境限制描述为代码缺陷。
- 构建显示ECharts完整包约1MB，记录为后续按需导入优化项。
- 使用真实Issue #4，前端分支基于API分支，形成可评审的堆叠PR。

## 阶段 4：GitHub导入与周期报告

- c9ed125保存第一次导入回归结果：14 passed / 7 failed。失败原因是测试MockTransport客户端缺少base_url，尚未到达业务断言。
- 补齐测试客户端base_url，修复Ruff长行后21 passed；覆盖幂等、PR关系、限流、404、401、服务端失败回滚、网络异常和分页截断。
- 报告显示前一等长周期、绝对差值、样本、规则提示和非随机选取的高返工案例。
