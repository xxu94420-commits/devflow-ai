# ADR 004：公网只读演示与本地工作空间分离

状态：接受（2026-10-01）；关联 Issue #10。

公开站保留 FastAPI 指标计算、React 筛选和 Markdown 下载，不将静态 JSON 冒充实时应用。使用单个多阶段 Docker 镜像：构建 React，再由 FastAPI 在同域提供静态文件和 API。原有本地双容器 Compose 保留。

READ_ONLY=true 时在 HTTP 边界拒绝所有非 GET/HEAD/OPTIONS 请求。即使提供有效写入密钥也不能解除只读；前端依据 capabilities 接口隐藏入口，默认禁止编辑直到确认服务能力。新接口同样受保护。

公开站使用独立、可重建的 SQLite 数据库，仅初始化 synthetic/demo 数据和读取 DevFlow AI 自身公开仓库。禁止把本地数据库、环境文件或 Git 凭据复制进镜像。真实 GitHub 导入失败时仍可展示 Demo，不制造替代的 Live 数据。

默认提供 Render 免费 Web Service 配置，不创建付费资源。免费实例会休眠且磁盘不持久，适合无用户写入的作品集演示；启动重建数据，GitHub 快照不宣称实时同步。上线需要用户的托管账号。生产多人协作仍需独立身份认证、数据库持久化、备份与容量验证。
