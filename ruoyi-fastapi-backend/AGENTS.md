# 后端 Codex 协作指南

## 1. 适用范围

本文件适用于 `ruoyi-fastapi-backend/` 及其所有子目录，并补充仓库根目录的 `AGENTS.md`。根目录规则仍然有效；涉及后端代码时，还必须遵循本文件。

## 2. 后端定位

后端不是单一 FastAPI CRUD 服务，而是由以下能力共同组成的平台：

- FastAPI HTTP/API 应用；
- SQLAlchemy 异步数据访问；
- PostgreSQL 主数据库及仓库保留的 MySQL 兼容能力；
- Redis 会话、缓存、限流、日志流和分布式协调；
- APScheduler 定时任务；
- RBAC 接口权限和部门数据权限；
- 文件存储、ACL、引用、回收站和对账；
- 插件发现、安装、迁移、启停和运行时；
- AI 模型管理与流式对话插件；
- `ruoyi` 运维 CLI 和 TUI。

修改任何基础设施代码时，应检查其对 HTTP 服务、CLI、插件和多 Worker 的共同影响。

当前数据库基线：

- 实际开发、运行、迁移和验收默认使用 PostgreSQL。
- 默认依赖文件为 `requirements-pg.txt`。
- 默认本地基础设施为根目录 `docker-compose.dev.yml`。
- `requirements.txt`、MySQL SQL 和 MySQL Compose 属于保留的兼容路径，不是当前首要运行基线。

新增 Shot Grid 或其他独立业务模块时，业务设计文档不能替代后端事实核对。实现前必须逐项对齐当前 DO/VO、响应与异常、权限依赖、文件引用、时间与逻辑删除语义以及 PostgreSQL 迁移约定；兼容扩展必须显式标注并验证，禁止把设计草案直接当成后端已有契约。

## 3. 目录职责

```text
app.py                  ASGI/脚本入口
server.py               FastAPI应用工厂和生命周期
config/                 环境、数据库、Redis、Scheduler
common/                 路由、上下文、注解、切面、公共模型
middlewares/            全局HTTP中间件
exceptions/             统一异常及处理器
module_admin/           平台管理业务
module_generator/       代码生成
module_plugin/          插件管理HTTP接口
module_task/            允许被调度器调用的任务
plugins/core/           插件平台和运行时
plugins/ai/             AI插件
cli/                    ruoyi CLI、Wizard和TUI
utils/                  跨模块工具
alembic/                平台数据库迁移入口
sql/                    MySQL/PostgreSQL初始基线
tests/                  后端测试
docs/                   运维和接入文档
```

不要编辑或依赖以下生成物：

- `build/`
- `*.egg-info/`
- `__pycache__/`
- `logs/`
- `vf_admin/`

## 4. 应用生命周期

后端入口优先使用：

```powershell
ruoyi app doctor --env=dev
ruoyi app run --env=dev
```

`server.py` 的生命周期顺序具有业务含义：

1. 创建 Redis 连接池。
2. 获取 Application Leader 锁并启动续租。
3. 校验传输加密运行配置。
4. 导入并创建平台实体表。
5. 启动插件运行时并同步插件实体。
6. 检查 Redis，初始化字典和参数。
7. 启动 Scheduler 和日志聚合。

修改生命周期时必须保证异常路径也会释放：

- 插件运行时；
- 日志聚合任务；
- Scheduler、锁续租和同步监听；
- Redis 连接池；
- SQLAlchemy Engine；
- Loguru enqueue sink。

不得仅在正常退出路径释放资源。

## 5. 路由与依赖

### 5.1 路由定义

- 业务路由放在对应模块的 `controller/`。
- 使用 `APIRouterPro` 定义路由组。
- 路由组需明确 `prefix`、`order_num`、`tags` 和认证依赖。
- 自动注册只扫描项目一级模块下的 `controller/[!_]*.py`。
- 不希望自动注册的路由必须明确设置 `auto_register=False`。
- 插件路由还必须经过插件运行时启停保护。

### 5.2 认证和授权

受保护接口通常需要：

```python
dependencies = [PreAuthDependency()]
```

接口级权限使用：

```python
dependencies = [UserInterfaceAuthDependency('system:xxx:list')]
```

或：

```python
dependencies = [RoleInterfaceAuthDependency('admin')]
```

涉及组织、用户、角色、文件或部门数据时，还应注入 `DataScopeDependency`。

