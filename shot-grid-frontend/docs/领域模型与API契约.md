# Shot Grid 领域模型与 API 契约

## 1. 文档状态

| 项目 | 内容 |
| --- | --- |
| 版本 | v2.4 |
| 状态 | 2026-08-20 冻结“创建/导入生产对象 → 独立委派生成唯一任务 → 制作 → 提交不可变版本 → 审核 → 完成/返修循环”契约；镜头/资产 v2 模板与手工创建均不接收制作人，导入和创建不得生成任务；生产履历改为六阶段投影，继续区分确认事实与推断事实。第一版只聚合既有正式表，不新增领域事件表，不伪造缺失的旧委派、改派或开始历史 |
| 建立日期 | 2026-08-07 |
| 最近修订 | 2026-08-20 |
| 数据库 | PostgreSQL |
| 业务前端 | 独立 `shot-grid-frontend`，工程配置参考 `ruoyi-fastapi-frontend` |
| 管理后台 | `ruoyi-fastapi-frontend` |
| 后端基座 | `ruoyi-fastapi-backend` |
| 产品来源 | `项目需求规格与业务规则.md`、`需求.md` |
| 历史参考 | `参考项目评估.md` |

本契约冻结“真实登录 → 选择受控 NAS 根目录并创建项目 → 初始化项目目录 → 创建或导入未分配的集、场次、镜头/资产制作分项 → 项目管理人独立委派并生成唯一任务 → 镜头及资产制作分项分别由管理人确认开工 → 制作人员线下制作 → 上传产出物 → NAS 发布 → 自动生成不可变版本和审核单 → 审核人提出来源版本问题 → 退回后制作人随新版本逐条说明处理方式 → 审核人逐条确认历史问题并检查新问题 → 全部问题关闭后确认完成”的主闭环。

若后续代码与本文冲突，必须先评审并更新契约，不能由前端页面或临时数据库字段自行改变业务定义。

## 2. 已确认的基座事实

以下内容已经从当前代码确认：

- 用户主表是 `sys_user`。
- `sys_user.user_id` 是 BigInteger 自增主键。
- 当前用户通过 `CurrentUserModel.user.userId` 获取。
- `/getInfo` 的 `CurrentUserModel.user` 使用专用 `CurrentUserInfoModel`，该安全响应模型不包含 `password`；独立业务前端还会二次投影必要身份字段，不缓存完整用户对象。
- 接口权限使用 `UserInterfaceAuthDependency`。
- 登录认证使用 `PreAuthDependency`。
- API 模型使用 snake_case Python 字段和 camelCase JSON alias。
- 分页响应字段为 `rows`、`pageNum`、`pageSize`、`total`、`hasNext`。
- 受保护文件上传接口是 `POST /common/files/upload`。
- 文件主键 `fileId` 是 36 位字符串。
- 文件业务引用由 `sys_file_reference` 表达。
- 文件业务引用会阻止误删，但不会自动授予下载权限。
- 已登记文件下载支持 HTTP Range 和 206/416。
- 平台文件表分别保存 `original_name`、`stored_name` 和 `storage_key`；通用受保护文件上传会先独立提交文件记录。
- 当前主数据库是 PostgreSQL。
- PostgreSQL 初始基线中的审计时间使用 `timestamp(0)`；Shot Grid SQLAlchemy DO 使用 PostgreSQL 方言下编译为 `TIMESTAMP(0) WITHOUT TIME ZONE` 的统一类型。
- 常规业务异常默认由统一响应工具以 HTTP 200 返回；Shot Grid 的真实 HTTP 409 等语义属于本模块需要显式实现的扩展契约。
- RuoYi 平台基座本身没有通用 NAS 根目录配置、项目目录初始化、版本文件发布到 UNC 路径或跨数据库与文件系统补偿能力。Shot Grid 已新增项目目录 Outbox Worker、目录诊断/人工重试和独立版本发布 Worker，但两个 Worker 均默认关闭，物理补偿仍未实现；不得把 Shot Grid 领域扩展描述为平台通用能力，也不得以本地临时目录测试冒充真实 UNC 验收。
- 独立业务前端已实现 Vue 3/Vite/Pinia/Vue Router/Axios/Element Plus 应用基座、自有登录页、六项本地路由白名单、统一请求与错误分流；项目、镜头和资产页已接入真实 API，并分别完成生产 Nginx 形态下的隔离子集旅程。真实工作台使用 `/shot-grid/tasks/mine`，任务详情深链 `/tasks/:taskId` 支持详情、编辑、等待开工和版本工作区；版本工作区接入 private preflight → 私有上传 → create 202、`current` 恢复、失败重试、版本历史/详情和受保护下载，版本深链 `/versions/:versionId` 归属 `reviews` 路由范围。任务工作台/版本上传也已在 fresh PostgreSQL、Redis DB 15、真实平台登录和生产前端形态下完成隔离子集浏览器旅程，版本发布阶段使用显式 `allow_local_root=True` 的本地 TEMP 适配器。资产模板与资产需求人工处理均已交付；审核详情已接鉴权 Blob 图片/视频预览、视频时间点、点/矩形/箭头/涂抹/文字批注、同任务版本 A/B 对比和退回后版本工作区入口，文件与 NAS 页面也已接真实业务 API，但二者尚无隔离浏览器旅程。真实版本缩略图文件未造夹具，任何子集都不等于真实 UNC/NAS、Range 真分段或完整系统 E2E。

## 3. 领域边界

### 3.1 本领域负责

- 项目和项目成员；
- NAS 根目录配置、项目存储绑定和目录操作；
- 集；
- 场次；
- 镜头；
- 资产；
- 镜头与资产关系；
- 镜头和资产导入批次；
- 镜头先导入后形成的待匹配资产需求；
- 镜头视频任务和资产图片任务；
- 不可覆盖的版本；
- 版本提交暂存与 NAS 发布；
- 版本文件用途；
- 跨版本修改问题、结构化批注、逐版本处理说明和逐条确认；
- 审核动作历史；
- 审核单和有序版本列表；
- 镜头与资产生产履历的只读聚合投影。

### 3.2 复用平台能力

- 用户、部门、平台角色和登录；
- JWT、Redis 会话和账号状态；
- 菜单与接口权限；
- 受保护文件、ACL、业务引用、回收站和访问审计；
- 字典、参数、日志和统一异常；
- PostgreSQL 连接、Alembic 和 PostgreSQL 初始化 SQL。

### 3.3 不进入当前领域

- 第二套用户和密码；
- 独立 Cookie 会话；
- 客户门户；
- 部门聊天；
- 在线剪辑；
- 在线图片生成或视频生成；
- 自定义实体和自定义字段设计器；
- AI 模型直接调用；
- 工时、预算和成本结算。

## 4. 核心关系

```text
sys_user ──< sg_project_member >── sg_project ── sg_project_storage >── sg_storage_root
                                      │                    │
                                      │                    └──< sg_storage_operation
                                      │
                                      ├──< sg_episode ──< sg_scene ──< sg_shot
                                      │                                  ├──< sg_shot_asset_requirement
                                      │                                  │
                                      ├──< sg_asset <── sg_shot_asset ───┘
                                      │       └──< sg_asset_item ──< sg_task
                                      │
                                      ├──< sg_import_batch
                                      │
                                      └──< sg_task（镜头任务）
                                             │
                                             ├──< sg_version_submission ──< sg_version_submission_file
                                             └──< sg_version
                                                    │
                                                    ├──< sg_version_candidate ──< sg_version_file >── sys_file_info
                                                    │        └──< sg_media_derivation
                                                    ├──< sg_note（问题来源版本与候选）
                                                    │       ├──< sg_version_issue_response >── sg_version_submission ── sg_version
                                                    │       └──< sg_issue_verification >── sg_version_candidate（确认候选）
                                                    ├──< sg_review_action（含执行动作的候选）
                                                    ├──< sg_version_candidate_selection
                                                    └──< sg_review_list_version >── sg_review_list

sg_project / sg_shot / sg_asset / sg_version / sg_note
   └── sys_file_reference（业务引用与删除保护）
```

核心路径只有一个：

```text
镜头或资产
→ 分配制作人并创建唯一任务
→ 制作人员在线下制作
→ 上传主产出文件
→ 暂存提交并发布到 NAS
→ 版本
→ 自动审核单
→ 当前版本修改问题（文字和/或画面标注）
→ 退回后逐条填写问题处理说明并上传下一版本
→ 审核人逐条确认历史问题，并可提出当前版本新问题
→ 全部问题关闭后确认最终版本并完成任务
```

## 5. 通用数据规则

### 5.1 主键

- 新建 `sg_` 业务表默认使用 BigInteger 自增主键，与 `sys_user.user_id` 对齐。
- API 中业务主键使用整数。
- `fileId` 保持平台定义的 36 位字符串，不转换为业务整数。
- 导入预览令牌、请求幂等键等临时标识使用字符串 UUID。

### 5.2 审计字段

可变业务主表统一包含：

| 数据库字段 | API 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| `create_by` | `createBy` | varchar(64) | 创建账号 |
| `create_time` | `createTime` | timestamp(0) | 创建时间 |
| `update_by` | `updateBy` | varchar(64) | 更新账号 |
| `update_time` | `updateTime` | timestamp(0) | 更新时间 |
| `remark` | `remark` | varchar(500) | 备注 |
| `lock_version` | `lockVersion` | integer | 乐观锁版本 |
| `del_flag` | 不直接开放 | char(1) | `0` 正常，`2` 逻辑删除 |

时间字段与现有后端保持一致：

- SQLAlchemy DO 使用 `DateTime`。
- PostgreSQL 使用 `timestamp(0) without time zone`。
- 后端按项目配置时区生成和解释时间，API 使用 ISO 8601 字符串。
- 当前基座可能返回不带偏移量的时间字符串，前端不得自行把它当作 UTC；统一按平台时区工具解析和展示。
- 如果未来升级为带时区存储，必须作为全项目时间策略变更实施，不能只修改 Shot Grid 单表。

### 5.3 状态值

- 数据库和 API 使用稳定英文代码。
- 中文名称只由前端或字典映射展示。
- 不使用 PostgreSQL ENUM，使用 varchar + `CHECK`，避免状态升级被数据库枚举类型锁死。
- 状态修改必须通过动作接口或 Service 状态机，不能使用通用字段更新绕过。

### 5.4 删除与归档

- `del_flag = '2'` 只表示逻辑删除，不表示业务归档。
- 业务归档必须写入明确的业务状态字段，归档后 `del_flag` 仍为 `0`。
- 项目使用 `project_status = 'archived'`。
- 集、场次、镜头和资产使用 `lifecycle_status = 'archived'`。
- 新建集、场次、镜头和资产时 `lifecycle_status` 默认是 `active`。
- 任务通过任务状态机关闭，不直接用 `del_flag` 表达任务完成或归档。
- 审核单使用 `review_status = 'archived'`。
- 项目、集、场次、镜头、资产、任务和审核单不向普通用户提供物理删除。
- 已有关联任务、版本、审核或文件的对象不得直接级联物理删除。
- 已提交版本、修改问题、逐版本处理说明、逐版本确认结果和审核动作历史不得覆盖。
- 物理清理属于单独的管理员治理流程，不包含在普通 CRUD。

### 5.5 乐观并发

- 项目、集、场次、镜头、资产、任务和审核单的更新请求必须携带 `lockVersion`。
- 更新 SQL 必须包含 `WHERE id = :id AND lock_version = :lockVersion`。
- 更新成功后 `lock_version + 1`。
- 未命中时返回并发冲突，不允许最后写入者静默覆盖。

### 5.6 数据库实现与迁移交付

每次新增或修改 Shot Grid 表结构必须同时交付：

1. `module_shot_grid/entity/do/` 下的 SQLAlchemy DO；
2. 可升级、可回滚的 PostgreSQL Alembic revision；
3. 同步更新 `ruoyi-fastapi-backend/sql/ruoyi-fastapi-pg.sql`；
4. PostgreSQL 下的约束、索引、升级和回滚验证。

只新增 DO、只修改初始化 SQL 或只写设计文档，都不算数据库交付完成。JSONB、部分唯一索引等 PostgreSQL 专用实现必须明确限制在 PostgreSQL 路径，不得无意影响仓库保留的 MySQL 兼容模块。

当前 Shot Grid Alembic head 为 `20260827_23`。06 增加任务/版本/审核完整性约束；07 增加媒体派生；08 至 19 依次补齐 NAS 管理、镜头号治理、跨版本问题、媒体引用、受管角色、排序、延迟目录、审核草稿和项目永久删除；20 增加版本轮次内多候选文件、候选级媒体派生与审核选择审计，并把既有每个版本回填为候选 01，历史 NAS 路径和业务文件名不改名；21 增加审核通过后的最终版本 NAS 交付 Outbox，由 Leader Worker 异步发布 `FINAL/` 文件和 `FINAL.json`；22 将单候选版本自动设为本轮最佳并回填历史数据；23 仅更名标准任务开工菜单，不自动扩大角色权限。媒体 Worker 默认关闭：图片使用 Pillow 生成 JPEG 缩略图和网页代理，视频使用显式配置的 FFmpeg 生成 JPEG 缩略图和 H.264/AAC faststart MP4；工具缺失或解码失败必须持久化安全错误并让前端降级原媒体，不得将原文件登记为代理。生成物继续进入 `sys_file_info`、`sys_file_reference` 和候选级 `sg_version_file`，成功提交前清理半成品。该增量链仍不是完整 RuoYi 空库 Alembic baseline。

媒体派生配置使用 `SHOT_GRID_MEDIA_WORKER_` 前缀；至少需要显式设置 `ENABLED=true` 才注册 Application Leader 内部任务，视频环境还需通过 `FFMPEG_PATH` 提供可执行文件。默认缩略图最长边 480、图片代理最长边 1920、视频代理最大宽度 1280；转换期间按 `HEARTBEAT_SECONDS` 续租，数据库回写继续使用 version + owner + attempt fencing。审核列表返回 `thumbnail` 和 `mediaDerivationStatus`，版本详情返回完整派生文件角色及同名状态；前端只能优先使用真实 `proxy_media`，代理加载失败时回退主 `review_media`。

> 升级到 `20260821_16` 若返回 `SG_SHOT_SEQUENCE_NOT_CONTIGUOUS`，表示旧数据仍不是场内连续编号。必须先备份并在克隆库核对镜头、任务、版本、文件和实际 NAS 目录，再通过受控场内重排与目录迁移治理；禁止直接 `stamp`、手改 `alembic_version` 或只改数据库编号绕过物理目录。

## 6. 数据表契约

### 6.1 `sg_project`

项目主表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `project_id` | bigint | 是 | 主键 |
| `project_code` | varchar(12) | 是 | 项目代号及产出文件前缀，保存规范化大写值，例如 `LCFR` |
| `project_name` | varchar(200) | 是 | 项目名称 |
| `project_type` | varchar(50) | 是 | 项目类型代码，MVP 固定为 `ai_short_film` |
| `project_description` | text | 否 | 项目描述 |
| `aspect_ratio` | varchar(20) | 是 | 画幅，默认 `16:9` |
| `planned_duration_ms` | bigint | 否 | 计划总时长，整数毫秒 |
| `delivery_date` | date | 否 | 交付日期 |
| `project_status` | varchar(20) | 是 | 项目状态 |
| `current_phase` | varchar(50) | 是 | 当前阶段代码，默认 `planning` |
| 通用审计字段 |  | 是 | 见 5.2 |

项目状态：

| 代码 | 中文 |
| --- | --- |
| `preparing` | 筹备中 |
| `active` | 进行中 |
| `completed` | 已完成 |
| `archived` | 已归档 |

约束：

- `project_code` 只允许 2—12 位大写 ASCII 字母或数字，在 `project_status <> 'archived' AND del_flag = '0'` 的记录中大小写不敏感唯一。
- `project_code` 同时是业务文件名前缀；不再维护可与其漂移的第二个 `file_prefix` 业务字段。若从 v0.4 草案或历史数据迁移，必须先验证二者一致，再迁移到 `project_code`。
- 系统可以根据项目中文名称提供首字母建议，但创建人必须确认并保存，上传时不得临时重新推导。
- `project_type` 使用稳定代码；MVP 只接受 `ai_short_film`，中文显示和 NAS 目录快照为“AI影视短片”。
- `aspect_ratio` 只允许 `16:9`、`21:9`、`2.39:1`、`9:16`、`1:1`。
- `project_status` 只允许 `preparing`、`active`、`completed`、`archived`；`current_phase` 只允许第 7.6 节代码。
- `planned_duration_ms >= 0`。
- 创建项目时必须在同一数据库事务中创建项目、至少一名项目管理人成员、唯一项目存储绑定和项目目录初始化操作。
- 只有 `sg_project_storage.storage_status = 'ready'` 的项目可以创建正式业务数据或提交版本；初始化中和失败状态只允许查询、重试初始化或受控撤销。
- 项目统计字段不直接存储，镜头总数、完成数、待审核数等由查询聚合。

### 6.2 `sg_project_member`

项目成员与项目内角色。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `project_id` | bigint | 是 | 关联 `sg_project` |
| `user_id` | bigint | 是 | 关联 `sys_user.user_id` |
| `project_role` | varchar(20) | 是 | 项目角色 |
| `producer_code` | varchar(12) | 条件必填 | 制作人文件名缩写，例如 `YJF` |
| `member_status` | varchar(20) | 是 | `active` 或 `removed`，默认 `active` |
| `joined_time` | timestamp(0) | 是 | 加入时间 |
| `removed_by` | bigint | 条件必填 | 软移除操作用户；仅 `removed` 时存在 |
| `removed_time` | timestamp(0) | 条件必填 | 软移除时间；仅 `removed` 时存在 |
| `create_by` | varchar(64) | 是 | 创建账号 |
| `create_time` | timestamp(0) | 是 | 创建时间 |

主键：

```text
(project_id, user_id)
```

MVP 项目角色：

| 代码 | 中文 | 说明 |
| --- | --- | --- |
| `director` | 项目管理人 | 项目管理、任务分配、审核、锁版 |
| `creator` | 制作人员 | 执行任务、查看 open 问题、逐条说明处理方式并提交版本 |

规则：

- 用户必须处于 `sys_user.status = '0'` 且 `del_flag = '0'`。
- 可被分配制作任务的成员必须设置 2—12 位大写 ASCII 字母或数字 `producer_code`；同一项目内不允许重复。
- 系统可以根据成员姓名提供首字母建议，但必须由项目管理人或管理员确认并保存；成员改名不能改变历史版本文件名。
- 平台管理员不是项目角色；是否绕过成员限制由平台权限决定。
- 一个项目始终至少保留一名 `director`。
- 不允许移除最后一名活动项目管理人。
- 普通成员接口只做软移除：将 `member_status` 改为 `removed` 并记录 `removed_by`、`removed_time`；不得物理删除成员关系或破坏历史任务外键。
- 项目范围、成员列表、总监计数和任务委派候选只认 `member_status = 'active'` 的成员。
- 重新添加已移除用户时复用原 `(project_id, user_id)` 关系，清空移除字段并恢复为 `active`；活动成员重复添加仍返回冲突。
- 旧版数据库结构无法表达软移除状态；存在 `removed` 成员时，成员生命周期迁移必须拒绝降级，禁止静默恢复访问。
- MVP 不创建 `client` 项目角色。

### 6.2.1 `sg_managed_user_role`

Shot Grid 对平台 `sys_user_role` 增量的来源标记。该表不是第三层业务角色，也不保存项目权限；它只证明某一条平台角色关系由 Shot Grid 首次创建并允许在满足条件时由 Shot Grid 撤回。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user_id` | bigint | 是 | 复合主键；对应 `sys_user_role.user_id` |
| `role_id` | bigint | 是 | 复合主键；对应 `sys_user_role.role_id` |
| `create_by` | varchar(64) | 是 | 创建来源标记的操作账号，默认空字符串 |
| `create_time` | timestamp(0) | 是 | 创建来源标记时间 |

约束与所有权规则：

- 主键为 `(user_id, role_id)`；同一字段组以复合外键引用 `sys_user_role(user_id, role_id)` 并使用 `ON DELETE CASCADE`，先删除受管平台角色关系时来源标记随之删除，不存在孤立来源行。
- 只有 Shot Grid 在同一事务中新建对应 `sys_user_role` 时才创建来源标记。若平台角色关系已存在而来源标记不存在，专用服务只复用该外部关系，不补写标记、不取得撤回权。
- 依赖数量不保存为可漂移计数器；每次同步都直接查询目标用户全部 `member_status='active'` 的 `sg_project_member.project_role`。查询不按项目状态过滤，因此归档项目仍计入历史只读依赖。
- 只有来源标记存在、对应 `sys_user_role` 仍一致且活动项目依赖为零时，才能在同一事务中删除该一条平台角色关系和来源标记。无标记关系、其他角色和其他业务来源的关系一律保留。
- 表不保存项目 ID、依赖计数、代理主键、角色键快照或来源类型；所有权只由复合来源行表达，依赖事实只由活动项目成员关系表达。
- PostgreSQL 迁移 `20260818_12`、初始化 SQL、SQLAlchemy DO 和 schema 注册保持上述结构一致；迁移只建来源表，不自动创建或猜测两个平台角色包。

### 6.3 `sg_episode`

集主表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `episode_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `episode_no` | integer | 是 | 集号，镜头业务文件名格式化为 `EP001` |
| `storage_dir_name` | varchar(32) | 是 | NAS 集目录快照，例如 `EP01` |
| `episode_name` | varchar(200) | 否 | 集名称 |
| `description` | text | 否 | 集说明 |
| `sort_order` | integer | 是 | 项目内排序 |
| `lifecycle_status` | varchar(20) | 是 | `active` 或 `archived` |
| 通用审计字段 |  | 是 | 见 5.2 |

约束：

- `episode_no > 0`。
- `(project_id, episode_no)` 在 `del_flag='0'` 的记录中唯一；业务归档仍占用原集号，避免历史 NAS 路径被新集复用。
- 镜头业务文件名中的集号由 `episode_no` 左侧补零至至少 3 位并增加 `EP` 前缀，不在数据库重复保存 `EP001` 字符串。
- `storage_dir_name` 创建时由后端按 `EP{episode_no:至少2位}` 生成并保持不可变；NAS 目录示例 `EP01` 与业务文件名集代码 `EP001` 是两个明确概念。
- 集存在未归档场次时不能直接归档。

### 6.4 `sg_scene`

场次主表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `scene_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `episode_id` | bigint | 是 | 所属集 |
| `scene_no` | integer | 是 | 集内场次号；正片场次从 1 开始，“序”固定为 0，文件名格式化为 `000` |
| `scene_name` | varchar(200) | 否 | 场次名称 |
| `description` | text | 否 | 场次描述 |
| `sort_order` | integer | 是 | 集内排序 |
| `lifecycle_status` | varchar(20) | 是 | `active` 或 `archived` |
| 通用审计字段 |  | 是 | 见 5.2 |

约束：

- `scene_no >= 0`；`0` 仅用于“序”，规范名称为“序”，API 派生代码为 `000`。
- `(episode_id, scene_no)` 在 `del_flag='0'` 的记录中唯一；业务归档仍占用原场次号，避免历史层级和路径产生歧义。
- `episode_id` 必须属于同一个 `project_id`。
- API 派生 `sceneCode = sceneNo 左侧补零至至少 3 位`。
- `(episode_id, sort_order)` 不强制唯一，但必须稳定排序。
- 场次存在未归档镜头时不能直接归档，除非明确执行级联归档方案。

### 6.5 `sg_shot`

镜头主表。状态、当前环节、负责人、最新版本和缩略图默认由任务与版本聚合，不作为多个可写事实字段重复保存。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `shot_id` | bigint | 是 | 稳定内部主键；不展示为镜头号，不参与 NAS 路径生成 |
| `project_id` | bigint | 是 | 所属项目，用于权限和高频查询 |
| `episode_id` | bigint | 是 | 所属集，用于目录唯一性和高频查询 |
| `scene_id` | bigint | 是 | 所属场次 |
| `shot_no` | integer | 是 | 场内连续镜序；第 1 镜派生 `S001`，第 2 镜派生 `S002` |
| `storage_dir_name` | varchar(32) | 否 | NAS 镜头目录快照；开始制作时才冻结为 `001_S001` |
| `duration_ms` | bigint | 是 | 镜头时长，整数毫秒 |
| `shot_size` | varchar(40) | 否 | 景别 |
| `camera_position` | varchar(100) | 否 | 机位 |
| `camera_movement` | varchar(100) | 否 | 运镜 |
| `focal_length` | varchar(50) | 否 | 焦段原始文本，例如 `135`、`35/25`、`24/18` |
| `description` | text | 是 | 镜头描述 |
| `dialogue` | text | 否 | 台词 |
| `sound_effect` | text | 否 | 音效说明 |
| `color_reference` | text | 否 | 色调参考说明，不保存临时文件 URL |
| `sort_order` | integer | 是 | 场内稳定排序键；Excel 导入和业务重排按 10 的倍数生成，业务界面不直接展示或编辑 |
| `lifecycle_status` | varchar(20) | 是 | `active` 或 `archived` |
| 通用审计字段 |  | 是 | 见 5.2 |

约束：

- `shot_no > 0`。
- `(scene_id, shot_no)` 在 `del_flag='0'` 的活动记录中唯一；同场活动镜头必须连续为 `1..N`，每个场次都重新从 `S001` 开始。符合安全删除条件的镜头设置 `del_flag='2'` 后释放编号，历史身份继续由不可复用的 `shot_id` 和审计记录追溯。
- API 派生 `shotCode = "S" + shotNo 左侧补零至至少 3 位`。
- `duration_ms >= 0`。
- `focal_length` 去除首尾空格后原样保存或为空，不把 `35/25` 等组合焦段强制换算为单一数值。
- `scene_id` 必须属于同一个 `project_id`。
- `episode_id`、`scene_id` 和 `project_id` 必须属于同一层级，建议使用组合外键保证一致。
- 新建和导入镜头的 `storage_dir_name` 为空。镜头任务开始时才按 `{scene_no:至少3位}_S{shot_no:至少3位}` 冻结名称并投递 Outbox；`shot_id` 不嵌入路径。
- 排序只允许影响范围内全部镜头均未开始制作；已分配但仍为 `not_started` 可以排序，任一镜头为 `preparing/in_progress/pending_review/revision/completed` 或存在版本/文件时整个动作失败。
- 删除后必须保持场内活动镜头连续。服务端从最早删除位置到场尾重查与排序相同的制作门禁；受影响区间存在 `storage_dir_name` 时以 `SG_SHOT_DELETE_DIRECTORY_EXISTS` 拒绝，禁止隐式改名。通过后目标镜头、其 `not_started` 任务及剩余镜头重编号在同一事务提交。
- 镜头响应中的 `status`、`currentStage`、`assignee`、`latestVersion` 和 `thumbnail` 是只读聚合字段。
- 镜头列表和详情响应派生 `sequencePosition`：在同一场次、同一生命周期内按 `(sort_order, shot_no, shot_id)` 稳定排序后从 1 开始计数。筛选或分页不得改变该位置。

#### 6.5.1 界面镜头表字段映射

业务界面可以展示以下 20 个业务字段。它们不是 Excel 导入模板的固定列：数据库只保存镜头自身事实，任务、版本、审核和资产关系产生的展示值不得反写为重复事实字段。当前 Excel 导入模板以第 14.1 节确认的 A:O 15 列为准，且不含制作人。

| 顺序 | 表头 | API 字段 | 数据来源 | 编辑方式 |
| --- | --- | --- | --- | --- |
| 1 | 集 | `episodeNo`、`episodeCode` | `sg_episode`，通过场次关联 | 修改镜头所属场次 |
| 2 | 场次 | `sceneNo`、`sceneName` | `sg_scene`，通过 `scene_id` 关联 | 修改镜头所属场次 |
| 3 | 本场第 N 镜 | `sequencePosition` | 与 `shotNo` 同义，均由同场稳定顺序派生 | 单场表格拖拽；编辑表单只读 |
| 4 | 镜序代码 | `shotNo`、`shotCode` | `sg_shot.shot_no`；第 N 镜必为 `S{N:03d}` | 不单独编辑，随场内顺序自动同步 |
| 5 | 时长(s) | `durationMs` | `sg_shot.duration_ms`，前端换算为秒显示 | 可编辑，后端保存整数毫秒 |
| 6 | 制作人 | `assignee` | 镜头唯一任务的 `assignee_user_id` 和 `sys_user` | 通过任务分配动作修改 |
| 7 | 镜头缩略图 | `thumbnail` | 最新版本中 `file_role = 'thumbnail'` 的平台文件 | 只读 |
| 8 | 制作内容描述 | `description` | `sg_shot.description` | 可编辑 |
| 9 | 景别 | `shotSize` | `sg_shot.shot_size` | 可编辑 |
| 10 | 机位 | `cameraPosition` | `sg_shot.camera_position` | 可编辑 |
| 11 | 镜头运动 | `cameraMovement` | `sg_shot.camera_movement` | 可编辑 |
| 12 | 焦段(mm) | `focalLength` | `sg_shot.focal_length` | 可编辑，按文本保存 |
| 13 | 场景 | `environmentAssets` | `sg_shot_asset` 关联的 `Environment` 资产 | 通过镜头资产关系修改 |
| 14 | 角色 | `characterAssets` | `sg_shot_asset` 关联的 `Character` 资产 | 通过镜头资产关系修改 |
| 15 | 台词/对白 | `dialogue` | `sg_shot.dialogue` | 可编辑 |
| 16 | 音效 | `soundEffect` | `sg_shot.sound_effect` | 可编辑 |
| 17 | 色调参考 | `colorReference` | `sg_shot.color_reference` | 可编辑；参考图片另走文件关系 |
| 18 | 备注 | `remark` | 通用审计字段 `remark` | 可编辑 |
| 19 | 当前最新反馈 | `latestFeedback` | 当前任务最近一条 open 修改问题；没有 open 问题时为空 | 只读 |
| 20 | 镜头状态 | `status` | 按第 7.1 节从唯一任务和版本聚合 | 只读 |

补充规则：

- “场内镜头位置”是面向用户的连续序位，不是 `shot_id`、Excel 行号、版本号或内部 `sortOrder`。界面统一显示“本场第 N 镜”。
- 业务前端写入 `sequencePosition`，服务端在项目行锁和场内镜头行锁内统一重排内部 `sort_order`；兼容客户端可以继续提交 `sortOrder`，但两者不得同时出现。
- “集”和“场次”是父级业务实体；“场景”和“角色”是镜头关联的资产分类，不能共用数据库字段。
- `durationSec` 接受最多三位小数，后端使用十进制定点运算换算为 `duration_ms`，不得通过二进制浮点直接计算。
- “制作人”不存在直接的 `sg_shot.assignee_user_id`；直接显示镜头唯一视频任务的负责人。
- “当前最新版本”按镜头唯一任务中的 `version_no DESC` 确定。
- “当前最新反馈”从任务全部版本关联的 open 修改问题中按 `create_time DESC, note_id DESC` 取一条，并返回来源版本摘要；没有 open 问题时返回 `null`。完整问题列表必须走独立接口。
- 缩略图只取当前最新版本中 `file_role = 'thumbnail'` 且按 `sort_order ASC, file_id ASC` 排序的首个文件；`is_primary` 只用于 `review_media`，不用于缩略图。当前版本没有缩略图时返回 `null`，不得静默回退到旧版本图片。
- 缩略图返回稳定 `fileId` 和 Shot Grid 专用授权访问地址，不保存 Blob URL、本机路径或未经授权的公开 URL；访问时仍按第 17 节实时校验项目、任务和平台文件 deny 决策。

### 6.6 `sg_asset`

资产主表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `asset_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `asset_name` | varchar(200) | 是 | 资产名称 |
| `asset_name_key` | varchar(200) | 是 | 统一空白、全半角和大小写后的匹配唯一键，不向前端展示 |
| `asset_type` | varchar(20) | 是 | 资产类型 |
| `storage_dir_name` | varchar(240) | 是 | NAS 资产子目录名快照 |
| `storage_path_key` | varchar(500) | 是 | 项目内规范化路径唯一键，不向前端展示 |
| `description` | text | 否 | 资产说明 |
| `sort_order` | integer | 是 | 项目内排序 |
| `lifecycle_status` | varchar(20) | 是 | `active` 或 `archived` |
| 通用审计字段 |  | 是 | 见 5.2 |

资产类型：

| 代码 | 中文 |
| --- | --- |
| `Character` | 角色 |
| `Environment` | 场景 |
| `Prop` | 道具 |

规则：

- MVP 只允许 `Character`、`Environment`、`Prop`，不接受 `other` 或任意自定义类型。
- 将来扩展类型时必须同步数据库约束、后端枚举/校验、字典、导入映射、目录与文件命名测试；不能只在字典管理中增加显示值。
- `asset_name_key` 必须由后端统一算法生成，手工创建和 Excel 导入共用同一实现；前端不得自行提交该值。
- 资产创建时按 Windows/SMB 安全规则生成并确认 `storage_dir_name`；`asset_type`、`asset_name`、规范键和目录快照共同构成稳定身份，创建后普通编辑均不可修改。
- 制作分项、任务描述、状态、制作人、缩略图、最新版本和批准版本来自 `sg_asset_item` 及其唯一任务；资产完成状态按全部活动制作分项聚合。
- 制作分项 `thumbnail` 只取其当前最新版本的首个 `file_role=thumbnail` 文件；最新版本没有缩略图时返回 `null`，不得回退旧版本。资产父级 `thumbnail` 按活动制作分项 `(sort_order, asset_item_id)` 升序选择第一张非空缩略图，保证列表、详情和不同前端视图的代表图一致。
- 资产列表的表格视图使用 Element Plus 原生树形懒加载（`lazy/load/row-key/tree-props`），父行为资产、子行为其活动制作分项；分页数量、筛选和批量选择仍以父资产为单位。子行不改变父资产的服务端聚合状态，不把某个分项状态作为整资产状态。
- 首次展开通过现有鉴权 `GET /shot-grid/projects/{projectId}/assets/{assetId}/items` 获取 `data: ShotGridAssetItemModel[]`，保留 `shotgrid:asset:query` 和项目访问依赖；前端过滤 `lifecycleStatus=active` 并按 `sortOrder/assetItemId` 排序，归档历史从详情查看。此变更不新增后端接口或数据库字段。
- 树节点键分别为 `asset:{projectId}:{assetId}` 和 `item:{projectId}:{assetItemId}`；`tree-props` 声明 `children/hasChildren`，并使用 `checkStrictly=true`。标准选择列只允许父资产进入原有批量业务链，分项行不能误传为资产或自动联动勾选。
- 子行展示自身 `productionItem/description/thumbnail/task/assetStatus/latestVersion`；制作人优先使用平台 `userName`，无任务为未分配。点击“分项详情”打开原资产抽屉并定位对应分项，不直接执行开工或绕过现有分项动作确认。
- 表格“说明”是当前主数据的组合视图：父行读取 `sg_asset.description`，子行读取同一父字段并追加自身 `sg_asset_item.description`。父子文本完全相同时只展示一次；父字段为空时不推断共有内容，保留原分项说明且提示父级尚未填写。该组合不写回字段、不修改任务 `requirements` 或版本快照，也不改变 `asset-v2` 导入映射。长文本使用 `ElText.line-clamp=3`，实际溢出时提供明确的展开/收起按钮；分项数归入父名称，版本归入子缩略图，父行显示分项状态计数，不再同时重复聚合状态标签。编辑/删除收进 `ElDropdown`，仍复用原动作和确认流程。
- 懒加载失败必须呈现错误，不能伪装成零个分项；可重试错误提供“重试分项”，权限错误不自动重试。人工刷新失效成功缓存并重新读取已展开分项；后台轮询等待当前分项请求完成，再通过公开 `updateKeyChildren` 刷新已加载分支，保留有效勾选、展开、滚动和图片预览；原空分支新增分项时才重建懒加载入口。后台不反复请求失败分支，人工刷新可重新尝试。项目、筛选、分页变化或卸载必须取消旧请求、清除旧树上下文，迟到响应不得调用失效表格的 `resolve`。
- 资产与制作分项响应分别携带后端计算的 `allowedActions`。动作集合必须同时满足平台权限、项目访问/角色、项目非 `completed/archived`、项目存储 `ready`、资源活动状态以及任务/版本约束；前端不得自行合成。
- 资产列表与详情返回 `itemStatusCounts`，固定包含 `unassigned/not_started/preparing/in_progress/reviewing/revision/completed` 七个非负整数键，仅统计活动且未删除分项。父级状态按 `revision → reviewing → in_progress → preparing → unassigned → not_started` 聚合；至少有一个活动分项且全部完成才为 `completed`，无活动分项为 `unassigned`。父级 `task.start` 仅表示可进入分项选择，至少存在一个实际可开工分项才返回；真正 start 必须对选中分项任务提交，不能整资产开工。
- 资产详情普通刷新必须保留编辑草稿对应的父资产/分项快照与锁号，不能用新锁提交旧稿；409“刷新后重试”应显式关闭旧操作上下文、刷新详情并要求重新核对。开工后等待详情刷新结束，还须再次复核操作代次才能通知父列表，防止同ID往返接受迟到事件。
- 目录成功回写必须先锁项目，再锁目录操作及任务/存储行，与开工事务使用同一项目协调锁；等待后仍复核 owner + attempt fencing。该锁仅在 NAS I/O 结束后的短事务持有，保证共享目录完成与新分项开工交错时不会遗漏已开工分项。
- 参考图片使用平台文件引用，业务类型为 `shotgrid_asset_reference`。

