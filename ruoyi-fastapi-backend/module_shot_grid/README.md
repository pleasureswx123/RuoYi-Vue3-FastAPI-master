# Shot Grid 后端模块

## 当前边界

本模块是 Shot Grid 业务后端的 PostgreSQL 领域模块。当前已交付：

- 25 张 `sg_` 领域表对应的 SQLAlchemy DO；
- 项目成员范围与项目角色权限依赖；
- 受平台角色菜单授权约束的 `GET /shot-grid/navigation`；
- 项目范围列表、详情、真实概览聚合、创建项目事务、存储初始化状态与项目成员管理；
- 项目编辑/归档，以及集、场次、镜头、资产和资产制作分项的查询、创建、修改与业务归档；
- 项目内镜头/资产制作人安全选项、镜头导入模板的鉴权二进制下载，以及完成/归档项目下集、场次、镜头、资产、资产制作分项和两类 Excel 导入写门禁；
- 项目任务分页、跨项目“我的任务”、任务详情/编辑、镜头或资产制作分项首次分配/受控改派，以及负责人开始任务；
- 镜头和资产 `.xlsx` 的安全预检、Redis 短期 Token、选中行全事务提交和 PostgreSQL 耐久幂等结果；
- 平台私有文件上传后的版本暂存、临时业务引用、默认关闭的 NAS 版本发布 Worker、正式版本/主文件引用/`auto_single` 审核单事务，以及版本文件专用授权下载；
- 任务版本、自动单版本审核单、跨版本修改问题、制作人逐条处理说明、审核人逐条确认、审核动作历史和 `approve/reject/defer` 状态闭环；
- 由 Application Leader 调度的 NAS 目录 Outbox Worker，包含数据库租约领取、心跳续租、退避重试、路径快照复核、幂等建目录和写权限探针；
- 项目目录初始化、集/镜头/资产动态目录确保，以及项目/动态目录操作的分页诊断、详情和人工对账重试 API；
- PostgreSQL Alembic 迁移链、初始化 SQL、菜单、权限按钮和字典种子；
- 元数据、导航、项目权限、项目事务、两类真实样表解析、任务/版本/审核、目录状态/DAO/路径适配器/Worker/路由和内部 Scheduler 任务的针对性测试入口。

当前批次仍不包含资产 Excel 模板下载、资产需求人工处理、`manual_batch` 人工批量审核单、媒体缩略图生成/代理/转码/元数据、完整审核前端和完整系统 E2E；镜头模板下载已经交付，两类预检按仓库内冻结样表执行。独立业务前端已接入镜头和资产的真实列表多视图、详情、CRUD、任务分配及 Excel 预检/提交，并已接入跨项目“我的任务”工作台、任务详情/开始/编辑、三步版本提交、刷新恢复、历史/详情和受保护下载。项目、镜头、资产和任务/版本四个子集已完成隔离 PostgreSQL、Redis DB 15、真实平台账号、生产 Nginx 与 Chrome 浏览器旅程；任务/版本旅程以显式 `allow_local_root=True` 的 TEMP 适配器验证发布算法和编排，不是真实 UNC/SMB/NAS 服务账号验收。平台私有上传当前单文件上限仍为 100 MiB，`mov` 已加入上传白名单；版本服务按真实字节校验 JPEG/PNG 与 MP4/MOV 容器签名/品牌，但尚未探测 codec、视频轨、可解码性或执行转码。已交付接口通过平台权限、项目角色、资源归属、项目/任务/版本行锁、乐观锁、业务归档、文件引用和同事务审计约束，不能使用通用代码生成 CRUD 绕过状态机。任何子集旅程都不是完整系统 E2E 或生产就绪证明。

资产类型、名称和完整目录身份在创建时一并冻结，普通 PUT 只修改描述、排序和备注；该 PUT 是三项非身份主数据的完整快照，省略描述或备注表示清空，省略排序表示归零。任何重命名、改类型或目录迁移都必须另建受控动作。制作分项在尚无版本时可补充或纠正主数据，已有正式版本后全部冻结；缺失制作分项只能作为未分配草稿保存或导入，首次分配、改派、批量分配、导入分配、开始任务和资产图片版本提交均失败关闭。镜头号、集号和场次号也不提供普通改号。正式版本事务按 `project → task/submission → version → auto_single review list → note` 锁序执行，避免项目元数据、改派、提交和审核并发穿透。

NAS 目录 Worker 和版本发布 Worker 的代码路径已经建立，但所有环境样例分别以 `SHOT_GRID_STORAGE_WORKER_ENABLED=false`、`SHOT_GRID_VERSION_WORKER_ENABLED=false` 默认关闭。本批次使用临时本地目录验证路径适配器时必须显式注入 `allow_local_root=True`；生产适配器默认只接受 Windows UNC。尚未使用真实 NAS、正式 Windows Worker 服务账号和 NAS/AD/共享 ACL 完成隔离 UNC E2E，因此不得把本批交付描述成 NAS 生产验收通过；源码、Mock、迁移、Scheduler 注册或本地临时目录测试也不能替代该门禁。

## 项目角色与受管平台角色

```http
GET /shot-grid/project-role-options
GET /shot-grid/projects/{projectId}/role-options
POST /shot-grid/platform-role-bindings/reconcile
```

