# 后端 Codex 协作指南

## 2026-11-16 交接合并后的现行规则

本节经用户确认，优先于本文后续历史记录中的冲突描述；历史测试记录仅说明当时环境，不是本次合并验收结果。

- 镜头与资产制作分项分配有效制作人后自动准备目录，不再以管理员确认开工、强制排期或完整制作信息作为额外门禁；目录成功后才能提交，提交和重试仍仅限当前有效制作人本人。
- 镜头待审核时允许继续提交新轮次；已完成镜头可由有权限的管理人发送正式反馈进入修改，普通评论不改变任务状态。资产同轮追加策略保持其独立契约。
- 保留主线独立的重新审核、审核周期、历史文件和撤销 Outbox。正式反馈遇到正在执行的最终交付时拒绝；撤销必须落入 Outbox，不得抢占 NAS I/O 或把失效终稿继续显示为有效。
- 新成果按版本目录隔离，FINAL 位于对应版本目录内，同时保留任务及审核周期子目录与 CURRENT 清单用于不可变历史和撤销；兼容历史路径。生产目录打开沿用签名 NAS 工具，交接包本地模拟工具不代表真实 NAS 验收。
- PostgreSQL 两侧迁移保留原编号，新增 `20261116_44` 汇合 `20261026_41` 与 `20261111_43`，不重写已执行历史。已在独立 PostgreSQL 实例验证两条升级路径及新库初始化，业务表结构与约束一致；没有升级现有业务库。此次使用合成测试数据，正式升级前仍须用生产备份的隔离恢复库验证。
- 每日多平台记录与成果提交独立，实际积分 0 有效；统计积分按平台分开，提交轮次和期间曾通过任务独立计算。权限、项目隔离、乐观锁、文件安全和事务约束继续有效。


## 2026-11-16 本地验证补充

- 任务详情的 `allowedActions` 必须允许有权限管理人对已完成镜头执行 `task.feedback`；关闭项目、归档目标、活动提交及非管理范围仍禁止。不能提前以任务已完成返回空动作，造成列表与反馈弹窗不一致。
- 兼容的资产人工开工接口不再要求排期，但不得借开工请求设置排期；有排期时保留首版基线与当前排期完整性检查。正常新任务仍走分配自动准备目录。
- FINAL 清单冲突重试使用现有版本路径校验器识别旧、新布局，并沿用任务/审核周期隔离目录与版本清单名。
- 真实 PostgreSQL 测试通过 `SHOT_GRID_TEST_ENV_FILE` 指向隔离连接配置；随机测试库的创建、断言与精确清理保护保持不变。完整记录见根目录 `docs/本地隔离验收记录-20261116.md`。

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
- 默认本地环境由根目录 `docker-compose.dev.yml` 启动后端、PostgreSQL 和 Redis；后端固定 Python 3.11.15、使用 `requirements-pg.lock.txt` 锁定 Python 依赖并内置 FFmpeg，前端仍在宿主机运行。本地 Linux 后端容器默认关闭 NAS 目录 Worker 和版本发布 Worker；公司生产 Linux 通过 `SHOT_GRID_NAS_SERVER_MOUNT_MAP` 只信任 `192.168.10.64`，把该服务器下任意用户新增的 `\\192.168.10.64\<共享>\<子目录>` 解析到容器动态挂载命名空间。宿主机 autofs 按共享名挂载 CIFS，Compose 以 `rslave` 传播子挂载；不得按业务根逐条修改环境变量或 Compose，不得允许其他 UNC 服务器，也不得给后端容器授予挂载权限。生产镜像中的 `app` 身份固定为 UID 100 / GID 101，CIFS 必须使用匹配的 `uid/gid + forceuid/forcegid`；真实验收必须用该非 root 身份在业务根目录覆盖创建、回读、删除和硬链接。解析成功不替代每次 I/O 前的 `cifs/smb3` 文件系统校验；挂载失效或普通宿主机目录必须失败关闭。详见 `docs/docker_dev_guide.md` 和根目录 `deploy/README.md`。
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

跨机器本地开发优先在仓库根目录使用：

```powershell
docker compose -f docker-compose.dev.yml up -d --build
```

此方式不依赖宿主机 Python 或 FFmpeg，但不覆盖真实 Windows UNC/NAS I/O 验收。

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

> 2026-08-31 后以 `20260831_26` 为当前 PostgreSQL head：20 在既有场内镜序、延迟目录、审核草稿和永久删除边界上新增“一个版本轮次包含多个候选文件”；21 新增审核通过后的最终版本 NAS 交付 Outbox；22 将单候选版本自动设为本轮最佳并回填历史数据；24 增加任务预期制作时间范围；25 增加不可变首版排期基线、只追加改期历史和独立排期权限；26 增加 NAS 根目录平台配置删除权限。`approve` 必须在审核事务创建唯一 `sg_final_delivery(pending)`，版本 Worker 在事务外把最佳候选无覆盖发布到同任务目录的 `FINAL/` 并写 `FINAL.json`。候选原文件保持不变。部署必须先执行 `upgrade 20260831_26` 再启动对应新代码。