#### 6.6.1 正式资产表头映射

| 顺序 | 表头 | API 字段 | 数据来源 | 编辑方式 |
| --- | --- | --- | --- | --- |
| 1 | 类型 | `assetType` | `sg_asset.asset_type` | 创建时选择，创建后普通编辑不可修改 |
| 2 | 名称 | `assetName` | `sg_asset.asset_name` | 创建时填写，创建后普通编辑不可修改 |
| 3 | 制作分项 | `productionItem` | `sg_asset_item.production_item` | 草稿可空；分配负责人前必须补齐 |
| 4 | 资产描述 | `description` | `sg_asset.description` | 可编辑 |
| 5 | 任务描述 | `taskDescription` | 当前制作分项唯一任务的 `requirements` | 通过任务分配或任务编辑动作修改 |
| 6 | 备注 | `remark` | 通用审计字段 `remark` | 可编辑 |
| 7 | 状态 | `status` | 当前制作分项唯一任务和版本聚合 | 只读 |
| 8 | 制作人 | `assignee` | 当前制作分项唯一任务和 `sys_user` | 通过任务分配动作修改；只允许一名主制作人 |

#### 6.6.2 `sg_asset_item`

资产制作分项表。一个资产可以包含多个制作分项，每个制作分项是独立分配、提交版本和审核的最小图片生产单元。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `asset_item_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目，用于权限和高频查询 |
| `asset_id` | bigint | 是 | 所属资产 |
| `production_item` | varchar(240) | 否 | 制作分项名称；允许以未分配草稿导入后补充，分配负责人前必填 |
| `production_item_key` | varchar(240) | 否 | 制作分项规范化匹配键，不向前端展示 |
| `description` | text | 否 | 制作分项描述 |
| `sort_order` | integer | 是 | 资产内稳定顺序，导入时按明细行生成 |
| `source_import_batch_id` | bigint | 否 | 来源资产导入批次；手工创建为空 |
| `source_row_no` | integer | 否 | 来源 Sheet 明细行号 |
| `import_row_key` | char(64) | 否 | 文件摘要、Sheet 和行号生成的来源行技术键，仅对相同字节工作簿稳定 |
| `lifecycle_status` | varchar(20) | 是 | `active` 或 `archived` |
| 通用审计字段 |  | 是 | 见 5.2 |

规则：

- 制作分项缺失时预检查返回警告而不是错误，正式提交仍创建 `sg_asset_item`，允许后续编辑补充。
- 空字符串或纯空白规范化为 `NULL`；数据库使用 `CHECK` 保证名称为空时规范键也为空，名称非空时规范键必填。
- `production_item` 有值时，`production_item_key` 必填；同一资产内活动制作分项名称大小写不敏感唯一。
- PostgreSQL 使用 `WHERE production_item_key IS NOT NULL AND lifecycle_status='active' AND del_flag='0'` 的部分唯一索引；未命名分项不参加名称唯一约束。
- 导入创建的分项必须保存 `import_row_key`，并在项目内建立非空部分唯一索引，用于阻止同一字节工作簿的同一来源行重复落库。
- `import_row_key` 由原文件 SHA-256、Sheet 和物理行号生成，只保证相同字节工作簿重试时稳定；工作簿重新保存后摘要会变化，尤其未命名分项仍可能被视为新来源行。当前 MVP 必须把这一点作为导入治理边界，长期跨文件幂等需在模板增加稳定 `rowUid` 或提供人工去重流程。
- 制作分项已有正式版本后不得普通修改；未产生版本时允许补充或纠正名称。
- 每个制作分项最多一个 `asset_image` 任务，任务只有一个 `assignee_user_id` 主制作人。
- 资产归档前必须先检查所有制作分项及其任务、版本和审核历史。

```sql
CHECK (
  (production_item IS NULL AND production_item_key IS NULL)
  OR
  (btrim(production_item) <> '' AND production_item_key IS NOT NULL)
)
```

### 6.7 `sg_shot_asset`

镜头与资产关系。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `project_id` | bigint | 是 | 项目 |
| `shot_id` | bigint | 是 | 镜头 |
| `asset_id` | bigint | 是 | 资产 |
| `usage_note` | varchar(500) | 否 | 使用说明 |
| `create_by` | varchar(64) | 是 | 创建账号 |
| `create_time` | timestamp(0) | 是 | 创建时间 |

主键：

```text
(shot_id, asset_id)
```

约束：

- 镜头和资产必须属于同一个项目。
- 通过组合外键或 Service 校验防止跨项目关联。

### 6.8 `sg_task`

任务主表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `shot_id` | bigint | 条件必填 | 所属镜头 |
| `asset_item_id` | bigint | 条件必填 | 所属资产制作分项 |
| `task_name` | varchar(240) | 是 | 任务名称 |
| `task_kind` | varchar(20) | 是 | `shot_video` 或 `asset_image` |
| `assignee_user_id` | bigint | 是 | 负责人 |
| `task_status` | varchar(20) | 是 | 任务状态 |
| `priority` | varchar(10) | 是 | 优先级 |
| `due_date` | date | 否 | 截止日期 |
| `requirements` | text | 否 | 制作要求 |
| 通用审计字段 |  | 是 | 见 5.2 |

任务状态：

| 代码 | 中文 |
| --- | --- |
| `not_started` | 待开工 |
| `in_progress` | 制作中 |
| `pending_review` | 待审核 |
| `revision` | 修改中 |
| `completed` | 已完成 |

优先级：

| 代码 | 中文 |
| --- | --- |
| `high` | 高 |
| `normal` | 中 |
| `low` | 低 |
| `urgent` | 紧急 |

关键约束：

```sql
CHECK (
  (shot_id IS NOT NULL AND asset_item_id IS NULL AND task_kind = 'shot_video')
  OR
  (shot_id IS NULL AND asset_item_id IS NOT NULL AND task_kind = 'asset_image')
)
```

其他规则：

- 负责人必须是当前项目成员且账号有效。
- 负责人必须已设置当前项目唯一的 `producer_code`。
- 任务与目标对象必须属于同一个项目。
- 资产制作分项名称为空时只允许保存为未分配草稿；首次分配、改派、批量分配、开始任务和提交版本均失败关闭。
- 镜头或资产制作分项首次分配主制作人时创建任务；未分配的目标不提前创建空负责人任务。
- 每个镜头最多一个 `shot_video` 任务，每个资产制作分项最多一个 `asset_image` 任务，使用 PostgreSQL 部分唯一索引保证。
- `assignee_user_id` 只保存一名主制作人；只有显式委派接口接受负责人，且一次委派只能选择一名活动项目成员，不得静默选择或创建多人负责人文本。
- 后续改派只更新现有任务负责人并记录操作日志，不创建第二个正式任务。
- 平台不执行图片或视频制作；任务仅承载制作要求、负责人、截止日期、上传版本和审核状态。

建议索引：

```sql
CREATE UNIQUE INDEX uk_sg_task_shot
ON sg_task(shot_id)
WHERE shot_id IS NOT NULL AND del_flag = '0';

CREATE UNIQUE INDEX uk_sg_task_asset_item
ON sg_task(asset_item_id)
WHERE asset_item_id IS NOT NULL AND del_flag = '0';
```

### 6.9 `sg_version`

提交版本主表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `version_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `task_id` | bigint | 是 | 所属任务 |
| `submission_id` | bigint | 是 | 来源 `sg_version_submission`，一对一追溯 |
| `version_no` | integer | 是 | 任务范围内递增序号 |
| `version_status` | varchar(20) | 是 | 版本状态 |
| `changelog` | text | 是 | 修改说明 |
| `ai_params` | jsonb | 否 | AI 生成参数快照 |
| `submitted_by` | bigint | 是 | 提交用户 |
| `submitted_time` | timestamp(0) | 是 | 提交时间 |
| `generated_at_ms` | bigint | 是 | 服务端生成版本业务文件名时的 Unix 毫秒时间戳 |
| `selected_candidate_id` | bigint | 否 | 本轮最佳候选；单候选由系统设置，多候选由审核人选择 |
| `selected_by` | bigint | 否 | 最近选择候选的审核用户；历史候选 01 回填可为空 |
| `selected_time` | timestamp(0) | 否 | 最近选择候选时间 |
| `lock_version` | integer | 是 | 审核并发控制 |

返回时派生：

```text
versionNumber = "V" + versionNo 左侧补零至至少 3 位
```

版本状态：

| 代码 | 中文 |
| --- | --- |
| `pending_review` | 待审核 |
| `rejected` | 已退回 |
| `final` | 最终版 |

约束：

- `UNIQUE(task_id, version_no)`。
- `UNIQUE(submission_id)`，一个提交最多形成一个正式版本。
- `version_no > 0`。
- 版本和任务必须属于同一个项目。
- 同一任务最多一个 `final`，通过 PostgreSQL 部分唯一索引保证。
- 创建后不可修改所属任务、序号、提交人、提交时间和已绑定文件。
- AI 参数是提交时快照，不随系统模型配置变化。
- 新版本号由后端在事务和行锁下分配，前端不计算。
- `generated_at_ms` 由后端生成，客户端不得传入或覆盖。
- 一个 `sg_version` 表示一个 V001/V002 审核与返修轮次，不表示单个候选文件；候选数量不参与版本计数。
- 单候选新提交轮次在正式版本事务内直接设置 `selected_candidate_id` 和主审核文件，`selected_by/selected_time` 保持为空且不写选择历史；多候选新轮次初始为空，审核人必须通过候选选择命令设置后，才能保存问题草稿、确认通过或退回。
- `selected_candidate_id` 必须引用同一 `version_id` 的候选。候选切换和版本 `lock_version + 1` 在同一事务完成。
- 镜头与资产只读投影使用统一“展示候选”：`selected_candidate_id` 非空时取该候选，否则按 `sort_order,candidate_no,candidate_id` 取首个候选。审核媒体业务文件名、缩略图和代理媒体都绑定该展示候选；多候选 `pending_review` 且尚未选择最佳候选是合法状态，不得返回 `SG_INVALID_STATE_TRANSITION`，也不得让资产缩略图退化为空。

建议索引：

```sql
CREATE UNIQUE INDEX uk_sg_version_task_final
ON sg_version(task_id)
WHERE version_status = 'final';
```

#### 6.9.1 `sg_version_candidate`

版本轮次内不可变的候选作品。候选展示号由 `version_no + candidate_no` 组成，例如 `V001_02`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `candidate_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `version_id` | bigint | 是 | 所属版本轮次 |
| `submission_file_id` | bigint | 是 | 来源候选提交文件，一对一 |
| `candidate_no` | integer | 是 | 轮次内从 1 连续递增的小编号 |
| `candidate_note` | varchar(500) | 否 | 制作人对该候选的简短说明 |
| `sort_order` | integer | 是 | 冻结展示顺序 |
| `create_by` / `create_time` |  | 是 | 创建审计 |

约束：`UNIQUE(version_id,candidate_no)`、`UNIQUE(submission_file_id)`、`candidate_no>0`。一个轮次至少一个候选；正式版本事务必须按提交命令稳定顺序一次性创建全部候选，不允许后补候选或删除候选。历史版本统一回填候选 01，但不重命名既有 NAS 文件。

#### 6.9.2 `sg_final_delivery`

审核通过后的数据库真相和 NAS 异步交付 Outbox。每个最终版本最多一行；候选源文件保持原位，不改名、不覆盖。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `final_delivery_id` | bigint | 是 | 主键 |
| `project_id/task_id/version_id/candidate_id` | bigint | 是 | 最终版本及其最佳候选；项目、任务、版本必须一致 |
| `source_file_id` | varchar(36) | 是 | 最佳候选的平台文件身份 |
| `business_file_name` | varchar(255) | 是 | 最终文件沿用的不可变业务文件名 |
| `source_nas_relative_path` | varchar(1200) | 是 | 已发布候选源文件相对项目根路径 |
| `final_nas_relative_path` | varchar(1200) | 是 | `{源文件父目录}/FINAL/{businessFileName}` |
| `manifest_nas_relative_path` | varchar(1200) | 是 | `{源文件父目录}/FINAL/FINAL.json` |
| `source_sha256/source_file_size` | char(64)/bigint | 是 | 审核事务冻结的源内容身份 |
| `delivery_status` | varchar(20) | 是 | `pending/publishing/published/failed` |
| `attempt_count/lease_owner/lease_until` |  | 是/否 | Worker 租约与 owner + attempt fencing |
| `last_error_key/last_error_message` | varchar | 否 | 仅失败态保存的安全错误 |
| `publish_mode` | varchar(20) | 否 | 成功时为 `hardlink/copied/reused` |
| `approved_by/approved_time` |  | 是 | 审核通过身份和时间 |
| `published_time` | timestamp(0) | 否 | NAS 文件和清单均完成后的时间 |

约束与执行语义：

- `UNIQUE(version_id)`，并通过候选复合外键保证候选属于该版本；同一任务最终版本唯一性继续由 `sg_version` 的部分唯一索引保证。
- `approve` 在审核事务中冻结上述字段并写入 `pending`；审核接口不访问 NAS。
- Worker 按 `project → task → version → final_delivery` 锁序领取，使用有期限租约、`FOR UPDATE SKIP LOCKED` 和 owner + attempt fencing；领取、NAS I/O、结果回写必须是短事务、事务外 I/O、短事务。
- 目标固定是源文件同级 `FINAL/`，优先建立硬链接；文件系统不支持时复制到 attempt 唯一临时文件，重新校验摘要和大小后无覆盖原子发布。
- `FINAL.json` 至少记录版本、候选、业务文件名、源/最终相对路径、摘要、大小、审核人和审核时间，不记录 UNC 绝对路径、凭据或密钥。
- 文件与清单全部成功后才可写 `published`。同路径已有相同内容可重用，不同内容或不同清单返回不可重试冲突；源文件内容变化失败关闭。

### 6.10 `sg_version_file`

版本文件用途关系。它补充 `sys_file_reference` 无法表达的“文件用途、主文件和顺序”，但不能替代平台文件业务引用。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `version_id` | bigint | 是 | 所属版本 |
| `candidate_id` | bigint | 是 | 所属版本候选，且必须与 `version_id` 一致 |
| `file_id` | varchar(36) | 是 | 关联 `sys_file_info.file_id` |
| `file_role` | varchar(30) | 是 | 文件用途 |
| `business_file_name` | varchar(255) | 是 | 按 Shot Grid 规则生成的展示和下载文件名 |
| `nas_relative_path` | varchar(1200) | 条件必填 | 相对项目根目录的 NAS 文件路径；主审核文件必须填写 |
| `nas_sha256` | char(64) | 条件必填 | NAS 文件摘要；主审核文件必须填写 |
| `nas_file_size` | bigint | 条件必填 | NAS 文件字节数；主审核文件必须填写 |
| `published_time` | timestamp(0) | 条件必填 | NAS 发布完成时间 |
| `is_primary` | char(1) | 是 | 是否主文件：`1` 是、`0` 否 |
| `sort_order` | integer | 是 | 展示顺序 |
| `create_by` | varchar(64) | 是 | 创建账号 |
| `create_time` | timestamp(0) | 是 | 创建时间 |

文件用途：

| 代码 | 说明 |
| --- | --- |
| `review_media` | 主审核图片或视频 |
| `thumbnail` | 缩略图 |
| `proxy_media` | 网页审核代理 |
| `source_original` | 原始生成或制作文件 |
| `source_repaired` | 修复后文件 |
| `first_frame` | 首帧 |
| `last_frame` | 尾帧 |
| `reference` | 参考媒体 |

主键：

```text
(version_id, file_id, file_role)
```

规则：

- `is_primary` 只允许 `0` 或 `1`。
- 每个候选恰好一个 `is_primary='1' AND file_role='review_media'`；部分唯一索引以 `candidate_id` 为边界。
- `is_primary='1'` 时 `file_role` 必须为 `review_media`，且 `nas_relative_path`、`nas_sha256`、`nas_file_size`、`published_time` 全部必填；`nas_file_size >= 0`。
- 每个候选的主 `review_media` 必须具有唯一且不可变的 `business_file_name`。
- 主 `review_media` 只有在 NAS 临时写入、摘要校验和原子改名完成后才能写入本表，因此本表不存在 `publishing` 半成品状态。
- 创建版本和 `sg_version_file`、`sys_file_reference` 必须处于同一事务。
- 对应业务引用使用：

```text
businessType = shotgrid_version_candidate
businessId   = candidateId 的字符串形式
```

- `sys_file_info.original_name` 保留用户上传时的原始名称，`stored_name` 和 `storage_key` 继续由平台文件服务管理；不得改写平台受保护文件。NAS 发布是以业务文件名生成的一份受控副本或同内容存储映射，不得反向修改平台 `storage_key`。
- 版本接口按候选分组返回文件；文件项至少包含 `{ candidateId, fileId, originalName, businessFileName, url, role, isPrimary }`，不返回 `storageKey`。
- 通用文件下载当前使用 `sys_file_info.original_name` 作为下载名。需要按 `business_file_name` 下载时，必须由 Shot Grid 授权下载接口复用底层流式能力并设置业务文件名，不能假设通用下载接口已经支持。

#### 6.10.1 主产出物业务文件命名

镜头视频：

```text
{projectCode}_EP{episodeNo:至少3位}_{sceneNo:至少3位}_S{shotNo:至少3位}_{producerNickName}_V{versionNo:至少3位}_{candidateNo:至少2位}_{generatedAtMs}.{extension}
```

示例：

```text
WGZR_EP001_001_S001_YJF_V001_01_1786094626499.mp4
```

镜头业务文件名同时包含 `versionNo` 与 `candidateNo`；前者必须与 `sg_version.version_no`、`sg_version_submission.reserved_version_no` 和审核轮次一致，后者必须与 `sg_version_candidate.candidate_no` 一致。

资产图片：

```text
{projectCode}_Asset_{assetType}_{safeAssetName}_{safeProductionItem}_{producerNickName}_V{versionNo:至少3位}_{candidateNo:至少2位}_{generatedAtMs}.{extension}
```

示例：

```text
WGZR_Asset_Environment_动力舱室内_动力舱恐怖气氛主视角_YJF_V001_01_1786094626499.jpg
```

生成规则：

1. `projectCode` 取版本提交暂存时项目已保存的 `sg_project.project_code`。
2. `producerNickName` 取任务负责人当前平台用户的 `sys_user.nick_name`；任务分配、Excel 匹配和版本文件名生成均使用该昵称，Shot Grid 不再采集项目级制作人缩写。兼容响应中的 `producerCode` 也由该昵称派生。
3. 镜头文件只允许 `.mp4`、`.mov`；资产文件只允许 `.jpg`、`.png`。扩展名根据服务端校验后的真实文件类型确定并转为小写，不能只相信客户端文件名。
4. 镜头文件名中的 `episodeNo`、`sceneNo`、`shotNo` 和 `versionNo` 左侧补零至至少 3 位，超过 999 时保留全部数字；候选号 `candidateNo` 左侧补零至至少 2 位。资产文件名使用相同的版本号和候选号规则。
5. `generatedAtMs` 是服务端 Unix 毫秒批次时间戳，与 `sg_version.generated_at_ms` 一致；同一轮全部候选共享该值。
6. `safeAssetName` 和 `safeProductionItem` 都使用 Unicode NFC 规范化，去除首尾空白，把控制字符和 `<>:"/\|?*` 替换为 `_`，合并连续空白或下划线；制作分项允许在导入时为空，但版本提交时规范化后为空必须拒绝。
7. `safeProductionItem` 取版本提交时任务所属 `sg_asset_item.production_item`，不允许上传者临时输入另一个值。
8. 文件名超过平台或文件系统安全长度时，在保留可辨识前缀的前提下按确定性规则缩短 `safeAssetName` 和 `safeProductionItem`，并追加资产 ID 的短哈希；不得截断项目、类型、制作人昵称、版本、候选或时间戳部分。
9. 各候选业务文件名在提交暂存事务内只生成一次并保持不可变。项目名、成员名、资产名或制作分项后续修改不追改历史版本文件名。
10. 同一 `X-Idempotency-Key` 重试必须返回第一次创建的版本轮次、候选小编号和业务文件名，不得生成新版本号、新候选号或新时间戳。

#### 6.10.2 NAS 目标路径

镜头主产出物：

```text
VIDEO\{episode.storage_dir_name}\{shot.storage_dir_name}\{business_file_name}
```

资产主产出物：

```text
ASSET\{asset.asset_type}\{asset.storage_dir_name}\{business_file_name}
```

- 数据库保存相对项目根目录的 `nas_relative_path`，完整 UNC 路径由 `sg_project_storage.project_path_snapshot` 安全拼接；不接受客户端传入完整目标路径。
- 每个 `sg_version_submission_file.temporary_relative_path` 位于自身目标文件同一目录，每次领取 attempt 使用包含 `submissionId/submissionFileId/attempt/random` 的唯一保留名称，保证最终原子发布不跨卷且不同候选、迟到 Worker 不复用同一临时文件。
- 正式和临时路径每次使用前都要重新解析并验证仍位于项目根目录内。
- NAS 目标已存在且摘要、大小均一致时视为幂等发布成功；任一不一致都禁止覆盖并返回 `SG_NAS_TARGET_CONTENT_CONFLICT`。

### 6.11 `sg_note`

跨版本修改问题主表。面向用户的正式名称是“修改问题（Review Issue）”；为兼容当前表名、权限码和部分 API，协议迁移期继续使用 `note/sg_note`，但其业务语义不再是聊天评论。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `note_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `version_id` | bigint | 是 | 问题首次提出时的来源版本，创建后不可变 |
| `reviewer_user_id` | bigint | 是 | 审核人 |
| `content` | text | 否 | 文字问题；与 `annotations` 至少一项有效 |
| `media_time_ms` | bigint | 否 | 视频时间点 |
| `annotations` | jsonb | 否 | 结构化批注数组 |
| `note_status` | varchar(20) | 是 | 处理状态 |
| `resolved_in_version_id` | bigint | 否 | 审核人确认问题已修复的后续版本 |
| `create_time` | timestamp(0) | 是 | 创建时间 |
| `update_time` | timestamp(0) | 是 | 更新时间 |

意见状态：

| 代码 | 中文 |
| --- | --- |
| `open` | 待处理 |
| `resolved` | 已解决 |

规则：

- 问题和来源版本必须属于同一个项目；只能在当前 `pending_review` 版本上创建，审核动作完成后不得补写问题。
- `content` 规范化后非空，或 `annotations.items` 至少包含一项有效标注；两者都为空时返回 `SG_ISSUE_CONTENT_REQUIRED`。
- 新问题统一为阻塞审核的 `open` 问题。旧字段 `is_mandatory` 不进入新产品契约；迁移期如暂时保留该列，新写入统一为 `1`，通过门禁不得再按该列筛选。
- `media_time_ms >= 0` 且不能超过已知媒体时长。
- 版本切换后必须以请求中的 `versionId` 为准重新校验。
- 已提交问题不保存整张 Canvas Data URL。
- 已提交问题正文、来源版本、时间点和批注不可覆盖。
- 新建时必须为 `open` 且 `resolved_in_version_id IS NULL`；只有后续版本的审核确认结果为 `resolved` 时，才能在同一事务改为 `resolved` 并写入该确认版本。
- 问题详情 API 为 open 问题返回派生字段 `pendingVersionId/pendingVersionNumber`：无确认时等于来源版本，最近一次确认是 `still_present` 时等于该确认版本；resolved 问题返回空。该字段只表达当前工作归属，不修改 `sg_note.version_id`。
- `resolved` 问题不可重新打开。后续版本如果出现相似问题，应创建绑定该后续版本的新问题，不能篡改旧问题。

#### 6.11.1 `sg_version_issue_response`

制作人随修订版本提交的逐条问题处理说明。响应先绑定版本提交；只有该提交达到 `committed` 后，才通过 `sg_version.submission_id` 成为对业务用户可见的版本处理记录，避免在版本尚未创建时保存可空或重复的 `version_id`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `response_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `submission_id` | bigint | 是 | 所属 `sg_version_submission` |
| `note_id` | bigint | 是 | 被处理的 open 修改问题 |
| `response_text` | text | 是 | 本版如何处理该问题 |
| `responded_by` | bigint | 是 | 实际提交人 |
| `create_time` | timestamp(0) | 是 | 创建时间 |

- `UNIQUE(submission_id, note_id)`；同一新版本对同一问题只有一条处理说明。
- `response_text` 规范化后必须非空，限制 2000 字符并按纯文本输出。
- create 锁定任务后，提交中的问题集合必须与该任务当时全部 open 问题精确一致：不得缺少、重复、夹带已关闭问题或跨任务引用。
- 首版提交没有历史 open 问题，不创建处理说明；修订提交至少存在一条 open 问题并为其逐条创建记录。
- 处理说明与 `sg_version_submission` 在同一短事务创建；正式版本事务不复制记录，只通过一对一 `submission_id` 关联。
- 提交达到 `committed` 后处理说明不可编辑或覆盖；提交失败时只在提交恢复界面内部可见，不作为正式版本历史展示。

#### 6.11.2 `sg_issue_verification`

审核人在后续版本上对历史 open 问题作出的逐条确认记录。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `verification_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `note_id` | bigint | 是 | 被确认的修改问题 |
| `checked_version_id` | bigint | 是 | 实际检查问题的后续版本 |
| `verification_result` | varchar(20) | 是 | `resolved` 或 `still_present` |
| `comment` | varchar(1000) | 条件必填 | `still_present` 时必须说明未解决原因；`resolved` 时为空 |
| `reviewer_user_id` | bigint | 是 | 审核人 |
| `create_time` | timestamp(0) | 是 | 确认时间 |

- `UNIQUE(note_id, checked_version_id)`；同一问题在同一被审核版本上只能确认一次。
- 问题来源版本、确认版本必须属于同一任务和项目，且确认版本序号必须大于来源版本序号。
- 确认记录创建后不可编辑或覆盖。
- `resolved` 必须在同一事务把问题改为 `resolved` 并写入 `resolved_in_version_id=checked_version_id`。
- `still_present` 必须携带非空 `comment`，保持问题为 `open`；退回后问题的派生 `pendingVersion` 等于 `checked_version_id`，来源版本只保留“已处理但未通过”历史。
- 当前版本新建的问题不在当前版本自我确认；它在下一次修订版本中才进入确认列表。

#### 6.11.3 旧 `sg_note_reply` 移除边界

旧回复表、旧意见数据与 `/notes/{noteId}/replies|reply|resolve` API 不属于新 MVP，迁移直接清理并删除，不提供兼容读写路径。制作人的处理说明只写入 `sg_version_issue_response`，审核人的逐条确认只写入 `sg_issue_verification`。

### 6.12 `sg_review_action`

审核动作不可变历史。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `action_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `version_id` | bigint | 是 | 审核版本 |
| `reviewer_user_id` | bigint | 是 | 操作人 |
| `action_type` | varchar(20) | 是 | 审核动作 |
| `from_status` | varchar(20) | 是 | 操作前状态 |
| `to_status` | varchar(20) | 是 | 操作后状态 |
| `reason` | varchar(1000) | 否 | 原因或说明 |
| `idempotency_key` | varchar(100) | 是 | 客户端审核动作幂等键 |
| `request_hash` | char(64) | 是 | 规范化审核命令 SHA-256 |
| `result_snapshot` | jsonb | 是 | 首次成功响应快照，用于耐久重放 |
| `create_time` | timestamp(0) | 是 | 操作时间 |

动作代码：

| 代码 | 中文 | 结果 |
| --- | --- | --- |
| `approve` | 确认通过 | `pending_review → final`，任务完成 |
| `reject` | 退回修改 | `pending_review → rejected` |
| `defer` | 稍后决定 | 状态保持 `pending_review` |

规则：

- 每次审核动作与版本、自动审核单、问题确认、问题状态和任务状态更新处于同一事务，并按 `project → task → version → auto_single review list → note → issue verification` 顺序加锁；`approve` 在同一事务追加唯一 `sg_final_delivery(pending)`，但不得执行 NAS I/O。
- 请求必须携带 `X-Idempotency-Key` 和版本 `lockVersion`；规范命令哈希必须包含按 `issueId` 稳定排序的完整 `issueVerifications`。`UNIQUE(version_id, reviewer_user_id, idempotency_key)` 防止重复动作。同键同一规范命令返回 `result_snapshot`，同键不同审核动作或不同逐条确认集合返回 `SG_IDEMPOTENCY_CONFLICT`。
- `approve` 必须确认所有带入当前版本的问题都已有 `resolved` 确认，并拒绝任务范围内任何 open 问题；不再按 `is_mandatory` 筛选。
- `reject` 必须确认所有带入当前版本的问题都已有 `resolved` 或 `still_present` 结果，并且至少存在一条 `still_present` 问题或绑定当前版本的新 open 问题。`reason` 只能作总述，不能替代结构化问题。
- `reject` 中确认 `resolved` 的问题也必须在本事务关闭；退回只继续携带 `still_present` 和当前版本新建的 open 问题。
- `defer` 记录动作但不伪造新状态。
- `approve` 同时把自动审核单改为 `completed`，把任务改为 `completed`。
- `reject` 同时把自动审核单改为 `completed`，把任务改为 `revision`；制作人员修改后上传下一不可覆盖版本。
- `final` 默认不可回退；如未来需要解锁，必须新增独立受控动作。

### 6.13 `sg_review_list`

审核单主表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `review_list_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `review_list_name` | varchar(240) | 是 | 审核单名称 |
| `description` | text | 否 | 说明 |
| `review_date` | date | 否 | 审核日期 |
| `review_mode` | varchar(20) | 是 | `auto_single` 或 `manual_batch` |
| `auto_version_id` | bigint | 条件必填 | 自动单对应版本；`auto_single` 必填，`manual_batch` 必须为空 |
| `review_status` | varchar(20) | 是 | 审核单状态 |
| 通用审计字段 |  | 是 | 见 5.2 |

审核单状态：

| 代码 | 中文 |
| --- | --- |
| `draft` | 草稿 |
| `active` | 审核中 |
| `completed` | 已完成 |
| `archived` | 已归档 |

规则：

- 每次成功提交版本时自动创建一个 `auto_single` 审核单，并加入且只加入当前版本。
- `auto_single` 必须保存 `auto_version_id`，`manual_batch` 的该字段必须为空；数据库使用模式/字段一致性 `CHECK` 兜底。
- 自动审核单创建失败时，版本、版本文件关系、业务文件引用和任务状态全部回滚。
- 人工 `manual_batch` 审核单使用有序多版本关系，创建、编辑、增删/排序版本、激活、完成和归档 API 已实现；激活后版本集合冻结。
- `auto_version_id` 使用非空部分唯一索引，保证同一版本只能有一个自动审核单；该版本仍可按权限加入人工批量审核单。

### 6.14 `sg_review_list_version`

审核单的有序版本关系。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `review_list_id` | bigint | 是 | 审核单 |
| `version_id` | bigint | 是 | 版本 |
| `sort_order` | integer | 是 | 审核顺序 |
| `create_by` | varchar(64) | 是 | 创建账号 |
| `create_time` | timestamp(0) | 是 | 创建时间 |

主键：

```text
(review_list_id, version_id)
```

约束：

- `(review_list_id, sort_order)` 唯一。
- 审核单和版本必须属于同一个项目。
- 调整顺序在一个事务内完成。

### 6.15 `sg_storage_root`

管理员维护的 NAS/UNC 根目录白名单。它只保存路径和密钥引用，不保存用户名、密码或明文凭据。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `storage_root_id` | bigint | 是 | 主键 |
| `root_code` | varchar(50) | 是 | 稳定代码，例如 `planning_nas_01` |
| `root_name` | varchar(120) | 是 | 显示名称 |
| `protocol` | varchar(20) | 是 | MVP 固定为 `smb_unc` |
| `unc_root_path` | varchar(1000) | 是 | 规范化 UNC 根路径，例如 `\\192.168.10.64\策划部` |
| `root_path_key` | varchar(1000) | 是 | 大小写不敏感的规范化唯一键，不向普通前端返回 |
| `credential_ref` | varchar(200) | 否 | 外部密钥或服务账号配置引用，不是凭据本身 |
| `root_status` | varchar(20) | 是 | `enabled` 或 `disabled` |
| `last_probe_status` | varchar(20) | 是 | `unknown`、`healthy`、`unreachable`、`unwritable` |
| `last_probe_time` | timestamp(0) | 否 | 最近探测时间 |
| `last_error_key` | varchar(100) | 否 | 最近安全错误键 |
| `last_error_message` | varchar(500) | 否 | 已净化的错误摘要，不含凭据和堆栈 |
| 通用审计字段 |  | 是 | 见 5.2 |

约束：

- `root_code` 和 `root_path_key` 在活动记录中唯一。
- `unc_root_path` 必须是 UNC 根路径，不能包含 `..`、通配符、驱动器相对路径或 URL。
- 修改根路径不能静默改变既有项目；既有项目使用 `sg_project_storage` 中的快照。
- `disabled` 只禁止新项目选择，不能让既有项目路径自动失效。
- 根目录探测、添加、修改和停用只允许平台管理员，并记录操作日志。

### 6.16 `sg_project_storage`

项目与 NAS 的一对一存储绑定及不可变路径快照。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `project_id` | bigint | 是 | 主键并关联 `sg_project` |
| `storage_root_id` | bigint | 是 | 关联 `sg_storage_root` |
| `root_path_snapshot` | varchar(1000) | 是 | 创建项目时的 UNC 根路径快照 |
| `project_type_dir_snapshot` | varchar(120) | 是 | 项目类型目录快照，MVP 为 `AI影视短片` |
| `project_dir_name_snapshot` | varchar(240) | 是 | 经确认的项目目录名快照 |
| `project_relative_path` | varchar(1200) | 是 | 相对根目录路径 |
| `project_path_snapshot` | varchar(2000) | 是 | 完整 UNC 项目路径快照，用于授权后查看和复制 |
| `project_path_key` | varchar(2000) | 是 | 大小写不敏感规范化路径键 |
| `storage_status` | varchar(20) | 是 | 项目存储状态 |
| `initialized_time` | timestamp(0) | 否 | 初始目录全部就绪时间 |
| `last_error_key` | varchar(100) | 否 | 最近错误键 |
| `last_error_message` | varchar(500) | 否 | 已净化的错误摘要 |
| `lock_version` | integer | 是 | 重试和迁移的乐观锁 |
| `create_by` / `create_time` |  | 是 | 创建审计 |
| `update_by` / `update_time` |  | 是 | 更新审计 |

项目存储状态：

| 代码 | 中文 | 允许动作 |
| --- | --- | --- |
| `initializing` | 初始化中 | 查询状态、后台执行初始化 |
| `ready` | 可用 | 正常业务读写 |
| `failed` | 初始化失败 | 查询、重试、在无业务数据时受控撤销 |
| `migrating` | 迁移中 | 只读；MVP 不提供普通迁移入口 |

约束：

- `project_id` 唯一，一个项目在 MVP 中只有一个活动存储绑定。
- `(storage_root_id, project_path_key)` 唯一，防止大小写变体或重复请求指向同一目录。
- 路径快照创建后不得通过项目普通编辑接口修改。
- `storage_status = 'ready'` 必须意味着项目根目录及 `ASSET\Character`、`ASSET\Environment`、`ASSET\Prop`、`VIDEO` 已经幂等确认存在且可写。
- 平台不物理删除任何无法证明为“本次操作新建且为空”的目录。

### 6.17 `sg_storage_operation`

目录初始化与动态目录创建的持久化 Outbox/执行记录，用于跨 PostgreSQL 与 NAS 的重试、租约和补偿。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `operation_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `operation_type` | varchar(30) | 是 | 操作类型 |
| `aggregate_type` | varchar(20) | 是 | `project`、`episode`、`shot`、`asset` |
| `aggregate_id` | bigint | 是 | 目标业务对象 |
| `target_relative_path` | varchar(1200) | 是 | 目标相对路径；项目初始化/项目级对账相对存储根目录，其他操作相对项目根目录 |
| `operation_status` | varchar(30) | 是 | 执行状态 |
| `idempotency_key` | varchar(100) | 是 | 服务端生成的稳定幂等键 |
| `attempt_count` | integer | 是 | 已执行次数 |
| `next_retry_time` | timestamp(0) | 否 | 下次允许重试时间 |
| `lease_owner` | varchar(100) | 否 | Worker 租约持有者 |
| `lease_until` | timestamp(0) | 否 | 租约过期时间 |
| `started_time` | timestamp(0) | 否 | 开始时间 |
| `completed_time` | timestamp(0) | 否 | 成功或最终失败时间 |
| `last_error_key` | varchar(100) | 否 | 最近错误键 |
| `last_error_message` | varchar(500) | 否 | 已净化错误摘要 |
| `create_by` / `create_time` |  | 是 | 创建审计 |
| `update_time` | timestamp(0) | 是 | 更新时间 |

