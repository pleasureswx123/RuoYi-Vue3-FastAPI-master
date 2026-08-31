# Shot Grid 泳道时间线与甘特排期设计

## 1. 文档状态

| 项目 | 内容 |
| --- | --- |
| 状态 | 已完成业务确认，等待实施计划评审 |
| 确认日期 | 2026-08-31 |
| 适用范围 | `shot-grid-frontend` 与 `ruoyi-fastapi-backend/module_shot_grid` |
| 当前 PostgreSQL head | `20260828_24`；实施时必须从该 head 新增后继迁移 |
| 目标用户 | 项目管理人、具备全项目数据范围的管理员、制作人员 |
| 不代表 | 功能已实现、依赖已安装、迁移已执行、性能或 E2E 已通过 |

本文冻结 Shot Grid 项目排期的首版业务边界、数据模型、接口、权限、交互和验收口径。实施计划和代码不得用页面局部状态、第三方组件内部模型或旧 `dueDate` 替代本契约。

## 2. 背景与目标

现有镜头与资产列表已经具有表格、卡片和领域看板视图，也能展示任务的 `expectedStartTime/expectedEndTime` 与时间提醒，但仍缺少跨任务的时间关系、人员撞期、基线偏差和项目整体排期入口。

本次目标是：

1. 让业务方按人员查看“谁在什么时间做什么、是否撞期”。
2. 让业务方按任务查看“各项工作何时开始结束、当前计划偏离首版计划多少”。
3. 允许授权管理人员通过拖动、缩放或精确表单调整任务排期。
4. 保留首版排期基线和每次改期的结构化历史，支持项目进度监管。
5. 在镜头、资产局部列表和项目综合排期页之间复用同一领域/API 契约。

## 3. 已确认的现有事实

- `sg_task.expected_start_time/expected_end_time` 已由 `20260828_24` 建立，为可空、成对、秒级业务本地时间。
- 当前时间只在管理人员确认开工时写入；开工后的普通任务编辑不允许修改该时间范围。
- `due_date` 是结束日期的兼容筛选投影，不是精确排期事实。
- 任务状态仍由管理员确认开工、目录 Outbox、版本提交和审核动作驱动。
- 镜头任务唯一属于一个镜头，资产图片任务唯一属于一个资产制作分项；未委派对象没有 `sg_task`。
- 前端是独立 Vue 3/Vite/Pinia/Vue Router/Axios/Element Plus 应用，并已提交 `package-lock.json`。
- 项目、任务和目标对象均已有 `lockVersion` 与项目访问/数据范围门禁。
- 当前代码没有统一的项目排期读模型，也没有结构化的任务改期历史。

## 4. 首版范围

### 4.1 包含

- 人员泳道时间线。
- 任务甘特图。
- 按日、周、月缩放。
- 自然时间连续计算，周末和节假日均可排期。
- 按人员、任务类型、状态、集/场、资产类型等视角分组。
- 当前排期、首版基线、临期、逾期、基线偏差和人员重叠提示。
- 管理人员拖动、缩放、精确时间编辑、改期原因和冲突二次确认。
- 镜头局部排期、资产局部排期和项目综合排期。
- 排期乐观锁、幂等、同事务审计和结构化变更历史。

### 4.2 不包含

- 工时、每日工时、假期日历、人员容量、利用率和成本模型。
- 任务依赖、依赖连线、关键路径、里程碑门禁和自动顺延。
- 自动开工、自动完成、自动暂停、自动改派或自动平衡人员负载。
- 通过拖入其他泳道改变负责人。
- 虚构的任务完成百分比。
- 跨项目人员冲突；首版冲突只在当前项目内计算。
- 未委派镜头或资产分项的虚拟任务。必须先走现有委派流程生成真实 `sg_task`。
- 已有排期的“取消排期”动作；首版只能创建或调整完整时间范围。

## 5. 核心决策

### 5.1 双模式职责

| 模式 | 默认视角 | 主要回答的问题 |
| --- | --- | --- |
| 人员泳道 | 按负责人分组 | 谁在什么时间做什么、是否有同人撞期 |
| 任务甘特 | 按任务层级分组 | 哪些任务何时开始结束、当前排期相对基线偏离多少 |