规则：

- 不得只依赖前端按钮权限。
- 不得把“已登录”等同于“有业务权限”。
- 不得为了方便给普通角色返回 `*:*:*`。
- 排除认证的公开路由必须保持范围最小，并检查 HTTP Method。
- 从 `RequestContext` 读取用户前，必须确保认证依赖已经执行。

## 6. Controller、Service、DAO、Entity

### 6.1 Controller

Controller 负责：

- 请求模型和查询参数；
- FastAPI 依赖注入；
- 登录、接口权限和数据范围；
- 操作日志、缓存、限流注解；
- 调用 Service；
- 使用 `ResponseUtil` 返回统一协议。

Controller 不应包含复杂事务或长段数据库逻辑。

### 6.2 Service

Service 负责：

- 业务校验；
- 跨 DAO 编排；
- 事务提交和回滚；
- 缓存一致性；
- 面向业务的异常转换。

事务范式：

```python
try:
    # DAO写入及跨实体编排
    await query_db.commit()
except Exception:
    await query_db.rollback()
    raise
```

需要新主键时由 DAO `flush()`，不要为了取得 ID 提前 `commit()`。

### 6.3 DAO

- 使用 SQLAlchemy 表达式和参数绑定。
- DAO 不应隐式提交由 Service 管理的事务。
- 分页统一复用 `PageUtil`。
- 动态条件使用 SQLAlchemy 条件表达式，不拼接不可信 SQL。
- 批量更新、删除必须明确 ID 范围和数据权限条件。

### 6.4 Entity

- `entity/do/`：SQLAlchemy 数据库实体。
- `entity/vo/`：Pydantic 请求、响应和查询模型。
- 保持现有 snake_case Python 字段与 camelCase API alias 约定。
- 新实体必须确保应用启动或迁移阶段能导入到 `Base.metadata`。

## 7. 数据库与迁移

当前项目实际使用 PostgreSQL。所有新功能、故障排查、迁移、索引设计和正式验收先以 PostgreSQL 为准。仓库仍保留 MySQL 兼容代码；除非任务明确移除 MySQL，否则不要无意破坏已有兼容路径。

### 7.1 平台表

平台表结构变更需要同时维护：

- SQLAlchemy DO；
- PostgreSQL Alembic 版本迁移；
- `sql/ruoyi-fastapi-pg.sql`；
- 相关种子和测试。

如果本次功能继续承诺 MySQL 兼容，再同步维护 `sql/ruoyi-fastapi.sql` 和对应方言测试。不得因为仓库存在 MySQL 文件，就把 MySQL 验证描述成当前生产验收结果。

不得把 `Base.metadata.create_all()` 当作已有表的升级机制。

### 7.2 插件表

插件迁移由 `plugin.yaml` 声明，并分别提供：

```text
migrations/mysql/
migrations/postgresql/
```

PostgreSQL 迁移是当前项目的必需交付物。只有插件清单继续声明 `mysql` 兼容时，才要求同步提供并验证 MySQL 迁移。

迁移需要稳定版本号、可追踪执行记录和明确的失败处理。升级时不得绕过插件生命周期直接执行未知 SQL。

### 7.3 数据库兼容

- 优先采用 PostgreSQL 可正确执行且可利用索引的查询方式。
- 注意遗留 MySQL `find_in_set` 与 PostgreSQL 数组、递归查询、类型系统和 SQL 方言差异。
- 如果公共代码仍声称双数据库兼容，新查询至少做双方言静态检查；只面向 PostgreSQL 的实现必须明确标注适用范围。
- 初始 SQL 中的平台菜单、权限码和默认任务应与代码保持一致。

### 7.4 Shot Grid 当前数据库边界

