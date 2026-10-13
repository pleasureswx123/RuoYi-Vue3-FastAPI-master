# 镜头与资产强制永久删除实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有镜头、资产强制删除改为永久删除业务历史及独占文件，保持原按钮、权限和操作方式。

**核心使用场景（用户补充）：** 有问题的目标强制彻底删除后，在原作用域使用同一镜头号或资产名称重新新建并上传。只有旧业务、独占 NAS 文件清理成功且路径占用释放后才允许复用；新对象必须使用新 ID，不继承旧任务、版本或文件引用。这是最终验收主线。

**Architecture:** Controller → Service → DAO 负责权限、范围及原子业务图删除；同事务写独立目标清理队列。Leader 后台任务用租约和 owner + attempt fencing 消费清单，事务外执行 NAS I/O；前端显示实际清理状态。

**Tech Stack:** FastAPI、SQLAlchemy Async、PostgreSQL/Alembic、现有 Redis/Leader 调度、Vue 3、Pinia、Element Plus、Vitest。

**Spec:** `docs/superpowers/specs/2026-10-13-force-delete-permanent-design.md`（用户已要求进入实施计划）。

## 全局约束

- 不增加删除模式、额外按钮或第二套权限；继续使用 `shotgrid:shot:forceDelete`、`shotgrid:asset:forceDelete`。
- 保持原因 1..500 字、每批 1..200 个不重复目标、lockVersion、项目范围及生命周期门禁。
- 不恢复或追溯清理此前逻辑删除的目标；但本次选中目标下的历史逻辑删除子记录必须纳入清理。
- 只保留最小操作审计和清理证据，保护其他业务引用及共享 NAS 父目录。
- 不在数据库事务中等待 NAS；没有真实文件清理证据不得报告文件已清理。
- 本地业务库已升级至 20261013_39；实施前重新核对 head，新迁移接续实际 head，禁止覆盖他人新增迁移。
- 不提交、推送或部署，除非用户另行授权。保留已有 env、部署、导入及其他工作区改动，不整库格式化。
- 默认在当前会话逐项实施；此计划本身不执行数据库升级或真实业务删除。

## 重点评审风险与归属

1. 目标存在历史软删除任务/分项：任务 2 必须证明完整删除且不影响相邻目标。
2. 两个目标共享审核单、平台文件或 NAS 父目录：任务 2、4 必须证明保留其他目标资源。
3. SMB 仍在运行但租约过期：任务 3、4 不得将“失去租约”视为 I/O 已终止，无法证明静默时拒绝清理。
4. 删除后立刻重建同名目标或重编号复用旧路径：任务 3 保持持久路径占用，任务 4 证明旧队列不能删除新对象。
5. Worker 关闭、刷新页面或项目被整体删除：任务 4、5 必须保留真实状态，失败可诊断，不能假报完成。

## 任务 1：建立独立目标清理模型与迁移

**文件**
- 新增 `ruoyi-fastapi-backend/module_shot_grid/entity/do/target_purge_do.py`
- 新增 `ruoyi-fastapi-backend/module_shot_grid/entity/vo/target_purge_vo.py`
- 新增 `ruoyi-fastapi-backend/module_shot_grid/dao/target_purge_dao.py`
- 新增 `ruoyi-fastapi-backend/alembic/versions/2026_10_13_1600-20261013_40_target_purge.py`（实施前检查版本号未占用）
- 修改 `ruoyi-fastapi-backend/sql/ruoyi-fastapi-pg.sql`
- 新增 `ruoyi-fastapi-backend/tests/module_shot_grid/test_target_purge_pg.py`

**接口与模型**
- `ShotGridTargetPurge`：purge_id、project_id、target_kind（shot/asset）、target_id、target_label、root/project 路径快照、清单 JSON、purge_status、attempt_count、lease_owner/until、next_retry_time、安全错误键、操作者/原因/时间。project/target 标识不设依赖业务对象存活的外键。
- 状态使用 `pending/processing/retry_wait/succeeded/failed`；清单内容由服务端生成，客户端不能指定路径。
- `ShotGridTargetPurgePath`：规范化路径占用，关联 purge_id；非成功清理保持占用，成功后释放。目录祖先/子孙冲突也必须检查，不能只依赖字符串相等。
- `ShotGridTargetPurgeStatusModel`：purgeId、targetKind、targetId、targetLabel、purgeStatus、可公开错误信息、canRetry；不返回内部凭据或完整私有根路径。