两种模式共用筛选、日期窗口、日/周/月缩放、基线、冲突、未排期池和编辑流程，不建立两套数据源。

### 5.2 当前计划与首版基线

- `expected_start_time/expected_end_time` 继续表示当前排期。
- 任务第一次取得完整排期时，同时冻结首版基线。
- 基线一旦写入不可修改；后续改期只更新当前排期。
- 当前计划和基线均不驱动任务状态机。
- 基线不是版本审核的“最终版本”，二者属于不同业务概念。

### 5.3 人员重叠

- 同一项目、同一负责人、两个未完成活动任务的当前排期区间相交时产生冲突。
- 区间按半开区间 `[start, end)` 判断；前一任务结束等于后一任务开始不算重叠。
- 冲突只警告，不阻止管理人员保存。
- 保存前必须由后端返回最新冲突集合，前端二次确认后再提交。
- 不计算每日工时、并行容量或任务权重。

### 5.4 第三方渲染边界

采用 SVAR Vue Gantt 开源核心作为时间网格、任务条、拖拽、缩放和虚拟渲染基础，通过项目自有 `ScheduleGanttAdapter` 隔离。Element Plus 继续承担筛选、表单、按钮、抽屉、确认框、空态、加载与消息提示。

不采购或依赖 PRO 能力。人员分组、基线影子和冲突样式由适配层与自有任务模板实现。第三方组件不得成为领域状态、权限或审计事实来源；如果未来替换渲染库，后端契约和 `ScheduleBoard` 上层组件不应改变。

## 6. 总体架构

```text
镜头列表局部排期 ─┐
资产列表局部排期 ─┼─> ScheduleBoard
项目综合排期页 ───┘      ├─ ScheduleToolbar
                         ├─ ScheduleSwimlaneView
                         ├─ ScheduleGanttView
                         ├─ ScheduleTaskDrawer
                         ├─ ScheduleEditDialog
                         └─ ScheduleUnscheduledDrawer
                                  │
                         ScheduleGanttAdapter
                                  │
                         SVAR Vue Gantt OSS

前端 Axios
  -> schedule_controller
  -> schedule_service
  -> schedule_dao
  -> sg_task 当前计划/基线
  -> sg_task_schedule_change 结构化历史
  -> SysOperLog 同事务平台审计
```

后端继续遵循 Controller → Service → DAO → DO/VO。排期不得塞入镜头/资产页面控制器，也不得绕过项目访问依赖、`ResponseUtil`、统一异常和事务体系。

## 7. 数据模型

### 7.1 `sg_task` 增量字段

新增：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `baseline_start_time` | `timestamp(0) without time zone` | 首版排期开始，首次写入后不可修改 |
| `baseline_end_time` | `timestamp(0) without time zone` | 首版排期结束，首次写入后不可修改 |

约束：

```sql
CHECK (
  (baseline_start_time IS NULL AND baseline_end_time IS NULL)
  OR
  (baseline_start_time IS NOT NULL
   AND baseline_end_time IS NOT NULL
   AND baseline_end_time > baseline_start_time)
)
```

业务规则：

- 当前排期仍使用既有 `expected_start_time/expected_end_time`。
- 首次排期时，当前范围和基线范围在同一事务写入同一个值。
- 后续更新不得改变基线。
- 当前排期结束时间变化时，同事务把 `due_date` 同步为结束日期。
- 首版不允许把已有当前排期清空。

### 7.2 `sg_task_schedule_change`