- 固定映射为 `director -> shotgrid_admin`、`creator -> shotgrid_creator`。创建项目以及成员新增/恢复、改角、移除在同一数据库事务中按目标用户全部活动项目成员关系增量同步 `sys_user_role`；归档不触发同步，归档项目中的活动成员继续计入历史只读依赖。
- `sg_managed_user_role` 使用 `(user_id, role_id)` 复合主键和指向 `sys_user_role` 的复合外键 `ON DELETE CASCADE`，仅保存 `create_by/create_time`。只有 Shot Grid 新建的平台角色关系才写来源标记；已有无标记关系只复用且永不由 Shot Grid 撤回。
- 两个角色选项接口返回 `projectRole/projectRoleLabel/systemRoleId/systemRoleKey/systemRoleName`；前端写请求仍只提交 `projectRole`，不得调用 `/system/*`。固定角色缺失、重复、停用/删除或权限包不安全时以稳定 503 失败关闭。
- 受管角色至少包含启用的 `shotgrid:navigation:list` 和一个启用的 Shot Grid 业务导航权限，且不得复用超级管理员、包含 `*:*:*`、`shotgrid:project:all`、任何非 `shotgrid:` 权限或存储根写权限。迁移 `20260818_12` 只建立来源表，不自动创建或猜测平台角色包。
- 领域审计记录 `platformRoleChanges` 的 `grantedRoleKeys/revokedRoleKeys/requiredPreservedRoleKeys/externalPreservedRoleKeys`。成功提交后控制器清理 `ApiGroup.USER_PERMISSION_MUTATION`；目标用户已打开的 SPA 仍需刷新或重新登录，成功响应不包含跨会话刷新标志。
- 通用管理端不能改名或删除两个固定角色键，不能把启用角色菜单包修改为不安全集合，也不能从通用用户角色入口移除活动成员所需或 Shot Grid 受管关系。停用固定角色是允许的紧急撤权动作，重新启用前必须通过完整权限包校验。
- 迁移不猜测存量关系。先升级到 `20260818_12`、再上线新代码；固定角色配置后，由同时拥有 `shotgrid:project:all` 和 `system:user:edit` 的管理员调用对账接口。对账使用同一来源与增量撤权规则，仅返回汇总计数；`downgrade` 会先精确删除来源表所有的 `sys_user_role`，再删来源表。

## 镜头与资产页面查询、模板与终态门禁

```http
GET /shot-grid/projects/{projectId}/shot-assignee-options
GET /shot-grid/projects/{projectId}/asset-assignee-options
GET /shot-grid/imports/shots/template
```

- `GET /shot-grid/projects/{projectId}/members` 支持可选 `projectRole=director|creator`；传入时按项目角色过滤，不传时返回全部活动项目成员。
- `shot-assignee-options` 要求登录、`shotgrid:shot:list` 和项目访问，使用 `pageNum/pageSize/keyword` 分页；只返回 `projectRole=creator` 的活动项目成员及有效未删除平台账号的 `userId/userName/nickName/avatar/deptId/deptName/projectRole/producerCode` 安全投影。兼容字段 `producerCode` 由 `sys_user.nick_name` 派生，关键字只匹配账号与昵称；镜头导入、真正创建、编辑或改派时仍由写事务重新校验成员状态和项目角色。
- `asset-assignee-options` 要求登录、`shotgrid:asset:list` 和项目访问，分页、关键字及安全投影与镜头选项一致；真正创建/编辑资产或制作分项、导入、首次分配或改派时仍由写事务重新校验项目状态、成员状态和平台用户昵称。
- 模板下载要求 `shotgrid:shot:import`，返回 XLSX 二进制、附件文件名 `镜头导入模板-shot-v1.xlsx` 和 `X-Shot-Grid-Template-Version: shot-v1`，不套统一 JSON envelope。应用层传输加密只精确放行这一条 GET；同前缀预检和提交 JSON 仍保持原加密策略。部署文件缺失或摘要不一致时返回 HTTP 503 / `SG_IMPORT_TEMPLATE_UNAVAILABLE`。
- 打包资源 `resources/templates/shot-v1.xlsx` 的冻结 SHA-256 为 `F6370BBB14548B645782ABF0734E930EC10470565821BA6C8FD1B6A2D9D96EE0`。匿名部署副本只改动 5 个 XML：`xl/workbook.xml` 删除 `x15ac:absPath`；`xl/sharedStrings.xml` 的 88 条共享字符串全部替换为只含表头、合法编号、制作人 A-C 和示例文本的匿名内容；`docProps/core.xml`、`docProps/app.xml` 匿名化作者/应用属性；`docProps/custom.xml` 清空自定义属性。其余 13 个 OOXML 条目（含两个 Sheet、styles、theme）与原样表字节一致；解析结果仍为 total 24、valid 24、warning 0、error 0、2 集、8 场、24 镜头。安全测试会拒绝驱动器路径、`file:` URI、UNC、个人/组织或应用元数据重新进入模板。
- 集、场次、镜头、资产和资产制作分项的创建、修改、归档在锁内读取项目状态；镜头和资产导入 preview 普通读取状态并拒绝，commit 再以 `FOR UPDATE` 锁定项目重检。`completed` 或 `archived` 均返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。项目 `completed` 时详情只保留合法的 `project.archive`，`archived` 时无写动作，镜头、资产和制作分项 `allowedActions` 同步为空。
- 资产及制作分项 `allowedActions` 由后端结合平台权限、项目管理人/全项目范围、项目状态、`storageStatus=ready`、资源生命周期、版本、任务状态和未提交版本发布记录计算：资产可返回 `asset.edit`、`assetItem.add`、`asset.archive`，并在全部活动分项均可分配时聚合返回 `task.assign`；制作分项可返回 `assetItem.edit`、`assetItem.archive`、`task.assign`，前端不能自行合成。资产删除允许级联处理尚未开始的任务和活动制作分项，但仍被镜头使用、已有版本或任一任务已开始时必须拒绝；分项已有版本后不再允许普通编辑，存在活动任务时不允许单独归档，任务已完成或存在非 `committed` 提交时不允许分配/改派。
- 制作分项缩略图只绑定该分项当前最新版本的首个 `thumbnail` 文件；最新版本无缩略图时返回空，不回退旧版本。父资产代表图按活动分项 `(sort_order, asset_item_id)` 升序选择第一张可用缩略图。下载 URL 仍为受保护的 `/shot-grid/versions/{versionId}/files/{fileId}/download`，不暴露绝对存储路径。
- 该终态门禁目前覆盖项目自身、集、场次、镜头、资产、资产制作分项及两类 Excel 导入；成员、任务、版本、审核、文件和目录操作等其余写接口尚未统一完成相同治理，不能从本批结论外推。

