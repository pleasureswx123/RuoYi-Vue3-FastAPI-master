# Shot Grid 后端模块

## 当前边界

本模块是 Shot Grid 业务后端的 PostgreSQL 领域模块。当前已交付：

- 25 张 `sg_` 领域表对应的 SQLAlchemy DO；
- 项目成员范围与项目角色权限依赖；
- 受平台角色菜单授权约束的 `GET /shot-grid/navigation`；
- 项目范围列表、详情、真实概览聚合、创建项目事务、存储初始化状态与项目成员管理；
- 项目编辑/归档，以及集、场次、镜头、资产和资产制作分项的查询、创建、修改与业务归档；
- 项目内镜头/资产任务委派候选安全选项、镜头与资产导入模板的鉴权二进制下载，以及完成/归档项目下集、场次、镜头、资产、资产制作分项和两类 Excel 导入写门禁；
- 项目任务分页、跨项目“我的任务”、任务详情/编辑、镜头或资产制作分项首次分配/受控改派，以及负责人开始任务；
- 镜头和资产 `.xlsx` 的安全预检、Redis 短期 Token、选中行全事务提交和 PostgreSQL 耐久幂等结果；
- 平台私有文件上传后的多候选版本暂存、逐文件临时业务引用、默认关闭的 NAS 版本发布 Worker、正式版本轮次/候选文件引用/`auto_single` 审核单事务，以及候选文件专用授权下载；
- 任务版本、自动单版本审核单、跨版本修改问题、制作人逐条处理说明、审核人逐条确认、审核动作历史和 `approve/reject/defer` 状态闭环；
- 由 Application Leader 调度的 NAS 目录 Outbox Worker，包含数据库租约领取、心跳续租、退避重试、路径快照复核、幂等建目录和写权限探针；
- 项目目录初始化、集/镜头/资产动态目录确保，以及项目/动态目录操作的分页诊断、详情和人工对账重试 API；
- PostgreSQL Alembic 迁移链、初始化 SQL、菜单、权限按钮和字典种子；
- 元数据、导航、项目权限、项目事务、两类真实样表解析、任务/版本/审核、目录状态/DAO/路径适配器/Worker/路由和内部 Scheduler 任务的针对性测试入口。

当前批次仍不包含资产需求人工处理、`manual_batch` 人工批量审核单、真实 FFmpeg 媒体缩略图/代理/转码验收和完整系统 E2E；镜头与资产 v2 模板下载已经交付。独立业务前端已接入镜头和资产的真实列表多视图、详情、CRUD、任务分配及 Excel 预检/提交，并已接入跨项目“我的任务”工作台、任务详情/开始/编辑、多候选版本提交、刷新恢复、历史/详情、受保护下载和 `auto_single` 候选选择/问题/退回/通过闭环。项目管理和任务/版本子集已有隔离 PostgreSQL、Redis DB 15、真实平台账号与浏览器旅程；旧镜头/资产导入旅程基于 v1 预分配规则，不能作为当前 v2“导入后未分配且不建任务”的验收证据，两类 v2 模板/导入、首次委派唯一性和六阶段生产履历仍需重新验证。多候选旅程使用测试专用 UNC 到本机临时目录映射验证真实私有上传、Worker 复制、数据库提交和审核编排，不是真实 UNC/SMB/NAS 服务账号、共享 ACL 或 FFmpeg 验收。平台私有上传当前单文件上限仍为 100 MiB，`mov` 已加入上传白名单；版本服务按真实字节校验 JPEG/PNG 与 MP4/MOV 容器签名/品牌，但尚未探测 codec、视频轨、可解码性或执行转码。已交付接口通过平台权限、项目角色、资源归属、项目/任务/版本行锁、乐观锁、业务归档、文件引用和同事务审计约束，不能使用通用代码生成 CRUD 绕过状态机。任何子集旅程都不是完整系统 E2E 或生产就绪证明。

