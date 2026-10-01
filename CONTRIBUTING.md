# 贡献指南

先创建Issue描述问题、口径和验收条件，再从main建立`codex/<feature>`（或团队约定）分支。小步提交，保留真实测试失败与修复，不能倒填时间或制造评审。

后端：`cd backend`，安装requirements后运行`python -m pytest -q`、`python -m ruff check .`、`python -m black --check .`。模型修改须生成/审阅Alembic迁移，验证upgrade/check/downgrade/upgrade，尤其注意SQLite批量迁移和PostgreSQL差异。

前端：`cd frontend && pnpm install --frozen-lockfile`，运行`pnpm lint && pnpm test && pnpm build`，并实际检查空数据、请求错误、移动/桌面布局。表单变化必须验证错误提示，不只看编译。

指标变化先更新metric-dictionary和测试，再更新界面。PR中说明分子/分母、样本窗口、缺失值处理和已知偏差。不得加入真实密钥、完整敏感Prompt、私人数据集。示例必须标为synthetic/demo。

维护辅助脚本`scripts/github_workflow.py`绑定本作品集仓库；它不是平台运行依赖，不应放到服务端执行。Fork贡献者用自己的GitHub CLI/网页工作流。
