# 镜头与资产强制删除实施计划

> **供执行代理使用：** 按任务使用 `superpowers:executing-plans`（建议在当前会话执行），或在用户选择后使用 `superpowers:subagent-driven-development`。复选框用于记录实际进度，不能提前勾选。

**目标：** 分别以 `shotgrid:shot:forceDelete` 和 `shotgrid:asset:forceDelete` 授权各制作阶段的逻辑删除，保持普通删除规则与现有数据范围。

**架构：** 增加专用强删 Service/DAO，沿用现有镜头、资产 Controller、VO 和权限投影。项目协调锁内完成逻辑删除、关系解绑、后台任务凭据失效和审计；NAS I/O 始终在事务外，保留历史及文件。两条批量接口与共享 Element Plus 确认组件服务单个及批量入口。

**技术栈：** PostgreSQL、Alembic、FastAPI、SQLAlchemy Async、Pydantic、Vue 3、Element Plus、项目 Axios、pytest、Vitest。

**设计依据：** [已批准设计](../specs/2026-10-13-shot-asset-force-delete-design.md)。状态：用户已批准顺序执行；实现与定向验证已落地，完整验收限制见验证记录。

## 全局约束

- 两权限独立，不授予默认角色，不替代项目管理身份或全部范围；已归档、已完成项目保持只读。
- 保留普通 `archive` 权限和接口；不扩展单独制作分项删除权限。
- 批量整批提交或回滚，锁版本必须一致；镜头不重编号，资产解除镜头关联。
- 逻辑删除保留文件、版本、审核历史和文件引用；不承诺同名目录复用，不增加物理删除或恢复能力。
- 新失败语义统一错误键 `SG_TARGET_FORCE_DELETED`；使用各表已有合法失败终态，不能引入未经迁移的状态值。
- 不新建平行请求或权限体系；中文文案与注释，ElForm 显式校验及按钮事件，不使用原生 submit。
- 沿用 PostgreSQL 基线和现有随机隔离测试库，不在真实业务数据上测试删除。
- 当前大量 DAO/Service 已有用户改动，执行前记录文件差异，逐段叠加；不覆盖、不暂存无关改动，不自动提交、推送或部署。

## 评审重点

1. 多角色授权：移除某角色权限但另一个角色仍有授权时，动作继续可用；最后一处授权撤销后后端拒绝。由任务 1、4 验证。
2. 后台 I/O 已开始：删除后物理写入可能返回，但旧 owner + attempt 不能提交业务结果。由任务 2 验证。
3. 共享目录及混合审核批次：目标删除不能停掉其他内容或替其他内容作审核结论。由任务 2 验证。
4. 归档分项、无任务资产、含错误锁版本的批量：全部目标语义一致，不能留下活动任务或半批删除。由任务 2 验证。
5. 页面迟到响应与权限撤回：弹窗切项目后不得用旧目标提交，按钮隐藏不代替接口校验。由任务 3、4 验证。

## 任务 1：接口、权限和数据库菜单契约

**文件：** 修改后端 `module_shot_grid/controller/{shot_crud_controller,asset_crud_controller}.py`、`entity/vo/{shot_crud_vo,asset_crud_vo}.py`；新增 `tests/module_shot_grid/test_force_delete_contract.py`、`test_force_delete_migration_pg.py`；新增 `alembic/versions/2026_10_13_1000-20261013_39_force_delete_permissions.py`，同步 `sql/ruoyi-fastapi-pg.sql`。以下后端路径均相对 `ruoyi-fastapi-backend/`。

**接口：**
- `ShotGridShotBatchForceDeleteModel`：复用镜头批量目标结构，加必填、去首尾空白后长度 1..500 的 `reason`；`items` 限定 1..200，不允许重复 ID。
- `ShotGridAssetBatchForceDeleteModel`：同样规则，目标字段为 `assetId/lockVersion`。
- 返回分别复用 `ShotGridShotBatchDeleteResultModel` 和 `ShotGridAssetBatchDeleteResultModel`。
- 注册设计中的两条 `batch-force-delete` 路由，分别调用任务 2 的 Service，认证、权限依赖和项目角色依赖沿用现有模式。

- [ ] 编写 VO 和路由测试：空列表、重复 ID、空白原因、201 项拒绝；200 项及中文原因可解析；两个接口分别只声明对应强删权限，仍有认证及项目管理范围依赖。
- [ ] 执行 `.venv/Scripts/python.exe -m pytest tests/module_shot_grid/test_force_delete_contract.py -q`，确认因缺少新模型/路由失败后实现。
- [ ] 编写幂等菜单升级/降级测试：两个权限挂正确父菜单；升级两次不重复；不增加普通角色绑定；降级仅撤销新增权限和关联。复用 `test_asset_manager_start_pg.py::isolated_pg_url`，使用随机测试库。
- [ ] 实现迁移与初始化 SQL。先确认 revision 38 仍是唯一 head；若有新的用户迁移，顺延本迁移版本和前驱并同步计划，不产生分叉。只承诺 PostgreSQL。
- [ ] 查看平台角色权限缓存失效链，测试撤销最后授权与多角色剩余授权，不能只测试前端 Store。若现有撤权链不失效，只在角色授权缓存相关范围补齐并增加回归测试。
- [ ] 重跑上述定向测试，确认通过；所有写操作测试只触及隔离测试数据。未接通 Service 前路由行为测试可保持明确未完成，不宣称任务整体通过。