操作类型：

```text
initialize_project
ensure_episode_directory
ensure_shot_directory
ensure_asset_directory
reconcile_directory
```

当前 Worker 执行状态：

```text
pending → processing → succeeded
                    ├→ retry_wait → processing
                    └→ failed

processing 租约过期 → 由新 owner 重新领取 processing
failed ──人工重试──→ 新建 reconcile_directory(pending)
```

`compensation_pending`、`compensated`、`compensation_failed` 是数据库为后续受控补偿保留的终态，当前 Worker 不产生这些状态，也不自动删除物理目录。

规则：

- `idempotency_key` 唯一；重复消费返回原操作，不重复创建目录。
- Worker 只在 PostgreSQL、显式配置 `SHOT_GRID_STORAGE_WORKER_ENABLED=true` 且当前进程仍持有 Application Leader 时，由内部任务 `_shot_grid_storage_outbox` 消费；所有环境样例默认关闭。
- Worker 使用 PostgreSQL `FOR UPDATE SKIP LOCKED` 和有期限租约；每次领取生成唯一 owner，续租与终态回写同时校验 owner 和 attempt。进程退出或租约过期后可由其他 Worker 接管，旧持有者不能覆盖新结果。
- 领取并提交、事务外 NAS I/O、结果回写是三个边界；数据库事务内不得执行或等待 SMB I/O。
- 长 I/O 按配置心跳续租。`operation_timeout_seconds` 是软超时诊断阈值，不取消 `asyncio.to_thread` 中仍运行的文件系统调用；租约丢失时也先等待物理 I/O 退出，避免旧线程脱离受管任务。若租约已经被接管，旧、新 Worker 的物理 I/O 仍可能短暂重叠；当前执行器只允许幂等目录创建和随机 `O_EXCL` 写探针，owner + attempt fencing 只保证旧持有者不能覆盖数据库终态。
- 正常关机或 Application Leader 失锁时必须先停止新领取、取消 Scheduler Job，再显式 drain 已登记的 NAS Job；当前操作完成 I/O 与租约收尾前，不得提前关闭全局数据库引擎或在同一进程重新竞争 Leader。
- 当前单轮最多按 `batch_size` 串行消费，尚未提供批内并发配置；后续如引入并发必须单独冻结 NAS 限流和同聚合互斥规则。
- 每次执行都要重新规范化路径，并确认最终解析路径位于本操作的约束根内：项目初始化/项目级对账以 NAS 存储根为约束根，动态目录以项目根为约束根。
- `ensure_*` 对已存在且类型正确的目录视为幂等成功；路径被文件占用或越界必须失败。
- 项目初始化与项目级 `reconcile_directory` 的 `target_relative_path` 必须等于 `sg_project_storage.project_relative_path`，从 `sg_storage_root` 拼接；集、镜头和资产级 `ensure_*`/`reconcile_directory` 从项目根目录拼接目标。
- 初始化项目会幂等确认项目根、`ASSET`、`ASSET\Character`、`ASSET\Environment`、`ASSET\Prop` 和 `VIDEO`，并在项目根执行随机文件写探针；不会创建场次目录或资产制作分项目录。
- 每一级已存在路径都拒绝符号链接和 Windows reparse point，最终解析路径必须仍在配置根目录内；路径被普通文件占用时最终失败。
- 补偿仍是后续能力。未来只能处理有持久证据证明为本操作新建且仍为空的目录；预先存在目录永不自动删除。

### 6.18 `sg_version_submission`

上传完成到正式版本创建之间的暂存编排记录。大视频复制到 NAS 不占用长数据库事务，也不会提前生成对业务用户可见的半成品版本。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `submission_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `task_id` | bigint | 是 | 所属任务 |
| `source_file_id` | varchar(36) | 迁移兼容 | 候选 01 的平台源文件镜像；新业务读取 `sg_version_submission_file` |
| `reserved_version_no` | integer | 是 | 为本次提交保留的任务内版本号 |
| `generated_at_ms` | bigint | 是 | 业务文件名时间戳，只生成一次 |
| `business_file_name` | varchar(255) | 迁移兼容 | 候选 01 业务文件名镜像 |
| `target_relative_path` | varchar(1200) | 迁移兼容 | 候选 01 NAS 目标路径镜像 |
| `temporary_relative_path` | varchar(1200) | 迁移兼容 | 候选 01 临时路径镜像 |
| `source_sha256` | char(64) | 迁移兼容 | 候选 01 摘要镜像 |
| `source_file_size` | bigint | 迁移兼容 | 候选 01 文件大小镜像 |
| `changelog` | text | 是 | 本轮修改说明 |
| `ai_params` | jsonb | 否 | 可选生成参数快照 |
| `submission_status` | varchar(20) | 是 | 提交编排状态 |
| `submitted_by` | bigint | 是 | 提交用户 |
| `idempotency_key` | varchar(100) | 是 | 客户端幂等键 |
| `attempt_count` | integer | 是 | NAS 发布尝试次数 |
| `lease_owner` / `lease_until` |  | 否 | Worker 租约 |
| `last_error_key` | varchar(100) | 否 | 最近错误键 |
| `last_error_message` | varchar(500) | 否 | 已净化错误摘要 |
| `create_time` / `update_time` |  | 是 | 时间审计 |

提交状态：

```text
pending → publishing → published → committing → committed
                     └→ failed ──重试──→ pending
```

约束与规则：

- `UNIQUE(task_id, reserved_version_no)`。
- `UNIQUE(task_id, submitted_by, idempotency_key)`；相同请求重试返回同一提交记录、版本号、时间戳和业务文件名。
- 每个提交至少有 1 个且不超过后端能力响应上限的 `sg_version_submission_file`；源文件唯一性和候选顺序由子表约束。
- 每个任务同时最多一个 `pending/publishing/published/committing/failed` 未解决提交，使用 PostgreSQL 部分唯一索引保证；失败后必须重试原提交，不能通过新建提交跳过保留版本号。
- `publishing/committing` 必须同时具有非空租约 owner 和到期时间，其余状态必须同时为空；`failed` 必须同时具有非空安全错误键和摘要，其余状态必须同时为空，由两个 `CHECK` 保证。
- 暂存创建时锁定任务并保留版本号；任务仍保持 `in_progress` 或 `revision`，直到正式版本提交成功。
- 首版任务不存在 open 问题；修订任务暂存时必须在同一事务为锁内重查的每条 open 问题创建一条 `sg_version_issue_response`，不得缺少或多出。问题集合或处理说明属于幂等命令哈希的一部分。
- 暂存事务同时为全部候选源文件创建 `businessType=shotgrid_version_submission` 临时平台文件引用；失败提交仍受引用保护，不作为无引用文件清理。正式版本事务把全部引用切换为 `businessType=shotgrid_version_candidate` 并分别绑定候选。
- 暂存和正式版本事务在锁任务、提交与版本资源前，必须先锁定所属项目行并复核项目未归档；统一锁序为 `project → task/submission → version`。这是防止首个版本与项目类型/画幅修改并发穿透冻结规则的上线门禁。
- 每次领取 `publishing` attempt 为尚未成功的每个候选生成含 `submissionId/submissionFileId/attempt/random` 的同目录唯一临时名；逐文件独占写入、校验真实大小和 SHA-256 后无覆盖原子发布。已发布候选在重试时只复核目标摘要和大小，不重复覆盖。
- 只有全部 `sg_version_submission_file.publish_status='published'`，父提交才能进入 `published/committing`。任一候选失败时不创建或暴露半个正式版本。
- `committing` 在一个短数据库事务中创建一个 `sg_version`、全部 `sg_version_candidate`、候选级 `sg_version_file`/`sys_file_reference`、一个自动审核单和关系，并把任务改为 `pending_review`。
- 只有 `committed` 产生通过 `sg_version.submission_id` 关联的正式版本并对业务列表可见；`sg_version_submission` 不保存重复的 `version_id`，状态响应通过该关系反查 `versionId/reviewListId`。`failed` 只在提交状态页和管理员诊断页可见。
- 数据库提交失败时保留已校验的 NAS 文件并重试 `committing`；不得重新分配版本号或覆盖目标文件。

#### 6.18.1 `sg_version_submission_file`

一次版本提交中的有序候选源文件和逐文件 NAS 发布状态。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `submission_file_id` | bigint | 是 | 主键 |
| `submission_id` | bigint | 是 | 所属提交批次 |
| `candidate_no` | integer | 是 | 轮次内连续候选号 |
| `source_file_id` | varchar(36) | 是 | 平台私有源文件 |
| `business_file_name` | varchar(255) | 是 | 含版本号与候选号的不可变业务文件名 |
| `target_relative_path` / `temporary_relative_path` | varchar(1200) | 是 | NAS 正式/临时相对路径 |
| `source_sha256` / `source_file_size` |  | 是 | 源文件摘要与大小快照 |
| `candidate_note` | varchar(500) | 否 | 制作人候选说明 |
| `sort_order` | integer | 是 | 创建命令冻结的展示顺序 |
| `publish_status` | varchar(20) | 是 | `pending/publishing/published/failed` |
| `published_time` | timestamp(0) | 条件必填 | 已发布时必填 |
| `last_error_key` / `last_error_message` |  | 条件必填 | 失败时必填 |
| `create_time` / `update_time` |  | 是 | 时间审计 |

约束：`UNIQUE(submission_id,candidate_no)`、`UNIQUE(source_file_id)`、`candidate_no>0`、`source_file_size>0`。候选号按 create 中 `sortOrder/clientFileKey` 的稳定有序列表分配，不按网络上传完成顺序分配；同一批次内容摘要重复必须在创建事务中拒绝。

### 6.19 `sg_import_batch`

镜头或资产 Excel 从预检查到正式提交的持久化批次摘要。逐行规范化数据和错误明细在提交前使用 Redis 短期保存；正式批次、来源摘要和提交结果进入 PostgreSQL。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `batch_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `import_type` | varchar(20) | 是 | `shot` 或 `asset` |
| `original_file_name` | varchar(255) | 是 | 原文件名，不含本地临时路径 |
| `file_sha256` | char(64) | 是 | 原文件摘要 |
| `template_version` | varchar(30) | 是 | 模板版本 |
| `batch_status` | varchar(20) | 是 | 批次状态 |
| `total_rows` | integer | 是 | 数据总行数 |
| `valid_rows` | integer | 是 | 可导入行数 |
| `warning_rows` | integer | 是 | 有警告行数 |
| `error_rows` | integer | 是 | 有错误行数 |
| `committed_rows` | integer | 是 | 已正式提交行数，默认 0 |
| `preview_token_hash` | char(64) | 否 | 预览 Token 哈希，不保存明文 Token |
| `preview_expires_time` | timestamp(0) | 否 | 预览数据到期时间 |
| `idempotency_key` | varchar(100) | 否 | 正式提交幂等键 |
| `selection_hash` | char(64) | 否 | 正式提交选中行及来源文件的稳定摘要 |
| `result_summary` | jsonb | 否 | 首次成功提交的结果快照，用于 Redis 过期后幂等重放 |
| `last_error_key` | varchar(100) | 否 | 最近失败错误键 |
| `last_error_message` | varchar(500) | 否 | 已净化的失败摘要 |
| `previewed_by` | bigint | 是 | 预检查用户 |
| `committed_by` | bigint | 否 | 正式提交用户 |
| `create_time` / `update_time` |  | 是 | 时间审计 |
| `committed_time` | timestamp(0) | 否 | 正式提交完成时间 |

状态：

```text
previewed → committing → committed
                    └──→ failed
previewed → expired
```

约束与规则：

- `CHECK(import_type IN ('shot', 'asset'))`；
- `CHECK(batch_status IN ('previewed', 'committing', 'committed', 'failed', 'expired'))`；
- 同一批次只能由预检查用户或有全项目权限的管理员提交；
- `UNIQUE(project_id, import_type, committed_by, idempotency_key)` 对非空幂等键生效；
- `previewed/expired` 不保存选择摘要或结果，`committing/failed` 保存选择摘要但不保存成功结果，`committed` 必须同时保存二者；
- 同一幂等键只有在 `selection_hash` 相同时才返回首次 `result_summary`；同键不同选择返回冲突；
- 明文导入 Token 和完整规范化行数据不写入普通日志；
- 若业务要求长期留存原始 Excel，应另存为平台受保护文件并建立业务引用，本表不能保存不受控临时路径。

### 6.20 `sg_shot_asset_requirement`

镜头表先于资产表导入时保存的资产需求。它不是正式资产，也不能自动产生资产任务。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `requirement_id` | bigint | 是 | 主键 |
| `project_id` | bigint | 是 | 所属项目 |
| `shot_id` | bigint | 是 | 来源镜头 |
| `asset_type` | varchar(20) | 是 | `Character`、`Environment`、`Prop` |
| `raw_name` | varchar(200) | 是 | Excel 原始名称 |
| `normalized_name` | varchar(200) | 是 | 规范化匹配名称 |
| `resolution_status` | varchar(20) | 是 | 解析状态 |
| `asset_id` | bigint | 否 | 唯一匹配的正式资产 |
| `source_import_batch_id` | bigint | 是 | 来源镜头导入批次 |
| `resolved_by` | bigint | 否 | 自动匹配为空，人工处理保存用户 |
| `resolved_time` | timestamp(0) | 否 | 解决时间 |
| `resolution_reason` | varchar(500) | 否 | 人工选择或忽略原因 |
| `create_by` / `create_time` |  | 是 | 创建审计 |
| `update_by` / `update_time` |  | 否 | 更新审计 |

状态：

```text
pending → matched
       ├→ conflict → matched | ignored
       └→ ignored
```

约束与规则：

- `UNIQUE(shot_id, asset_type, normalized_name)`；
- `matched` 时 `asset_id` 必填，且资产必须属于同一项目和相同资产类型；
- `pending`、`conflict`、`ignored` 时不建立正式 `sg_shot_asset`；
- 自动匹配仅允许唯一候选，多个候选不得按创建时间或主键静默选择；
- 人工解决和忽略必须使用动作接口并保留操作者、时间和原因；
- `raw_name` 是来源审计，不随资产改名被覆盖。

### 6.21 外键、唯一约束与查询索引总则

外键策略：

- 业务主表、任务、版本、审核、存储绑定和平台用户/文件引用默认 `ON DELETE RESTRICT`，不使用级联物理删除历史。
- 项目、集、场次、镜头和资产通过业务归档与 `del_flag` 管理生命周期；数据库外键不代替 Service 的归档前置校验。
- `sg_shot_asset`、`sg_review_list_version` 等关系表也不依赖普通接口的物理级联；管理员物理治理必须先生成影响清单并独立执行。
- 冗余保存的 `project_id`、`episode_id` 只用于权限、高频查询和组合约束，写入时必须通过组合外键或 Service 保证父级一致。

PostgreSQL 必须至少提供以下唯一性：

```sql
-- 有效项目代号大小写不敏感唯一
CREATE UNIQUE INDEX uk_sg_project_code_active
ON sg_project (lower(project_code))
WHERE project_status <> 'archived' AND del_flag = '0';

-- 历史项目内制作人缩写字段仍保留唯一索引，仅用于兼容存量数据
CREATE UNIQUE INDEX uk_sg_project_member_producer_code
ON sg_project_member (project_id, lower(producer_code))
WHERE producer_code IS NOT NULL AND member_status = 'active';

-- 同一根目录下项目路径唯一
CREATE UNIQUE INDEX uk_sg_project_storage_path
ON sg_project_storage (storage_root_id, project_path_key);

-- 场内镜头号唯一；物理目录通过 scene_no + shot_no 保持同集内唯一
CREATE UNIQUE INDEX uk_sg_shot_scene_no_active
ON sg_shot (scene_id, shot_no)
WHERE del_flag = '0';

-- 同类型资产规范化名称唯一
CREATE UNIQUE INDEX uk_sg_asset_name_active
ON sg_asset (project_id, asset_type, asset_name_key)
WHERE lifecycle_status = 'active' AND del_flag = '0';

CREATE UNIQUE INDEX uk_sg_asset_storage_path
ON sg_asset (project_id, storage_path_key)
WHERE del_flag = '0';

-- 同一资产内已命名制作分项唯一；未命名分项由主键和导入幂等关系识别
CREATE UNIQUE INDEX uk_sg_asset_item_name_active
ON sg_asset_item (asset_id, production_item_key)
WHERE production_item_key IS NOT NULL
  AND lifecycle_status = 'active'
  AND del_flag = '0';

CREATE UNIQUE INDEX uk_sg_asset_item_import_row
ON sg_asset_item (project_id, import_row_key)
WHERE import_row_key IS NOT NULL AND del_flag = '0';

-- 同一平台源文件只能作为一个提交候选
CREATE UNIQUE INDEX uk_sg_submission_file_source
ON sg_version_submission_file (source_file_id);

-- 一个版本轮次内候选号唯一
ALTER TABLE sg_version_candidate
ADD CONSTRAINT uk_sg_candidate_version_no UNIQUE (version_id, candidate_no);

-- 每任务最多一个未解决版本提交；failed 必须重试原记录
CREATE UNIQUE INDEX uk_sg_version_submission_active
ON sg_version_submission (task_id)
WHERE submission_status IN ('pending', 'publishing', 'published', 'committing', 'failed');

CREATE UNIQUE INDEX uk_sg_import_batch_idempotency
ON sg_import_batch (project_id, import_type, committed_by, idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX uk_sg_shot_asset_requirement_key
ON sg_shot_asset_requirement (shot_id, asset_type, normalized_name);
```

高频索引至少覆盖：

- `sg_project_member(user_id, project_id)`；
- `sg_episode(project_id, lifecycle_status, sort_order)`；
- `sg_scene(episode_id, lifecycle_status, sort_order)`；
- `sg_shot(project_id, episode_id, scene_id, lifecycle_status, sort_order)`；
- `sg_asset(project_id, asset_type, lifecycle_status, sort_order)`；
- `sg_asset_item(project_id, asset_id, lifecycle_status, sort_order)`；
- `sg_task(project_id, assignee_user_id, task_status, due_date)`；
- `sg_version(task_id, version_no DESC)`；
- `sg_note(version_id, note_status, create_time DESC)`，按来源版本查询问题；
- `sg_note(project_id, note_status, note_id)`，按任务联结版本后查询全部 open 问题；
- `sg_version_issue_response(submission_id, note_id)` 唯一，并增加 `note_id` 查询索引；
- `sg_issue_verification(note_id, checked_version_id)` 唯一，并增加 `checked_version_id` 查询索引；
- `sg_review_list(project_id, review_status, create_time DESC)`；
- `sg_storage_operation(operation_status, next_retry_time, lease_until)`；
- `sg_storage_operation(project_id, aggregate_type, aggregate_id, operation_id DESC)`，用于按业务对象取得最新目录操作；
- `sg_storage_operation(project_id, create_time DESC, operation_id DESC)`，用于项目目录诊断分页；
- `sg_version_submission(submission_status, lease_until, update_time)`。
- `sg_import_batch(project_id, import_type, batch_status, create_time DESC)`；
- `sg_shot_asset_requirement(project_id, resolution_status, asset_type, normalized_name)`。

所有状态列、二选一任务归属、正数编号、非负时长/文件大小和归一化状态值必须使用 `CHECK` 约束兜底；不能只依赖 Pydantic 校验。

## 7. 聚合状态规则

### 7.1 镜头、制作分项和资产状态

镜头和资产制作分项状态不由普通成员手动设置，根据其唯一任务和版本聚合：

| 代码 | 中文 | 建议计算条件 |
| --- | --- | --- |
| `unassigned` | 未分配 | 尚未创建任务 |
| `not_started` | 待开工 | 唯一任务为 `not_started` |
| `preparing` | 目录准备中 | 已确认开工，等待目录成功 |
| `in_progress` | 制作中 | 唯一任务为 `in_progress` |
| `reviewing` | 审核中 | 唯一任务为 `pending_review` |
| `revision` | 修改中 | 唯一任务为 `revision` |
| `completed` | 已完成 | 唯一任务为 `completed` 且存在最终版本 |

资产列表与详情返回 `itemStatusCounts`，固定包含 `unassigned/not_started/preparing/in_progress/reviewing/revision/completed` 七个非负整数键，仅统计活动且未删除分项。父级状态按 `revision → reviewing → in_progress → preparing → unassigned → not_started` 聚合；至少有一个活动分项且全部完成才为 `completed`，无活动分项为 `unassigned`。父级 `task.start` 仅表示可进入分项选择，至少存在一个实际可开工分项才返回；真正 start 必须对选中分项任务提交，不能整资产开工。 普通成员不能直接写入任一聚合状态。

### 7.2 任务状态流转

```text
not_started
  ├─镜头：管理人确认资产齐备并开工─┐
  └─资产：管理人逐分项确认开工───┴→ preparing → 目录就绪 → in_progress
     （已有成功目录可直接进入 in_progress）

in_progress
  └─上传并提交版本──────→ pending_review

pending_review
  ├─确认通过────────────→ completed
  ├─退回修改────────────→ revision
  └─稍后决定────────────→ pending_review

revision
  └─上传并提交新版本────→ pending_review
```

规则：

- 上传文件成功不等于版本提交成功。
- 任务存在活动 `sg_version_submission` 时禁止创建第二次提交；NAS 发布期间任务仍保持原 `in_progress` 或 `revision`。
- 创建版本、业务文件名、文件引用、自动审核单和任务转为 `pending_review` 在同一业务事务完成。
- 审核确认通过后版本直接转为 `final`，任务转为 `completed`。
- 审核确认通过前必须逐条确认全部带入问题已在当前版本解决，且任务不存在任何 open 问题。
- 审核退回前必须逐条确认全部带入问题，并至少保留一条 `still_present` 问题或创建一条绑定当前版本的新问题；版本转为 `rejected`，任务转为 `revision`，旧版本不可覆盖。

### 7.3 版本状态流转

```text
pending_review
  ├─approve──────→ final
  ├─reject───────→ rejected
  └─defer────────→ pending_review

rejected
  └─不可改回；修订必须创建新版本

final
  └─MVP 中不可回退
```

### 7.3.1 修改问题跨版本状态机

```text
来源版本提出问题
  └─创建──────────────→ open（originVersionId 固定）

open
  └─制作人提交后续版本──→ open + 该版本处理说明
       ├─审核确认 resolved──────→ resolved（记录 resolvedInVersionId）
       └─审核确认 still_present─→ open（继续带入下一版本）

resolved
  └─不可重新打开；相似问题必须在当时版本新建问题
```

- 处理说明不会改变问题状态；制作人无权自行关闭问题。
- 一个问题跨 V001、V002、V003 仍是同一 `note_id`，通过不同版本的处理说明和确认记录展示过程，不复制问题主记录。
- 当前版本新建的问题不在同一版本自我确认；退回并形成下一版本后才进入历史问题确认列表。

### 7.4 版本提交与 NAS 发布状态机

```text
pending
  └─Worker 取得租约────────→ publishing

publishing
  ├─全部候选逐个临时写入、摘要校验、原子改名成功→ published
  └─可恢复或最终失败────────────→ failed

published
  └─开始短数据库事务────────────→ committing

committing
  ├─版本、引用、审核单、任务全部提交→ committed
  └─事务失败────────────────────→ published（等待重试）

failed
  └─授权重试且源文件仍有效────────→ pending
```

规则：

- `pending` 到 `published` 只处理 NAS 文件，不修改任务为待审核。
- `published` 要求本批全部候选文件均已按各自最终业务文件名存在，且摘要和大小与平台源文件一致；部分候选成功只能保留为可恢复发布证据，不能把父提交标为 `published`。
- `committed` 是唯一会生成一个正式版本轮次、全部候选并把任务改为 `pending_review` 的终态。
- 前端只能在 `committed` 显示提交成功；`pending/publishing/published/committing` 均为处理中，`failed` 仍占用该任务且只能重试原提交记录。
- MVP 不提供放弃失败提交并跳过保留版本号的普通入口；必须先重试成功或由管理员完成明确对账和清理。
- 用户页面将 `pending/publishing/published/committing` 统一显示为“正在提交”，将 `failed` 显示为“提交失败”，不能显示成版本待审核。
- 版本发布 Worker 默认关闭，只在 PostgreSQL、`SHOT_GRID_VERSION_WORKER_ENABLED=true` 且当前进程仍持有 Application Leader 时注册内部任务 `_shot_grid_version_publisher`；正常关机或失锁必须先停止新领取并 drain 活动 Job。
- 领取、NAS I/O、正式版本提交和结果回写保持“短事务 → 事务外 I/O → 短事务”；租约、心跳和 owner + attempt fencing 防止迟到结果覆盖新终态。软超时只用于诊断，不声称能够硬杀仍运行的 SMB 文件复制。
- 自动化测试只能显式 `allow_local_root=True` 使用临时本地目录；该路径不能冒充真实 Windows Worker 账号、NAS/AD/共享 ACL 和隔离 UNC E2E。

### 7.5 项目存储状态机

```text
initializing
  ├─初始目录全部确认可写──→ ready
  └─初始化失败──────────→ failed

failed
  └─项目管理人或管理员重试，新建项目级 reconcile_directory──→ initializing

ready
  └─受控迁移（后续能力）──→ migrating ──→ ready | failed
```

- 项目数据库记录可以在 `initializing` 时存在，但不能被描述为可正常使用。
- `ready` 前禁止创建集、场次、镜头、资产和版本提交。
- 初始化失败不自动删除项目；用户可查看净化错误、执行幂等重试，或在没有业务数据时由管理员受控撤销。
- 项目级初始化或对账成功才把 `sg_project_storage` 改为 `ready`，最终失败才改为 `failed`。动态集、镜头或资产目录失败只记录安全错误，不把已经就绪的项目根存储降级为初始化失败。
- 集、镜头和资产响应中的 `directoryStatus` 是最新目录操作的只读映射：尚未开始制作且不存在对象目录操作时为 `not_created`，`pending/processing/retry_wait → pending`，`succeeded → ready`，`failed → failed`。补偿状态当前未由 Worker 产生；`not_created` 不能默认解释为 `ready`。
- 人工重试不覆盖失败操作，也不创建第二条 `initialize_project`。项目及动态目录均创建新的 `reconcile_directory`，旧操作继续作为不可变执行历史。

### 7.6 项目生命周期与当前阶段

```text
preparing ──开始制作──→ active ──完成校验──→ completed ──归档──→ archived
     └──────────────────────归档────────────────────────────→ archived
active ─────────────────────归档────────────────────────────→ archived
```

- `preparing` 是项目创建后的默认业务状态，与存储 `initializing/ready` 分开。
- `completed` 必须通过动作接口设置；所有纳入交付的活动镜头和资产制作分项都必须存在已完成任务与唯一最终版本，资产完成状态由其全部活动分项聚合。
- `archived` 为只读终态，MVP 不提供恢复接口。
- 当前代码对 `completed`、`archived` 项目下的集、场次、镜头、资产和资产制作分项创建/修改/归档在锁内拒绝；镜头与资产 Excel preview 普通读取项目状态并拒绝，commit 再以 `FOR UPDATE` 锁定项目重检，稳定返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。项目 `completed` 时 `allowedActions` 只可包含已授权的 `project.archive`，`archived` 时为空；镜头、资产和制作分项在两种状态下均不返回写动作。
- 上述终态镜像门禁确认了项目自身、集、场次、镜头、资产、资产制作分项及两类 Excel 导入。成员、任务、版本、审核、文件和目录操作等其余全域写接口尚未统一完成同一轮治理，文档和前端不得将本批门禁外推为全系统不可变保证。
- `current_phase` 只允许 `planning`、`asset_production`、`shot_production`、`review`、`delivery`、`completed`，对应展示文案固定为“制作规划、资产制作、镜头制作、版本审核、交付确认、项目完成”；由项目管理人或管理员显式调整，它不替代任务状态机。

### 7.7 审核单状态机

```text
自动单版本审核单：active ── approve | reject ──→ completed ──→ archived
                         └─ defer ─────────────→ active

人工批量审核单：draft ── activate ──→ active ── complete ──→ completed ──→ archived
```

- 自动审核单创建即为 `active`，只包含对应版本，不能手工增删或排序。
- 人工批量审核单只有 `draft` 可修改版本集合与顺序；`active` 后集合冻结。
- 人工批量审核单完成不直接改变其中版本状态；每个版本仍必须执行独立审核动作。

### 7.8 导入批次与资产需求状态机

导入批次：

```text
previewed ──确认提交──→ committing ──事务成功──→ committed
    │                         └─事务失败──────→ failed
    └─预览 TTL 到期且未提交───────────────→ expired
```

镜头资产需求：

```text
pending ──唯一资产自动匹配──→ matched
   ├─候选不唯一或历史数据冲突──→ conflict ──人工选择──→ matched
   └─项目管理人明确忽略─────────→ ignored
conflict ──明确忽略──────────→ ignored
```

- 正式提交使用 `SELECT ... FOR UPDATE` 锁定批次；`committing`、全部领域写入和 `committed` 在同一个数据库事务内完成。
- 任一选中行失败时该事务整体回滚；随后仅用独立短事务把批次记为 `failed` 并保存净化错误摘要，不得补写任何领域实体。
- `failed` 批次不保留半成功集、场次、镜头、资产、关系或目录操作，重新导入必须重新预检查；导入流程本身不得创建任务。
- `matched` 必须同时存在有效 `asset_id` 和幂等 `sg_shot_asset` 关系。
- 资产表导入只自动处理唯一匹配；冲突不能通过字典、前端排序或最早创建规则静默消解。

## 8. 权限模型

权限判断必须同时通过：

```text
已登录
AND 拥有平台接口权限
AND 是项目成员或拥有明确的全项目管理权限
AND 目标资源确实属于该项目
AND 当前项目角色允许该业务动作
```

独立业务前端还必须执行“当前账号平台权限 ∩ 详情响应 `allowedActions`”双门禁。`version.add`、`version.query`、`version.retry`、`version.list` 和 `file.download` 是独立能力，不能因用户能打开任务详情就推导其可上传、查询提交、重试、查看历史或下载文件；后端仍按实时项目角色、任务负责人、任务/项目状态和文件关系重新授权。

项目角色与平台角色保持两层事实，但成员生命周期通过专用服务维护以下固定映射：

```text
sg_project_member.project_role = director
  -> sys_role.role_key = shotgrid_admin

sg_project_member.project_role = creator
  -> sys_role.role_key = shotgrid_creator
```

该映射只确保用户具备候选平台接口权限，不扩大项目数据范围。平台角色存在不代表项目成员存在，项目成员存在也不代表平台接口权限存在；最终授权仍是两层交集及资源/状态门禁。

### 8.1 平台权限码

第一批权限码：

| 权限码 | 说明 |
| --- | --- |
| `shotgrid:storageRoot:list` | 查看可选 NAS 根目录 |
| `shotgrid:storageRoot:query` | 查看 NAS 根目录详情与健康状态 |
| `shotgrid:storageRoot:add` | 新增 NAS 根目录配置 |
| `shotgrid:storageRoot:edit` | 修改或停用 NAS 根目录配置 |
| `shotgrid:storageRoot:probe` | 执行 NAS 可达性和写权限探测 |
| `shotgrid:navigation:list` | 获取当前用户 Shot Grid 范围导航 |
| `shotgrid:project:list` | 查看项目列表 |
| `shotgrid:project:query` | 查看项目详情 |
| `shotgrid:project:add` | 创建项目 |
| `shotgrid:project:edit` | 修改项目 |
| `shotgrid:project:archive` | 归档项目 |
| `shotgrid:project:start` | 将筹备中项目转为进行中 |
| `shotgrid:project:complete` | 完成项目并执行完整性校验 |
| `shotgrid:project:overview` | 查看项目概览统计 |
| `shotgrid:storage:path` | 查看和复制所属项目 NAS 路径 |
| `shotgrid:storage:retry` | 重试项目或业务目录初始化 |
| `shotgrid:member:list` | 查看项目成员 |
| `shotgrid:member:add` | 添加成员 |
| `shotgrid:member:edit` | 修改项目角色 |
| `shotgrid:member:remove` | 移除成员 |
| `shotgrid:episode:list` | 查看集列表 |
| `shotgrid:episode:add` | 创建集 |
| `shotgrid:episode:edit` | 修改集 |
| `shotgrid:episode:archive` | 归档集 |
| `shotgrid:scene:list` | 查看场次 |
| `shotgrid:scene:query` | 查看场次详情 |
| `shotgrid:scene:add` | 创建场次 |
| `shotgrid:scene:edit` | 修改场次 |
| `shotgrid:scene:archive` | 归档场次 |
| `shotgrid:shot:list` | 查看镜头 |
| `shotgrid:shot:query` | 查看镜头详情 |
| `shotgrid:shot:add` | 创建镜头 |
| `shotgrid:shot:edit` | 修改镜头 |
| `shotgrid:shot:archive` | 归档镜头 |
| `shotgrid:shot:import` | 导入镜头表 |
| `shotgrid:asset:list` | 查看资产列表 |
| `shotgrid:asset:query` | 查看资产详情 |
| `shotgrid:asset:add` | 创建资产 |
| `shotgrid:asset:edit` | 修改资产 |
| `shotgrid:asset:archive` | 归档资产 |
| `shotgrid:asset:import` | 导入资产表 |
| `shotgrid:assetRequirement:list` | 查看镜头资产待匹配需求 |
| `shotgrid:assetRequirement:resolve` | 人工选择唯一正式资产并完成匹配 |
| `shotgrid:assetRequirement:ignore` | 有原因地忽略待匹配需求 |
| `shotgrid:assetRequirement:rematch` | 重新执行项目范围唯一匹配 |
| `shotgrid:import:list` | 查看所属项目导入批次 |
| `shotgrid:import:query` | 查看导入结果摘要 |
| `shotgrid:task:list` | 查看任务列表 |
| `shotgrid:task:query` | 查看任务详情 |
| `shotgrid:task:edit` | 修改任务要求、优先级和截止日期 |
| `shotgrid:task:assign` | 分配或改派制作任务 |
| `shotgrid:task:start` | 开始任务（管理人确认镜头或资产制作分项） |
| `shotgrid:version:list` | 查看版本列表 |
| `shotgrid:version:query` | 查看版本详情 |
| `shotgrid:version:add` | 上传并提交任务版本 |
| `shotgrid:version:retry` | 重试本人失败的版本提交 |
| `shotgrid:version:review` | 审核版本 |
| `shotgrid:note:list` | 查看修改问题、处理说明和确认记录（兼容权限码） |
| `shotgrid:note:add` | 在当前待审核版本提出修改问题（兼容权限码） |
| `shotgrid:reviewList:list` | 查看审核单 |
| `shotgrid:reviewList:query` | 查看审核单详情 |
| `shotgrid:reviewList:add` | 创建人工批量审核单 |
| `shotgrid:reviewList:edit` | 修改草稿审核单和顺序 |
| `shotgrid:reviewList:activate` | 激活人工审核单 |
| `shotgrid:reviewList:complete` | 完成人工审核单 |
| `shotgrid:reviewList:archive` | 归档审核单 |
| `shotgrid:file:download` | 通过 Shot Grid 授权接口预览或下载版本文件 |
| `shotgrid:project:all` | 平台管理员跨项目管理 |

