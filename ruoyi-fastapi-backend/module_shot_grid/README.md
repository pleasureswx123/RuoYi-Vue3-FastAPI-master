# Shot Grid 后端模块

## 手工业务资源接口契约

项目修改、状态动作，以及集、场次、镜头、资产和资产制作分项的列表、详情、创建、修改、归档接口统一位于
`/shot-grid/projects/{projectId}`。接口同时执行平台 RBAC 与项目访问校验；嵌套写入会核对父资源的
`project_id`，镜头还会核对集与场次层级。

所有修改、状态动作和归档请求必须携带 `lockVersion`。版本过期返回 HTTP 409 和稳定错误键
`SG_LOCK_VERSION_CONFLICT`。归档只写业务状态 `archived`，并保持 `del_flag='0'`；`del_flag='2'`
仅保留给真正删除语义。集号、场次号、集内镜头号、项目内资产名称/路径键与制作分项名称的唯一性，
继续由 PostgreSQL 初始化 SQL、Alembic head 与 SQLAlchemy DO 中现有的唯一索引和检查约束共同保证。

## 当前边界

本模块是 Shot Grid 业务后端的 PostgreSQL 领域模块。当前已交付：

- 22 张 `sg_` 领域表对应的 SQLAlchemy DO；
- 项目成员范围与项目角色权限依赖；
- 受平台角色菜单授权约束的 `GET /shot-grid/navigation`；
- 项目范围列表、详情、真实概览聚合、创建项目事务、存储初始化状态与项目成员管理；
- 镜头和资产 `.xlsx` 的安全预检、Redis 短期 Token、选中行全事务提交和 PostgreSQL 耐久幂等结果；
- PostgreSQL Alembic 迁移链、初始化 SQL、菜单、权限按钮和字典种子；
- 元数据、导航、项目权限、项目事务和两类真实样表解析的针对性测试。

此外，源码已覆盖项目编辑/归档、集/场次/镜头/资产/制作分项 CRUD、待匹配需求处理、任务分配与开始、版本提交和查询、人工审核单、版本意见/回复、`approve`/`reject`/`defer` 审核动作、工作台、搜索、文件发现及专用版本文件访问。`review_controller.py` 已公开三个具名审核动作和动作历史查询，`review_service.py` 已实现加锁、角色/状态/乐观锁校验、不可变动作历史、唯一 final 与任务状态变更；所以旧描述“审核动作闭环仍未实现”与源码不符，现已更正。

上述结论来自静态源码和针对性单元测试，只能表述为 **源码完成，待集成/E2E**。本次没有在真实 PostgreSQL、Redis、文件服务、受控 SMB/NAS 和浏览器中验证完整闭环，不能标记为验收通过。媒体格式/大小/编码等产品限制、NAS 发布成功语义及 UNC 桌面协议仍待产品和运维确认。Excel 模板下载端点未生成；预检按仓库内已冻结样表执行。

版本提交先在 `sg_version_submission` 冻结任务版本号、服务端毫秒时间戳、业务文件名和幂等键。Worker 将平台私有上传复制到项目 NAS 临时路径，核对 SHA-256 后以同文件系统 `rename` 发布；正式数据库事务失败时保持 `published` 并允许复用同一 submission 重试，不重新生成冻结字段。同任务活动提交由 PostgreSQL 部分唯一索引兜底。

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

## NAS 目录消费者

`ShotGridStorageOperationWorker` 消费 `sg_storage_operation`。每次领取和结算各自使用短事务，NAS I/O
在线程中执行且不占用数据库事务；租约超时后其他 Worker 可接管，目录创建使用 `exist_ok=True` 保持幂等。
生产环境应为每个进程设置唯一 Worker ID，并用独立进程循环调用 `run_once()`。可配置
`SHOT_GRID_STORAGE_WORKER_LEASE_SECONDS`、`MAX_ATTEMPTS`、`RETRY_BASE_SECONDS` 和 `BATCH_SIZE`。

管理员接口 `/shot-grid/admin/storage-operations` 提供脱敏诊断、失败重试与目录对账。真实验收必须使用
管理员配置的受控 SMB 共享；临时目录测试只验证路径和幂等逻辑，不能作为 NAS/SMB 验收结论。

安全门禁在线程中、`openpyxl` 建立工作簿对象前扫描全部 OOXML Sheet（含隐藏 Sheet），并在 Redis 写入和数据库提交前检查预览 JSON 大小。镜头模板版本为 `shot-v1`，资产模板版本为 `asset-v1`。上传原文件只用于临时解析，不持久化本地路径；若需长期保留，必须另走平台受保护文件和业务引用。

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

- 已有 RuoYi PostgreSQL 基线库：执行 Alembic `upgrade head`；当前 Shot Grid head 为 `20260810_04`。
- 新数据库：执行同步后的 `sql/ruoyi-fastapi-pg.sql`，脚本会直接建立最新结构并写入当前 Alembic 版本。
- 历史上已经落地 22 张 `sg_` 表但没有 `alembic_version` 的库，必须先备份并在克隆库核对为 01 结构，才能 `stamp 20260810_01` 后执行 `upgrade head`；不得直接对未核验的正式库 stamp。
- `20260810_04` 是无版本历史库的采用/修复 revision，会把时间精度、审计人默认值、序场次/资产制作分项/主文件约束和集场次编号唯一性收敛为仓库从 01 起就声明的当前契约。时间精度收敛到秒会舍弃历史秒以下精度，升级前必须保留可恢复备份。
- 04 在任何 `ALTER` 或时间精度收敛前先预检历史数据；若存在序场次命名不一致、资产制作分项名称/键不成对、非审核媒体被标为主文件，或未删除的集号/场次号（含归档行）重复，会以稳定的 `SG_SHOT_GRID_REPAIR_*` PostgreSQL 异常整体回滚。必须先治理冲突数据再重试，迁移不会猜测或静默改写业务数据。
- 04 的 downgrade 只回退 Alembic 版本号，不把数据库重新污染为从未被正式 revision 声明的旧弱结构，也不能恢复已舍弃的秒以下精度；灾难恢复应使用升级前备份。
- 04 只修复有业务语义的差异；`selection_hash`、`result_summary`、成员生命周期字段的物理列顺序，以及 PostgreSQL 对等价 `CHECK`/部分索引的 cast 文本差异，不通过重建表处理。
- 从 `20260810_03` 继续降级到旧成员结构前必须不存在 `member_status='removed'` 的成员；迁移会安全失败，防止旧代码静默恢复已移除成员的项目访问。

当前仓库尚无完整平台 Alembic baseline，因此不能把 Shot Grid 增量 revision 描述为能够从真正空库独立建立全部 RuoYi 平台表。