- Shot Grid 领域模块位于 `module_shot_grid/`，包含 22 张 `sg_` 表 DO、项目访问依赖、范围导航、项目创建/存储状态/成员/范围查询、镜头与资产制作人选项、镜头导入模板下载、镜头和资产 Excel 预检与正式提交、独立任务管理、版本提交/NAS 发布、`auto_single` 自动审核闭环，以及 NAS 目录 Outbox Worker、目录操作查询和人工重试接口。
- 首个增量迁移为 `20260810_01`，并已同步 `sql/ruoyi-fastapi-pg.sql`、菜单、权限和字典种子。
- `20260810_04` 是无版本历史库的采用/向前修复迁移：统一秒级时间精度和空字符串审计默认值，补强序场次、资产制作分项、主文件及集/场次编号约束；不得改写历史 01/02/03 代替修复。无 `alembic_version` 的历史库只能在备份和克隆核验后 stamp 01，再执行 upgrade head。04 必须在任何 ALTER 前预检冲突并整体失败，不能猜测修复业务数据；downgrade 不恢复从未被正式 revision 声明的旧弱漂移，秒以下精度只能从升级前备份恢复。
- 当前 head `20260811_06` 在任何 DDL 前预检版本提交的源文件唯一性、每任务未解决提交唯一性，以及状态、租约和错误字段组合；冲突分别以 `SG_VERSION_FILE_ALREADY_BOUND`、`SG_VERSION_SUBMISSION_ACTIVE` 或 `SG_VERSION_SUBMISSION_EXECUTION_STATE_CONFLICT` 整体失败。通过后增加“我的任务”索引、源文件全局唯一索引、将 `failed` 纳入每任务未解决提交部分唯一索引、提交执行/错误状态 `CHECK`，并为审核动作增加持久化幂等键、请求哈希和首次成功响应快照。06 的 downgrade 精确移除本 revision 对象，并把活动提交索引恢复为 05 的不含 `failed` 语义，不修改业务数据。
- Shot Grid 只承诺 PostgreSQL；非 PostgreSQL 环境不得把 `sg_` 模型加入平台元数据，Shot Grid revision 的升级和降级必须保持 no-op。
- 已有平台 PostgreSQL 库通过 Alembic 执行增量迁移；新库通过同步后的 PostgreSQL 初始化 SQL 建立全量结构并写入 Alembic head。当前仍不存在完整平台 Alembic baseline，不得声称首个 Shot Grid revision 能从真正空库独立建立 RuoYi 平台。
- 项目创建/编辑/归档、成员变更、集/场次/镜头/资产普通管理、任务分配/改派/开始、Excel 正式提交、版本正式提交、审核意见/回复/解决、审核动作和目录人工重试必须由 Service 在同一数据库事务写领域数据、必要的 Outbox/文件引用与 `SysOperLog`；不得使用会异步入 Redis 的平台 `@Log` 冒充同事务审计。项目、集、场次、镜头、资产和制作分项已实现业务归档而非物理删除；独立业务前端的项目、镜头和资产真实列表/详情、CRUD、任务分配及对应 Excel 预检/提交已接入真实接口，不回退 Mock。项目管理、镜头管理/镜头 Excel 导入、资产管理/资产 Excel 导入三个子集均已完成隔离 PostgreSQL、Redis、真实平台账号、生产 Nginx 与 Chrome 浏览器旅程。资产需求人工处理、`manual_batch` 审核单、媒体派生及任务/版本/审核等其余业务页面仍待后续实现；任何子集旅程均不等于完整系统 E2E 或生产就绪。
- 项目管理页面使用四项查询/预览类接口：`GET /shot-grid/storage-roots/options` 只返回 `enabled + healthy` 根目录的安全摘要；`POST /shot-grid/storage-roots/{storageRootId}/project-path-preview` 只执行规范化、路径拼接和占用检查，不写库、不创建目录；`GET /shot-grid/member-candidates` 用于创建项目，要求 `shotgrid:project:add`；`GET /shot-grid/projects/{projectId}/member-candidates` 用于成员维护，要求 `shotgrid:member:add` 和项目总监角色。两类候选查询均应用 `DataScopeDependency(SysUser)`，只分页返回有效平台账号的用户、昵称、头像和部门摘要，不返回联系方式、认证字段或密码。项目创建和添加/恢复成员事务也必须使用同一用户数据范围重新校验账号，路径预览不能替代创建事务内对根目录和路径冲突的重新校验。
- 镜头页通过 `GET /shot-grid/projects/{projectId}/shot-assignee-options` 分页查询可分配制作人；接口要求 `shotgrid:shot:list` 与项目访问，只返回活动项目成员、有效未删除平台账号且具有非空项目内 `producerCode` 的安全摘要，`keyword` 只匹配账号、昵称和制作人缩写。创建、编辑和分配写事务仍必须重新校验，不得把选项响应当成写入授权。
- 资产页通过 `GET /shot-grid/projects/{projectId}/asset-assignee-options` 分页查询可分配制作人；接口要求 `shotgrid:asset:list` 与项目访问，分页、关键字和安全投影规则与镜头制作人选项一致。资产或制作分项创建、编辑、导入、首次分配和改派仍必须在写事务中重新校验项目状态、成员状态和项目内制作人缩写。
- `GET /shot-grid/imports/shots/template` 要求 `shotgrid:shot:import`，直接返回鉴权后的 XLSX 二进制、文件名为 `镜头导入模板-shot-v1.xlsx` 的 `Content-Disposition` 和 `X-Shot-Grid-Template-Version: shot-v1`，不套 JSON envelope。应用层传输加密只精确放行该 GET，不得把同前缀预检或提交 JSON 路由降级为明文。部署资源缺失或摘要不符稳定返回 HTTP 503 / `SG_IMPORT_TEMPLATE_UNAVAILABLE`。
- 后端打包模板 `module_shot_grid/resources/templates/shot-v1.xlsx` 的冻结 SHA-256 为 `F6370BBB14548B645782ABF0734E930EC10470565821BA6C8FD1B6A2D9D96EE0`。它从正式样表生成匿名部署副本时只改动 5 个 XML：`xl/workbook.xml` 删除 `x15ac:absPath`，`xl/sharedStrings.xml` 的 88 条共享字符串全部替换为只含表头、合法编号、制作人 A-C 和示例文本的匿名内容，`docProps/core.xml` 与 `docProps/app.xml` 匿名化作者/应用属性，`docProps/custom.xml` 清空自定义属性。其余 13 个条目（含两个 Sheet、styles、theme）保持字节不变；解析结果仍为 total 24、valid 24、warning 0、error 0、2 集、8 场、24 镜头。测试必须同时守住摘要、匿名内容边界及不存在驱动器路径、`file:` URI、UNC、个人/组织或应用元数据泄露。
- 集、场次、镜头、资产和资产制作分项的创建、修改、归档在锁定并读取项目后拒绝 `completed`、`archived`；镜头与资产 Excel preview 普通读取项目状态并拒绝，commit 再以 `FOR UPDATE` 锁定项目重检，统一返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。项目详情在 `completed` 时只允许合法的 `project.archive`，在 `archived` 时不返回写动作；镜头、资产和制作分项的 `allowedActions` 同步为空。该门禁目前覆盖项目自身、集、场次、镜头、资产、资产制作分项及两类 Excel 导入，不能推断成员、任务、版本、审核、文件或目录操作等其余全域写接口已经统一完成终态治理。
- 项目成员添加、修改和移除在锁定项目行后必须重新解析当前操作者的项目访问范围，并再次要求 `director`，防止操作者在等锁期间被移除或降级后仍完成写入；Controller 前置依赖不能替代该锁内复核。
- 2026-08-11 本批最新后端静态验证记录：`python -m ruff check module_shot_grid config middlewares tests/module_shot_grid` 通过，`python -m ruff format module_shot_grid config middlewares tests/module_shot_grid --check` 报告 177 files already formatted；包含资产契约、制作人选项、终态 CRUD/导入门禁和既有镜头链的 11 个定向测试文件为 90 passed；完整 `tests/module_shot_grid` 为 483 passed、2 skipped，两个跳过项均因当前环境不允许创建目录符号链接。镜头模板二进制契约、镜头/资产制作人选项路由和权限已由 OpenAPI/路由测试确认。
- 镜头管理/镜头 Excel 导入子集已在隔离 PostgreSQL、Redis DB 15、真实 FastAPI/平台账号、生产 Nginx 和 Chrome 下完成浏览器旅程：下载模板 11883 bytes 且摘要匹配，preview 为 24/24、0 警告行、0 错误行、2 集/8 场/24 镜头，选中 24 行后 commit HTTP 200，创建 2 集、8 场、24 镜头、24 任务、24 待匹配需求和 26 条目录操作。数据库终态与 UI 一致，Redis 预检键提交后为 0，浏览器控制台 0 error/0 warning，退出后详情深链回登录页。
- 资产管理/资产 Excel 导入子集也已完成相同隔离形态的真实浏览器旅程：preview 为 total 20、valid 19、warningRows 3、errorRows 1；一次提交 19 个可导入行后生成 11 个活动资产、19 个制作分项、19 个任务和 1 个显式隔离夹具自动匹配，并完成三视图、筛选、详情深链/刷新、资产/分项 CRUD 与业务归档、任务改派、7 条成功同事务审计、Redis Token 清理、控制台 0 error/0 warning及退出保护验证。该旅程只验证缩略图真实空态；资产模板下载因 `artifact_tool` 不可用未交付、未测试。项目仅使用逻辑 `storageStatus=ready` 夹具，Worker 关闭且 12 条目录 Outbox 均为 `pending`，没有验证真实缩略图文件或 UNC/NAS I/O，也不是完整系统 E2E；隔离容器、端口、数据库、Redis DB 15 和临时文件均已清理，原 9099 服务与基础 PostgreSQL/Redis 未改动。
- 资产创建时同时冻结 `asset_type/asset_name/asset_name_key/storage_dir_name/storage_path_key`；普通编辑只允许描述、排序和备注，重命名、改类型或目录迁移必须使用后续受控动作。制作分项无版本时可补充，已有版本后主数据冻结；资产图片版本提交前必须补齐制作分项。资产及制作分项响应中的 `allowedActions` 是后端根据平台权限、项目角色、项目状态、存储状态、资源生命周期、任务/版本及未提交版本发布状态计算的唯一动作依据，前端不得自行合成。制作分项缩略图只取该分项当前最新版本的 `thumbnail` 文件，不回退旧版本；父资产代表图按活动分项 `(sort_order, asset_item_id)` 顺序选择第一张可用的当前最新版本缩略图。正式版本事务统一按 `project → task/submission → version → auto_single review list → note` 顺序加锁，避免项目元数据、改派、提交和审核并发穿透。
- 任务列表提供项目范围与跨项目 `GET /shot-grid/tasks/mine`；首次分配的 `taskLockVersion` 必须为空，已有任务改派时必须携带当前 `taskLockVersion`，开始任务必须携带 `lockVersion`。任务存在任何非 `committed` 提交（包括 `failed`）时禁止改派，只允许重试原提交或走后续明确治理动作。
- 版本提交固定为“平台私有上传 → 创建临时 `businessType=shotgrid_version_submission` 文件引用 → 默认关闭的版本发布 Worker → NAS 摘要校验与无覆盖原子发布 → 正式版本/主文件引用/`auto_single` 审核单短事务”。`committed` 的 `versionId` 通过 `sg_version.submission_id` 反查，`sg_version_submission` 不重复保存 `version_id`。每次领取使用含 attempt 和随机值的唯一临时文件名；目标文件已存在时仅摘要和大小完全一致才按幂等成功处理，禁止覆盖。
- 当前文件类型门禁按真实字节校验 JPEG/PNG 与 MP4/MOV 容器签名/品牌，不包含 codec、视频轨、可解码性或转码探测；平台私有上传上限仍为 100 MiB。不得把签名嗅探描述成完整媒体有效性验证。
- 审核意见与回复是版本绑定的不可变历史，意见只通过解决动作改变状态。`approve/reject/defer` 均要求 `X-Idempotency-Key`，审核动作把规范化请求哈希和首次成功结果快照持久化；同键异命令必须冲突。`approve` 必须拒绝仍存在的 open mandatory 意见，`reject` 必须有原因或 open mandatory 意见，`defer` 只记录动作而不改变版本状态。当前只实现自动单版本审核单，`manual_batch` 仍是设计能力。
- 目录 Worker 默认关闭，仅在 PostgreSQL 且 `SHOT_GRID_STORAGE_WORKER_ENABLED=true` 时由 Application Leader 注册内部任务 `_shot_grid_storage_outbox`。每条操作执行前再次检查 Leader；数据库以 `FOR UPDATE SKIP LOCKED` 提供领取互斥，并以有期限租约和 owner + attempt fencing 拒绝旧持有者迟到回写。租约接管窗口不承诺旧、新 Worker 的物理 I/O 完全不重叠，因此当前执行器只能承载幂等目录创建和随机 `O_EXCL` 写探针。内部任务不得被数据库 Scheduler 同步当成普通 `sys_job` 删除或记录成高频任务日志。
- 版本发布 Worker 同样默认关闭，仅在 PostgreSQL、`SHOT_GRID_VERSION_WORKER_ENABLED=true` 且当前进程仍持有 Application Leader 时注册内部任务 `_shot_grid_version_publisher`。领取、NAS I/O、提交正式版本和结果回写保持短事务/事务外 I/O 边界，并使用租约心跳与 owner + attempt fencing；正常关机或失锁必须 drain 已登记版本发布 Job。自动化测试显式允许的本地临时目录不能冒充真实 UNC 验收。
- `initialize_project` 及项目级 `reconcile_directory` 的 `target_relative_path` 相对 NAS 存储根目录，值等于项目绑定的 `project_relative_path`；集、镜头、资产级 `ensure_*` 及 `reconcile_directory` 的目标相对项目根目录。不得把这两个作用域混为一套路径拼接规则。
- Worker 必须先提交领取短事务，再在线程中执行路径校验、幂等建目录和写探针，最后以短事务回写结果；软超时只做诊断并继续心跳续租，不能声称能够硬终止仍在运行的 SMB I/O。APScheduler 的 AsyncIOExecutor 不会等待已取消 Job，因此正常关机和 Leader 失锁必须显式 drain 已登记的 NAS Job，完成当前 I/O 与租约收尾后才能关闭数据库或重新竞争。当前单轮批次串行消费，尚未启用批内并发。
- 项目初始化成功才把项目存储改为 `ready`；项目级最终失败改为 `failed`。动态目录失败只记录安全错误，不得把已经就绪的项目根存储降级为初始化失败。人工重试不覆盖旧操作：项目和动态目录都新建 `reconcile_directory`，要求原因、幂等键和重新校验后的路径快照，并在同事务写操作日志。
- 自动化测试只允许通过显式 `allow_local_root=True` 使用临时本地目录；生产适配器默认只接受 UNC。源码、迁移、Mock/临时目录测试和服务启动均不能替代真实 Windows Worker 账号、NAS/AD/共享 ACL 及隔离 UNC 根目录 E2E。
- Excel 正式提交使用 `selectedRows[{sheetName,rowNumber}]`，不能只用跨 Sheet 不唯一的物理行号；预览明文 Token 和行明细只短期存 Redis，PostgreSQL `sg_import_batch.selection_hash/result_summary` 负责跨 Redis 生命周期的幂等重放。

