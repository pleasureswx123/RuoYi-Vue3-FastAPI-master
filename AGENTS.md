# Codex 项目协作指南

## 1. 适用范围

本文件适用于仓库根目录及其所有子目录。若子目录存在更具体的 `AGENTS.md`，应同时遵循子目录规则；发生冲突时，以距离目标文件最近的规则为准。

## 2. 沟通与文档

- 默认使用中文回复。
- 项目文档、提交说明、设计说明和代码注释以中文为主，代码标识符、协议字段及第三方库名称保持原文。
- 先说明结论、影响和验证结果，再展开实现细节。
- 明确区分：
  - 已由代码确认的事实；
  - 根据配置作出的推断；
  - 尚未运行验证的内容。
- 不得把源码存在、页面能打开、静态检查通过或构建成功描述成完整 E2E 已通过。

## 3. 项目全貌

本项目是基于 RuoYi-Vue3 改造的前后端分离管理平台。

当前项目实际使用的主数据库是 **PostgreSQL**。本地开发、问题排查、数据库迁移和正式验收均默认以 PostgreSQL 为准。仓库仍保留 MySQL 驱动、SQL 基线和 Compose 文件，它们属于兼容能力，不代表当前生产运行环境。

### 3.1 顶层目录

- `ruoyi-fastapi-frontend/`：Vue 3、Vite、Pinia、Vue Router、Element Plus 管理端。
- `ruoyi-fastapi-backend/`：FastAPI、SQLAlchemy Async、Redis、APScheduler 后端。
- `ruoyi-fastapi-test/`：独立 Playwright 端到端测试工程。
- `docker-compose.dev.yml`：仅启动本地 PostgreSQL 和 Redis，并使用命名卷持久化。
- `docker-compose.my.yml`：MySQL 完整部署拓扑。
- `docker-compose.pg.yml`：PostgreSQL 完整部署拓扑。

### 3.2 主要运行边界

```text
浏览器
  → Vue Router / Pinia / Axios
  → Vite 代理或 Nginx
  → FastAPI 中间件
  → Controller
  → Service
  → DAO
  → MySQL 或 PostgreSQL

Redis：
  会话、验证码、配置缓存、接口缓存、限流、日志流、分布式锁、调度同步

本地文件系统：
  公开文件、私有文件、回收站、隔离区、代码生成产物

外部网络：
  AI 模型提供商及可选的 IP 地址查询服务
```

### 3.3 基座对齐原则

在本仓库新增独立业务应用、业务模块、数据表或 API 时，必须先与现有前后端基座的实际代码和 PostgreSQL 基线对齐，不能等到实现阶段或用户提醒后才核对。

- 后端事实以 `ruoyi-fastapi-backend/` 中现有 DO、VO、Controller、Service、DAO、权限依赖、异常处理、响应工具、文件服务和 PostgreSQL 初始化 SQL 为准。
- 前端事实以 `ruoyi-fastapi-frontend/` 中现有依赖版本、请求封装、认证、权限、路由、状态管理、组件体系和构建配置为准。
- 需求文档、历史参考项目和设计草案不能覆盖已确认的基座事实；发生差异时先标记为“兼容扩展”或“当前不一致”，完成评审并同步文档后再实现。
- 表字段类型、审计字段、逻辑删除、时间语义、分页、响应 envelope、错误状态、权限依赖、文件引用和迁移交付必须逐项核对，不能只凭名称相似判断兼容。
- 新能力确需扩展基座时，必须明确扩展点、兼容边界和验证方式，不得把尚未实现的扩展描述成基座已有能力。
- 已确认的对齐结论必须同步写入最近作用域的 `AGENTS.md` 和正式契约，不能只保留在聊天记录中。

## 4. 关键入口与核心链路

### 4.1 后端入口

- ASGI/脚本入口：`ruoyi-fastapi-backend/app.py`
- 应用工厂与生命周期：`ruoyi-fastapi-backend/server.py`
- 环境配置：`ruoyi-fastapi-backend/config/env.py`
- 数据库：`ruoyi-fastapi-backend/config/database.py`
- Redis：`ruoyi-fastapi-backend/config/get_redis.py`
- 调度器：`ruoyi-fastapi-backend/config/get_scheduler.py`
- 自动路由注册：`ruoyi-fastapi-backend/common/router.py`