- [ ] 先写隔离 PG 迁移测试：从 39 升级、创建清理记录后删除业务对象记录仍保留、非法状态拒绝、往返降级无待处理任务时成功。
- [ ] 运行 `SHOT_GRID_RUN_PG_TESTS=1` 下 `pytest tests/module_shot_grid/test_target_purge_pg.py -q`，确认预期缺失实现失败。
- [ ] 实现模型、迁移与初始化 SQL；存在未完成清理记录时降级拒绝，避免丢失待删文件清单。
- [ ] 重跑通过，检查 Alembic 单 head；不把隔离库迁移自动应用到业务库。

## 任务 2：按目标永久删除业务图与文件引用

**文件**
- 修改 `module_shot_grid/dao/force_delete_dao.py`、`service/force_delete_service.py`（均在后端目录下）
- 新增 `module_shot_grid/dao/target_purge_graph_dao.py`
- 修改 `tests/module_shot_grid/test_force_delete_pg.py`
- 新增 `tests/module_shot_grid/test_target_purge_graph_pg.py`

**接口**
- `lock_target_graph(db, project_id, kind, target_ids) -> TargetPurgeGraph`：返回目标及全部子对象 ID 集合，不按 del_flag 过滤子记录。
- `prepare_cleanup_manifest(db, graph, actor, now) -> TargetCleanupManifest`：记录独占 NAS 路径、平台文件、共享保留项；结构定义在 target_purge_vo.py，路径绝不来自请求。
- `delete_target_graph(db, graph) -> dict[str, int]`：按 RESTRICT 外键逆拓扑删除，返回各类删除数量，不提交事务。
- Service 保持当前 `batch_delete_shots/assets` 方法，事务内调用上述接口并创建每目标清理记录，最终一次 commit。

- [ ] 以 `project_purge_dao.py:delete_project_graph/prepare_exclusive_files` 为范围参考，逐项核对 DO 外键和 `SysFileReference.business_type/business_id`，记录到领域契约；不得复制 project_id 全范围删除条件。
- [ ] 写失败用例：历史软删除子对象、版本候选互相引用、问题回复与审核动作、空自动单、非空混合人工单、共享平台附件、相邻镜头和资产均不受影响。
- [ ] 使用至少两个项目、两个目标的真实 PG fixtures；预置实际文件引用，断言删除目标完整消失、其他数据精确不变、队列和审计存在。
- [ ] 按锁定 ID 集合实现删除；先置空版本 selected_candidate_id 再删除候选；镜头资产需求按设计分别删除或解除匹配。项目级导入批次不整批删。
- [ ] 平台文件移除目标引用后仍有引用或保留策略禁止清理时保留；独占文件按现有文件服务不可再次绑定的状态入队，不绕过其策略。
- [ ] 注入审计/入队失败，断言业务图与引用整体回滚；跑 `pytest tests/module_shot_grid/test_target_purge_graph_pg.py tests/module_shot_grid/test_force_delete_pg.py -q`。

## 任务 3：阻止在途写入、路径重用及队列竞态

**文件**
- 修改 `dao/target_purge_dao.py`、`service/force_delete_service.py`
- 检查并按需修改 `dao/storage_operation_dao.py`、`dao/version_submission_dao.py`、`dao/final_delivery_dao.py`、`dao/media_derivation_dao.py`
- 修改路径创建入口 `service/shot_crud_service.py`、`service/asset_crud_service.py`、`service/storage_management_service.py`；沿调用链覆盖导入、重编号及任务开工的路径创建。
- 新增 `tests/module_shot_grid/test_target_purge_concurrency_pg.py`