## 8. Redis、缓存和日志

Redis 用于：

- JWT 会话；
- 验证码和账号锁定；
- 字典、参数、接口结果缓存；
- 接口限流；
- 在线用户；
- 日志 Stream；
- Scheduler 同步；
- Application/插件生命周期锁；
- 传输加密防重放。

修改 Redis Key 时：

- 优先复用 `RedisInitKeyConfig`、`LockConstant` 和现有命名空间。
- 明确 TTL、失效时机和多 Worker 行为。
- 删除或批量扫描 Key 时避免无界 `KEYS`。
- Redis 不可用时，认证、强制传输加密等安全路径不得静默降级。

修改 `@ApiCache` 或 `@ApiCacheEvict` 时，要检查实体变更影响的所有列表、详情、用户信息和动态路由缓存。

日志通过 Redis Stream 聚合写入数据库。不得同时在各 Worker 直接重复落相同业务日志。

## 9. 调度器

- 只有持有 Application Leader 锁的 Worker 持续运行 Scheduler。
- 锁续租失败后必须停止本地调度，不能继续以旧 Leader 身份执行。
- 任务增删改后保留 Redis Pub/Sub 同步机制。
- “立即执行一次”不能造成长期调度任务重复注册。
- 可调度函数必须位于允许模块内，并通过任务调用字符串校验。
- 定时任务异常必须记录任务日志，但不能导致 Scheduler 监听器崩溃。

