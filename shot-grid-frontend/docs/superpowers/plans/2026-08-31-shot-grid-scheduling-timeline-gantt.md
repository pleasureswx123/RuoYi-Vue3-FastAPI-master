# Shot Grid 项目排期双视图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**目标：** 在镜头、资产列表和项目深层路由中提供共用的人员泳道时间线与任务甘特图，让项目管理人员按自然时间安排任务、识别同负责人重叠并追踪当前排期相对首次基线的变化。

**架构：** 后端以 `sg_task` 当前排期和不可变首次基线为唯一事实源，新增结构化排期变更表、窗口化读模型和带幂等/乐观锁/重叠二次确认的写事务；前端以 Pinia 共享同一排期窗口，由 `ScheduleBoard` 在人员泳道与任务甘特之间切换，第三方甘特仅通过适配层提供开源核心渲染和水平拖拽。镜头、资产入口只施加目标类型筛选，项目排期页提供全量视角。

**技术栈：** Vue 3.5、Pinia 3、Vue Router 4、Axios、Element Plus 2、Vite 6、Vitest、`@svar-ui/vue-gantt@2.7.2`（MIT，仅 OSS 核心）、FastAPI、Pydantic 2、SQLAlchemy Async、PostgreSQL、Alembic、pytest。

**需求依据：** [项目排期双视图设计](../specs/2026-08-31-shot-grid-scheduling-timeline-gantt-design.md)、[领域模型与 API 契约](../../领域模型与API契约.md)、[项目需求规格与业务规则](../../项目需求规格与业务规则.md)。

## 全局约束

- 时间为无时区、秒精度的业务本地时间；自然日连续计算，周末和节假日均可排，提供日/周/月缩放。
- `expectedStartTime` 与 `expectedEndTime` 必须同时存在或同时为空，当前版本不允许清空已有排期；首次完整排期同时冻结基线，之后只修改当前排期。
- 默认只读；仅具备 `shotgrid:task:schedule` 且在项目内为 `director` 或拥有 `has_all_scope` 的管理人员可进入编辑模式。
- 同项目、同负责人、活动且未完成任务的半开区间重叠只警告；第二次请求必须携带服务端返回的完整冲突任务 ID 快照，变化后重新确认。
- 拖拽只允许水平方向移动或调整起止时间，禁止跨泳道改负责人；人员调整继续使用已有分配/改派流程。
- 不实现跨项目负载、工时容量、依赖关系、关键路径、自动排程、工作日历或伪造进度百分比。
- Element Plus 继续承载筛选、按钮、弹窗、抽屉、表单、空态、加载与提示；排期编辑表单使用 `ElForm` / `ElFormItem`、显式 `@click` 和 `validate()`，不得使用原生 submit 链。
- 第三方甘特限制在 `ScheduleGanttAdapter` 内；不使用 SVAR PRO 的 baseline、resource management、working calendars、critical path 或 auto scheduling。
- 保留工作区已有非本功能改动；只暂存本计划列出的明确文件，不推送远程。

## 任务 1：锁定 OSS 甘特依赖并建立适配层技术门禁

**文件：**

- 修改：`shot-grid-frontend/package.json`
- 修改：`shot-grid-frontend/package-lock.json`
- 新增：`shot-grid-frontend/src/views/schedule/adapters/svarGanttAdapter.js`
- 新增：`shot-grid-frontend/src/views/schedule/components/ScheduleGanttAdapter.vue`
- 新增：`shot-grid-frontend/tests/unit/scheduleGanttAdapter.spec.js`

**步骤：**