**接口**
- `assert_targets_quiescent(db, graph) -> None`：存在 publishing/committing/processing/compensation_pending 等真实执行状态时抛 409 `SG_TARGET_PURGE_RUNTIME_ACTIVE`，过期租约也不直接允许删除。
- `assert_paths_available(db, project_id, paths) -> None`：在项目锁内检查路径祖先/后代占用，冲突抛 409 `SG_TARGET_PURGE_PATH_RESERVED`。

- [ ] 写双会话测试，交错执行 Worker 领取与删除；断言不能在目标已删除后领取，或删除因先领取而拒绝。
- [ ] 写执行状态租约过期仍拒绝、同名创建/导入/重编号拒绝复用的失败用例。
- [ ] 统一项目协调锁与目标运行记录锁的顺序；锁等待后重查，避免先查状态后删除窗口。
- [ ] 保持旧 I/O 不可硬杀的事实；失去执行状态但无法证明任务退出的恢复流程必须阻止清理，留待管理员诊断，不能自动假定安全。
- [ ] 跑 `pytest tests/module_shot_grid/test_target_purge_concurrency_pg.py -q`，证明相邻目标可正常写入且没有扩大锁范围为 NAS I/O 长事务。

## 任务 4：目标级文件清理 Worker

**文件**
- 新增 `service/target_purge_path_adapter.py`、`service/target_purge_worker_service.py`
- 修改 `dao/target_purge_dao.py`、`module_task/shot_grid_storage_task.py`
- 修改 `service/project_purge_service.py`：存在未完成目标清理时拒绝项目整体清理，防止两个队列并发处理同路径。
- 新增 `tests/module_shot_grid/test_target_purge_path_adapter.py`、`test_target_purge_worker.py`
- 修改 `tests/module_task/test_shot_grid_storage_task.py`

**接口**
- `TargetPurgePathAdapter.cleanup(context: TargetCleanupManifest) -> CleanupResult`：只操作服务端冻结的清单；返回已清理和受保护项。
- `ShotGridTargetPurgeWorkerService.run_once(...)`、`run_scheduled_batch(...)`：采用 project_purge_worker_service 的 session_factory/path_adapter/租约参数约定。
- DAO 提供 claim_next、renew_lease、mark_succeeded、mark_retry_wait、mark_failed；所有回写校验 owner、attempt 和有效租约。

- [ ] 写失败用例：越界路径、项目/场次/资产分类根目录、共享目录、符号链接、未实际挂载 CIFS、清理一半中断、路径已不存在。
- [ ] 写 Worker 用例：失租不回写、心跳失败、重复消费、平台文件仍有其他引用、项目整体清理被阻止。
- [ ] 实现短事务领取 → 事务外 I/O → 短事务回写，沿用现有 NAS 服务器/挂载与平台文件根解析；不同目标的清单不能互相包含。
- [ ] 对清单逐项幂等处理；先后失败均不报告全部成功；成功后原子释放路径占用。保留现有重试次数和退避约定，不引入另一套配置。
- [ ] 接入现有存储调度任务，遵循 PostgreSQL、Worker 开关和 Application Leader 门禁，不增加可由用户编辑的 sys_job。
- [ ] 跑 `pytest tests/module_shot_grid/test_target_purge_path_adapter.py tests/module_shot_grid/test_target_purge_worker.py tests/module_task/test_shot_grid_storage_task.py -q`。

## 任务 5：接口清理状态与原入口反馈

**文件**
- 修改后端 `controller/shot_crud_controller.py`、`controller/asset_crud_controller.py`、`entity/vo/shot_crud_vo.py`、`entity/vo/asset_crud_vo.py`
- 新增后端 `controller/target_purge_controller.py`、`service/target_purge_service.py`、`tests/module_shot_grid/test_target_purge_router.py`
- 修改前端 `src/components/ForceDeleteAction.vue`、`src/api/shot-grid/shots.js`、`src/api/shot-grid/assets.js`
- 新增前端 `src/api/shot-grid/targetPurges.js`、`src/components/TargetPurgeStatus.vue`
- 修改镜头/资产 ListView，在行删除导致卸载后由页面级状态组件承接清理提示。
- 修改 `tests/unit/forceDeleteAction.spec.js`，新增 `tests/unit/targetPurgeStatus.spec.js`