- Shot Grid 领域模块位于 `module_shot_grid/`，包含 26 张 `sg_` 表 DO、项目访问依赖、范围导航、项目创建/存储状态/成员/范围查询、项目角色到固定平台角色的受管增量绑定、镜头与资产委派候选、v2 镜头/资产模板下载、两类 Excel 预检与正式提交、独立任务管理、版本提交/NAS 发布、`auto_single` 自动审核闭环，以及 NAS 目录 Outbox Worker、目录操作查询和人工重试接口。
- 首个增量迁移为 `20260810_01`，并已同步 `sql/ruoyi-fastapi-pg.sql`、菜单、权限和字典种子。
- `20260810_04` 是无版本历史库的采用/向前修复迁移：统一秒级时间精度和空字符串审计默认值，补强序场次、资产制作分项、主文件及集/场次编号约束；不得改写历史 01/02/03 代替修复。无 `alembic_version` 的历史库只能在备份和克隆核验后 stamp 01，再执行 upgrade head。04 必须在任何 ALTER 前预检冲突并整体失败，不能猜测修复业务数据；downgrade 不恢复从未被正式 revision 声明的旧弱漂移，秒以下精度只能从升级前备份恢复。
- 当前 head `20260831_26` 是 PostgreSQL-only 增量链：15 至 19 保持镜头/资产延迟目录、连续编号、审核草稿和项目永久删除语义；20 至 22 完成候选级提交、最终交付和单候选规范化；23 更名标准开工菜单；24 增加成对预期时间；25 增加排期基线、结构化改期历史、`shotgrid:task:schedule` 权限和排期查询索引；26 增加 `shotgrid:storageRoot:remove` 权限。
- PostgreSQL 部署必须先执行 `upgrade 20260831_26`，再启动对应新代码。固定角色配置完成后，由同时具有 `shotgrid:project:all` 和 `system:user:edit` 的管理员调用 `POST /shot-grid/platform-role-bindings/reconcile` 对账存量成员；对账失败必须整体回滚。
- 一次提交创建一个版本轮次和 `1..N` 个候选，候选不得拆成多个版本。只有全部候选完成无覆盖 NAS 发布，才允许在短事务中创建正式版本、候选、候选文件、一个自动审核单并把任务改为 `pending_review`；任一文件失败时不得暴露半个正式版本。
- 单候选新轮次由系统在正式版本事务内直接设置 `selected_candidate_id` 和主审核文件，`selected_by/selected_time` 保持为空且不写审核人选择历史；多候选新轮次初始不选择，审核人显式选择后才能记录问题或提交结论。问题草稿、正式问题、历史问题确认和审核动作都必须校验并保存同一候选；存在草稿时禁止切换候选，禁止静默迁移批注。
- 镜头与资产列表、详情、卡片和故事板的最新版本只读投影不得把“尚未选择最佳候选”误判为缺少审核媒体或无缩略图。存在 `selected_candidate_id` 时展示该候选；待审核且尚未选择时按 `sort_order/candidate_no/candidate_id` 稳定展示候选 01，并让缩略图、代理媒体和业务文件名使用同一展示候选。
- 2026-08-14 起，审核正式基线为“来源版本修改问题 → 制作人随修订版本逐条处理说明 → 审核人在新版本逐条确认 `resolved/still_present` → 未关闭问题继续跨版本”。问题主记录永久绑定来源版本，不复制或迁移；所有 open 问题都阻止通过，不再按 `is_mandatory` 区分普通/必须修改。接口必须通过最近一次 `still_present` 确认推导 `pendingVersionId/pendingVersionNumber`：待处理工作归属最近被退回的版本，而来源版本只保留“已处理但未通过”的历史证据。
- 新模型使用 `resolved_in_version_id`、版本提交逐条问题处理说明和逐版本审核确认记录。制作人的处理说明通过版本提交一对一关联正式版本；审核确认只能由 `approve/reject` 审核事务创建并改变问题状态。选择 `resolved` 时不填写补充说明，选择 `still_present` 时必须说明未解决原因。旧 `sg_note_reply` 不再承担业务闭环。
- 当前版本的新问题先保存为 `sg_review_issue_draft`，草稿仅通过审核上下文返回给授权审核人，并以 `lock_version` 控制编辑和删除并发；任务问题查询、版本正式问题查询和生产履历不得读取草稿。`reject` 在锁定审核图后把草稿批量写为 `sg_note`、删除草稿并完成版本/任务/审核单状态转换，全部处于同一事务；发布后继续遵循正式问题不可变规则。
- Shot Grid 只承诺 PostgreSQL；非 PostgreSQL 环境不得把 `sg_` 模型加入平台元数据，Shot Grid revision 的升级和降级必须保持 no-op。
- 已有平台 PostgreSQL 库通过 Alembic 执行增量迁移；新库通过同步后的 PostgreSQL 初始化 SQL 建立全量结构并写入 Alembic head。当前仍不存在完整平台 Alembic baseline，不得声称首个 Shot Grid revision 能从真正空库独立建立 RuoYi 平台。
- 项目创建/编辑/归档、成员变更、集/场次/镜头/资产普通管理、任务分配/改派/开始、Excel 正式提交、版本正式提交、修改问题创建、版本逐条处理说明、审核逐条确认、审核动作和目录人工重试必须由 Service 在规定事务边界写领域数据、必要的 Outbox/文件引用与 `SysOperLog`；不得使用会异步入 Redis 的平台 `@Log` 冒充同事务审计。旧审核意见/回复/解决事务属于迁移前实现事实，不再作为新功能契约。项目、集、场次、镜头、资产和制作分项已实现业务归档而非物理删除；独立业务前端的项目、镜头、资产、跨项目“我的任务”工作台、任务详情/编辑/等待开工、版本提交恢复、版本历史/详情和鉴权下载已接入真实接口，不回退 Mock。旧 v1 镜头/资产导入旅程包含“导入时预分配并创建任务”的已废弃行为，不能验收 v2 新流程；任务/版本旅程只使用显式 `allow_local_root=True` 的 TEMP 适配器验证发布算法和前后端编排，不是正式 UNC/SMB/NAS 服务账号验收。任何子集旅程均不等于完整系统 E2E 或生产就绪。
- 项目管理页面使用四项查询/预览类接口：`GET /shot-grid/storage-roots/options` 只返回 `enabled + healthy` 根目录的名称、编码、规范化 UNC 根路径和健康摘要，供已授权项目创建人直接确认保存位置；不得返回 `credentialRef`、内部路径键或错误堆栈。`POST /shot-grid/storage-roots/{storageRootId}/project-path-preview` 只执行规范化、路径拼接和占用检查，不写库、不创建目录；项目目录名称由项目名称唯一生成，前端在根目录或项目名称变化后自动防抖调用并展示结果，不要求用户额外点击预览按钮。`GET /shot-grid/member-candidates` 用于创建项目，要求 `shotgrid:project:add`；`GET /shot-grid/projects/{projectId}/member-candidates` 用于成员维护，要求 `shotgrid:member:add` 和项目管理人角色。两类候选查询均应用 `DataScopeDependency(SysUser)`，并支持可选的精确 `deptId` 过滤；创建项目页面必须传当前登录账号部门，只允许选择同部门账号。候选接口只分页返回有效平台账号的用户、昵称、头像和部门摘要，不返回联系方式、认证字段或密码。项目创建和添加/恢复成员事务也必须使用同一用户数据范围重新校验账号，路径预览不能替代创建事务内对根目录和路径冲突的重新校验。
- 平台管理端通过 `GET/POST/PUT/DELETE /shot-grid/admin/storage-roots` 和 `POST /shot-grid/admin/storage-roots/{storageRootId}/probe` 维护根目录白名单。删除只允许具备 `shotgrid:storageRoot:remove` 的管理员删除已停用、未被任何 `sg_project_storage` 引用且锁版本一致的平台配置；必须在根目录行锁内复核并逻辑删除、同事务审计，绝不删除或改写实际 NAS 目录和文件。探测必须由后端服务账号在事务外对规范化 UNC 根目录执行随机临时文件的独占创建、回读和删除，再以短事务持久化健康状态与同事务操作日志；不得把浏览器所在账号能打开共享目录当成后端可写证据。新增、路径变更或停用后重新启用时状态重置为 `unknown`，只有 `enabled + healthy` 才能进入创建项目选项。
- 镜头页通过 `GET /shot-grid/projects/{projectId}/shot-assignee-options` 分页查询可分配制作人；接口要求 `shotgrid:shot:list` 与项目访问，只返回 `projectRole=creator` 的活动项目成员和有效未删除平台账号，`keyword` 只匹配账号与昵称。兼容响应字段 `producerCode` 由 `sys_user.nick_name` 派生，不能再读取项目成员表旧缩写。该选项只服务独立委派/改派，镜头创建、编辑和导入不得接收制作人；分配写事务必须重新校验，不能把选项响应当成写入授权。
- 资产页通过 `GET /shot-grid/projects/{projectId}/asset-assignee-options` 分页查询可分配制作人；接口要求 `shotgrid:asset:list` 与项目访问，分页、关键字和安全投影规则与镜头制作人选项一致。该选项只服务制作分项的独立委派/改派，资产、制作分项创建/编辑和导入不得接收制作人；首次分配和改派仍必须在写事务中重新校验项目状态、成员状态和平台用户昵称。
- 资产列表批量分配以父资产为前端选择单位，但后端写入目标必须是活动制作分项任务；`POST /shot-grid/projects/{projectId}/asset-items/batch-assign` 接收最多 200 个 `assetItemId/taskLockVersion` 并整批回滚。资产单个或批量删除只允许无镜头引用、无版本且任务均未开始的资产，事务内软删除未开始任务、归档并软删除活动制作分项及父资产；不得绕过任务状态、引用和乐观锁门禁。
- 资产描述在任一未删除分项任务离开 `not_started` 后冻结，包含 `preparing/in_progress/pending_review/revision/completed` 及已归档分项；只修改父资产排序和内部备注仍允许，原权限、项目/NAS/生命周期与乐观锁门禁不变。资产详情通过派生字段 `descriptionLocked` 表达字段只读，`asset.edit` 仍服务元数据编辑。普通 PUT 保持完整快照语义，锁定后必须带回原资产描述；后端在与开工共用的项目协调锁内复核，改变或清空说明返回 HTTP 409 / `SG_ASSET_DESCRIPTION_LOCKED` 并整笔回滚。仅文本规范化一致的历史空白不视为改动，锁定后保留原始存储文本；不因分项归档而解锁，不写新表字段、不改任务状态。
- 资产 Excel 的“描述/资产描述”统一映射 `assetDescription → sg_asset.description`；类型、名称、资产描述允许单列纵向合并并取左上角值。可选“分项补充要求/制作分项描述”逐行映射 `itemDescription → sg_asset_item.description`，不允许合并；未提供该列时为空，禁止复制父描述到分项。备注属于分项。同一资产的非空描述冲突必须报错；此调整不迁移历史数据。任务查询须读取父资产描述并与分项补充要求组合到 `targetDescription`，保证制作人员能看到完整内容。
- 独立制作分项删除走 `POST /shot-grid/projects/{projectId}/asset-items/{assetItemId}/delete`，复用资产删除权限 `shotgrid:asset:archive`，并在 `project → asset → item → task/submission` 锁序中复核管理范围、项目/NAS/生命周期、分项锁版本、任务未开始、无版本和非 `committed` 提交。只逻辑删除目标分项及其未开始任务，保留父资产、其他分项和 NAS 文件，并在同一事务写删除原因及审计。新动作 `assetItem.delete` 的投影必须与写入边界一致；已有制作历史仍只能走合法归档，不得删除。
- 2026-09-08 镜头列表新增 `shotNoStart/shotNoEnd` 数值闭区间筛选：位于场次后，两端均可空，单端表示无另一侧边界；填写值须为 PostgreSQL INTEGER 范围内的正整数，起始不能大于结束。前端使用 ElForm/ElFormItem 与 ElInput 校验、统一查询和重置，后端 VO 复核并在 DAO 用参数化 SQLAlchemy 条件 `shot_no >= start` / `shot_no <= end` 过滤；原项目范围、权限、分页及编号显示不变。区间查询禁止整场自动加载与拖拽排序，表格/卡片/故事板及排期查询均传递范围。无需表结构迁移。
- 2026-09-08 新建镜头改为手填 `shotNo`：不从 0001 起号、不要求连续或递增；项目协调锁内按 `scene_id + shot_no` 查询全部未删除记录查重（含归档记录），数据库唯一索引兜底并发冲突，返回 `SG_SHOT_NO_CONFLICT`。创建只插入新镜头与关系/审计，不重排其他镜头、不创建任务或目录。创建必填 `shotNo`，不接受 `sequencePosition/sortOrder`；为保持现有 INTEGER 排序键 `shotNo * 10`，手填编号范围为 1..214748364。编辑页编号只读。列表默认每页 10 条。
- 2026-09-08 导入补充规则：仅场次和镜头号必填；时长留空按 0 毫秒、制作内容留空按空字符串保存，其他业务字段可空，并允许在编辑镜头中分次补充。已填写值继续校验格式与长度；景别、机位、镜头运动、焦段各最多 500 字符，镜头备注最多 2000 字符，场景资产名称仍最多 200 字符。PostgreSQL 新 head 为 `20260908_27`（接续 `20260831_26`），已有库必须先备份并执行迁移再使用放宽后的长度；只扩容 `sg_shot` 五列，不改变资产名称或公共审计备注上限。降级锁表后预检所有镜头（含历史记录），存在超旧上限文本则整体拒绝，禁止截断。
- 2026-09-08 起，Excel 镜头导入保留原始编号：不要求从 `0001` 开始，不要求连续或按行递增，允许跳号、乱序及向已有场次补号；仍校验正整数格式、至少四位数字显示和同场次编号唯一性。正式提交不得重新编号现有或导入镜头。此项为导入规则变更，现有拖拽和删除的场内重排机制尚未解耦，不得把非连续导入数据描述为非法数据或声称全链路已支持自由编号；后续调整需单独核对冻结目录与任务安全边界。
- 2026-08-28 起，镜头号统一为至少四位纯数字：第 1 镜 `0001`、第 12 镜 `0012`，超过四位不截断。数据库 `shot_no`、`sequencePosition` 和稳定 `shot_id` 不变；新建目录冻结为 `{sceneNo:03d}_{shotNo:04d}`，新业务文件名使用四位数字镜头段。Excel 当前模板 `shot-v3` 的编号单元格使用文本格式，导入兼容正整数数值/纯数字文本并补齐显示，不再接受 S 前缀。此次不回填旧记录、不重命名已有目录/文件、不执行旧数据迁移；已冻结的路径仍按原快照读取。版本发布路径校验必须同时识别新数字目录（如 `000_0001`）与既有 S 前缀冻结目录（如 `001_S001`）；不得因编号展示变化拒绝合法发布，也不得放宽相对路径层级、临时文件归属、路径越界或禁止覆盖校验。
- 2026-08-28 起，新建镜头与资产候选的业务文件名不再追加 Unix 毫秒时间戳，统一以 `_V{版本号至少3位}_{候选号至少2位}.{扩展名}` 结尾。`generated_at_ms` 继续作为批次生成时间元数据保存，数据库字段不删除、不回填；已有提交（含失败重试）、正式版本及 NAS 文件名/路径保持冻结，不按新规则重算。版本号仍在任务锁内分配，重放返回原提交；NAS 同名同摘要可复用，不同内容必须拒绝覆盖。
- `GET /shot-grid/imports/shots/template` 要求 `shotgrid:shot:import`，直接返回鉴权后的 XLSX 二进制、文件名为 `镜头导入模板-shot-v3.xlsx` 的 `Content-Disposition` 和 `X-Shot-Grid-Template-Version: shot-v3`，不套 JSON envelope。应用层传输加密只精确放行该 GET，不得把同前缀预检或提交 JSON 路由降级为明文。部署资源缺失或摘要不符稳定返回 HTTP 503 / `SG_IMPORT_TEMPLATE_UNAVAILABLE`。
- 镜头打包模板 `module_shot_grid/resources/templates/shot-v3.xlsx` 的冻结 SHA-256 为 `23FF46F60BD4E52A7C3B9350F89882BB18963C92823AC40AFE601AC1553204F8`，主数据区为 A:O 15 列且不含制作人。资产打包模板 `module_shot_grid/resources/templates/asset-v2.xlsx` 的冻结 SHA-256 为 `B551AC1D1D5EDC20A025B0ED90157412E1365006108816F08CB2C59AE4301696`，主数据区为 A:F 且不含制作人。旧镜头 v1/v2、资产 v1 文件只保留为历史资源，不再由模板服务下载。测试必须守住版本、摘要、表头边界以及不存在驱动器路径、`file:` URI、UNC、个人/组织或应用元数据泄露。
- 集、场次、镜头、资产和资产制作分项的创建、修改、归档在锁定并读取项目后拒绝 `completed`、`archived`；镜头与资产 Excel preview 普通读取项目状态并拒绝，commit 再以 `FOR UPDATE` 锁定项目重检，统一返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。项目详情在 `completed` 时只允许合法的 `project.archive`，在 `archived` 时不返回写动作；镜头、资产和制作分项的 `allowedActions` 同步为空。该门禁目前覆盖项目自身、集、场次、镜头、资产、资产制作分项及两类 Excel 导入，不能推断成员、任务、版本、审核、文件或目录操作等其余全域写接口已经统一完成终态治理。
- 项目成员添加、修改和移除在锁定项目行后必须重新解析当前操作者的项目访问范围，并再次要求 `director`，防止操作者在等锁期间被移除或降级后仍完成写入；Controller 前置依赖不能替代该锁内复核。
- 2026-08-26 多候选增量最新验证记录：后端 Ruff check 和本次改动 Python 文件 format check 通过，完整 `tests/module_shot_grid` 为 608 passed、2 skipped；前端版本提交/审核直接相关 3 个测试文件为 40 passed，改动范围 ESLint 和 1930 modules 生产构建通过。fresh PostgreSQL `20260826_20`、隔离 Redis 和浏览器已完成 `V001` 三候选选择退回、`V002` 两候选选择通过闭环；该旅程使用测试专用 UNC 到本机临时目录映射，不替代正式 NAS 服务账号、SMB/CIFS、共享 ACL、FFmpeg 或完整系统 E2E。
- 2026-08-11 的镜头和资产导入浏览器旅程使用已废弃的 v1 制作人预分配契约，并在导入时分别创建了 24 个和 19 个任务；它们只保留为历史实现证据，不能验收 v2“模板无制作人、导入后全部未分配、任务创建数为 0”的规则。v2 模板下载、预检、提交、手工创建和后续独立委派链必须重新执行定向验证；旧旅程中真实 UNC/NAS、缩略图和完整 E2E 未验证的边界继续有效。
- 任务工作台/版本上传子集使用 fresh PostgreSQL head `20260811_06`（22 张 `sg_` 表）、Redis DB 15、真实平台登录、生产 Nginx 和 Chrome：`/workbench` 返回 21 条任务并验证服务端分页 20+1 与关键字命中 1 条；`taskId=900001` 开始接口 HTTP 200，`lockVersion` 由 0 变 1；选择 5663 B 的 `logo.png` 后严格依次得到 preflight 200、private upload 200、create 202，pending 页面 reload 后由 current 200 恢复。随后以显式 `allow_local_root=True` 的本地 TEMP 适配器推进 `published → committed` 两阶段且 attempt=1，形成 V001 `pending_review`、任务 `lockVersion=2`、1 个 `auto_single` 审核单和 1 条正式文件引用；受保护版本详情与下载均为 200，下载 5663 B 且 SHA-256 与源文件一致。浏览器控制台 0 error/0 warning；localStorage/sessionStorage 不含认证 Token、幂等键、`fileId`、修改说明或 AI 参数，登录期间认证 Token 只存在 `Admin-Token` Cookie，logout 200 后 Cookie 清除且任务/版本深链守卫生效；验收目标已精确清理。该结论仅关闭隔离任务/版本子集门禁：TEMP 适配器是算法与编排验证，夹具目录补齐只是逻辑预览，未验证真实 UNC/SMB/NAS 服务账号、审核前端、`manual_batch`、codec、媒体轨、可解码性或转码，也不是完整系统 E2E。
- 资产创建时同时冻结 `asset_type/asset_name/asset_name_key/storage_dir_name/storage_path_key`；普通编辑只允许描述、排序和备注，重命名、改类型或目录迁移必须使用后续受控动作。制作分项仅在未分配或唯一任务仍为 `not_started` 且尚无版本时可补充；管理人员确认开工后主数据立即冻结，不等待首个版本提交。资产图片版本提交前必须补齐制作分项。资产及制作分项响应中的 `allowedActions` 是后端根据平台权限、项目角色、项目状态、存储状态、资源生命周期、任务/版本及未提交版本发布状态计算的唯一动作依据，前端不得自行合成。制作分项缩略图只取该分项当前最新版本的 `thumbnail` 文件，不回退旧版本；父资产代表图按活动分项 `(sort_order, asset_item_id)` 顺序选择第一张可用的当前最新版本缩略图。旧正式版本事务当前按 `project → task/submission → version → auto_single review list → note` 顺序加锁；新审核闭环必须扩展为问题处理说明和确认记录的稳定锁序，避免项目元数据、改派、提交和审核并发穿透。
- 任务列表提供项目范围与跨项目 `GET /shot-grid/tasks/mine`；独立业务前端的 `/workbench` 使用该跨项目真实数据源，`/tasks/:taskId` 使用任务详情和编辑真实接口，等待管理端开工。镜头任务详情额外返回详情专用 `shotProduction`，投影当前镜头的时长、制作内容、景别、机位、镜头运动、焦段、台词/对白、音效、色调参考和备注；任务列表仍只返回目标摘要，不把完整制作信息扩入列表响应。动作必须同时满足平台权限与后端 `allowedActions`。任务编辑继续按项目管理权限复核。镜头任务仅允许具备 `shotgrid:task:start` 的项目 `director` 或 `has_all_scope` 管理人员确认开工；制作人只能等待，不能自行开始。管理人线下确认依赖资产齐备后提交 `{ lockVersion, shotLockVersion, assetsConfirmed: true }`，服务端在锁内复核管理范围、任务与镜头版本、状态及当前负责人仍为有效 `creator`，并在同一事务审计人工确认。资产任务同样由具备上述权限和范围的管理人员按制作分项确认，以 `{ lockVersion, assetLockVersion, assetItemLockVersion, startConfirmed: true }` 提交；锁内复核任务、父资产和分项三份版本、分项内容及有效负责人，同事务审计。只递增任务版本，不修改父资产和分项元数据版本；其他分项不随本分项或共享目录开工；版本 preflight/create 和失败提交重试仍只允许当前受派的活动制作人员本人，管理人不得代提交或代重试。首次分配的 `taskLockVersion` 必须为空，已有任务改派时必须携带当前 `taskLockVersion`，开始任务必须携带 `lockVersion`。任务存在任何非 `committed` 提交（包括 `failed`）时禁止改派，只允许当前活动负责人重试原提交或走后续明确治理动作。
- 资产列表与详情返回 `itemStatusCounts`，固定包含 `unassigned/not_started/preparing/in_progress/reviewing/revision/completed` 七个非负整数键，仅统计活动且未删除分项。父级状态按 `revision → reviewing → in_progress → preparing → unassigned → not_started` 聚合；至少有一个活动分项且全部完成才为 `completed`，无活动分项为 `unassigned`。父级 `task.start` 仅表示可进入分项选择，至少存在一个实际可开工分项才返回；真正 start 必须对选中分项任务提交，不能整资产开工。
- 目录成功回写必须先锁项目，再锁目录操作及任务/存储行，与开工事务使用同一项目协调锁；等待后仍复核 owner + attempt fencing。该锁仅在 NAS I/O 结束后的短事务持有，保证共享目录完成与新分项开工交错时不会遗漏已开工分项。
- 镜头和资产制作分项统一“未开工可改派，开工后禁止普通改派”：无任务时可首次分配；已有任务只有 `not_started` 且不存在非 `committed` 提交（包括 `failed`）时可改派。`preparing/in_progress/pending_review/revision/completed` 均不返回 `task.assign`，管理人员亦不可绕过。单个和批量分配必须在既有项目、目标和任务锁内核对状态与乐观锁，已开工返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`；批量任一目标不满足条件整批回滚，不重置任务或修改历史。任务、镜头、分项和父资产列表/详情投影须一致，父资产只有全部活动分项均可分配才返回该动作；保留平台权限、管理范围、项目状态、NAS 就绪、生命周期和成员有效性门禁。
- 版本提交当前实现固定为“本地候选文件校验 → `POST /shot-grid/tasks/{taskId}/version-submissions/preflight` → 逐候选 `POST /common/files/upload` 平台私有上传 → `POST /shot-grid/tasks/{taskId}/version-submissions` 创建提交并返回 HTTP 202”。preflight 接收有序 `candidates[]`（`clientFileKey/fileName/fileSize/sortOrder/candidateNote`），create 按同一顺序接收对应 `clientFileKey/fileId/sortOrder/candidateNote`；两者同时携带 `issueResponses`，首版为空，修订版精确覆盖锁内重查的全部 open 问题，并纳入幂等命令哈希。候选顺序、文件或问题集合变化必须冲突，不能静默接受过期命令。preflight、create 与失败提交 retry 都必须校验当前用户就是任务当前委派的活动 `creator` 本人，不接受 `director`、管理员或全项目范围代提交。其余 NAS 无覆盖发布、逐候选文件引用切换、`committed` 反查版本和逐候选唯一临时文件规则保持不变。
- `GET /shot-grid/tasks/{taskId}/version-submissions/current` 用于刷新后的未解决提交恢复；状态查询只把 `committed` 视为成功，`failed` 保留原提交行并通过 retry 接口重置原行，不能另建一条绕过占用约束。前端自动轮询每轮最多 30 次，连续 3 次查询错误后暂停，使用有上限的指数退避，并在 401/403/404 时停止；到达边界后只允许人工刷新或合法重试。版本历史、版本详情和受保护 Range 下载分别使用独立的 `shotgrid:version:list`、`shotgrid:version:query`、`shotgrid:file:download` 权限，失败重试使用 `shotgrid:version:retry`；`/versions/:versionId` 深链归属 `reviews` 路由域。
- 版本创建的稳定幂等键与命令指纹只保存在当前前端内存上下文；创建响应不明时，同一文件、同一命令重放必须复用已上传 `fileId` 和幂等键，并跳过重复 preflight/upload。任务、操作和文件切换使用 generation/abort 防止同 ID 往返的 ABA 迟到响应继续提交；上传或下载返回 Blob 时，统一请求层只在 JSON Content-Type 且响应不超过 64 KiB 时解析错误体，并保留 `httpStatus/code/errorKey/details`，不得把二进制正文误解码或把 401/403/404/409/413/416/5xx 抹平成同一提示。
- 当前文件类型门禁按真实字节校验 JPEG/PNG 与 MP4/MOV 容器签名/品牌，不包含 codec、视频轨、可解码性或转码探测；平台私有上传上限仍为 100 MiB。不得把签名嗅探描述成完整媒体有效性验证。
- 当前代码中的审核意见、回复和独立解决动作是旧模型事实。新正式契约中，问题永久绑定来源版本；`approve/reject` 请求必须精确携带全部带入问题的 `resolved/still_present` 确认并在同一事务落库，`approve` 要求全部确认 resolved 且任务无 open 问题，`reject` 要求至少一条 still_present 或当前版本新问题，`defer` 只记录动作。三种动作仍要求 `X-Idempotency-Key`、规范命令哈希和持久结果快照；问题确认集合属于命令哈希，制作人和普通 CRUD 均不能直接解决问题。
- 目录 Worker 默认关闭，仅在 PostgreSQL 且 `SHOT_GRID_STORAGE_WORKER_ENABLED=true` 时由 Application Leader 注册内部任务 `_shot_grid_storage_outbox`。每条操作执行前再次检查 Leader；数据库以 `FOR UPDATE SKIP LOCKED` 提供领取互斥，并以有期限租约和 owner + attempt fencing 拒绝旧持有者迟到回写。租约接管窗口不承诺旧、新 Worker 的物理 I/O 完全不重叠，因此当前执行器只能承载幂等目录创建和随机 `O_EXCL` 写探针。内部任务不得被数据库 Scheduler 同步当成普通 `sys_job` 删除或记录成高频任务日志。
- 版本发布 Worker 同样默认关闭，仅在 PostgreSQL、`SHOT_GRID_VERSION_WORKER_ENABLED=true` 且当前进程仍持有 Application Leader 时注册内部任务 `_shot_grid_version_publisher`。领取、NAS I/O、提交正式版本和结果回写保持短事务/事务外 I/O 边界，并使用租约心跳与 owner + attempt fencing；正常关机或失锁必须 drain 已登记版本发布 Job。自动化测试显式允许的本地临时目录不能冒充真实 UNC 验收。
- 同一内部版本 Worker 也消费 `sg_final_delivery`：只允许把审核事务冻结的最佳候选发布到源文件同级 `FINAL/`，优先硬链接、失败时校验复制，同时写不可覆盖的 `FINAL.json`。文件与清单都成功后才回写 `published`；相同内容可幂等重用，不同内容、不同清单或源摘要变化必须失败关闭。审核请求内禁止执行 NAS I/O。
- `initialize_project` 及项目级 `reconcile_directory` 的 `target_relative_path` 相对 NAS 存储根目录，值等于项目绑定的 `project_relative_path`；集、镜头、资产级 `ensure_*` 及 `reconcile_directory` 的目标相对项目根目录。不得把这两个作用域混为一套路径拼接规则。
- Worker 必须先提交领取短事务，再在线程中执行路径校验、幂等建目录和写探针，最后以短事务回写结果；软超时只做诊断并继续心跳续租，不能声称能够硬终止仍在运行的 SMB I/O。APScheduler 的 AsyncIOExecutor 不会等待已取消 Job，因此正常关机和 Leader 失锁必须显式 drain 已登记的 NAS Job，完成当前 I/O 与租约收尾后才能关闭数据库或重新竞争。当前单轮批次串行消费，尚未启用批内并发。
- 项目初始化成功才把项目存储改为 `ready`；项目级最终失败改为 `failed`。动态目录失败只记录安全错误，不得把已经就绪的项目根存储降级为初始化失败。人工重试不覆盖旧操作：项目和动态目录都新建 `reconcile_directory`，要求原因、幂等键和重新校验后的路径快照，并在同事务写操作日志。
- 自动化测试只允许通过显式 `allow_local_root=True` 使用临时本地目录。生产适配器只接受 Windows 直接 UNC、`SHOT_GRID_NAS_UNC_MOUNT_MAP` 的精确根映射，或 `SHOT_GRID_NAS_SERVER_MOUNT_MAP` 明确允许服务器后的动态共享映射；Linux 每次真实 I/O 前都必须验证解析到的共享挂载根为 `cifs/smb3`，不得把动态命名空间本身或任意本地绝对路径当成 NAS。配置了服务器白名单后，未命中的 UNC 服务器在 Windows 和 Linux 均失败关闭。源码、迁移、Mock/临时目录测试和服务启动均不能替代正式服务账号、NAS/AD/共享 ACL 及隔离 UNC 根目录 E2E。
- 资产删除（单个及批量）必须在项目、资产和分项/任务锁内检查全部未删除分项，包括已归档历史；任一任务不是 `not_started`（含 `preparing`），或任一分项已有版本、任务存在非 `committed` 提交，均禁止删除父资产。列表与详情的 `asset.archive` 使用相同阻断条件，不能通过先归档分项绕过开工保护。仍须无镜头引用并满足原权限与状态约束；全部未开工时只软删除活动分项及其未开始任务和父资产，不改写已归档分项历史，不删除 NAS 文件。分项删除同样禁止已开工任务。
- 镜头、资产及制作分项的手工创建和 Excel 导入只创建生产对象与关系，聚合状态必须为 `unassigned`，不得创建对象目录 Outbox、接收制作人或创建任务；集目录 Outbox 仍按集契约处理。资产创建时只冻结稳定目录身份，第一次实际目录操作由管理人员确认某个资产制作分项开工触发。Excel 正式提交仅使用 `selectedRows[{sheetName,rowNumber}]`，不能只用跨 Sheet 不唯一的物理行号，也不得包含 `assigneeUserId`；预览明文 Token 和行明细只短期存 Redis，PostgreSQL `sg_import_batch.selection_hash/result_summary` 负责跨 Redis 生命周期的幂等重放。
- 第一次委派必须走独立任务分配 Service，创建 `assignee_user_id` 非空、`task_status='not_started'` 的唯一 `shot_video` 或 `asset_image` 任务；后续改派只更新同一任务。镜头与资产制作分项的 `not_started` 均展示为“待开工”，由管理人员逐项确认。新目录尚未就绪时，开工进入 `preparing`，沿用现有 NAS 目录 Outbox；目录成功后才进入 `in_progress`。已有成功目录可直接进入 `in_progress`；未开工和目录准备中均不得提交版本。正式提交不可变版本后进入 `pending_review`，审核通过时版本进入 `final` 且任务进入 `completed`，退回时任务进入 `revision` 并通过新版本循环。
- 生产履历顶部固定投影“创建/导入、委派、制作、提交版本、审核、完成”六阶段，下方版本循环返回审核动作、来源问题、处理说明和确认结果。阶段投影不是审计事件；`sg_task.create_time` 只能证明任务记录建立，不能作为确认的委派、改派或开始事件，无法由正式记录证明的历史必须返回 `evidenceLevel='inferred'` 或缺省。

### 7.5 任务预期制作时间

- `20260828_24` 引入 `sg_task.expected_start_time/expected_end_time`；当前 PostgreSQL head 为 `20260831_26`。两字段为可空、成对、秒级业务本地时间，沿用 `SHOT_GRID_DATETIME`；DB 约束结束严格晚于开始，不能使用随时间变动的 CHECK。
- 管理人员开工命令可携带 `priority/expectedStartTime/expectedEndTime`。任务尚无计划时，前端开工表单要求完整范围；带时区、半个范围、反序/相等时间拒绝，取得项目和任务锁后拒绝新建的过去开始时间（422 / `SG_TASK_EXPECTED_TIME_INVALID`）。任务已有计划时，开工命令省略时间并保留原值，不因计划开始已过去拒绝；已有计划只通过排期 API 修改。首次时间/基线与原状态、版本、目录 Outbox、审计同事务保存，失败整体回滚。`due_date` 同步为预期结束的日期，仅兼容既有筛选/排序。
- 预期时间仅供制作人参考。任务是否开工/完成由原有管理员确认、目录、提交和审核链决定；禁止定时到期完成，禁止把预期时间加入 preflight/create/retry 或普通改派门禁。制作人在合法状态下可提前或逾期提交。
- 任务列表/详情、镜头列表顶层、镜头任务摘要和资产分项摘要返回两项预期时间；镜头列表直接复用原查询已有的任务时间投影，不额外逐行读取详情。正常/临近结束/延期是前端展示提醒，不新增任务状态或调度任务。旧日期保留、迁移前备份，降级遇到已填写时间时必须拒绝，避免静默丢失安排。
- 资产列表及详情返回 `itemTimeGroups`，按活动且未删除分项的 `taskStatus/expectedEndTime` 分组并提供正整数 `itemCount`；未分配或任务已删除的分项以空任务状态和空结束时间计入。列表复用当前页已有的批量分项引用查询，详情复用已加载分项，不新增逐资产查询。只投影提醒计算输入，不保存正常/预警/延期状态，也不把旧 `dueDate` 当作精确结束时间。

### 7.6 任务排期、基线与改期历史

- 2026-09-10 开工规则：镜头任务和资产制作分项任务在开工时建立首次排期，不因同一负责人其他任务的排期重叠而拒绝，也不要求先到排期页处理。仍须校验开工权限、项目范围、状态、乐观锁、负责人、时间范围及人工确认，并在同一事务保存首次排期基线、历史、目录 Outbox 和审计。排期 API 的冲突提示与二次确认规则保持不变。

- `20260831_25` 已实现统一项目排期：`sg_task.expected_start_time/expected_end_time` 继续作为当前计划，首次完整排期同事务冻结不可变基线，后续改期只更新当前计划；已有完整计划在迁移中只复制为基线，不伪造历史操作人、原因或时间。无计划任务保持为空，未委派对象不得创建虚拟任务。
- 新增只追加的结构化任务排期变更表，并继续写同事务 `SysOperLog`。当前计划、兼容 `due_date`、任务 `lock_version`、结构化历史和操作日志必须整体提交或回滚；项目永久删除业务图必须在任务前显式处理排期历史。对应 PostgreSQL Alembic、DO/VO、索引、初始化 SQL、权限种子和降级保护必须同步，不能依赖 `create_all()`。
- 排期读取以项目、时间窗口和稳定分页为边界，镜头、资产和项目综合视图共用一个后端读模型；未排期任务独立分页。冲突只计算当前项目内同一负责人未完成活动任务的当前计划，使用半开区间 `[start,end)`，不引入工时容量、跨项目负载、任务依赖、关键路径或自动调度。
- 改期要求 `shotgrid:task:schedule` 且操作者为项目 `director` 或 `has_all_scope` 管理人员。Service 使用短事务按“项目协调锁 → 任务锁”顺序复核实时权限、数据范围、项目/目标/任务状态、负责人、时间、乐观锁、幂等键和最新冲突集合；冲突允许二次确认，但集合变化必须重新确认。改期允许计划开始早于当前时间以表达延期，不改变任务状态、负责人、目录、版本或审核链，也不执行 NAS/Redis/外部 I/O。
- 当前任务已有排期时，开工命令只保留并展示现值，不因计划开始已过去而拒绝；尚无排期时，开工仍可按原规则建立首次完整范围并通过共享排期领域逻辑冻结基线。已有计划的修改必须走排期 API，不能在开工接口内形成第二套改期规则。
- 正式契约见 `../shot-grid-frontend/docs/superpowers/specs/2026-08-31-shot-grid-scheduling-timeline-gantt-design.md`。迁移、接口和定向测试存在不等于生产迁移、真实负载性能或完整 E2E 已通过；验收时必须分别提供证据。

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


### 镜头分配与开工前置条件（2026-11-02）

镜头导入、新建和编辑允许制作信息留空；单条、批量分配及未开工改派不要求制作内容非空，允许先分配制作人和排期。镜头制作内容为可选字段，空值、空字符串或纯空白均不阻止确认开工；镜头列表、详情和任务的 `task.start` 不再受内容完整性限制，开工接口不再校验内容必填。保留权限、管理范围、任务状态、成员有效性、排期、NAS 就绪和乐观锁门禁。景别、机位、镜头运动、焦段、时长等不新增必填限制；资产制作分项规则不变。


### 镜头 Excel 缩略图忽略边界（2026-09-08）

镜头导入忽略内嵌缩略图及绘图，不解码图片、不生成业务附件；单元格、样式和合并结构继续按原有解析契约处理。原始文件先通过 ZIP/OOXML 安全检查并计算 SHA-256，解析时仅在内存副本中移除媒体和绘图关系、用空绘图替换绘图内容，不改动上传原文件或摘要。

镜头路径显式开启图片独立计数：`xl/media/` 直属的 png/jpg/jpeg/gif/bmp/tif/tiff/webp/emf/wmf/svg 文件不占用 `max_archive_entries`（默认 256）额度，图片数量上限复用 `max_rows_per_workbook`（默认 10,000）。非图片条目仍按原上限检查；所有原始条目仍受文件大小、总解压大小、压缩比、路径、重复条目、加密和 OOXML 复杂度门禁约束。此扩展不改变资产导入安全门禁。


### 镜头管理编号排序（2026-09-09）

镜头管理的集、场次下拉选项分别按集编号、场次编号升序加载，包含写入后的选项刷新；镜头列表默认按集编号、场次编号、场内镜头 `(sortOrder, shotNo, shotId)` 排序。不再以集或场次的导入顺序作为列表排序依据，场内拖拽顺序保持有效。排序在服务端分页前执行，不修改历史排序数据。


### 退回后追加审核问题

- 2026-09-10：退回动作无论是否含新草稿都须二次提醒审核人检查是否还有遗漏或待补充问题，取消保留当前内容。最新退回版本在任务仍为 revision、制作人尚未受理下一版提交时，允许有 shotgrid:note:add 权限的项目管理人或全范围管理员追加正式问题（文字、画面标注、附件复用既有契约）；发送后立即进入制作人问题查询，已发送内容仍不可修改或删除。追加必须持有项目、任务、版本锁，复核最新版本和未解决提交；不重开审核单、不改变任务状态或候选，递增来源版本锁，同事务写 sg_note、文件引用和审计。下一版已受理（含发布中、失败待重试）或已生成时禁止追加旧版；追加先成功则原提交预检快照失效，制作人须刷新并补齐处理说明。
# 2026-09-23 审核期间追加候选

版本 preflight/create 可传 `targetVersionNo`，在当前 `pending_review` 轮次追加不可变候选；仅当前有效制作人可操作。使用 `submission_mode=append` 的独立 Outbox 批次，候选编号连续，复用已有版本和自动审核单，合并完整文件引用，保留选择与草稿并递增版本锁。项目→任务→版本锁内复核状态，追加未完成（含失败待重试）时拒绝审核结论；退回或通过后拒绝追加。新轮次唯一性使用部分索引，PostgreSQL 迁移与初始化 SQL 必须同步，存在追加记录时禁止降级。
# 2026-09-23 逐文件提示词

候选预检/创建/状态/详情/审核上下文增加可选 `generationPrompt`，最长10,000字符，支持换行和制表符、拒绝其他控制字符。提交文件与正式候选均用独立 TEXT 字段保存，同事务复制，幂等校验覆盖提示词；旧 candidateNote 不改义。迁移 `20260923_29` 同步初始化 SQL，存在提示词数据时拒绝降级，不执行提示词内容。


### 已上传文件后补提示词（2026-09-23）

补充前述提示词契约：`PUT /shot-grid/versions/{versionId}/candidates/{candidateId}/generation-prompt` 接收必传的 `generationPrompt` 和 `previousGenerationPrompt`（均可 null），复用 10,000 字多行校验。接口复用 `shotgrid:version:add`，服务端在项目→任务→版本→候选锁内复核活动成员为当前受派制作人，管理员和审核人不得代填；归档项目禁止保存。待审核、退回及通过后的文件均可补录或编辑，原值不一致返回 `SG_PROMPT_CONFLICT`，避免覆盖并发修改。只更新正式候选提示词，不修改原提交快照、文件、轮次、审核状态或版本锁号；同事务审计操作者、候选、前后摘要及长度，不记录完整提示词。版本详情返回 `canEditGenerationPrompt` 供按钮显隐，前端通过 Element Plus Form 校验并显式保存，失败保留输入；切换候选隔离迟到响应。本段取代此前不支持提交后编辑提示词的说明。


## 统一 WebSocket 实时失效通知（2026-09-23）

- 新增 `module_realtime`，沿用 FastAPI/APIRouterPro 自动注册和平台 Redis；不新增数据库表、权限菜单或第三方依赖。该通道是可扩展的统一订阅入口，首批仅注册 `shot-grid.version` 资源主题，后续主题必须新增对应的服务端授权检查。
- `POST /realtime/ticket` 走现有登录与 Axios/传输加密链，返回 30 秒有效的一次性票据；每用户每分钟最多 30 次申请。`/realtime/ws` 在首帧接收 `{type:"auth",ticket}`，票据由 Redis 原子消费并绑定 Origin；禁止把 JWT 或票据放在 URL。WS Origin 同时受 APP_CORS_ALLOWED_ORIGINS 限制。HTTP 内网例外不扩大到其他环境。
- 客户端发送 `subscribe/unsubscribe`（topic + resourceId）和 `ping`；服务端回复 `ready/subscribed/pong/event`。每连接最多 20 个订阅，消息不超过 4096 字符，每 20 秒窗口最多 100 条，65 秒无心跳断开。每次订阅、事件发送和每 20 秒重新校验登录会话、活动账号、`shotgrid:version:query` 与版本所属项目范围；Redis/鉴权故障关闭连接，不降级放行。
- 初次正式提交、同轮追加及后补提示词在数据库提交成功后发布 `version.changed`，reason 为 `version.created/candidates.appended/prompt.updated`。Redis Pub/Sub 将事件传递给不同 Worker；事件只含事件 ID、主题、资源 ID、类型和原因，不含文件、路径、提示词或审核意见。
- Pub/Sub 是失效提示，不是可重放业务事件账本；发布超时或故障不反转已提交业务。订阅确认、重连、页面恢复可见均回源校验，前台每 30 秒额外补查；无需为通知新增迁移。若将来需要逐条必达的任务事件，必须另增事务 Outbox，不得把本通道声称为可靠消息队列。
- 前端 `useRealtimeStore` 为应用共用单连接，`useVersionRealtime` 管理页面订阅、合并刷新和销毁。登出清理连接和订阅，断线按上限 30 秒的退避重连。审核详情增量更新候选并提示新增数量，不调用清空草稿的整页加载；保留当前预览、问题、附件和确认意见。发现他人更换最佳候选或审核状态改变时保留输入并阻止误提交，提示人工核对。
- Vite `/dev-api` 启用 WS 代理；Shot Grid Nginx 明确转发 `/prod-api/realtime/ws` 的 Upgrade/Connection，关闭缓冲并设 90 秒超时。当前只在审核详情订阅版本，其他页面及业务事件尚未接入，不能描述成全站推送已完成。


### 逐文件审核与最终交付（2026-09-23）

审核期间不要求选择最佳候选。每条问题草稿、画面批注及退回后补充问题通过 candidateId 绑定当前版本的具体文件，服务端在项目、任务、版本锁内校验候选归属；编辑不得改绑，删除不受最终候选选择影响。退回一次发布本轮全部文件的问题，制作人按来源文件查看。通过时才必选最终交付文件，同一审核事务设置 selectedCandidateId 和主文件并进入现有 FINAL Outbox；未清理的新问题或未解决历史问题仍禁止通过。退回和暂缓属于轮次级动作，不要求最终候选；对应动作及历史问题确认的候选字段允许 null，表示轮次级确认。PostgreSQL 迁移 20260923_30 保留原有候选外键和全部历史数据，有轮次级记录时拒绝降级。本段替代此前先选最佳才能批注的规则。


### 我的完整提交记录（2026-09-23）

工作台“最近提交”改为“我的提交”，使用 Element Plus 表格、表单和服务端分页（默认每页 10 条，可选 20/50），按提交时间与版本 ID 倒序展示本人实际提交的全部可访问版本。按项目名称/编号、任务名称、审核状态和提交日期筛选，查询和重置回到第一页；表格显示项目、任务与提交说明、版本、候选文件数、提交时间、版本审核状态及版本/审核入口。

兼容沿用 `GET /shot-grid/versions/mine/recent` 地址和 `shotgrid:version:list`，其 recent 名称不代表时间或条数上限。查询扩展 `projectKeyword`（最多 200 字）、`taskKeyword`（最多 240 字）、`submittedFrom/submittedTo`（YYYY-MM-DD，包含两端日期，倒置返回参数错误），保留 `versionStatus/pageNum/pageSize`。列表模型兼容增加可空的 `projectName/projectCode/taskName/autoReviewListId`，本人提交接口实际通过任务、项目和自动审核单关联填充，避免前端逐行补查版本详情。审核入口必须使用返回的真实审核单 ID。

数据范围继续强制 `submitted_by = 当前用户`、活动项目成员关系、项目与任务未删除，不以当前任务受派人过滤；转交后本人历史提交仍可见，项目归档后在成员访问权限仍有效时保留历史查询，撤销成员权限后不可见。所有筛选在数据库计数与分页前完成，无数据库表变更或迁移。前端加载失败明确提示并支持重试，卸载/新请求中止旧请求，筛选草稿不污染当前已应用分页条件。


### 2026-09-23 退回修改交接与履历展示

- 普通待开工改派规则不变；已退回任务新增 `task.transfer`。仅具有 `shotgrid:task:assign` 且具备项目总监或全部数据范围的管理人员可转交，适用于镜头和资产制作分项。
- `POST /shot-grid/versions/{versionId}/transfer-revision` 接收 `{assigneeUserId, reason, handoffNote?, lockVersion, taskLockVersion}`；必须是最新 rejected 版本且任务 revision，无未完成或失败待重试提交。项目、目标和接手 creator 均须活动有效。沿用项目→任务→版本锁，锁内复核权限、状态与 CAS。
- 审核 reject 支持可选 `revisionTransfer: {assigneeUserId, reason, handoffNote?}`，与发布问题和审核结论处于同一事务；其他审核动作禁止该字段，默认不转交。保留原审核幂等语义。
- 仅更新当前任务负责人、审计字段和任务版本，任务保持 revision，不新建任务、不提前创建 V002，不重置目录、排期和历史版本提交人。新负责人逐条说明原问题处理结果后提交下一版，原负责人保留自己的提交记录。
- PostgreSQL 迁移 `20260923_31` 为 sg_task 增加只追加 JSONB `revision_transfers`（人员和时间快照、来源版本、原因、交接说明），作为业务历史随任务保留。已有转交记录时禁止降级丢失历史；该功能不承诺 MySQL。
- 制作履历返回 `task_transferred` 独立事件和版本 `files` 完整审核文件摘要。版本卡片去重展示版本、提交人、说明及查看作品/查看审核入口，文件列表折叠显示；处理说明数量不代表问题已解决。
- 审核页显示本版提交人、实际审核动作记录和当前查看文件；没有动作时显示等待审核，不把浏览者当作已审核人。当前负责人不同于提交人时单独显示。
- 任务详情额外返回 `latestHandoff` 类型化交接摘要，在制作要求上方展示最近交接的人员、时间、原因和交接说明；列表接口不携带交接历史。


### 2026-09-23 审核问题来源文件展示

问题详情兼容增加可空字段 `originCandidateNumber`，由问题绑定的 `originCandidateId` 联查来源版本下的候选编号，格式如 `V001_02`；不使用当前候选或数组顺序推断。复核卡片优先显示来源文件编号，缺失时明确提示来源文件待确认；历史对比标题显示实际加载的候选编号。沿用现有问题读取权限、数据范围和响应协议，无数据库结构变更。

### 2026-09-24 制作履历任务信息补充

履历 lanes[].task 兼容增加可空 expectedStartTime/expectedEndTime 与 baselineStartTime/baselineEndTime，分别读取现有 sg_task 当前计划与首次冻结排期。沿用现有履历权限、项目范围及响应协议，不新增数据库字段或迁移。任务建立节点显示任务创建人、创建时间、任务名称、当前制作人及当前计划制作时间；首次排期保留在数据契约中，不在该节点重复展示；当前负责人不代表最初受派人，首次排期也不等于创建时即已设置的时间。计划时间不代表实际开工或完成时间；未设置明确展示“未设置”。创建人不推断为审核人。
### 2026-09-24 镜头列表转交前制作人

镜头列表及详情兼容增加 previousAssigneeNames，读取任务 revision_transfers 的 fromUserId/fromName 快照，按最近转交优先并按用户去重，无记录返回空数组。不返回交接原因等完整记录，不增加逐行请求；沿用镜头读取权限与项目数据范围，无数据库迁移。列表制作人列区分当前制作人与转交前制作人；当前制作人筛选语义不变。

### 2026-09-24 追加问题实时同步

退回后的追加问题在事务成功提交后发布 shot-grid.version / version.changed（issue.appended），失败不发布。制作任务详情订阅最新返修版本并增量更新 openIssues，版本履历订阅当前查看版本并增量更新意见；保留制作人的处理说明、当前文件及预览状态，隔离切换任务或版本后的迟到响应。沿用现有订阅授权、跨 Worker Redis 广播和断线/可见性/定期回源补偿；不是离线消息或全站通知。
### 2026-09-24 镜头列表任务抽屉入口

镜头 allowedActions 兼容增加 task.work 与 task.review，仅作为详情导航入口，不替代写接口鉴权。活动且存储就绪的项目中，当前受派 creator 在 in_progress/revision/pending_review 且具备任务查询和版本提交权限时返回 task.work；项目 director 或 has_all_scope 管理人员在 pending_review 且具备版本审核、版本查询及审核单查询权限时返回 task.review。没有唯一任务审核人字段，不以登录人推断指定审核人。列表分别显示“去做任务”“去修改”“追加审核文件”“审核任务”；审核入口点击时通过最新版本详情的 autoReviewList.reviewListId 定位真实审核单，不用版本 ID 替代。复用 RelatedDetailDrawer，内部关联导航继续留在抽屉，关闭后刷新当前列表并保留筛选分页；接口权限和数据范围保持不变，无迁移。
### 2026-09-24 审核结果实时同步

审核动作事务提交成功后发布 version.changed（review.approve/reject/defer），回滚不发送。镜头列表复用统一 WS 连接，仅订阅当前页最新版本，合并事件后按当前筛选分页回源，切页取消旧订阅，写入或筛选草稿期间推迟刷新，并保留定期补查。任务详情订阅待审核及返修版本，增量回源任务状态、allowedActions 和问题，状态变化本身不清空上传表单。沿用既有版本订阅授权及所有业务接口鉴权，不新增主题或数据库字段。

### 2026-09-24 返修新版本实时同步

新轮次正式提交成功后，除向新版本发送 version.created 外，同时向同一任务上一轮版本发送 version.superseded 失效提示，便于仍订阅旧版本的镜头列表回源最新状态与审核入口，再切换新版本订阅。上一轮 ID 在任务锁内、创建新版本前读取；事务失败不通知；首版无上一轮时仅通知新版本；追加候选仍只发送 candidates.appended。沿用现有版本订阅鉴权和 Redis 通道，不传递新版本业务数据，不新增主题或数据库字段。

### 2026-09-24 返修期追加问题入口

镜头 allowedActions 增加 task.appendIssue：仅活动且存储就绪项目的 director 或全部范围管理人员，在任务 revision、最新版本 rejected、无未完成提交且具备版本审核/查询、审核单查询、问题新增权限时返回。列表显示“追加发送问题”，用真实自动审核单 ID 打开现有审核抽屉。追加提交仍由服务端锁内复核下一版是否已受理，成功后沿用 issue.appended 通知制作人增量回源；导航不替代写入鉴权。

### 2026-09-24 旧版追加入口实时失效

返修下一版提交事务受理成功即向上一版发送 submission.accepted；不等待 NAS 正式发布。旧版审核页收到事件或周期补查时重新读取审核上下文的 canAppendIssues，只更新追加权限，不整页重置候选和草稿。服务端继续在项目/任务锁内拒绝已有未完成提交或已有新版本时追加意见；WS 不替代该并发门禁。

### 2026-09-24 审核与本人提交按任务分组

项目审核单和本人提交查询兼容增加 groupByTask，默认 false 保持原有逐条分页；true 时在原权限与筛选范围内先按任务分组分页，total 表示分组数，rows 返回该页任务下全部匹配记录。人工批量审核单独立成组，不虚构任务归属。项目审核列表项兼容增加 taskName，沿用现有任务关联；无数据库迁移。我的提交始终受 submitted_by、有效项目成员及未删除项目/任务约束，转交后不扩大到他人提交。前端使用 Element Plus 树表，父任务默认折叠、子版本倒序、键包含项目和实体类型；父级状态表示筛选内最新匹配版本，不冒充任务当前状态。筛选先于分组，旧调用方不传 groupByTask 时响应与分页语义不变。

### 2026-09-24 工作台与审核默认镜头排序

我的制作任务、我的提交、版本审核前端默认请求 orderByColumn=shotNo、isAsc=ascending；我的制作任务重置筛选恢复该默认。三个列表的服务端查询兼容 shotNo，按项目 ID、数字集号、数字场次号、数字镜头号、任务 ID 稳定排序，无镜头号的资产任务/批量单排后。同任务版本保留新到旧。分组查询在分页前使用同一排序选取任务组，不能只对当前页排序。保留旧排序调用兼容及原权限、数据范围、筛选语义，无迁移。


### 本版整体反馈（2026-09-24）

审核意见支持 `issueScope=candidate|version`，默认 candidate 保持现有文件反馈契约；version 必须有文字、不得传候选、视频时间点或画面标注。整体反馈仍绑定具体版本，草稿 `candidateId`、正式问题 `originCandidateId` 为 null，不得回落到当前候选。沿用草稿发布、退回后追加、制作人逐条回复、下版逐条复核和实时同步权限/事务链。编辑草稿不可改变反馈范围。前端使用 `ElTabs type="border-card"` 展示“整体反馈意见 / 填写修改意见”，未保存或提交中禁止切换；整体反馈独立分组且不显示候选画面定位。PostgreSQL 迁移 `20260924_32` 放开两个候选字段空值并同步初始化 SQL；已有整体反馈时拒绝降级，避免错误绑定或数据丢失。


### 已发布意见编辑与删除（2026-09-24）

追加窗口内兼容开放 `PUT/DELETE /versions/{versionId}/additional-issues/{issueId}`，沿用 `shotgrid:note:add` 与项目审核管理权限，只允许操作本人在该版本提出且仍 open 的问题。PUT 沿用追加模型，DELETE 使用版本 `lockVersion`。追加、编辑、删除共同持有项目/任务/版本锁，并复核最新退回版本、任务 revision、版本锁、无已受理的下一版提交；制作人提交受理成功即关闭全部入口，不等待 NAS 发布。编辑不能改变整体/候选归属，保留原始提出人/时间；删除只清除该条意见及业务附件引用，不删除附件实体，关联历史由外键保护。编辑前后快照和删除前快照在同事务写平台审计，为避免 2000 字符截断按 auditId + part/parts 分片保存完整 JSON；恢复需管理员据快照核对版本边界处理，不开放用户直接恢复。成功后递增版本锁并发布 issue.updated / issue.deleted，制作人按版本实时回源刷新意见及数量。此条取代“已发布意见不可编辑/删除”的旧限制；下一版提交后的历史仍不可改。

### 2026-09-24 已发布问题禁止删除（替代前述删除契约）

退回前的问题草稿仍可删除；已发布问题禁止删除，包括追加窗口内本人提出的问题。前端移除删除操作，旧 DELETE additional-issues 接口保留鉴权并明确拒绝（SG_PUBLISHED_ISSUE_DELETE_FORBIDDEN），不修改问题、附件引用、版本或任务状态。下一版提交前仍可追加新问题、编辑本人未解决问题；下一版受理后禁止追加与编辑。删除草稿不自动改变任务状态，不开放退回版本直接通过。

### 2026-09-24 批量整体反馈并退回（旧接口兼容，后续新入口见文末）

镜头列表全部选中可审核任务时，可填写同一份整体文字反馈，点击“发送意见并退回修改”。POST /shot-grid/projects/{projectId}/review-overall-feedback/batch-reject 接收 versionIds（1..100，正整数且不重复）与 content（非空、最多 10000 字）。必须同时具备 shotgrid:note:add、shotgrid:version:review，并逐项复核项目审核管理范围、活动项目、最新待审核版本、任务待审核、自动审核单 active、无未完成文件提交。有已有草稿或上轮问题待复核时拒绝，必须进入任务逐个审核，不隐式发送原草稿或代替历史复核。同项目按任务 ID 固定顺序加锁，复用整体反馈草稿发布和审核退回逻辑；所有意见、任务 revision、版本 rejected、审核单 completed 及审计同一事务提交，失败整批回滚。成功后逐版本发布 review.reject 实时通知；不改变制作人。前端固定打开弹窗时的具体版本，不自动改投新版本。整体反馈发布后禁止删除，下一版提交前允许作者编辑。无数据库迁移。


### 2026-09-28 批量反馈与历史问题复核

镜头列表入口升级为“批量反馈与复核”。新接口 `POST /shot-grid/projects/{projectId}/review-overall-feedback/batch` 是兼容扩展，旧 `batch-reject` 接口保留原有保守限制。沿用登录认证、同时具备 `shotgrid:note:add` 与 `shotgrid:version:review`、项目 director 或全部范围管理人员、现有 camelCase/envelope、审核 Service/DAO 和同事务审计，无数据库迁移。

请求字段：`action: save_draft|reject`、`content`（最多 10000 字，保存草稿或附带参考内容时必须非空）、`referenceFileIds`（可省略，默认空，最多 5 个不重复 UUID）、`items`（1..100 个不重复版本）。每项携带 `versionId/lockVersion`、明确的 `drafts: [{draftId, lockVersion}]` 快照，以及 `issueVerifications: [{issueId, result, comment}]`。不支持批量通过或转交负责人。

- 弹窗只读取打开时选中的版本，展示历史问题、制作人处理说明、逐镜头复核进度与已有草稿。问题默认未复核；支持勾选问题后统一标记“已解决”或“仍需修改”，后者必须填写原因。已有草稿展示后须显式确认发布，默认不勾选。
- `save_draft` 只为每项保存新的整体反馈草稿，不发送、不改变任务或版本状态、不提交历史复核结果。复核选择仅留在当前弹窗，关闭后不保存。版本锁递增，重复提交相同快照被拒绝。
- `reject` 必须完整复核每个版本全部带入问题，仍存在的问题必须填写原因；每个任务必须至少存在共同新反馈、已有草稿、当前新问题或仍未解决问题。所有历史问题均解决且没有新问题时，应从批量退回中取消选择，单独审核通过。
- 后端先锁项目并复核可写状态，再按任务 ID 固定顺序锁版本并重查管理范围、最新待审核状态、活动自动审核单和无未完成文件提交；已有草稿 ID 集合及各自锁号必须与请求精确一致。草稿新增、修改或删除都会导致冲突，绝不隐式发布审核人没看到的草稿。
- 新共同意见复用整体反馈草稿，历史复核复用现有审核动作：原问题不复制或迁移，制作人说明与逐版本确认保留。整批草稿、问题、复核、状态及审计一次提交，任何项失败整批回滚；仅提交成功后发布逐版本 `review.reject` 通知。
- 前端使用 ElForm 校验和显式按钮、ElTable 选择；加载/提交期间禁用，防重复请求。项目切换或卸载取消读取并隔离迟到结果，弹窗期间暂停列表自动刷新。冲突保留输入并要求重新核对；网络结果未知时不直接重试，需刷新确认。禁止自动换成更新版本后重发。

### 2026-09-28 批量反馈参考内容

- “批量反馈与复核”的补充反馈步骤与“批量追加发送问题”均提供“参考内容（可选）”，最多 5 个，每个不超过 20 MiB。支持 BMP/JPG/JPEG/PNG/GIF 图片、PDF/Office/TXT 文档及 MP4/MOV 短视频；沿用单条反馈规则，附件不能替代整体反馈文字。
- 前端复用 `ReviewReferenceInput` 与 `useReviewReferenceAttachments`，通过既有鉴权上传接口 `/common/files/upload` 上传一次，再将同一组文件 ID 用于全部目标。展示文件名、图片预览、移除和上传进度；上传期间禁用编辑；关闭或卸载取消未完成上传并隔离迟到结果。上传失败不提交业务反馈，已成功上传的文件保留 ID，重试仅上传剩余文件。
- 批量补充反馈的 `referenceFileIds` 是可选兼容扩展，旧请求仍可省略；`save_draft/reject` 都把这些文件交给现有 `add_issue_draft` 引用链路。校验当前审核人的所有权、上传人、私有本地存储、有效状态、类型及大小。文件引用与草稿、问题、复核和状态在同一事务提交或回滚；发布草稿时引用迁移到正式问题。同一文件可被多个问题引用，下载继续逐业务鉴权，无新增表或迁移。
- 批量追加复用 `additional-issues` 已有 `referenceFileIds` 字段，各项独立提交，成功项引用保留；不改变部分成功和未知结果停止的原有语义。通用上传成功不表示反馈已发送，未绑定的上传文件遵循既有文件生命周期，不直接删除共享文件。
- 第二步与最终汇总展示共同参考资料，前后切换保留本次文件；清空新增反馈同时移除本次文字和文件，不影响已有草稿、复核或草稿确认。保存新增反馈草稿会保存文字与参考内容，不提交复核结果。

### 2026-09-28 制作中镜头任务调整（兼容扩展）

新增 POST /shot-grid/projects/{projectId}/shots/production-adjustments，单条与批量共用（1..100 项），仅作用于活动项目中的 in_progress 镜头任务。保持普通编辑、待开工改派与返修交接原规则。请求包含 reason、items；每项有 shotId/taskId/lockVersion/shotLockVersion 及稀疏 changes，省略字段不修改，文本 null 明确清空。允许计划起止时间、负责人、优先级及镜头制作内容/时长/景别/机位/镜头运动/焦段/对白/音效/色调参考/备注；禁止更改镜头身份、目录和实际开工时间。

沿用登录认证、task:edit、项目 director/全部范围；按变更字段额外要求 task:assign、task:schedule 或 shot:edit。Service 持有项目协调锁，按 taskId 排序锁任务、镜头，校验双版本、目标活动性、有效制作人和无待完成/失败待重试的版本提交。最终负责人及排期用于重叠校验（包含批内目标），重叠需显式确认精确冲突快照。整批业务、只追加排期历史及完整前后审计同事务提交，失败整体回滚。沿用平台日志分片记录长文本，首次排期不覆盖；无新增数据库结构或迁移。前端 ElForm/ElTable 三步确认，仅勾选字段进入请求，支持统一和逐镜头值；未知提交结果不直接重试。

### 2026-09-28 制作任务参考内容（兼容扩展）

- 制作调整 `changes.referenceFileIds` 为可选追加列表（1..5 个规范 UUID），省略不修改。每个任务累计最多 5 个有效文件，同一文件去重；批量共享上传文件引用，任一项失败整批回滚。
- 复用平台私有文件上传与 `sys_file_reference`，业务类型 `shotgrid_task_reference`、业务 ID 为任务 ID，不新增数据表或迁移。仅接受当前操作者本人拥有且上传的活动本地私有文件，支持与反馈参考资料相同的图片、文档及 MP4/MOV，每个不超过 20 MiB。追加需要任务编辑及镜头编辑权限，沿用制作调整的管理范围、双锁和状态门禁。
- 任务详情返回 `referenceFiles`；`GET /shot-grid/tasks/{taskId}/reference-files/{fileId}/download` 复用任务查询权限、项目可见范围与平台文件鉴权下载（deny 优先、支持 Range），不得公开 URL 或绕过文件服务。项目永久删除纳入该类业务引用的解除与独占文件清理。
镜头列表和镜头详情的 referenceFiles 与任务详情共用任务参考文件引用及鉴权下载地址；列表按当前页任务 ID 批量查询，未分配镜头返回空列表，不逐镜头请求。任务详情、镜头详情和列表展开制作要求统一显示参考内容，图片可预览，文件可下载。

### 2026-09-28 任务参考说明与列表列

制作调整中的参考内容排在字段末尾，支持纯文字或附件。changes.referenceDescription 为追加说明（单次及累计最多 10000 字），空值不清空旧内容；与 referenceFileIds 共用管理范围、双锁、镜头编辑权限及原子事务审计。sg_task 新增可空 Text reference_description，迁移 20260928_33；有文字时禁止降级丢失数据。任务、镜头详情及镜头列表返回 referenceDescription，制作要求与附加参考内容列同时展示文字和受保护附件。附件仍累计最多 5 个，每个 20 MiB。


### 2026-09-28 项目共享资料（兼容扩展）

- 创建、编辑项目支持可选 `referenceDescription`（最多 10000 字）和 `referenceFileIds`（最多 5 个不重复 UUID）；资料可为剧本、参考文档、图片或 MP4/MOV，每个不超过 20 MiB。编辑省略字段保留原值，说明 null/空白清空，文件空列表解除引用，不直接删除物理文件。
- 已核对 PostgreSQL 项目 DO、VO、项目管理权限/行锁/乐观锁、平台私有文件与事务：说明存入 `sg_project.reference_description`，迁移 `20260928_34` 接续 `20260928_33`，同步初始化 SQL；文件复用 `sys_file_reference`，类型 `shotgrid_project_reference`、业务 ID 为项目 ID。新增引用必须为操作者本人上传且拥有的有效本地私有文件，已绑定本项目的资料允许其他项目管理人保留；跨项目任意文件 ID 不构成授权。
- 资料随项目创建/编辑及审计同事务保存；继承既有创建权限、编辑 director/全部范围、项目可写状态和 lockVersion 门禁。任务详情（镜头及资产）实时投影 `projectReferenceDescription/projectReferenceFiles`，不复制到任务。项目详情返回 `referenceDescription/referenceFiles`。下载必须经过项目查询或任务查询的接口权限、项目成员/全部范围、精确业务引用及平台文件鉴权（deny 优先）；不返回公开链接。
- 前端复用 Element Plus Form、既有参考资料上传/预览组件和统一 Axios，上传失败不保存项目；保留已成功上传 ID 供重试，关闭/切换隔离迟到响应。项目永久删除解除本类引用，仍被其他业务引用的共享文件保留。资料说明按纯文本显示。归档只读。
- 验证范围：定向模型/服务/路由与表单测试、隔离 PostgreSQL 引用事务和迁移验证；这些证据不代表完整系统 E2E。


### 2026-09-28 可选预告片集 EP000

集号允许 0..2147483647，EP000 表示可选预告片，EP001 起为正片。Excel 可增加名为 EP000 的工作表（复制官方模板工作表并改名），与正片一起或单独导入；不需要预告片时无需添加。新建集可手动输入 0，默认仍建议下一正片集号。集号在项目内唯一，归档集继续占号，负数、越界与重复 Sheet 集号仍拒绝。

基座对齐：沿用 sg_episode 整数集号、原权限/项目锁/事务、导入预览与幂等提交、唯一索引及目录 Outbox；仅放宽 VO、解析与 PostgreSQL CHECK，迁移 20260928_35 接续 34，同步 PostgreSQL 初始化 SQL。展示统一三位 EP000；NAS 沿用至少两位目录快照约定（预告片 EP00，正片 EP01 等），不重命名任何已有目录，不改变镜头文件名规则。迁移不新增预告片数据，降级锁表且遇到任何集号 0（含删除/归档）拒绝，无数据截断或重编号。此兼容扩展仅承诺 PostgreSQL。

### 版本文件复制 NAS 路径（2026-09-28）

版本详情和审核上下文的文件模型兼容增加可空 `nasPath`，由项目冻结的 `project_path_snapshot` 与文件冻结的 `nas_relative_path` 拼接为完整 UNC 文件地址。沿用现有版本查询/审核权限和项目可见范围；不新增路由、权限或数据库迁移，不返回服务器挂载路径或凭据。路径缺失、非 UNC 或存在越界片段时返回 null。复制的是该版本文件原始 NAS 位置，不是另行发布的 FINAL 副本。版本文件行右侧仅在有路径时提供 Element Plus 复制按钮，复用支持内网 HTTP 的剪贴板工具，并提示成功或失败。


### 2026-09-29 制作人工作台任务与提交分层

工作台使用“我的任务 / 提交记录”标签页，任务默认未完成，提交记录按最近提交时间倒序并沿用按任务分组分页。替代 2026-09-24 对这两个工作台列表的默认镜头排序约定；版本审核列表不变。任务行使用 Element Plus Table，展示当前任务状态和最新版本摘要，详情复用 RelatedDetailDrawer，关闭刷新当前任务页，标签切换保留筛选和分页。已退回版本不代表当前任务待修改，历史查询继续按本人实际提交范围。

基座核对：沿用任务 Controller/Service/DAO/VO、当前用户强制受派与活动成员范围、ResponseUtil 分页 envelope、PostgreSQL 条件表达式。任务筛选兼容增加 unfinishedOnly（默认 false，与具体 taskStatus 取交集），排序增加 workbench：固定待修改、制作中、待审核、待开工、目录准备中、已完成，组内按 expectedEndTime（缺失回退 dueDate，空值末尾）、紧急优先级、任务 ID 升序。workbench 是固定优先顺序，不随 isAsc 反转；所有筛选与排序在计数和分页前执行，不扩大权限。不改表、事务、写操作或文件引用，无迁移；此扩展验证范围为 PostgreSQL。取消仅当前页的状态统计，不将其冒充全量统计。制作人不提供自行开工入口。


### 2026-09-29 提交记录筛选体验

提交记录默认全部状态、不限时间，按最近提交倒序。审核状态使用全部/已退回/待审核/最终版本快捷选项；项目使用可搜索且可清空的选择器；日期提供今天、近7天、近30天快捷项，包含今天和起止日。状态、项目、日期选择立即经过 ElForm 校验后查询，文字搜索按 Enter 或显式按钮执行；快速切换取消旧请求并拒绝迟到回写，加载保留列表，清空筛选回到第一页。状态提示明确只筛选历史版本，不推断当前任务状态。

基座对齐与兼容扩展：复用 review Controller → Service → DAO → VO、PreAuth/CurrentUser、shotgrid:version:list、ResponseUtil 和 SQLAlchemy PostgreSQL 条件表达式。新增 GET /shot-grid/versions/mine/projects，返回 data[{projectId, projectName, projectCode, projectStatus}]，按项目去重；严格以本人 submitted_by、当前活动项目成员、未删除项目/任务限定，允许仍可访问的归档项目与转交前历史提交，不要求 project:list，也不允许全部范围身份查看他人提交选项。原 mine/recent 增加可选 projectId 精确匹配，projectKeyword 保留兼容，均在计数和分组分页前应用；taskKeyword 仍仅匹配任务名称，前端提示不得宣称独立的镜头/资产字段搜索。项目选项失败独立提示并可重试，不影响其他筛选。无数据表、文件引用、写事务和迁移变更。


### 2026-09-29 工作台审核入口与角色呈现

- 同时具备 `shotgrid:reviewList:list` 与 `shotgrid:version:review` 时显示“待审核”标签并默认进入；具有 `shotgrid_creator` 角色的兼任制作人继续保留有权限的“我的任务”和“提交记录”。没有审核能力的用户沿用制作入口，仍分别校验任务/版本列表权限。角色判断仅决定页面呈现，不替代服务端权限与项目范围校验。
- 审核队列使用 `GET /shot-grid/review-lists/mine`，新增可选 `projectKeyword`（最多 200 字符，仅该队列使用），按项目名称或编号模糊匹配；现有 `keyword` 匹配审核单名称，`reviewMode` 区分自动单版和人工批量。所有条件在计数和分页前执行，固定按创建时间倒序。
- 沿用活动审核单、非归档且未删除项目、活动 director 成员范围或跨项目全部数据范围；不是个人独占指派。操作“进入审核”继续要求审核单详情权限。未修改状态流转、写入或数据库结构。
- 审核区采用独立标题、Element Plus Form 筛选、Table 和居中分页；项目/名称通过搜索或 Enter 查询，类型立即查询，每页 10/20/50 条，查询和修改条数回到第一页。保留加载、错误重试、空态、请求取消及迟到响应隔离。


### 2026-09-29 审核工作台抽屉与快捷筛选

- “进入审核”复用 `RelatedDetailDrawer`，不离开工作台；关闭后刷新审核队列和项目选项，保留已应用筛选、排序和页码，仅在记录减少导致页码越界时回退到最后有效页。
- 审核类型改为全部/自动单版/人工批量快捷切换；项目支持名称或编号搜索下拉选项，选择后按 `projectId` 精确过滤；名称 Enter 或搜索按钮查询，清空名称立即查询。切换类型、项目、排序可取消旧请求并隔离迟到响应。
- 新增 `GET /shot-grid/review-lists/mine/projects`：认证和 `shotgrid:reviewList:list` 权限与审核队列一致，DAO 共用活动审核单、非归档未删除项目及活动 director/全部范围约束，返回去重项目 `projectId/projectName/projectCode`；无额外项目列表权限依赖，不从当前页推导选项。
- `/review-lists/mine` 增加可选 `projectId`，保留旧 `projectKeyword` 兼容；`isAsc` 控制创建时间及同时间审核单 ID 的稳定排序。工作台默认最早创建优先，亦可选择最近创建优先；接口未传排序方向时保持原倒序默认。此条更新上一节的固定倒序说明。无数据库迁移。


### 2026-09-29 待审核按内容检索与镜头顺序

- 工作台 `/review-lists/mine` 使用独立 `ShotGridMineReviewQueryModel`，扩展 `taskKind`（shot_video/asset_image）、`submitterKeyword`（账号或姓名）、`submittedFrom/submittedTo`（含首尾日期）以及 `orderByColumn=submittedTime`；沿用原项目、审核方式及范围约束。`keyword` 匹配审核单名称、任务名称和镜头序号，组合条件通过同一版本的 EXISTS 判断；批量单任一成员版本满足全部条件即可命中，仍按审核单计数、分页。
- 镜头排序复用数值型集/场/镜头序号，按项目、镜头/资产/批量类别、集、场、镜头、任务、版本和审核单 ID 稳定排列；资产和批量单不虚构镜头号。提交时间排序使用单版版本提交时间，批量单使用创建时间，并由列表说明明确区分。工作台默认等待最久；项目审核列表契约不变。
- 列表新增可空 taskKind/submittedByName/submittedTime，单版标题优先 taskName；制作人显示实际提交人而非当前负责人；首版/后续版本只依据 versionNo，不推断所有后续版本都已退回。批量单保留原名称、版本数及明确的创建时间标签。
- 内容类型快捷筛选替代审核组织方式；项目、内容搜索、排序、审核方式、制作人、日期及操作按钮在桌面端常驻同一行，不使用折叠，窄屏自动换行。类型/项目/排序/日期选择立即查询，文本支持 Enter，清空恢复默认。主操作进入审核/批量审核使用实心主色，同色 plain 查看作品仅在单版存在 autoVersionId 且具备版本详情权限时显示；均使用已有详情抽屉。未增加“审核下一项”，未改写任何业务状态，无数据库迁移。


### 2026-09-29 审核制作人筛选使用项目成员

- 制作人改为可搜索、可清空的 Element Plus 下拉框，选择后通过 `submittedBy` 用户 ID 精确匹配版本提交人，不能按当前任务负责人替代。保留 `submitterKeyword` 查询兼容。
- 新增 `/review-lists/mine/producers?projectId=...`，继承认证及 `shotgrid:reviewList:list` 权限。选项来自审核范围内项目的活动 creator 成员和未删除用户，按用户 ID 去重；未选项目时聚合该范围全部项目，指定项目仍须通过相同的活动 director/全部数据范围约束，不能查询任意项目用户。项目范围与待审核项目下拉框一致，不依赖当前页提交记录推导。
- 展示姓名与账号，切换项目立即清空制作人并重载成员；请求可取消且隔离迟到结果，加载期间禁用，失败提供重试。单行筛选布局不变，无数据库迁移。

### 2026-09-29 单任务排期允许重叠直接保存

单任务 `PUT /shot-grid/tasks/{taskId}/schedule` 允许同一制作人员排期重叠，不再返回重叠二次确认门禁；调整排期弹窗移除重叠清单与确认复选框，正常校验后一次保存。旧请求字段 overlapAcknowledged / expectedConflictTaskIds 兼容接收，但不作为保存条件，前端不自动代确认；仍记录实际重叠任务与原请求确认值。权限、项目范围、活动目标及负责人、只读状态、lockVersion、幂等、时间范围、原因、不可变基线和同事务历史审计规则保持不变。此变更仅覆盖单任务排期接口，不变更批量制作调整的独立确认协议，无数据库迁移。

### 2026-09-29 排期实际节点与日期提示

排期详情和编辑复用现有 production-history 鉴权接口，严格按当前 taskId 对应 lane 聚合创建、首次/最近提交、最近审核与审核通过时间；资产分项通过父资产请求，不能混入其他分项。当前履历无独立开工节点，明确显示未记录，不从基线推断。加载失败显示重试，不冒充无历史；切换任务中止请求并隔离迟到结果。计划早于创建、晚于首次提交、未开工计划已开始、未完成计划已结束为提示，不阻断补录；原时间与新时间并列展示。单任务排期保存仍先检查权限、版本和幂等，起止完全相同返回 SG_TASK_SCHEDULE_UNCHANGED，不递增版本、不新增历史。旧幂等命令回放不受影响。无需数据库迁移。

### 2026-09-30 先排期再确认开工

镜头任务与资产制作分项统一先通过既有 `PUT /shot-grid/tasks/{taskId}/schedule` 保存计划起止时间，再由管理人员确认开工。开工接口在原权限、项目协调锁、目标及任务版本检查后拒绝未排期任务（422 `SG_TASK_SCHEDULE_REQUIRED`）；已有排期只读沿用，不接受开工请求覆盖日期，不再在开工事务建立首次排期或基线。旧时间字段保留模型解析以返回明确错误；不改表，不需迁移，旧履历保留。

单项开工弹窗的设置/调整排期入口复用现有排期表单、权限、幂等键、必填原因及历史记录；保存后仅以该响应的新任务版本确认开工，父对象版本与原上下文校验保持不变。取消开工不撤销已经单独保存的排期，关闭后刷新父列表。批量开工可在当前弹窗对未排期项统一设置或逐项调整，调用既有单任务排期接口逐项保存原因、历史和幂等键，回写成功项的新任务锁号；保留选择、不自动开工。开工范围使用 ElTable 选择，只有用户明确选择“仅选择已排期项”才缩减范围；未排期或失败待核对的选中项阻断开工。部分失败不撤销已保存项，权限或网络错误停止后续保存，不自动重试。镜头列表另提供独立“批量设置排期”，面向有排期权限的待开工任务，不要求开工权限、不提供开工按钮。各展示入口统一称为“计划起止时间”。

### 2026-09-30 待排期派生阶段

工作流展示统一为待分配 → 待排期 → 待开工 → 制作中（目录准备中为中间阶段）→ 待审核 / 待修改 / 已完成。底层任务状态 `not_started` 保持不变；缺少完整 `expectedStartTime` / `expectedEndTime` 时派生 `pending_schedule`，完整排期后展示为待开工，排期保存不触发开工。任务和镜头响应保留原状态，前端统一使用任务及时间字段派生展示；不得把派生阶段写回任务状态机。

任务、镜头与排期查询接受 `pending_schedule`；筛选 `not_started` 只返回已有完整排期的未开工任务，判定在数据库分页前执行。资产父级和分项的 `assetStatus` 属于派生聚合，可返回 `pending_schedule`。`itemStatusCounts` 扩为八个固定非负整数键：`unassigned/pending_schedule/not_started/preparing/in_progress/reviewing/revision/completed`，覆盖旧七键约定。父级优先级为 revision → reviewing → in_progress → preparing → unassigned → pending_schedule → not_started；全部活动分项完成才为 completed。

镜头表格/卡片/故事板/详情、资产列表/分项/详情、工作台、任务详情、排期详情/未排期列表及制作履历当前阶段统一展示；制作履历阶段条增加排期与确认开工。历史原始 not_started 只称未开工，不以当前排期倒推历史事件，不虚构开工或排期时间。本次无表结构变更，无需数据库迁移。

### 2026-09-30 排期原因选填

单项首次排期、调整排期、批量排期及制作任务调整的原因统一选填，前端保留 500 字上限，日期和其他业务校验不变。后端接受省略、空字符串或纯空白原因，统一规范化为“未填写”后参与幂等、历史及审计，兼容历史表非空原因约束；非字符串或超长内容仍拒绝。不需数据库迁移。此约定替代此前必填原因要求。


### 2026-09-30 镜头待完善阶段

镜头无任务且制作内容为空白时派生 `pending_info`（待完善）；内容非空且无任务为 `unassigned`（待分配）。待完善镜头可先分配制作人；已有任务按任务状态及排期展示待排期/待开工，不退回待完善，同时提示内容待补充。列表在数据库分页前派生筛选，详情与制作履历保持一致；不新增持久状态或虚构历史事件。制作内容缺失仅作提示，不阻止确认开工；仅针对镜头，资产保持原规则，无数据库迁移。


### 2026-09-30 镜头编辑参考内容

镜头创建/未开工编辑增加可选 referenceDescription（10000 字）和 referenceFileIds（最多 5 个 UUID，单个 20 MiB），省略保留，说明 null/空白与文件空列表明确清空。说明存入 sg_shot.reference_description，PostgreSQL 迁移 20260930_36 接续 20260928_35；附件复用平台私有业务引用 shotgrid_shot_reference。新增附件必须本人上传并拥有，已绑定本镜头的附件可由其他项目管理人保留，沿用项目协调锁、任务状态、镜头乐观锁与同事务审计/回滚。仅扩展 PostgreSQL 基线。

镜头响应另含 shotReferenceDescription/shotReferenceFiles 供编辑，referenceDescription/referenceFiles 聚合镜头资料和原任务追加资料供查看；任务详情实时投影镜头参考内容，不复制、不覆盖任务追加内容。下载由镜头查询或任务查询权限、项目范围、精确镜头引用和平台 ACL 共同约束；任务入口只可下载其关联镜头资料。项目永久删除解除该类引用并沿用独占文件清理，软删除保留引用。标题显示集/场次/镜头完整编号。上传失败不保存，保存仍由 ElForm 校验，未保存关闭提醒包含附件草稿。

### 2026-09-30 制作任务编辑允许排期重叠

单项及批量制作任务编辑允许同一制作人员排期重叠，保存不再要求额外勾选或冲突快照确认，页面不展示内部任务 ID 清单。制作调整接口兼容接收 overlapAcknowledged / expectedConflicts，但不再作为保存门禁；不由前端代为确认，实际重叠任务及原请求确认值仍写入排期历史。权限、双版本锁、状态限制、原子事务和不可变基线保持不变。本规则替代此前制作调整重叠二次确认约定，无数据库迁移。


### 2026-10-08 资产名称允许纠错

活动项目内有资产编辑权限的管理人员可通过原 PUT 修改活动资产名称，包括已有分项开工的资产；类型和 NAS 目录快照保持不可变，描述仍受原开工门禁限制。assetName 省略保留，显式空白/null/超长拒绝；复用创建规范化与安全规则，在项目协调锁、资产乐观锁内检查同项目同类型活动名称唯一。改名同事务同步规范键及未删除分项任务标题，递增资产和受影响任务锁号，审计旧名与新名。目录 Outbox、已有 NAS 目录和版本文件不重命名；后续提交文件使用新名称及原目录。无表结构变更，无需迁移。


### 2026-10-08 资产分项批量管理与制作调整

资产父行只用于圈定分组，批量工作区必须明确勾选实际制作分项，每次最多 100 项。分配支持统一制作人或逐项填写，按制作人分组复用原 batch-assign，每组原子提交；排期支持统一时间或逐项填写，逐项复用原任务排期接口，未改动项跳过。任一组或任务失败即停止后续写入，展示已保存、失败待核对和未执行项，禁止直接重复发送；关闭刷新后重新选择。不自动确认开工。

新增 POST /shot-grid/projects/{projectId}/asset-items/production-adjustments，复用平台响应、项目管理范围、任务编辑权限及受控调整事务。每项携带任务、父资产、分项三份乐观锁；仅活动父资产及有稳定名称的活动分项，在 not_started/in_progress/revision 且无未完成或失败待重试提交时允许调整。任务制作要求与优先级需 task:edit，分项说明/备注及追加参考资料另需 asset:edit。普通改派仅 not_started 允许；返修交接走既有独立接口。整批任一校验失败回滚，任务锁递增；说明/备注变更才递增分项锁，父资产锁及目录快照不变，全部调整留存同事务审计。参考文件复用 shotgrid_task_reference，必须本人上传并拥有，追加保留已有引用，每项最多 5 个、单个 20 MiB。无新增表或迁移。

批量反馈、复核和返修追加问题复用既有版本审核接口，目标始终是所选分项最新版本；父资产不能作为反馈目标。审核仍重读上下文并使用版本锁、草稿与携带问题门禁。人员泳道和任务甘特共用分项快捷入口：排期、确认开工、改派、制作要求及参考资料调整、反馈复核、返修追加问题、任务与分项详情。点击重读后端可操作项，跨项目或详情切换隔离迟到响应，写入成功刷新当前列表和排期图。


### 2026-10-08 资产状态与阶段操作对齐

兼容扩展：资产制作分项未建立任务且制作分项名称为空白时派生 `pending_info`（待完善）；名称齐备且未建立任务为 `unassigned`。沿用稳定名称校验，说明、备注、图片等可选内容不影响完整性，已有任务不退回待完善。SQL 分页筛选、列表、详情及父级汇总使用相同判定；`itemStatusCounts` 新增固定非负整数键 `pending_info`，共九键。聚合顺序为 revision → reviewing → in_progress → preparing → pending_info → unassigned → pending_schedule → not_started；全部活动分项完成才为 completed，无活动分项仍为 unassigned。只扩展读取派生状态，不修改任务状态、数据库表、权限和事务，无需迁移。

资产父行按汇总提供完善信息、分配制作人、设置排期及选择分项开工入口；父资产仅圈定分组，操作必须进入详情或工作区明确选择实际分项。分项操作列按当前阶段优先显示完善信息、分配制作人、设置排期、确认开工，保留有权使用的辅助操作。完善信息复用原分项编辑表单；按钮继续取 allowedActions 与平台权限交集，排期继续复用项目管理范围、活动目标和原任务排期 API。


### 2026-10-08 资产开工入口须先有完整排期

资产父级列表 SQL 的可开工分项统计、详情分项 allowedActions 与前端开工按钮均要求任务仍为 not_started 且 expectedStartTime/expectedEndTime 齐全；权限、有效制作人和稳定分项名称等原门禁保持不变。缺少任一时间时优先显示设置排期，不显示确认开工；完整排期后显示确认开工，可保留调整排期。父资产仅在有已排期可开工分项时显示选择分项开工；混合状态只允许选择其中合格分项。表格、卡片、类型看板、资产详情及排期快捷操作复用同一判定，不因当前日期到达而自动开工。读取派生条件与已有开工服务 SG_TASK_SCHEDULE_REQUIRED 门禁对齐，无数据库迁移。


### 2026-10-08 资产制作人任务入口

资产分项 allowedActions 增加 task.work，与镜头制作人入口对齐：项目可写且存储就绪、资产和分项活动、分项名称齐备、当前用户为有效受派 creator，并有 task:query 与 version:add 权限，任务处于 in_progress/revision/pending_review 时返回。前端分别显示去做任务、去修改、追加审核文件，复用任务详情抽屉；人员泳道及甘特同步复用分项动作。此入口只导航，实际提交与失败重试仍由原任务和版本接口复核身份、状态及版本；不允许制作人自行开工，不扩大管理权限，无迁移。


### 2026-10-08 资产待审核入口

父资产存在 reviewing 分项时向具备审核与查询权限的管理人优先展示审核入口；点击重读活动分项 allowedActions，单个合格分项直达审核单，多个先选择。分项 task.review 对齐镜头 version:review、version:query、reviewList:query 交集，不把 note:add 作为查看审核入口的额外条件；实际反馈、审核写入仍由原接口独立授权。版本详情的 autoReviewList.reviewListId 为审核目标，必须核对版本 taskId，不以 versionId 替代审核单。待审核与待开工混合时，开工明确标注选择分项开工及数量，仅作用于合格待开工分项。无新接口或迁移。

### 2026-10-08 资产分项状态筛选

资产列表 `assetStatus` 查询按活动且未删除分项的对应状态计数大于零匹配，不再仅比较父资产优先状态；包括 completed，任一已完成分项即可命中。无活动分项的资产继续归入 unassigned 筛选。过滤在计数和分页前执行，父资产不重复，返回的父级 assetStatus 和完整 itemStatusCounts 仍保留原聚合语义；不改变任务状态、权限范围、分项加载或数据结构，无需迁移。


### 2026-10-09 NAS 项目目录冲突与人工重新检查

项目初始化及项目级 reconcile_directory 不再合并已有无主目录。Worker 在事务外 NAS I/O 中，为本次新建的项目目录独占写入 `.shot-grid-project-owner`；标记使用项目 ID、冻结路径及存储绑定创建时间的 SHA-256 作为归属身份，不随操作重试变化。已有目录仅在标记完全一致时允许修复初始目录树；缺失、空白或不同标记均以 `SG_STORAGE_PROJECT_DIRECTORY_CONFLICT` 终止，不自动重试、不覆盖、不清空、不自动接管空目录。检查与 mkdir 竞争失败时仍须验证归属。创建目录后、标记写入前进程中断会失败关闭，须人工处理，不按空目录推断归属。

项目存储面板展示冻结目标路径、复制路径、手动备份或重命名提示及“重新检查并初始化”。复用现有项目重试权限、原因、lockVersion、幂等与审计，新增 reconcile_directory 记录并由原 Leader Worker 执行；重新检查不代表即时成功，需刷新存储状态确认。数据库创建受理与 NAS 初始化成功须明确区分。历史未标记目录不自动补标记；已就绪项目的普通动态目录操作保持原行为，项目级重新初始化仍需人工核对旧目录。不增加 API、数据库表字段或迁移，不提供强制覆盖或自动备份。


### 2026-10-09 项目创建前 NAS 路径检查

扩展原 POST /shot-grid/storage-roots/{storageRootId}/project-path-preview，复用登录、project:add 权限及平台可选健康根目录契约，无新权限或迁移。请求增加 checkNas（默认 false）；响应保留 pathConflict 表示平台数据库占用，增加 nasPathStatus（not_checked/available/exists/unavailable）和安全 nasCheckMessage。普通输入预览仍只计算路径并查数据库，点击创建或重新检查才查真实 NAS。仅使用服务端已配置根目录与规范化项目名推导路径，释放只读数据库事务后在线程中读取；复用 UNC 映射、CIFS 校验、路径范围和符号链接/重解析点检查。超时停止等待，拒绝把无权限、网络故障或同名文件当成可用路径；不创建、覆盖、删除目录或写归属标记。

创建窗口每次提交均重新检查，不复用缓存的可用结果；检查通过才上传附件并提交创建。冲突或不可用时保留全部表单内容，展示完整路径、复制路径和重新检查入口；重新检查成功不自动创建，须继续点击创建。变更项目名或根目录使旧检查失效，关闭/卸载隔离迟到响应。预检查不预留目录，创建事务的数据库唯一性和后台 Worker 目录归属校验仍负责处理检查后的竞争；不自动覆盖既有目录。


### 2026-10-12 项目成员多角色

- 同一成员可同时具有 `director` 与 `creator`；`sg_project_member_role(project_id, user_id, project_role)` 是唯一授权事实来源，`sg_project_member.project_role` 仅为兼容投影（director 优先），不得用于权限、制作人筛选或平台角色依赖判断。
- 新增、恢复、编辑和项目初始成员使用非空 `projectRoles` 数组；兼容旧 `projectRole` 单值请求，两者同时传入拒绝。响应增加 `projectRoles`，项目身份增加 `myProjectRoles`。筛选按“包含角色”处理，不能连接产生重复成员或分页总数膨胀。
- 增加管理身份不影响制作任务；仅撤销 creator 时检查活动任务。撤销 director 或移除成员必须在项目锁内至少保留一名活动管理人。平台受管角色按所有活动项目的角色并集增量同步，原有来源标记、数据范围、缓存失效与审计边界保持。
- 双角色同时有管理和制作能力，但提交版本/重试仍只能操作本人受派任务；拥有跨项目范围也必须保留真实活动成员角色，无成员身份不能伪造 creator。
- PostgreSQL 新迁移 `20261012_37` 接续 `20260930_36`，回填全部旧成员（含已移除）；存在多角色或缺失角色时禁止降级。发布须先备份、停止旧版写服务、升级数据库并同时更新前后端；不允许新旧写服务混跑。


### 2026-10-12 项目创建者保护

- `sg_project.creator_user_id` 固定保存创建者用户 ID；创建项目时自动加入创建者并授予 director，与请求指定的初始成员角色取并集。审计 create_by 保持原语义，运行时不按账号名称推断身份，不增加绕过权限或数据范围的通道。
- 成员响应增加 `isProjectCreator`；查询按创建者、管理人、加入时间及用户 ID 排序。概览和完整成员列表共用组件，创建者显示标识、隐藏移除，编辑时 director 不可取消，仍可增减 creator（撤销 creator 继续受活动任务约束）。
- 后端新增、恢复、编辑与移除均在原项目协调锁内检查；移除创建者或提交缺少 director 的角色集合返回 409 `SG_PROJECT_CREATOR_PROTECTED`，跨项目管理员也不能绕过。未提供转交接口；创建者身份不可由普通项目编辑修改。
- PostgreSQL 迁移 `20261012_38` 接续 37：按创建账号和创建时成员记录匹配唯一历史用户；无法确认则保留空值，不猜测或授予权限。已确认创建者若被移除或缺少 director 则拒绝迁移并回滚，需先核对。降级仅移除身份字段，保留成员及角色，降级后不再有创建者保护。


### 2026-10-13 镜头与资产强制永久删除

- 沿用 `shotgrid:shot:forceDelete`、`shotgrid:asset:forceDelete` 独立权限和原 batch-force-delete 接口，不新增使用者选项。列表当前行的普通删除之后显示强删，无需选择复选框；资产只删除父资产及其全部制作分项。弹窗使用 Element Plus Form 显式校验原因，保持 `lock-scroll=false`，避免本地 Chrome 滚动条引发布局抖动。
- 登录、动作权限、项目 director/全部范围、生命周期、目标归属、lockVersion 和项目协调锁仍生效；强删允许目录未就绪，禁止目录迁移。普通删除规则不变。
- 同一数据库事务冻结独占 NAS/平台文件清单、建立 `sg_target_purge` 与路径占用、物理删除目标业务图及历史、写独立操作审计。包括已归档或逻辑删除的资产分项；共享审核单只移除目标内容，空审核单删除；其他镜头的编号和文件不变。其他镜头的资产需求保留来源并解除匹配。仍被其他业务引用的文件保留，归属不明确或在保留期的文件拒绝清理。
- 目录、版本发布、媒体、最终交付有执行中的 I/O 时拒绝本次删除，租约过期也不代表 I/O 已停止。这四种 Worker 禁止自动接管过期执行态；需管理员确认旧进程与 I/O 全部退出后按精确任务人工恢复，不能仅按租约时间重置。
- Leader 目录调度链处理目标清理：短事务领取、事务外 NAS I/O、owner/attempt/有效租约门禁回写。失败保留路径占用；failed/retry_wait 可授权重试。processing 过期不自动接管，前端提示联系管理员处理。
- PostgreSQL `20261013_40` 接续 39，初始化 SQL 同步；身份写入触发器覆盖创建、导入、改名与重编号。原冻结目录及当前同号/同名身份一直占用到全部清理成功，届时允许新 ID 重建并重新上传同名文件。强删服务检查迁移门禁，未升级返回 `SG_TARGET_PURGE_UPGRADE_REQUIRED`。不承诺 MySQL 支持。
- 状态接口 GET `/shot-grid/projects/{projectId}/target-purges`，必填 `targetKind`，支持 `purgeId/unfinishedOnly/pageNum/pageSize`；POST `/{purgeId}/retry` 使用同项目、同实体强删权限。公开响应不含实际根路径/文件清单。列表加载、详情删除返回和刷新恢复清理状态；清理中同编号不可复用。
- 升级必须先停止并排空全部旧 Worker，再执行 40 并启动全部新 Worker；严禁旧版本与新版本混跑。升级不执行历史已逻辑删除目标的追溯物理清理。迁移回退不会恢复已删除业务，存在未完成清理时拒绝降级。
- 当前仅实现并执行定向测试；业务库尚未执行 40，真实 NAS 删除—同号重建—同名上传闭环未验收，不能视为生产启用完成。详见 `docs/superpowers/plans/2026-10-13-force-delete-permanent-verification.md`。


### 2026-10-13 Windows 永久清理修复

Windows 不得直接绕过 `rmtree.avoids_symlink_attacks` 检查。Windows 分支从卷/UNC共享根开始以 GENERIC_READ 和仅共享读锁住全部祖先目录，OPEN_REPARSE_POINT 打开并按句柄检查重解析点；递归期间持有父目录句柄，通过 SetFileInformationByHandle 标记精确句柄删除。无法获得句柄、文件被写入占用、重解析点或权限不足均失败，不降级无保护递归。Linux 沿用原安全 rmtree/CIFS 门禁。仅 FILE_READ_ATTRIBUTES 不足以阻止重命名，禁止替换 GENERIC_READ。

镜头、资产导入遇到 `ck_sg_target_purge_reserved` 应明确返回 `SG_TARGET_PURGE_PATH_RESERVED` 和清理后重新预览提示，不折叠为普通数据库冲突。真实项目16原失败队列1、2已恢复成功且占用为0；只验证这两个目录和独占文件清理，不代表同号重新上传完整E2E已完成。


### 2026-10-14 任务关联镜头附件下载

任务详情的项目归属取自 `detail.project.project_id`，不存在顶层 `detail.project_id`。任务关联镜头参考附件下载继续先执行任务详情权限与项目范围校验，再按嵌套项目 ID、目标镜头 ID 和文件 UUID 校验业务引用及平台 ACL；不增加公开地址或绕过授权。


### 2026-10-26 重新审核（PostgreSQL 41，尚未部署）

- 镜头任务与资产制作分项共用 `POST /shot-grid/versions/{versionId}/reopen-review`；权限为 `shotgrid:version:reopen` 与 `shotgrid:version:review` 交集，并锁内复核有效 director/全部范围。权限种子不自动给角色授权。已完成/归档项目、非活动或删除目标、无效制作人、非最新最终版本、未决提交或正在执行的最终交付均拒绝。
- 命令携带版本 lockVersion、taskLockVersion、reviewCycle、必填原因与 X-Idempotency-Key；项目→任务→版本→审核单/交付短事务锁顺序，原 final/completed/completed 转 pending_review/pending_review/active。只操作目标任务；资产父状态仍派生聚合。事务写 reopen 审核历史、周期和审计，提交后实时通知。原通过与已解决问题不改写；新问题绑定新周期，正式退回才对制作人发布。
- sg_review_cycle 保存周期，sg_version.review_cycle 指向当前周期；版本创建建立周期1，通过/退回关闭周期，reopen追加新周期。草稿创建携带 reviewCycle（兼容默认1），旧周期请求拒绝。重新审核期间不允许追加候选，提交预检/受理/重试/落库共用校验，退回后提交下一版本。
- sg_final_delivery 同时承担 publish/revoke Outbox，按 version_id+review_cycle+operation 唯一；validity_status 与 delivery_status 分离。重开立即使原交付 revoked，pending 发布取消，历史 published/failed 保留；新增 revoke 事件异步同步。发布中一律拒绝重开，租约过期不接管。
- 每次通过写 `FINAL/T{taskId}-V{versionNo:03d}-R{cycle:03d}/` 不可变文件及 FINAL.json；任务级 `FINAL/CURRENT-{taskId}.json` 是可原子替换的有效清单，避免资产多个分项共享目录时互相覆盖。generation 使用交付事件ID，拒绝低代次覆盖，撤销写 valid=false。历史目录不是当前有效终稿依据。
- 同任务交付按事件顺序执行：前序有效发布或撤销处于 pending/publishing/failed 时后序不执行。失败撤销可从当前版本重试，跨版本展示未完成撤销状态。Worker保留短事务、事务外I/O、心跳、owner+attempt fencing及软超时收敛；后台清单同步不假装数据库与NAS原子一致。
- PostgreSQL 迁移 20261026_41 回填首周期、扩展约束和权限；新库初始化SQL同步。存在重新审核或新目录交付记录时拒绝降级。永久清理图包含审核周期。未改 MySQL 承诺，未在业务库执行迁移。


### 2026-10-26 重新审核迁移兼容修复

应用启动的 Base.metadata.create_all 可能在 40 版数据库提前创建 sg_review_cycle。41 迁移在事务内锁表并核对字段类型、长度、时间精度、空值、默认值、主键、外键和检查约束；仅接纳结构一致的空表，保留该表并正常回填周期。不通过 DROP TABLE 或 stamp 绕过升级；已有历史数据或结构不一致时明确拒绝。新增隔离 PostgreSQL 用例覆盖启动预建空表、结构漂移和已有数据，加上迁移升降级保护共 4 项通过。用户本地业务库仅做只读核对，修复后仍需停止后端并手动重试升级；本次修复尚未提交或部署。

### 2026-10-26 旧最终交付清单冲突修复

旧失败 publish 记录若错误为 SG_FINAL_MANIFEST_CONFLICT，且源文件、旧 FINAL 文件与 FINAL.json 路径严格匹配旧布局，人工重试在任务/版本/交付行锁内将目标改为现行 T{taskId}-V{versionNo}-R{reviewCycle} 目录，并记录旧、新路径审计，同事务重置为 pending。仍复核项目管理范围、当前 final 版本和 completed 任务。非旧布局、已失效交付和 revoke 不通过此分支迁移；保留旧 NAS 文件和清单，Worker 继续校验摘要与无覆盖发布。不改表，不需要数据库迁移。


### 2026-10-26 NAS 本机打开签名

镜头表格和资产制作分项共用 NasFolderMenu。先读取鉴权版本详情并核对项目/任务/版本，单目录直接申请短时签名凭证并唤起工具，多目录才弹出选择。正常发起打开后不显示浮动提示；右键“安装／打开帮助”提供安装/更新、重试和复制，失败时显示错误及帮助。网页不推断安装状态或打开成功。

- 新增 POST /shot-grid/versions/{version_id}/nas-open-ticket，body 为 {projectId, taskId, fileId}，不接受客户端 UNC。沿用登录认证、shotgrid:version:query 和版本详情项目/任务可见性；服务端再次确认文件归属与安全目录。响应 data 为 {folder, uri, expiresIn: 60}，Cache-Control: no-store。
- 新增 GET /shot-grid/nas-opener/public-key，同样鉴权及权限控制，只返回 publicKeyXml。网页将公钥绑定到静态安装模板后下载；直接下载未绑定模板不能安装。
- 独立 RSA 私钥由 SHOT_GRID_NAS_SIGNING_KEY_FILE 指定，缺失失败关闭，不使用 JWT/传输密钥，不自动生成。PKCS1v15 + SHA256 对固定用途 SGNAS1、签发/过期时间、随机 nonce、完整目录签名。协议为 shotgrid-nas://open-v1/<payload>.<signature>。工具只信任安装时公钥，拒绝旧无签名协议、篡改、过期、错误用途、危险路径；有效期60秒，最多容忍签发时间超前5秒。本机同一用户以原子文件创建阻止凭证重放。
- 工具只打开已存在的公司 NAS 目录，使用当前 Windows/NAS ACL；正常请求直接打开，不再弹出目录确认。公钥轮换后需升级工具；离线验签无法立即撤销已签发凭证，最长60秒有效窗口。无数据库迁移、无新增角色权限。
- 详见 ../shot-grid-frontend/docs/NAS文件夹本机打开.md；本地验收不等于生产后端部署验收。


### NAS 打开入口扩展（2026-10-26）

项目存储（含文件中心嵌入面板）、文件中心正式文件、自动审核单版本行，以及任务/审核/版本详情共用的 VersionDetailCard，在原复制路径或查看审核按钮后增加 NasOpenButton。项目目录打开自身，文件入口绑定 fileId，只打开该文件父目录；审核版本行无唯一目录时选择。人工批量审核单本身没有唯一版本，需进入详情选择具体版本文件。新建项目的预览路径尚未形成项目绑定，不提供打开入口。

新增 POST /shot-grid/projects/{projectId}/nas-open-ticket：登录 + shotgrid:storage:path + ProjectAccessDependency；重新读取数据库项目存储快照，仅 ready 状态可签发，拒绝客户端指定路径，返回原签名协议及 no-store。公钥接口允许 version:query 或 storage:path，业务签名接口仍分别校验原权限；版本文件入口不扩大文件/版本可见范围。沿用现有密钥、本机工具和协议，无迁移。新按钮只在使用时挂载帮助组件，切换目标取消旧请求；正常发起不弹浮动卡。尚未部署。

### 2026-10-30 镜头先分配后完善

首次分配的任务要求快照允许为空，改派不覆盖任务补充要求。任务详情继续以 `shotProduction` 展示镜头最新制作信息，补齐后刷新即可显示；不将补充后的镜头描述回填覆盖独立任务要求。单个、批量分配复用原事务和审计；分配不自动开工或创建 NAS 目录。

### 2026-10-27 项目工作区与侧边栏筛选

- 登录默认进入授权项目列表；所有项目仅指当前账号可访问的项目。选定项目后，镜头、资产、工作台、审核和文件页面固定该项目，切换统一返回项目列表。现有会话 Pinia 保存当前项目及筛选，导航携带 projectId；退出/切换项目清空筛选，旧请求取消或隔离，不回退其他项目。
- 镜头侧边栏按集展开场次，资产按 Character/Environment/Prop 分类；制作人与预期制作周期使用 Element Plus Form 按钮校验后应用，复用现有鉴权选项接口。失败与空选项分别展示，可重试。
- 新增可选 productionFrom/productionTo 日期筛选，含首尾日，以任务 expectedStartTime/expectedEndTime 与日期区间有交集为准；未排期任务不匹配，倒置日期返回校验错误。镜头、资产、本人任务、工作台审核/提交记录及排期查询在数据库分页前筛选。资产的负责人和周期必须由同一个活动未删除分项任务同时满足。
- 本人任务新增可选 projectId/assigneeUserId，均与服务端本人及活动成员范围取交集，绝不扩大为他人任务。审核、提交查询保留原范围与权限。复用原 Controller → Service → DAO、响应与参数绑定，无表结构、迁移或新权限。
- 本次只调整现有业务文件，不新增业务目录；运行数据目录允许生成。


### 2026-10-27 本机 Windows 流程联调环境

- 当前工作目录没有 Git 元数据。本机开发服务为 PostgreSQL 15432、Redis 16379/db2、后端 9099、Shot Grid 前端 5174；不得将这些本地配置作为公司生产部署配置。
- 使用既有管理 API 新增并启用 shotgrid_admin/shotgrid_creator 角色包；仅含 Shot Grid 业务权限，未授予跨项目全部范围、平台管理权限、NAS 配置写权限或永久删除权限。项目创建/成员同步仍经过既有角色保护和事务服务。
- 根目录 LOCAL_DEV（本地联调存储（当前电脑））通过既有 Windows 共享 `\\localhost\D$\lqh\shot-grid-main\shot-grid\output\local-runtime\local-nas` 真实探测后登记。没有新增 Windows 共享或扩大共享 ACL，也没有写死 healthy 状态。它是本机磁盘上的联调存储，不是公司 NAS 验收。
- 本机 .env.dev 已开启目录、版本发布及媒体派生 Worker；FFmpeg 由当前 .venv 内 imageio-ffmpeg 提供，并配置绝对可执行路径。仍使用 Application Leader、租约和 owner/attempt fencing；没有修改工作器实现或放宽权限。Linux/生产继续遵守原 CIFS 挂载规则。
- 本地流程演示项目 LOCALDEMO / projectId=1：1 集、2 场、4 镜头、3 类资产、5 个已排期任务，admin 是项目管理人兼制作人。图片版本 1 已审核通过并完成最终交付，视频版本 2 保留待审核以便交互验证。所有内容均为标注清楚的本地演示数据。
- 已通过真实鉴权 API 验证登录、角色选项、根目录探测、项目初始化、集/场/镜头/资产创建、分配、排期、镜头与分项开工、图片/视频上传和版本发布、自动审核单、图片审核通过及最终交付；图片最终文件 SHA-256 与源文件一致。视频缩略图/代理完成且鉴权 Range 返回 206/1024 字节；匿名请求返回 JSON code=401，未返回文件（平台当前 HTTP envelope 为 200）。本轮不是完整浏览器 E2E，也不消除之前记录的 8 项扩展回归失败。
- 启动脚本位于既有 output/local-runtime/start-local.ps1，只启动缺失服务、复用数据，不安装依赖或重启已有服务。已验证重复执行保持当前进程和数据。

### 2026-10-28 本机数据库中断恢复

- 本机 PostgreSQL 于 15:05 因子进程异常码 `0xC0000135` 退出；前端、后端和 Redis 仍监听，但数据库连接被拒绝。日志未指出具体缺失依赖，不能将某个 DLL 或系统组件认定为已确认根因。故障记录保留在 `output/local-runtime/postgres-crash-20261028.err`。
- 使用原数据目录，经 `pg_ctl -w` 启动并完成 PostgreSQL 自身崩溃恢复，没有初始化、迁移、删除或回填数据。启动脚本改用绝对数据目录、进程级 PostgreSQL PATH、追加式服务日志、数据库就绪及 `SELECT 1` 检查，并验证前端代理的验证码接口；普通服务再次启动前保留旧日志，进程提前退出时报告失败。
- 已验证实际登录、用户信息、项目列表和项目详情通过 5174 前端代理返回 HTTP 200 / code 200；数据库保留 1 项目、4 镜头、3 资产、5 任务和 2 版本。脚本语法和重复执行通过，四个已有服务进程保持不变。仅代表本次恢复及接口验证，不代表完整浏览器 E2E 或系统异常已永久消除。


### 2026-10-28 镜头表格逐列编辑

- 默认基础列固定为镜头预览、镜头号、场次、时长、制作内容、计划时间、制作人、镜头状态。表头“添加列”选择已有镜头参数、台词、音效、色调、参考内容及备注，不新增任意自定义字段。展示偏好继续按账号保存；业务值不存入浏览器缓存。
- 取消独立操作列。基础信息通过单元格锚定的 Element Plus Popover/Form 编辑，读取最新详情后保留完整字段、附件及资产快照并提交 lockVersion。制作人复用分配/改派，计划时间复用排期，制作中信息修改复用原制作调整事务；状态菜单只暴露原业务动作，不提供任意写状态接口。详情、履历及删除入口保留在预览与更多菜单中。
- 制作人与预期制作周期表头筛选和侧边栏共用会话 Store；镜头页面监听变更重新查询，不因同项目筛选而重建整页。状态多选新增兼容查询参数 shotStatuses（逗号分隔的既有状态）；未知状态拒绝，多个值取并集，与旧 shotStatus 及项目/场次/制作人/日期条件取交集，在数据库分页前生效。
- 兼容扩展原 PUT /shot-grid/projects/{projectId}/shots/{shotId}：允许无冻结目录、无任何目录操作记录、无已开工任务/版本/提交记录的镜头修改 sceneId/shotNo。锁内复核活动项目与目标场次、同项目范围、制作状态、lockVersion 和编号唯一性；更新 sceneId/episodeId/shotNo/sortOrder，保持 shotId、任务、附件和资产关联。只递增镜头锁版本，审计修改前后身份。不重排其他镜头，不迁移或改写已有 NAS 目录；目录冻结或已开工继续拒绝。
- 沿用登录、shotgrid:shot:edit、项目 director/全部范围、项目协调锁、统一异常和响应；增加 allowedActions 中的 shot.editIdentity 提示能力，不增加权限码或绕过服务端校验。无表结构和迁移变更，本次仅承诺 PostgreSQL。编号上限与创建一致，为 214748364，保证排序键乘 10 不溢出。

- 本轮定向验证：前端 125 项、后端 134 项通过，相关 ESLint/Ruff 和生产构建通过（仍有大分包警告）；真实 PostgreSQL 改号/换场次/冲突/状态筛选验证完成，演示字段已恢复。完整浏览器 E2E 未执行，详见前端 docs/领域模型与API契约.md 的本轮验证记录。

### 2026-10-30 镜头右侧栏与反馈评论（兼容扩展）

- 删除镜头管理下方成果面板，点击镜头只打开右侧栏；仅保留成果展示、反馈说明、制作参考三个页签。成果逐版本显示提交日期/说明/候选，媒体按需预览；制作参考仅显示镜头与任务已有参考文字/图片，不展示路径、提示词或其他操作。
- 已核实：20260814_10 曾删除旧 sg_note_reply，自由讨论不是现有处理说明能力。新建 PostgreSQL sg_issue_comment（迁移 20261030_41），评论只追加，归属已发布 sg_note，通过 note 的 version/project 保持归属；不修改问题状态、版本号、任务或锁版本，不替代正式返修处理说明与审核确认。
- GET/POST /shot-grid/versions/{versionId}/issues/{issueId}/comments；读取要求 note:list，写入额外要求 note:comment。项目访问和有效 director/creator/all-scope 通过既有项目访问服务验证；写入沿用项目→任务→版本→问题锁，锁后复核成员、目标和归档状态，同事务写评论与审计。查询按 commentId 倒序游标分页，每次最多 50 条。
- 写入 {content, requestId}，正文去首尾空白后 1–2000 字，允许换行，不接受其他控制字符；按 issue+author+requestId 唯一，同内容重试返回原结果，不同内容返回409。服务端生成作者及时间。客户端失败保留草稿和幂等键，成功后清空；跨镜头/版本迟到响应不得写入新上下文。
- 角色菜单增加独立 note:comment；仅给已有 note:list 的活动受管 shotgrid_admin/shotgrid_creator 角色补充，其他角色不自动授权。接口身份仍以原认证、平台权限及项目范围交集为准。同步 schema、PostgreSQL 初始化 SQL、清理依赖顺序及定向测试；不扩展 MySQL。已有库升级前备份，降级若已有评论则拒绝，避免丢失讨论记录。

- 本轮验证：前端 15 项侧栏/评论组件测试及 1 项列表交互测试通过，后端 52 项定向测试及 1 项降级保护测试通过，含真实 PostgreSQL 评论持久化/幂等/范围隔离；Ruff、ESLint、生产构建通过（保留既有大分包警告）。数据库已备份并升级至 20261030_41；运行服务已重载并刷新权限缓存。完整 E2E 未执行，命令与边界见前端 docs/领域模型与API契约.md 的 2026-10-30 本轮验证记录。

### 2026-10-30 镜头分配后直接制作（替代旧开工前置规则）

- 按用户最新决定，仅镜头取消“完善信息 → 排期 → 确认开工”门禁：未分配镜头统一为 unassigned，制作内容及参考参数可空；首次分配或历史 not_started 任务重新分配时，在原分配事务内自动冻结镜头目录并创建/复用目录 Outbox。目录成功直接 in_progress，否则 preparing，Worker 成功后进入 in_progress。排期保持可选；不伪造首次排期或实际制作日期。
- 不新增表/字段/API，不需要 Alembic 结构迁移。原镜头 start 兼容接口拒绝写入并提示自动制作，allowedActions 不再返回 task.start。资产任务仍需原开工确认与排期，版本提交仍限有效当前制作人且目录就绪；权限、项目范围、项目协调锁、乐观锁、事务审计和文件安全不放宽。
- 本条取代此前镜头待完善、待排期与管理人手动开工规定；资产规则、审核/返修、普通改派与删除的状态保护不变。前端保留可选排期编辑，但不将其作为镜头下一步；制作优先进入任务。
- 存量数据使用 scripts/activate_assigned_shots.py --project-id <ID> 先预览，备份后追加 --apply；只扫描指定项目未删除 shot_video/not_started 任务，复用原分配服务以同负责人转换，不直接 SQL 批量改状态。每镜头独立事务并同事务审计，失败即停，重跑只处理剩余待开工任务；未就绪存储、归档目标、失效制作人不强行放行。回退须先停 Worker 并评审数据库备份恢复，已创建目录不自动删除。

- 本轮定向验证：后端 200 + 29 项通过（另 1 项环境跳过），前端 109 + 7 项通过，Ruff/ESLint 和生产构建通过；本地已备份并转换唯一历史待开工镜头，真实 Worker 完成目录准备、提交入口可用。未执行完整 E2E，详细命令及范围见 docs/领域模型与API契约.md 本节验证记录。

### 2026-10-30 镜头任务直接反馈（兼容扩展）

- 镜头状态展示及筛选统一把 revision 标为“反馈”、completed 标为“通过”，保留原查询值和数据库状态，不新增状态或迁移。资产状态名称不变。
- 镜头列表状态菜单、任务详情与右侧反馈页签共用 ShotTaskFeedbackDialog；当前项目可跨场次多选 1–100 颗镜头。填写共同反馈、逐镜头补充及共用参考附件；只有最新 pending_review 或 rejected 版本可发送，不允许对无版本/已通过镜头伪造返修。
- 已核实并复用 getTaskDetail、版本 review-context、既有项目 batch feedback（每次一颗镜头）及 append issue API。pending_review 发送正式问题并退回 revision；rejected 仅追加正式问题。后端 task.allowedActions 增加 task.feedback 展示能力，要求活动镜头、活动项目、director/全部范围、无未完成提交，且具备 note:add、version:review、version:query、task:query。最终写权限、项目归属和版本状态仍由既有服务在锁内验证，不新增写接口或权限码。
- 读取时冻结项目、镜头、任务、最新版本和 lockVersion；旧问题必须逐条复核，仍需修改必须填原因，已有草稿明确确认后才一起发布。草稿/历史问题保留附件与画面查看入口，禁止默认批量判定已解决。评论继续是独立讨论记录，不改变审核状态。
- 混选待审核和已退回镜头时逐镜头独立事务，不承诺整批原子性。首个失败即停止，展示已发送、未执行或结果未知；结果未知要求刷新核对，不自动重放。附件上传失败保留输入，可重试；项目切换、卸载和迟到读取隔离，发送中禁止重复点击和关闭。无新增业务目录，无本次业务数据回填。


### 2026-11-02 资产分配即制作与分项成果侧栏（替代资产人工开工前置规则）

- 按用户最新授权，资产分项分配制作人后自动进入制作流程。单项/批量分配均在原项目协调锁、资产/分项/任务锁和分配事务内创建或复用 ensure_asset_directory Outbox；共享目录已成功则 in_progress，否则 preparing，由原 Worker 完成后转入 in_progress。只启动本次分配分项，不启动同资产未选分项。计划时间、制作说明均不作为分配门禁；分项名称仍为必要的制作对象标识。
- 已核对现有 assign_asset_item/batch_assign_asset_items、DAO 的目录状态读取、目录 Worker fencing 及正式任务模型。沿用 active creator、管理范围、taskLockVersion、事务回滚与审计，不新增表/字段/API、权限码、依赖或业务目录。分配不修改资产和分项元数据 lockVersion，不伪造排期/首版基线；制作中普通改派、审核和只允许当前活动制作人提交的限制保持。
- task/asset/item allowedActions 不再暴露 task.start。正常页面无需确认开工；原资产 start API 作为旧客户端兼容路径保留原锁和确认校验，不用于新流程。历史 not_started/pending_schedule 投影保留兼容，列表常用筛选增加 preparing 并去掉旧待开工/待排期入口；revision/completed 展示为“反馈/通过”。本条取代此前“资产仍需排期与确认开工”的说明。
- 资产列表点击制作分项行、名称或缩略图打开 440px（最多 92vw）的非遮罩右侧栏。复用现有 ShotResultsPanel，以 projectId+assetId+assetItemId 隔离，保留镜头模式。三页签为成果展示（提交日期/内容/候选图片及按需预览）、反馈说明（按版本的问题/评论与历史）、制作参考（父资产、分项、任务文字及图片）。提交成果进入原任务详情，添加反馈复用原审核/追加问题入口，旧版只读。评论沿用来源版本、幂等键及未发送离开门禁。
- 侧栏校验项目、父资产、分项、任务和版本归属；不匹配停止展示，跨分项/项目/权限切换取消旧请求、忽略迟到结果。文件与评论继续原鉴权。资产文件夹暂沿用只读位置演示，不借用镜头本地模拟目录身份、不接正式 NAS；镜头本地模拟入口保持。
- 历史转换复用 scripts/activate_assigned_shots.py，新增 --target-kind asset（默认仍 shot）。先 --project-id <ID> --target-kind asset 预览，备份后加 --apply。只处理指定项目未删除 asset_image/not_started 任务，逐项复用分配服务，同负责人、独立事务、失败即停。恢复需停 Worker 并评审备份，生成的目录不自动删除，不自动迁移其他项目。


### 2026-11-02 资产间关联（本轮对齐及实现契约）

已核实 sg_shot_asset 仅描述镜头→资产，不能复用来表达资产间关系。本轮兼容扩展 PostgreSQL sg_asset_relation，来源资产→引用资产的有向资料关系，同项目复合外键、禁止自关联/重复，最多 50 项。资产下所有制作分项共用；允许互相关联但不递归展开，不形成开工依赖。createAsset 可传 relatedAssetIds 与资产同事务保存；后续独立 GET/PUT /projects/{projectId}/assets/{assetId}/relations，写入沿用 asset:edit、director/all-scope、项目协调锁、来源资产 lockVersion、活动目标校验与审计；读取沿用 asset:query 和项目访问依赖。不改变开工状态、制作分配或排期。移除关联仅移除关系，不删除资产/文件；永久删除资产通过双向 FK CASCADE 删除关系，软删除目标不展示，已归档目标保留只读标记但不可新选。读取批量使用现有分项/任务/版本摘要，成果优先 finalVersion，否则 latestVersion 明确标注未通过。查看成果继续已有版本与文件鉴权，不通过关系绕过权限。新增 PostgreSQL Alembic 20261102_42 并同步初始化 SQL；不扩展 MySQL。前端继续 Element Plus，选择器可搜索/分页多选，任务与右侧栏复用关联区域。现有目录结构不变。


#### 资产关联交付与验证（2026-11-02）

- 已实现：新建资产可选 relatedAssetIds；资产详情、任务详情和资产任务右侧栏“关联资产”可查看；有管理权限可调整。关联挂在父资产，所有制作分项共用。每个引用资产显示分类、活动分项、制作人、状态和成果入口；优先通过版本，无通过版本时展示最新提交并明确标注“未通过，仅供参考”。不复制文件，不触发开工，不建立递归依赖。
- GET/PUT 完整入口为 `/shot-grid/projects/{projectId}/assets/{assetId}/relations`。PUT 请求 `{lockVersion, relatedAssetIds}`，成功返回标准 data envelope，包含 projectId、assetId、lockVersion、canEdit、relatedAssets；relatedAssets 的 items 包含 task/version 只读摘要。写入要求 asset:edit 与 asset:query，前端搜索另需 asset:list；沿用 ProjectRoleDependency、项目访问范围和现有文件权限。移除后原资产、任务及文件保持。
- 表单采用 Element Plus Form model/rules/validate；校验失败不请求，保存 loading/重复提交拦截，失败保留草稿，409 或网络结果未知必须刷新核对。读取支持取消、项目/资产归属核验和迟到响应隔离。选择器支持搜索、分页和最多 50 项；关联本身不可选当前资产。
- 已备份本地 PostgreSQL 为 `output/local-runtime/before-asset-relations-20261102-115629.dump`（pg_restore --list 验证可读），执行 `.venv/Scripts/python.exe -m alembic upgrade head`，实库版本 20261102_42。仅新增关系表，未回填任何业务关系。重启本仓库 9099 后端，5174 前端继续运行；数据库 SELECT 1、前端代理/Redis 验证通过，OpenAPI 可见新 GET/PUT。仅证明本地服务/接口注册就绪。
- 后端实际执行：`.venv/Scripts/python.exe -m pytest -q tests/module_shot_grid/test_asset_crud_service.py --tb=short` 原回归 118 passed；新增成果优先级测试用 `-k asset_relations` 为 2 passed。启用 `SHOT_GRID_RUN_PG_TESTS=1` 后执行 `pytest -q tests/module_shot_grid/test_asset_manager_start_pg.py -k asset_relations --tb=short` 为 9 passed，均使用独立临时 PostgreSQL 数据库。迁移精度同步后单独重跑 migration 用例 1 passed，增加新建失败整体回滚断言后 create/read 用例 1 passed。覆盖来源乐观锁、权限/管理范围、无效/归档目标、自关联、跨项目复合 FK、双向删除清理和有数据拒绝降级。
- 前端实际执行（前端目录，使用本机 Node）：`node node_modules/vitest/vitest.mjs run tests/unit/assetRelations.spec.js tests/unit/shotResultsPanel.spec.js --reporter=dot` 首轮 24 passed/1 failed（新建弹窗测试缺少异步挂载等待），补齐等待后 assetRelations 7 passed；shotResultsPanel 18 passed。`node node_modules/vitest/vitest.mjs run tests/unit/assetViews.spec.js --reporter=dot` 最终 130 passed；修正旧测试误选名称按钮/隐藏列占位内容、同步反馈/通过文案，并修复 AssetTreeTable 在卸载后延迟回调重复销毁 Sortable。已有删除状态组件测试产生未 Mock 网络警告，未出现未捕获错误，未将其作为真实网络验证。
- 修改范围 ESLint --max-warnings=0、Ruff check 和 format 定向检查通过。首轮 Ruff 的测试注解与 dict 写法已修正。执行 `node node_modules/vite/bin/vite.js build --mode production` 成功，仍有既有大包警告，未提高限制或新增依赖。修改表单未使用原生 submit。
- 代码备份 `output/local-runtime/before-asset-relations-20261102-114549.zip`，额外 AssetDetailView、AssetListView、AssetTreeTable 和 service 单测原件保存在同运行目录。无 .git 元数据，无法执行有效 git status/diff；使用备份比对与新增行空白检查。未新增业务目录、未推送远程、未接入正式 NAS、未执行浏览器自动化或完整 E2E。不能把定向测试或构建成功描述为发布验收通过。
- 回退边界：有关系数据时迁移拒绝 downgrade；需先停止应用/Worker、备份并评审恢复，不允许通过直接删除关系数据强行降级。

### 2026-11-02 镜头连续提交与完成后直接反馈（替代旧限制）

- 镜头任务 pending_review 时，制作端默认提交下一轮版本，不再默认追加同轮候选；无需等待制片或总监审核。共用提交服务 targetVersionNo 省略表示 new_round，可在 in_progress/revision/pending_review 执行预检、受理、失败重试和发布；显式 targetVersionNo 的旧同轮追加契约继续兼容。资产前端仍保持既有同轮追加行为。服务端编号以实际保留序列为准，前端预计编号不作为路径或版本身份。
- 新版正式发布事务才将前一待审核版本的自动审核单归档、推进旧版本和旧审核单锁；旧文件、候选、意见草稿和审核记录保留，旧版状态仍记录其最后状态，不伪造退回或通过结论。任务保持 pending_review，新轮自动审核单 active。原最新版本校验及未完成提交门禁阻止旧审核操作污染新轮次；发布失败事务回滚，旧轮次不提前归档。新轮次提交若有未关闭历史问题必须逐条携带处理说明，继续反馈快照/幂等/锁版本校验；同轮追加不重复处理问题。
- 复用 POST /versions/{versionId}/additional-issues 支持最新 final/completed 镜头直接正式反馈，前端镜头任务反馈弹窗支持与待审核/返修镜头跨场次混选。服务端在原项目→任务→版本锁内复核 director/all-scope、额外 version:review 权限、当前项目/集/场/镜头活动状态、最新版本、lockVersion 和无正在受理提交；仅新增问题可触发，编辑历史问题不触发重新制作。写问题、附件引用、版本 final→rejected、任务 completed→revision、版本/任务锁及审计在同一事务提交；原制作人不变，原通过审核动作保留。普通评论接口不变，不改变状态。
- 完成后反馈保留已 published 的历史交付；pending/publishing 交付在同一事务置 failed（SG_FINAL_DELIVERY_REOPENED）、递增 attempt、清除租约，旧 Worker 无法以原 owner/attempt 回写。已经进行的 NAS I/O 不能硬中断，可能留下历史文件，不能把目录残留当作当前已通过结果。新轮再通过时，V002 及以后使用 FINAL/FINAL-Vnnn.json，V001 保留 FINAL.json；路径适配器只接受原 FINAL.json 或与当前版本号严格匹配的清单，不覆盖旧交付文件和清单。数据库指向当前审核版本；正式 NAS 操作仍走既有 Worker 和路径校验。
- 制作任务和列表提供“继续提交新版本”；不依赖选中最新历史版本才能看到镜头提交入口。未完成提交恢复和原草稿保护继续有效。已返修的历史交付显示为历史资料，不再提供旧最终版本重新发布按钮。
- 创建后直接分配沿用已实现的自动目录准备，不强制制作内容、时长、计划时间或参考资料，不新增确认开工步骤。目录由系统自动准备，未就绪时不伪造可提交；目录就绪即可由当前活动制作人本人提交，管理人不能代提交。已通过任务收到正式反馈前不允许绕过完成状态自行提交。
- 本次与现有 VO、Controller、Service、DAO、PG 状态约束、审核动作、文件引用及最终交付租约逐项对齐：无新 API、权限码、表字段、迁移或业务目录。新增隔离 PG 测试位于现有 tests/module_shot_grid。旧版回退代码前应停止新提交和 Worker 并备份；已发送正式反馈和历史记录不得通过回退代码删除。

本轮验证与交付记录：
- 后端：`.venv/Scripts/python.exe -m pytest -q tests/module_shot_grid/test_version_submission_service.py tests/module_shot_grid/test_review_service.py tests/module_shot_grid/test_shot_crud_service.py tests/module_shot_grid/test_task_service.py tests/module_shot_grid/test_final_delivery_path_adapter.py --tb=short`：383 passed、12 skipped（既有不适用参数组合）。首轮 3 失败为旧“待审核禁止新轮次”断言及旧夹具缺少版本状态字段，更新后通过；日志 continuous-shot-backend-tests.log。
- 隔离 PostgreSQL：设置 SHOT_GRID_RUN_PG_TESTS=1，运行 test_continuous_shot_pg.py 最初 5 passed；补充旧 Worker fencing、已交付保留、关闭项目/归档镜头保护后，用 `-k 'complete_feedback or project_closed or shot_archived'` 为 3 passed / 4 deselected（含 1 个加强后复测），共 7 个不同用例有通过证据。覆盖空制作说明/无排期直接分配、自动目录准备、本人连续 V001→V002、旧版审核拒绝、通过后并发反馈、返修 V003→待审核再交 V004、历史问题处理说明不遗漏、再通过与分版本交付清单；同时验证创作者/无审核权限/过期锁/坏附件失败不改变已通过状态。初轮夹具的空值持久化、目录适配器方法名和审核候选参数不完整已修正。随机测试库均由夹具清理，没有修改本地演示业务数据。NAS 检查和发布 I/O 使用测试替身，该链路不是实际上传或真实 NAS E2E。日志 continuous-shot-pg.log、continuous-shot-pg-extra.log。
- 前端：versionSubmissionPanel/versionWorkspace/shotTaskFeedback/taskViews/shotViews 五文件首轮 218 passed；新增快捷入口和交付历史提示定向首轮 4 passed / 1 failed（只读测试账号未带审核权限，交付提示位于审核区）；补齐测试权限后 reviewViews/shotViews 相关 3 passed / 132 skipped。补测有重叠，不累计为全量测试数。日志 continuous-shot-frontend.log、continuous-shot-extra-frontend.log、continuous-shot-feedback-frontend.log。已有直接挂载夹具仍提示无 router-view，不将组件验证当作浏览器 E2E。
- 修改范围 Ruff check、Ruff format --check（9 文件）、ESLint --max-warnings=0 通过；Vite production build 通过，保留既有大包警告。最终清单适配器另验证旧 FINAL.json 不变、新版本清单创建及错误版本编号拒绝。
- 已重启仅本工作区 9099 后端，复用原 PostgreSQL/Redis/5174 前端。重启前确认无 pending/publishing/committing 本地提交；启动脚本的数据库 SELECT 1、前端代理/后端/Redis 检查通过。未执行验证码登录或完整浏览器 E2E，未操作公司 NAS、远程部署或推送。
- 备份 output/local-runtime/before-continuous-shot-submit-20261102.zip，补充审核页面备份 before-continuous-shot-review-view-20261102.zip。无 Git 元数据，git status 失败；通过备份比对和新增行空白检查代替 git diff --check。无数据库迁移或业务目录新增。


### 2026-11-02 提交目录按分项与版本分层（替代平铺布局）

- 新轮次镜头文件路径为项目冻结目录下 `SHOT/EPxxx/场次号/镜头号/Vxxx/业务文件名`；场次至少三位、镜头至少四位。资产为 `ASSET/类型/资产冻结目录/分项名称__分项ID/Vxxx/业务文件名`。分项名称按既有 Windows 文件名规则清洗并截取 80 字符，稳定 ID 防止字符清洗、长名称或归档后复用名称导致不同分项混放。版本号仍以每任务的保留序列分配，不使用版本数据库 ID。
- 同轮全部候选同目录、不同轮次隔离。旧提交快照、旧版本、文件引用均不迁移、不删除；失败重试/正式提交只允许本任务精确匹配的新旧两种布局。旧版本显式追加读取该版本冻结原文件目录，不能把同一历史轮次拆到两个布局。新轮次一律新布局。
- 复用原提交 Outbox 和 Worker，不增加 API、表字段、迁移、权限或业务目录。版本受理冻结实际文件相对路径；事务外发布在既有项目根中逐段创建新目录，每段检查 reparse/symlink 与根目录约束。原 SHA-256、无覆盖、幂等、租约及 owner+attempt fencing 不变。原目录准备 Outbox 仍兼容 VIDEO 与父资产快照；不会为历史空目录自动执行删除。
- 最终交付由原文件父目录派生，因此新布局交付位于对应 `Vxxx/FINAL/`，旧布局仍按原位置；分版本交付清单策略保持。目标永久清理在原精确归属基础上同时核对该镜头 VIDEO 旧目录及 SHOT 四级新目录，不扩大到整场/整集；其他目标路径冲突仍失败关闭。这里只修改代码与隔离测试，不对本地演示或公司 NAS 执行实际删除。
- 版本文件 VO 增加可空 `folderRelativePath`，仅原始 review_media 投影冻结项目目录名与业务相对文件夹，拒绝异常路径，不暴露磁盘/容器绝对路径。原 nasPath、受保护下载与预览不变。镜头侧栏和版本文件入口在本机 DEV 优先使用该字段，通过 `demo-layout/<base64url相对目录>` 映射已配置的本地演示根；打开器再验证层级、目录段、磁盘根约束与链接。无字段旧响应继续兼容 ID 演示协议。非本机环境仍只预览 NAS 位置，不改变当前用户要求的本地模拟边界。
- 本次为兼容扩展；事实已核对 Submission/File DO、DAO 任务与文件归属、VO、审核交付适配器、目录和清理适配器、前端文件权限及现有打开器协议。无需数据库迁移；不搬移已有业务文件，回退代码前需停止提交/发布 Worker 并保留本次新布局的读取能力，不能以旧适配器继续消费新路径快照。


本轮验证与本地交付：
- 后端定向命令 `.venv/Scripts/python.exe -m pytest -q tests/module_shot_grid/test_version_submission_service.py tests/module_shot_grid/test_version_publish_path_adapter.py tests/module_shot_grid/test_final_delivery_path_adapter.py tests/module_shot_grid/test_target_purge_path_adapter.py tests/module_shot_grid/test_storage_path_adapter.py tests/module_shot_grid/test_version_nas_path.py --tb=short`：最终 152 passed / 2 skipped。初轮遗漏旧镜头目录快照必填校验已补回。随后新增版本内 FINAL 和精确镜头清理用例，对 final_delivery_path_adapter / target_purge_path_adapter 两文件定向复测 13 passed（与前一组重叠）。review_service / version_publish_worker_service 另 112 passed / 12 skipped。日志 version-folders-tests.log、version-folders-review-tests.log。
- 隔离 PostgreSQL（SHOT_GRID_RUN_PG_TESTS=1）：continuous_shot_pg / append_candidates_pg / target_purge_graph_pg 的 complete_feedback、real_append_preserves、exclusive_files 最终 3 passed / 14 deselected；新增 two_asset_items、legacy_pending 两例通过。共 5 个不同场景验证镜头连续轮次及新旧目录精确清理范围、两个资产分项各自 V001/V002、旧目录追加、引用与审核保护。初轮两个连接超时和补测夹具 task_id 名称错误分别经重跑/修正后通过；随机测试库均清理，未修改演示业务数据。日志 version-folders-pg-final.log、version-folders-assets-pg.log。PG 发布 I/O 为替身；临时本机文件适配器测试另验证真实字节复制、SHA-256、重入无覆盖和目录隔离，不是公司 NAS 验收。
- 前端 `node node_modules/vitest/vitest.mjs run tests/unit/folderOpener.spec.js tests/unit/versionFolderButton.spec.js --reporter=dot` 23 passed；更新入口字段断言后，versionFolderButton / shotResultsPanel 两文件 21 passed（重叠不累加）。修改范围 ESLint --max-warnings=0、17 个 Python 文件 Ruff check 和 format --check 通过。Vite production build 成功，保留既有大包警告。日志 version-folders-frontend.log、version-folders-entrances.log、version-folders-build.log。
- Windows 打开器 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File shot-grid-frontend/public/shot-grid-folder-opener.ps1 -Mode Test` 验证 3 个命名目录、5 个非法层级及旧协议/NAS 2 合法、24 非法请求。已备份旧 exe 并更新当前用户安装，保留原 DemoRoot。通过运行脚本 verify-version-folders-demo.ps1 真正在既有 folder-preview/目录分层演示 下创建镜头 V001/V002、资产正面 V001/V002 和侧面 V001 演示副本，没有打开 Explorer、连接公司 NAS 或写业务记录。此前直接在 PowerShell 7 编译演示源码因引用差异失败，改用 Windows PowerShell 5.1 脚本验证成功，不把失败输出当作目录创建证据。
- 本地重启前确认没有活动提交；仅重启本工作区 9099 后端。启动脚本使用 PowerShell 7（Windows PowerShell 5.1 不能解析其现有编码），最终数据库 SELECT 1、Redis、前端代理检查成功。运行中 OpenAPI 已包含 folderRelativePath，三个相关前端资源 HTTP 200。未执行浏览器自动化、真实 HTTP 上传或完整 E2E。
- 无 Git 元数据，git status 失败；代码备份 before-version-folders-20261102.zip，打开器备份 before-version-folders-opener-20261102.exe 均位于 output/local-runtime。按备份比对新增行无尾随空白，保留全部原目录与业务文件；无数据库迁移、远程发布或推送。


