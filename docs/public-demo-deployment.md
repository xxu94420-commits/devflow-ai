# 公网只读演示

关联 Issue #10 / PR #11 / ADR 004。2026-10-01已部署并完成公网验收：**https://devflow-ai-demo.onrender.com**。

当前运行提交：`efc0609ab748227c4036127542a9753816b98f01`（PR #13），2026-10-02完成新版验收。首次部署为 `0c2308d`（PR #11）。Render服务仍为 Docker / Free；后续文档提交不改变已运行的程序版本。

新版实际验收：`/api/ci/status` 返回3600秒周期、artifact权限未配置；公开采集3条真实运行，计数保持null。浏览器项目详情显示采集时间、来源链接和权限提示，截图为 `docs/screenshots/public-ci-evidence.png`。完整JUnit回流仅在本地独立验收库验证，未上传本机凭据或数据库。

## Render 免费 Web Service

1. 登录自己的 [Render 账号](https://dashboard.render.com/)。选择 Hobby 工作空间和 Free 实例；不要为本演示添加付费实例、磁盘或数据库。如账号要求支付信息，先停下确认。
2. 在主分支 CI 通过后打开 [部署入口](https://render.com/deploy?repo=https://github.com/xxu94420-commits/devflow-ai)，或 New → Blueprint，连接此仓库并读取根目录 `render.yaml`。
3. 审核资源仅有一个 `devflow-ai-demo` Docker Web Service，plan=free。保持 READ_ONLY=true；不需要 GitHub Token、数据库密码或自定义域名。
4. 点击部署。首次拉取依赖需要数分钟，Render 提供实际的 HTTPS 地址，名称冲突时可能带后缀，不能预先假定网址。
5. 按下方清单验收后，再把**实际地址**写入 README 和简历。当前关闭自动部署，后续更新在 CI 通过后手动部署最新主分支。

## 数据与边界

- 单个多阶段镜像内构建 React，FastAPI 同域提供 `/`、`/assets` 和 `/api`；前端不会请求访客电脑的 localhost。
- 镜像使用非 root 用户，只复制程序、迁移和构建产物。Docker 上下文排除 `.env`、Git、本地数据库、依赖目录与缓存。
- 启动执行迁移，幂等生成42个 synthetic/demo 任务。`DEMO_IMPORT_GITHUB=true` 时读取 `xxu94420-commits/devflow-ai`，最多一页/列表、最多20个PR详情，总时间预算60秒；失败不影响Demo。
- Issue/PR/Commit元数据为启动快照，项目详情显示采集时间与覆盖范围。CI另由 `CI_SYNC_INTERVAL_SECONDS=3600` 每小时读取最新运行，服务休眠期间不采集；页面展示实际启用状态。Live没有人工AI记录时保留缺失。
- CI运行元数据不需要Token；下载JUnit artifact需要维护者在Render Environment自行配置 `GITHUB_TOKEN`，仅此仓库的Actions读取权限即可。此配置可选，未配置时计数显示未知；不要发送Token到聊天或提交Git。详见[自动测试链路](ci-test-evidence.md)。
- 不上传本地数据库，不导入毕业论文仓库，不复制本机 GitHub 凭据。公开数据就是 synthetic/demo 和公开仓库元数据。
- `READ_ONLY=true` 在服务端拒绝全部非 GET/HEAD/OPTIONS 方法，返回403；正确API Key也不能绕过。公开站没有新增、导入、编辑或密钥输入入口。
- 仍可切换数据模式、筛选日期/项目、查看五个页面和下载 Markdown。所有读取数据都是公开的；只读不等于隐私权限管理。

## 限制

Render [免费实例](https://render.com/docs/free) 空闲15分钟后休眠，重新访问存在冷启动等待；免费用量受账号额度限制。磁盘是临时的，重新部署/重建可能丢失，因此本站只保存可重建演示数据。每次新容器初始化的模拟日期会变化；不用于长期真实指标观测。未提供常驻可用性承诺或负载测试结果。

需要常驻演示时，可在明确预算后选付费实例；真实多人协作应另行设计账号、持久数据库、备份和权限。

## 本机验证同一镜像

```sh
docker build -t devflow-public .
docker run --rm -p 127.0.0.1:8081:8000 devflow-public
```

打开 `http://localhost:8081`。本机默认不请求GitHub，添加 `-e DEMO_IMPORT_GITHUB=true` 可读取上述公开仓库。原来的 `docker compose up --build` 仍用于本地可编辑工作空间。

## 上线验收

- HTTPS 首页与 JS/CSS 返回成功，没有 localhost 请求。
- `/api/capabilities` 返回 `{"read_only":true}`；`/api/health` 返回200。
- 所有五页可浏览，任务详情、项目筛选、周报预览和下载可用。
- `POST /api/demo/seed`、`POST /api/github/import`、`PUT /api/tasks/1` 返回403，数据库记录不变化。
- `/api/missing` 和 `/.env` 返回404。
- Demo 标记明确；Live 仅展示实际导入内容，缺少样本时不生成效率结论。

GitHub Actions `public-demo-smoke` 会实际构建并运行此镜像，验证上述基础HTTP契约；公网 HTTPS 和浏览器体验需要部署后单独验收。

可复现已执行的公网HTTP验收（要求先安装backend依赖）：

```sh
python scripts/check_public_demo.py https://devflow-ai-demo.onrender.com
```

脚本先检查服务宣告只读，再发送应被拒绝的写请求；不得对其他工作空间运行。首次验收结果：42个模拟任务、1个真实仓库，主页/指标/详情/报告通过，写入返回403且读取数据保持一致，未知及环境文件路径返回404。