推荐通过后端 CLI 启动：

```powershell
cd ruoyi-fastapi-backend
ruoyi app doctor --env=dev
ruoyi app run --env=dev
```

应用启动顺序不可随意打乱：

1. 创建 Redis 连接池。
2. 竞争并续租 Application Leader 锁。
3. 校验传输加密配置。
4. 初始化平台数据库元数据。
5. 发现、校验并启动插件。
6. 初始化字典和参数缓存。
7. 启动调度器和日志聚合任务。

关闭时必须先停止插件运行时和后台任务，再关闭 Redis、数据库连接池和日志 sink。

### 4.2 登录与权限链

```text
POST /login
  → IP 黑名单、验证码、账号锁定、密码校验
  → 生成 JWT
  → Redis 保存会话 Token
  → GET /getInfo
  → GET /getRouters
  → 前端动态注册菜单和页面路由
```

权限分为三层：

- 登录认证：`PreAuthDependency` / `CurrentUserDependency`
- 接口权限：`UserInterfaceAuthDependency` / `RoleInterfaceAuthDependency`
- 数据权限：`DataScopeDependency`

新增或修改受保护接口时必须同时检查三层权限，不得只依赖前端按钮显隐。

### 4.3 标准业务分层

普通管理模块遵循：

```text
Controller → Service → DAO → DO
                   ↘ VO
```

- Controller 负责参数、FastAPI 依赖、权限、日志和响应格式。
- Service 负责业务规则、跨 DAO 编排和事务边界。
- DAO 只负责数据库读写，不应擅自提交跨业务事务。
- DO 是 SQLAlchemy 表实体。
- VO 是 Pydantic 请求、响应和查询模型。

新增和修改操作通常由 Service 统一执行 `commit()`；异常路径必须 `rollback()`。需要获取新增主键时使用 `flush()`，不要提前提交。

## 5. 后端开发约定

- 最低 Python 版本为 3.10。
- 优先使用异步 FastAPI、`AsyncSession` 和异步 Redis API。
- 不要在异步请求链中直接执行长时间同步 I/O；确需同步处理时，应明确隔离。
- 复用现有 `ResponseUtil`、异常类型、日志、缓存、限流和权限依赖，不要在单个接口中另建一套返回协议。
- 新路由放入对应模块的 `controller/`，并使用 `APIRouterPro`；确认是否需要自动注册及 `order_num`。
- 新业务模型遵循现有 Pydantic alias/camelCase 约定，避免前后端字段风格漂移。
- 修改用户、角色、菜单、权限或系统配置后，必须考虑相关 Redis 缓存失效。
- 日志中不得记录密码、Token、API Key、私钥、完整身份证号或其他敏感信息。
- 定时任务可调用路径受 `JobConstant.JOB_WHITE_LIST` 限制；不要扩大到任意模块或动态执行不可信代码。

## 6. 数据库规则

当前项目实际使用 PostgreSQL；代码仓库仍保留 MySQL 兼容能力。

- 新功能设计、迁移、索引、查询优化和验收优先以 PostgreSQL 为准。
- 在项目尚未正式移除 MySQL 支持前，修改公共 ORM 和平台表时仍需检查是否会无意破坏已有 MySQL 兼容路径；如果只支持 PostgreSQL，应在变更说明中明确范围。
- 不得只依赖 `Base.metadata.create_all()` 完成已有表结构升级；它不能可靠处理字段修改、索引变更和数据迁移。
- 平台结构变更必须提供 PostgreSQL Alembic 版本迁移，并同步维护 `ruoyi-fastapi-backend/sql/ruoyi-fastapi-pg.sql`。
- 如果该变更继续承诺 MySQL 兼容，再同步维护 `ruoyi-fastapi-backend/sql/ruoyi-fastapi.sql`。
- 插件表变更应通过插件清单声明迁移；PostgreSQL 迁移是当前必需项，MySQL 迁移取决于该插件是否继续声明 MySQL 兼容。
- 数据范围查询必须继续使用 SQLAlchemy 条件表达式，不得通过字符串拼接 SQL 绕过参数绑定。
- 任何删除、迁移、回填或批量修复操作都应提供明确范围、事务策略和可恢复方案。