### 2026-11-02 交付清单默认隐藏（Windows）

- 最终交付保留原 FINAL.json / FINAL-Vxxx.json 名称、内容、数据库路径与校验规则；文件与清单发布并验证成功后，Windows 设置 FILE_ATTRIBUTE_HIDDEN，保留其他属性。重入复用与文件竞争恢复路径也设置隐藏。媒体成果不隐藏，隐藏失败仅记录通用警告，不把完整交付误报为失败。
- 该展示属性仅适用于 Windows 后端/本机示例；Linux/CIFS 不声称具有相同隐藏行为。资源管理器启用“隐藏的项目”时仍能看到记录。没有删除记录、改迁移、改变文件权限或新增业务目录。
- 已隐藏本地“目录分层演示”镜头及资产正面分项 V002/FINAL 中的两份清单，并验证隐藏标志和 SHA-256 未变。`python -m pytest -q tests/module_shot_grid/test_final_delivery_path_adapter.py --tb=short` 6 passed，覆盖新发布/重复发布隐藏、清单不变及媒体可见；修改两文件 Ruff check --fix 与 format 通过。确认无活动提交后仅重启本工作区后端，启动脚本数据库/Redis/代理检查通过。未进行正式 NAS 或浏览器完整 E2E。
- 代码和文档备份 output/local-runtime/before-hide-final-manifest-20261102.zip。无 Git 元数据，按备份比较新增行空白。