## 任务、版本与自动审核

任务链主要接口：

```http
GET  /shot-grid/tasks/mine
GET  /shot-grid/projects/{projectId}/tasks
GET  /shot-grid/tasks/{taskId}
PUT  /shot-grid/tasks/{taskId}
POST /shot-grid/projects/{projectId}/shots/{shotId}/assign
POST /shot-grid/projects/{projectId}/shots/batch-assign
POST /shot-grid/projects/{projectId}/asset-items/{assetItemId}/assign
POST /shot-grid/tasks/{taskId}/start
```

- 首次分配时 `taskLockVersion` 必须为空；已有任务改派时必须携带当前 `taskLockVersion`，并更新同一任务。任务存在任何非 `committed` 的版本提交（包括 `failed`）时禁止改派。
- 镜头批量分配最多接收 200 个 `shotId/taskLockVersion`，按镜头 ID 固定顺序加锁，并在一个事务中复用上述首次分配/改派规则；任一项失败时整批回滚。
- 资产列表批量分配最多接收 200 个 `assetItemId/taskLockVersion`，选择的父资产会展开为全部活动制作分项；批量删除最多接收 200 个 `assetId/lockVersion`。两者均按稳定 ID 顺序加锁并在单事务执行，任一目标状态或锁版本冲突时整批回滚。
- `start` 请求必须携带 `lockVersion`。制作人员只能开始本人任务；项目管理人或管理员代操作仍记录实际操作人。资产任务开始前会再次锁定制作分项并校验名称完整性，防止历史异常任务进入制作流程。
- 独立业务前端 `/workbench` 以 `GET /shot-grid/tasks/mine` 为真实数据源，`/tasks/:taskId` 读取真实详情并调用开始/编辑接口；写按钮必须同时满足平台权限和详情 `allowedActions`。后端仍会重新校验项目访问、负责人/总监身份、任务与目标状态并在写事务中加锁，前端显隐不能替代授权。
- 平台不执行图片或视频制作；任务负责人在线下制作后，按“本地校验 → 只读预检 → 平台私有上传 → 创建版本提交”进入版本发布链。

版本与审核主要接口：

```http
POST /shot-grid/tasks/{taskId}/version-submissions/preflight
POST /common/files/upload
POST /shot-grid/tasks/{taskId}/version-submissions          # HTTP 202
GET  /shot-grid/tasks/{taskId}/version-submissions/current
GET  /shot-grid/version-submissions/{submissionId}
POST /shot-grid/version-submissions/{submissionId}/retry
GET  /shot-grid/tasks/{taskId}/versions
GET  /shot-grid/versions/{versionId}
GET  /shot-grid/projects/{projectId}/review-lists
GET  /shot-grid/review-lists/{reviewListId}
GET  /shot-grid/versions/{versionId}/notes
POST /shot-grid/versions/{versionId}/notes
GET  /shot-grid/notes/{noteId}/replies
POST /shot-grid/notes/{noteId}/reply
POST /shot-grid/notes/{noteId}/resolve
GET  /shot-grid/versions/{versionId}/review-actions
POST /shot-grid/versions/{versionId}/review-actions
GET  /shot-grid/versions/{versionId}/files/{fileId}/download
```