涉及调度修改时至少验证：

- 单 Worker；
- 多 Worker；
- Leader 失锁；
- 数据库任务变更同步；
- 异步和同步任务；
- 执行日志。

## 10. 文件管理

文件域涉及数据库状态和物理文件两个事实来源。

- 公开文件只适合可公开访问的资源。
- 受保护附件必须通过文件鉴权接口下载。
- 正式业务附件用 `fileId` 建立业务引用。
- 业务数据和文件引用必须同事务提交。
- 文件处于引用或保留期时不得移入回收站或永久清理。
- 路径解析必须验证最终路径仍位于配置根目录。
- 私有文件鉴权保持默认拒绝，`deny` 优先于 `allow`。
- 对账修复必须记录原因、操作者和移动前后位置。
- 隔离区文件不能通过静态目录公开访问。
- 永久清理前必须锁定目标记录并再次校验状态。

`file_service.py`、`file_info_dao.py` 和 `file_util.py` 已经很大。新增能力优先拆分为边界清楚的服务，不继续堆积到单一类。

## 11. 插件系统

插件以 `plugin.yaml` 为唯一清单契约。修改插件时同步检查：

- manifest schema；
- 权限码和菜单树；
- Controller 自动扫描；
- 实体导入；
- MySQL/PostgreSQL 迁移；
- 种子；
- 定时任务；
- 前端路径；
- Python/npm 依赖；
- 启停和卸载行为。

