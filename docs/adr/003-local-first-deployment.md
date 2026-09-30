# ADR 003：SQLite优先与同源部署

状态：接受。日期：2026-09-30。

个人作品集先使用SQLite，数据文件通过Docker命名卷持久化。SQLAlchemy统一查询层、Alembic显式版本迁移，预留psycopg PostgreSQL连接串。运行时不调用create_all，避免绕过迁移历史；测试临时数据库可使用create_all。

前端静态资源由Nginx服务，`/backend/`代理到FastAPI，避免在浏览器使用Docker内部域名。Compose只绑定127.0.0.1。生产公网部署需TLS、完整身份认证、审计和备份，当前API Key仅用于限制写入，不能代替多租户访问控制。

选择单体而非微服务，因为边界尚在验证，模块化服务已足以支持作品集。代价是长导入占用线程、分析在内存聚合，规模化后需分页和数据库聚合。