**接口**
- 批量结果新增 `purges: ShotGridTargetPurgeStatusModel[]`，保留既有 deleted* 字段。
- `GET /shot-grid/projects/{projectId}/target-purges`：按 targetKind、purgeId、状态筛选，标准分页；后端同时限制项目访问与对应强删权限，禁止借 kind 查看另一类记录。
- `POST /shot-grid/projects/{projectId}/target-purges/{purgeId}/retry`：只允许 failed/retry_wait，锁内重新校验权限和范围，返回最新状态；不接受客户端路径。
- `TargetPurgeStatus` 使用 ElAlert/ElTable 和现有 Axios，页面加载后查询未完成项；清理完成停止轮询，切项目/卸载中止旧请求。重试按钮为清理失败恢复入口，不是第二种删除方式。

- [ ] 写失败测试：删除原因门禁不变；提示明确不可恢复；提交返回 pending 时显示“业务记录已删除，文件清理中”，不得提示删除全部完成。
- [ ] 补后端无权限/跨项目/另一实体权限拒绝、重复重试、Worker 关闭仍为 pending 的测试。
- [ ] 实现同一按钮的新语义：文案“将永久删除当前镜头（或资产）、制作历史及独占文件，此操作不可恢复”；保留原因和最终确认，不加模式选择。
- [ ] 页面级清理反馈证明目标行已卸载仍能查看结果、刷新后恢复待处理状态、失权停止查询与重试。
- [ ] 跑 `pytest tests/module_shot_grid/test_target_purge_router.py -q`；前端运行 `node node_modules/vitest/vitest.mjs run tests/unit/forceDeleteAction.spec.js tests/unit/targetPurgeStatus.spec.js --maxWorkers=1`。

## 任务 6：综合验证与交付记录

**文件**
- 更新后端/前端 `AGENTS.md`、`shot-grid-frontend/docs/领域模型与API契约.md`
- 新增 `docs/superpowers/plans/2026-10-13-force-delete-permanent-verification.md`

- [ ] 同步权限、事务、历史删除、独占/共享边界和清理状态契约，移除当前保留历史/NAS 的旧强删说明；保留历史验证记录并明确已被新语义替代。
- [ ] 后端用 `.venv/Scripts/python.exe` 执行本计划全部定向测试，PG 测试仅通过 `SHOT_GRID_RUN_PG_TESTS=1` 在随机隔离库执行；保留 skip、失败和缺依赖情况。
- [ ] 执行改动文件 Ruff、前端 ESLint、前端生产构建及 `git diff --check`；不重复与此次无关的全量失败诊断。
- [ ] 在用户本机 Chrome 验证表格强删弹窗打开/输入/取消，保留 `lock-scroll=false` 的滚动条宽度保护，不点击真实数据最终删除。
- [ ] 创建明确隔离的一次性目标与文件，在获准的测试存储执行永久删除，验证目标目录消失、共享文件保留、数据库业务图不存在、审计仍在；没有可用安全测试 NAS 时单列为未验证，不冒充上线验收。
- [ ] 对镜头和资产分别验证完整重建闭环：原目标先上传文件 → 强删进入清理中时同编号/同名创建被明确拒绝 → 清理成功 → 在原作用域同编号/同名创建成功且实体 ID 不同 → 重新分配/开工并以相同文件名上传成功，版本从新目标初始状态开始，NAS 无旧文件冲突或旧引用串入。失败重试和重复消费之后也必须通过此闭环。
- [ ] 升级说明包含数据库和文件备份、Worker 配置与权限检查、迁移命令、状态查询、失败重试及“降级不能恢复已删数据”。业务库迁移和部署必须作为后续明确动作，不隐式执行。

## 自审与实施顺序

依赖顺序为 1 → 2 → 3 → 4 → 5 → 6。中间任务完成不单独启用真实强删，待后台清理、路径占用和前端状态反馈一起完成再交付。

已覆盖设计中的原入口、完整业务图、共享保护、在途 I/O、同名复用、清理审计、失败重试、项目删除协调和不可恢复边界。执行中发现新业务引用必须先补范围及隔离测试，不允许按项目范围扩大删除来绕过外键。