新增只追加的结构化历史表：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schedule_change_id` | bigint | 主键 |
| `project_id` | bigint | 项目 ID |
| `task_id` | bigint | 任务 ID，与项目组成复合外键 |
| `operator_user_id` | bigint | 操作人用户 ID，用于稳定授权与幂等范围 |
| `from_start_time/from_end_time` | timestamp(0) | 修改前范围；初次排期时成对为空 |
| `to_start_time/to_end_time` | timestamp(0) | 修改后完整范围 |
| `change_type` | varchar(20) | `initial/move/resize_start/resize_end/dialog`；由后端根据前后值规范化 |
| `operation_source` | varchar(20) | `start/swimlane/gantt/dialog`；仅作来源审计 |
| `change_reason` | varchar(500) | 非空改期原因；初次排期可使用固定“首次排期” |
| `overlap_acknowledged` | boolean | 是否确认过重叠 |
| `overlap_task_ids` | jsonb | 当次确认的冲突任务 ID 有序快照 |
| `task_lock_version_before/after` | integer | 修改前后任务版本 |
| `idempotency_key` | varchar(128) | 幂等键 |
| `request_hash` | varchar(64) | 规范化命令 SHA-256，用于识别同键不同命令 |
| `result_snapshot` | jsonb | 首次成功结果安全快照，供原样重放 |
| `create_by/create_time` | 通用审计类型 | 操作人和操作时间 |

约束：

- `to_start_time/to_end_time` 必须成对且结束严格晚于开始。
- `from_start_time/from_end_time` 必须成对为空或成对有效。
- 同一 `task_id + operator_user_id + idempotency_key` 唯一。
- 记录不提供普通更新和删除 API。
- 项目永久删除业务图时，必须在删除任务前显式清理该项目的排期历史；不得依赖无边界级联。

建议索引：

```text
(project_id, task_id, create_time DESC, schedule_change_id DESC)
(project_id, create_time DESC)
```

### 7.3 冲突查询索引

为活动任务时间窗口查询增加 PostgreSQL 索引，至少覆盖：

```text
(project_id, assignee_user_id, expected_start_time, expected_end_time, task_id)
WHERE del_flag = '0' AND expected_start_time IS NOT NULL
```

最终是否采用普通 B-tree 或额外范围表达式索引，必须以真实 `EXPLAIN (ANALYZE, BUFFERS)` 决定，不在设计阶段承诺未经验证的索引收益。

## 8. 迁移与历史数据

实施时从 `20260828_24` 新增后继 PostgreSQL Alembic revision，并同步 `ruoyi-fastapi-backend/sql/ruoyi-fastapi-pg.sql`。

迁移规则：

1. 增加基线字段和历史表。
2. 对当前已有完整 `expected_start_time/expected_end_time` 的任务，把同一范围复制到基线字段。
3. 当前无完整排期的任务保持基线为空，不回填虚构日期。
4. 迁移不创建伪造的排期变更记录，因为无法证明历史操作人、原因和时间。
5. 迁移不修改任务状态、负责人、锁版本、创建/更新时间或已有 `due_date`。
6. 降级若存在基线或排期历史必须失败关闭，要求先备份并显式处理数据。

此前系统没有开工后改期入口，因此迁移时“当前排期复制为基线”是现有数据能够支持的最强事实；文档和 UI 必须把这类记录说明为“迁移时冻结的现有计划”，不能伪造原始操作历史。

## 9. 权限与状态门禁

### 9.1 权限

- 读取项目排期：`shotgrid:task:list` + 项目访问范围。
- 修改排期：新增 `shotgrid:task:schedule`。
- 修改者必须同时是当前项目 `director`，或具备 `has_all_scope` 管理范围。
- 制作人员只读查看授权范围内排期，不能通过前端构造请求改期。
- 新权限进入菜单/权限种子，但不因成员角色映射自动无条件授予；固定角色包继续由平台管理员显式配置并对账。
- 后端在读取响应中返回 `allowedActions`，写接口仍须实时复核，不依赖前端按钮显隐。

### 9.2 状态

允许修改当前排期的任务状态：

```text
not_started, preparing, in_progress, pending_review, revision
```

禁止修改：

- `completed` 任务；
- 已归档或已完成项目；
- 逻辑删除任务；
- 已归档/删除镜头或资产制作分项；
- 当前负责人已不是有效项目 `creator` 的异常任务。

改期不改变任务状态，不创建目录 Outbox，不触发版本、审核或通知链。

## 10. 统一读取 API

### 10.1 项目排期

```http
GET /shot-grid/projects/{projectId}/schedule
Permission: shotgrid:task:list
```

查询参数：

```text
windowStart, windowEnd                 必填，秒级业务本地时间
targetKind=all|shot|asset_item         默认 all
groupBy=assignee|task_kind|status|episode|scene|asset_type
assigneeUserIds, taskStatuses, priorities, keyword
episodeIds, sceneIds, assetTypes
pageNum, pageSize                      pageSize 最大 1000
```

读取范围：

- 当前排期或首版基线与可视窗口相交的任务进入结果。
- 结果按分组稳定键、目标业务排序键和 `taskId` 排序。
- 冲突计算不受当前页面的状态、关键字或分组筛选限制，但只覆盖当前项目可见的未完成活动任务。
- 返回 `serverTime` 供前端校准提醒；正常、临期、逾期和基线偏差由前端根据原始时间本地重算，不持久化为状态。

响应主体：

```text
window: { start, end, serverTime }
lanes[]: { laneId, laneType, name, sortOrder, taskCount, conflictCount }
rows[]:
  taskId, projectId, taskKind, taskStatus, priority, lockVersion
  target: { targetKind, targetId, parentId?, code?, name, sortOrder }
  assignee: { userId, userName, nickName? }
  currentStart, currentEnd, baselineStart, baselineEnd
  conflicts[]: { taskId, targetName, startTime, endTime }
  allowedActions[]