后续资源沿用：

```text
shotgrid:<resource>:list
shotgrid:<resource>:query
shotgrid:<resource>:add
shotgrid:<resource>:edit
shotgrid:<resource>:archive
shotgrid:<resource>:<domain-action>
```

### 8.2 项目角色矩阵

| 动作 | 平台管理员 | 项目管理人 | 制作人员 |
| --- | --- | --- | --- |
| 查看所属项目 | 允许 | 允许 | 允许 |
| 查看所有项目 | 需 `shotgrid:project:all` | 禁止 | 禁止 |
| 创建项目 | 需平台权限 | 需平台权限 | 禁止 |
| 修改项目 | 允许 | 允许 | 禁止 |
| 启动、完成或归档项目 | 允许 | 允许 | 禁止 |
| 配置 NAS 根目录 | 需存储根管理权限 | 禁止 | 禁止 |
| 查看/复制所属项目 NAS 路径 | 允许 | 允许 | 允许 |
| 重试项目目录初始化 | 允许 | 允许 | 禁止 |
| 管理项目成员 | 允许 | 允许 | 禁止 |
| 创建/修改集和场次 | 允许 | 允许 | 默认禁止 |
| 创建/修改镜头和资产 | 允许 | 允许 | 禁止 |
| 导入镜头和资产表 | 允许 | 允许 | 禁止 |
| 解决或忽略资产待匹配需求 | 允许 | 允许 | 禁止 |
| 分配任务 | 允许 | 允许 | 禁止 |
| 查看所属项目任务、版本和修改问题 | 允许 | 允许 | 允许只读查看；本人任务可见完整来源标注与处理历史 |
| 确认镜头开工 | 具备对应接口权限及项目管理/跨项目管理范围时允许 | 具备接口权限并人工确认资产齐备后允许 | 禁止，等待管理人员确认 |
| 确认资产分项开工 | 具备对应接口权限及项目管理/跨项目管理范围时允许 | 具备接口权限并人工确认该分项开工条件后允许 | 禁止，等待管理人员确认 |
| 提交版本 | 管理员身份不授权；仅本人同时为当前委派的活动 `creator` 时允许 | `director` 禁止代提交 | 仅当前委派且活动的本人任务 |
| 重试失败提交 | 管理员身份不授权；仅本人同时为当前委派的活动 `creator` 时允许 | `director` 禁止代重试 | 仅本人创建的提交且仍为当前委派的活动制作人 |
| 提出修改问题 | 允许 | 允许 | 禁止 |
| 随新版本提交逐条处理说明 | 管理员身份不授权；仅随本人作为当前活动制作人的新版本提交 | `director` 禁止代提交 | 仅当前委派且活动的本人任务 |
| 在当前版本逐条确认问题 | 允许 | 允许 | 禁止 |
| 审核版本 | 允许 | 允许 | 禁止 |
| 确认版本并完成任务 | 允许 | 允许 | 禁止 |
| 创建和组织人工审核单 | 允许 | 允许 | 禁止 |
| 下载项目文件 | 通过项目及文件授权后允许 | 通过项目及文件授权后允许 | 通过所属项目及文件授权后允许 |

前端按钮根据同一矩阵显示，但后端是最终授权者。

### 8.3 后端权限依赖

Shot Grid 后端必须分层完成授权：

1. 路由组使用 `PreAuthDependency()` 校验登录态；
2. 接口使用 `UserInterfaceAuthDependency('shotgrid:...')` 校验平台权限码；
3. 项目资源使用 Shot Grid 自有的 `ProjectAccessDependency` 校验项目成员或 `shotgrid:project:all`；
4. 写操作再使用 `ProjectRoleDependency` 校验 `director`、`creator` 等项目内角色；
5. Service 和 DAO 继续校验目标资源的 `project_id`，不能只相信路径参数。

`shotgrid:project:all` 只扩大数据范围，不自动授予动作权限。镜头及资产分项开工均要求 `shotgrid:task:start` 和项目管理范围，并执行人工确认。版本 preflight/create 和失败提交重试仍必须满足“当前用户就是任务当前委派的活动 `creator` 本人”的业务门禁，平台超级管理员也不能代交或代重试。

任务动作与文件还要增加资源关系校验：

- 项目成员可以只读查看所属项目的镜头、资产、任务、版本、修改问题、处理说明、确认记录和文件，满足局域网项目协作；写动作仍按角色和任务负责人限制。
- 成员移除后立即失去项目读取和文件访问权；任务改派后旧负责人仍可作为项目成员只读查看，但立即失去提交和重试该任务的动作权，历史提交人身份和审计记录保留。
- 镜头及资产分项开工必须执行第 15.2 节的管理范围、人工确认及双/三版本门禁。版本 preflight/create 和重试提交仍执行 `TaskAssigneeDependency` 或等价 Service 校验，在写事务或正式创建锁内确认 `current_user.user_id == task.assignee_user_id`、项目成员为活动 `creator` 且平台账号有效；`director`、管理员、超级管理员和 `shotgrid:project:all` 均不得绕过本人提交要求。
- Shot Grid 文件下载接口在项目/任务授权通过后复用平台流式下载和 Range 能力；显式 deny ACL 仍优先，不能由项目权限绕过。

现有 `DataScopeDependency` 面向部门、用户和平台角色数据范围，不能代替项目成员关系。项目列表必须在查询中联结 `sg_project_member`；只有拥有 `shotgrid:project:all` 且显式请求全量范围时才能绕过成员过滤。

项目成员身份也不能自动授予平台文件下载权限。文件访问按第 17 节执行独立授权校验。

### 8.4 固定受管平台角色包

部署必须提供两个角色键唯一、启用且未删除的最小权限包；项目/成员专用服务只按角色键解析，不接受前端传入 `roleId` 或自定义角色键：

| `sys_role.role_key` | 项目角色映射 | 必需能力 | 角色包边界 |
| --- | --- | --- | --- |
| `shotgrid_admin` | `director` | 至少启用的 `shotgrid:navigation:list` 和一个启用的 Shot Grid 业务导航权限；按第 8.2 节为项目管理人配置所需 Shot Grid 项目/成员/业务对象/任务/审核权限 | 只是 Shot Grid 项目管理人接口包，不是平台超级管理员，也不授予跨项目范围 |
| `shotgrid_creator` | `creator` | 至少 `shotgrid:navigation:list`；按第 8.2 节配置项目只读、本人任务、版本提交/重试、文件下载等权限 | 只能结合活动项目成员和本人任务门禁使用 |

两个受管角色包都禁止包含：

- `*:*:*`；
- `shotgrid:project:all`；
- 任意 `system:*`；当前实现进一步拒绝所有不以 `shotgrid:` 开头的权限码；
- `shotgrid:storageRoot:add`、`shotgrid:storageRoot:edit`、`shotgrid:storageRoot:probe` 及后续等价的存储根管理写权限。

`shotgrid:storageRoot:list`、`shotgrid:storageRoot:query` 是受管角色包允许包含的只读例外；新增、修改、停用和探测仍由独立的 Shot Grid 存储管理员平台角色承担。跨项目平台管理员也必须使用独立、非受管角色；专用成员服务不得创建、修改或撤回这些角色。

后端必须在 `GET /shot-grid/project-role-options` 和每次项目创建、成员新增/恢复、项目角色变更及成员移除事务内重新校验：固定角色唯一、启用、未删除，至少包含启用的 `shotgrid:navigation:list` 和一个启用的 Shot Grid 业务导航权限，且不含上述禁用权限。配置不安全时失败关闭；不能因用户另有超级管理员角色就跳过固定角色包校验。项目归档不触发本轮角色同步，归档项目中的活动成员仍保留历史只读依赖。

某用户即使拥有 `shotgrid_admin`，在目标项目内不是活动 `director` 时仍不能执行总监写动作；某用户是 `director` 但平台包缺少对应接口权限时也必须拒绝。最终授权始终取“平台权限 ∩ 项目成员/项目角色 ∩ 资源归属/状态/`allowedActions`”。

### 8.5 菜单与独立业务端边界

`shot-grid-frontend` 是独立业务应用，不直接加载平台 `/getRouters` 返回的全部管理菜单。`sys_menu` 建立稳定 `route_name='ShotGrid'` 根目录，下设：

| 顺序 | 菜单 | 路由键 | 路径 |
| --- | --- | --- | --- |
| 1 | 工作台 | `workbench` | `/workbench` |
| 2 | 项目 | `projects` | `/projects` |
| 3 | 镜头管理 | `shots` | `/shots` |
| 4 | 资产库管理 | `assets` | `/assets` |
| 5 | 版本审核 | `reviews` | `/reviews` |
| 6 | 文件与 NAS | `files` | `/files` |

业务端通过以下专用接口获取当前用户有权看到的 Shot Grid 后代菜单：

```http
GET /shot-grid/navigation
Permission: shotgrid:navigation:list
```

- 后端继续复用 `sys_role_menu` 角色授权，只返回根节点 `ShotGrid` 范围内可见、启用的菜单；
- 响应返回稳定路由键，不向独立业务端注入任意 Vue 组件路径；
- 业务端使用白名单将路由键映射为本地异步组件；未知路由键拒绝注册并记录净化告警；
- 菜单管理负责标题、图标、顺序、显示、停用和角色授权；用户、角色、字典等系统管理菜单仍只由 `ruoyi-fastapi-frontend` 解析；
- 独立业务前端的项目创建和成员管理只调用 `/shot-grid/...` 专用接口；禁止调用 `/system/user/authRole`、`/system/role/*` 或任何其他 `/system/*` 读取/写入平台角色。平台用户、角色和菜单的通用管理仍留在 `ruoyi-fastapi-frontend`；
- MVP 不修改公共 `sys_menu` 增加应用字段；未来出现多个独立业务应用后再评审通用应用范围模型。

当前业务端已按上述六个 `routeKey` 建立固定本地注册表，并同时校验返回路径。未知键、重复键或路径不匹配项会被丢弃；后端返回值不能注入 Vue 组件。当前六个目标页面只展示“业务数据功能待接入、未使用 Mock 数据”的实施边界，不代表对应业务 CRUD 已完成。

### 8.6 平台字典种子与治理边界

首批平台字典：

| 字典类型 | 首批稳定值 | 用途 |
| --- | --- | --- |
| `sg_project_type` | `ai_short_film` | 项目类型，显示为 AI 影视短片 |
| `sg_aspect_ratio` | `16:9`、`21:9`、`2.39:1`、`9:16`、`1:1` | 项目画幅 |
| `sg_asset_type` | `Character`、`Environment`、`Prop` | 资产类型 |
| `sg_project_phase` | `planning`、`asset_production`、`shot_production`、`review`、`delivery`、`completed` | 项目当前阶段 |
| `sg_task_priority` | `low`、`normal`、`high`、`urgent` | 任务优先级 |

- 字典、菜单和按钮权限种子必须通过 PostgreSQL Alembic 数据迁移和 `sql/ruoyi-fastapi-pg.sql` 同步交付；
- 字典代码是 API 与数据库存储值，中文只用于显示；
- 任务、版本、提交、审核、存储和导入批次状态由 Service 状态机与数据库 `CHECK` 约束控制；如建立同名展示字典，也不得通过字典管理添加后端不支持的状态；
- 扩展项目类型或资产类型前必须同步评审目录、命名、Excel、数据库约束和前端映射，不能只在字典管理中增加一行。

## 9. API 通用契约

### 9.1 路由前缀

```text
/shot-grid
```

登录和平台用户信息继续使用：

```text
GET  /captchaImage
POST /login
GET  /getInfo
POST /logout
GET  /shot-grid/navigation
```

独立业务前端开发环境从 `/` 运行，并以 `/dev-api` 作为代理前缀；生产静态资源基路径固定为 `/shot-grid-app/`，API 前缀为 `/prod-api`。生产反向代理必须剥离 `/prod-api` 后再转发后端真实路径，例如浏览器请求 `/prod-api/getInfo` 时后端收到 `/getInfo`。`/shot-grid-app/` 是页面部署路径，不是后端 `/shot-grid` 业务 API 前缀。

### 9.2 请求与响应命名

- URL 路径使用 kebab-case 或资源复数名。
- 查询和 JSON 使用 camelCase。
- Python VO 使用 snake_case，通过 alias 输出 camelCase。
- 数据库使用 snake_case。
- 不在前端自行转换多套字段名称。

### 9.3 成功响应

单个资源：

```json
{
  "code": 200,
  "msg": "操作成功",
  "success": true,
  "time": "2026-08-07T16:00:00+08:00",
  "data": {}
}
```

分页列表：

```json
{
  "code": 200,
  "msg": "查询成功",
  "success": true,
  "time": "2026-08-07T16:00:00+08:00",
  "rows": [],
  "pageNum": 1,
  "pageSize": 20,
  "total": 0,
  "hasNext": false
}
```

### 9.4 失败响应

Shot Grid 失败响应继续保持平台统一 envelope，并在 `data` 中增加稳定 `errorKey`：

```json
{
  "code": 409,
  "msg": "数据已被其他用户修改，请刷新后重试",
  "success": false,
  "time": "2026-08-07T16:00:00+08:00",
  "data": {
    "errorKey": "SG_OPTIMISTIC_LOCK_CONFLICT"
  }
}
```

Shot Grid 模块内的错误响应遵守：

- Shot Grid 领域错误的 HTTP 状态与响应体 `code` 保持一致；
- `errorKey` 是前端业务分支的稳定依据；
- `msg` 是用户提示的兜底文本；
- `data.details` 可提供字段级错误等安全详情，但不得包含堆栈、SQL 或内部路径；
- 前端同时读取 HTTP 状态和响应体 `code`，兼容平台认证与接口授权以及其他模块仍可能存在的 HTTP 200 + body `code`。

`PreAuthDependency` 和 `UserInterfaceAuthDependency` 生成的平台认证、接口授权响应可以不包含 Shot Grid `errorKey`；前端应先执行平台统一错误处理，再处理 Shot Grid 领域错误。

独立业务前端统一把失败转换为 `ApiError`，并保留 `status`、`httpStatus`、`code`、`errorKey`、`data`、`details` 和原始响应。401 必须清除本地 `Admin-Token` 与身份/导航状态并回登录；403、404 和 5xx 分别进入无权限、页面不存在和服务异常路径，5xx 不得回退为空数据；409、413 和 416 保留为可区分的业务提示。

现有 `ServiceException` 会进入平台通用异常处理并返回 HTTP 200，不能直接承载上述状态语义。后端实现必须新增 Shot Grid 领域异常及处理器，例如：

```text
ShotGridDomainException
├── httpStatus
├── errorKey
├── message
└── details
```

处理器必须生成完整统一 envelope，并设置真实 HTTP 状态；不得由各 Controller 重复拼装错误响应。

并发冲突、上传超限和 Range 错误必须保留真实 HTTP 409、413、416。`PreAuthDependency` 和 `UserInterfaceAuthDependency` 产生的认证、接口授权错误继续遵循平台现有响应方式；本阶段不改造全局认证契约。Shot Grid 自身的项目成员或项目角色拒绝访问，由领域异常处理器返回真实 HTTP 403。

### 9.5 分页查询

统一查询字段：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `pageNum` | integer | 1 | 页码 |
| `pageSize` | integer | 20 | 每页数量，最大 100 |
| `orderByColumn` | string | 资源默认 | 白名单排序字段 |
| `isAsc` | string | `descending` | `ascending` 或 `descending` |
| `keyword` | string | 空 | 关键字 |

排序字段必须在后端白名单映射为 SQLAlchemy 列，不接受任意 SQL 字符串。

### 9.6 幂等性

以下写操作接受 `X-Idempotency-Key`：

- 创建项目；
- 重试项目或动态目录初始化；
- 镜头批量导入提交；
- 资产批量导入提交；
- 创建和重试版本提交；
- 审核动作；
- 创建审核单。

同一用户、同一业务动作、同一幂等键重复请求返回第一次结果，不重复创建记录。

幂等结果存储位置和 TTL 在后端实现设计时确定，默认使用 Redis。

### 9.7 独立业务前端认证与路由契约

- 自有登录页只提交账号、密码和按 `/captchaImage` 返回决定是否启用的验证码，不提供记住密码，不在 LocalStorage、SessionStorage 或 Pinia 中保存密码。
- Token 沿用平台 Cookie 名 `Admin-Token`，`path=/`，请求头使用 `Authorization: Bearer <token>`。同域不同路径部署可共享该 Cookie，但真实共享效果仍需在生产域、HTTPS 和浏览器策略下验收。
- 登录成功后必须依次完成 `/getInfo` 和 `/shot-grid/navigation` 初始化；刷新受保护路由时复用同一初始化流程，初始化并发请求只允许一个在途 Promise。
- 项目创建和成员新增/恢复、改角、移除的成功响应保持原有项目/成员模型，不增加权限刷新或跨会话推送字段。控制器在数据库事务成功提交后通过 `ApiCacheEvict(ApiGroup.USER_PERMISSION_MUTATION)` 清理平台身份、路由、用户、角色、菜单和数据范围相关接口缓存；项目创建只在业务响应码 202 时触发，成员写在业务成功码 200 时触发。
- `/shot-grid/navigation` 当前不使用接口缓存，但已打开的 SPA 会继续持有旧身份和导航 Pinia 快照，直到目标用户手动刷新页面、重新执行 `/getInfo` 与 `/shot-grid/navigation` 初始化或重新登录。数据库提交后的新请求必须按服务端最新授权结果执行；旧前端按钮显隐既不能继续授权已撤回动作，也不能证明新增权限尚未生效。
- `/getInfo` 后端只输出不含 `password` 的专用安全用户 VO；前端会话只保存 `userId`、`userName`、`nickName`、`avatar`、部门摘要、角色和权限列表。
- 范围导航只接受 `workbench`、`projects`、`shots`、`assets`、`reviews`、`files`，并映射到固定本地路径；无任何有效导航时进入 403，不得默认授予六项菜单。
- 退出无论后端调用是否成功都清理本地会话；后端错误仍向调用方报告，不能因本地清理而伪装退出接口成功。
- 项目、镜头与资产一级页已调用真实 API，均不包含失败回退 Mock；工作台已接入真实 `/tasks/mine`，`/tasks/:taskId` 已接入任务详情/编辑/等待开工和版本工作区，`/versions/:versionId` 使用 `reviews` 路由范围展示真实版本详情。版本审核一级页的审核列表/动作以及文件与 NAS 一级页仍是下一批真实 API 接入边界。
- 任务/版本列表、详情和异步操作必须使用 AbortController、请求/操作 generation 与任务/文件身份复核隔离迟到响应；同一 ID 切走再返回的 ABA 也不得覆盖新上下文。
- 版本上传的 `fileId`、幂等键、修改说明和 AI 参数只保存在当前组件内存，不写入 localStorage、sessionStorage 或持久 Pinia；相关写 API 设置 `repeatSubmit:false`，避免平台重复提交元数据持久化敏感命令。
- 二进制下载错误只在响应 Content-Type 为 JSON 且响应体不超过 64 KiB 时解析，并保留后端 `errorKey/details`；真实二进制不得被误当 JSON，临时 Object URL 使用后必须释放。
- 生产构建页面根路径固定为 `/shot-grid-app/`。仓库 Nginx 模板必须对该路径提供 SPA 深链回退，并将 `/prod-api/...` 剥离 `/prod-api` 后代理到后端。本批隔离运行已验证页面根路径和项目详情深链返回 200 `text/html`、`/prod-api/captchaImage` 返回 200 JSON；这只证明当前生产代理形态和项目管理子集，不代表完整部署或生产就绪。

## 10. 第一批项目 API

### 10.0 NAS 根目录选择与路径预览

平台管理端维护接口：

```http
GET  /shot-grid/admin/storage-roots
GET  /shot-grid/admin/storage-roots/{storageRootId}
POST /shot-grid/admin/storage-roots
PUT  /shot-grid/admin/storage-roots/{storageRootId}
POST /shot-grid/admin/storage-roots/{storageRootId}/probe
```

管理端只保存规范化 UNC 白名单，不保存用户名、密码或明文凭据。新增、路径变更或停用后重新启用时，健康状态必须回到 `unknown`；探测由 9099 后端服务账号在事务外创建、回读并删除随机临时文件，15 秒软超时后记录不可达。浏览器所在账号能打开共享目录不能替代后端探测。只有 `rootStatus=enabled` 且 `lastProbeStatus=healthy` 的根目录才能进入以下项目创建选项。

```http
GET  /shot-grid/storage-roots/options
POST /shot-grid/storage-roots/{storageRootId}/project-path-preview
Permissions:
  shotgrid:storageRoot:list
  shotgrid:project:add
```

普通项目创建人只能看到 `enabled` 且最近探测可用的根目录选项；响应包含规范化 `uncRootPath`，用于创建表单直接确认保存位置，但不返回 `credentialRef`、`rootPathKey` 或错误堆栈。

根目录选项响应只包含安全摘要：

```json
{
  "data": [
    {
      "storageRootId": 10,
      "rootCode": "PLAN_SMB",
      "rootName": "策划部",
      "protocol": "smb_unc",
      "uncRootPath": "\\\\192.168.10.64\\策划部",
      "lastProbeStatus": "healthy",
      "lastProbeTime": "2026-08-11T10:00:00"
    }
  ]
}
```

`lastProbeStatus=healthy` 是后端根目录配置与最近探测状态的筛选条件。仅在隔离数据库中写入该值的逻辑夹具不证明真实 SMB/UNC 已由正式 Windows Worker 账号访问或写入，不能作为 NAS/AD/共享 ACL 验收证据。

项目目录名称不单独采集，由项目名称唯一生成。前端在根目录或项目名称变化后自动防抖发起路径预览，不设置额外按钮。路径预览请求：

```json
{
  "projectType": "ai_short_film",
  "projectName": "罗刹夫人"
}
```

响应返回经规范化校验的目录名、完整路径预览和冲突状态：

```json
{
  "data": {
    "storageRootId": 10,
    "rootName": "策划部",
    "projectDirectoryName": "罗刹夫人",
    "projectRelativePath": "AI影视短片\\罗刹夫人",
    "projectPathPreview": "\\\\192.168.10.64\\策划部\\AI影视短片\\罗刹夫人",
    "pathConflict": false
  }
}
```

该 POST 是无副作用预览：不创建数据库记录、不创建目录，也不改变根目录探测状态。创建项目时必须重新锁定并校验根目录和路径冲突，不能信任旧预览结果。

管理员配置接口：

```http
GET  /shot-grid/admin/storage-roots
POST /shot-grid/admin/storage-roots
GET  /shot-grid/admin/storage-roots/{storageRootId}
PUT  /shot-grid/admin/storage-roots/{storageRootId}
POST /shot-grid/admin/storage-roots/{storageRootId}/probe
Permissions:
  shotgrid:storageRoot:list|query|add|edit|probe
```

探测必须在根目录下创建随机命名临时目录和小文件、完成读回后安全清理；清理目标必须经根路径校验。接口只返回净化诊断，不接受或返回明文凭据。

### 10.1 项目列表

```http
GET /shot-grid/projects
Permission: shotgrid:project:list
```

查询：

```text
pageNum
pageSize
keyword
projectStatus
orderByColumn = projectCode | projectName | deliveryDate | createTime
isAsc
```

普通用户只返回其成员项目。拥有 `shotgrid:project:all` 的平台管理员可以通过 `scope=all` 查看全部项目。

列表项最少返回：

```json
{
  "projectId": 1001,
  "projectCode": "LCFR",
  "projectName": "罗刹夫人",
  "projectType": "ai_short_film",
  "projectTypeName": "AI影视短片",
  "aspectRatio": "2.39:1",
  "plannedDurationMs": 510000,
  "deliveryDate": "2026-09-15",
  "projectStatus": "active",
  "currentPhase": "shot_production",
  "storageStatus": "ready",
  "myProjectRole": "director",
  "totalEpisodes": 2,
  "totalScenes": 8,
  "totalShots": 24,
  "totalAssets": 12,
  "totalAssetItems": 20,
  "completedShots": 11,
  "completedAssets": 5,
  "completedAssetItems": 8,
  "pendingReviewShots": 5,
  "pendingReviewAssets": 2,
  "pendingReviewAssetItems": 3,
  "revisionShots": 6,
  "revisionAssets": 3,
  "revisionAssetItems": 4,
  "unassignedShots": 2,
  "unassignedAssets": 4,
  "unassignedAssetItems": 5,
  "overallProgress": 43.2,
  "lockVersion": 0
}
```

统计字段为服务端聚合，只读。

### 10.2 创建项目

```http
POST /shot-grid/projects
Permission: shotgrid:project:add
Header: X-Idempotency-Key
```

请求：

```json
{
  "projectCode": "LCFR",
  "projectName": "罗刹夫人",
  "projectType": "ai_short_film",
  "projectDescription": "AI 影视短片项目",
  "aspectRatio": "2.39:1",
  "plannedDurationMs": 510000,
  "deliveryDate": "2026-09-15",
  "storageRootId": 10,
  "directorUserIds": [1],
  "members": [
    {"userId": 2, "projectRole": "creator"}
  ],
  "remark": ""
}
```

数据库事务：

1. 校验创建人平台权限。
2. 规范化并校验项目代号、类型、画幅，并使用项目名称生成目录名。
3. 锁定并重新校验 NAS 根目录已启用、路径未冲突。
4. 校验项目管理人和成员账号有效。
5. 创建 `sg_project` 和项目成员。
6. 锁定目标平台用户，按全部活动项目成员关系同步 `director -> shotgrid_admin`、`creator -> shotgrid_creator`；只为新建 `sys_user_role` 写 `sg_managed_user_role` 来源标记。
7. 创建 `sg_project_storage(initializing)` 和唯一 `initialize_project` 存储操作 Outbox。
8. 将 `platformRoleChanges` 写入操作日志并提交。

任何数据库步骤失败均回滚，不能产生没有项目管理人或没有存储绑定的项目。接口返回 HTTP 202：

```json
{
  "code": 202,
  "msg": "项目目录正在初始化",
  "success": true,
  "data": {
    "projectId": 1001,
    "projectStatus": "preparing",
    "storageStatus": "initializing",
    "statusUrl": "/shot-grid/projects/1001/storage"
  }
}
```

前端轮询或订阅存储状态；只有状态变为 `ready` 才显示“项目创建成功”并进入业务页面。初始化失败显示可重试错误，不得伪装成功。

控制器只在业务响应码 202 时清理 `ApiGroup.USER_PERMISSION_MUTATION`。响应不返回平台角色变化或权限刷新字段；目标成员已经打开的 SPA 仍需手动刷新或重新登录。

### 10.3 项目详情

```http
GET /shot-grid/projects/{projectId}
Permission: shotgrid:project:query
```

需要项目成员或 `shotgrid:project:all`。

返回项目基础信息、聚合统计、当前用户项目角色和允许动作集合。

建议响应包含：

```json
{
  "data": {
    "projectId": 1001,
    "projectCode": "LCFR",
    "projectName": "罗刹夫人",
    "projectDescription": "AI 影视短片项目",
    "projectStatus": "active",
    "storageStatus": "ready",
    "myProjectRole": "director",
    "allowedActions": [
      "project.edit",
      "member.manage",
      "scene.create",
      "shot.create",
      "version.review"
    ],
    "lockVersion": 0
  }
}
```

`allowedActions` 仅供界面体验，不能替代后端权限校验。

### 10.4 修改项目

```http
PUT /shot-grid/projects/{projectId}
Permission: shotgrid:project:edit
```

请求：

```json
{
  "projectName": "罗刹夫人",
  "projectDescription": "AI 影视短片项目",
  "projectType": "ai_short_film",
  "aspectRatio": "2.39:1",
  "plannedDurationMs": 510000,
  "deliveryDate": "2026-09-20",
  "currentPhase": "shot_production",
  "remark": "",
  "lockVersion": 0
}
```

项目状态不能通过本接口修改，只能使用独立的启动、完成和归档动作。项目代号、NAS 根目录、项目目录名和路径快照也不能通过本接口修改；请求携带这些额外字段时返回 422。项目已经存在正式版本时，项目类型和画幅也禁止普通修改；如确有需要，必须使用独立管理员动作、迁移方案和审计。

### 10.5 归档项目

```http
POST /shot-grid/projects/{projectId}/archive
Permission: shotgrid:project:archive
```

请求：

```json
{
  "reason": "项目已经交付",
  "lockVersion": 3
}
```

归档不物理删除项目、版本和文件。归档后默认只读。

归档成功时设置 `project_status = 'archived'`，保留 `del_flag = '0'`，并按 `lockVersion` 执行乐观锁更新。MVP 不提供恢复归档接口。

项目归档不在本轮平台角色同步触发链。归档项目中的 `member_status='active'` 成员仍保留历史只读访问，其项目角色继续计入受管平台角色依赖；归档接口不得据此撤回 `sys_user_role`。

### 10.6 项目概览

```http
GET /shot-grid/projects/{projectId}/overview
Permission: shotgrid:project:overview
```

返回《项目需求规格与业务规则》第 13 节冻结的全部统计。统计仅包含当前项目 `del_flag='0'` 且未归档的集、场次、镜头、资产和制作分项，由后端统一聚合；`overallProgress` 分母为 0 时返回 `0.0`。`completedAssets` 表示所有活动制作分项均已完成且至少存在一个制作分项的资产数；待审核、修改中资产表示至少一个制作分项处于对应状态。

```text
overallProgress =
  (completedShots + completedAssetItems)
  / (totalShots + totalAssetItems)
  * 100
```

结果保留一位小数；前端不得按当前分页数据重新计算。

### 10.7 项目存储状态、路径与重试

```http
GET  /shot-grid/projects/{projectId}/storage
POST /shot-grid/projects/{projectId}/storage/retry
GET  /shot-grid/projects/{projectId}/storage/operations
GET  /shot-grid/projects/{projectId}/storage/operations/{operationId}
POST /shot-grid/storage-operations/{operationId}/retry
Permissions:
  shotgrid:storage:path
  shotgrid:storage:retry
```

- 状态接口对项目成员或 `shotgrid:project:all` 返回 `storageStatus`、最近净化错误、`lockVersion` 和更新时间；不返回凭据、根路径键、租约或内部临时路径。项目管理人/管理员可在任一存储状态查看完整项目路径快照；制作人员只有在 `ready` 时获得该路径，初始化中或失败时返回 `projectPathSnapshot=null`。
- 制作人员不能执行目录重试。项目详情的 `allowedActions` 只有在存储状态确为 `failed`、项目未归档且当前用户同时满足项目角色与平台 `shotgrid:storage:retry` 权限时才包含 `storage.retry`。
- 项目重试只允许 `failed` 状态，请求必须携带 `X-Idempotency-Key`，正文固定为：

```json
{
  "lockVersion": 3,
  "reason": "NAS 权限已修复，重新确认项目目录"
}
```

- 项目重试在同一短事务锁定项目及存储绑定，校验项目未归档、乐观锁、没有活动项目目录操作后，新建项目级 `reconcile_directory(pending)`，把存储改回 `initializing`、清除旧错误并写操作日志。旧 `initialize_project`/失败操作不覆盖、不删除。
- 动态目录重试正文只包含非空 `reason`，同时要求 `X-Idempotency-Key`。它只接受最终 `failed` 且 `aggregateType` 为 `episode|shot|asset` 的来源操作；后端重新校验项目未归档、项目根存储仍 `ready`、业务对象仍存在、当前目录快照等于来源目标且不存在活动同聚合操作，再新建同聚合的 `reconcile_directory(pending)`。
- 两个重试接口均返回真实 HTTP 202，`data` 包含 `operationId`、`projectId`、`operationStatus`、`replayed` 和可查询详情的 `statusUrl`。同一用户、作用域、`X-Idempotency-Key` 和规范化命令重放首次受理结果；同键不同正文返回 `SG_IDEMPOTENCY_CONFLICT`。
- 操作分页和详情只对项目管理人或具有全项目范围且拥有接口权限的管理员开放。分页支持 `operationType`、`operationStatus`、`keyword`、`pageNum`、`pageSize`、`orderByColumn` 和 `isAsc`；`keyword` 只匹配相对路径快照、稳定错误键和净化错误摘要。排序字段白名单为 `operationId|createTime|updateTime|nextRetryTime`，默认 `orderByColumn=createTime`、`isAsc=descending`，相同创建时间再按 `operationId` 倒序。响应只返回操作类型、聚合目标、相对路径快照、状态、尝试次数、重试/开始/完成时间及净化错误，不返回 `leaseOwner`、`leaseUntil`、内部幂等键、凭据引用或服务器绝对路径。

### 10.8 启动与完成项目

```http
POST /shot-grid/projects/{projectId}/start
POST /shot-grid/projects/{projectId}/complete
Permissions:
  shotgrid:project:start
  shotgrid:project:complete
```

两者均携带 `lockVersion`。启动要求存储已 `ready`；完成要求所有纳入交付的活动镜头和资产制作分项均有 `completed` 任务及唯一 `final` 版本。失败返回尚未完成对象的安全汇总，不返回无界列表。

## 11. 第一批项目成员 API

### 11.0 项目角色选项

```http
GET /shot-grid/project-role-options
Permission: shotgrid:project:add

GET /shot-grid/projects/{projectId}/role-options
Permission: shotgrid:member:add OR shotgrid:member:edit
Project role: director
```

第一条供创建项目使用；第二条供已有项目的成员新增/恢复和角色修改使用，并校验当前用户对目标项目仍是 `director`。两个接口都实时解析并安全校验固定平台角色包，成功时按 `director`、`creator` 稳定顺序返回：

```json
{
  "code": 200,
  "msg": "操作成功",
  "success": true,
  "time": "2026-08-18T16:00:00+08:00",
  "data": [
    {
      "projectRole": "director",
      "projectRoleLabel": "项目管理人",
      "systemRoleId": 10,
      "systemRoleKey": "shotgrid_admin",
      "systemRoleName": "Shot Grid 项目管理人"
    },
    {
      "projectRole": "creator",
      "projectRoleLabel": "制作人员",
      "systemRoleId": 11,
      "systemRoleKey": "shotgrid_creator",
      "systemRoleName": "Shot Grid 制作人员"
    }
  ]
}
```

`systemRoleId/systemRoleKey/systemRoleName` 是安全投影，只供显示、诊断和固定映射完整性校验；项目创建和成员写请求仍只提交 `projectRole`。任一固定角色缺失、重复、停用/删除或权限包不安全时，接口以第 19 节稳定 503 错误失败关闭，不返回部分选项，前端禁用相关写表单且不得回退硬编码角色或调用 `/system/*`。

### 11.0.1 存量平台角色对账

```http
POST /shot-grid/platform-role-bindings/reconcile
Permissions: shotgrid:project:all AND system:user:edit
```

该接口只供平台管理员在 `20260818_12` 迁移完成并配置好两个固定角色后，对存量活动成员和历史来源标记执行一次全事务对账。服务按用户 ID 稳定加锁，复用成员写链的增量授权、外部关系保留和来源标记撤权规则；任一固定角色配置异常或任一用户同步失败时整体回滚。响应只返回处理用户数、变更用户数以及新增、撤回、依赖保留、外部保留的绑定计数，不返回用户清单或完整角色实体。成功提交后清理 `ApiGroup.USER_PERMISSION_MUTATION`，已打开的 SPA 仍需刷新或重新登录。

