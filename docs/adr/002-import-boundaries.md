# ADR 002：公开仓库、有界导入与事务回滚

状态：接受。日期：2026-09-30。

导入通过 GitHub REST，默认每类最多2页，每页100个。仓库须公开；Token只在后端环境中使用。Issue列表中的PR排除，PR使用独立接口；评审采用首个submitted_at，不能用关闭时间冒充评审时间。

单轮只对前20个PR获取评审和Commit关系，界面显示未覆盖范围。网络/5xx最多3次短重试；403/429直接报告限流或权限问题，用户稍后重试，不长时间阻塞。任何错误回滚整轮数据，之前成功轮次保留。

`(project_id, number)`和`(project_id, sha)`唯一键+upsert保证串行重复幂等，并发冲突返回409。PR—Issue仅识别本仓库显式closing关键字引用，是文本关系而非GitHub已确认关闭事件；不会自动创建Task或猜测AI参与。

局限：同步导入不适用于大型仓库；GitHub分页不是快照，远程数据在导入中变化仍可能漏项。后续采用后台队列、游标、增量水位与导入批次审计。

参考接口语义：[Issues](https://docs.github.com/en/rest/issues/issues)、[Reviews](https://docs.github.com/en/rest/pulls/reviews)、[Rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)。业务口径自行设计。