pageNum, pageSize, total, hasNext, unscheduledCount
```

### 10.2 未排期任务池

```http
GET /shot-grid/projects/{projectId}/schedule/unscheduled
Permission: shotgrid:task:list
```

只返回已经存在真实 `sg_task`、负责人有效、当前排期为空且任务未完成的任务，支持与排期主接口一致的目标和人员筛选及服务端分页。未委派对象继续在镜头/资产原页面显示“未分配”，不能进入未排期任务池。

### 10.3 排期历史

```http
GET /shot-grid/tasks/{taskId}/schedule-changes
Permission: shotgrid:task:query
```

按 `createTime DESC, scheduleChangeId DESC` 分页返回结构化历史。制作人员可读取本人任务及其已有项目访问范围内的历史；不得借此扩大任务详情或跨项目访问权限。

## 11. 修改排期 API

```http
PUT /shot-grid/tasks/{taskId}/schedule
Permission: shotgrid:task:schedule
Header: Idempotency-Key
```

请求：

```json
{
  "lockVersion": 8,
  "expectedStartTime": "2026-09-01T09:00:00",
  "expectedEndTime": "2026-09-05T18:00:00",
  "operationSource": "gantt",
  "changeReason": "上游素材延迟交付",
  "overlapAcknowledged": false,
  "expectedConflictTaskIds": []
}
```

规则：

- 不接收带偏移时区或小数秒的值，沿用业务本地时间。
- 两个时间必须完整，结束严格晚于开始。
- 排期更新允许开始时间早于服务端当前时间，以真实表达既有计划或延期；时间处于过去不等于状态变化。
- `changeReason` 规范化后必须非空，最长 500 字符。
- `operationSource` 只允许 `swimlane/gantt/dialog`；首次排期若来自开工命令由后端记录 `start`。
- `changeType` 由后端比较前后范围推导，不相信客户端分类。
- 成功时更新当前范围、兼容 `due_date`、任务 `lockVersion`、结构化历史和 `SysOperLog`；首次排期还冻结基线。

成功响应返回更新后的完整排期行和最终冲突摘要，前端不得继续使用本地推算结果覆盖它。

## 12. 冲突二次确认

第一次提交发现重叠且 `overlapAcknowledged=false` 时：

```text
HTTP 409
errorKey = SG_TASK_SCHEDULE_OVERLAP
data = { conflicts[], conflictTaskIds[] }
```

前端使用 Element Plus 确认框列出负责人、任务名称和时间范围。用户确认后携带：

```text
overlapAcknowledged=true
expectedConflictTaskIds=[服务端上次返回的稳定有序集合]
```

后端在同一项目协调锁内重新计算：

- 集合相同：允许保存并在历史中记录确认事实和冲突快照。
- 集合变化：仍返回 `SG_TASK_SCHEDULE_OVERLAP`，要求用户重新确认。
- 任务 `lockVersion` 变化：返回 `SG_OPTIMISTIC_LOCK_CONFLICT`，不执行排期更新。

## 13. 事务、锁与幂等

写入采用短数据库事务：

```text
锁项目协调行
  -> 锁目标 task
  -> 复核项目/角色/数据范围/负责人/目标生命周期/任务状态
  -> 校验 lockVersion 与时间范围
  -> 计算当前项目同负责人重叠集合
  -> 校验二次确认集合
  -> 首次时冻结 baseline
  -> 更新 expected range + dueDate + task lockVersion
  -> 插入 sg_task_schedule_change
  -> 写 SysOperLog
  -> commit
