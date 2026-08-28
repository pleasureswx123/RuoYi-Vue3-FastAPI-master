# 未开工可改派规则实施计划

> 执行方式：在当前工作区按 `superpowers:executing-plans` 顺序实施，保留已有修改；使用 `superpowers:test-driven-development` 补充回归测试。本次不提交或推送代码。

**目标：** 镜头和资产制作分项仅在未开工时允许普通改派，开工后不显示入口且后端拒绝写入。

**设计：** 复用现有任务分配 Service、项目协调锁、目标及任务行锁、乐观锁和同事务审计。已有任务仅允许 `not_started` 改派；没有任务时仍可首次分配。前端以服务端 `allowedActions` 与平台权限的交集控制入口，批量操作保留整批回滚。

**技术栈：** Vue 3、Element Plus、Pinia、Axios、FastAPI、SQLAlchemy Async、PostgreSQL。

**确认依据：** 用户确认“未开工可改派，开工后禁止普通改派”；正式规则同步到《领域模型与API契约》和前后端 AGENTS.md。

## 约束

- `preparing/in_progress/pending_review/revision/completed` 全部禁止普通改派，包括管理人员。
- 保留项目范围、成员有效性、平台权限、存储状态、生命周期、任务锁版本和非 committed 提交门禁。
- 不重置已开工任务，不修改已有负责人或版本历史，不新增任务交接能力。
- 批量目标包含不可分配任务时整体失败，不能跳过该目标并部分成功。
- 不改数据库结构；真实数据库测试只使用现有隔离临时库夹具。

## 1. 写入和动作投影

涉及后端 `task_service.py`、`shot_crud_service.py`、`asset_crud_service.py` 和 `asset_crud_dao.py`。

- [x] 扩展现有 Service 测试，覆盖两类任务的所有状态，以及任务、镜头、分项的动作投影。
- [x] 扩展现有 PostgreSQL 开工测试，验证开工后父资产和子分项不可分配、混合状态批量回滚。
- [x] 运行相关测试并确认旧实现会违反新规则。
- [x] 分配写入在任务锁版本核对后使用 `task.task_status != 'not_started'` 拒绝已开工任务，返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。
- [x] 任务投影只接受 `not_started`；镜头及分项投影接受无任务或 `not_started`；父资产 SQL 阻断条件改为存在非 `not_started` 任务。
- [x] 重跑后端 Service、DAO、Router 和隔离 PostgreSQL 定向门禁。

## 2. 前端入口和说明

涉及 `ShotListView.vue`、`AssetListView.vue`、两类原有分配弹窗以及 `shotViews.spec.js` / `assetViews.spec.js`。

- [x] 镜头列表和批量选择不再在缺少 `allowedActions` 时放行；测试覆盖无权限投影和已开工时隐藏入口、取消选择。
- [x] 调整旧测试中“制作中仍可改派”的夹具；保留待开工改派成功及锁版本提交验证。
- [x] 分配弹窗和批量错误文案明确仅未开工可改派。
- [x] 同步正式需求、API 契约和前后端协作规则。
- [x] 运行直接相关前端测试、改动文件 ESLint、Ruff 和 diff 检查。
- [x] 使用浏览器只读核验已开工分项不显示改派、未开工分项仍显示，测试不修改用户业务数据。


## 本次验证结果

- 后端相关 Service / DAO / Router 测试：194 passed。
- 隔离 PostgreSQL 改派测试：9 passed，覆盖父子动作投影、两类任务混合批量回滚、开工后携带最新锁版本仍拒绝改派；全部随机测试数据库均清理完成。
- 前端直接相关测试分两组运行：21 passed 和 4 passed。覆盖按钮显隐、待开工改派原任务、任务锁版本、批量选择、刷新移除选择及详情入口。
- 改动范围 Ruff check、Ruff format --check、ESLint 和 git diff --check 通过。
- 真实资产页面：翱天舱室内主视角为制作中，仅显示分项详情；反打视角为待开工，保留改派任务；父资产不可批量勾选。没有提交、删除或开始任何用户业务任务。
- 较大范围前端回归曾出现两项失败：本次调整夹具导致的轮询预期已修正并重新通过；另一项既有资产标签样式断言期望 effect=light，而当前组件为 effect=dark，本次不改动用户现有样式。该较大范围运行也跳过了已知的冻结目录拖拽用例，并存在既有 el-dialog 解析和生产履历网络告警，不代表完整前端测试通过。
- 未运行完整 E2E、生产构建；未提交或推送代码。

### 实际命令

后端目录：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/module_shot_grid/test_task_service.py tests/module_shot_grid/test_asset_crud_service.py tests/module_shot_grid/test_shot_crud_service.py tests/module_shot_grid/test_task_router.py tests/module_shot_grid/test_asset_crud_dao.py -q --tb=short
$env:SHOT_GRID_RUN_PG_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/module_shot_grid/test_asset_manager_start_pg.py -k 'assignment' -q --tb=short
```

前端目录：

```powershell
node node_modules/vitest/vitest.mjs run tests/unit/assetViews.spec.js tests/unit/shotViews.spec.js --maxWorkers=1 --no-file-parallelism --reporter=dot -t '缺少改派权限投影|镜头行直接进入|镜头行分配操作|原生表格选择|列表自动刷新移除|切换立即清空表格选择|可将当前页选中的镜头批量分配|制作任务开始后详情页|树表子行的'
node node_modules/vitest/vitest.mjs run tests/unit/assetViews.spec.js tests/unit/shotViews.spec.js --maxWorkers=1 --no-file-parallelism --reporter=dot -t '树表后台刷新剔除|列表按分项目录准备状态|镜头任务改派仍完整展示'
node node_modules/eslint/bin/eslint.js src/views/asset/AssetListView.vue src/views/asset/components/AssetAssignDialog.vue src/views/shot/ShotListView.vue src/views/shot/components/ShotAssignDialog.vue tests/unit/assetViews.spec.js tests/unit/shotViews.spec.js
```

## 2026-08-28 提交前复核

本次复核同时覆盖后续增加的开工时间范围、时间提醒和列表操作调整；以上记录保留为改派阶段的历史验证。

- 后端七个相关测试文件：284 passed；范围包含资产 DAO/Service、镜头 Service、任务 Service/VO、迁移契约及版本提交 Service。
- `SHOT_GRID_RUN_PG_TESTS=1` 下完整运行 `test_asset_manager_start_pg.py`：41 passed，覆盖真实迁移、开工、改派、删除、并发和回滚；仅使用自动清理的随机隔离数据库。
- 前端 `assetViews/shotViews/taskViews/taskPresentation/errorViews`：193 passed、1 failed。失败项为“移动区间存在冻结目录时不提交重排”：既有模板已注释拖拽列，测试仍读取拖拽柄。已逐段核对失败用例与本次提交前 HEAD 完全相同，拖拽列也已在该 HEAD 中注释；本次不修改拖拽功能，不能将此结果称为前端测试全通过。
- 前端全量 ESLint、生产构建通过；保留已有大包告警。后端 Shot Grid 模块与测试 Ruff check、20 个改动 Python 文件的 Ruff format --check 通过。
- 未运行完整系统 E2E；环境配置、部署模板行尾差异、数据库备份、浏览器产物和 Excel 临时锁文件不属于本次提交范围。