- 预检请求体固定为 `fileName/fileSize/changelog/aiParams`，只读取任务、项目、成员、状态、未解决提交和扩展名，并验证业务文件名、目标相对路径可生成及目录快照字段完整；它不写数据库、不创建引用、不上传文件、不访问 NAS，也不检查实际目标文件。正式创建仍会在锁定项目、任务与源文件后全量复核权限、项目/任务状态、资源归属、文件授权与摘要、业务上下文、未解决提交、目标相对路径生成和目录快照一致性，以关闭 TOCTOU 窗口；实际目标文件已存在的摘要冲突由 Worker 无覆盖发布阶段处理。
- 创建提交要求 `shotgrid:version:add` 且任务详情包含 `version.add`；查询 current/status、失败重试、版本历史/详情和文件下载分别受 `shotgrid:version:query`、`shotgrid:version:retry`、`shotgrid:version:list` / `shotgrid:version:query`、`shotgrid:file:download` 约束。项目成员、负责人/总监、资源归属和状态仍由后端逐接口复核。
- 暂存事务为源文件建立 `businessType=shotgrid_version_submission` 临时引用；正式版本短事务将引用切换为 `shotgrid_version`，同时创建不可变版本、主 `sg_version_file`、`auto_single` 审核单和关系，并把任务改为 `pending_review`。`committed` 状态下的 `versionId` 通过 `sg_version.submission_id` 反查，提交表不重复保存该列。
- `current` 返回当前任务未解决提交，用于页面刷新后恢复；状态机中只有 `committed` 表示正式版本成功。`failed` 仍占用原提交行，只能经 retry 重置并重试原行，不能通过新建提交绕过唯一性和任务占用约束。前端每轮自动查询最多 30 次，连续 3 次查询错误后暂停，使用有上限的指数退避；401/403/404 立即停止，到达边界后保留人工刷新或合法重试。
- 前端将稳定幂等键和已上传 `fileId` 只保存在当前内存上下文。创建响应未知时，同一命令重放复用原 `fileId` 与幂等键并跳过重复 preflight/upload；同键异命令由后端拒绝。任务、操作或文件切换通过 AbortController 和 generation 检查阻止 ABA 迟到响应继续上传、创建或覆盖当前页面。统一请求层只对 JSON Content-Type 且不超过 64 KiB 的 Blob/ArrayBuffer 错误体做有界解析，并保留 `httpStatus/code/errorKey/details`。
- 每次发布 attempt 使用同目录唯一 `.sgtmp-{submissionId}-a{attempt}-{random}.part` 临时文件。发布校验源文件真实摘要和大小，目标已存在时只有摘要和大小完全相同才视为幂等成功；不同内容返回冲突，绝不覆盖目标。
- 修改问题永久绑定来源版本；制作人提交修订版时必须逐条填写处理说明，审核人只能在新版本审核动作中逐条确认 `resolved/still_present`。`resolved` 不携带补充说明，`still_present` 必须填写未解决原因。审核动作要求 `X-Idempotency-Key` 和版本 `lockVersion`，服务端持久化规范请求哈希与首次成功结果快照；同键同请求重放，同键异请求冲突。
- `approve` 要求全部带入问题确认已修复且当前版没有新问题；`reject` 要求至少一条问题仍存在或当前版有新问题，并把仍未关闭问题的 `pendingVersion` 推进到当前被退回版本。问题来源与标注不迁移，任务版本历史按 `pendingVersion` 展示当前待处理、按来源版本展示“已处理但未通过”的审计历史；`defer` 只记录历史。
- `/versions/:versionId` 前端深链归属 `reviews` 路由域，读取真实版本详情；任务页历史列表与版本详情都不依赖 Mock。专用下载同时验证版本文件关系、平台 `sys_file_reference`、版本到项目资源链和实时项目访问，再复用平台 Range 下载，支持 200/206 并对无效 Range 保留 416；显式 `deny` ACL 始终优先，并使用净化后的业务文件名。

## Excel 导入配置

部署时可通过以下环境变量调整安全边界：

| 环境变量 | 默认值 | 说明 |
| --- | ---: | --- |
| `SHOT_GRID_IMPORT_MAX_FILE_SIZE_BYTES` | `10485760` | 单个 `.xlsx` 最大字节数 |
| `SHOT_GRID_IMPORT_MAX_ARCHIVE_ENTRIES` | `256` | ZIP 条目上限 |
| `SHOT_GRID_IMPORT_MAX_UNCOMPRESSED_BYTES` | `67108864` | 解压后总字节上限 |
| `SHOT_GRID_IMPORT_MAX_COMPRESSION_RATIO` | `200` | 单条目最大压缩比 |
| `SHOT_GRID_IMPORT_MAX_ROWS_PER_WORKBOOK` | `10000` | 工作簿业务行上限 |
| `SHOT_GRID_IMPORT_MAX_OOXML_ROWS_PER_WORKBOOK` | `12000` | 含隐藏 Sheet 的 OOXML 物理行上限 |
| `SHOT_GRID_IMPORT_MAX_OOXML_CELLS_PER_WORKBOOK` | `200000` | OOXML 物理单元格及共享字符串条目上限 |
| `SHOT_GRID_IMPORT_MAX_OOXML_XML_ELEMENTS` | `1000000` | OOXML XML 元素总量上限 |
| `SHOT_GRID_IMPORT_MAX_OOXML_COLUMNS_PER_SHEET` | `128` | 单个 Sheet 最大列号 |
| `SHOT_GRID_IMPORT_MAX_OOXML_MERGE_RANGES` | `20000` | 合并区域数量上限 |
| `SHOT_GRID_IMPORT_MAX_OOXML_MERGED_CELLS` | `200000` | 合并区域展开后的单元格总量上限 |
| `SHOT_GRID_IMPORT_MAX_CELL_TEXT_LENGTH` | `10000` | 单个单元格文本字符上限 |
| `SHOT_GRID_IMPORT_MAX_OOXML_TEXT_CHARACTERS` | `8000000` | 共享字符串引用展开后的文本字符总量上限 |
| `SHOT_GRID_IMPORT_MAX_PREVIEW_JSON_BYTES` | `16777216` | Redis Token 载荷及 HTTP 预览 JSON 的 UTF-8 字节上限 |
| `SHOT_GRID_IMPORT_PREVIEW_TTL_SECONDS` | `1800` | Redis 预览有效期 |
| `SHOT_GRID_IMPORT_REDIS_KEY_PREFIX` | `shotgrid:import:preview` | Redis Key 前缀 |