### 11.0.2 成员候选分页

```http
GET /shot-grid/member-candidates?pageNum=1&pageSize=20&keyword=杨景锋
Permission: shotgrid:project:add

GET /shot-grid/projects/{projectId}/member-candidates?pageNum=1&pageSize=20&keyword=杨景锋&deptId=100
Permission: shotgrid:member:add
Project role: director
```

第一条用于创建项目选择项目管理人和初始成员；第二条用于已创建项目的成员维护，并额外执行项目管理人角色校验。二者都不等于某个项目的活动成员列表，均通过 `DataScopeDependency(SysUser)` 约束候选范围，并支持可选的精确 `deptId` 过滤。创建项目页面必须提交当前登录账号的部门 ID，只展示同部门候选；计划总时长和交付日期不属于创建主流程输入。接口只返回未删除、未停用且当前操作者有权选择的 `sys_user` 安全投影。分页响应 `rows` 中单项为：

```json
{
  "userId": 2,
  "userName": "yangjingfeng",
  "nickName": "杨景锋",
  "avatar": "",
  "deptId": 100,
  "deptName": "制作部"
}
```

响应不得包含密码、手机号、邮箱、登录 IP、盐、Token 或其他认证字段。候选查询只解决安全选人；项目创建和添加/恢复成员事务继续应用同一 `DataScope(SysUser)`，重新校验账号状态与项目角色。成员添加、修改和移除在锁定项目行后还必须重新校验操作者仍为 `director`，不能只依赖 Controller 进入时的角色结果。

### 11.1 成员列表

```http
GET /shot-grid/projects/{projectId}/members
Permission: shotgrid:member:list
```

可选查询参数：`projectRole=director|creator`。传入时只返回指定项目角色的活动成员；不传时返回该项目全部活动成员。例如，制作人员列表使用：

```http
GET /shot-grid/projects/{projectId}/members?projectRole=creator
```

返回：

```json
{
  "rows": [
    {
      "userId": 1,
      "userName": "director",
      "nickName": "项目管理人",
      "avatar": "",
      "deptId": 100,
      "deptName": "导演组",
      "projectRole": "director",
      "producerCode": null,
      "joinedTime": "2026-08-07T16:00:00+08:00",
      "accountStatus": "0"
    }
  ]
}
```

### 11.2 添加成员

```http
POST /shot-grid/projects/{projectId}/members
Permission: shotgrid:member:add
```

请求：

```json
{
  "userId": 2,
  "projectRole": "creator"
}
```

重复添加同一用户返回冲突，不静默覆盖其项目角色。

新增或恢复成员时，服务在同一事务内按全部活动项目成员关系增量同步目标用户的平台角色。若当前需要的映射关系原已存在则记录为 `requiredPreservedRoleKeys`；无来源标记的外部关系仍不补标记、不取得撤回权。只有关系已不再被活动成员需要且没有来源标记时才记录为 `externalPreservedRoleKeys`。成功后控制器清理 `ApiGroup.USER_PERMISSION_MUTATION`。成员响应仍是 `ShotGridProjectMemberModel`，不暴露平台角色变更明细。

### 11.3 修改成员角色

```http
PUT /shot-grid/projects/{projectId}/members/{userId}
Permission: shotgrid:member:edit
```

请求：

```json
{
  "projectRole": "creator"
}
```

`projectRole` 显式 `null` 非法。当前 Shot Grid 前端不提交独立 `producerCode`；同名响应字段不得作为分配、匹配或文件命名依据。

角色确有变化时，服务先在未提交事务中更新成员角色，再按更新后的全部活动成员关系同步；同步同一用户时先建立仍需但缺失的新映射，再判断旧映射是否可撤回。仍被其他活动成员关系依赖时记录 `requiredPreservedRoleKeys`，无依赖但关系没有来源标记时记录 `externalPreservedRoleKeys`。`grantedRoleKeys/revokedRoleKeys/requiredPreservedRoleKeys/externalPreservedRoleKeys` 只进入领域审计 `platformRoleChanges`，不进入成员成功响应。

### 11.4 移除成员

```http
DELETE /shot-grid/projects/{projectId}/members/{userId}
Permission: shotgrid:member:remove
```

规则：

- 不能移除最后一名项目管理人。
- 用户仍负责活动任务时返回冲突，先完成任务转交。
- 成功后仅将成员关系软移除并保留历史任务引用；重新加入同一用户会复用并恢复原成员关系。
- 成员移除后立即失去项目查询和业务动作权限。
- 软移除后在同一事务内按目标用户全部活动项目成员关系重算固定角色依赖；只有关系带 `sg_managed_user_role` 来源标记且已无任何活动成员依赖时才撤回，外部平台角色和仍被其他项目依赖的角色保留。
- 领域审计记录 `platformRoleChanges`，数据库提交后控制器清理 `ApiGroup.USER_PERMISSION_MUTATION`；目标用户已打开的 SPA 仍需手动刷新身份和导航。
- 文件访问授权同步策略在 17.1 决策关闭后执行。

## 12. 第一批集与场次 API

### 12.1 集列表与创建

```http
GET  /shot-grid/projects/{projectId}/episodes
POST /shot-grid/projects/{projectId}/episodes
Permissions:
  shotgrid:episode:list
  shotgrid:episode:add
```

创建请求：

```json
{
  "episodeNo": 1,
  "episodeName": "第一集",
  "description": "",
  "sortOrder": 10
}
```

响应派生：

```text
episodeCode = "EP" + episodeNo 左侧补零至至少 3 位（镜头业务文件名使用）
storageDirName = "EP" + episodeNo 左侧补零至至少 2 位（NAS 目录使用）
```

创建集的数据库事务同时创建 `ensure_episode_directory` Outbox，接口返回目录状态。实体创建成功但目录尚未就绪时不得把 `directoryStatus` 伪装为 `ready`。

### 12.2 修改与归档集

```http
PUT  /shot-grid/projects/{projectId}/episodes/{episodeId}
POST /shot-grid/projects/{projectId}/episodes/{episodeId}/archive
Permissions:
  shotgrid:episode:edit
  shotgrid:episode:archive
```

修改和归档必须携带 `lockVersion`。存在活动场次时默认禁止归档。

### 12.3 场次列表

```http
GET /shot-grid/projects/{projectId}/episodes/{episodeId}/scenes
Permission: shotgrid:scene:list
```

支持：

```text
keyword
pageNum
pageSize
orderByColumn = sceneNo | sceneName | sortOrder | createTime
isAsc
```

返回集摘要和镜头数聚合字段。

### 12.4 创建场次

```http
POST /shot-grid/projects/{projectId}/episodes/{episodeId}/scenes
Permission: shotgrid:scene:add
```

请求：

```json
{
  "sceneNo": 1,
  "sceneName": "舱室惊醒",
  "description": "低温休眠舱液压阀爆开。",
  "sortOrder": 10
}
```

### 12.5 场次详情、修改与归档

```http
GET  /shot-grid/projects/{projectId}/scenes/{sceneId}
PUT  /shot-grid/projects/{projectId}/scenes/{sceneId}
POST /shot-grid/projects/{projectId}/scenes/{sceneId}/archive
Permissions:
  shotgrid:scene:query
  shotgrid:scene:edit
  shotgrid:scene:archive
```

修改和归档必须携带 `lockVersion`。存在活动镜头时默认返回冲突。归档成功时设置 `lifecycle_status = 'archived'`，保留 `del_flag = '0'`。

## 13. 第一批镜头 API

### 13.0 项目内镜头制作人选项

```http
GET /shot-grid/projects/{projectId}/shot-assignee-options
Permission: shotgrid:shot:list
Project access: required
```

查询：`pageNum`、`pageSize`、`keyword`。返回标准顶层分页字段 `rows/pageNum/pageSize/total/hasNext`；每行只包含：

```json
{
  "userId": 2,
  "userName": "xiaoliang",
  "nickName": "晓亮",
  "avatar": null,
  "deptId": 103,
  "deptName": "制作组",
  "projectRole": "creator",
  "producerCode": "XL"
}
```

服务端只返回 `projectRole=creator`、`memberStatus=active` 的项目成员以及状态正常且未删除的平台账号；`keyword` 只匹配登录账号和昵称。兼容字段 `producerCode` 由 `sys_user.nick_name` 派生。该接口是独立委派/改派的分页安全选项，不返回联系方式、认证字段或完整用户实体，也不替代任务分配事务内对账号、成员、项目角色和用户昵称的重新校验。镜头创建、编辑和 Excel 导入不调用该选项，也不接收制作人；项目管理人不能作为镜头制作人。

### 13.1 镜头列表

```http
GET /shot-grid/projects/{projectId}/shots
Permission: shotgrid:shot:list
```

查询：

```text
pageNum
pageSize
keyword
episodeId
sceneId
shotStatus
assigneeUserId
assetId
orderByColumn = episodeNo | sceneNo | shotNo | sortOrder | durationMs | updateTime
isAsc
```

同一接口支持表格、卡片和故事板。前端不得为三种视图建立三套数据源。`orderByColumn=sortOrder` 时，服务端先按集的 `(sortOrder, episodeNo)` 排列，再按场次的 `(sortOrder, sceneNo)` 排列，最后按场内镜头 `(sortOrder, shotNo, shotId)` 排列，禁止仅按镜头排序键跨集或跨场交错。

列表项：

```json
{
  "shotId": 3001,
  "projectId": 1001,
  "episodeId": 1501,
  "episodeNo": 1,
  "episodeCode": "EP001",
  "sceneId": 2003,
  "sceneNo": 1,
  "sceneCode": "001",
  "sceneName": "舱室惊醒",
  "shotNo": 1,
  "shotCode": "S001",
  "storageDirName": null,
  "directoryStatus": "not_created",
  "durationMs": 6000,
  "shotSize": "中近景",
  "cameraPosition": "低机位",
  "cameraMovement": "缓慢推进",
  "focalLength": "35/25",
  "description": "舱室内主角惊醒",
  "environmentAssets": [
    {"assetId": 4001, "assetName": "动力舱室内"}
  ],
  "characterAssets": [
    {"assetId": 4002, "assetName": "主角"}
  ],
  "dialogue": "",
  "soundEffect": "警报声、蒸汽泄压声",
  "colorReference": "冷蓝主色，红色警报光",
  "remark": "面部需保持一致",
  "sortOrder": 100,
  "sequencePosition": 1,
  "status": "reviewing",
  "assignee": {
    "userId": 2,
    "nickName": "杨景锋",
    "producerCode": "YJF"
  },
  "thumbnail": {
    "fileId": "5ed39e04-2f29-45ab-a58c-4f8168f5131a",
    "name": "WGZR_EP001_001_S001_YJF_V004_1786094626499-thumbnail.jpg",
    "url": "/shot-grid/versions/9004/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download"
  },
  "latestVersion": {
    "versionId": 9004,
    "versionNumber": "V004",
    "status": "pending_review",
    "businessFileName": "WGZR_EP001_001_S001_YJF_V004_1786094626499.mp4"
  },
  "latestFeedback": {
    "noteId": 12003,
    "content": "人物起身动作需要更快",
    "noteStatus": "open",
    "createTime": "2026-08-07T16:00:00"
  },
  "assetCount": 3,
  "lockVersion": 1
}
```

### 13.2 创建镜头

```http
POST /shot-grid/projects/{projectId}/shots
Permission: shotgrid:shot:add
```

请求：

```json
{
  "sceneId": 2003,
  "durationMs": 6000,
  "shotSize": "中近景",
  "cameraPosition": "低机位",
  "cameraMovement": "缓慢推进",
  "focalLength": "35/25",
  "description": "舱室内主角惊醒",
  "dialogue": "",
  "soundEffect": "警报声、蒸汽泄压声",
  "colorReference": "冷蓝主色，红色警报光",
  "remark": "面部需保持一致",
  "sequencePosition": 1,
  "assetIds": [4001, 4002]
}
```

事务：

1. 校验项目、集、场次和资产归属。
2. 校验 `sequencePosition` 在 `1..本场活动镜头数+1` 范围内；未提交时追加到本场末尾。服务端以位置派生 `shotNo/shotCode`，保证为 `1..N` / `S001..Snnn`。
3. 新镜头的 `storageDirName` 保持为空，不创建 NAS 目录操作。
4. 创建镜头。
5. 创建镜头资产关系。
6. 将镜头聚合状态保持为 `unassigned`；创建接口不接受 `assigneeUserId`，也不创建任务。
7. 写操作日志并提交。

镜头或关系创建失败时必须整体回滚。响应返回 `storageDirName=null` 和 `directoryStatus=not_created`；项目管理人后续通过第 15.1 节独立委派，第一次委派才创建 `not_started` 的唯一任务。

### 13.3 镜头详情

```http
GET /shot-grid/projects/{projectId}/shots/{shotId}
Permission: shotgrid:shot:query
```

返回：

- 镜头基础字段；
- 场次摘要；
- 关联资产；
- 任务摘要；
- 最新版本摘要；
- 聚合状态；
- 当前用户允许动作。

完整历史版本、修改问题、逐版本处理说明和确认记录使用独立分页接口，不在一个详情请求中无界返回。

### 13.4 修改镜头

```http
PUT /shot-grid/projects/{projectId}/shots/{shotId}
Permission: shotgrid:shot:edit
```

请求包含可修改的制作字段、完整 `assetIds` 和 `lockVersion`。普通修改只允许目标未分配或唯一任务仍为 `not_started`；任务进入 `preparing/in_progress/pending_review/revision/completed` 后详情不再返回 `shot.edit`，列表隐藏编辑入口，直接调用接口返回 HTTP 409 / `SG_SHOT_EDIT_PRODUCTION_STARTED`。普通修改不允许变更 `sceneId`、`shotNo` 或 `sequencePosition`；镜序只通过下方场内重排动作修改，避免表单与拖拽出现两套心智模型。

表格拖拽使用独立动作，不得为了排序补齐并覆盖整份镜头表单：

```http
PUT /shot-grid/projects/{projectId}/shots/{shotId}/sequence
Permission: shotgrid:shot:edit
Project role: director
```

```json
{
  "sequencePosition": 2,
  "lockVersion": 1
}
```

服务端锁定项目和目标镜头所属场次的活动镜头，校验位置范围与目标镜头乐观锁，并计算被移动区间。区间内镜头只能是未分配或任务仍为 `not_started`；任一镜头已进入 `preparing/in_progress/pending_review/revision/completed` 或已有版本/文件时整个动作拒绝。校验通过后，服务端同步场内 `sequencePosition`、`shotNo` 和 `shotCode`，保证第 N 镜始终是 `S{N:03d}`，被顺移镜头同时推进 `lockVersion`。无目录镜头在事务内直接改号；如区间内存在历史冻结目录，则投递受控 NAS 迁移 Outbox，迁移成功后再原子切换目录快照与编号。

拖拽只在表格已筛选到具体集和具体场次、没有关键字/状态/制作人附加筛选、使用升序排序且已加载完整场次时启用。前端按每页最多 100 条读取全部结果，单场超过 2000 条或仍在加载时禁用拖拽；完整加载后隐藏分页，提交的 `sequencePosition` 必须是整场位置。成功或失败后都重新读取完整场次。不再向用户暴露与拖拽分离的“按当前顺序重新编号”常规动作；下列接口仅保留为历史客户端兼容和人工修复通道：

```http
POST /shot-grid/projects/{projectId}/shots/renumber
Permission: shotgrid:shot:edit
Project role: director
```

```json
{"sceneId": 2003}
```

兼容动作使用与拖拽相同的“未开始制作”门禁，`not_started` 任务不构成阻断。无目录镜头直接在事务内连续化；已有冻结目录时才进入 `migrating` 并执行两阶段 NAS 迁移。操作及映射写入审计，失败不得出现“数据库已改号但目录未迁移”的半完成状态。

### 13.5 删除镜头

```http
POST /shot-grid/projects/{projectId}/shots/{shotId}/archive
Permission: shotgrid:shot:archive
```

单条删除与批量删除先锁定所有目标镜头，再按场次锁定完整活动镜头集合。每场从最早删除位置到场尾只能包含尚无任务或唯一任务状态为 `not_started`、且没有版本/文件的镜头；任务一旦进入 `preparing`、`in_progress`、`pending_review`、`revision` 或 `completed` 就必须整批拒绝。受影响区间任一镜头已有 `storage_dir_name` 时以 `SG_SHOT_DELETE_DIRECTORY_EXISTS` 整体拒绝，删除链不得隐式迁移 NAS 目录。

删除采用逻辑归档，不物理删除镜头；存在的 `not_started` 任务在同一事务中软删除。目标镜头同时设置 `lifecycle_status = 'archived'` 和 `del_flag = '2'`，随后在同一事务中把该场剩余活动镜头连续化为 `S001..Snnn` 并推进受影响行 `lockVersion`，从而既释放活动唯一索引又不留下编号空洞。`20260813_09` 只回填没有活动任务且没有正式版本的历史误删镜头，已有制作历史的归档镜头不自动释放编号。

```http
POST /shot-grid/projects/{projectId}/shots/batch-delete
Permission: shotgrid:shot:archive
```

请求为 `items[{shotId,lockVersion}]`，最多 200 项，不允许重复镜头；服务端按镜头 ID 固定顺序加锁，任何一项不存在、锁版本冲突或任务已经开始时整批回滚。

### 13.6 批量分配镜头制作人

```http
POST /shot-grid/projects/{projectId}/shots/batch-assign
Permission: shotgrid:task:assign
Project role: director
```

请求：

```json
{
  "assigneeUserId": 2,
  "items": [
    {"shotId": 3001, "taskLockVersion": null},
    {"shotId": 3002, "taskLockVersion": 4}
  ]
}
```

`items` 最多 200 项且镜头 ID 不得重复。尚未创建任务的镜头传 `taskLockVersion=null`，已有任务必须提交列表响应中的当前 `taskLockVersion`。服务端按镜头 ID 固定顺序锁定目标，逐项复用单镜头分配的制作人员资格、任务状态、未完成版本提交和乐观锁规则；首次分配创建唯一 `shot_video` 任务，改派更新原任务。整批只写一条批量审计并在一个事务中提交，任一项失败时全部回滚。

响应返回 `assignedShotIds`、`assignedCount`、`createdTaskCount` 和 `reassignedTaskCount`。

### 13.7 独立业务端已实现交互边界

- `/shots` 先选择可访问项目，再加载项目详情、集列表和第 13.0 节制作人选项；集选择驱动场次分页。关键字、集、场次、聚合状态、制作人、排序和服务端分页统一传给第 13.1 节列表。
- 表格、卡片和故事板只切换同一批 `rows` 的表现形式，不发出三套语义不同的查询。项目切换、筛选变化、预检完成后的刷新和组件卸载会中止旧请求，迟到响应不得污染新项目上下文；切换项目还必须关闭创建/导入弹窗，清空旧项目的预检 Token、幂等键、选中行和问题明细。创建、导入、编辑和分配弹窗在项目/镜头 ID 之外还冻结单调递增的 `operationGeneration`；同一 ID 切走再返回并重开同类弹窗时，旧实例的迟到 `saved/imported/assigned/refresh` 事件不得关闭新弹窗或刷新当前上下文。
- `/projects/{projectId}/shots/{shotId}` 使用真实详情并保留独立深链。表格、卡片和故事板中的详情入口在当前列表右侧打开可调整宽度的抽屉，复用同一详情组件和接口；关闭抽屉销毁实例并中止详情请求，编辑、分配或删除成功后同步刷新列表，不丢失当前筛选与分页。表格行同时提供编辑和删除，首列可选择当前页中允许分配或删除的镜头；列表上方提供制作人下拉、批量分配和批量删除。批量分配只提交用户当前明确勾选的镜头，不隐式修改筛选结果的其他页；创建/编辑弹窗、分配/改派弹窗、批量分配和删除动作调用第 13.2、13.4、13.6、15.1、13.5 节接口。按钮同时参考平台权限、项目角色、存储状态、项目状态和后端 `allowedActions`，但不替代服务端授权。
- 镜头时长在界面按秒输入时最多保留三位小数，转换为安全整数毫秒后提交，不用浮点字符串或格式化文本作为持久值。
- `thumbnail.url` 只接受 `/shot-grid/versions/{versionId}/files/{fileId}/download` 形式的受保护相对路径。前端必须通过统一请求层获取 Blob 并创建临时 Object URL；403/404 显示安全占位，取消、项目/镜头切换和卸载时中止请求并释放 Object URL。禁止直接用 `<img src>` 绕过 Bearer Token，也禁止持久化 Blob。
- 导入弹窗下载本节冻结模板，上传 `.xlsx` 后展示工作簿级与行级错误/警告，并按 Sheet 管理 `selectedRows[{sheetName,rowNumber}]`。明文 `importToken` 与稳定 `X-Idempotency-Key` 只存在当前组件内存；同一次 commit 重试复用该键，重新选择文件会建立新预检会话。页面显示后端的创建/复用/任务/资产需求/目录操作统计，不从选中行数猜测结果。

## 14. 镜头导入契约

导入分为“预检查”和“正式提交”，不能读取 Excel 后由前端直接循环创建。

模板下载：

```http
GET /shot-grid/imports/shots/template
Permission: shotgrid:shot:import
```

成功响应为 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` 二进制，不套统一 JSON envelope；响应包含下载文件名 `镜头导入模板-shot-v2.xlsx` 和 `X-Shot-Grid-Template-Version: shot-v2`。应用层传输加密中间件只精确放行该路径的 GET，以便浏览器按 Blob 下载；POST、子路径和镜头 preview/commit JSON 不得因共同前缀被放宽。资源缺失或摘要不一致时返回 HTTP 503 / `SG_IMPORT_TEMPLATE_UNAVAILABLE`。

部署资源固定为后端包内 `module_shot_grid/resources/templates/shot-v2.xlsx`，SHA-256 为：

```text
B6F24078CA56295E9E6CCE50BB3455AF198DFFFE5C08F8D85605A68C09439ECE
```

当前 v2 模板为匿名业务模板，主数据区固定为 A:O 15 列且不含“制作人”；旧 `shot-v1.xlsx` 只保留为历史资源，不再由服务下载。解析统计仍应为 total 24、valid 24、warning 0、error 0、2 集、8 场、24 镜头，但不会解析、匹配或返回制作人。摘要与内容测试同时扫描驱动器绝对路径、`file:` URI、UNC、个人/组织、应用属性和 `x15ac:absPath`，禁止部署模板重新泄露本地或网络环境信息。

### 14.1 预检查

```http
POST /shot-grid/projects/{projectId}/shots/import/preview
Content-Type: multipart/form-data
Permission: shotgrid:shot:import
```

输入与工作簿边界：

- MVP 正式模板和保证支持的格式为 `.xlsx`；当前契约以后端包内 v2 模板为准，不承诺 `.xls` 或 `.csv`；
- 镜头模板版本固定为 `shot-v2`；资产模板版本固定为 `asset-v2`。不能把 WPS 元数据当作模板版本；
- 单文件默认上限为 10 MiB、ZIP 条目 256、解压总量 64 MiB、单条目压缩比 200；单工作簿业务数据行默认上限为 10000 行，预览 Token 默认有效 1800 秒；
- `openpyxl` 前必须流式扫描全部 OOXML Sheet（含隐藏 Sheet）。默认上限为：物理行 12000、单元格/共享字符串条目 200000、XML 元素 1000000、单 Sheet 列号 128、合并区域 20000、合并展开单元格 200000、单格文本 10000 字符、共享字符串引用展开后的文本总量 8000000 字符；Redis Token 载荷和 HTTP 预览 JSON 的 UTF-8 大小均不得超过 16 MiB；这些阈值可由部署配置收紧，但不得由请求放宽；
- ZIP 条目默认最多 256 个、解压后总大小默认最多 64 MiB、单条目压缩比默认最多 200；必须拒绝目录穿越、外部链接、业务单元格公式和压缩炸弹；
- 上传文件只用于临时解析，不立即成为业务附件。
- preview 普通读取项目状态并拒绝 `projectStatus=completed|archived`，返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`；它不加项目行锁，前端隐藏入口只是体验优化。
- 每个可见 Sheet 表示一集，Sheet 名必须匹配 `^EP(\d{3,})$`，例如 `EP001`、`EP002`；解析后的集号必须大于 0。
- 导入器遍历全部可见业务 Sheet；规范化后集号重复、Sheet 名不合法或业务 Sheet 缺少主表头时，预检查失败。隐藏辅助 Sheet 可以忽略，但必须返回工作簿级警告。
- 主表从 `A1` 开始，只读取第一段连续非空表头；遇到首个空表头即停止。因此 v2 模板的正式数据区为 `A:O`，后续空白分隔的辅助内容不得被解析为镜头数据。
- 冻结窗格、筛选、样式、空白辅助区域等格式差异不得影响解析结果。

当前正式导入表头按顺序固定为 15 列：

| 列 | 表头 | 规范字段 | 导入规则 |
| --- | --- | --- | --- |
| A | 场次 | `sceneNo`、`sceneName` | `序` 固定映射为 `0`、`000`、`序`；`01场` 等映射为正整数场次号 |
| B | 镜头号 | `shotNo` | 接受 `S001` 等格式，规范化为正整数；在当前场次内唯一，不同场次可分别从 `S001` 开始 |
| C | 时长(s) | `durationMs` | 秒值精确换算为整数毫秒 |
| D | 镜头缩略图 | — | 只读列，导入忽略 |
| E | 制作内容描述 | `description` | 镜头制作内容 |
| F | 景别 | `shotSize` | 文本 |
| G | 机位 | `cameraPosition` | 文本 |
| H | 镜头运动 | `cameraMovement` | 文本 |
| I | 焦段(mm) | `focalLength` | 去首尾空格后按文本保留，兼容 `135`、`35/25`、`24/18` |
| J | 场景 | `environmentAssetNames` | 只形成 `Environment` 资产关系或待匹配需求 |
| K | 台词/对白 | `dialogue` | 文本 |
| L | 音效 | `soundEffect` | 文本 |
| M | 色调参考 | `colorReference` | 文本；文件引用另走文件关系 |
| N | 备注 | `remark` | 文本 |
| O | 镜头状态 | — | 只读列，导入忽略 |

派生规则：

- `episodeNo`、`episodeCode` 从 Sheet 名派生，不从行数据读取。
- `sortOrder` 按 Sheet 内有效数据行顺序生成稳定递增值，不把 Excel 行号保存为业务主键。
- 当前模板没有“角色”和“道具”列，不从制作内容、台词或备注中猜测 Character/Prop；这两类关系由资产导入、镜头详情人工维护或后续模板版本提供。
- “镜头缩略图”和“镜头状态”作为只读列整表忽略，并返回一次工作簿级警告，不逐行产生重复警告。

返回：

```json
{
  "data": {
    "batchId": 9001,
    "importToken": "b1f84d62-...",
    "expiresAt": "2026-08-07T16:30:00+08:00",
    "summary": {
      "totalRows": 24,
      "validRows": 24,
      "warningRows": 0,
      "errorRows": 0,
      "distinctEpisodes": 2,
      "distinctScenes": 8,
      "distinctShots": 24
    },
    "rows": [
      {
        "rowKey": "4b8f4fa2b6b5c93c2a6f806e8b3f15e8399cd520ee7b5d2dd9dfad3cd6f0a7a1",
        "sheetName": "EP001",
        "rowNumber": 2,
        "normalized": {
          "episodeNo": 1,
          "sceneNo": 0,
          "sceneCode": "000",
          "sceneName": "序",
          "sortOrder": 10,
          "shotNo": 1,
          "description": "控制室红光警报",
          "durationMs": 5000,
          "shotSize": "中近景",
          "cameraPosition": "低机位",
          "cameraMovement": "缓慢推进",
          "focalLength": "35/25",
          "assetRequirements": [
            {"assetType": "Environment", "rawName": "控制室", "matchedAssetId": 4001}
          ],
          "dialogue": "立即撤离！",
          "soundEffect": "警报声、蒸汽泄压声",
          "colorReference": "冷蓝主色，红色警报光",
          "remark": "面部需保持一致"
        },
        "warnings": [],
        "errors": [],
        "canImport": true
      }
    ]
  }
}
```

规则：

- Sheet 名无法派生集号，或数据行缺少场次、镜头号时返回错误，不随机生成编号。
- `序` 规范化为 `sceneNo=0`、`sceneCode=000`、`sceneName=序`；`01场`、`1场`、`001` 等可规范化为正整数场次号，但无法识别的文本必须报错。
- `durationSec` 最多接受三位小数，并精确换算为整数 `durationMs`。
- 模板、预检响应和正式提交都不包含制作人；导入后的镜头固定为 `unassigned`，不创建任务。
- “场景”名称存在唯一 `Environment` 资产时解析为正式关系；尚不存在时形成 `pending` 待匹配需求，不作为行错误，也不在镜头导入事务中隐式创建正式资产。
- 规范化后出现多个资产候选或历史同名脏数据时返回冲突错误，禁止自动选择。
- 重复集和场次可以映射同一规范实体，但名称字段冲突必须报错。
- 同一场次内重复镜头号必须报错；不同场次可以使用相同镜头号。
- 总集数、总场次数和总镜头数按已生成 `normalized` 结构的行去重统计，分别使用 `episodeNo`、`(episodeNo, sceneNo)` 和 `(episodeNo, sceneNo, shotNo)`；资产数据库匹配产生的行错误只影响 `validRows/errorRows`，不得缩减结构统计，也不能使用 Excel 原始行数替代。
- Token 明文及完整规范化行数据只存入 Redis，具有短 TTL，并绑定用户、项目、导入类型、批次、模板版本、原文件摘要和可提交行集合；数据库只保存 Token 哈希。
- 预检查创建 `sg_import_batch(status=previewed)`，数据库只保存来源摘要和统计；逐行规范化数据与错误明细按短 TTL 存入 Redis。

### 14.2 正式提交

```http
POST /shot-grid/projects/{projectId}/shots/import/commit
Permission: shotgrid:shot:import
Header: X-Idempotency-Key
```

请求：

```json
{
  "importToken": "b1f84d62-...",
  "selectedRows": [
    {"sheetName": "EP001", "rowNumber": 2},
    {"sheetName": "EP002", "rowNumber": 2}
  ]
}
```

规则：

- 重新验证 Token 的用户、项目、TTL 和文件摘要。
- 锁定导入批次和项目后重新验证项目仍非 `completed/archived`；预检后状态变化也必须拒绝并回滚，不能依赖预检时的旧状态。
- 只允许提交 `canImport=true` 的行；不存在制作人匹配错误或前端制作人覆盖流程。
- `selectedRows` 不接受 `assigneeUserId`；出现该字段应按请求模型的额外字段策略拒绝，而不能静默创建任务。
- Sheet 内物理行号不是工作簿全局标识；服务端以 `sheetName + rowNumber` 定位选择，并据此计算 `selection_hash`。
- 提交前重新检查数据库唯一性，不能只相信预览结果。
- MVP 采用全选行事务：任一选中行失败，全部回滚。
- 锁定并更新导入批次、创建集、场次、未分配镜头、已匹配镜头资产关系和待匹配资产需求处于同一业务事务；导入不得创建镜头任务，并在事务末把批次改为 `committed`。
- 同事务为新集和新镜头创建幂等目录操作 Outbox；NAS I/O 在事务提交后由 Worker 执行。
- 同一 Token 成功提交后不能再次消费。
- 同一提交用户、项目、导入类型和幂等键重复请求，在选择摘要一致时从 PostgreSQL `result_summary` 返回首次结果；即使 Redis 已过期或服务已重启也不得重复创建数据。
- 业务事务失败时全部领域数据回滚，再由独立短事务将批次标记为 `failed`；该失败记录不构成半成功导入。

### 14.3 资产预检查

```http
POST /shot-grid/projects/{projectId}/assets/import/preview
Content-Type: multipart/form-data
Permission: shotgrid:asset:import
```

模板下载：

```http
GET /shot-grid/imports/assets/template
Permission: shotgrid:asset:import
```

该路径已交付固定 `asset-v2` 资源 `module_shot_grid/resources/templates/asset-v2.xlsx`，下载文件名为 `资产导入模板-asset-v2.xlsx`，响应头为 `X-Shot-Grid-Template-Version: asset-v2`。模板使用 `Sheet1!A:F`、黑底白字表头和合并父级结构，示例内容全部使用虚构名称且“类型”列带下拉约束；模板不含制作人。服务端校验冻结 SHA-256 `B551AC1D1D5EDC20A025B0ED90157412E1365006108816F08CB2C59AE4301696` 后才返回，资源缺失或摘要变化时以 `SG_IMPORT_TEMPLATE_UNAVAILABLE` 失败关闭。旧 `asset-v1.xlsx` 只保留为历史资源，不再由服务下载。

当前正式 v2 模板的主数据区为 `Sheet1!A:F`，表头依次为“类型、名称、描述、制作分项、备注、状态”。导入器只读取从 A1 开始的首段连续非空表头，后续空表头不参与解析。

模板结构为 12 个逻辑资产、20 个制作分项：Environment 2/4、Prop 4/4、Character 6/12。移除制作人列后，历史第 16 行的复合制作人不再产生错误；第 6—8 行缺少制作分项，仅产生警告。原始父级/分项结构统计、可导入行数和用户最终选择行数是三个不同口径，响应和页面不得混写。

样表使用合并单元格表达父子层级：合并区域内的“类型、名称、描述”必须取合并区域左上角值；不得对普通未合并空白单元格盲目前向填充。每个有效明细行创建一个制作分项，同一合并资产区域只创建一个 `sg_asset`。

支持字段：

| 标准字段 | 中文别名 | 必填 | 规则 |
| --- | --- | --- | --- |
| `assetType` | 类型、资产类型 | 是 | `Character`、`Environment`、`Prop` 或角色、场景、道具 |
| `assetName` | 名称、资产名称 | 是 | 项目内同类型规范化名称唯一 |
| `productionItem` | 制作分项 | 否 | 允许暂缺并返回警告；只能以未分配草稿导入，分配负责人前必须补齐 |
| `assetDescription` | 资产描述 | 否 | 资产主数据描述；当前样表没有独立列 |
| `itemDescription` | 描述、制作分项描述 | 否 | 当前样表 C 列；按明细行写入 `sg_asset_item.description`，合并时各分项继承相同值 |
| `taskDescription` | — | — | 不属于导入字段；由第一次委派时的任务分配命令填写 |
| `remark` | 备注 | 否 | 业务备注 |

规则：

- MVP 不静默更新已有字段；同一合并区域或连续规范化键相同的明细行映射为一个资产及多个制作分项，不按物理行重复创建资产。数据库已有同类型同名称资产时可复用父资产并新增尚不存在的分项，但资产字段冲突必须报错；
- 文件内同一资产的非空制作分项名称重复时返回所有相关行错误；数据库已有同资产同制作分项时返回冲突，不静默覆盖；
- 制作分项为空时返回行警告并允许按“未分配”提交，创建可后续编辑的 `sg_asset_item`；委派前必须补齐分项名称；
- “根据资产表决定有多少类型”只统计三种允许类型中本文件实际包含的类型和数量，不允许 Excel 创建新类型代码；
- 预检查返回每种类型的有效、警告、错误数量，以及预计可解决的镜头资产需求数量；
- “状态”、缩略图、最新版本和完成度等只读列不参与写入并返回忽略警告；
- 模板、预检响应和正式提交均不包含制作人；Token、TTL、来源摘要和数据库重新校验规则与镜头导入一致。
- 当前实现只按原文件摘要、Sheet 和物理行生成技术行键，尚不能识别“工作簿重新保存或移动行后的同一未命名分项”；引入稳定 `rowUid` 前，这类跨文件疑似重复提示是明确的后续缺口。

### 14.4 资产正式提交与自动匹配

```http
POST /shot-grid/projects/{projectId}/assets/import/commit
Permission: shotgrid:asset:import
Header: X-Idempotency-Key
```