## 7. Redis、调度与多 Worker

- Redis 是认证会话、缓存、限流、日志聚合和分布式协调的组成部分，不是可随意移除的可选缓存。
- 不得将多 Worker 下的共享状态退化为进程内全局变量。
- APScheduler 只有 Application Leader 可以持续调度。
- 修改 Leader 锁、续租、失锁处理或重新竞争逻辑时，必须覆盖：
  - 多 Worker 同时启动；
  - 锁续租失败；
  - Leader 退出；
  - 新 Worker 接管；
  - 调度任务重复执行风险。
- 普通 Worker 发起任务变更后，要保留现有 Redis 同步通知机制。

## 8. 文件管理规则

项目存在两类文件：

- 公开资源：可通过 `/profile` 静态访问，不适合敏感附件。
- 受保护文件：通过鉴权下载，并受所有者、部门、ACL、业务引用和保留策略约束。

正式业务附件应使用 `BusinessFileUpload`，业务表单保存 `{ fileId, name, url }`，后端以完整 `fileId` 列表同步引用。

文件相关变更必须保持：

- 业务记录和文件引用处于同一事务。
- 文件仍被业务引用时不得直接删除。
- 私有文件访问默认拒绝，`deny` ACL 优先于 `allow`。
- 回收站、恢复、永久清理和隔离操作均有审计。
- 路径必须限制在配置的存储根目录内，禁止目录穿越。
- 对账和 SHA-256 校验是完整性机制，不应因前端不展示而删除。
- 永久删除不可恢复，执行前必须确认精确目标和权限。

详细接入规则见：

```text
ruoyi-fastapi-backend/docs/file_management_usage_guide.md
```

## 9. 插件系统规则

插件以 `plugin.yaml` 为契约，清单可以声明：

- 后端模块、路由；
- 前端页面、菜单；
- 权限码；
- 数据库迁移和种子；
- 定时任务；
- Python/npm 依赖；
- 数据库兼容性。

修改插件时必须保证清单、后端源码、前端源码、数据库迁移、种子和权限菜单保持一致。

- 不得在应用启动期间自动执行 `pip install` 或 `npm install`。
- 依赖安装只能通过显式插件命令和依赖策略完成。
- 安装、升级、启停、卸载和清理必须走插件生命周期服务，不能只修改数据库状态。
- 插件路由必须保留运行时启停保护。
- 插件迁移必须可追踪、可诊断，并考虑失败恢复。
- 前端插件组件路径使用 `plugin/<plugin-id>/...`，必须能被 `pluginViewResolver` 和 `import.meta.glob` 解析。

## 10. AI 插件与外部服务

- AI 模型配置属于敏感数据。
- 不得在日志、异常响应、测试快照或前端状态中输出真实 API Key。
- 当前 API Key 使用由 JWT Secret 派生的 Fernet 密钥加密；修改密钥策略时必须提供已有密文迁移方案。
- 自定义模型 `base_url` 必须继续进行 URL 和内网访问约束校验，防止 SSRF。
- 真实 AI Provider 调用可能产生费用；没有用户明确授权时，不执行付费模型验证。
- 模拟响应、Mock 或只验证模型对象创建，不能描述为真实 Provider 对话成功。

## 11. 传输加密

传输层使用 RSA-OAEP + AES-256-GCM，并通过时间戳、nonce 和 Redis 防重放。

- 不得在仓库提交真实 JWT Secret、RSA 私钥、数据库密码或 Provider Key。
- `optional` 与 `required` 模式含义不同，不能为了兼容问题直接降低为明文。
- `required` 模式下 Redis 防重放不可用时应保持失败关闭。
- 上传、下载等 multipart/binary 路径应按现有排除策略处理。
- 密钥轮换要保留 `kid` 和兼容窗口，并覆盖前端公钥缓存 TTL。
- 修改协议字段时必须同步后端中间件、前端 `transportCrypto` 和公开配置接口。

## 12. 前端开发约定