安全门禁在线程中、`openpyxl` 建立工作簿对象前扫描全部 OOXML Sheet（含隐藏 Sheet），并在 Redis 写入和数据库提交前检查预览 JSON 大小。镜头模板版本为 `shot-v1`，资产模板版本为 `asset-v1`。资产原样表原始结构为 12 个逻辑资产、20 个制作分项，其中 Environment 2/4、Prop 4/4、Character 6/12；第 6—8 行缺少制作分项且带有制作人，在当前规则下必须改为“未分配”后才可导入，不能直接创建任务，第 16 行因复合制作人产生错误。上传原文件只用于临时解析，不持久化本地路径；若需长期保留，必须另走平台受保护文件和业务引用。

资产模板下载仍未交付：仓库原样表不能直接作为部署资源，必须先通过规定的 `artifact_tool` 安全匿名化、渲染和复核流程。该工具链当前不可用时保持失败关闭，不提供 `GET /shot-grid/imports/assets/template`，也不得把原样表直接复制到后端资源目录；资产 preview/commit 不受此下载缺口影响。

## NAS 目录 Worker 配置

目录 Worker 仅在 PostgreSQL、当前进程仍是 Application Leader 且显式启用时注册内部 APScheduler 任务 `_shot_grid_storage_outbox`。它不是 `sys_job`，不会被普通数据库任务同步或后台任务管理页面编辑。

| 环境变量 | 默认值 | 当前含义 |
| --- | ---: | --- |
| `SHOT_GRID_STORAGE_WORKER_ENABLED` | `false` | 是否允许真实目录消费；部署核验前保持关闭 |
| `SHOT_GRID_STORAGE_WORKER_POLL_INTERVAL_SECONDS` | `2` | 内部任务轮询间隔秒数 |
| `SHOT_GRID_STORAGE_WORKER_BATCH_SIZE` | `20` | 单轮最多领取的操作数 |
| `SHOT_GRID_STORAGE_WORKER_LEASE_SECONDS` | `120` | 单次领取租约秒数 |
| `SHOT_GRID_STORAGE_WORKER_HEARTBEAT_SECONDS` | `30` | 长 I/O 心跳续租间隔 |
| `SHOT_GRID_STORAGE_WORKER_OPERATION_TIMEOUT_SECONDS` | `60` | 软超时诊断阈值；不会硬杀仍运行的 SMB 线程 |
| `SHOT_GRID_STORAGE_WORKER_MAX_ATTEMPTS` | `5` | 自动尝试上限 |
| `SHOT_GRID_STORAGE_WORKER_RETRY_DELAYS_SECONDS` | `[5,15,60,300]` | 可恢复错误的退避秒数 |

领取使用 PostgreSQL `FOR UPDATE SKIP LOCKED`，每次领取生成唯一 owner，并以 owner + attempt fencing 约束续租及结果回写。事务边界固定为：领取并提交短事务 → 在线程中执行 NAS I/O → 结果回写短事务。软超时只标记诊断并继续心跳，`asyncio.to_thread` 中的 SMB 调用不会被强制终止；租约失效时也必须等待实际 I/O 退出，避免旧线程脱离受管任务。租约已被接管时旧、新 Worker 的物理 I/O 仍可能短暂重叠，因此当前只允许幂等目录创建和随机 `O_EXCL` 写探针，fencing 只保证旧持有者不能覆盖数据库终态。

内部任务会登记活动 NAS Job。正常关机或 Leader 失锁时先停止新领取、触发 Scheduler 取消，再显式等待活动 Job 完成当前 I/O 和租约收尾；只有 drain 完成后才继续释放 Redis/数据库基础设施或重新竞争 Leader。

当前自动执行状态为：

```text
pending → processing → succeeded
                    ├→ retry_wait → processing
                    └→ failed

processing 租约过期 → 由新 owner 重新领取 processing
failed ──人工重试──→ 新建 reconcile_directory(pending)
```

`compensation_pending`、`compensated`、`compensation_failed` 仍是表结构预留状态，当前 Worker 不自动删除目录，也不发起物理补偿。

## 版本发布 Worker 配置

版本发布 Worker 仅在 PostgreSQL、当前进程仍是 Application Leader 且显式启用时注册内部 APScheduler 任务 `_shot_grid_version_publisher`。它同样不是 `sys_job`，不会被普通任务管理页面编辑。