## 任务 2：逻辑删除事务、可见性和后台一致性

**新文件：** `module_shot_grid/service/force_delete_service.py`、`module_shot_grid/dao/force_delete_dao.py`；测试 `tests/module_shot_grid/test_force_delete_service.py`、`test_force_delete_pg.py`、`test_force_delete_workers.py`。

**修改范围：** `service/{shot_crud_service,asset_crud_service,storage_worker_service,version_publish_worker_service,final_delivery_worker_service,media_derivation_service,storage_management_service,version_submission_service,review_service}.py` 与对应现有 DAO；审核/任务/搜索/文件中心读取链按测试暴露的缺口修正。不重构无关模块。

**公开接口：** `ShotGridForceDeleteService.batch_delete_shots(db: AsyncSession, project_id: int, command: ShotGridShotBatchForceDeleteModel, current_user: CurrentUserModel, access: ShotGridProjectAccessModel) -> ShotGridShotBatchDeleteResultModel`；资产方法 `batch_delete_assets` 使用对应资产模型及返回类型。Service 自身复核动作权限与范围，不能只信 Controller。

**DAO 边界：** `ShotGridForceDeleteDao` 只负责有范围的锁定、查询与写入，不 commit。以 `project_id` 限制所有目标，返回用于审计的目标、任务、关系及后台操作 ID；既有任务状态值不改写为不存在的 cancelled，使用 `del_flag='2'`、递增锁号，实体同时 `lifecycle_status='archived'`。

- [ ] 先写参数化失败测试，覆盖 task_status 的 `not_started/preparing/in_progress/pending_review/revision/completed`，无任务、空分项、归档分项和已有版本；断言成功后目标与任务逻辑删除、文件引用和历史仍在，其他镜头编号不变。
- [ ] 写越项目、普通权限、错误锁号、非管理身份、冻结项目和第二项失败的事务测试；失败后第一项和关系、后台任务、审计全部保持原值。
- [ ] 执行 `.venv/Scripts/python.exe -m pytest tests/module_shot_grid/test_force_delete_service.py -q`，确认新能力缺失引起失败。
- [ ] 实现项目协调锁和统一锁序，在事务内冻结完整目标图；解绑 `sg_shot_asset` 及对应资产需求关系，审计保留解除关系的 ID。资产处理全部未删除分项，包括归档分项；镜头不调用编号同步。
- [ ] 对目标未完成提交、目录操作、最终交付及媒体任务设置已有失败终态、清空租约/重试时间并递增 attempt；按各表 CHECK 同步错误及完成时间字段。已成功/已 committed 历史不改写。共享父目录及场级重编号操作不按目标 ID 简单整笔取消，保留其他实体操作并阻止删除目标的后续回写；必要时在原操作的目标处理环节跳过已删除目标。
- [ ] 在后台领取、续租、完成、失败、手动重试和正式提交处复核目标存活及 fencing。结果事务统一先取得项目协调锁，之后复核所有权；禁止长事务包住 NAS I/O。
- [ ] 为两种 I/O 交错顺序编写 PostgreSQL 测试：删除先提交时旧回写无效；Worker 先完成时删除随后完整生效。覆盖目录、版本提交、最终交付、媒体；用可控事件屏障替代 sleep。失败重试不能重新激活目标。
- [ ] 测试混合审核批次保留其他成员可审核，已删除目标不阻塞批次完成、不自动通过其他目标；读查询过滤删除任务，历史审核动作和候选保留。
- [ ] 增加 `shot.forceDelete`、`asset.forceDelete` 的 allowedActions 投影，与写事务的动作权限、管理范围和项目可写条件一致；只对尚未删除且可操作实体返回。
- [ ] 验证任务、版本、审核、搜索、文件中心及直接下载路径不能绕过已删除业务的可见性；平台文件引用保留，已有路径占用检查不放开。
- [ ] 运行新增三个测试文件及既有镜头/资产 CRUD、版本提交、审核、四类 Worker 定向回归；PostgreSQL 测试设置 `SHOT_GRID_RUN_PG_TESTS=1`。输出 skipped 时记录未执行，不计通过。

## 任务 3：单个与批量前端操作

**文件（相对 `shot-grid-frontend/`）：** 新建 `src/components/ForceDeleteDialog.vue` 和 `tests/unit/forceDeleteDialog.spec.js`、`forceDeleteActions.spec.js`；修改 `src/api/shot-grid/{shots,assets}.js`、`src/views/shot/{ShotListView,ShotDetailView}.vue`、`src/views/asset/{AssetListView,AssetDetailView}.vue`。