规则：

- 应用启动只做依赖门禁，不自动安装依赖。
- 真实安装依赖必须通过 `ruoyi plugin install-deps`。
- 安装、升级、启用、停用、卸载和清理走现有生命周期 Service。
- 涉及破坏性操作时提供 plan/dry-run，并保留生命周期锁和审计。
- 不得通过直接修改 `sys_plugin` 状态冒充生命周期操作完成。
- 插件禁用后，其 HTTP 路由、任务和 Hook 都不应继续提供业务能力。

## 12. AI 插件

- Provider API Key 写库前加密，响应只返回掩码。
- 不在日志、异常、测试快照中出现解密后的 Key。
- 当前加密密钥由 JWT Secret 派生；更换 JWT Secret 前必须考虑历史 API Key 重加密。
- 自定义 `base_url` 必须保留 SSRF 防护，禁止环回、链路本地和未批准内网地址。
- 流式响应必须正确处理客户端断开、Provider 异常和取消。
- 未获用户明确授权时，不执行可能收费的真实模型调用。
- 单元测试中的 Mock Provider 成功不能当作真实 Provider 验收。

## 13. 传输加密

- 协议由后端中间件、工具类、公开配置接口和前端实现共同组成。
- 修改信封字段、AAD、算法或路径策略时必须同步前端。
- `required` 模式必须拒绝明文请求。
- nonce 防重放依赖 Redis；安全路径不得失败开放。
- 密钥轮换通过 `kid` 和 legacy key pairs 完成。
- 上传、下载、Swagger 等排除路径必须经过最小范围审查。
- 不得提交真实私钥；现有 `.env.*` 中的示例材料也不得复制到新文件或回复中。