请求继续使用 `importToken` 和 `selectedRows[{sheetName,rowNumber}]`，不接受 `assigneeUserId`。合并单元格解析后每个预览行都是自包含记录，允许只选择同一父资产下的部分可导入分项；未选择行不落库。锁定批次后的一个业务事务包含：

`X-Idempotency-Key`、Token 和 `selection_hash` 保护同一预览与提交请求，不把语义相近但文件摘要已经变化的新工作簿视为同一请求；未命名分项的跨文件逻辑去重仍受上一节所述边界限制。

- `sg_import_batch` 从 `previewed` 进入 `committing` 并最终成为 `committed`；
- 按去重键创建资产和未分配制作分项，冻结稳定目录身份但不创建目录 Outbox；
- 不创建资产图片任务；第一次委派必须另行调用第 15.1 节任务分配接口；
- 按 `(project_id, asset_type, normalized_name)` 查询待匹配需求；
- 唯一匹配时幂等创建 `sg_shot_asset` 并将需求改为 `matched`；
- 无候选保持 `pending`，候选不唯一改为 `conflict`；
- 写入操作审计。

任一步骤失败时整个选中批次及其领域写入回滚，随后用独立短事务记录 `failed` 摘要；NAS I/O 仍由成功业务事务后的 Worker 执行。资产提交成功响应分别返回新增三类资产数、新增制作分项数、缺失制作分项警告数、自动匹配数、仍待匹配数和冲突数；兼容任务统计字段如仍保留，其值必须为 0。

### 14.5 导入批次与待匹配需求 API

```http
GET  /shot-grid/projects/{projectId}/imports
Permission: shotgrid:import:list

GET  /shot-grid/projects/{projectId}/imports/{batchId}
Permission: shotgrid:import:query

GET  /shot-grid/projects/{projectId}/asset-requirements
Permission: shotgrid:assetRequirement:list

POST /shot-grid/projects/{projectId}/asset-requirements/{requirementId}/resolve
Permission: shotgrid:assetRequirement:resolve

POST /shot-grid/projects/{projectId}/asset-requirements/{requirementId}/ignore
Permission: shotgrid:assetRequirement:ignore

POST /shot-grid/projects/{projectId}/asset-requirements/rematch
Permission: shotgrid:assetRequirement:rematch
```

人工解决请求必须携带唯一 `assetId`、原因和幂等键；后端重新校验项目、类型和资源归属。忽略需求必须填写原因。重新匹配只处理当前项目的 `pending/conflict`，不会覆盖人工 `ignored` 决策。

## 15. 任务、版本与自动审核契约

### 15.1 分配制作人并创建任务

```http
POST /shot-grid/projects/{projectId}/shots/{shotId}/assign
POST /shot-grid/projects/{projectId}/asset-items/{assetItemId}/assign
Permission: shotgrid:task:assign
```

请求：

```json
{
  "assigneeUserId": 2,
  "priority": "normal",
  "dueDate": "2026-08-15",
  "taskLockVersion": null
}
```

规则：

- 本节接口是普通业务链中唯一允许创建制作任务的入口；镜头、资产、制作分项的手工创建和 Excel 导入不得复用内部建任务函数。
- 负责人必须是有效项目制作人员且平台用户昵称非空；内部兼容字段 `producerCode` 由该昵称派生。
- 镜头创建 `taskKind=shot_video`，资产制作分项创建 `taskKind=asset_image`。
- 镜头首次分配不接收前端编辑的制作要求：首次分配和已有任务改派弹窗都只读展示当前镜头的制作内容、景别、机位、镜头运动、焦段、台词/对白、音效、色调参考和备注，且不提交 `taskDescription`；后端在锁定镜头后以 `sg_shot.description` 建立任务 `requirements` 快照，即使旧客户端传入该字段也不得覆盖。首次分配前调整内容走镜头编辑，任务建立后的要求调整走独立任务编辑动作。
- 镜头已有任务时，改派命令只保留 `assigneeUserId/taskLockVersion`，不得借改派修改制作要求、优先级或截止日期。
- 资产制作分项名称为空时不得首次分配或改派；后端返回 HTTP 422 / `SG_ASSET_PRODUCTION_ITEM_REQUIRED`，批量分配任一目标不完整时整批回滚。
- 目标尚无任务时创建 `not_started` 任务，此时 `taskLockVersion` 必须为空；已有未完成任务时必须携带当前 `taskLockVersion`，执行受控改派并记录审计，不创建第二个任务。
- 已有任务存在任何非 `committed` 版本提交时禁止改派，`failed` 也属于未解决提交；必须重试原提交或使用后续明确治理动作。
- 已完成任务默认禁止改派；如需返工，必须新增明确的重新开启动作。
- 镜头详情的 `allowedActions` 必须与改派写入门禁一致：未分配时可返回首次分配；已有 `not_started/preparing/in_progress/pending_review/revision` 任务且不存在非 `committed` 提交时，才可返回 `task.assign`。已完成任务不得返回该动作；所有状态仍同时要求平台分配权限、项目管理范围、项目可写、NAS 就绪和镜头未归档。前端按唯一任务是否存在区分“分配任务”和“改派任务”，不能仅凭已存在任务就展示入口。

### 15.2 开始任务

```http
POST /shot-grid/tasks/{taskId}/start
Permission: shotgrid:task:start
```

开工统一由管理人员确认，请求按任务类型区分；分配不自动开工：

| 任务类型 | 操作人 | 请求体 |
| --- | --- | --- |
| 镜头 `shot_video` | 有接口权限的项目 `director` 或 `has_all_scope` 管理人员 | `{ "lockVersion": 0, "shotLockVersion": 0, "assetsConfirmed": true }` |
| 资产 `asset_image` | 有接口权限的项目 `director` 或 `has_all_scope` 管理人员 | `{ "lockVersion": 0, "assetLockVersion": 0, "assetItemLockVersion": 0, "startConfirmed": true }` |

- 镜头与资产制作分项的 `not_started` 均显示“待开工”。资产是否齐备由管理人员线下确认，系统只记录人工确认，不自动判断依赖完成度，也不提供撤销、暂停或批量开工。
- 镜头列表返回 `taskId`、`taskLockVersion` 和 `allowedActions`；原 `lockVersion` 仍是镜头版本。列表和详情共用管理范围、接口权限、项目可写、NAS 就绪、目标活动、任务未开始等动作门禁；写接口还会复核当前负责人资格，失效时需先重新分配。
- 服务端先锁项目并重新解析访问权限，再锁任务和目标；镜头必须分别检查任务与镜头锁版本、`assetsConfirmed` 严格为布尔 `true`、当前负责人仍是活动且账号有效的 `creator`。缺少人工确认或镜头锁号返回 422 / `SG_SHOT_START_CONFIRMATION_REQUIRED`；过期版本返回 409；负责人失效返回 409 / `SG_TASK_ASSIGNEE_INVALID`。制作人即使有 `task:start` 权限也不能自行开工任一类型任务。
- 资产同样在项目锁内重查权限，再锁任务、父资产和选中分项，复核三份版本、活动生命周期、完整分项名称及有效负责人。缺少 `startConfirmed: true` 或资产/分项锁号返回 422 / `SG_ASSET_START_CONFIRMATION_REQUIRED`；确认字段严格为布尔值。版本过期返回 409。开工只递增任务版本，不递增未修改的父资产与分项元数据版本。
- 开工只接受 `not_started`。镜头在同一事务中冻结 `storageDirName` 并创建幂等 `ensure_shot_directory`；资产仍锁父资产并复用共享的 `ensure_asset_directory`。新目录未就绪时进入 `preparing`，Worker 在目录成功后以 owner + attempt fencing 回写 `in_progress`；已有成功目录可直接进入 `in_progress`。尚未开工的任务不会随共享目录成功而推进。
- 目录失败仍保持 `preparing`，通过原目录重试链恢复；请求事务中不执行 NAS I/O。现有已开工任务不回退、不要求重新确认。
- 两类人工确认与状态/Outbox 同事务记录审计：操作人、时间、项目、镜头或资产及分项、任务、负责人、双/三版本和 `confirmationMethod=manual`。确认时间表示管理人放行时间，不证明制作人员已在线下实际开工。
- 任务详情等待时自动查询状态；两类任务制作人均无需再次点击开始。未开工与目录准备中均不能 preflight/create 版本，进入制作中后仍只有当前受派制作人员可以提交，管理人不获得代提交权限。
- 镜头和资产列表三种视图、工作台及任务/资产详情复用有界状态查询：待开工每 5 秒，目录准备中每 1.5 秒且每轮最多 80 次；资产列表依据 `itemStatusCounts`，不能因父级为制作中而漏掉其他待开工/准备中分项。仅查询已确认的筛选、分页和排序；保留当前内容与有效勾选，列表及资产详情在筛选草稿、相关弹窗或写入期间暂停；任务详情保留编辑快照且不替换锁号，切项目/路由和卸载中止请求并隔离迟到响应。连续 3 次失败或归一化 401/403/404 停止并提示人工刷新；当前结果无待开工/准备中项时停止。轮询只读取服务端状态，不触发开工。

权限交付：PostgreSQL 增量 `20260827_23` 仅将标准权限菜单“开始本人任务”更名为“开始任务”，不修改既有角色授权、任务状态或历史审计。部署后由平台管理员显式为 `shotgrid_admin` 配置 `shotgrid:task:start`，刷新权限缓存/会话并核对实际按钮；不自动扩大角色授权，`shotgrid_creator` 即使仍有此权限也不能自行开工。


### 15.3 上传并自动提交版本

用户界面中的“上传并提交版本”是一个业务动作，基于现有文件基座严格按三步执行：

1. 完成本地候选数量、每文件类型/大小、整批大小、任务身份和当前动作校验，再调用私有 preflight；
2. preflight 成功且任务/权限/候选 generation 仍一致时，对每个候选调用 `POST /common/files/upload` 上传受保护文件并取得各自 `fileId`；
3. 按 preflight 的同一稳定顺序调用版本提交创建接口并处理 HTTP 202，等待 NAS 发布和正式版本事务完成；只有状态变为 `committed` 才向用户显示整个轮次提交成功。

私有预检接口：

```http
POST /shot-grid/tasks/{taskId}/version-submissions/preflight
Permission: shotgrid:version:add
```

请求：

```json
{
  "candidates": [
    {
      "clientFileKey": "local-01",
      "fileName": "shot-final-a.mp4",
      "fileSize": 10485760,
      "sortOrder": 0,
      "candidateNote": "动作节奏更快"
    },
    {
      "clientFileKey": "local-02",
      "fileName": "shot-final-b.mov",
      "fileSize": 12582912,
      "sortOrder": 1,
      "candidateNote": "表演更自然"
    }
  ],
  "changelog": "根据上一轮意见加快人物起身动作",
  "aiParams": null,
  "issueResponses": [
    {
      "issueId": 7101,
      "responseText": "已调整起身动作节奏，并在当前版本重新检查衔接。"
    }
  ]
}
```

`candidates` 初始配置为 `1..10` 项；每项 `fileSize` 大于 0 且不超过单文件上限，合计不超过批次上限，`clientFileKey` 与 `sortOrder` 均唯一且顺序连续。首版 `issueResponses=[]`；修订版必须恰好覆盖当前任务全部 open 问题。成功响应至少返回 `ready=true`、`taskId`、`taskKind`、`taskStatus`、规范化候选摘要、`maxCandidates/maxFileSize/maxBatchSize`、`openIssueSnapshotHash` 和 `allowedActions=["version.add"]`。预检是无锁、无写库、无文件副作用的尽早拒绝，只读取并验证当前用户就是任务当前委派的活动 `creator`、完整任务上下文、项目/目录就绪、open 问题集合与逐条处理说明、未解决提交、候选数量/顺序/扩展名/大小、业务文件名和目录快照可生成；预检不访问 NAS、不检查实际目标文件、不保留版本号、不创建提交或文件引用，也不承诺后续 create 必然成功。

预检失败、权限撤销、任务上下文切换或用户换文件时不得执行上传。预检只能校验文件名和声明大小；真实字节签名、容器品牌和摘要仍只能在上传后校验。上传已经成功但业务提交尚未建立引用即失败时，孤儿私有文件由平台保留、对账和回收机制治理，前端不得盲删。

```http
POST /shot-grid/tasks/{taskId}/version-submissions
Permission: shotgrid:version:add
Header: X-Idempotency-Key
```

请求：

```json
{
  "candidates": [
    {
      "clientFileKey": "local-01",
      "fileId": "5ed39e04-2f29-45ab-a58c-4f8168f5131a",
      "sortOrder": 0,
      "candidateNote": "动作节奏更快"
    },
    {
      "clientFileKey": "local-02",
      "fileId": "7bc27aa5-e61d-40a8-86fb-b3494fac65b0",
      "sortOrder": 1,
      "candidateNote": "表演更自然"
    }
  ],
  "changelog": "根据上一轮意见加快人物起身动作",
  "aiParams": null,
  "openIssueSnapshotHash": "8d5c...省略...e41a",
  "issueResponses": [
    {
      "issueId": 7101,
      "responseText": "已调整起身动作节奏，并在当前版本重新检查衔接。"
    }
  ]
}
```

提交前必须验证：

- 当前用户必须就是任务当前的 `assignee_user_id`；不存在项目管理人、平台管理员、超级管理员或全项目范围代提交权限；
- 任务负责人仍是 `member_status='active' + project_role='creator'` 的项目成员，平台账号有效且用户昵称可用；若该持久状态在任务创建后失效，返回 `SG_TASK_ASSIGNEE_STATE_INVALID`/409，而不是把它当作新分配请求参数错误；
- 任务状态是 `in_progress` 或 `revision`；
- `in_progress` 首版不得携带问题处理说明；`revision` 必须存在 open 问题，且 `issueResponses` 与锁内重查的 open 问题集合完全一致；
- create 必须回传 preflight 返回的 `openIssueSnapshotHash`；后端按稳定 `issueId + originVersionId` 集合重新计算并比较，不一致返回 `SG_ISSUE_SNAPSHOT_CONFLICT`，随后仍逐项校验处理说明，不能只相信哈希；
- 每个 `fileId` 对应受保护、有效且当前用户有权使用的文件；候选 ID、文件 ID、排序均不得重复；
- 每个文件尚未被其他提交候选或正式候选引用，同一批次 SHA-256 重复内容拒绝；
- 项目存储、所属集/镜头目录或资产目录已经 `ready`；
- 任务必须具有完整稳定目录绑定；Worker/重试时重新计算的目标路径必须与暂存快照一致，否则以 `SG_VERSION_TARGET_PATH_CONFLICT`/409 失败，不能复用仅表示非法路径输入的 `SG_STORAGE_PATH_INVALID`；
- 当前任务不存在活动或待处理失败的版本提交；
- `shot_video` 只接受扩展名匹配且真实字节具有允许的 MP4/MOV 容器签名/品牌的文件；
- `asset_image` 只接受扩展名匹配且真实字节具有 JPEG/PNG 签名的文件；当前不探测 codec、视频轨、可解码性或转码结果，不能把容器/图片签名嗅探描述成完整媒体有效性验证；
- `asset_image` 任务所属制作分项必须已经填写且安全规范化后非空，否则返回 `SG_ASSET_PRODUCTION_ITEM_REQUIRED`，不得生成缺段文件名。

create 不能信任预检结果。后端必须在上传后重新锁定项目与任务，并在锁内重取当前委派人、活动 `creator` 成员状态、平台账号状态、任务状态、未解决提交和稳定目录上下文，再锁定并复核源文件授权、存储键、摘要与大小；该正式复检负责关闭 preflight 与 create 之间的 TOCTOU 窗口，且不允许 `director`、管理员或全项目范围代提交。

锁定任务行后，在一个短数据库事务中：

1. 分配任务范围内下一个保留版本号；
2. 生成一次 `generated_at_ms`，按稳定顺序分配连续候选号并生成每个候选不可变 `business_file_name`；
3. 计算并保存每个候选的 NAS 正式相对路径和同目录临时路径；
4. 创建一个 `sg_version_submission(status=pending)` 和全部 `sg_version_submission_file`；
5. 为每条 open 问题创建不可变 `sg_version_issue_response`；
6. 为全部源文件创建 `businessType=shotgrid_version_submission` 临时平台文件引用；
7. 提交事务并返回 HTTP 202。

初始响应至少返回：

```json
{
  "code": 202,
  "data": {
    "submissionId": 8004,
    "submissionStatus": "pending",
    "reservedVersionNumber": "V004",
    "candidateCount": 2,
    "candidates": [
      {
        "candidateNumber": "V004_01",
        "businessFileName": "WGZR_EP001_001_S001_YJF_V004_01_1786094626499.mp4"
      },
      {
        "candidateNumber": "V004_02",
        "businessFileName": "WGZR_EP001_001_S001_YJF_V004_02_1786094626499.mov"
      }
    ],
    "statusUrl": "/shot-grid/version-submissions/8004",
    "taskStatus": "revision"
  }
}
```

Worker 按第 7.4 节完成 NAS 发布后，在一个短数据库事务中：

1. 创建一个 `sg_version`；
2. 按冻结顺序创建全部 `sg_version_candidate` 和各候选主 `sg_version_file`；
3. 将全部源文件引用从 `shotgrid_version_submission` 切换为正式 `shotgrid_version_candidate` 引用；
4. 通过 `submission_id` 将本次逐条问题处理说明关联到新版本；
5. 创建 `review_mode=auto_single`、`review_status=active` 的审核单和版本关系；
6. 把任务改为 `pending_review`；
7. 把提交改为 `committed`；正式版本通过 `sg_version.submission_id` 反向关联，不在提交表重复保存 `version_id`；
8. 提交事务。

提交状态接口：

```http
GET  /shot-grid/tasks/{taskId}/version-submissions/current
GET  /shot-grid/version-submissions/{submissionId}
POST /shot-grid/version-submissions/{submissionId}/retry
Permissions:
  shotgrid:version:query
  shotgrid:version:retry
```

- `current` 使用 `shotgrid:version:query`，用于详情刷新后恢复当前未解决提交；没有未解决提交时返回 `data=null`。
- 只有任务当前委派的活动 `creator` 本人可以重试由本人创建的失败提交；项目管理人和管理员可以查询其数据范围内的提交，但不得代重试。
- `retry` 仅允许 `failed`，重新验证任务负责人、源文件、NAS 路径和项目状态，并复用原版本号、时间戳和业务文件名。
- `committed` 响应返回 `versionId`、`candidateCount`、候选摘要、`reviewListId`、`versionStatus=pending_review` 和 `taskStatus=pending_review`；单候选轮次返回系统自动设置的 `selectedCandidateId`，多候选轮次初始返回 `null`。
- 第一阶段文件上传已由基座独立提交，当前平台单文件上限为 100 MiB，`mov` 已加入上传白名单。暂存或发布失败不得谎报版本成功；已建立临时引用的源文件继续受删除保护，最终无引用文件才进入平台保留、对账和回收机制。
- 前端自动轮询单轮最多 30 次，连续错误 3 次暂停，并使用上限 30 秒的指数退避；401/403/404 立即停止自动轮询，终态允许手工刷新。`failed` 必须重试原行，不能新建第二条提交。
- create 返回结果未知时，前端复用内存中的原有序 `fileId` 列表和 `X-Idempotency-Key` 重放 create，并跳过 preflight 与上传；同键但候选文件、顺序、说明或问题响应不同仍返回 `SG_IDEMPOTENCY_CONFLICT`。任务、候选或操作 generation 已变化时，迟到响应不得刷新当前详情。

### 15.4 审核与循环修改

制作人任务页读取当前问题：

```http
GET /shot-grid/tasks/{taskId}/issues?status=open
Permission: shotgrid:note:list
```

响应按来源版本号、问题创建时间稳定排序，返回每条问题的 `issueId/originVersionId/originVersionNumber/originCandidateId/originCandidateNumber/content/mediaTimeMs/annotations/status/resolvedInVersionId`，以及已提交版本上的 `responses[]` 和包含 `checkedCandidateId` 的 `verifications[]`。制作人员只能读取有权访问任务的数据，不能在该接口回复、解决或确认问题。

审核页读取当前版本上下文：

```http
GET /shot-grid/versions/{versionId}/review-context
Permission: shotgrid:version:review
```

响应至少分为：

```json
{
  "currentVersion": {
    "versionId": 5002,
    "versionNumber": "V002",
    "selectedCandidateId": 6202,
    "candidates": [
      { "candidateId": 6201, "candidateNumber": "V002_01", "sortOrder": 0 },
      { "candidateId": 6202, "candidateNumber": "V002_02", "sortOrder": 1 }
    ]
  },
  "carriedIssues": [
    {
      "issueId": 7101,
      "originVersionId": 5001,
      "originVersionNumber": "V001",
      "content": "起身动作节奏过慢",
      "annotations": null,
      "currentVersionResponse": {
        "responseText": "已调整起身节奏并检查前后衔接。"
      }
    }
  ],
  "currentVersionIssues": []
}
```

`carriedIssues` 只包含来源版本早于当前版本、提交当前版本时仍 open 且具有本版处理说明的问题；`currentVersionIssues` 是审核人在当前版本新建的问题。接口必须同时验证同任务、同项目和当前版本状态，不能由前端拼接多个版本列表推断审核上下文。

审核人选择本轮最佳候选：

```http
PUT /shot-grid/review-lists/{reviewListId}/versions/{versionId}/selection
Permission: shotgrid:version:review
Header: X-Idempotency-Key
```

请求体为 `{ "candidateId": 6202, "lockVersion": 0 }`。后端锁定项目、自动审核单、版本与候选后，校验候选属于路径版本、版本仍为 `pending_review`、审核单仍为 `active`，写入 `sg_version_candidate_selection`、更新 `sg_version.selected_candidate_id/selected_by/selected_time` 并递增版本锁。当前版本存在任何问题草稿时禁止切换到其他候选，返回 `SG_CANDIDATE_SELECTION_LOCKED`。同一幂等键、同一请求直接重放首次结果；使用新幂等键再次选择当前候选会留下不改变版本锁的幂等记录，操作审计结果标记 `changed=false`，不会伪造一次候选切换。人工批量审核单只负责组织轮次，候选选择仍写回该轮次对应的 `auto_single` 审核上下文。

审核人在当前版本保存私有问题草稿：

```http
POST /shot-grid/versions/{versionId}/issues
Permission: shotgrid:note:add
```

该兼容路径不再直接创建正式 `sg_note`，而是写入当前活动 `auto_single` 审核单的 `sg_review_issue_draft`。请求必须携带当前 `candidateId`，且该值等于锁内 `sg_version.selected_candidate_id`；尚未选择候选或请求候选已过期时拒绝。请求可携带 `content`、`mediaTimeMs`、`annotations` 和 `referenceFileIds[]`，但 `content` 规范化后非空或 `annotations.items` 至少一项有效，二者必须满足其一；参考文件不能单独代替问题描述或画面标注。草稿固定绑定路径版本、当前最佳候选、当前审核单和创建审核人，仅通过审核上下文返回；制作人任务问题列表、版本正式问题列表和生产履历不得返回草稿。

`referenceFileIds[]` 最多 5 项且不可重复，每项必须是当前审核人上传、仍有效的本地受保护文件，单个不超过 20 MiB，扩展名限 BMP/GIF/JPG/PNG、PDF、Office、TXT、MP4/MOV。草稿引用使用 `sys_file_reference(businessType=shot_grid_review_issue_draft,businessId=draftId)`；`reject` 与问题发布处于同一事务，把引用迁移到 `businessType=shot_grid_review_issue,businessId=noteId` 后删除草稿引用。该能力复用平台引用表，不新增附件 JSON 列或平行文件表。

草稿编辑与删除：

```http
PUT    /shot-grid/versions/{versionId}/issue-drafts/{draftId}
DELETE /shot-grid/versions/{versionId}/issue-drafts/{draftId}
Permission: shotgrid:note:add
```

两条路径都要求当前版本和任务仍为 `pending_review`、自动审核单仍为 `active`，并携带当前 `lockVersion`。PUT 重新校验文字/标注和媒体时间；DELETE 不保留可恢复副本。审核草稿只在发布前可变，不能借这些接口修改或删除正式 `sg_note`。

最终审核动作：

```http
POST /shot-grid/versions/{versionId}/review-actions
Permission: shotgrid:version:review
Header: X-Idempotency-Key
```

V002 及后续版本请求体示例：

```json
{
  "actionType": "reject",
  "selectedCandidateId": 6202,
  "reason": "仍有一项需要继续修改",
  "lockVersion": 0,
  "issueVerifications": [
    {
      "issueId": 7101,
      "result": "still_present",
      "comment": "节奏仍偏慢，请继续压缩。"
    }
  ]
}
```

- 审核动作必须使用持久幂等键；同一审核人、版本和幂等键的同一规范请求重放首次结果，同键异请求返回 `SG_IDEMPOTENCY_CONFLICT`。
- `approve/reject/defer` 都必须回传锁内当前 `selectedCandidateId` 并纳入命令哈希；未选择、候选不属于版本、候选已被他人切换或版本锁过期均返回 409。审核动作、问题发布和历史问题确认都绑定该候选。
- 对 V002 及后续版本，`approve/reject` 的 `issueVerifications` 必须恰好覆盖 `review-context.carriedIssues`，不得遗漏、重复、夹带当前版本新问题或其他任务问题；V001 没有带入问题时必须为空。
- `reject`：逐条确认结果与审核动作在同一事务保存；`still_present` 必须填写未解决原因；至少一条结果为 `still_present`、当前版本已存在正式 open 问题或存在问题草稿。事务在状态转换前把当前审核单全部草稿批量写为绑定当前版本的不可变 `sg_note` 并删除草稿；随后版本变为 `rejected`，自动审核单完成，任务变为 `revision`，制作人此时首次看到本轮问题，全部未关闭问题在任务页归属当前被退回版本。任一步失败必须整体回滚。总述 `reason` 可空，不能替代修改问题。
- 制作人员收到全部 open 问题后在线下修改，再按 15.3 逐条填写 `issueResponses` 并提交；系统创建下一版本号和新的自动审核单。
- `approve`：所有带入问题的结果必须都是 `resolved`，并且当前版本不存在新建 open 问题或问题草稿；存在草稿时返回 `SG_REVIEW_DRAFTS_EXIST`，不允许静默丢弃草稿。同一事务关闭这些问题、记录 `resolvedInVersionId`、把版本改为 `final`、完成自动审核单和任务，并创建唯一 `sg_final_delivery(pending)`。响应的 `finalDelivery` 返回交付 ID、状态和 `FINAL/` 相对路径；它表示已入队，不表示 NAS 已发布。版本详情和 `review-context.currentVersion` 持续返回最新 `finalDelivery`，页面仅在 `deliveryStatus=published` 时显示最终文件已落 NAS。
- `defer`：保留待审核状态，只记录动作，私有问题草稿保持原状且仍不对制作人公开。
- 每个问题永久绑定来源版本并可跨多版保持 open；后续版本通过处理说明和确认记录与问题关联，不能迁移问题、复制问题或覆盖旧版本文件。任务页通过派生 `pendingVersion` 把当前待处理工作展示在最近被退回版本下，来源版本只展示历史结果。
- 旧的 `/notes/{noteId}/replies|reply|resolve` 已移除；问题只能通过后续版本审核动作中的逐条确认解决。

### 15.5 其余资源路径

以下路径继续冻结：

```text
/shot-grid/projects/{projectId}/assets
/shot-grid/projects/{projectId}/assets/{assetId}/production-history
/shot-grid/projects/{projectId}/shots/{shotId}/production-history
/shot-grid/projects/{projectId}/tasks
/shot-grid/projects/{projectId}/versions
/shot-grid/projects/{projectId}/review-actions
/shot-grid/projects/{projectId}/review-lists
/shot-grid/projects/{projectId}/files
/shot-grid/tasks/mine
/shot-grid/tasks/{taskId}
/shot-grid/tasks/{taskId}/issues
/shot-grid/tasks/{taskId}/versions
/shot-grid/tasks/{taskId}/version-submissions/preflight
/shot-grid/tasks/{taskId}/version-submissions
/shot-grid/tasks/{taskId}/version-submissions/current
/shot-grid/version-submissions/{submissionId}
/shot-grid/versions/{versionId}
/shot-grid/versions/{versionId}/review-context
/shot-grid/versions/{versionId}/issues
/shot-grid/versions/{versionId}/issue-drafts/{draftId}
/shot-grid/versions/{versionId}/review-actions
/shot-grid/versions/{versionId}/final-delivery/retry
/shot-grid/review-lists/{reviewListId}
```

动作接口：

```text
POST /shot-grid/tasks/{taskId}/start
POST /shot-grid/tasks/{taskId}/version-submissions/preflight
POST /shot-grid/tasks/{taskId}/version-submissions
POST /shot-grid/version-submissions/{submissionId}/retry
POST /shot-grid/versions/{versionId}/final-delivery/retry
POST /shot-grid/versions/{versionId}/issues
PUT  /shot-grid/versions/{versionId}/issue-drafts/{draftId}
DELETE /shot-grid/versions/{versionId}/issue-drafts/{draftId}
POST /shot-grid/versions/{versionId}/review-actions
POST /shot-grid/review-lists/{reviewListId}/versions
PUT  /shot-grid/review-lists/{reviewListId}/versions/order
```

旧 `/projects/{projectId}/notes`、`/versions/{versionId}/notes` 和 `/notes/{noteId}/replies|reply|resolve` 路径全部移除，不再提供兼容读取或写入动作。

### 15.6 资产 API

```http
GET  /shot-grid/projects/{projectId}/asset-assignee-options
GET  /shot-grid/projects/{projectId}/assets
POST /shot-grid/projects/{projectId}/assets
GET  /shot-grid/projects/{projectId}/assets/{assetId}
PUT  /shot-grid/projects/{projectId}/assets/{assetId}
POST /shot-grid/projects/{projectId}/assets/{assetId}/archive
GET  /shot-grid/projects/{projectId}/assets/{assetId}/items
POST /shot-grid/projects/{projectId}/assets/{assetId}/items
PUT  /shot-grid/projects/{projectId}/asset-items/{assetItemId}
POST /shot-grid/projects/{projectId}/asset-items/{assetItemId}/archive
POST /shot-grid/projects/{projectId}/asset-items/{assetItemId}/delete
Permissions:
  shotgrid:asset:list|add|query|edit|archive
```

`asset-assignee-options` 要求 `shotgrid:asset:list` 与项目访问，支持 `pageNum/pageSize/keyword`；只返回 `projectRole=creator` 的活动项目成员及有效未删除平台账号的 `userId/userName/nickName/avatar/deptId/deptName/projectRole/producerCode` 安全摘要，其中兼容字段 `producerCode` 由 `sys_user.nick_name` 派生。关键字只匹配账号和昵称；候选响应不是写入授权，创建、编辑、导入、首次分配和改派事务仍重新校验成员状态、项目角色和用户昵称。

列表支持 `assetType`、`assetStatus`、`assigneeUserId`、`keyword`、分页和白名单排序。资产列表、详情和制作分项响应分别包含：

- 资产 `allowedActions`：可选 `asset.edit`、`assetItem.add`、`asset.archive`；资产归档只在不存在活动制作分项和活动任务时返回。
- 制作分项 `allowedActions`：可选 `assetItem.edit`、`assetItem.archive`、`assetItem.delete`、`task.assign`；已有正式版本后不返回普通编辑，活动任务阻止归档，任务已完成或存在任何非 `committed` 版本提交时不返回分配/改派。

- `assetItem.delete` 仅在任务未分配或仍为 `not_started`、没有正式版本且没有非 `committed` 版本提交时返回；`failed` 提交同样阻止删除。项目可写、NAS 就绪、父资产/分项活动状态、平台 `shotgrid:asset:archive` 权限及项目管理范围仍是共同前提。

- 制作分项 `thumbnail`：只来自当前最新版本首个缩略图文件；无缩略图返回 `null`，不回退旧版本。
- 父资产 `thumbnail`：按活动制作分项 `(sortOrder, assetItemId)` 升序选择第一张可用缩略图；前端不得根据视图或加载顺序重新计算。
- 缩略图 URL 只使用受保护相对路径 `/shot-grid/versions/{versionId}/files/{fileId}/download`，必须经统一鉴权请求层获取 Blob。

`POST /asset-items/{assetItemId}/delete` 使用上述完整项目路径，请求为 `{ "reason": "新增后不再需要", "lockVersion": 0 }`，原因去除首尾空白后必须为 1–500 字。成功返回 `{ projectId, assetId, deletedAssetItemId }`。Service 在锁内重新校验并将目标分项标记为 `lifecycle_status=archived, del_flag=2`，存在未开始任务时一并逻辑删除该任务；任务已开始返回 `SG_ASSET_TASK_ALREADY_STARTED`，已有版本返回 `SG_ASSET_HAS_VERSION`，未完成提交返回 `SG_ASSET_ITEM_SUBMISSION_IN_PROGRESS`，锁冲突返回 `SG_OPTIMISTIC_LOCK_CONFLICT`，均为 HTTP 409。删除原因与结果必须同事务写审计，任何失败整体回滚。父资产和其他分项不变，不删除 NAS 文件，也不创建清理任务；可以删掉最后一个未开始分项并保留空资产，后续重新新增。归档接口保持原语义，归档的历史分项继续展示。删除成功后前端刷新详情、资产列表、缩略图与履历，已删分项不再出现在标签和卡片中。

创建请求示例：

```json
{
  "assetType": "Environment",
  "assetName": "动力舱室内",
  "description": "低温休眠舱内部环境",
  "sortOrder": 10,
  "remark": "保持冷蓝色调",
  "items": [
    {
      "productionItem": "动力舱恐怖气氛主视角",
      "description": "恐怖气氛主视角",
      "sortOrder": 10
    }
  ]
}
```

创建资产的数据库事务必须：

1. 生成并冻结安全 `storageDirName` 和路径键；
2. 创建资产；
3. 创建一个或多个制作分项；制作分项名称允许为空；
4. 不创建 `ensure_asset_directory` Outbox，目录状态保持 `not_created`；
5. 所有制作分项保持 `unassigned`，创建接口不接收 `assigneeUserId/taskDescription`，也不创建任务；
6. 项目管理人后续通过第 15.1 节独立委派，第一次委派才创建 `not_started` 的唯一 `asset_image` 任务；制作人开始该资产任一制作分项任务时才异步确保共享资产目录。

资产详情返回制作分项列表、每个分项的唯一任务及最新/最终版本、后端动作集合、确定性缩略图、使用镜头数和 `directoryStatus`。资产类型、显示名称、规范键和 `storageDirName/storagePathKey` 在创建时组成不可拆分的稳定身份，普通 PUT 只接受描述、排序、备注和 `lockVersion`；该 PUT 是三项非身份主数据的完整快照，省略描述或备注表示清空，省略排序表示归零。重命名、改类型或目录迁移必须使用后续受控动作。制作分项仅在未分配或唯一任务仍为 `not_started` 且尚无版本时可补充或纠正主数据；任务进入 `preparing/in_progress/pending_review/revision/completed` 后，其名称、描述、排序和备注等主数据立即禁止普通修改。归档不能级联删除历史版本。资产和制作分项写接口均在锁内拒绝 `completed/archived` 项目；资产导入 preview 先普通读取拒绝，commit 再锁项目重检。

前端展示边界：资产列表、卡片和类型看板使用父资产 `thumbnail` 作为单张代表图；资产详情头部忽略父资产代表图，按活动 `items` 的 `(sortOrder, assetItemId)` 稳定顺序逐项展示 `item.thumbnail`、制作分项名称及 `latestVersion` 状态。任一分项 `thumbnail=null` 时保留该分项独立占位，禁止回退旧版本、父资产代表图、归档分项或其他分项图片。

### 15.7 任务查询与编辑 API

```http
GET /shot-grid/tasks/mine
GET /shot-grid/projects/{projectId}/tasks
GET /shot-grid/tasks/{taskId}
PUT /shot-grid/tasks/{taskId}
Permissions:
  shotgrid:task:list|query|edit
```