### 2026-11-03 定稿只读摘要与列表筛选

- 现有镜头/资产列表查询兼容增加 hasFinal: bool | None，分页前按同任务、同项目版本 final 或既有 sg_final_delivery.approved_time 过滤；含重新反馈后的历史通过记录。未更改 Controller 认证、接口权限、项目访问范围或任何写入流程。
- common_vo.ShotGridApprovedVersionModel 为只读摘要，镜头列表/详情与资产分项新增 approvedVersion。资产父级 approvedItemCount 统计有通过记录的活动未删除分项，finalizedItemCount 仅统计当前 completed、版本 final、交付 published 的活动分项。旧状态计数不变；未知归档不等于已完成。未新增数据库字段、索引、迁移或接口路径，PostgreSQL 为实际验证范围。
- 版本详情/最终交付原契约仍为 source.parent/FINAL，前端只据此构造已归档版本的本地模拟目录入口。文件权限、业务引用、SHA-256、只读摘要范围及 Worker fencing 不变。正式契约同步 shot-grid-frontend/docs/领域模型与API契约.md。
- 验证：CRUD DAO/Service/VO 首轮 282 passed；增加 lateral 后更新旧数量断言。后续 DAO/Asset Service/Router 159 passed，既有资产关联两路由旧断言 12 与实际 14 不符，补齐关联接口权限断言后 Router 16 passed；非全量后端测试。Ruff 通过。当前演示 PostgreSQL 使用只读事务验证筛选分区数量与投影、计数关系，无业务写入。未执行完整 E2E 或 NAS 验收。日志与备份见 output/local-runtime/final-display-*。


