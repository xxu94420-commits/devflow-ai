# 数据字典与关联协议

所有实体含整数主键id；时间用SQL DateTime保存UTC无时区值，输入带时区时间先转换UTC。日期接口接受ISO 8601。数据库建表与索引由`backend/migrations/versions`中的显式Alembic脚本管理。

| 实体 | 关键字段 | 来源和约束 |
| --- | --- | --- |
| Project | name, repository, description, mode, created_at, imported_at, import_note | repository唯一；mode=live/demo；import_note表示最近导入覆盖范围 |
| Requirement | project_id, title, description, change_count, created_at, completed_at | 人工记录；变更数非负；完成不得早于创建 |
| Issue | project_id, requirement_id, number, title, author, labels(JSON), state, url, created_at, closed_at | GitHub公开数据；(project_id,number)唯一；PR从Issue列表排除 |
| Task | project_id, requirement_id, issue_id, title, description, task_type, estimated_hours, actual_hours, uses_ai, rework_count, created_at, completed_at | 标题≤200，描述≤2000；7种类型；耗时有限非负；完成必须有actual_hours |
| AIInteraction | task_id, tool, stage, purpose, prompt_summary, suggestion_summary, prompt_count, suggestion_count, accepted_count, human_modification_count, modification_notes, estimated_before_hours, actual_hours, quality_result, notes, created_at | 人工脱敏；摘要≤1000；prompt_count≥1；0≤accepted_count≤suggestion_count；采纳布尔可由accepted_count>0得出 |
| Commit | project_id, sha, message, author, url, created_at | (project_id,sha)唯一；时间取Git committer date；不采集源码差异 |
| PullRequest | project_id, number, title, author, labels, state, url, created_at, first_review_at, closed_at, merged_at | 唯一键同Issue；未采集到正式评审时为null |
| TestResult | task_id, name, passed, total, created_at | total≥1，0≤passed≤total；每条是一轮套件执行 |
| Defect | task_id, title, severity, created_at, resolved_at | severity=low/medium/high/critical；resolved_at可空；不得早于created_at |
| Retrospective | task_id, summary, action_item, created_at | 摘要≤2000，行动≤1000；与任务关联 |
| TaskCommit / TaskPR | task_id+commit_id / task_id+pr_id | 联合主键；同项目；支持多对多 |
| PRCommit / PRIssue | pr_id+commit_id / pr_id+issue_id | GitHub导入关系；PRIssue是显式文本引用而非关闭事件认证 |

## 链路建立

1. 导入Project、Issue、PR、Commit，保留远程真实时间。
2. POST requirements创建需求；PUT issues/{issue_id}/requirement/{requirement_id}关联Issue。
3. POST tasks声明项目、需求、Issue。所有外键由服务验证归属，拒绝跨项目关联。
4. POST interactions / tests / defects / retrospectives追加记录。PUT tasks/{id}完整更新耗时与状态；PUT defects/{id}记录resolved_at。
5. PUT tasks/{id}/links增量关联本平台Commit/PR的id（不是GitHub编号）；重复关联不重复插入。
6. GET tasks/{id}合并各实体时间线，并返回缺陷数、首次测试和AI统计。

Task允许尚未关联Issue/Requirement，以支持独立任务与补录；界面不能把缺失链路伪装为完整链路。Requirement可以通过Task直接关联，也可以从所关联Issue取得。数据删除未实现，避免误删链路；本地测试数据库可由测试框架销毁。

## 模式与范围

Demo实体依赖一个`synthetic/devflow-demo`项目；seed第一次执行生成42个任务，重复执行返回created=false，不刷新日期或覆盖人工修改。Live导入不创建AI记录；只在用户明确记录后出现AI数据。默认展示最近30天，历史仓库可能需要调整日期。