资产类型、名称和完整目录身份在创建时一并冻结，但手工创建和 Excel 导入都不创建资产对象目录 Outbox；制作人开始任一资产制作分项任务时才锁定父资产、创建或复用共享目录操作，任务经 `preparing` 等待成功后进入 `in_progress`。普通 PUT 只修改描述、排序和备注；该 PUT 是三项非身份主数据的完整快照，省略描述或备注表示清空，省略排序表示归零。任何重命名、改类型或目录迁移都必须另建受控动作。制作分项在尚无版本时可补充或纠正主数据，已有正式版本后全部冻结；缺失制作分项只能作为未分配草稿保存或导入，首次分配、改派、批量分配、开始任务和资产图片版本提交均失败关闭。镜头号、集号和场次号也不提供普通改号。手工创建或 Excel 导入只创建镜头/资产制作分项，不接受制作人且不得创建任务；首次显式委派才创建唯一的 `not_started` 任务。正式版本事务按 `project → task/submission → version → auto_single review list → note` 锁序执行，避免项目元数据、改派、提交和审核并发穿透。

NAS 目录 Worker 和版本发布 Worker 的代码路径已经建立，所有环境样例仍以 `SHOT_GRID_STORAGE_WORKER_ENABLED=false`、`SHOT_GRID_VERSION_WORKER_ENABLED=false` 安全关闭。Windows 运行节点可直接使用 UNC；公司 Linux 生产节点通过 `SHOT_GRID_NAS_SERVER_MOUNT_MAP` 只允许 `192.168.10.64`，并把该服务器下任意共享动态解析到 autofs/CIFS 命名空间；`SHOT_GRID_NAS_UNC_MOUNT_MAP` 仍保留为精确根兼容能力。每次探测、目录操作和版本发布前都要确认实际共享挂载根位于 `cifs/smb3`，防止 autofs 或 NAS 失效后误写本地磁盘。本地测试只有显式 `allow_local_root=True` 才能使用临时目录。启用前仍必须以正式 NAS 服务账号完成共享 ACL、真实读写删除、目录创建、版本发布和失败恢复验收；源码、Mock、迁移或 Scheduler 注册不能替代该门禁。

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
GET /shot-grid/imports/assets/template
```

- `GET /shot-grid/projects/{projectId}/members` 支持可选 `projectRole=director|creator`；传入时按项目角色过滤，不传时返回全部活动项目成员。
- `shot-assignee-options` 要求登录、`shotgrid:shot:list` 和项目访问，使用 `pageNum/pageSize/keyword` 分页；只返回 `projectRole=creator` 的活动项目成员及有效未删除平台账号的 `userId/userName/nickName/avatar/deptId/deptName/projectRole/producerCode` 安全投影。兼容字段 `producerCode` 由 `sys_user.nick_name` 派生，关键字只匹配账号与昵称；该接口只服务显式任务委派，委派事务仍重新校验成员状态和项目角色。
- `asset-assignee-options` 要求登录、`shotgrid:asset:list` 和项目访问，分页、关键字及安全投影与镜头选项一致；该接口只服务显式任务委派，首次分配或改派事务仍重新校验项目状态、成员状态和平台用户昵称。
- 任务列表与详情的 `assignee` 安全摘要同时返回 `userName/nickName`；业务页面优先展示 `sys_user.user_name`，`nickName` 只作为缺失时的历史兼容回退，避免把制作人账号缩写当作姓名。
- 版本列表、详情、最近提交及人工审核单中的 `submitterName` 统一取 `sys_user.user_name`；文件名中的制作人标识仍按冻结契约取 `sys_user.nick_name`，不得因展示姓名调整而重命名历史版本文件。
- 两类模板下载分别要求对应导入权限，返回 XLSX 二进制和 `X-Shot-Grid-Template-Version`，不套统一 JSON envelope。应用层传输加密只精确放行模板 GET；同前缀预检和提交 JSON 仍保持原加密策略。部署文件缺失或摘要不一致时返回 HTTP 503 / `SG_IMPORT_TEMPLATE_UNAVAILABLE`。
- 当前服务资源为 `resources/templates/shot-v2.xlsx` 与 `resources/templates/asset-v2.xlsx`，附件文件名分别为 `镜头导入模板-shot-v2.xlsx`、`资产导入模板-asset-v2.xlsx`。冻结 SHA-256 分别为 `B6F24078CA56295E9E6CCE50BB3455AF198DFFFE5C08F8D85605A68C09439ECE`、`B551AC1D1D5EDC20A025B0ED90157412E1365006108816F08CB2C59AE4301696`；镜头主数据区固定 A:O 15 列，资产固定 A:F 6 列，均不含制作人。旧 `shot-v1.xlsx`、`asset-v1.xlsx` 仅保留为历史资源，不再由服务下载。
- 集、场次、镜头、资产和资产制作分项的创建、修改、归档在锁内读取项目状态；镜头和资产导入 preview 普通读取状态并拒绝，commit 再以 `FOR UPDATE` 锁定项目重检。`completed` 或 `archived` 均返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。项目 `completed` 时详情只保留合法的 `project.archive`，`archived` 时无写动作，镜头、资产和制作分项 `allowedActions` 同步为空。
- 镜头制作字段只允许在未分配或唯一任务仍为 `not_started` 时编辑；任务进入 `preparing/in_progress/pending_review/revision/completed` 后详情不再返回 `shot.edit`，列表也隐藏编辑入口，直接调用普通更新接口返回 HTTP 409 / `SG_SHOT_EDIT_PRODUCTION_STARTED`。负责人改派仍是独立受控动作，不能借改派覆盖镜头制作字段。
- 资产及制作分项 `allowedActions` 由后端结合平台权限、项目管理人/全项目范围、项目状态、`storageStatus=ready`、资源生命周期、版本、任务状态和未提交版本发布记录计算：资产可返回 `asset.edit`、`assetItem.add`、`asset.archive`，并在全部活动分项均可分配时聚合返回 `task.assign`；制作分项可返回 `assetItem.edit`、`assetItem.archive`、`assetItem.delete`、`task.assign`，前端不能自行合成。资产删除允许级联处理尚未开始的任务和活动制作分项，但仍被镜头使用、已有版本或任一任务已开始时必须拒绝；分项仅在未分配或任务仍为 `not_started` 且尚无版本时允许普通编辑，任务开始后直接调用更新接口返回 HTTP 409 / `SG_ASSET_ITEM_PRODUCTION_STARTED`。存在活动任务时不允许单独归档，任务已完成或存在非 `committed` 提交时不允许分配/改派。
- 制作分项独立删除使用项目范围 `/asset-items/{assetItemId}/delete`：必须未开始制作、无版本及非 `committed` 提交，携带删除原因和分项锁版本；逻辑删除目标及未开始任务并在同事务记录审计，不删除父资产、其他分项或 NAS 文件。已有历史的分项继续使用合法归档。
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
- 手工创建和 Excel 导入只创建未分配业务对象，不创建空负责人任务；首次显式委派必须提供非空 `assigneeUserId` 并创建唯一 `not_started` 任务，后续改派更新同一任务，不得创建第二条正式任务。
- 镜头批量分配最多接收 200 个 `shotId/taskLockVersion`，按镜头 ID 固定顺序加锁，并在一个事务中复用上述首次分配/改派规则；任一项失败时整批回滚。
- 资产列表批量分配最多接收 200 个 `assetItemId/taskLockVersion`，选择的父资产会展开为全部活动制作分项；批量删除最多接收 200 个 `assetId/lockVersion`。两者均按稳定 ID 顺序加锁并在单事务执行，任一目标状态或锁版本冲突时整批回滚。
- `start` 请求必须携带 `lockVersion`，且只允许任务当前委派的活动 `creator` 本人执行。后端在行锁内确认当前用户就是 `assignee_user_id`、项目成员仍为 `active + creator` 且平台账号有效；`director`、管理员、超级管理员和 `shotgrid:project:all` 均不得代开始。资产任务开始前还会锁定制作分项并校验名称完整性，防止历史异常任务进入制作流程。
- 独立业务前端 `/workbench` 以 `GET /shot-grid/tasks/mine` 为真实数据源，`/tasks/:taskId` 读取真实详情并调用开始/编辑接口；写按钮必须同时满足平台权限和详情 `allowedActions`。任务编辑仅向项目管理人开放且只允许 `not_started`，进入 `preparing/in_progress/pending_review/revision/completed` 后不再返回 `task.edit`，更新接口在行锁内同样以 HTTP 409 / `SG_INVALID_STATE_TRANSITION` 拒绝；开始任务只向当前活动负责人本人开放，前端显隐不能替代后端授权和状态门禁。
- 平台不执行图片或视频制作；任务负责人在线下制作后，按“本地校验 → 只读预检 → 平台私有上传 → 创建版本提交”进入版本发布链。
- 制作履历按“创建/导入 → 委派 → 制作 → 提交版本 → 审核 → 完成”六阶段投影。开始任务进入 `in_progress`；不可变版本正式提交后进入 `pending_review`；通过后版本为 `final` 且任务为 `completed`；退回后任务为 `revision`，制作人提交新版本继续审核循环。历史数据若只有任务创建时间而没有独立委派审计，只能标记为 `inferred`，不得把 `task.create_time` 伪装成已确认的委派事件。

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
PUT  /shot-grid/versions/{versionId}/selected-candidate
POST /shot-grid/versions/{versionId}/review-actions
GET  /shot-grid/versions/{versionId}/files/{fileId}/download
```