### 2026-11-11 每日多平台记录与产出统计（实施对齐）

- 兼容扩展：在现有 DO/VO/DAO/Service/Controller 及 Vue/Element Plus 目录增加每日记录，不新增业务目录。PostgreSQL 迁移 20261111_43，基于 20261102_42；初始化 SQL 同步。新增 sg_daily_record，task_id/project_id 复合 FK 与任务删除级联；平台积分 NUMERIC(16,4)，实际 0 不回退估算，日期用 DATE，时间沿用 TIMESTAMP(0)。
- 新权限 shotgrid:daily:write（本人记录读写）和 shotgrid:daily:stats（项目统计），迁移将已有任务列表角色授予本人记录、已有排期角色授予统计；仍由当前项目成员/管理范围及当前制作人校验，角色不跨项目扩大。菜单由既有导航查询返回。现有会话需刷新权限或重新登录。
- 一天/任务/本人/平台/账号/模型/类型一条累计记录；不同平台独立，单次保存最多 30 行原子事务，UUID 防重复、lockVersion 防覆盖；记录可补填、改正、作废，保留历史，不设日报审批。只关联已有任务，不产生任务/版本/文件。
- 明细与统计按项目和日期（含首尾，最大 366 天）查；积分按平台分组，不提供跨平台积分总数；生成图片和视频分开。提交轮次与通过任务数从版本/交付事实单独计算，不与记录 join，不归因到平台。通过统计表示期间曾通过的不同任务，不是当前完成数量。
- 截图上传不作为首版步骤，备注选填；不接外部平台自动扣费。仅支持 PostgreSQL；本轮验证结果在实施后追加。


