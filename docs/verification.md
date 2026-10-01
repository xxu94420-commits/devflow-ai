# 实际验证记录

执行日期：2026-09-30首次实现，2026-10-01继续交付验证。

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
