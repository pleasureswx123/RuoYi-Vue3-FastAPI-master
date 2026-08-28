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

- Shot Grid 开工统一由管理人员确认，请求字段按任务类型区分：镜头任务仅允许具备 `shotgrid:task:start` 的项目 `director` 或 `has_all_scope` 管理人员确认开工；制作人只能等待，不能自行开始。管理人线下确认依赖资产齐备后提交 `{ lockVersion, shotLockVersion, assetsConfirmed: true }`，服务端在锁内复核管理范围、任务与镜头版本、状态及当前负责人仍为有效 `creator`，并在同一事务审计人工确认。资产任务同样由具备上述权限和范围的管理人员按制作分项确认，以 `{ lockVersion, assetLockVersion, assetItemLockVersion, startConfirmed: true }` 提交；锁内复核任务、父资产和分项三份版本、分项内容及有效负责人，同事务审计。只递增任务版本，不修改父资产和分项元数据版本；其他分项不随本分项或共享目录开工；版本 preflight/create 和失败提交重试仍只允许当前受派的活动制作人员本人，管理人不得代提交或代重试。新目录尚未就绪时，开工进入 `preparing`，沿用现有 NAS 目录 Outbox；目录成功后才进入 `in_progress`。已有成功目录可直接进入 `in_progress`；未开工和目录准备中均不得提交版本。不自动检查资产依赖，不重置已开工任务。
- 资产列表与详情返回 `itemStatusCounts`，固定包含 `unassigned/not_started/preparing/in_progress/reviewing/revision/completed` 七个非负整数键，仅统计活动且未删除分项。父级状态按 `revision → reviewing → in_progress → preparing → unassigned → not_started` 聚合；至少有一个活动分项且全部完成才为 `completed`，无活动分项为 `unassigned`。父级 `task.start` 仅表示可进入分项选择，至少存在一个实际可开工分项才返回；真正 start 必须对选中分项任务提交，不能整资产开工。
- 目录成功回写必须先锁项目，再锁目录操作及任务/存储行，与开工事务使用同一项目协调锁；等待后仍复核 owner + attempt fencing。该锁仅在 NAS I/O 结束后的短事务持有，保证共享目录完成与新分项开工交错时不会遗漏已开工分项。

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
- Shot Grid 项目“归档”只冻结业务写入并保留数据库与 NAS 数据；“永久删除”是独立的不可恢复操作，只允许同时具备 `shotgrid:project:delete` 和跨项目全部数据范围的管理员执行。永久删除必须校验当前项目名称、删除原因和 `lockVersion`，在事务内删除项目业务图并写入独立 `sg_project_purge` 审计/清理队列；NAS 项目目录与独占平台文件由 Leader 后台任务使用租约、`SKIP LOCKED` 和 owner + attempt fencing 清理。不得通过 Navicat 直接删除项目表记录，也不得在数据库事务中等待 NAS I/O。

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
- Shot Grid NAS 目录 Outbox 使用内部任务 `_shot_grid_storage_outbox`，只允许在 PostgreSQL、显式开启 `SHOT_GRID_STORAGE_WORKER_ENABLED` 且当前进程仍持有 Application Leader 时注册和执行；该任务不是可由后台编辑的 `sys_job`。
- Shot Grid 目录 Worker 的正确性不能只依赖 Leader 单实例：数据库领取必须继续使用有期限租约、`FOR UPDATE SKIP LOCKED` 及 owner + attempt fencing。领取、NAS I/O、结果回写必须分成短事务、事务外 I/O、短事务，禁止在数据库事务中等待 SMB。
- 当前目录 Worker 单轮按批量上限串行消费，尚未提供批内并发配置；目录 I/O 使用软超时标记并继续心跳续租，不会也不能把 `asyncio.to_thread` 中仍运行的 SMB 调用硬杀。

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
- 例外：公司内网 `192.168.10.122:12580/12581` 经用户明确决定固定使用 HTTP，生产配置必须显式使用 `TRANSPORT_CRYPTO_ENABLED=false`、`TRANSPORT_CRYPTO_MODE=off`，并在部署文档中保留风险边界。该例外只适用于当前可信内网，不得扩展到公网、跨互联网链路或其他环境；未来切换 HTTPS 时必须恢复 `required` 并重新验收真实加密登录。
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