- 预检请求体固定为有序 `candidates[]`（每项含 `clientFileKey/fileName/fileSize/sortOrder/candidateNote`）以及 `changelog/aiParams/issueResponses`。后端校验候选数量、连续顺序、单文件/整批大小和任务上下文，并为同一轮次生成共享版本号与时间戳、连续候选号和逐候选业务文件名；它不写数据库、不创建引用、不上传文件、不访问 NAS，也不检查实际目标文件。正式创建仍会在固定顺序锁定项目、任务与全部源文件后全量复核当前负责人本人、活动成员/账号、项目/任务状态、资源归属、文件授权与摘要、批内重复内容、业务上下文、未解决提交、目标相对路径生成和目录快照一致性，以关闭 TOCTOU 窗口；实际目标文件已存在的摘要冲突由 Worker 无覆盖发布阶段处理。
- 创建提交要求平台 `shotgrid:version:add`、任务详情包含 `version.add`，并且操作者是任务当前委派的活动 `creator` 本人；`director`、管理员、超级管理员和全项目范围不得代提交或代重试。查询 current/status、失败重试、版本历史/详情和文件下载分别受 `shotgrid:version:query`、`shotgrid:version:retry`、`shotgrid:version:list` / `shotgrid:version:query`、`shotgrid:file:download` 约束，其中查询可以按项目范围授权，retry 仍为当前活动负责人本人专属。
- 暂存事务为每个源文件建立 `businessType=shotgrid_version_submission` 临时引用；Worker 按候选独立记录发布状态并跳过已成功候选。只有全部候选均发布完成，正式版本短事务才把全部引用切换为 `shotgrid_version`，同时创建一个不可变版本轮次、全部 `sg_version_candidate`/`sg_version_file`、候选级媒体派生任务、一个 `auto_single` 审核单和关系，并把任务改为 `pending_review`。单候选版本在同一事务内自动设为本轮最佳并将其审核媒体设为主文件，不写审核人选择历史；多候选版本初始不选最佳，审核人选择后才切换主审核媒体。`committed` 状态下的 `versionId` 通过 `sg_version.submission_id` 反查，提交表不重复保存该列。
- `current` 返回当前任务未解决提交，用于页面刷新后恢复；状态机中只有 `committed` 表示正式版本成功。`failed` 仍占用原提交行，只能经 retry 重置并重试原行，不能通过新建提交绕过唯一性和任务占用约束。前端每轮自动查询最多 30 次，连续 3 次查询错误后暂停，使用有上限的指数退避；401/403/404 立即停止，到达边界后保留人工刷新或合法重试。
- 前端将稳定幂等键、候选顺序和按 `clientFileKey` 映射的已上传 `fileId` 只保存在当前内存上下文。创建响应未知时，同一命令重放复用完整有序文件列表与幂等键并跳过已完成的 preflight/upload；同键异命令由后端拒绝。任务、操作或候选列表切换通过 AbortController 和 generation 检查阻止 ABA 迟到响应继续上传、创建或覆盖当前页面。统一请求层只对 JSON Content-Type 且不超过 64 KiB 的 Blob/ArrayBuffer 错误体做有界解析，并保留 `httpStatus/code/errorKey/details`。
- 每个候选的每次发布 attempt 使用同目录唯一 `.sgtmp-{submissionId}-{candidateNo:02d}-a{attempt}-{random}.part` 临时文件，并严格校验提交号、候选号和 attempt。发布逐文件校验源文件真实摘要和大小，目标已存在时只有摘要和大小完全相同才视为幂等成功；不同内容返回冲突，绝不覆盖目标。
- 单候选新版本的 `selectedCandidateId` 由系统直接设置，审核人无需执行没有比较意义的选择动作；多候选版本初始为空，必须先通过候选选择接口确定最佳候选，之后才能新增问题草稿或执行 `approve/reject/defer`。人工选择请求持久幂等记录并受版本 `lockVersion` 保护。存在当前版本草稿时禁止切换候选，问题草稿、正式问题、问题核验和审核动作都绑定当时选中的候选，避免审核结论漂移到其他文件。
- 镜头与资产只读投影在多候选尚未选择最佳时稳定展示候选 01；选择后展示当前最佳候选。业务文件名、缩略图和代理媒体必须来自同一展示候选，合法的多候选 `pending_review + selectedCandidateId=null` 不得让镜头列表返回 409，也不得让资产列表和详情丢失候选 01 的缩略图。
- 修改问题永久绑定来源版本；制作人提交修订版时必须逐条填写处理说明，审核人只能在新版本审核动作中逐条确认 `resolved/still_present`。`resolved` 不携带补充说明，`still_present` 必须填写未解决原因。审核动作要求 `X-Idempotency-Key` 和版本 `lockVersion`，服务端持久化规范请求哈希与首次成功结果快照；同键同请求重放，同键异请求冲突。
- 当前版新问题先写 `sg_review_issue_draft`，仅授权审核人在审核上下文中可见；草稿携带 `lock_version`，在审核单仍活动时可编辑或删除。每条问题可附带最多 5 个、单个不超过 20 MiB 的受保护参考文件，草稿和正式问题分别通过 `sys_file_reference` 的 `shot_grid_review_issue_draft`、`shot_grid_review_issue` 类型保存引用。`approve` 要求全部带入问题确认已修复、当前版没有正式新问题且没有草稿；`reject` 要求至少一条问题仍存在或当前版有问题草稿，并在同一事务把草稿发布为不可变 `sg_note`、迁移参考文件引用、删除草稿、推进版本/任务/审核单状态及仍未关闭问题的 `pendingVersion`。问题来源与标注不迁移，任务版本历史按 `pendingVersion` 展示当前待处理、按来源版本展示“已处理但未通过”的审计历史；`defer` 只记录历史并保留私有草稿。参考文件只能通过校验草稿/问题、项目关系和平台 deny ACL 的 Shot Grid 专用接口下载。
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

