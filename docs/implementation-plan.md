# DevFlow AI 实施设计

本项目从空目录开始自主实现。业务代码不取自其他统计看板。

1. 建立关系模型、指标口径及 FastAPI MVP，以临时数据库测试关键约束。
2. 添加 React/TypeScript 页面、ECharts 图表、任务和 AI 记录入口。
3. GitHub REST 公开仓库导入，分页、限流、事务和幂等键。
4. 范围周报、前一等长周期比较、实际开发案例及局限说明。
5. Alembic、Docker Compose、CI，运行完整测试与构建并记录证据。

## 目录和 API

`backend/app` 存放模型、schema、指标服务、导入服务与 API；`backend/tests` 为离线测试；`frontend/src` 为页面和图表；`docs` 存放口径、协议和 ADR。

REST API 前缀 `/api`：projects、requirements、issues、tasks、interactions、commits、pull-requests、tests、defects、retrospectives；分析入口 metrics，项目导入 github/import，演示初始化 demo/seed，周报 reports。任务详情返回链路时间线。

## 关系模型

Project 区分 live/demo。Requirement 关联多个 Issue 与 Task；Task 可关联 Issue、多个 AIInteraction、Commit、PR、TestResult、Defect、Retrospective。Commit/PR 通过中间表支持多任务。GitHub 对象保留 author、labels、状态和来源时间，复合唯一键防止重复。

分析按项目模式隔离；任务按完成时间归属窗口，开放任务不参与耗时均值。GitHub 指标独立于人工 AI 数据，不从提交文字猜测 AI 使用。