```

- 同一项目的排期修改通过项目协调锁串行化，保证冲突确认集合在写入事务内稳定。
- 事务中不执行 NAS、外部网络或 Redis I/O。
- 同一任务、操作人和幂等键重放返回首次成功结果，不重复递增锁版本或写历史。
- 相同幂等键但请求内容不同必须返回冲突，不能覆盖首次命令。
- 失败路径整体回滚。

## 14. 开工契约调整

当前开工窗口把完整预期时间作为新开工必填字段，并拒绝过去的开始时间。引入预排期后调整为：

1. 任务已有当前排期：开工窗口只读展示该范围，开工请求省略时间并保留现值；即使计划开始已经过去，也不得因此拒绝开工。
2. 任务尚无当前排期：开工窗口继续要求完整范围并拒绝新的过去开始时间；开工 Service 复用排期领域逻辑，在同一事务冻结基线和写首次排期历史。
3. 如需在开工前改变已有排期，管理人员必须先通过排期更新接口完成，不在开工命令中建立第二条改期规则。

## 15. 前端信息架构

### 15.1 页面入口

- 镜头列表新增“泳道时间线”“甘特图”，保留表格、卡片、分镜板。
- 资产列表新增“泳道时间线”“甘特图”，保留表格、卡片、类型看板。
- 项目列表或项目详情提供“综合排期”操作，进入 `/projects/:projectId/schedule` 深层路由。
- 不新增顶级导航项。

### 15.2 组件边界

```text
ScheduleBoard
├─ ScheduleToolbar
├─ ScheduleSwimlaneView
├─ ScheduleGanttView
├─ ScheduleTaskDrawer
├─ ScheduleEditDialog
└─ ScheduleUnscheduledDrawer

ScheduleGanttAdapter
├─ 领域行/泳道 -> 渲染器数据
├─ 渲染器拖动/缩放 -> 排期草稿事件
└─ 基线、冲突、只读与禁用状态模板
```

共享项目排期状态进入 Pinia 或项目现有共享 Store；页面级弹窗草稿和拖动草稿保持组件局部。不得在三个入口复制请求和业务判断。

### 15.3 工具栏

- 上一窗口、回到今天、下一窗口；左右导航每次移动一个完整可视窗口。
- 日期窗口使用包含首尾的自然日期，不在浏览工具栏显示无意义的零点时间；查询内部继续使用次日零点作为排他结束边界。
- 日/周/月缩放。
- 分组方式。
- 负责人、任务状态、优先级、关键字及领域筛选。
- 仅看冲突、仅看延期、显示/隐藏基线。
- 未排期任务数量与抽屉。
- 授权管理人员的“进入/退出排期编辑”。

未排期抽屉中的真实任务提供“安排时间”动作，打开同一个 `ScheduleEditDialog` 创建首次完整排期并冻结基线；未委派对象不显示该动作。

视图模式、缩放、分组和窗口写入路由 query，刷新可恢复；筛选状态必须按 `projectId` 隔离。

默认窗口偏重未来规划，并保证今天不会在月底贴到视图右侧：

- 日：过去 7 天、今天、未来 23 天，共 31 个自然日。
- 周：按周一对齐，过去 4 周、当前周、未来 8 周，共 13 周。
- 月：按月初对齐，过去 3 个月、当前月、未来 9 个月，共 13 个月。

首次进入且没有显式窗口时按当前缩放生成默认窗口；切换缩放时以当前可见的今天为锚点，今天不在当前窗口时保留当前窗口中点；“回到今天”明确恢复当前缩放的默认窗口。显式 URL 范围和用户手动选择范围不得在加载或刷新时被默认值覆盖。

### 15.4 任务条表达

- 实色任务条表示当前排期，颜色表示真实任务状态。
- 虚线或半透明影子表示首版基线。
- 红色边框/标记表示同一负责人重叠。
- 临期、逾期和基线偏差使用标签或图标，不伪造成完成进度。
- 同一人员泳道的重叠任务上下堆叠，不互相遮挡。
- 点击任务条打开详情抽屉，展示当前范围、基线、负责人、状态、冲突和排期历史。

### 15.5 编辑保护

- 默认只读；只有显式进入编辑模式后才响应拖动和缩放。
- 只允许水平移动和调整左右边界，不允许垂直拖动改变负责人或分组。
- 拖动过程中显示新起止时间和相对基线偏移。
- 松开只生成草稿并打开 `ScheduleEditDialog`，不得立即调用写接口。
- 对话框使用 `ElForm/ElFormItem/ElDatePicker/ElInput/ElButton`，通过 `validate()` 和显式 `@click` 提交，不使用原生 submit。
- 保存中锁定目标任务条并阻止重复提交。
- 成功后以服务端响应替换本地行；失败时恢复原位置并保留原因草稿供重试。

## 16. 前端数据流与异常

```text
路由/筛选/窗口变化
  -> 取消旧请求并递增 generation
  -> 获取分页 schedule read model
  -> 适配为泳道或甘特数据