安全门禁在线程中、`openpyxl` 建立工作簿对象前扫描全部 OOXML Sheet（含隐藏 Sheet），并在 Redis 写入和数据库提交前检查预览 JSON 大小。镜头模板版本为 `shot-v2`，资产模板版本为 `asset-v2`；两类模板和提交请求都不包含制作人。预检与提交只处理镜头或资产制作分项，正式提交结果中的任务创建数固定为 0；导入后由项目管理人另行显式委派。上传原文件只用于临时解析，不持久化本地路径；若需长期保留，必须另走平台受保护文件和业务引用。

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

Worker owner 仅用于租约和 fencing，不得写入面向业务用户的 `createBy/updateBy`。目录结果回写使用原操作发起人。任务详情遇到历史误写的内部 owner 时，先从最近成功的镜头目录操作回溯业务发起人；仅在无法回溯时安全投影为“系统目录服务”，不向前端泄漏进程、租约或 UUID 标识。

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

版本预检和创建接口统一使用 `SHOT_GRID_VERSION_SUBMISSION_` 边界，默认每轮最多 10 个候选、单文件最大 100 MiB、整批最大 500 MiB。后端始终重新校验，前端限制只用于即时提示；可通过 `MAX_CANDIDATES`、`MAX_FILE_SIZE_BYTES`、`MAX_BATCH_SIZE_BYTES` 调整部署上限，但三处配置与网关上传限制必须同步验收。

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