项目任务列表支持 `taskKind`、`taskStatus`、`assigneeUserId`、`dueDateFrom`、`dueDateTo`、`priority`、`scope=project|mine` 和分页。所属项目成员可以只读查看项目任务；工作台使用独立 `GET /shot-grid/tasks/mine` 跨项目查询，负责人范围由后端根据当前用户强制注入，不能相信前端筛选来判定写权限。任务列表与详情的 `assignee` 返回安全摘要 `{userId,userName?,nickName?,producerCode?,memberStatus?}`；业务页面统一优先展示 `userName`，`nickName` 仅作为缺失时回退。

任务详情审计字段不得暴露目录 Worker 的租约 owner。历史任务若曾把内部 owner 误写入 `updateBy`，服务端应从该镜头最近成功的目录操作回溯业务发起人；只有发起人证据缺失时才显示“系统目录服务”。

`PUT` 只允许项目管理人或管理员在任务仍为 `not_started` 时修改 `requirements`、`priority`、`dueDate` 和 `lockVersion`，不能直接修改状态或负责人。进入 `preparing/in_progress/pending_review/revision/completed` 后详情不再返回 `task.edit`，直接调用更新接口也必须在任务行锁内返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。负责人变更必须使用 `assign` 动作；状态只通过开始、版本提交和审核动作改变。

独立业务前端工作台真实调用 `/tasks/mine`，支持任务类型、状态、优先级、截止区间、关键字、排序和服务端分页；行项进入 `/tasks/:taskId`。任务详情展示项目、归属对象、要求、负责人、锁版本及版本摘要，并仅在平台权限与 `allowedActions` 同时满足时开放编辑或版本提交；开工操作位于镜头/资产管理页，任务详情只等待管理人员放行。

镜头任务的 `GET /shot-grid/tasks/{taskId}` 额外返回详情专用 `shotProduction`：`durationMs/description/shotSize/cameraPosition/cameraMovement/focalLength/dialogue/soundEffect/colorReference/remark`。这些字段来自任务当前关联的 `sg_shot` 只读投影，供制作人在任务详情完整查看制作资料；任务列表及其中的 `target` 继续保持摘要结构，不返回该完整对象。分配和改派弹窗使用镜头详情中的同组字段只读展示；任务 `requirements` 与 `shotProduction.description` 不同时，前端把前者作为“任务补充要求”独立显示，相同时不重复。

### 15.8 版本与修改问题查询 API

```http
GET  /shot-grid/tasks/{taskId}/versions
GET  /shot-grid/versions/{versionId}
GET  /shot-grid/tasks/{taskId}/issues
GET  /shot-grid/versions/{versionId}/review-context
POST /shot-grid/versions/{versionId}/issues
Permissions:
  shotgrid:version:list|query
  shotgrid:note:list|add
```

- 版本和问题列表必须分页；版本默认按版本号倒序，open 问题按来源版本号和创建时间稳定排序。
- 版本列表和详情中的 `submitterName` 使用 `sys_user.user_name` 展示业务用户名；`sys_user.nick_name` 仅继续用于冻结的业务文件名制作人标识，展示规则不得触发历史文件重命名。
- `GET /shot-grid/versions/{versionId}` 额外返回非空只读 `productionTarget`，它与版本、任务、镜头或资产制作分项在同一次受保护查询中投影，不新增审核单重复事实。`targetType=shot` 时返回 `requirements + shot{durationMs,description,shotSize,cameraPosition,cameraMovement,focalLength,dialogue,soundEffect,colorReference,remark}`；`targetType=asset_item` 时返回 `requirements + asset{assetId,assetItemId,assetType,assetName,assetDescription,assetRemark,productionItem,itemDescription,itemRemark}`。两种目标只能返回对应的一个子对象；接口继续只要求 `shotgrid:version:query` 与项目访问，不额外要求 `shotgrid:task:query`。
- 任务详情内的版本历史和版本详情使用真实查询 API；`/versions/:versionId` 归属 `reviews` 路由范围。下载必须调用第 15.10 节专用授权接口，不得拼接平台存储地址。
- 所属项目成员可以只读访问版本、问题、处理说明和确认历史；制作人员只能随本人任务版本提交写入逐条处理说明，不能创建或确认问题。
- 保存问题草稿接受 `content/mediaTimeMs/annotations/referenceFileIds`，不接受 `isMandatory`；文字或标注必须至少一项有效，并按第 16 节校验。审核上下文额外返回 `currentVersionDrafts[]`，每项包含 `draftId/projectId/reviewListId/versionId/reviewerUserId/reviewerName/content/mediaTimeMs/annotations/referenceFiles/lockVersion/createTime/updateTime`。正式问题的 `referenceFiles[]` 同样返回 `fileId/originalName/contentType/fileSize/downloadUrl`。
- 草稿参考文件下载：`GET /shot-grid/issue-drafts/{draftId}/reference-files/{fileId}/download`；仅审核方在实时项目权限校验通过后访问。正式问题参考文件下载：`GET /shot-grid/issues/{issueId}/reference-files/{fileId}/download`；制作人与其他授权项目成员必须同时通过项目关系、问题引用和平台显式 deny 校验。
- 镜头视频草稿的 `mediaTimeMs` 不能超过媒体允许范围；资产图片草稿禁止携带 `mediaTimeMs`。草稿在审核待决期间可携带乐观锁编辑或删除；经 `reject` 发布为正式问题后不可覆盖，状态只由后续版本审核动作改变。
- 旧 `/versions/{versionId}/notes` 与 `/notes/{noteId}/replies|reply|resolve` 全部移除。

### 15.9 人工批量审核单 API

本节接口已转化为代码。`manual_batch` 使用现有主表与有序多版本关系，不新增重复事实表；写接口由平台权限、项目管理人角色、项目归属、状态机、乐观锁和同事务审计共同约束。

```http
GET  /shot-grid/projects/{projectId}/review-lists
POST /shot-grid/projects/{projectId}/review-lists
GET  /shot-grid/review-lists/{reviewListId}
PUT  /shot-grid/review-lists/{reviewListId}
POST /shot-grid/review-lists/{reviewListId}/versions
DELETE /shot-grid/review-lists/{reviewListId}/versions/{versionId}
PUT  /shot-grid/review-lists/{reviewListId}/versions/order
POST /shot-grid/review-lists/{reviewListId}/activate
POST /shot-grid/review-lists/{reviewListId}/complete
POST /shot-grid/review-lists/{reviewListId}/archive
Permissions:
  shotgrid:reviewList:list|add|query|edit|activate|complete|archive
```

- 人工创建时 `reviewMode=manual_batch`、`reviewStatus=draft`；自动单版本审核单不接受这些编辑接口。
- 只有草稿可以添加、移除或排序版本；激活后版本集合冻结。
- 加入的版本必须属于同一项目且为可审核版本，不能跨项目关联。
- 激活、完成、归档和排序请求均携带 `lockVersion`；排序提交完整 `{versionId, sortOrder}` 集合并在一个事务内校验唯一性。
- 完成人工审核单不批量修改版本状态；版本仍通过 `/versions/{versionId}/review-actions` 独立审核。
- 创建接口可在同一事务携带初始 `versionIds`，避免前端两步创建产生无版本孤立草稿；后续增删和排序仍只允许草稿。
- 激活时所有版本必须仍为 `pending_review`；完成时不得存在 `pending_review` 版本。

### 15.10 Shot Grid 文件下载与 NAS 路径 API

```http
GET /shot-grid/projects/{projectId}/files
GET /shot-grid/versions/{versionId}/files/{fileId}/download
GET /shot-grid/shots/{shotId}/nas-path
GET /shot-grid/assets/{assetId}/nas-path
Permission:
  shotgrid:file:download
  shotgrid:storage:path
```

- 项目文件分页使用 `shotgrid:storage:path` 与项目访问双门禁，只查询活动 `sg_version_file → sg_version → sg_task → sys_file_info` 正式关系。支持 `keyword`、`fileRole`、`versionStatus`、`taskKind`、分页及 `submittedTime|businessFileName|fileSize` 白名单排序；关键字只匹配业务文件名、原文件名和任务名。
- 文件项返回 `fileId/projectId/versionId/taskId/taskName/taskKind/versionNo/versionNumber/versionStatus/originalName/businessFileName/role/isPrimary/contentType/fileSize/nasRelativePath/publishedTime/submittedTime/downloadUrl/thumbnail`。`thumbnail` 只投影同一版本中活动的首个 `file_role=thumbnail` 文件，结构为 `{fileId,url}`；没有派生缩略图时返回 `null`，不得回退旧版本、原始大文件或公开地址。不得返回 `storedName`、`storageKey`、平台物理路径、文件哈希、NAS 凭据或内部路径键；镜头/资产归属继续通过任务详情推导，不在文件关系重复维护。
- 下载接口先执行版本、任务、项目角色、`sg_version_file` 与 `sys_file_reference(businessType=shotgrid_version)` 双重文件关系校验，再复用平台流式下载与 HTTP Range 能力，并以净化后的 `business_file_name` 设置安全下载名；平台显式 `deny` ACL 始终优先于业务成员授权。
- 原生视频播放器使用 `POST /shot-grid/versions/{versionId}/files/{fileId}/playback-ticket` 领取短期票据，再访问 `GET /shot-grid/playback/{ticket}/versions/{versionId}/files/{fileId}`。Redis 只保存票据哈希、用户/会话哈希和资源绑定，不保存明文登录 Token；播放请求每次校验登录会话仍有效，并从数据库重建用户权限后重新执行项目范围、文件关系与 ACL 决策。Redis 不可用时失败关闭，不回退为公开文件 URL。
- 路径接口只返回经权限校验的目录/文件路径快照和复制文本，不返回 NAS 凭据或平台 `storageKey`。
- 浏览器端未确认桌面协议处理器前，接口和页面都不承诺直接打开 UNC 路径。
- 用户通过 SMB 直接访问 NAS 时不经过平台权限；部署必须额外配置 NAS/AD/Windows 共享 ACL。

### 15.11 镜头与资产生产履历读取 API

生产履历是镜头或资产详情页的只读聚合读模型，用于一次返回来源对象、当前阶段、任务泳道、不可覆盖版本及其审核闭环。前端不得为每个制作分项、版本或问题分别串联现有详情接口形成 N+1 请求，也不得在浏览器中重新推断阶段、计数和证据等级。

```http
GET /shot-grid/projects/{projectId}/shots/{shotId}/production-history
Permissions (strict AND):
- shotgrid:shot:query
- shotgrid:version:query
- shotgrid:reviewList:query
- shotgrid:note:list

GET /shot-grid/projects/{projectId}/assets/{assetId}/production-history
Permissions (strict AND):
- shotgrid:asset:query
- shotgrid:version:query
- shotgrid:reviewList:query
- shotgrid:note:list
```

两个接口均要求有效登录态、上述四项平台权限的严格 AND 和 `ProjectAccess` 项目访问；资源必须属于路径中的项目。镜头接口以 `shotgrid:shot:query` 作为对象读取权限，资产接口以 `shotgrid:asset:query` 作为对象读取权限，两者都必须同时具备 `shotgrid:version:query`、`shotgrid:reviewList:query` 和 `shotgrid:note:list`，因为同一响应会完整聚合版本、审核单、审核动作和修改问题。任一权限缺失时必须按平台统一鉴权语义拒绝整个请求，不得只凭对象查询权限返回敏感子集，也不得静默删减字段形成含义不完整的履历。镜头不存在或不属于项目时返回 HTTP 404 / `SG_SHOT_NOT_FOUND`，资产不存在或不属于项目时返回 HTTP 404 / `SG_ASSET_NOT_FOUND`；认证和鉴权失败沿用平台统一语义。成功响应使用标准 envelope，`data` 固定为：

```json
{
  "subject": {},
  "summary": {},
  "lanes": [],
  "events": []
}
```

#### 15.11.1 `subject` 与 `summary`

`subject` 返回当前详情对象的安全摘要：

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `subjectType` | `shot\|asset` | 路径决定，不接受前端输入 |
| `subjectId/projectId` | `int` | 真实领域主键 |
| `projectCode/projectName` | `string` | 项目安全摘要 |
| `code` | `string?` | 镜头稳定代码；资产可为空 |
| `name` | `string` | 镜头或资产显示名称 |
| `description` | `string?` | 当前主数据说明 |
| `lifecycleStatus` | `active\|archived` | 业务生命周期，不使用 `delFlag` 代替 |
| `assetType` | `Character\|Environment\|Prop?` | 仅资产返回 |
| `thumbnailFileId` | `string?` | 后端只在 `lifecycleStatus=active` 的泳道中按排序选择代表缩略图文件 ID；没有活动泳道缩略图时返回 `null`，不得回退到归档泳道；不返回公开 URL、NAS 路径或物理存储键 |
| `createdAt` | `datetime` | 领域对象创建时间 |

`summary` 返回整个对象的聚合阶段与计数：

```text
currentStage, activeStep,
laneCount, taskCount, versionCount,
reviewActionCount, rejectionCount,
issueCount, openIssueCount, resolvedIssueCount,
finalVersionCount
```

所有计数为大于等于 0 的整数。`currentStage` 与 `activeStep` 的映射固定为：

| `currentStage` | `activeStep` | 含义 |
| --- | ---: | --- |
| `created` | 0 | 来源对象已经建立但尚无任务 |
| `assigned` | 1 | 已建立任务，尚未开始 |
| `production` | 2 | 任务正在制作 |
| `review` | 4 | 已提交不可变版本，当前版本待审核；步骤 3“提交版本”已完成 |
| `revision` | 4 | 审核退回后的制作—提交—审核循环；具体返修节点由版本时间线表达 |
| `final` | 5 | 已存在最终版本且任务已完成 |

镜头只有一个 `shot` 泳道。资产的每个未逻辑删除制作分项形成一个 `assetItem` 泳道，并通过 `lifecycleStatus=active|archived` 保留业务归档状态；资产汇总阶段只读取 `active` 泳道，归档泳道继续保留在 `lanes/events` 供追溯但不阻塞当前进度。无活动泳道时为 `created/0`，全部活动泳道完成时为 `final/5`，任一活动泳道返修时为 `revision/4`，其余情况取未完成活动泳道中最早的 `activeStep`。历史计数覆盖响应中全部未逻辑删除泳道及其任务、版本和审核记录，包括已经业务归档但仍需追溯的制作分项。前端六步展示文案固定为“创建/导入、委派、制作、提交版本、审核、完成”；`revision` 不是第七步，返修循环在版本时间线中展开。

#### 15.11.2 `lanes`

每个泳道返回：

```text
laneId, laneType, name, sortOrder, lifecycleStatus,
sourceImportBatchId, currentStage, activeStep,
task, latestVersion, finalVersion,
versionCount, reviewActionCount, rejectionCount,
issueCount, openIssueCount
```

- `laneType` 只允许 `shot|assetItem`；镜头泳道 `laneId` 为镜头 ID，资产泳道 `laneId` 为制作分项 ID。
- `sourceImportBatchId` 只有当前正式记录保存了明确来源批次时才返回；为空时不得推断为 Excel 导入。
- `task` 为空表示尚未建立任务；非空时返回 `taskId/taskName/taskKind/taskStatus/priority/dueDate/assignee/createTime/updateTime`。`taskKind` 只允许 `shot_video|asset_image`，`taskStatus` 只允许 `not_started|preparing|in_progress|pending_review|revision|completed`；`preparing` 用于镜头或资产任务等待各自目录 Outbox。
- `assignee` 与本节其他操作人统一使用安全摘要 `{userId?, userName?, nickName?}`；页面优先显示账号 `userName`，昵称仅为补充或历史回退。
- `latestVersion` 和 `finalVersion` 使用 `{versionId,versionNo,versionNumber,versionStatus,submittedTime}`；`versionStatus` 只允许 `pending_review|rejected|final`。

#### 15.11.3 `events` 与证据等级

`events` 按 `occurredAt,eventId` 时间正序返回。通用字段为：

```text
eventId, eventType, occurredAt, evidenceLevel,
title, description, laneIds[], actor?, resourceRef,
importBatch?, versionCycle?
```

`eventType`、证据和负载规则固定为：

| `eventType` | 证据 | 规则 |
| --- | --- | --- |
| `subject_created` | `confirmed` | 来自镜头或资产正式创建时间；`resourceRef` 指向 `shot|asset` |
| `subject_imported` | `confirmed` | 仅在资产制作分项保存明确 `sourceImportBatchId` 且批次有提交时间时返回；`laneIds` 表示该批次建立的分项 |
| `lane_created` | `confirmed` | 仅用于 `sourceImportBatchId` 为空的手工资产制作分项，来自分项自身 `createTime/createBy`；`resourceRef` 指向 `assetItem`，导入分项不得重复返回该事件 |
| `task_created` | `inferred` | 任务 `createTime` 只能证明任务记录建立，标题固定表达“制作任务已建立”，不得宣称该时刻已有可审计的首次委派命令、开始或改派 |
| `version_cycle` | `confirmed` | 来自不可覆盖的正式版本；一个事件完整携带本版 `versionCycle` |

`evidenceLevel` 只允许 `confirmed|inferred`。页面必须把 `inferred` 显示为“按现有记录推断”，不得与确认事实使用相同视觉和文案。当前表结构不能重建的旧改派、旧开始、暂停或恢复历史必须缺省；禁止使用当前负责人、任务更新时间或通用操作日志反推并伪造事件。镜头当前不保存可直接证明的来源批次，因此不得根据名称、时间或 Excel 业务习惯生成镜头导入事件。

`resourceRef={resourceType,resourceId}` 只提供稳定资源标识，不返回前端路由。`resourceType` 允许 `shot|asset|assetItem|importBatch|task|version|reviewList|issue`。`importBatch` 只随 `subject_imported` 返回，字段为：

```text
batchId, originalFileName, importType, batchStatus,
committedBy?, committedTime?
```

`importType` 只允许 `shot|asset`，`batchStatus` 只允许 `previewed|committing|committed|failed|expired`。第一版业务端没有导入批次详情深链，前端只展示来源摘要。

#### 15.11.4 `versionCycle`

每个 `version_cycle` 事件包含：

```text
versionId, versionNo, versionNumber, versionStatus,
changelog, submittedTime, submitter,
primaryFile?, thumbnailFile?, autoReviewList?,
reviewActions[], sourceIssues[], issueResponses[], issueVerifications[]
```

- `primaryFile/thumbnailFile` 使用安全摘要 `{fileId,businessFileName,fileRole,isPrimary,contentType?,fileSize}`，不返回 NAS 路径、平台物理文件名、存储键或摘要；
- `autoReviewList` 为空表示当前版本没有可用自动审核单，否则返回 `reviewListId/reviewListName/reviewStatus`；
- `reviewActions` 是对本版执行的审核动作，字段为 `actionId/actionType/fromStatus/toStatus/reason/reviewer/createTime`，`actionType` 只允许 `approve|reject|defer`；
- `sourceIssues` 只包含首次在本版提出的问题，字段为 `issueId/originVersionId/originVersionNumber/reviewer/content/mediaTimeMs/hasAnnotations/annotationCount/status/resolvedInVersionId/resolvedInVersionNumber/createTime/updateTime`。生产履历不返回原始 `annotations` 聚合载荷，具体结构化画面批注只通过受权限保护的审核详情接口读取；
- `issueResponses` 只包含提交本版时制作人对历史 open 问题保存的逐条处理说明，字段为 `responseId/issueId/originVersionId/originVersionNumber/responseText/responder/createTime`；
- `issueVerifications` 只包含审核本版时对历史问题保存的逐条确认，字段为 `verificationId/issueId/originVersionId/originVersionNumber/checkedVersionId/checkedVersionNumber/result/comment/reviewer/createTime`，`result` 只允许 `resolved|still_present`。

四个数组按“本版审核动作、本版来源问题、本版处理说明、本版审核确认”分开投影，不得把某个问题的全部跨版本记录嵌回 `sourceIssues`，也不得复制或迁移问题身份。字段语义继续服从第 15.4 节的跨版本问题闭环。

#### 15.11.5 前端跳转、错误与实现边界

前端根据稳定资源标识和 `versionCycle` 中的关联对象使用 Vue Router 导航：任务进入 `/tasks/:taskId`，版本进入 `/versions/:versionId`，自动审核单进入 `/reviews/:reviewListId`。问题的文字、时间点、标注数量和状态摘要在版本节点内展开，具体画面标注进入所属审核单后按审核详情权限读取；当前审核页尚未实现按 `issueId` 定位，因此不得生成带 `issueId` 的伪深链。导入批次没有独立业务端详情路由时不渲染跳转。

页面必须实现加载、空历史、请求失败、无权限、资源不存在和重试状态；5xx 不得伪装为 `events=[]`。对象、项目或制作分项切换时取消过期请求并隔离迟到响应。

第一版不新增数据库表和 Alembic 迁移，只从 `sg_shot/sg_asset/sg_asset_item/sg_task/sg_version/sg_version_file/sg_review_list/sg_review_action/sg_note/sg_version_issue_response/sg_issue_verification/sg_import_batch` 等既有正式记录批量聚合。六阶段是当前进度投影，不等于六条确认审计事件。未来如需从上线时刻开始完整记录委派、改派、开始、暂停和恢复命令，可以评审后增加 append-only 的 `sg_production_event`；该表是后续增强项，不是本版已实现能力，也不得宣称能自动补齐历史事件。

## 16. 批注数据契约

`sg_review_issue_draft.annotations` 与发布后的 `sg_note.annotations` 使用同一结构；发布事务原样复制规范化 JSON。顶层包含 `schemaVersion`：

```json
{
  "schemaVersion": 1,
  "sourceWidth": 1920,
  "sourceHeight": 1080,
  "items": [
    {
      "id": "annotation-client-uuid",
      "type": "circle",
      "color": "#ff3b30",
      "strokeWidth": 0.004,
      "points": [
        { "x": 0.25, "y": 0.30 },
        { "x": 0.42, "y": 0.58 }
      ],
      "text": null
    }
  ]
}
```

规则：

- `x`、`y`、`strokeWidth` 使用 `0..1` 归一化值。
- 每个坐标必须校验范围。
- 服务端最多接受 100 个批注 item、每个 item 512 个点、合计 4096 个点，批注 JSON UTF-8 大小不超过 64 KiB；批注类型是满足 `^[A-Za-z][A-Za-z0-9_-]{0,31}$` 的安全可扩展字符串，不限定为当前 UI 已知图形。
- `sourceWidth`、`sourceHeight` 只用于还原与诊断，不作为坐标事实。
- 视频批注时间使用非负整数 `mediaTimeMs`，并且不能超过镜头时长；资产图片意见禁止携带该字段。
- 文本经过长度限制和安全转义。
- 不接受图片 Data URL、Blob URL 或任意 HTML。
- 当前前端工具约定：`point` 使用 1 个坐标，`rectangle` 和 `arrow` 使用 2 个起止坐标，`freehand` 使用 1 至 512 个连续坐标及归一化 `strokeWidth`，`text` 使用 1 个锚点和非空 `text`；自由曲线在拖动中实时预览，并按最小距离采样控制载荷，箭头渲染按媒体画幅换算线段角度，文字只通过 Vue 文本插值渲染。

## 17. 文件访问与媒体设计

### 17.1 项目成员文件下载授权

已确认：

- `sys_file_reference` 只表达业务引用和删除保护。
- 它不会自动让项目成员获得下载权限。

冻结方案：提供 Shot Grid 专用授权下载/预览接口，并为平台文件访问服务增加仅适用于 `businessType=shotgrid_version` 的受控业务授权扩展，不为每个项目成员批量复制 `sys_file_acl` 行。

授权顺序：

1. 验证登录和 `shotgrid:file:download`；
2. 验证 `fileId` 确实通过 `sg_version_file` 和 `sys_file_reference` 绑定目标版本；
3. 验证版本 → 任务 → 项目资源链；
4. 验证项目成员或明确的全项目数据范围；
5. 调用平台文件访问决策，显式 `deny` 仍然优先；
6. 复用底层流式下载、Range、审计和内容类型能力；
7. 使用净化后的 `business_file_name` 设置响应下载名。

必须满足：

- 成员移除或任务改派后权限立即按实时成员/任务关系收回；
- 不覆盖手工 deny ACL；
- 多项目共享文件权限正确；
- 支持 Range；
- 不泄露 `storageKey`；
- 查询使用版本、任务、成员和文件关系索引，不扫描无界数据；
- 能覆盖访问审计。

`sys_file_reference` 本身仍不授予下载权限；只有专用接口完整通过上述决策才允许访问。通用 `/common/files/...` 不因为 Shot Grid 业务引用自动放行项目成员。

审核参考内容遵循相同原则：草稿和正式问题分别使用独立业务引用类型；页面返回的 `downloadUrl` 必须指向上述 Shot Grid 专用接口，不得返回通用私有文件下载 URL 冒充业务授权。

NAS/SMB 直接访问不经过上述接口。部署必须使用 NAS、Windows/AD 或等价共享 ACL 单独控制；若部门共享对全部项目开放，应在上线安全评审中明确接受该平台外访问边界。

### 17.2 媒体处理

待确认：

- 缩略图工具；
- 视频代理和转码工具；
- 任务队列与 Worker；
- 生产媒体最大体积是否需要高于当前平台私有上传的 100 MiB；
- 失败重试；
- 产物保留与清理；
- 多 Worker 去重。

当前主产出物格式已经冻结并按真实字节探测：镜头为 MP4/MOV 容器签名/品牌，资产为 JPEG/PNG 签名；`mov` 已加入平台上传白名单。当前不探测 codec、视频轨、可解码性或执行转码；100 MiB 是平台上传基座限制，不代表媒体代理、转码或真实 NAS 大文件性能已验收。

媒体状态至少需要：

```text
pending
processing
ready
failed
```

是否使用独立媒体任务表在阶段 5 设计前决定。

## 18. 事务边界

必须处于单一数据库事务：

| 动作 | 同事务内容 |
| --- | --- |
| 创建项目 | 项目、总监成员、初始成员、按固定映射增量维护的 `sys_user_role`、仅对 Shot Grid 新建关系写入的 `sg_managed_user_role`、项目存储绑定、初始化目录 Outbox、含 `platformRoleChanges` 的操作日志 |
| 新增/恢复成员 | 锁定目标用户与项目，新增或恢复项目成员，按全部活动成员关系增量维护平台角色与来源标记，写含 `platformRoleChanges` 的操作日志 |
| 修改成员角色 | 锁定目标用户与项目，在未提交事务中更新项目角色，再按最新全部活动成员关系先补所需映射、后释放或保留旧映射，写含 `platformRoleChanges` 的操作日志 |
| 移除成员 | 锁定目标用户与项目，软移除成员，按全部活动成员关系仅撤回 Shot Grid 有来源且无依赖的映射，写含 `platformRoleChanges` 的操作日志 |
| 创建集或资产 | 业务实体；集按集契约创建目录 Outbox，资产包含未分配制作分项和稳定目录快照但不创建对象目录 Outbox；均不得创建任务 |
| 创建镜头 | 未分配镜头、场内连续 `shot_no`、镜头资产关系和操作审计；`storage_dir_name` 为空，不创建目录 Outbox 或任务 |
| 导入镜头 | 导入批次、集、场次、未分配且场内连续的镜头、已匹配资产关系、待匹配资产需求和操作审计；镜头目录 Outbox 与任务创建数均固定为 0 |
| 开始镜头任务 | 锁定项目/任务/镜头，冻结 `storage_dir_name`，任务进入 `preparing`，创建幂等目录 Outbox 并写操作审计；Worker 成功后单独回写 `in_progress` |
| 导入资产 | 导入批次、去重资产、逐行未分配制作分项、稳定目录快照、待匹配需求解析、镜头资产关系、操作审计；资产目录 Outbox 与任务创建数均固定为 0 |
| 确认资产分项开工 | 管理人员在项目/任务/父资产/分项锁内复核三版本及人工确认，只开始选中任务；创建或复用共享目录 Outbox，同事务审计，失败全回滚。目录未就绪进入 `preparing`，已成功则 `in_progress`；Worker 只推进已 `preparing` 分项 |
| 分配目标 | 锁定项目和目标；新建唯一任务，或携带任务锁版本受控改派现有任务；存在任何非 committed 提交时整体拒绝 |
| 暂存版本提交 | 锁定项目与任务、重查全部 open 问题、校验逐条处理说明覆盖、保留版本号、生成业务文件名和 NAS 目标、创建 `sg_version_submission` 与 `sg_version_issue_response`、建立 `shotgrid_version_submission` 临时文件引用 |
| 正式提交版本 | 版本、版本文件及 NAS 摘要、切换为 `shotgrid_version` 主文件引用、自动审核单、任务状态、提交状态；版本通过 `submission_id` 反向关联 |
| 保存/修改/删除问题草稿 | 当前待审核版本与活动自动审核单、草稿乐观锁、文字/标注至少一项门禁、操作审计；草稿不进入制作人问题查询 |
| 审核退回 | 带入问题逐条确认、草稿批量发布为正式问题并删除草稿、问题状态与解决版本、审核动作幂等记录/请求哈希/结果快照、版本状态、自动审核单状态、任务修改状态；全部同事务 |
| 审核通过 | 带入问题全部 `resolved` 且任务无 open 问题门禁、问题状态与解决版本、最终唯一性、审核动作幂等记录/请求哈希/结果快照、版本状态、自动审核单状态、任务完成状态、唯一最终交付 Outbox |
| 创建人工审核单 | 审核单、有序版本关系 |
| 修改业务附件 | 领域文件关系、平台业务引用 |

NAS I/O 不得在数据库事务内执行。`sg_storage_operation`、`sg_version_submission` 和 `sg_final_delivery` 负责跨资源编排：目录 Worker 已按“领取短事务 → 事务外路径校验/幂等建目录/写探针 → 结果短事务”实现；版本 Worker 已按“领取短事务 → 事务外唯一临时写入/真实摘要校验/无覆盖原子发布 → 正式版本或失败回写短事务”实现，并继续消费最终交付 Outbox，以硬链接或校验复制发布 `FINAL/` 文件和 `FINAL.json`。数据库事务失败时保留可校验的 NAS 文件并重试提交，不能重新分配版本号或盲目覆盖文件。目录 Worker 和版本 Worker 都默认关闭，真实 UNC E2E 是生产启用门禁。

平台权限缓存不属于数据库事务。项目创建在业务响应码 202、成员新增/恢复/改角/移除在业务成功码 200 后，由控制器统一清理 `ApiGroup.USER_PERMISSION_MUTATION`；失败响应和回滚事务不得清缓存。缓存失效不等于浏览器状态推送，目标用户已打开的 SPA 仍需刷新或重新登录。项目归档不调用平台角色同步，也不清理由角色变化触发的权限缓存。

目录 Worker 的软超时不会终止正在运行的 `asyncio.to_thread` 文件系统调用，只记录诊断并继续续租直至 I/O 退出；不得把该阈值描述为 SMB 硬超时。租约接管期间也不能宣称物理 I/O 绝不重叠，数据库 fencing 保证的是旧结果不能覆盖新终态。当前调度批内串行消费，不能描述为已经启用批内并发。

平台物理文件上传先于业务事务完成。创建版本暂存后必须以 `shotgrid_version_submission` 临时引用保护源文件；正式版本事务原子切换为 `shotgrid_version` 引用。若暂存事务尚未建立引用即失败，已上传但未引用的文件由平台保留、对账和回收流程处理，不能在异常处理中盲目永久删除。

## 19. 错误键

第一批稳定错误键。表中的 code 同时表示真实 HTTP 状态和响应体 `code`：