拖动/缩放
  -> 本地草稿
  -> 原因对话框
  -> PUT schedule
       ├─ 200：替换任务、刷新受影响泳道
       ├─ 409 overlap：二次确认并带冲突集合重试
       ├─ 409 lock：回滚并刷新该任务
       ├─ 403/项目只读：回滚并退出编辑模式
       └─ 网络/5xx：回滚，保留原因，允许重试
```

错误边界：

- 列表查询失败显示失败态和重试，不得显示为空排期。
- 迟到响应不得覆盖已切换的项目、筛选或时间窗口。
- 跨人员泳道拖动立即回弹，并提示使用现有改派流程。
- 权限或 `allowedActions` 变化时退出编辑模式。
- 首版不增加 WebSocket；成功修改后定向刷新任务和受影响泳道，其他并发由乐观锁处理。

## 17. 自然时间与缩放

- 所有日期使用项目现有业务本地时间、秒级精度和无偏移 JSON 格式。
- 排期持续时长为 `expectedEndTime - expectedStartTime` 的自然经过时间。
- 周末和节假日不跳过、不压缩、不改变拖动结果。
- 日、周、月只改变每单位像素和表头粒度，不改变保存的真实时间。
- 月缩放仍按实际日历日期定位，不把一个月固定为 30 天写回数据库。
- 页面复用当前 30 秒及恢复可见时的本地提醒重算思路，不增加时间状态轮询。

## 18. 性能设计

- 读取只覆盖当前窗口，并预取左右各一个可视窗口。
- 平移、缩放和筛选请求防抖，旧请求可取消且有 generation 隔离。
- 主接口按稳定顺序分页，每页最多 1000 条；未排期池独立分页。
- 人员泳道和甘特行使用虚拟渲染，不能让全部 DOM 常驻。
- 组件和渲染依赖按排期入口懒加载，不能扩大登录页和普通列表首包。
- 实施前用真实项目统计校准测试集；默认最低基准为总计 5,000 个任务、当前窗口 2,000 个任务、200 条人员泳道。
- 基准测试记录 API 查询、首屏可交互、平移缩放和拖动响应；不得只以生产构建成功证明性能。

## 19. 开源渲染核心技术门禁

进入完整业务开发前，必须先用固定夹具验证 SVAR OSS 适配层：

1. Vue 3/Vite 当前版本可构建并按需加载。
2. 日/周/月时间刻度可表达自然时间。
3. 任务条可水平移动和调整左右边界。
4. 只读/禁用状态可由项目权限控制。
5. 同人重叠任务可稳定堆叠或由适配层安全表达。
6. 自有任务模板可表达基线和冲突，不调用 PRO API。
7. 基准数据下虚拟渲染与交互达到可用水平。
8. MIT 许可证文本、包版本和 `package-lock.json` 一并固定。

任一门禁失败时，停止进入领域写入和页面全面接入，重新评审适配层或开源渲染核心。不得静默引入商业版、另一套 UI 框架或手写低质量全量甘特替代。

## 20. 稳定错误键

| errorKey | HTTP | 场景 |
| --- | --- | --- |
| `SG_TASK_SCHEDULE_INVALID` | 422 | 时间缺半、格式/精度错误、结束不晚于开始、原因非法，或尝试清空已有排期 |
| `SG_TASK_SCHEDULE_OVERLAP` | 409 | 存在未确认冲突，或二次提交时冲突集合变化 |
| `SG_OPTIMISTIC_LOCK_CONFLICT` | 409 | 任务锁版本已变化 |
| `SG_TASK_SCHEDULE_READ_ONLY` | 409 | 项目、任务或目标当前不可改期 |
| `SG_IDEMPOTENCY_CONFLICT` | 409 | 相同幂等键对应不同规范化命令 |

认证、项目不存在/不可见、平台权限和数据范围错误继续复用现有 Shot Grid 错误协议。

## 21. 验证与验收

### 21.1 后端

- 迁移约束、现有时间到基线的可证明回填、初始化 SQL 同步和禁止有数据降级。
- 首次排期同时冻结当前范围和基线，后续改期基线不变。
- 当前范围、`due_date`、任务版本、结构化历史和 `SysOperLog` 同事务成功或回滚。
- 权限、项目角色、数据范围、项目状态、任务状态、目标生命周期和负责人有效性。
- 自然时间、过去时间改期、半开区间冲突、二次确认集合变化。
- 项目协调锁、任务乐观锁、幂等重放和幂等内容冲突。
- 项目永久删除业务图包含排期历史。

### 21.2 前端单元/组件

- 统一 API 数据到两种视图的适配。
- 日/周/月几何变换不修改业务时间。
- 默认只读、进入编辑、拖动预览、原因校验和保存 loading。
- 跨泳道回弹、失败回滚、冲突确认、锁冲突刷新和重复提交保护。
- 基线、状态、冲突、临期和逾期表达不互相冒充。
- 路由 query 恢复、项目隔离、取消请求和 ABA 迟到响应隔离。
- 本次表单作用域不存在原生 submit 链路。

### 21.3 真实页面交互

至少完成：

1. 镜头局部泳道和甘特读取。
2. 资产分项局部泳道和甘特读取。
3. 项目综合排期同时显示镜头和资产任务。
4. 日/周/月切换和路由刷新恢复。
5. 初次排期、拖动平移、两端缩放和精确编辑。
6. 同人冲突二次确认后保存。
7. 并发锁冲突后回滚与刷新。
8. 制作人员只读，管理权限被撤销后写入失败关闭。
9. 保存后刷新页面仍保持当前范围、基线和历史。

这些旅程只证明排期子系统；不替代完整 Shot Grid E2E、真实 NAS、媒体处理或生产部署验收。

## 22. 实施顺序边界

后续实施计划应按以下依赖顺序拆分：

1. 开源渲染核心适配技术门禁。
2. PostgreSQL 迁移、DO/VO、初始化 SQL、权限和错误契约。
3. 排期只读 DAO/Service/API 与冲突查询。
4. 结构化历史和排期写事务。
5. 共享前端 Store、适配器和只读双视图。
6. 编辑、冲突确认、错误回滚和开工契约调整。
7. 三类入口、性能基准和真实页面验收。

每一阶段只声明它实际通过的验证，不得把“依赖已安装”“页面可打开”“静态检查通过”描述成排期功能完成。

## 23. 已确认决策摘要

| 决策 | 结论 |
| --- | --- |
| 时间计算 | 自然时间连续计算，周末和节假日可排 |
| 缩放 | 日、周、月 |
| 页面入口 | 镜头和资产局部视图 + 项目综合深层页；不新增顶级导航 |
| 编辑方式 | 拖动/缩放 + 精确对话框；默认只读，显式进入编辑 |
| 人员改派 | 不通过泳道拖动，继续使用现有受控改派 |
| 基线 | 首次完整排期冻结，后续只改当前计划 |
| 审计 | 结构化只追加历史 + 同事务平台操作日志 |
| 撞期 | 同项目同人未完成任务重叠；警告并二次确认，可继续保存 |
| 进度表达 | 真实状态、时间位置、临期/逾期、基线偏差和冲突；无虚假百分比 |
| 任务依赖 | 首版不支持，不显示依赖连线，不改变开工门禁 |
| 渲染方案 | SVAR Vue Gantt OSS + 项目适配层 + Element Plus 外围交互 |
| 数据核心 | 继续以 `sg_task` 为唯一任务和当前排期事实，不创建平行任务体系 |