**接口：** `batchForceDeleteShots(projectId, items, reason)` 与 `batchForceDeleteAssets(projectId, items, reason)` 走原 Axios 实例，保持 ID 字符串精度。组件 props：`modelValue: boolean`、`entityType: 'shot'|'asset'`、`items: Array`、`loading: boolean`；事件 `update:modelValue`、`confirm({ reason })`。父组件保存 projectId 与选中项快照、发请求及刷新。

- [ ] 先写交互测试：无新权限隐藏入口；普通删除权限不出现强删；强删权限且 allowedActions 命中时所有制作阶段可操作；资产批量只使用父资产选择，不把子分项 ID 当资产 ID。
- [ ] 执行 `npm.cmd test -- tests/unit/forceDeleteDialog.spec.js tests/unit/forceDeleteActions.spec.js`，确认新增行为缺失后实现。
- [ ] 增加独立危险操作入口及共享弹窗。ElForm 的 model、rules、FormItem prop 和 validate 必须真实工作；原因必填，提交中禁用，失败保留原因与选择，关闭重置校验。文案明确文件保留、资产解绑和镜头编号不变。
- [ ] 单个复用一项目标的批量接口；混合选择中有任何不可强删项则禁止整批提交，显示原因，不静默丢弃。详情删除成功返回所属列表，列表成功刷新并清除对应选择。
- [ ] 测试空白原因拒绝、有效原因仅请求一次、loading 防重、请求失败、切项目、关闭重开及迟到响应；项目变化时关闭并清空旧弹窗，过期响应不能修改新页面。
- [ ] 重跑上述测试及现有 `assetViews.spec.js`、直接相关镜头页面测试；检查本次修改组件无原生 submit 依赖。不要修改现有未提交的 ShotImportDialog。

## 任务 4：契约同步与集成验收

**文件：** 修改 `ruoyi-fastapi-backend/AGENTS.md`、`shot-grid-frontend/AGENTS.md`、`shot-grid-frontend/docs/领域模型与API契约.md`；新建 `docs/superpowers/plans/2026-10-13-shot-asset-force-delete-verification.md`。

- [ ] 同步路由、权限、请求、错误、事务、后台失效、逻辑删除、文件保留及编号语义，明确这是一项新兼容扩展。
- [ ] 完成隔离 PostgreSQL 的菜单升级/降级、事务回滚、并发结果与授权撤销验证；先读取测试环境配置方式，不打印密码、不向实际业务库运行清理。
- [ ] 用隔离测试账号/项目验证镜头和资产各一条完整路径：授权→开工后强删→关联与待办刷新→撤权→后端拒绝。普通删除限制回归，文件保留；若只能使用业务浏览器会话，限只读检查，真实删除测试留在隔离环境。
- [ ] 运行改动 Python 文件 Ruff、前端改动文件 ESLint、相关 pytest/Vitest；因新增迁移和跨后台契约，在阶段结束集中运行后端完整测试、Shot Grid 完整 lint/test 与一次 `npm.cmd run build:prod`。既有失败区分基线与本次引入，不反复运行已通过的相同检查。
- [ ] 执行 `git diff --check` 和 `git status --short`，逐文件核对修改归属，确保未包含 env、输出、密钥或用户无关改动。
- [ ] 记录实际命令、成功、失败、跳过、未运行项，分别说明静态检查、单测、真实 PostgreSQL、浏览器和 NAS 的证据级别；完成代码评审后交付，未经授权不提交、推送或部署。

## 计划自检

设计的权限、删除语义、关联关系、文件保留、并发、共享目录、审核、前端、迁移及撤权要求均有对应任务。任务 1 的路由依赖任务 2 的 Service，两者合并到同一可用阶段再验收；不能把只有菜单的状态作为可交付功能。五项评审重点均落入具体测试。当前仅完成设计与计划，尚无测试通过或功能实现结论。


## 执行记录与裁定

- 沿用当前工作区，保留所有已有修改；未创建工作树、未提交、未部署。
- 将弹窗与入口合为 `ForceDeleteAction.vue`，组件持有目标快照与上下文代次，四个页面复用；这是减少重复编排的局部实现选择，不改变接口。
- 复用现有 Worker 的 owner + attempt 条件回写；删除事务统一失效凭据，未另建取消状态。真实 PG 测试覆盖目录、最终交付、媒体的旧凭据以及待提交版本终止；尚未穷举双事务交错和真实 SMB。
- 保留自动审核唯一关系；人工审核关系解绑写审计，加入及激活过滤逻辑删除任务。独立评审发现的三个问题均已修复。
- 服务端身份请求每次读取 UserDao 当前角色菜单；未引入新的权限缓存。真实浏览器授权/撤权旅程尚未执行。
- 验证记录：`2026-10-13-shot-asset-force-delete-verification.md`。不将以下尚未完成的全量门禁、真实浏览器或 NAS 验收勾选为通过。