- 前端开发必须遵守当前工程已经确定的 Vue、Vue Router、Pinia、Axios、Element Plus、公共组件和 Store 体系；后端开发必须遵守 FastAPI、SQLAlchemy、Controller → Service → DAO → DO/VO、权限依赖和事务体系。不得为了局部省事绕开所属技术栈、重复造轮子或在前后端之间混用职责。
- Element Plus 是前端通用 UI 的默认且强制优先实现。表单、输入框、选择器、复选框、单选框、按钮、表格、分页、弹窗、抽屉、卡片、标签、空态、加载、提示和确认等已有对应组件时，原则上必须使用 Element Plus，不得用原生控件加自制交互替代。
- 业务表单和筛选表单默认使用 `ElForm` / `ElFormItem`，不得仅因原生 `<form>` 能提交就脱离组件体系。`section`、`header`、`nav`、`article` 等纯语义容器，以及 `<video>`、`canvas` 等 Element Plus 没有等价能力的浏览器原生元素可以保留。
- 本项目业务 UI 禁止依赖浏览器原生 `submit` 作为业务动作入口。业务表单、筛选表单、弹窗表单、登录表单和确认操作不得使用 `<form @submit...>`、`<el-form @submit...>`、`@submit.prevent` 或 `ElButton native-type="submit"` 驱动业务提交；已有代码中的同类写法属于待治理技术债，不构成后续实现依据。
- 表单提交必须充分使用 Element Plus 契约：`ElForm` 绑定 `model` 和按需配置 `rules`，字段由 `ElFormItem prop` 承载，`ElButton @click` 显式调用统一处理函数，处理函数通过表单实例 `validate()` / `validateField()` 门禁后再执行业务请求，重置使用 `resetFields()` / `clearValidate()`，并落实 loading、disabled、错误提示和重复提交保护。需要 Enter 触发时，在对应 Element Plus 输入组件上调用同一处理函数，不得退回原生 `submit` 链路。
- 表单相关变更验收时必须检查本次作用域内不存在上述原生提交依赖，并通过按钮点击、校验失败、校验成功、加载和重置等直接交互证明 Element Plus Form 契约真实生效；不得把标签替换或页面可打开当作完成证据。
- UI 框架重构必须迁移完整组件结构、属性和交互契约，禁止只把原生标签改成组件标签。以 Element Plus Form 为例，必须按场景正确配置 `model`，用 `ElFormItem` 承载字段并配置对应 `prop`，同时处理提交、校验、布局、加载和可访问性；只有标签名称变化不算完成重构。
- 上述完整迁移要求适用于全部 UI 组件，不只适用于 Form。表格必须落实数据源、列、`row-key`、选择/排序事件、加载和空态；分页必须落实当前页、每页数量、总数及变更事件；弹窗和抽屉必须落实显隐模型、关闭流程、销毁/重置、提交加载及焦点行为；输入、选择、上传、图片预览、按钮、卡片、标签、提示和确认等也必须使用对应组件的标准属性、事件、插槽和状态能力。
- UI 框架改造的验收对象是最终组件树和运行行为，而不是源码中出现了 `el-` 前缀。提交前必须检查组件层级、数据绑定、事件、禁用/加载/错误/空态、可访问性及响应式布局，并通过直接相关的测试或页面交互验证；仅替换标签、仅套一层组件、继续由自制 DOM/CSS/脚本承担核心行为，均判定为未完成。
- 全项目表格遵循 [Element Plus Table 官方契约](https://element-plus.org/en-US/component/table)。行列数据使用 `ElTable` / `ElTableColumn`，键值信息使用 `ElDescriptions`，不得用原生 `<table>` 或手写 DOM 模拟通用表格交互。选择使用 `type="selection"`、`selectable`、`selection-change` 和公开实例方法，不用插槽中的自制复选框维护另一套选择行为；业务行优先使用稳定 `row-key`，树形或保留选择时必须设置。按数据关系使用树形表，不能为了统一外观给平级数据虚构父子关系。
- 资产与制作分项通过 `ElTable` 的 `lazy`、`load`、`row-key`、`tree-props` 展示两级树，父子键包含实体类型和项目范围。父资产分页和批量操作仍以资产为单位，子分项不参与父级选择；展开复用现有鉴权分项接口，保持加载、失败重试、刷新、空态和迟到响应隔离。不得把加载失败当成空分项，也不得因父级可操作而扩大子分项权限。
- 例外仅限 Element Plus 或现有公共组件确实无法覆盖、浏览器协议要求原生元素、或经验证存在明确的可访问性/性能约束。采用例外前必须说明原因、影响和验证方式；“实现更快”“已经写过”或“不熟悉组件库”不是例外理由。
- 页面状态应按作用域放入 Vue 组合式状态或 Pinia，共享状态不得复制为页面级全局变量；导航统一使用 Vue Router；请求统一使用项目 Axios 封装；跨页面复用优先抽取到现有 `components/`、composables 或 Store，禁止在页面内另建平行体系。
- 修改既有页面时必须检查本次作用域内是否仍存在同类原生控件、自制交互或绕过技术栈的实现，并在合理范围内一并治理；不能只替换用户指出的单个节点而保留紧邻的同类违规。
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

### 13.0 快速迭代阶段的分级验证

当前产品功能补齐阶段默认以快速迭代为目标，验证必须与改动风险和开发阶段匹配，不能在每个小改动后重复执行发布级全量门禁。

- 日常小改动只执行最小定向检查：优先检查改动文件、相关模块或一条核心交互；不默认同时运行全量 lint、全量测试、生产构建和完整浏览器旅程。
- 纯文案、样式和局部模板调整通常只做静态检查或单页目视验证；局部逻辑改动只运行直接相关测试；依赖、构建配置、公共基础设施或跨模块契约变更才增加构建或更大范围测试。
- 同一代码状态已经通过的检查不得无理由重复运行。连续开发中的多个相关改动应合并到一个阶段节点集中验证，而不是每修改一个文件就重新跑一遍。
- 浏览器检查只覆盖本次改动最关键的一条路径；除非正在排查视觉或交互问题，不生成多张截图、不遍历无关页面。
- 命令输出默认保留结论和必要错误摘要，不在聊天中回传完整测试清单、构建产物列表或大段重复日志，以减少等待时间和 Token 消耗。
- 阶段功能完成、准备提交重要里程碑、准备发布或用户明确要求时，再执行全量 lint、完整测试、生产构建和必要 E2E；产品全部功能完成后的最终验收必须恢复严格门禁。
- 认证、权限、数据隔离、事务、迁移、文件安全、并发和不可恢复操作属于高风险变更，即使在快速迭代阶段也必须执行与风险直接相关的验证，不得以提速为由省略关键正确性检查。
- 最小检查通过只代表本次改动的定向证据，不得描述为完整测试、完整 E2E 或发布就绪。

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

- 本地开发优先使用 `docker-compose.dev.yml` 启动后端、PostgreSQL 和 Redis；前端继续在宿主机运行。后端开发镜像固定 Python 3.11.15 并内置 FFmpeg。本地 Linux 容器默认关闭 NAS 目录与版本发布 Worker；公司 Linux 生产节点只允许用户配置 `\\192.168.10.64\<共享>\<子目录>`，宿主机通过 autofs 在 `/mnt/ruoyi-shot-grid/dynamic/<共享>` 按需挂载 CIFS，Compose 以 `rslave` 把该挂载命名空间传入容器，后端通过 `SHOT_GRID_NAS_SERVER_MOUNT_MAP` 做固定服务器级解析。不得为每个业务根手工增加 Compose bind，不得允许其他 UNC 服务器，也不得在后端容器内授予挂载权限。生产后端应用身份固定为 UID 100 / GID 101，所有动态 CIFS 共享必须使用 `uid=100,gid=101,forceuid,forcegid`；每次探测和真实 I/O 仍须确认目标共享实际位于 `cifs/smb3`，安装脚本必须以该非 root 身份验证创建、回读、删除和硬链接。平台数据库根目录白名单控制业务可选根，NAS 服务账号 ACL 控制可访问共享；root 探测、普通 bind 目录或手工修改数据库健康状态都不能作为真实 NAS 验收。
- 公司内网 `192.168.10.122` 的正式部署使用 `docker-compose.prod.yml` 和固定项目名 `ruoyi-shot-grid-prod`；映射平台管理端 `12580`、Shot Grid `12581` 和 PostgreSQL Navicat 只读入口 `12582`。宿主机 `5432` 属于既有项目，禁止复用；`12582` 只能使用受限只读角色查询 `sg_*` 表，应用数据库超级用户不得交给客户端。Redis、后端和业务文件必须留在本项目独立网络/命名卷内，不得复用或重启服务器既有项目。
- 当前两个入口固定使用 HTTP；由于浏览器不会为普通内网 HTTP IP 开放 Web Crypto，服务器生产环境必须按已评审例外关闭传输加密，并把 `APP_CORS_ALLOWED_ORIGINS` 限制为两个明确的 HTTP 来源。不得通过前端伪随机降级或隐藏错误来冒充加密仍然生效。
- 生产发布统一走 `deploy/deploy.sh`：先构建版本镜像，再等待独立依赖健康、创建 PostgreSQL 备份、执行 Alembic 迁移和应用/加密预检，最后健康门禁切换；禁止把 `docker-compose.pg.yml` 当作该服务器的生产文件。
- 生产默认关闭 `DB_ECHO` 和文件日志，由 Docker `local` 日志驱动限额轮转；真实密钥只允许保存在服务器 `/etc/ruoyi-shot-grid/production.env`（0600），不得写入仓库、GitHub Secrets 输出或镜像层。
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

1. 当前主分支和 GitHub Actions 已统一为 `main`；内网生产 CD 只能由带 `ruoyi-prod` 标签的专用 self-hosted Runner 手动触发，并受 `intranet-production` Environment 审批约束。服务器外网依赖不稳定时，Windows 开发机使用 `deploy/remote-deploy.ps1` 从已提交的 `main` 构建并离线传输版本镜像，服务器仍必须执行同一套备份、迁移和健康门禁。
2. 后端 `.env.*` 被 Git 跟踪，其中包含示例密码和私钥材料。
3. Alembic 当前已有 Shot Grid `20260810_01 → 20260828_24` 增量迁移链；`05` 至 `19` 保持目录执行、任务/版本/审核、媒体派生、NAS 管理、镜头号治理、跨版本问题、受管角色、延迟目录、审核草稿和项目永久删除语义；`20` 增加一轮多候选、候选级媒体和审核选择；`21` 增加审核通过后的最终版本 NAS 交付 Outbox；`22` 将仅有一个候选的版本自动设为本轮最佳并回填历史单候选；`23` 将标准权限菜单“开始本人任务”更名为“开始任务”，不修改任务状态或自动扩大角色授权；`24` 增加任务预期制作时间范围，仅供制作人参考，不回填历史时间或驱动任务状态。固定角色包仍由平台管理端显式配置。媒体 Worker 默认关闭，视频派生必须配置 FFmpeg。全平台仍缺少能够从真正空库独立建立全部 RuoYi 平台表的完整 baseline。新库使用同步后的 PostgreSQL 初始化 SQL并写入 head，已有平台库执行增量迁移。无版本标记的历史库必须先备份并在克隆库核验结构，不能未经确认直接 `stamp`。
4. Shot Grid 当前 PostgreSQL head 为 `20260828_24`：一个 `sg_version` 表示 V001/V002 轮次，一轮包含 `1..N` 个不可变候选；单候选由系统直接设为本轮最佳且不伪造审核人选择历史，多候选仍由审核人显式选择。审核通过时数据库事务同时创建唯一 `sg_final_delivery(pending)`；同一 Leader 版本 Worker 在事务外将最佳候选发布到源文件同级 `FINAL/`，优先硬链接、失败时校验复制，并写 `FINAL.json`。候选原文件不改名、不覆盖；文件与清单都完成后才能标记 `published`。领取、NAS I/O、回写继续使用短事务、租约、`SKIP LOCKED` 和 owner + attempt fencing。
5. Shot Grid 前端已提交依赖锁文件并使用 `npm ci`；平台管理端仍没有提交 `package-lock.json`，其 CI 与生产镜像使用 `npm install`，存在依赖漂移风险。
6. 新生产 `docker-compose.prod.yml` 已提供独立持久化卷；历史 `docker-compose.my.yml` / `docker-compose.pg.yml` 仍没有完整持久化与安全边界，只能作为兼容参考，不能直接上线。
7. 后端 CORS 默认仍允许任意 Origin 以兼容开发环境；生产必须通过 `APP_CORS_ALLOWED_ORIGINS` 显式收紧，新生产环境模板固定为 `192.168.10.122:12580/12581` 两个来源。
8. 前端生产构建产物较大，Monaco、AI、Mermaid、Shiki 等需要进一步拆包。
9. README 描述了 `ruoyi-fastapi-app`，但当前仓库不存在该移动端目录。

修复这些问题时应分别提交、分别验证，不要把安全治理、数据库迁移和大规模业务重构混在一个不可审查的改动中。