| 环境变量 | 默认值 | 当前含义 |
| --- | ---: | --- |
| `SHOT_GRID_VERSION_WORKER_ENABLED` | `false` | 是否允许真实版本文件 NAS 发布；真实 UNC 核验前保持关闭 |
| `SHOT_GRID_VERSION_WORKER_POLL_INTERVAL_SECONDS` | `2` | 内部任务轮询间隔秒数 |
| `SHOT_GRID_VERSION_WORKER_BATCH_SIZE` | `5` | 单轮最多领取的提交数 |
| `SHOT_GRID_VERSION_WORKER_LEASE_SECONDS` | `900` | 单次领取租约秒数 |
| `SHOT_GRID_VERSION_WORKER_HEARTBEAT_SECONDS` | `30` | 长 I/O 心跳续租间隔 |
| `SHOT_GRID_VERSION_WORKER_OPERATION_TIMEOUT_SECONDS` | `300` | 软超时诊断阈值；不会硬杀文件复制线程 |
| `SHOT_GRID_VERSION_WORKER_MAX_ATTEMPTS` | `5` | 自动尝试上限 |
| `SHOT_GRID_VERSION_WORKER_RETRY_DELAYS_SECONDS` | `[5,15,60,300]` | 可恢复错误的退避秒数 |

领取与提交使用 PostgreSQL 行锁、租约及 owner + attempt fencing。事务边界固定为：领取并提交短事务 → 在线程中复制、实际摘要校验和无覆盖发布 → 正式版本短事务或失败回写短事务。正常关机或 Leader 失锁时必须停止新领取并 drain 活动版本发布 Job。软超时只记录诊断并继续受管心跳，不能宣称能够硬终止仍运行的 SMB I/O。

## NAS 目录路径作用域与目录结果

- `initialize_project` 和项目级 `reconcile_directory` 的 `target_relative_path` 相对 `sg_storage_root`，必须等于项目绑定的 `project_relative_path`。成功后确认项目根目录、`ASSET/Character`、`ASSET/Environment`、`ASSET/Prop` 和 `VIDEO` 存在且项目根可写。
- `ensure_episode_directory`、`ensure_shot_directory`、`ensure_asset_directory` 以及非项目级 `reconcile_directory` 的目标相对项目根目录，分别只允许 `VIDEO\EPxx`、`VIDEO\EPxx\Sxxx`、`ASSET\{Character|Environment|Prop}\资产目录` 等冻结快照。
- 每次执行重新比对配置根路径、根路径快照、项目相对路径和完整项目路径快照，并拒绝越界、非法片段、符号链接、Windows reparse point 及被普通文件占用的目录。
- 项目初始化或项目级对账成功后才把 `sg_project_storage` 改为 `ready`；其最终失败才把项目存储改为 `failed`。动态目录失败只记录安全错误，不把已就绪的项目根存储降级为失败。

### 目录诊断与人工重试 API

```http
GET  /shot-grid/projects/{projectId}/storage/operations
GET  /shot-grid/projects/{projectId}/storage/operations/{operationId}
POST /shot-grid/projects/{projectId}/storage/retry
POST /shot-grid/storage-operations/{operationId}/retry
```

- 操作列表、详情和人工重试只允许项目管理人或具有全项目范围且拥有对应接口权限的管理员；分页关键字只匹配相对路径、稳定错误键和净化错误摘要，默认按 `createTime` 倒序并以 `operationId` 倒序打破同时间并列。安全诊断不返回租约 owner、租约时间、内部幂等键、凭据引用或内部绝对路径。
- 项目重试要求存储状态为 `failed`，请求包含 `lockVersion`、非空 `reason` 和 `X-Idempotency-Key`；受理后新建项目级 `reconcile_directory`，把项目存储改回 `initializing`，返回真实 HTTP 202。
- 动态目录重试只接受最终 `failed` 的集、镜头或资产操作，重新校验项目未归档、项目根存储仍 `ready`、业务对象仍存在且目标路径快照未变化，再新建 `reconcile_directory`。旧操作保持不可变。
- 人工重试和操作日志处于同一数据库事务；同一用户、作用域、幂等键和规范化命令重放首次受理结果，同键不同命令返回冲突。
- 制作人员可通过项目存储状态接口查看 `ready` 项目的路径；初始化中或失败时隐藏完整 UNC。项目详情只在存储确为 `failed` 且用户有权限时返回 `storage.retry` 允许动作。

## 2026-08-11 本批验证