## 验证记录

- 2026-08-26 多候选增量完成后，后端完整 `tests/module_shot_grid` 为 608 passed、2 skipped；Ruff check 和本次改动 Python 文件 format check 通过。前端版本提交/审核直接相关 3 个测试文件为 40 passed，改动范围 ESLint 和 1930 modules 生产构建通过；构建仍有既有 `@vueuse/core` PURE annotation 与大 chunk 警告。
- `python -m ruff check module_shot_grid config middlewares tests/module_shot_grid` 通过，`python -m ruff format module_shot_grid config middlewares tests/module_shot_grid --check` 报告 161 files already formatted。
- 版本预检 3 个定向测试文件为 43 passed。
- 完整 `tests/module_shot_grid` 为 499 passed、2 skipped；两个跳过项均因当前 Windows 环境不允许创建目录符号链接。
- 任务工作台/版本上传子集以 fresh PostgreSQL head `20260811_06`（22 张 `sg_` 表）、Redis DB 15、真实平台登录、生产 Nginx 和 Chrome 执行：`/workbench` 查询到 21 条任务，服务端分页为 20+1，关键字筛选命中 1 条；`taskId=900001` 开始接口 HTTP 200，`lockVersion` 0→1。
- 选择 5663 B 的 `logo.png` 后，浏览器网络顺序严格为 preflight 200 → private upload 200 → create 202；pending 状态 reload 后由 current 200 恢复。显式 `allow_local_root=True` 的本地 TEMP 适配器随后按两阶段推进 `published → committed`，attempt=1，形成 V001 `pending_review`、任务 `lockVersion=2`、1 个 `auto_single` 审核单和 1 条正式文件引用；受保护版本详情与下载均为 200，下载 5663 B 且 SHA-256 与源文件一致。
- 浏览器控制台为 0 error/0 warning；localStorage/sessionStorage 不含认证 Token、幂等键、`fileId`、修改说明或 AI 参数，登录期间认证 Token 只存在 `Admin-Token` Cookie；logout 200 后 Cookie 清除且任务/版本深链守卫生效，验收目标已精确清理。该证据只关闭隔离任务/版本子集门禁：TEMP 适配器仅验证算法和编排，夹具目录补齐仅为逻辑预览，未使用真实 UNC/SMB/NAS 服务账号，也未验证审核前端、`manual_batch`、codec、媒体轨、可解码性或转码，不是完整系统 E2E。
- 2026-08-26 多候选增量使用 fresh PostgreSQL head `20260826_20`、隔离 Redis DB 15、真实平台登录和浏览器页面完成 `V001` 三候选提交 → 选择 `V001_02` → 发布修改要求并退回 → `V002` 两候选提交 → 选择 `V002_02` → 确认历史问题已修复并通过的闭环；任务最终为 `completed`。5 个候选都完成真实私有上传、版本 Worker 复制、正式候选/文件引用提交和物理文件 SHA-256 复核，首次发布失败后从页面重试并复用原提交及 `V001`。该旅程使用测试专用 UNC 到本机临时目录映射，不证明正式 NAS 服务账号、SMB/CIFS 挂载、共享 ACL、FFmpeg 或生产媒体能力，也不是完整系统 E2E。
- 2026-08-26 旅程结束后已停止隔离前后端，删除 5 个私有上传夹具、本机映射目录、临时数据库并清空专用 Redis DB 15；15174/19099 无监听，未改动现有 PostgreSQL/Redis 容器及其他数据库或 Redis DB。
- 2026-08-11 的镜头导入浏览器旅程基于旧 `shot-v1` 模板和“导入即预分配任务”规则。它曾验证 24 行解析、三视图、筛选、深链、会话清理和目录 Worker 关闭边界，但其中模板含制作人、导入创建 24 个任务及详情直接出现负责人等结论已被 v2 契约废止，不能作为当前验收证据。
- 当前必须重新验证 `shot-v2` 下载及冻结摘要、A:O 15 列预检、导入后 24 个镜头均未分配、任务创建数为 0，以及随后显式委派只创建一个唯一任务。逻辑 `storageStatus=ready` 夹具和关闭的 Worker 仍不能证明真实 UNC/NAS、物理目录、写探针或 NAS/AD/Windows 共享 ACL。
- 验收后已关闭浏览器和后端 PID 12996，删除临时 Nginx 容器/镜像、隔离数据库、Redis DB 15 数据及临时文件；18080/19098 端口空闲，原 9099 服务、PostgreSQL 服务及其他数据库和 Redis 其他 DB 未改动。