实施与验证结果（2026-11-11）：
- 已新增每日记录 /daily-records 与产出统计 /production-statistics；菜单来自 sys_menu 和现有 navigation，工作台及本人任务有快捷入口。当前项目范围继承路由和会话。多平台行一次保存，实际积分/单次估算二选一，免费填 0；支持补填、修改、作废、修改历史和 Excel 导出，截图及审核不作为填写步骤。常用选择在当前用户/项目会话中保留。
- 统计包含按平台总量、平台/人员/图片视频类型分组；提交轮次按 submitted_time，期间曾通过任务按 approved_time 去重，与消耗记录不 join、不按平台归因；平台筛选不改变这两个任务指标，界面已注明。实际与估算分别标记；不同平台不合计。
- 新旧代码对比备份 before-daily-records-20261111.zip；数据库备份 before-daily-records-*.dump；已有本地演示库由 42 正常升级至 43，保留原业务数据。未对正式环境或 NAS 操作，未新增演示消耗数据。
- tests/module_shot_grid/test_daily_records.py：3 passed，含两个真实随机隔离 PostgreSQL 测试，覆盖精度/免费0、本人/他人/项目范围、伪造统计权限但无管理角色拒绝、UUID 并发重放、唯一键、乐观锁、历史、作废、整组失败回滚、日期过滤；临时库清理。导航 DAO/Service 6 passed；旧元数据测试的 35 表及“所有业务 FK 均 RESTRICT”断言已落后于评论/资产关联等扩展，补为38表并精确列举允许级联的关系后 metadata 15 passed。没有放宽业务写权限。
- 前端每日记录组件3例通过：Element Plus Form 必填失败不请求、多平台一次保存/实际0/失败保留/UUID稳定、统计首屏读取。routeRegistry 3例通过，覆盖新白名单。组件夹具有既有重复注册及非 router-view 守卫警告，不等同真实浏览器路由验收。
- 修改范围 ESLint、Ruff 检查通过；format 发现 schema.py 长行后已格式化。业务前端构建成功，保留既有大包警告；最后局部表单 prop 调整由组件测试验证。
- 本机服务重启后数据库/Redis/前端代理通过，运行中 OpenAPI 有3条新增路径（4个操作），新页面 Vite 模块 HTTP200。未登录请求按现有平台协议返回HTTP200、业务code401，并未获得记录。只读验证真实角色菜单：admin有记录/统计，creator_demo仅每日记录；本月示例源版本自动返回4次提交、2个曾通过任务。现有会话需重新登录刷新权限。
- 未运行全量E2E、人工浏览器验收、真实平台积分API或正式部署；没有读取真实平台账单，平台名称自由填写，大小写/多余空白规范化，同平台别名暂由团队约定。日期范围最多366天，明细50条一页，单次保存最多30行，导出最多10000条且逐页查询（导出期间有他人修改时不是数据库快照）。
- 2026-11-03交接压缩包仍为当时快照，不含本次功能；下次交接须重新打包当前代码及43迁移。