## 14. CLI

CLI 与 Web 应用复用同一配置和业务服务。

- 命令输出支持 text/json 时，JSON 模式不得混入颜色、emoji 或普通日志。
- 危险命令必须遵循确认、`--yes`、`--allow-prod` 和 dry-run 约束。
- 生产环境禁止默认执行破坏性命令。
- 命令异常应映射为稳定退出码。
- 不要在 CLI Controller 中复制业务规则；优先复用 runtime/service。
- 修改命令后同步检查 completion、wizard 和 TUI 是否引用该命令契约。

## 15. 配置与密钥

- `.env.dev`、`.env.prod`、`.env.dockermy`、`.env.dockerpg` 当前被 Git 跟踪，这是已知风险，不应继续加入任何真实凭据。
- 不得在工具输出中打印环境文件原值。
- 新配置项需要：
  - Pydantic Settings 字段；
  - 所有环境示例；
  - 配置文档；
  - 必要的启动校验；
  - 安全默认值。
- 生产环境不应启用 reload、SQL echo、默认密码或示例密钥。
- JWT 签名密钥、AI 凭据加密密钥和传输 RSA 私钥应分离管理。

## 16. 后端验证

在后端目录执行：

```powershell
pip install -r requirements-pg.txt
python -m ruff check .
python -m ruff format . --check
python -m pytest -q
```

针对改动优先补充并运行对应目录测试，例如：

```powershell
python -m pytest tests/module_admin -q
python -m pytest tests/plugins -q
python -m pytest tests/cli -q
```

涉及数据库方言、Redis、Scheduler 或生命周期时，纯 Mock 单元测试不够，还应运行对应集成环境。

如果环境缺少 pytest、数据库、Redis 或插件依赖，必须明确报告未执行项，不得用 Ruff 通过代替测试通过。

## 17. 完成标准

后端改动完成前确认：

1. 路由、权限码和数据范围一致。
2. Service 事务能正确提交和回滚。
3. PostgreSQL 迁移、查询和索引已验证；若继续承诺 MySQL 兼容，也已检查对应路径。
4. Redis Key、TTL 和缓存失效完整。
5. 多 Worker 不产生重复调度或重复初始化。
6. 日志和响应不泄露敏感数据。
7. Ruff、目标测试及必要集成验证已真实执行。
8. 文档、SQL、插件清单或 CLI 帮助已同步。