### 历史 v1 资产管理与资产 Excel 导入子集（当前契约已失效）

- 2026-08-11 的资产导入旅程基于旧 `asset-v1` 样表和制作人预分配规则。它曾验证列表多视图、CRUD/归档、任务改派、会话清理和缩略图空态，但其中复合制作人校验、导入创建 19 个任务、按制作人筛选导入结果以及“资产模板未交付”等结论已被 v2 契约废止，不能作为当前验收证据。
- 当前必须重新验证 `asset-v2` 下载及冻结摘要、A:F 6 列预检、全部制作分项未分配、任务创建数为 0，以及首次显式委派创建唯一任务；仍需另行验证真实版本缩略图文件和 UNC/NAS I/O。
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

- 已有 RuoYi PostgreSQL 基线库：执行 Alembic `upgrade head`；当前 Shot Grid head 为 `20260826_20`。若 16 以 `SG_SHOT_SEQUENCE_NOT_CONTIGUOUS` 失败，必须先在备份和克隆库核对任务、版本、文件及真实 NAS 目录，再走受控场内重排和目录迁移治理，禁止强行 `stamp`。
- 新数据库：执行同步后的 `sql/ruoyi-fastapi-pg.sql`，脚本会直接建立最新结构并写入当前 Alembic 版本。
- 历史上已经落地 22 张 `sg_` 表但没有 `alembic_version` 的库，必须先备份并在克隆库核对为 01 结构，才能 `stamp 20260810_01` 后执行 `upgrade head`；不得直接对未核验的正式库 stamp。
- `20260810_04` 是无版本历史库的采用/修复 revision，会把时间精度、审计人默认值、序场次/资产制作分项/主文件约束和集场次编号唯一性收敛为仓库从 01 起就声明的当前契约。时间精度收敛到秒会舍弃历史秒以下精度，升级前必须保留可恢复备份。
- `20260810_05` 为 NAS Worker 补充存储操作执行状态一致性约束和两个非唯一的项目维度查询索引。升级会先检查历史 `sg_storage_operation`；若状态、租约、重试时间或完成时间互相矛盾，会以 `SG_STORAGE_OPERATION_EXECUTION_STATE_CONFLICT` 整体失败，必须先治理冲突数据再重试，迁移不会自动改写业务状态。两个新索引不引入数据唯一性冲突；降级会恢复 04 版 `target_relative_path` 列注释，并精确移除 05 新增的一个约束和两个索引，不回写或删除存储操作数据。
- `20260811_06` 在任何 DDL 前检查：同一 `source_file_id` 不得被多条提交占用；每个任务在 `pending/publishing/published/committing/failed` 中最多一条未解决提交；提交状态、租约与错误字段组合必须一致。冲突分别以 `SG_VERSION_FILE_ALREADY_BOUND`、`SG_VERSION_SUBMISSION_ACTIVE` 或 `SG_VERSION_SUBMISSION_EXECUTION_STATE_CONFLICT` 整体失败，迁移不猜测修复业务数据。通过后安装“我的任务”索引、源文件唯一索引、包含 `failed` 的未解决提交部分唯一索引、提交执行/错误状态约束，以及审核动作幂等键、SHA-256 请求哈希、首次成功响应快照和唯一约束。downgrade 只移除 06 对象并恢复 05 的活动提交索引语义，不回写业务数据。
- `20260812_07` 增加媒体派生任务表；`20260812_08` 至 `20260825_19` 依次补齐 NAS 管理、镜头号治理、跨版本问题、受管角色、延迟目录、审核草稿和项目永久删除；`20260826_20` 增加版本轮次内多候选文件、候选级媒体派生和审核候选选择历史，并把既有版本回填为候选 01；`20260826_21` 增加最终版本 NAS 交付；`20260826_22` 自动选择并回填单候选版本。历史 NAS 文件不改名。
- 04 在任何 `ALTER` 或时间精度收敛前先预检历史数据；若存在序场次命名不一致、资产制作分项名称/键不成对、非审核媒体被标为主文件，或未删除的集号/场次号（含归档行）重复，会以稳定的 `SG_SHOT_GRID_REPAIR_*` PostgreSQL 异常整体回滚。必须先治理冲突数据再重试，迁移不会猜测或静默改写业务数据。
- 04 的 downgrade 只回退 Alembic 版本号，不把数据库重新污染为从未被正式 revision 声明的旧弱结构，也不能恢复已舍弃的秒以下精度；灾难恢复应使用升级前备份。
- 04 只修复有业务语义的差异；`selection_hash`、`result_summary`、成员生命周期字段的物理列顺序，以及 PostgreSQL 对等价 `CHECK`/部分索引的 cast 文本差异，不通过重建表处理。
- 从 `20260810_03` 继续降级到旧成员结构前必须不存在 `member_status='removed'` 的成员；迁移会安全失败，防止旧代码静默恢复已移除成员的项目访问。

当前仓库尚无完整平台 Alembic baseline，因此不能把 Shot Grid 增量 revision 描述为能够从真正空库独立建立全部 RuoYi 平台表。
