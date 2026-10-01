# 实际验证记录

执行日期：2026-09-30首次实现，2026-10-01继续交付验证。

## 2026-10-02 自动测试证据链路

- 本地后端57项、前端6项测试通过；Ruff、Black（单worker）、ESLint、Prettier、TypeScript与生产构建通过。
- 功能提交025f9d7的[GitHub Actions](https://github.com/xxu94420-commits/devflow-ai/actions/runs/36894843708)已完成且success；包含backend、frontend、test-evidence、docker-smoke、public-demo-smoke。
- 第一阶段真实run 36857274639回流44个通过用例，重复同步仍只有1条关联TestResult。它与最终57+6项回归不是同一批运行。
- 浏览器实际打开独立验收库的真实任务，确认Issue、CI运行、测试时间线、41/3分套件计数、来源链接和SHA256；只读页无同步和关联编辑入口。截图为 `docs/screenshots/ci-evidence.png`，不是公网已配置凭据的证据。
- Windows Black多worker执行曾挂起，改为单worker后完成；不将环境进程问题描述为业务测试失败。
- 文档提交0708ca8的push检查成功，但PR run 36896069176首次attempt在拉取nginx镜像元数据时遇到Docker Hub 502；该次后端、前端与公网容器作业通过。保留失败记录并重跑完整工作流，不把上游故障伪造成测试用例失败。

## 已完成的检查

- 后端最初4项指标测试通过；API阶段10项通过；GitHub导入初次14通过/7失败，修复模拟客户端base_url后21通过；增加日期边界及完整更新链路后23通过。
- Ruff检查和Black格式检查通过。
- Alembic实际执行upgrade → check → downgrade → upgrade；`check`确认模型和迁移无新增差异。降级仅对初始空库操作。
- TypeScript、ESLint、Prettier检查通过；Vitest 3项通过；Vite生产构建通过。
- [GitHub Actions 首轮验证](https://github.com/xxu94420-commits/devflow-ai/actions/runs/36689990449)：backend、frontend、docker-smoke均success，提交95275a9。
- Docker任务实际构建前后端镜像，`docker compose up --build -d --wait`成功；通过Nginx请求首页、健康接口、Demo初始化和指标接口。
- 真实公开仓库导入：论文仓库首次0 Issue / 0 PR / 3 Commit；本项目首次5 Issue / 3 PR / 6 Commit。数量只代表采集时点，不是虚构业务量。

## 浏览器验收

- 桌面和窄屏均实际打开；总览显示趋势、任务分布和synthetic/demo标记。
- AI页面显示每类型AI与非AI各3个样本，不输出时间节约率。
- 周报按钮实际生成Markdown预览，含前期比较、返工规则和案例。
- 实际创建`synthetic/demo data · 浏览器验收任务`并保存模拟AI摘要，任务自动显示AI标记、Prompt 1次、采纳1条和新增时间线事件。该记录只在本地demo库，未当作真实开发工时。
- 浏览器工具等待Blob下载事件超时，未据此声称文件落盘成功。增加服务端Markdown attachment下载接口，并以HTTP测试验证内容、文件名与预览一致；前端改为直接下载该地址。

## 非阻断提示和未验证范围

- Starlette/AnyIO弃用警告仍存在，当前测试通过。
- 按需导入后ECharts构建块526.44KB（gzip176.89KB），相较初版完整导入1,036.31KB减少；仍超过Vite默认500KB提示。此处是构建产物大小，不是网络加载性能测试。
- 本机无Docker；部署验证由上述Linux CI完成，不声称本机Docker运行成功。
- 未执行PostgreSQL集成回归、负载测试、完整无障碍审计或多用户安全审计。
- 先前移除远程字体时文本替换留下CSS片段，被Prettier检测并修复。未忽略错误直接交付。

## 2026-10-01 下载与交付回归

- 增加Markdown附件接口后24项Pytest通过，Ruff/Black通过。
- TypeScript、ESLint、Prettier复查通过；图表优化后的生产构建与3项Vitest通过。
- 浏览器任务创建、AI保存、统计聚合、时间线更新和Live来源说明实际通过，浏览器error日志为空。
- 最终主分支CI以仓库Actions中的实际状态为准；不将早先提交的成功当作后续代码已验证。
- 最终功能提交`c35daf9`的[PR验证](https://github.com/xxu94420-commits/devflow-ai/actions/runs/36850593007)与[push验证](https://github.com/xxu94420-commits/devflow-ai/actions/runs/36850588460)均success，包含24项后端测试、3项前端测试、格式/构建/迁移和Docker冒烟。

## 2026-10-01 公网只读演示验收

- 新增只读边界、初始化失败/超时验证后，后端31项测试通过；前端仍3项通过。Ruff、Black、ESLint、Prettier、TypeScript与生产构建通过。
- PR #11分支提交26c469b的[CI](https://github.com/xxu94420-commits/devflow-ai/actions/runs/36855429199)和合并提交0c2308d的[主分支CI](https://github.com/xxu94420-commits/devflow-ai/actions/runs/36855614811)均success，包含新增public-demo-smoke作业的真实容器构建与运行。
- 用户本人登录Render；创建一个Docker / Free服务，实际部署0c2308d，公网地址为 https://devflow-ai-demo.onrender.com。
- `scripts/check_public_demo.py` 实际对公网执行通过：主页、指标、项目/任务详情、Markdown下载；7种写请求返回403，任务/项目响应不变；`/.env`及未知API返回404。
- 公网浏览器实际呈现只读标识、42个模拟任务及图表，截图保存为 `docs/screenshots/public-demo.png`。本地同构预览实际查看项目筛选、任务完整时间线与报告预览；不将本地浏览器检查混称为全部公网交互已逐项检查。
- 公网Live实际读取本项目仓库，采集时间UTC `2026-10-01T11:31:36.644843`，快照为6 Issues / 5 PRs / 18 Commits；此为当时采集结果，不是持续同步或历史业务规模。无毕业论文仓库或本地人工记录上传。
- 未声称浏览器文件下载已落盘：验证的是HTTP附件响应与正文。保留冷启动、临时磁盘和上游限流限制。