- `python -m ruff check module_shot_grid config middlewares tests/module_shot_grid` 通过，`python -m ruff format module_shot_grid config middlewares tests/module_shot_grid --check` 报告 161 files already formatted。
- 版本预检 3 个定向测试文件为 43 passed。
- 完整 `tests/module_shot_grid` 为 499 passed、2 skipped；两个跳过项均因当前 Windows 环境不允许创建目录符号链接。
- 任务工作台/版本上传子集以 fresh PostgreSQL head `20260811_06`（22 张 `sg_` 表）、Redis DB 15、真实平台登录、生产 Nginx 和 Chrome 执行：`/workbench` 查询到 21 条任务，服务端分页为 20+1，关键字筛选命中 1 条；`taskId=900001` 开始接口 HTTP 200，`lockVersion` 0→1。
- 选择 5663 B 的 `logo.png` 后，浏览器网络顺序严格为 preflight 200 → private upload 200 → create 202；pending 状态 reload 后由 current 200 恢复。显式 `allow_local_root=True` 的本地 TEMP 适配器随后按两阶段推进 `published → committed`，attempt=1，形成 V001 `pending_review`、任务 `lockVersion=2`、1 个 `auto_single` 审核单和 1 条正式文件引用；受保护版本详情与下载均为 200，下载 5663 B 且 SHA-256 与源文件一致。
- 浏览器控制台为 0 error/0 warning；localStorage/sessionStorage 不含认证 Token、幂等键、`fileId`、修改说明或 AI 参数，登录期间认证 Token 只存在 `Admin-Token` Cookie；logout 200 后 Cookie 清除且任务/版本深链守卫生效，验收目标已精确清理。该证据只关闭隔离任务/版本子集门禁：TEMP 适配器仅验证算法和编排，夹具目录补齐仅为逻辑预览，未使用真实 UNC/SMB/NAS 服务账号，也未验证审核前端、`manual_batch`、codec、媒体轨、可解码性或转码，不是完整系统 E2E。
- 镜头管理/镜头 Excel 导入子集已在隔离 PostgreSQL、Redis DB 15、真实 FastAPI/平台账号、生产 Nginx 和 Chrome 下执行：模板为 11883 bytes 且 SHA-256 命中冻结值；preview UI 显示 24/24、warningRows 0、errorRows 0、2 集/8 场/24 镜头，EP001/EP002 各 12 行并选中全部 24 行；commit HTTP 200，首次结果 `idempotentReplay=false`，创建 2 集、8 场、24 镜头、24 任务、24 待匹配需求和 26 条目录操作，复用集/场均为 0、资产关系为 0。
- 数据库核验为 2 集、8 场、24 镜头、24 任务（三名制作人各 8）、24 待匹配需求、0 镜头资产关系、1 个 `committed` 导入批次、镜头时长合计 79000 ms；2 条集目录操作与 24 条镜头目录操作均为 `pending`。同事务审计为 1 条且 `status=0`，`method` 字符串长度 79，未超过字段上限；Redis 预检键提交后为 0。
- 浏览器三视图均显示 24 条，EP002 筛选为 12 条，场次包含 `000/001/002/003`；详情深链及刷新显示 `EP002/000/S001` 和“晓亮/XL”任务；控制台 0 error/0 warning，退出后访问详情深链回带 redirect 的登录页。
- 该结果只关闭镜头管理与镜头 Excel 导入子集浏览器门禁。旅程使用逻辑 `storageStatus=ready` 夹具且 Worker 关闭，不能证明真实 UNC/NAS；不会创建物理目录、执行写探针或验证 NAS/AD/Windows 共享 ACL，也不能替代完整系统 E2E。
- 验收后已关闭浏览器和后端 PID 12996，删除临时 Nginx 容器/镜像、隔离数据库、Redis DB 15 数据及临时文件；18080/19098 端口空闲，原 9099 服务、PostgreSQL 服务及其他数据库和 Redis 其他 DB 未改动。

### 资产管理与资产 Excel 导入子集

- 验证环境为隔离 PostgreSQL、Redis DB 15、真实 FastAPI/平台账号、生产 Nginx 和 Chrome。正式原样表 preview 显示 total 20、valid 19、warningRows 3、errorRows 1；错误行不可选，选中全部 19 个可导入行后一次 commit 成功，生成 11 个活动资产、19 个制作分项、19 个任务和 1 个自动匹配。该自动匹配来自显式隔离资产需求夹具，不是镜头样表自然产生的匹配。
- 数据库活动资产类型为 Character 5、Environment 2、Prop 4。表格、卡片和类型看板同源展示，Environment 筛选为 2 条，“蒋浩”制作人筛选为 8 条；详情深链 `/projects/880001/assets/2` 及 reload 均成功。
- 临时 `assetId=12`、`assetItemId=20` 完成创建、父资产编辑、制作分项编辑、分项归档和父资产归档；两者最终均为 `archived/lockVersion=2`，临时分项 `taskCount=0`，活动集合仍为 11 个资产/19 个分项/19 个任务。`taskId=3` 从用户 880103、`lockVersion=0` 改派到用户 880102、`lockVersion=1`；最终任务分布为蒋浩 8、嘉璋 3、占峰 8。
- `sys_oper_log` 共 7 条且全部成功，分别覆盖导入、资产创建/编辑、制作分项编辑/归档、父资产归档和任务改派。12 条 `ensure_asset_directory` Outbox 全部为 `pending`，符合目录 Worker 关闭的预期。浏览器控制台为 0 error/0 warning；localStorage 为空，sessionStorage 仅含前端传输配置与 repeat-submit 元数据，不含认证、导入 Token 或幂等密钥；退出后访问详情深链重定向到 `/login?redirect=/projects/880001/assets/2`，Redis `access_token:*` 为 0。
- 本旅程只验证真实缩略图空态，没有构造或读取真实版本缩略图文件。资产模板下载因规定的 `artifact_tool` 安全流程不可用而保持未交付、UI 静态禁用且未测试。项目使用逻辑 `storageStatus=ready` 夹具，Worker 关闭，未执行真实 UNC/NAS I/O；该结论只能称为“隔离资产管理/资产导入子集 E2E PASS”，不能外推为完整系统 E2E、真实 NAS 或生产就绪。
- 验收后已关闭 Playwright，停止后端 PID 29056/32996，删除唯一临时 Nginx 容器且未新建镜像；18081/19099 端口空闲，隔离 PostgreSQL 库存在数/连接数为 0/0，Redis DB 15 `DBSIZE=0` 且 owner 键为 0，54 项 TEMP 精确删除。原 9099 PID 4820 仍监听，基础 PostgreSQL/Redis 均保持 healthy。