| errorKey | code | 场景 |
| --- | --- | --- |
| `SG_CURRENT_USER_INVALID` | 401 | 当前登录用户上下文缺少有效用户标识 |
| `SG_PROJECT_ID_INVALID` | 422 | 路径中的项目 ID 非法 |
| `SG_PROJECT_NOT_FOUND` | 404 | 项目不存在或不可见 |
| `SG_PROJECT_VERSIONED_METADATA_IMMUTABLE` | 409 | 项目已有正式版本，类型或画幅不能普通修改 |
| `SG_PROJECT_CODE_CONFLICT` | 409 | 项目编码重复 |
| `SG_PROJECT_CREATE_CONFLICT` | 409 | 并发创建项目发生不可重放冲突 |
| `SG_PROJECT_NOT_READY` | 409 | 项目 NAS 存储尚未就绪，禁止业务写入 |
| `SG_PROJECT_NOT_COMPLETABLE` | 409 | 仍有未完成镜头或资产制作分项，不能完成项目 |
| `SG_PROJECT_ACCESS_DENIED` | 403 | 非项目成员 |
| `SG_LAST_DIRECTOR_REQUIRED` | 409 | 尝试移除或降级最后一名项目管理人 |
| `SG_MEMBER_ALREADY_EXISTS` | 409 | 成员重复添加 |
| `SG_MEMBER_NOT_FOUND` | 404 | 项目成员不存在 |
| `SG_MEMBER_USER_INVALID` | 422 | 待添加用户不存在、已停用或不满足成员条件 |
| `SG_PLATFORM_ROLE_MISSING` | 503 | `shotgrid_admin` 或 `shotgrid_creator` 尚未配置 |
| `SG_PLATFORM_ROLE_DUPLICATE` | 503 | 固定角色键查询到多条平台角色，配置不唯一 |
| `SG_PLATFORM_ROLE_DISABLED` | 503 | 固定平台角色已停用或逻辑删除 |
| `SG_PLATFORM_ROLE_UNSAFE` | 503 | 固定角色复用超级管理员、缺少有效 `shotgrid:navigation:list`、含全局/非 Shot Grid/存储根写权限等不安全配置 |
| `SG_PLATFORM_ROLE_CONTRACT_PROTECTED` | 409 | 管理端尝试改名或删除固定平台角色键 |
| `SG_PROJECT_ROLE_BINDING_PROTECTED` | 409 | 管理端尝试移除活动成员所需或带来源标记的平台角色关系 |
| `SG_ACTIVE_PROJECT_MEMBER_USER_PROTECTED` | 409 | 管理端尝试删除仍有活动项目成员关系或来源标记的用户 |
| `SG_MEMBER_HAS_ACTIVE_TASKS` | 409 | 成员仍有活动任务 |
| `SG_PRODUCER_CODE_REQUIRED` | 422 | 被分配制作任务的成员缺少平台用户昵称（错误键为兼容保留） |
| `SG_PRODUCER_CODE_CONFLICT` | 409 | 历史兼容的项目制作人缩写重复 |
| `SG_EPISODE_NO_CONFLICT` | 409 | 项目内集号重复 |
| `SG_EPISODE_NOT_FOUND` | 404 | 集不存在、不属于目标项目或不可见 |
| `SG_EPISODE_HAS_ACTIVE_SCENES` | 409 | 集仍有活动场次，不能归档 |
| `SG_SHOT_TASK_ALREADY_STARTED` | 409 | 镜头任务已经开始，禁止单条或批量删除 |
| `SG_SHOT_EDIT_PRODUCTION_STARTED` | 409 | 镜头任务已经开始，禁止普通编辑制作字段 |
| `SG_STORAGE_ROOT_NOT_FOUND` | 404 | NAS 根目录配置不存在或不可见 |
| `SG_STORAGE_ROOT_DISABLED` | 409 | NAS 根目录已停用，不能创建新项目 |
| `SG_STORAGE_ROOT_UNAVAILABLE` | 503 | NAS 根目录不可达或不可写 |
| `SG_STORAGE_PATH_INVALID` | 422 | 路径片段非法、越界或使用保留名称 |
| `SG_STORAGE_PATH_CONFLICT` | 409 | 规范化 NAS 路径已被占用 |
| `SG_STORAGE_INITIALIZATION_FAILED` | 503 | 项目目录初始化失败 |
| `SG_STORAGE_OPERATION_NOT_FOUND` | 404 | 目录操作不存在、不属于目标项目或当前用户不可见 |
| `SG_STORAGE_OPERATION_NOT_RETRYABLE` | 409 | 当前目录操作状态不可重试 |
| `SG_SCENE_NO_CONFLICT` | 409 | 集内场次号重复 |
| `SG_SCENE_HAS_ACTIVE_SHOTS` | 409 | 场次仍有镜头 |
| `SG_SCENE_NOT_FOUND` | 404 | 场次不存在、不属于目标项目或不可见 |
| `SG_SCENE_PROLOGUE_INVALID` | 422 | 序场次与 `sceneNo=0/sceneName=序` 规则不一致 |
| `SG_SHOT_NO_CONFLICT` | 409 | 场内镜头号重复 |
| `SG_SHOT_NOT_FOUND` | 404 | 镜头不存在、不属于目标项目或不可见 |
| `SG_SHOT_SEQUENCE_POSITION_INVALID` | 409 | 场内镜头位置超出当前活动镜头范围，需刷新后重试 |
| `SG_SHOT_SEQUENCE_NOT_CONTIGUOUS` | 409 | 创建或导入后的场内镜序不能形成 `S001..Snnn` 连续集合 |
| `SG_SHOT_START_CONFIRMATION_REQUIRED` | 422 | 镜头开工未确认资产齐备或缺少镜头锁版本 |
| `SG_ASSET_START_CONFIRMATION_REQUIRED` | 422 | 资产分项开工未人工确认条件齐备或缺少资产/分项锁版本 |
| `SG_TASK_ASSIGNEE_INVALID` | 409 | 镜头或资产分项开工时当前负责人已不是有效制作人员，应重新分配 |
| `SG_SHOT_REORDER_PRODUCTION_STARTED` | 409 | 被移动区间内至少一个镜头已开始制作或已有版本/文件 |
| `SG_SHOT_DELETE_DIRECTORY_EXISTS` | 409 | 删除会让后续镜头前移，但受影响区间存在已冻结目录，禁止隐式改名 |
| `SG_SHOT_RENUMBER_EMPTY` | 409 | 目标场次没有可重编号的活动镜头 |
| `SG_SHOT_RENUMBER_LIMIT_EXCEEDED` | 409 | 单场活动镜头超过受控重编号上限 |
| `SG_SHOT_RENUMBER_HISTORY_EXISTS` | 409 | 兼容重编号动作遇到已开始任务、版本或文件 |
| `SG_SHOT_RENUMBER_DIRECTORY_NOT_READY` | 409 | 目标场次至少一个镜头目录尚未就绪 |
| `SG_SHOT_RENUMBER_TEMPORARY_NO_UNAVAILABLE` | 409 | 数据库无法分配安全的两阶段临时镜头号 |
| `SG_STORAGE_SOURCE_MISSING` | 409 | 受控目录迁移的源目录不存在或迁移状态不完整 |
| `SG_ASSET_NAME_REQUIRED` | 422 | 资产创建或导入时，名称规范化后为空或超长 |
| `SG_ASSET_NAME_CONFLICT` | 409 | 项目内同类型资产名称或目录冲突 |
| `SG_ASSET_NOT_FOUND` | 404 | 资产不存在、不属于目标项目或不可见 |
| `SG_ASSET_ITEM_NOT_FOUND` | 404 | 资产制作分项不存在、不属于目标项目或不可见 |
| `SG_ASSET_VERSIONED_METADATA_IMMUTABLE` | 409 | 资产制作分项已有版本，禁止普通修改其主数据 |
| `SG_ASSET_PRODUCTION_ITEM_INVALID` | 422 | 已填写的制作分项安全规范化后不可用 |
| `SG_ASSET_ITEM_PRODUCTION_STARTED` | 409 | 资产制作任务已经开始，禁止普通修改制作分项主数据 |
| `SG_ASSET_PRODUCTION_ITEM_CONFLICT` | 409 | 同一资产内非空制作分项名称重复 |
| `SG_ASSET_PRODUCTION_ITEM_REQUIRED` | 422 | 资产制作分项为空，禁止分配、改派、开始任务或提交版本 |
| `SG_TASK_ASSIGNEE_INVALID` | 422 | 普通创建任务时，制作人不是活动项目成员或平台账号已停用/删除 |
| `SG_TASK_ASSIGNEE_AMBIGUOUS` | 422 | 制作人字段包含多名候选，无法确定唯一主制作人 |
| `SG_TASK_ASSIGNEE_STATE_INVALID` | 409 | 已存在任务的当前负责人已被移除、停用或删除，版本提交前必须治理任务状态或改派 |
| `SG_TASK_NOT_FOUND` | 404 | 任务不存在、不属于可访问项目或不可见 |
| `SG_TASK_ACTION_DENIED` | 403 | 当前动作要求任务当前委派的活动 `creator` 本人执行，但当前用户不满足；`director`、管理员和全项目范围不构成代操作权限 |
| `SG_TASK_REASSIGN_SUBMISSION_CONFLICT` | 409 | 任务存在非 committed 版本提交（包括 failed），禁止改派 |
| `SG_CROSS_PROJECT_REFERENCE` | 409 | 跨项目关联 |
| `SG_RESOURCE_WRITE_CONFLICT` | 409 | 集、场次、镜头或资产写入遇到未归类的并发数据库约束冲突 |
| `SG_OPTIMISTIC_LOCK_CONFLICT` | 409 | 乐观锁冲突 |
| `SG_IDEMPOTENCY_KEY_INVALID` | 422 | 幂等键缺失、为空或超过长度限制 |
| `SG_IDEMPOTENCY_CONFLICT` | 409 | 同一幂等键绑定了不同规范化命令或选中行 |
| `SG_IMPORT_TOKEN_INVALID` | 400 | 导入 Token 不合法 |
| `SG_IMPORT_TOKEN_EXPIRED` | 410 | 导入 Token 过期 |
| `SG_IMPORT_TOKEN_CONFLICT` | 409 | Token 内容、哈希或持久化批次不一致 |
| `SG_IMPORT_TOKEN_FORBIDDEN` | 403 | 当前用户无权消费该预检 Token |
| `SG_IMPORT_HAS_ERRORS` | 422 | 选中行仍有错误 |
| `SG_IMPORT_BATCH_NOT_FOUND` | 404 | 导入批次不存在或不可见 |
| `SG_IMPORT_BATCH_STATE_CONFLICT` | 409 | 导入批次当前状态不可提交或重复消费 |
| `SG_IMPORT_FILE_HASH_MISMATCH` | 409 | Token 绑定的原文件摘要不一致 |
| `SG_IMPORT_FILE_TYPE_INVALID` | 422 | 上传文件不是允许的 `.xlsx` 类型 |
| `SG_IMPORT_FILE_NAME_INVALID` | 422 | 上传文件名为空或不符合安全限制 |
| `SG_IMPORT_FILE_EMPTY` | 422 | 上传文件为空 |
| `SG_IMPORT_FILE_TOO_LARGE` | 413 | 上传文件超过配置的大小上限 |
| `SG_IMPORT_FILE_INVALID` | 422 | 文件不是可解析的安全 XLSX 工作簿 |
| `SG_IMPORT_ARCHIVE_UNSAFE` | 422 | XLSX ZIP 条目、路径、压缩比或解压总量不安全 |
| `SG_IMPORT_WORKBOOK_TOO_COMPLEX` | 413 | OOXML 行、单元格、列、XML 元素、合并区域或总文本超过资源上限 |
| `SG_IMPORT_CELL_TEXT_TOO_LONG` | 422 | 单个 OOXML 单元格文本超过配置上限 |
| `SG_IMPORT_PREVIEW_TOO_LARGE` | 413 | Redis Token 载荷或 HTTP 预览 JSON 超过配置上限 |
| `SG_IMPORT_EXTERNAL_LINK_NOT_ALLOWED` | 422 | 工作簿包含外部链接 |
| `SG_IMPORT_WORKBOOK_EMPTY` | 422 | 工作簿没有可导入的可见业务 Sheet |
| `SG_IMPORT_SHEET_NAME_INVALID` | 422 | 镜头业务 Sheet 名不能解析为 `EPnnn` |
| `SG_IMPORT_EPISODE_DUPLICATE` | 422 | 多个 Sheet 规范化为同一集号 |
| `SG_IMPORT_TEMPLATE_INVALID` | 422 | 资产模板结构或合并区域不符合冻结规则 |
| `SG_IMPORT_TEMPLATE_VERSION_MISMATCH` | 409 | Token 或批次绑定的模板版本与当前实现不一致 |
| `SG_IMPORT_TEMPLATE_UNAVAILABLE` | 503 | 打包镜头模板缺失或 SHA-256 与冻结值不一致，拒绝返回未知内容 |
| `SG_IMPORT_HEADER_REQUIRED` | 422 | 缺少必需表头 |
| `SG_IMPORT_HEADER_INVALID` | 422 | 出现不允许的表头或表头结构 |
| `SG_IMPORT_HEADER_DUPLICATE` | 422 | 同一标准字段被多个表头重复映射 |
| `SG_IMPORT_HEADER_MISMATCH` | 422 | 镜头 A:O 固定表头顺序不匹配 |
| `SG_IMPORT_ROW_LIMIT_EXCEEDED` | 422 | 工作簿物理行或业务行超过配置上限 |
| `SG_IMPORT_SELECTED_ROW_INVALID` | 422 | 提交选择不存在、重复或不可导入的来源行 |
| `SG_IMPORT_PREVIEW_STORE_UNAVAILABLE` | 503 | Redis 预览存储当前不可用 |
| `SG_IMPORT_DATABASE_CONFLICT` | 409 | 预检后数据库状态变化导致正式提交冲突 |
| `SG_IMPORT_COMMIT_FAILED` | 500 | 正式提交事务失败且已回滚，响应只返回净化摘要 |
| `SG_ASSET_REQUIREMENT_NOT_FOUND` | 404 | 待匹配资产需求不存在或不可见 |
| `SG_ASSET_REQUIREMENT_CONFLICT` | 409 | 候选不唯一、类型不符或需求已被他人处理 |
| `SG_TASK_ALREADY_EXISTS` | 409 | 镜头或资产制作分项已经存在正式任务 |
| `SG_TASK_FILE_TYPE_INVALID` | 422 | 视频或图片任务上传了不允许的文件类型 |
| `SG_VERSION_FILE_ALREADY_BOUND` | 409 | 文件已经作为其他版本主产出物 |
| `SG_VERSION_SUBMISSION_ACTIVE` | 409 | 任务已有正在处理或待处理失败的提交 |
| `SG_VERSION_SUBMISSION_NOT_FOUND` | 404 | 版本提交不存在或不可见 |
| `SG_VERSION_SUBMISSION_FAILED` | 503 | NAS 发布失败，正式版本尚未创建 |
| `SG_VERSION_SUBMISSION_NOT_RETRYABLE` | 409 | 当前提交状态不可重试 |
| `SG_VERSION_SOURCE_FILE_UNAVAILABLE` | 503 | 平台源文件不存在或暂时不可读取 |
| `SG_VERSION_SOURCE_FILE_CHANGED` | 409 | 平台源文件的真实大小或 SHA-256 与暂存快照不一致 |
| `SG_VERSION_TARGET_PATH_CONFLICT` | 409 | 任务目录绑定不完整，或版本目标路径快照与当前稳定目录身份不一致 |
| `SG_VERSION_PUBLISH_LEASE_LOST` | 409 | 版本发布 owner + attempt 租约已经失效，迟到 Worker 不得回写 |
| `SG_NAS_TEMP_CONTENT_CONFLICT` | 409 | 当前 attempt 的唯一 NAS 临时文件名发生冲突 |
| `SG_NAS_TARGET_CONTENT_CONFLICT` | 409 | NAS 目标文件已存在但真实大小或摘要不一致，禁止覆盖 |
| `SG_VERSION_NUMBER_CONFLICT` | 409 | 并发版本号冲突 |
| `SG_VERSION_NOT_FOUND` | 404 | 正式版本不存在或不可见 |
| `SG_FINAL_VERSION_CONFLICT` | 409 | 已存在最终版本 |
| `SG_REVIEW_LIST_NOT_FOUND` | 404 | 自动单版本审核单不存在或不可见 |
| `SG_AUTO_REVIEW_LIST_INTEGRITY_CONFLICT` | 409 | 自动审核单与唯一版本关系不完整 |
| `SG_NOTE_NOT_FOUND` | 404 | 修改问题不存在或不可见（兼容错误键） |
| `SG_NOTE_MEDIA_TIME_INVALID` | 422 | 资产问题携带时间点，或视频时间点超过镜头时长（兼容错误键） |
| `SG_ISSUE_CONTENT_REQUIRED` | 422 | 修改问题的文字和画面标注同时为空 |
| `SG_REVIEW_ISSUE_DRAFT_NOT_FOUND` | 404 | 问题草稿不存在、已删除、已发布或不属于当前审核单 |
| `SG_REVIEW_DRAFTS_EXIST` | 409 | 当前审核单仍有未发布问题草稿，不能确认通过 |
| `SG_REVIEW_REFERENCE_FILE_LIMIT_EXCEEDED` | 400 | 单条问题引用超过 5 个参考文件 |
| `SG_REVIEW_REFERENCE_FILE_INVALID` | 400 | 参考文件不存在、已失效、不属于当前审核人或引用关系无效 |
| `SG_REVIEW_REFERENCE_FILE_TYPE_INVALID` | 400 | 参考文件扩展名不在业务白名单 |
| `SG_REVIEW_REFERENCE_FILE_TOO_LARGE` | 400 | 单个参考文件超过 20 MiB |
| `SG_ISSUE_RESPONSE_COVERAGE_INVALID` | 422 | 修订提交没有逐条覆盖全部 open 问题，或包含重复、已关闭、跨任务问题 |
| `SG_ISSUE_SNAPSHOT_CONFLICT` | 409 | preflight 后 open 问题集合变化，必须重新确认逐条处理说明 |
| `SG_ISSUE_VERIFICATION_COVERAGE_INVALID` | 422 | 审核动作没有逐条确认全部带入问题，或确认项重复、越界 |
| `SG_ISSUE_VERIFICATION_COMMENT_REQUIRED` | 422 | 问题确认选择 `still_present` 但未填写具体未解决原因 |
| `SG_REVIEW_OPEN_ISSUES_EXIST` | 409 | 仍有 open 修改问题，不能确认通过 |
| `SG_REVIEW_REJECT_ISSUE_REQUIRED` | 422 | 退回修改时不存在 `still_present` 历史问题或当前版本新问题 |
| `SG_INVALID_STATE_TRANSITION` | 409 | 非法状态流转 |
| `SG_FILE_ACCESS_DENIED` | 403 | 项目、任务或平台文件访问决策拒绝下载 |

前端根据 `errorKey` 选择交互文案，`msg` 用于兜底，不通过中文字符串比较业务分支。

### 19.1 预检 issue 键

预检接口成功解析工作簿时返回真实 HTTP 200。下列键位于工作簿或 `rows[].errors[]/warnings[]` 中，不是顶层 HTTP `code`；错误行不能正式提交，警告行可按规则提交。

| issueKey | severity | 载体 | 场景 |
| --- | --- | --- | --- |
| `SG_ASSET_NAME_REQUIRED` | error | 行 | 资产名称缺失 |
| `SG_ASSET_TYPE_INVALID` | error | 行 | 资产类型不是允许的三种类型 |
| `SG_IMPORT_DURATION_INVALID` | error | 行 | 镜头时长不能精确解析 |
| `SG_IMPORT_FIELD_TOO_LONG` | error | 行 | 单元格规范化后超过字段上限 |
| `SG_IMPORT_FORMULA_NOT_ALLOWED` | error | 行 | 可写业务列包含公式 |
| `SG_IMPORT_REQUIRED_FIELD_MISSING` | error | 行 | 镜头必填字段缺失 |
| `SG_IMPORT_SCENE_INVALID` | error | 行 | 场次文本不能规范化 |
| `SG_IMPORT_SHOT_NO_INVALID` | error | 行 | 镜头号不能规范化 |
| `SG_TASK_ASSIGNEE_INVALID` | error | 行 | 制作人不能唯一匹配为有效活动成员 |
| `SG_ASSET_PRODUCTION_ITEM_MISSING` | warning | 行 | 资产制作分项缺失，允许后续补充 |
| `SG_IMPORT_HIDDEN_SHEETS_IGNORED` | warning | 工作簿 | 隐藏辅助 Sheet 已忽略 |
| `SG_IMPORT_READONLY_COLUMNS_IGNORED` | warning | 工作簿 | 状态等只读列已忽略，不参与写入 |

## 20. 第一批验收用例

目录 Worker 与版本发布 Worker 本批均提供了 DAO、路径适配器、租约/心跳/重试服务、内部 Scheduler 任务和针对性测试入口；目录链另有管理 API。当前后端 Ruff check 通过，Ruff format `--check` 报告 161 files already formatted；完整 `tests/module_shot_grid` 为 499 passed、2 skipped，两个跳过项均因当前 Windows 环境不允许创建目录符号链接，preflight 相关 3 个定向测试文件为 43 passed。项目选项/成员候选、镜头/资产制作人选项和镜头模板路由已由 OpenAPI/路由测试确认。独立业务前端 lint、32 文件/148 单测和生产构建通过，构建处理 1796 个模块，仅保留既有 `@vueuse/core` PURE annotation 两条警告；测试覆盖任务工作台/详情、三步版本提交、current 恢复、轮询停止与重试、历史/详情/下载、权限双门禁、内存幂等重放、迟到结果/ABA 隔离和 Blob 错误保真。生产前端形态下，项目管理和任务工作台/版本上传子集已有隔离 PostgreSQL、Redis DB 15、真实 FastAPI/平台账号和 Chrome 旅程；2026-08-11 的镜头/资产旅程基于已废止的 v1 导入预分配规则，不能验收 v2“模板无制作人、导入后未分配且不建任务”的契约。任务/版本子集的 `published → committed` 使用显式 `allow_local_root=True` 的本地 TEMP 适配器，只证明两阶段发布算法与业务编排；自动化本地文件系统和逻辑目录夹具都不能证明真实 Windows/NAS 服务账号、UNC/SMB 或共享 ACL。静态门禁和当前子集证据不能替代两类 v2 模板/导入、首次委派唯一性、六阶段生产履历、完整系统 E2E、真实 UNC 版本发布、资产缩略图或真实 NAS 门禁。

### 20.0 已完成的项目管理子集旅程

验证环境使用当前 PostgreSQL 初始化基线创建的隔离数据库，Alembic head 为 `20260811_06`；Redis 使用隔离 DB 15；浏览器通过生产 Nginx 和真实平台管理员账号访问真实 FastAPI 后端。已走通：

```text
登录与六项导航
→ 健康根目录选项、路径预览
→ POST 创建项目，HTTP 202
→ 项目详情、真实概览与详情深链刷新
→ PUT 编辑项目，HTTP 200
→ 项目成员候选
→ POST 添加、PUT 修改、DELETE 软移除成员，均 HTTP 200
→ 存储操作详情
→ POST 归档，HTTP 200，并在归档列表回查
→ POST 退出，HTTP 200
→ 退出后访问详情深链，返回带 redirect 的登录页
```

数据库终态确认项目为 `archived`、`lockVersion=2`，管理员成员仍为 `active`，测试制作人员已软移除且最后缩写为 `NG2`；项目存储为 `initializing`，`initialize_project` 操作为 `pending`；项目与成员写入留下 6 条同事务审计。退出后 Redis 中 `access_token:*` 为 0。

测试根 `\\127.0.0.1\shot-grid-e2e` 只是隔离数据库中的逻辑 `healthy` 夹具，目录 Worker 明确关闭。该旅程没有连接真实 SMB 共享、没有以正式 Windows/NAS 服务账号执行目录创建，也没有验证 NAS/AD/共享 ACL、写探针、失败重试或 Leader 接管。因此它只能称为“项目管理子集浏览器旅程”，不能称为完整系统 E2E、真实 NAS E2E 或生产就绪。

### 20.0.1 历史 v1 镜头导入旅程（已被 v2 契约失效）

验证环境使用隔离 PostgreSQL、Redis DB 15、真实 FastAPI/平台账号、生产 Nginx 和 Chrome，并运行最终 `operationGeneration` 版本。已走通：

```text
下载旧 `shot-v1` 模板 11883 bytes，SHA-256 命中 F6370BBB...D96EE0
→ preview UI 为 24/24、warningRows=0、errorRows=0、2 集/8 场/24 镜头
→ EP001、EP002 各 12 行，选中全部 24 行
→ commit HTTP 200，首次结果 idempotentReplay=false
→ 按已经废弃的导入预分配规则创建 2 集、8 场、24 镜头、24 任务、24 待匹配需求和 26 条目录操作
→ 表格、卡片、故事板各显示 24 条；EP002 筛选显示 12 条
→ 场次筛选包含 000/001/002/003
→ 详情深链及刷新显示 EP002/000/S001 与“晓亮/XL”任务
→ 浏览器控制台 0 error/0 warning
→ 退出后访问详情深链，返回带 redirect 的登录页
```

commit 结果中的复用集/场均为 0、资产关系为 0。数据库终态确认 2 集、8 场、24 镜头、24 任务（三名制作人各 8）、24 待匹配需求、0 镜头资产关系、1 个 `committed` 导入批次、镜头时长合计 79000 ms；2 条集目录操作和 24 条镜头目录操作均为 `pending`。同事务审计恰 1 条且 `status=0`，`method` 字符串长度 79，未超过字段上限。Redis 预检键在提交后为 0。

该旅程只能证明旧 v1 实现曾经按当时契约运行；其中“模板含制作人、导入创建 24 个任务”的行为已被 v2 明确禁止，不能作为当前验收证据。当前必须重新验证 `shot-v2` 下载与摘要、15 列预检、24 个镜头未分配、任务创建数为 0，以及随后独立委派创建唯一任务。原旅程没有验证真实 UNC/NAS、Windows 服务账号、共享 ACL、写探针或故障恢复，也不是完整系统 E2E。

### 20.0.2 历史 v1 资产导入旅程（已被 v2 契约失效）

验证环境使用隔离 PostgreSQL、Redis DB 15、真实 FastAPI/平台账号、最终生产构建、生产 Nginx 和 Chrome；项目为逻辑 `storageStatus=ready` 夹具，目录 Worker 保持关闭。实际走通：

```text
登录并进入资产一级页
→ 上传旧 v1 资产样表
→ preview UI 为 total=20、valid=19、warningRows=3、errorRows=1
→ 按已经废弃的制作人预分配规则选中 19 行并提交
→ 创建 11 个活动资产、19 个制作分项、19 个任务和 1 个自动匹配
→ 表格、卡片、类型看板同源；Environment 筛选为 2，蒋浩筛选为 8
→ 创建临时 assetId=12/assetItemId=20，编辑父资产与分项，依次归档分项和父资产
→ taskId=3 从 userId=880103、lockVersion=0 改派到 userId=880102、lockVersion=1
→ 详情深链 /projects/880001/assets/2 与 reload 成功
→ 浏览器控制台 0 error/0 warning
→ 退出后访问详情深链，重定向到 /login?redirect=/projects/880001/assets/2
```

数据库终态为 11 个活动资产、19 个活动制作分项和 19 个任务；类型分布 Character 5、Environment 2、Prop 4。临时资产和分项最终均为 `archived/lockVersion=2`，临时分项 `taskCount=0`，因此活动数量保持 11/19/19。任务最终分布为蒋浩 8、嘉璋 3、占峰 8。自动匹配 1 条来自显式隔离资产需求夹具，不是镜头样表自然生成的需求。

`sys_oper_log` 共 7 条且全部成功，分别覆盖导入、资产创建/编辑、制作分项编辑/归档、父资产归档和任务改派。12 条 `ensure_asset_directory` Outbox 全部为 `pending`，符合 Worker 关闭预期。localStorage 为空，sessionStorage 仅有前端传输配置和 repeat-submit 元数据，不含认证、导入 Token 或幂等密钥；退出后 Redis `access_token:*` 为 0。

本旅程只能证明旧 v1 实现曾经按当时契约运行；其中“模板含制作人、复合制作人导致错误、导入创建 19 个任务”的行为已被 v2 明确禁止，不能作为当前验收证据。当前必须重新验证 `asset-v2` 下载与摘要、6 列预检、全部制作分项未分配、任务创建数为 0，以及随后独立委派创建唯一任务。原旅程只验证真实缩略图空态，逻辑 ready、Worker 关闭和 12 条 pending Outbox 也不证明真实 UNC/NAS I/O。

验收后已关闭 Playwright，停止后端 PID 29056/32996，删除唯一临时 Nginx 容器；复用的 `nginx:1.27-alpine` 镜像未由本批构建且保留。18081/19099 端口空闲，隔离 PostgreSQL 库存在数/连接数为 0/0，Redis DB 15 `DBSIZE=0` 且 owner 键为 0，54 项 TEMP 精确删除，backend `.venv` 不存在。原 9099 PID 4820 仍监听，基础 PostgreSQL/Redis 均为 healthy，无 E2E Git 残留。

### 20.0.3 已完成的任务工作台与版本上传子集旅程

验证环境使用 fresh PostgreSQL（Alembic head `20260811_06`、22 张 Shot Grid 表）、隔离 Redis DB 15、真实 FastAPI/平台账号登录、生产前端代理和 Chrome。版本物理发布显式使用 `allow_local_root=True` 的本地 TEMP 适配器；为版本目标补齐的目录只属于隔离夹具和逻辑路径预览，不是 NAS 目录创建证据。

实际走通：

```text
真实平台登录
→ /workbench 返回 21 条本人任务，分页 20 + 1，keyword 服务端过滤为 1 条
→ taskId=900001 开始任务 HTTP 200，lockVersion 0 → 1
→ 选择 logo.png（5663 bytes）
→ preflight HTTP 200
→ /common/files/upload 私有上传 HTTP 200
→ create HTTP 202，网络顺序确认无提前上传/创建
→ pending 状态刷新页面，current HTTP 200 恢复同一提交
→ 本地 TEMP 适配器两阶段发布 published → committed，attempt=1
→ 形成 V001/pending_review，任务 lockVersion=2、auto_single 审核单 1、正式文件引用 1
→ 版本详情与受保护下载 HTTP 200，下载 5663 bytes 且 SHA-256 与上传源一致
→ 控制台 0 error/0 warning；localStorage/sessionStorage 无认证 Token/fileId/幂等键/修改说明/AI 参数
→ 登录期间认证 Token 只存在 Admin-Token Cookie，logout HTTP 200 后 Cookie 清除，任务与版本深链均受登录守卫保护
```

隔离数据库、Redis DB 15、本地 TEMP 适配器目录及本批临时运行资源均已按清单精确清理。该结果可命名为“任务工作台与版本上传隔离子集 E2E PASS”，但本地 `allow_local_root` 只验证路径适配、文件摘要和两阶段发布算法，不是真实 Windows/NAS 服务账号、UNC/SMB 或共享 ACL 验收。审核前端、`manual_batch`、codec/媒体轨/可解码性/转码、媒体派生和完整系统 E2E 仍未验证。

### 20.1 正向闭环

```text
真实 RuoYi 登录
→ GET /getInfo
→ GET /shot-grid/navigation，只返回六项业务导航
→ 选择受控 NAS 根目录并预览项目路径
→ 创建项目，项目、总监成员、存储绑定和初始化 Outbox 同时入库
→ Worker 真实创建项目目录，项目存储变为 ready
→ 添加制作人员
→ 预检查并提交镜头 Excel，按去重键创建集、场次、镜头和资产待匹配需求
→ 预检查并提交资产 Excel，创建三类资产并自动解析唯一待匹配需求
→ 人工处理剩余冲突，镜头 001 关联场景和角色资产，NAS 目录为 EP01\S001
→ 分配杨景锋，创建唯一视频任务
→ 项目管理人线下确认资产齐备，在镜头管理确认开工
→ 等待目录就绪进入制作中，制作人员在线下完成视频
→ 上传 MP4，创建版本提交暂存，发布到 NAS
→ 发布成功后自动生成 V001、规范业务文件名和单版本审核单
→ 项目管理人退回并提交审核意见
→ 制作人员上传修改视频，自动生成 V002 和新审核单
→ 项目管理人确认通过，V002 成为最终版本且任务完成
→ 刷新后数据、文件、版本、审核意见和权限保持正确
```

### 20.2 必须覆盖的负向用例

- 未登录不能访问任何 `/shot-grid` 业务接口。
- 没有平台权限时返回无接口权限。
- 有平台权限但不是项目成员时不能读取项目资源。
- 制作人员不能管理项目成员。
- 不能创建没有项目管理人的项目。
- 不能移除最后一名项目管理人。
- 项目创建和成员新增/恢复、改角、移除的前端网络记录中不能出现任何 `/system/*` 请求，写请求只提交 `projectRole` 而不提交平台角色 ID、角色键或菜单 ID。
- 两条 role-options API 只在固定角色唯一、启用、未删除、至少含有效 `shotgrid:navigation:list` 且不含超级权限、跨项目范围、非 Shot Grid 权限或存储根写权限时返回完整两项；任一异常以对应稳定 503 失败关闭。
- 平台已有但无 `sg_managed_user_role` 来源标记的角色关系不得被 Shot Grid 撤回；同一角色仍被其他活动项目成员关系依赖时也不得撤回。
- 成员从 `creator` 改为 `director` 时，在同一事务内更新成员后先补齐 `shotgrid_admin`，再仅在满足来源和零依赖条件时撤回 `shotgrid_creator`；任一步失败，项目成员、平台角色、来源标记和审计全部回滚。
- 项目归档不触发受管平台角色同步；归档项目中的活动成员继续计入历史只读依赖。
- 成功写入后平台权限缓存命名空间被清理，但目标用户已打开的 SPA 不会自动更新；刷新或重新登录后才能以新 `/getInfo` 和 `/shot-grid/navigation` 结果验收导航与按钮。
- 项目编码大小写变体不能重复。
- 禁用、不可达或不可写的 NAS 根目录不能创建可用项目。
- 项目目录初始化失败时项目不能进入正常业务页面，重试不得重复创建项目或目录。
- 路径片段包含越界、Windows 保留名或非法字符时必须被拒绝。
- 路径链中存在符号链接或 Windows reparse point 时必须被拒绝，即使最终解析结果仍在根目录内。
- 项目初始化最终失败才允许把项目存储改为 `failed`；集、镜头或资产目录失败不能把已就绪的项目根存储降级为失败。
- 人工重试必须保留原失败操作并新建 `reconcile_directory`；同一幂等命令重放不能创建第二条操作，同键不同原因或 `lockVersion` 必须返回冲突。
- Worker 默认关闭，非 PostgreSQL、非 Leader 或开关未启用时不得消费目录操作；Leader 失锁后不能继续领取新操作。
- 同一项目内集号不能重复。
- 同一集内场次号不能重复。
- 同一场次内镜头号不能重复；不同场次可以分别从 `S001` 开始。
- 单场拖拽成功后必须自动保证“第 N 镜 = S{N:03d}”；被移动区间任一镜头已开始制作或已有版本/文件时整体拒绝。无目录镜头在事务内直接改号；历史冻结目录只在 NAS 迁移成功后原子切换数据库编号。
- 单条或批量删除成功后必须自动保证剩余镜头仍为 `S001..Snnn`；从最早删除位置到场尾任一镜头已开始制作、已有版本/文件或冻结目录时整体拒绝，数据库和目录都不得出现半完成状态。
- 不能将其他项目的场次或资产关联到当前镜头。
- 相同 `lockVersion` 并发修改时只有一个成功。
- 同一镜头或资产制作分项不能创建第二个正式任务。
- 资产制作分项允许缺失名称并以未分配草稿导入，预检查产生警告；名称缺失时可后续编辑，但不能分配、改派、开始任务或提交图片版本。
- 显式委派每次只允许选择一名主制作人；多选或复合负责人输入必须拒绝，不能静默选取第一人。
- 镜头及资产分项开工必须拒绝制作人、缺少管理范围/权限、未人工确认、双/三版本过期、失效负责人或不合法状态请求；同分项并发只能成功一次，不同分项共用一个目录操作，未开工分项不能被 Worker 带动。版本 preflight/create 和失败提交重试必须拒绝非当前受派活动制作人，管理员不得代操作。
- 视频任务不能提交图片，图片任务不能提交视频。
- 同一任务存在活动或失败待处理提交时不能创建第二个提交。
- NAS 发布失败时不能生成正式版本、审核单或把任务改为待审核。
- NAS 目标文件摘要冲突时不能覆盖原文件。
- 正式版本事务失败时不能留下半成品版本或审核单，并必须复用原保留版本号重试。
- 业务文件名必须使用保存的项目缩写、主制作人的平台用户昵称、服务端版本号和时间戳；资产文件名还必须使用制作分项中保存的名称；镜头与资产文件名都包含对应版本号，重试时所有已生成值不得变化。
- 资产主产出物文件名各段顺序必须为“项目、`Asset`、类型、资产名称、制作分项、制作人、版本、时间戳”，示例必须生成 `WGZR_Asset_Environment_动力舱室内_动力舱恐怖气氛主视角_YJF_V001_1786094626499.jpg`。
- 导入预览不能随机生成缺失镜头号。
- 导入预览后数据库被其他用户修改时，提交必须重新检查冲突。
- 镜头导入引用尚不存在的资产时只能生成待匹配需求，不能生成正式资产或资产任务。
- 资产导入只能自动匹配项目内同类型、同规范化名称的唯一候选，冲突必须进入人工处理。
- 导入批次任一选中行失败时，不能留下半成功集、场次、镜头、资产、任务、关系或目录操作。
- 隐藏 Sheet、伪造超大行列坐标、超量合并区域、共享字符串重复引用和超大预览 JSON 必须在 `openpyxl` 建立对象、Redis 写入或数据库提交之前被对应资源门禁拒绝。
- 重复幂等键不能重复创建项目、导入镜头、导入资产、待匹配需求或镜头资产关系。
- 原资产工作簿重新保存、移动行或更改 Sheet 后再次导入时，未命名制作分项不能被静默复制；该用例在稳定 `rowUid` 或人工去重治理落地前标记为未关闭门禁。

## 21. 评审后仍需关闭的部署与产品参数

完成本文评审后，按顺序继续：

1. 确认是否在 `ASSET`、`VIDEO` 之外增加 `DOC`、`AUDIO`、`DELIVERY`、`EXCHANGE`，并冻结各目录写入规则。
2. 冻结最大图片/视频大小、视频编码、分辨率、时长和超时参数。
3. 选择缩略图和视频代理 Worker 工具链；平台不承担正式图片或视频制作。
4. 确认公司是否存在统一 UNC 桌面协议处理器；未确认前只提供查看和复制路径。
5. 冻结 NAS/AD/Windows 共享 ACL 部署方案，明确网页权限之外的直接 SMB 访问边界。
6. 决定已完成任务是否需要“重新打开”；MVP 当前禁止，未来动作必须有原因和审计。
7. 两类样表、模板版本、默认最大行数、文件大小、预览 TTL 和资产名称规范化已冻结；当前服务只下载 `shot-v2.xlsx` 与 `asset-v2.xlsx`，冻结 SHA-256 分别为 `B6F24078CA56295E9E6CCE50BB3455AF198DFFFE5C08F8D85605A68C09439ECE`、`B551AC1D1D5EDC20A025B0ED90157412E1365006108816F08CB2C59AE4301696`，两类模板均不含制作人。旧 v1 文件只保留为历史资源。上传原文件仅临时解析、不长期留存，确需留存时必须另走受保护文件引用。
8. 决定资产模板是否增加跨重新保存仍保留的稳定 `sourceRowId/rowUid`；未引入前需冻结人工去重治理流程。
9. 基础表、`20260810_01 → 20260814_10` 迁移链、种子、项目/成员/集/场次/镜头/资产/制作分项普通管理、两类导入、资产需求、独立任务、版本发布、跨版本修改问题闭环、人工批量审核，以及默认关闭的 NAS 目录和媒体派生 Worker 已转化为代码；独立业务前端也已实现制作人逐条处理说明、审核人逐条确认、审核缩略图、网页代理优先和原媒体降级。导入后未分配、首次委派创建唯一任务和六阶段生产履历已进入本轮重构，但既有 v1 浏览器旅程不能作为这些新规则的验收证据；真实 FFmpeg 视频派生、Range 真分段、审核/文件浏览器旅程、UNC/NAS 部署验收和完整系统 E2E 继续按本契约分批验收。

上述 1—8 是评审、部署或数据治理参数，不得由页面开发临时猜测。第 9 项只说明当前第一批实现边界，未落地的契约章节仍是设计，不是已实现能力。