1. 先写失败测试，固定适配器输入为 `{ tasks, scale, readonly }`，输出事件仅允许 `task-click`、`range-change-request`；验证只读模式不发写事件、垂直移动不改变 `assigneeUserId`、日/周/月映射为自然时间刻度。
2. 执行 `npm.cmd test -- tests/unit/scheduleGanttAdapter.spec.js --reporter=dot`，确认测试因适配层缺失而失败。
3. 安装并锁定 `@svar-ui/vue-gantt@2.7.2`；组件和样式仅在适配器中动态导入，页面其他组件不得直接依赖其 API。
4. 将当前排期转换成 SVAR task 数据；基线、冲突标记和只读态使用项目自有 class/overlay 表达，不调用 PRO API。对第三方回调统一换算为秒精度本地时间，并拒绝负责人变化。
5. 增加包含 5,000 任务、当前窗口 2,000 条、200 泳道的纯转换基准测试，记录转换时间和输出数量；DOM 性能在任务 11 的真实页面门禁验证。
6. 重跑适配器测试和 `npx.cmd eslint` 对应文件，确认依赖可由 Vite 懒加载构建。

## 任务 2：新增排期基线、变更审计和权限迁移

**文件：**

- 新增：`ruoyi-fastapi-backend/alembic/versions/2026_08_31_1800-20260831_25_add_task_scheduling.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/entity/do/task_do.py`
- 新增：`ruoyi-fastapi-backend/module_shot_grid/entity/do/task_schedule_change_do.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/entity/do/__init__.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/schema.py`
- 修改：`ruoyi-fastapi-backend/sql/ruoyi-fastapi-pg.sql`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/service/project_purge_service.py`
- 修改：`ruoyi-fastapi-backend/tests/module_shot_grid/test_migration_contract.py`
- 修改：`ruoyi-fastapi-backend/tests/module_shot_grid/test_schema_metadata.py`
- 修改：`ruoyi-fastapi-backend/tests/module_shot_grid/test_project_purge_service.py`

**步骤：**

1. 先扩展迁移和 metadata 测试：`sg_task` 增加成对基线字段；`sg_task_schedule_change` 具有设计文档规定的外键、JSONB、请求哈希、结果快照和 `(task_id, operator_user_id, idempotency_key)` 唯一约束；权限种子新增 `shotgrid:task:schedule`。
2. 先写永久删除测试，断言变更历史在任务之前显式删除且独立清理审计仍保留。
3. 执行上述三个测试文件，确认新增约束和删除顺序在原实现上失败。
4. 实现 revision `20260831_25`：仅 PostgreSQL 执行；已有完整 expected range 复制到 baseline，不生成历史行、不改变任务状态/负责人/锁版本/审计时间；增加排期窗口、冲突和历史查询索引。
5. 降级在任何基线或排期变更历史存在时显式失败，避免静默丢失；空数据时按外键逆序清理。
6. 同步 SQLAlchemy DO、`schema.py` 与 PostgreSQL 初始化 SQL；在项目永久删除业务图中先删 `sg_task_schedule_change` 再删 `sg_task`。
7. 运行迁移契约、metadata、purge 测试及 `python -m alembic heads`，唯一 head 必须为 `20260831_25`。

## 任务 3：定义排期 VO、时间规则与读模型契约

**文件：**

- 新增：`ruoyi-fastapi-backend/module_shot_grid/entity/vo/task_schedule_vo.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/entity/vo/__init__.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/entity/vo/task_vo.py`
- 新增：`ruoyi-fastapi-backend/tests/module_shot_grid/test_task_schedule_vo.py`
- 修改：`ruoyi-fastapi-backend/tests/module_shot_grid/test_task_vo.py`

**步骤：**

1. 先写 Pydantic 失败测试：查询窗口 `windowStart < windowEnd`、无时区、无微秒；`pageSize <= 1000`；`targetKind=all|shot|asset_item`；`groupBy=assignee|task_kind|status|episode|scene|asset_type`；写请求禁止部分时间、清空和非法来源。
2. 定义 `ShotGridScheduleQueryModel`、`ShotGridSchedulePageModel`、`ShotGridScheduleTaskModel`、`ShotGridScheduleGroupModel`、`ShotGridScheduleUpdateModel`、`ShotGridScheduleConflictModel`、`ShotGridScheduleChangeModel` 与未排期响应模型。
3. 所有响应字段保持 camelCase alias；日期序列化为 `YYYY-MM-DDTHH:mm:ss`，不附加 `Z` 或偏移。
4. 为任务列表/详情增加只读基线字段，保持既有 expected 字段兼容；开工 VO 改为：已有排期时允许省略时间，未排期时仍要求未来完整区间。
5. 运行 VO 定向测试并通过 Ruff check/format。

## 任务 4：实现窗口查询、未排期、历史和冲突 DAO

**文件：**

- 新增：`ruoyi-fastapi-backend/module_shot_grid/dao/task_schedule_dao.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/dao/task_dao.py`
- 新增：`ruoyi-fastapi-backend/tests/module_shot_grid/test_task_schedule_dao.py`

**步骤：**

1. 先写 SQL 编译和 DAO 测试，覆盖：current 或 baseline 与窗口相交；目标类型和分组筛选；稳定 `(group sort, start, task_id)` 排序；最大 1,000 分页；未排期只返回真实活动任务。
2. 为冲突查询写测试，断言它不受当前 UI 筛选影响，只限制当前项目、同负责人、活动未完成任务，并使用 `[start, end)` 条件 `other.start < end AND other.end > start`。
3. 实现 `get_schedule_page()`、`get_unscheduled_page()`、`get_schedule_changes()`、`find_overlap_task_ids()`、`get_idempotency_result()`、`add_schedule_change()`；项目锁复用现有项目协调锁，任务锁使用 `FOR UPDATE`。
4. 查询只返回页面需要的任务、负责人、镜头/资产分项、episode/scene/asset type 摘要，不把 ORM 实体泄漏到 Controller。
5. 运行 DAO 定向测试，并对 PostgreSQL 方言编译结果断言索引可用的过滤/排序字段。

## 任务 5：实现排期写事务、幂等回放与开工兼容

**文件：**

- 新增：`ruoyi-fastapi-backend/module_shot_grid/service/task_schedule_service.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/service/task_service.py`
- 新增：`ruoyi-fastapi-backend/tests/module_shot_grid/test_task_schedule_service.py`
- 修改：`ruoyi-fastapi-backend/tests/module_shot_grid/test_task_service.py`
- 修改：`ruoyi-fastapi-backend/tests/module_shot_grid/test_asset_manager_start_pg.py`

**步骤：**

1. 先写服务失败测试：director/全范围管理员成功；creator、项目外管理人、归档项目、非活动任务、完成任务、锁冲突失败；首次排期冻结 baseline；后续只改 current；任务锁版本递增一次。
2. 写重叠双请求测试：首次返回 `SG_TASK_SCHEDULE_OVERLAP` 与有序冲突 ID；确认快照一致后保存；冲突集合变化时再次 409；边界相接不冲突。
3. 写幂等测试：同操作人、任务和幂等键 + 同请求哈希返回已保存 `result_snapshot`，不同哈希返回 `SG_IDEMPOTENCY_CONFLICT`；提交后网络重试不重复递增版本或写历史。
4. 实现固定锁序“项目协调行 → 任务”，锁内复核权限/范围/项目/任务/负责人/锁版本/时间/冲突；不在事务内执行 Redis、NAS 或其他外部 I/O。
5. 服务端从旧/新范围推导 `initial|move|resize_start|resize_end|dialog`，保存 source、reason、acknowledged、冲突快照、前后锁版本、SHA-256 与结果快照。
6. 开工兼容：已有排期时请求省略时间且不因已进入过去而阻断；未排期时要求未来完整区间，并在同一开工事务冻结首次基线、写 initial 历史；不得覆盖已有 baseline。
7. 运行服务单测与真实 PostgreSQL 定向测试；并发门禁至少覆盖同任务乐观锁和同幂等键唯一约束。

## 任务 6：交付排期 REST API 与权限边界

**文件：**

- 新增：`ruoyi-fastapi-backend/module_shot_grid/controller/task_schedule_controller.py`
- 修改：`ruoyi-fastapi-backend/module_shot_grid/controller/task_controller.py`
- 新增：`ruoyi-fastapi-backend/tests/module_shot_grid/test_task_schedule_router.py`
- 修改：`ruoyi-fastapi-backend/tests/module_shot_grid/test_task_router.py`

**步骤：**

1. 先写路由测试，固定以下接口与权限：
   - `GET /shot-grid/projects/{projectId}/schedule`
   - `GET /shot-grid/projects/{projectId}/schedule/unscheduled`
   - `GET /shot-grid/tasks/{taskId}/schedule-changes`
   - `PUT /shot-grid/tasks/{taskId}/schedule`，必填 `X-Idempotency-Key`
2. 读接口使用项目访问范围和 `shotgrid:task:list`/`query`；写接口同时要求 `shotgrid:task:schedule`，业务层再复核 director 或全范围管理能力。
3. 统一返回既有 `ResponseUtil` envelope；稳定错误键为 `SG_TASK_SCHEDULE_INVALID`、`SG_TASK_SCHEDULE_OVERLAP`、`SG_TASK_SCHEDULE_READ_ONLY`、`SG_OPTIMISTIC_LOCK_CONFLICT`、`SG_IDEMPOTENCY_CONFLICT`。
4. 验证静态 `/schedule/unscheduled` 位于任何可能捕获它的动态路径之前；运行路由和自动注册测试。

## 任务 7：建立前端排期 API、状态模型和请求隔离

**文件：**

- 新增：`shot-grid-frontend/src/api/shot-grid/schedules.js`
- 新增：`shot-grid-frontend/src/store/modules/schedule.js`
- 新增：`shot-grid-frontend/src/views/schedule/schedulePresentation.js`
- 新增：`shot-grid-frontend/tests/unit/scheduleApi.spec.js`
- 新增：`shot-grid-frontend/tests/unit/scheduleStore.spec.js`
- 新增：`shot-grid-frontend/tests/unit/schedulePresentation.spec.js`

**步骤：**

1. 先写 API 测试固定 URL、query 与 `X-Idempotency-Key`/`repeatSubmit:false`；写 Store 测试覆盖 query 状态、项目隔离、窗口 buffer、AbortController、generation 和迟到响应丢弃。
2. Store 保存 `mode`、`scale`、`groupBy`、`windowStart/End`、`targetKind`、筛选、分页、未排期数量和编辑态；切项目时清空任务、错误、选中项和冲突快照。
3. 读取当前窗口并向左右各扩展一个 viewport buffer；相同有效窗口去重，缩放/平移取消旧请求。
4. 展示层统一状态/优先级/任务类型/错误文案，禁止构造不存在的进度百分比；排期 409、锁冲突和只读错误给出可行动提示。
5. 运行三个定向测试文件与 ESLint。

## 任务 8：实现共享只读泳道、甘特、工具栏和详情抽屉

**文件：**

- 新增：`shot-grid-frontend/src/views/schedule/ScheduleBoard.vue`
- 新增：`shot-grid-frontend/src/views/schedule/components/ScheduleToolbar.vue`
- 新增：`shot-grid-frontend/src/views/schedule/components/PersonnelSwimlane.vue`
- 新增：`shot-grid-frontend/src/views/schedule/components/TaskGantt.vue`
- 新增：`shot-grid-frontend/src/views/schedule/components/ScheduleTaskDrawer.vue`
- 新增：`shot-grid-frontend/src/views/schedule/components/UnscheduledTaskDrawer.vue`
- 新增：`shot-grid-frontend/tests/unit/scheduleBoard.spec.js`

**步骤：**

1. 先写组件测试：默认只读；人员视角按负责人泳道分组并堆叠重叠条；任务视角显示当前条和首次基线；日/周/月切换更新 route query；点击任务打开抽屉。
2. 工具栏用 Element Plus Select/RadioGroup/Button/Form 实现视角、缩放、分组、时间窗口、筛选、回到今天、编辑模式和未排期入口。
3. `PersonnelSwimlane` 负责“谁在何时做什么”和重叠堆叠；`TaskGantt` 通过 adapter 渲染任务层级与基线 overlay；两者消费同一 Store 响应，不各自请求数据。
4. 详情抽屉展示当前排期、首次基线、负责人、状态、目标和最近变更；未排期抽屉独立分页，不生成虚拟负责人或空白任务。
5. 增加 skeleton、空态、错误重试、超 1,000 条分页提示和窄屏降级；运行组件测试与 ESLint。

## 任务 9：实现显式编辑、拖拽回滚和重叠二次确认

**文件：**

- 新增：`shot-grid-frontend/src/views/schedule/components/ScheduleEditDialog.vue`
- 新增：`shot-grid-frontend/src/views/schedule/useScheduleMutation.js`
- 修改：`shot-grid-frontend/src/views/schedule/ScheduleBoard.vue`
- 修改：`shot-grid-frontend/src/views/schedule/components/PersonnelSwimlane.vue`
- 修改：`shot-grid-frontend/src/views/schedule/components/TaskGantt.vue`
- 修改：`shot-grid-frontend/src/views/task/components/TaskStartDialog.vue`
- 修改：`shot-grid-frontend/src/views/task/useTaskStartDialog.js`
- 修改：`shot-grid-frontend/tests/unit/scheduleBoard.spec.js`
- 修改：`shot-grid-frontend/tests/unit/taskViews.spec.js`

**步骤：**

1. 先写交互测试：无权限不能进入编辑；进入编辑后只允许水平 move/resize；跨泳道动作被拒绝；弹窗按钮显式校验；保存中禁用；取消和失败恢复原时间。
2. `ScheduleEditDialog` 使用 `ElForm`，字段为起止时间、必填变更原因；按钮 `@click` 调用同一 `validate()` 处理函数，不出现 `<form>`、`@submit.prevent` 或 `native-type=submit`。
3. 每次写入生成独立幂等键；首次 overlap 409 显示冲突任务清单，确认后附带 `overlapAcknowledged=true` 和完整 `expectedConflictTaskIds` 重试；锁冲突/冲突集合变化则刷新任务并重新确认。
4. 拖拽采用 optimistic preview，但只在成功后提交 Store；取消、API 错误、generation 变化或组件卸载均回滚，保留弹窗原因草稿供重试。
5. 开工弹窗已有排期时只读展示且请求不携带时间；未排期时仍按既有规则录入未来范围，后端负责冻结基线。
6. 运行排期组件和开工交互测试，额外静态扫描本次表单作用域的原生 submit 违规。

## 任务 10：接入镜头、资产列表与项目深层路由

**文件：**

- 修改：`shot-grid-frontend/src/router/index.js`
- 修改：`shot-grid-frontend/src/router/routeRegistry.js`
- 新增：`shot-grid-frontend/src/views/schedule/ProjectScheduleView.vue`
- 修改：`shot-grid-frontend/src/views/project/ProjectDetailView.vue`
- 修改：`shot-grid-frontend/src/views/shot/ShotListView.vue`
- 修改：`shot-grid-frontend/src/views/asset/AssetListView.vue`
- 修改：`shot-grid-frontend/tests/unit/deepRoutes.spec.js`
- 修改：`shot-grid-frontend/tests/unit/routeRegistry.spec.js`
- 修改：`shot-grid-frontend/tests/unit/projectViews.spec.js`
- 修改：`shot-grid-frontend/tests/unit/shotViews.spec.js`
- 修改：`shot-grid-frontend/tests/unit/assetViews.spec.js`

**步骤：**

1. 先写失败测试：深层路由 `/projects/:projectId/schedule` 可直接进入；项目详情有排期入口；镜头列表新增人员泳道/任务甘特并强制 `targetKind=shot`；资产列表同样强制 `asset_item`；原三种视图保持不变。
2. `ProjectScheduleView` 懒加载 `ScheduleBoard`，不新增顶级菜单；route query 持久化 `mode/scale/groupBy/windowStart/windowEnd`，非法值使用稳定默认值并 replace 纠正。
3. 列表中的两种排期模式直接复用 `ScheduleBoard`，保留当前 `projectId` 上下文和已有筛选摘要；离开排期模式中止请求并释放大组件。
4. 项目详情增加“项目排期”按钮，权限不足仍可只读进入，只隐藏编辑能力而不是整个页面。
5. 运行路由与三类视图定向测试，并验证原表格/卡片/看板切换用例未回归。

## 任务 11：文档同步、性能与真实页面验收

**文件：**

- 修改：`ruoyi-fastapi-backend/AGENTS.md`
- 修改：`shot-grid-frontend/AGENTS.md`
- 修改：`shot-grid-frontend/docs/需求.md`
- 修改：`shot-grid-frontend/docs/项目需求规格与业务规则.md`
- 修改：`shot-grid-frontend/docs/领域模型与API契约.md`
- 修改：`shot-grid-frontend/docs/使用说明.md`
- 修改：`shot-grid-frontend/docs/superpowers/specs/2026-08-31-shot-grid-scheduling-timeline-gantt-design.md`（仅在实现事实与已冻结契约需要一致化时）

**步骤：**

1. 同步最终字段、权限码、路由、错误键、管理员操作步骤、自然时间规则、基线语义、重叠二次确认和明确不支持项；设计文档中不得把未验证能力写成已交付。
2. 后端最小门禁：排期 migration/metadata/DAO/service/router、任务开工和 purge 定向测试；对改动 Python 文件执行 Ruff check 与 format --check；执行 `python -m alembic heads`。
3. 前端最小门禁：排期 adapter/API/store/board、task/shot/asset/project/route 定向 Vitest，改动文件 ESLint；依赖与懒加载变更执行 `npm.cmd run build:prod`。
4. 使用本地 PostgreSQL/Redis 和真实页面验证一条核心旅程：项目排期只读打开 → 日/周/月缩放 → 人员/任务模式切换 → 管理员进入编辑 → 移动任务 → 重叠警告 → 二次确认 → 当前排期更新而基线不变 → 历史可见。未执行真实 NAS/版本发布时必须明确排除。
5. 在 5,000 总任务、2,000 当前窗口、200 泳道数据下记录首次渲染、缩放和平移的可用性；如未达到可交互门槛，优先缩小窗口/分页/虚拟化，不增加 PRO 依赖。
6. 执行 `git diff --check`、需求覆盖矩阵、占位符扫描和最终 `git status --short`；只暂存本功能文件。独立审查关闭 Critical/Important 后再声明完成，不自动 push。

## 需求覆盖与完成门禁

| 冻结需求 | 实施任务 | 完成证据 |
| --- | --- | --- |
| 人员泳道 + 任务甘特双模式 | 1、7、8、10 | 适配器/组件/入口测试与真实页面切换 |
| 按人员、任务及业务维度查看 | 3、4、7、8 | VO、DAO 分组查询与 Store/工具栏测试 |
| 自然时间、日/周/月 | 1、3、8 | 时间校验与刻度映射测试 |
| 首次基线不可变 | 2、5、8、9 | migration/service 测试及页面更新前后对比 |
| 管理员编辑、制作人只读 | 2、5、6、9 | 权限路由、服务和交互测试 |
| 重叠警告后二次确认 | 4、5、9 | 半开区间、快照变化和重试测试 |
| 三类入口共用同一事实源 | 7、10 | 路由及 project/shot/asset 视图测试 |
| 审计、幂等、乐观锁 | 2、5、6、9 | 唯一约束、回放、并发和失败回滚测试 |
| 性能与懒加载边界 | 1、7、10、11 | 转换基准、生产构建与窗口化页面验收 |

只有上述门禁均有实际证据、且未将静态/单测/构建误报为完整 E2E，才可将本功能标记为实现完成。