## 分层

```text
controller → service → dao → entity/do
                    ↘ entity/vo

接口权限
  → PreAuthDependency
  → UserInterfaceAuthDependency
  → ProjectAccessDependency
  → ProjectRoleDependency
  → Service/DAO 资源归属复核
```

业务 API 使用 `/shot-grid` 前缀，权限码使用 `shotgrid:<resource>:<action>`。Shot Grid 表只承诺 PostgreSQL，用户和受保护文件继续复用 `sys_user`、`sys_file_info` 与 `sys_file_reference`。模块只在 `DB_TYPE=postgresql` 时把领域 DO 注册到平台 `Base.metadata`，避免 MySQL 启动链错误创建不兼容的部分索引和 PostgreSQL `CHECK`。

## 数据库交付路径

- 已有 RuoYi PostgreSQL 基线库：执行 Alembic `upgrade head`；当前 Shot Grid head 为 `20260818_12`。
- 新数据库：执行同步后的 `sql/ruoyi-fastapi-pg.sql`，脚本会直接建立最新结构并写入当前 Alembic 版本。
- 历史上已经落地 22 张 `sg_` 表但没有 `alembic_version` 的库，必须先备份并在克隆库核对为 01 结构，才能 `stamp 20260810_01` 后执行 `upgrade head`；不得直接对未核验的正式库 stamp。
- `20260810_04` 是无版本历史库的采用/修复 revision，会把时间精度、审计人默认值、序场次/资产制作分项/主文件约束和集场次编号唯一性收敛为仓库从 01 起就声明的当前契约。时间精度收敛到秒会舍弃历史秒以下精度，升级前必须保留可恢复备份。
- `20260810_05` 为 NAS Worker 补充存储操作执行状态一致性约束和两个非唯一的项目维度查询索引。升级会先检查历史 `sg_storage_operation`；若状态、租约、重试时间或完成时间互相矛盾，会以 `SG_STORAGE_OPERATION_EXECUTION_STATE_CONFLICT` 整体失败，必须先治理冲突数据再重试，迁移不会自动改写业务状态。两个新索引不引入数据唯一性冲突；降级会恢复 04 版 `target_relative_path` 列注释，并精确移除 05 新增的一个约束和两个索引，不回写或删除存储操作数据。
- `20260811_06` 在任何 DDL 前检查：同一 `source_file_id` 不得被多条提交占用；每个任务在 `pending/publishing/published/committing/failed` 中最多一条未解决提交；提交状态、租约与错误字段组合必须一致。冲突分别以 `SG_VERSION_FILE_ALREADY_BOUND`、`SG_VERSION_SUBMISSION_ACTIVE` 或 `SG_VERSION_SUBMISSION_EXECUTION_STATE_CONFLICT` 整体失败，迁移不猜测修复业务数据。通过后安装“我的任务”索引、源文件唯一索引、包含 `failed` 的未解决提交部分唯一索引、提交执行/错误状态约束，以及审核动作幂等键、SHA-256 请求哈希、首次成功响应快照和唯一约束。downgrade 只移除 06 对象并恢复 05 的活动提交索引语义，不回写业务数据。
- `20260812_07` 增加媒体派生任务表及每版本唯一缩略图、代理媒体索引；`20260812_08` 增加 5173“系统管理 → NAS 根目录”菜单与管理权限入口，不硬编码任何具体环境的 UNC 地址。根目录新增后必须由后端服务账号执行随机临时文件创建、回读和删除探测，只有 `enabled + healthy` 才能供 5174 创建项目选择。`20260813_09` 释放没有活动任务和正式版本的历史误删镜头编号；新删除镜头直接写入 `del_flag='2'`。`20260814_10` 切换到跨版本修改问题闭环，`20260817_11` 修复媒体派生文件版本引用类型，`20260818_12` 以 PostgreSQL-only 迁移增加 `sg_managed_user_role` 来源标记且不创建固定平台角色。
- 04 在任何 `ALTER` 或时间精度收敛前先预检历史数据；若存在序场次命名不一致、资产制作分项名称/键不成对、非审核媒体被标为主文件，或未删除的集号/场次号（含归档行）重复，会以稳定的 `SG_SHOT_GRID_REPAIR_*` PostgreSQL 异常整体回滚。必须先治理冲突数据再重试，迁移不会猜测或静默改写业务数据。
- 04 的 downgrade 只回退 Alembic 版本号，不把数据库重新污染为从未被正式 revision 声明的旧弱结构，也不能恢复已舍弃的秒以下精度；灾难恢复应使用升级前备份。
- 04 只修复有业务语义的差异；`selection_hash`、`result_summary`、成员生命周期字段的物理列顺序，以及 PostgreSQL 对等价 `CHECK`/部分索引的 cast 文本差异，不通过重建表处理。
- 从 `20260810_03` 继续降级到旧成员结构前必须不存在 `member_status='removed'` 的成员；迁移会安全失败，防止旧代码静默恢复已移除成员的项目访问。

当前仓库尚无完整平台 Alembic baseline，因此不能把 Shot Grid 增量 revision 描述为能够从真正空库独立建立全部 RuoYi 平台表。
