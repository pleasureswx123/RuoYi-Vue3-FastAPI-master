# Shot Grid 后端模块

## 当前边界

本模块是 Shot Grid 业务后端的 PostgreSQL 领域模块。当前已交付：

- 22 张 `sg_` 领域表对应的 SQLAlchemy DO；
- 项目成员范围与项目角色权限依赖；
- 受平台角色菜单授权约束的 `GET /shot-grid/navigation`；
- 项目范围列表、详情、真实概览聚合、创建项目事务、存储初始化状态与项目成员管理；
- 项目编辑/归档，以及集、场次、镜头、资产和资产制作分项的查询、创建、修改与业务归档；
- 镜头和资产 `.xlsx` 的安全预检、Redis 短期 Token、选中行全事务提交和 PostgreSQL 耐久幂等结果；
- 由 Application Leader 调度的 NAS 目录 Outbox Worker，包含数据库租约领取、心跳续租、退避重试、路径快照复核、幂等建目录和写权限探针；
- 项目目录初始化、集/镜头/资产动态目录确保，以及项目/动态目录操作的分页诊断、详情和人工对账重试 API；
- PostgreSQL Alembic 迁移链、初始化 SQL、菜单、权限按钮和字典种子；
- 元数据、导航、项目权限、项目事务、两类真实样表解析、目录状态/DAO/路径适配器/Worker/路由和内部 Scheduler 任务的针对性测试。

当前批次仍不包含独立任务分配/改派与状态动作、资产需求人工处理、版本文件发布和审核闭环。Excel 模板下载端点也未生成；预检按仓库内已冻结样表执行。已交付的普通管理接口同样通过项目角色、资源归属、项目行锁、乐观锁、业务归档、目录 Outbox 和同事务审计约束，不能使用通用代码生成 CRUD 绕过状态机。

资产类型、名称和完整目录身份在创建时一并冻结，普通 PUT 只修改描述、排序和备注；该 PUT 是三项非身份主数据的完整快照，省略描述或备注表示清空，省略排序表示归零。任何重命名、改类型或目录迁移都必须另建受控动作。制作分项在尚无版本时可补充或纠正主数据，已有正式版本后全部冻结。镜头号、集号和场次号也不提供普通改号。未来版本创建事务上线前必须先锁定所属项目行，再创建版本，避免与项目画幅或类型修改产生并发竞态。

NAS 目录 Worker 的代码路径已经建立，但所有环境样例都以 `SHOT_GRID_STORAGE_WORKER_ENABLED=false` 默认关闭。本批次使用临时本地目录验证路径适配器时必须显式注入 `allow_local_root=True`；生产适配器默认只接受 Windows UNC。尚未使用真实 NAS、正式 Windows Worker 服务账号和 NAS/AD/共享 ACL 完成隔离 UNC E2E，因此不得把本批交付描述成 NAS 生产验收通过。

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

安全门禁在线程中、`openpyxl` 建立工作簿对象前扫描全部 OOXML Sheet（含隐藏 Sheet），并在 Redis 写入和数据库提交前检查预览 JSON 大小。镜头模板版本为 `shot-v1`，资产模板版本为 `asset-v1`。上传原文件只用于临时解析，不持久化本地路径；若需长期保留，必须另走平台受保护文件和业务引用。

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

### 路径作用域与目录结果

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

- 操作列表、详情和人工重试只允许项目总监或具有全项目范围且拥有对应接口权限的管理员；分页关键字只匹配相对路径、稳定错误键和净化错误摘要，默认按 `createTime` 倒序并以 `operationId` 倒序打破同时间并列。安全诊断不返回租约 owner、租约时间、内部幂等键、凭据引用或内部绝对路径。
- 项目重试要求存储状态为 `failed`，请求包含 `lockVersion`、非空 `reason` 和 `X-Idempotency-Key`；受理后新建项目级 `reconcile_directory`，把项目存储改回 `initializing`，返回真实 HTTP 202。
- 动态目录重试只接受最终 `failed` 的集、镜头或资产操作，重新校验项目未归档、项目根存储仍 `ready`、业务对象仍存在且目标路径快照未变化，再新建 `reconcile_directory`。旧操作保持不可变。
- 人工重试和操作日志处于同一数据库事务；同一用户、作用域、幂等键和规范化命令重放首次受理结果，同键不同命令返回冲突。
- 制作人员可通过项目存储状态接口查看 `ready` 项目的路径；初始化中或失败时隐藏完整 UNC。项目详情只在存储确为 `failed` 且用户有权限时返回 `storage.retry` 允许动作。

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

- 已有 RuoYi PostgreSQL 基线库：执行 Alembic `upgrade head`；当前 Shot Grid head 为 `20260810_05`。
- 新数据库：执行同步后的 `sql/ruoyi-fastapi-pg.sql`，脚本会直接建立最新结构并写入当前 Alembic 版本。
- 历史上已经落地 22 张 `sg_` 表但没有 `alembic_version` 的库，必须先备份并在克隆库核对为 01 结构，才能 `stamp 20260810_01` 后执行 `upgrade head`；不得直接对未核验的正式库 stamp。
- `20260810_04` 是无版本历史库的采用/修复 revision，会把时间精度、审计人默认值、序场次/资产制作分项/主文件约束和集场次编号唯一性收敛为仓库从 01 起就声明的当前契约。时间精度收敛到秒会舍弃历史秒以下精度，升级前必须保留可恢复备份。
- `20260810_05` 为 NAS Worker 补充存储操作执行状态一致性约束和两个非唯一的项目维度查询索引。升级会先检查历史 `sg_storage_operation`；若状态、租约、重试时间或完成时间互相矛盾，会以 `SG_STORAGE_OPERATION_EXECUTION_STATE_CONFLICT` 整体失败，必须先治理冲突数据再重试，迁移不会自动改写业务状态。两个新索引不引入数据唯一性冲突；降级会恢复 04 版 `target_relative_path` 列注释，并精确移除 05 新增的一个约束和两个索引，不回写或删除存储操作数据。
- 04 在任何 `ALTER` 或时间精度收敛前先预检历史数据；若存在序场次命名不一致、资产制作分项名称/键不成对、非审核媒体被标为主文件，或未删除的集号/场次号（含归档行）重复，会以稳定的 `SG_SHOT_GRID_REPAIR_*` PostgreSQL 异常整体回滚。必须先治理冲突数据再重试，迁移不会猜测或静默改写业务数据。
- 04 的 downgrade 只回退 Alembic 版本号，不把数据库重新污染为从未被正式 revision 声明的旧弱结构，也不能恢复已舍弃的秒以下精度；灾难恢复应使用升级前备份。
- 04 只修复有业务语义的差异；`selection_hash`、`result_summary`、成员生命周期字段的物理列顺序，以及 PostgreSQL 对等价 `CHECK`/部分索引的 cast 文本差异，不通过重建表处理。
- 从 `20260810_03` 继续降级到旧成员结构前必须不存在 `member_status='removed'` 的成员；迁移会安全失败，防止旧代码静默恢复已移除成员的项目访问。

当前仓库尚无完整平台 Alembic baseline，因此不能把 Shot Grid 增量 revision 描述为能够从真正空库独立建立全部 RuoYi 平台表。