- 前端入口：`ruoyi-fastapi-frontend/src/main.js`
- 路由守卫：`ruoyi-fastapi-frontend/src/permission.js`
- 动态路由：`ruoyi-fastapi-frontend/src/store/modules/permission.js`
- HTTP 封装：`ruoyi-fastapi-frontend/src/utils/request.js`

规则：

- 业务请求统一走现有 Axios 实例，不要绕过 Token、传输加密、错误处理和重复提交保护。
- 菜单来自后端 `/getRouters`，新增页面时同时确认数据库菜单、权限码和组件路径。
- 插件页面放在 `ruoyi-fastapi-frontend/plugins/<plugin-id>/`。
- 大型依赖如 Monaco、Mermaid、Shiki、KaTeX 和 AI 消息组件应优先按页面懒加载。
- 不要继续提高 `chunkSizeWarningLimit` 来掩盖大包问题；应优先拆包或延迟加载。
- 当前项目使用 npm；不要无说明地切换包管理器。
- 当前 `package-lock.json` 被忽略，涉及依赖变更时必须明确指出构建不可复现风险，不得声称依赖已被锁定。

Windows PowerShell 下使用：

```powershell
cd ruoyi-fastapi-frontend
npm.cmd run test:plugin
npm.cmd run build:prod
```

## 13. 验证要求

按改动范围选择最小但充分的验证。

### 13.1 Python 静态检查

```powershell
python -m ruff check ruoyi-fastapi-backend ruoyi-fastapi-test
python -m ruff format ruoyi-fastapi-backend ruoyi-fastapi-test --check
```

### 13.2 后端测试

```powershell
cd ruoyi-fastapi-backend
python -m pytest -q
```

如果当前 Python 环境缺少 pytest 或项目依赖，应明确报告“未执行”，不得写成测试通过。

### 13.3 前端

```powershell
cd ruoyi-fastapi-frontend
npm.cmd run test:plugin
npm.cmd run build:prod
```

### 13.4 E2E

完整 E2E 需要真实启动前端、后端、数据库和 Redis：

```powershell
cd ruoyi-fastapi-test
python -m pytest -v
```

启动成功、健康检查成功、Swagger 可访问或前端构建成功，都不能替代登录、权限、CRUD、文件、插件和调度的实际端到端验证。

## 14. Docker 与部署

- 本地依赖优先使用 `docker-compose.dev.yml`。
- MySQL/PostgreSQL 完整拓扑分别使用 `docker-compose.my.yml`、`docker-compose.pg.yml`。
- 生产部署前必须为数据库、Redis 和文件目录配置持久化卷。
- 生产环境不得使用默认密码、示例私钥或无版本的 `latest` 镜像。
- 数据库和 Redis 端口默认不应暴露到公网。
- 后端健康不等于业务可用；部署验收至少要验证登录、数据库写入、Redis 会话和前端代理。

## 15. Git 与交付边界

- 修改前先确认仓库根目录和 `git status`。
- 保留用户已有修改，不得覆盖无关变更。
- 不提交 `.env`、私钥、Token、日志、缓存、构建目录和临时文件。
- 提交前检查：

```powershell
git diff --check
git status --short
```

- 本地 commit 不代表已 push。
- 未经明确要求不得推送远程、创建 PR 或修改远程资源。
- 报告验证结果时列出实际执行的命令、成功项、失败项和未执行项。

## 16. 当前已知工程风险

后续改动不得忽略以下现状：

1. 当前主分支是 `main`，但 GitHub Actions 只监听 `master`。
2. 后端 `.env.*` 被 Git 跟踪，其中包含示例密码和私钥材料。
3. Alembic 已接入，但当前 PostgreSQL 平台没有已提交的 `versions` 迁移链。
4. 前端没有提交依赖锁文件，Docker 使用 `npm install`。
5. 完整部署 Compose 没有数据库和 Redis 数据持久化卷。
6. 后端 CORS 当前允许任意 Origin，生产环境需要收紧。
7. 前端生产构建产物较大，Monaco、AI、Mermaid、Shiki 等需要进一步拆包。
8. README 描述了 `ruoyi-fastapi-app`，但当前仓库不存在该移动端目录。

修复这些问题时应分别提交、分别验证，不要把安全治理、数据库迁移和大规模业务重构混在一个不可审查的改动中。
