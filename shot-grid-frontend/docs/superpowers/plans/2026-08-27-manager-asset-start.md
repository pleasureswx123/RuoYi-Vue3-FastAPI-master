# 资产按制作分项由管理员确认开工

> 执行方式：使用 superpowers:subagent-driven-development 分工执行、定向审查；沿用当前 `codex/manager-shot-start` 工作树以便用户继续本地手测，不提交或推送。原“资产由本人开始”规则被本轮用户目标取代。

**目标：**资产库也由管理员决定任务开工；一个资产的多个制作分项独立分配、独立确认、独立推进，不因共享目录或其他分项开工而自动开始。

**实现边界：**复用任务 start API、Vue/Element Plus、现有权限与目录 Outbox，不新增资产依赖自动检查、整资产一键开工、批量开工、撤销或暂停动作。

## 固定契约

- 镜头请求保持 `{ lockVersion, shotLockVersion, assetsConfirmed: true }`；资产分项请求使用 `{ lockVersion, assetLockVersion, assetItemLockVersion, startConfirmed: true }`。
- 两类任务仅允许有 `shotgrid:task:start` 的项目 director 或 has_all_scope 管理人确认；当前负责人必须仍是活动有效 creator。制作人不能自己开工，管理员不能代交版本。
- 资产操作锁项目、任务、父资产、目标分项并复核访问范围、三份版本、生命周期、任务状态、分项内容及人工确认；人工确认和目录/状态写入同事务审计。失败全部回滚。
- 未分配不创建任务；分配后为 `not_started`，前端统一显示“待开工”；开工后共享目录未就绪则 `preparing`，已就绪则 `in_progress`。Worker 只推进已经 `preparing` 的分项，其他分项不动。
- 列表/详情新增 `itemStatusCounts`，键固定为 `unassigned/not_started/preparing/in_progress/reviewing/revision/completed`，只统计活动且未删除分项；所有值为非负整数。修复 preparing 的 SQL/Python 投影。父资产聚合优先级为 revision、reviewing、in_progress、preparing、unassigned、not_started；全部完成才 completed，无活动分项 unassigned。
- 父资产 `allowedActions` 中 `task.start` 仅作为进入分项开工入口，至少有可开工分项时返回；分项 `allowedActions` 为实际任务 start 动作。父资产本身不可提交 start。
- 资产列表三种视图提供开始入口，打开现有资产详情抽屉供管理员选择分项；详情逐分项提供 small 开始按钮及含资产、分项、负责人的人工确认框。
- 列表根据分项计数、详情根据各分项状态轮询，待开工 5 秒，目录准备 1.5 秒最多 80 次；复用已有有界轮询，保留筛选/勾选/弹窗，错误及 ABA/卸载隔离。制作端工作台与任务详情统一等待管理人开工，不再保留资产自行开始入口。
- 不改数据库结构，因此不新增 Alembic 版本；旧目录、已开始任务和版本数据保持。旧客户端资产自开工请求在服务端拒绝。

## 任务与验收

- [x] 后端：任务 VO/Service/动作投影，资产 DAO/VO/Service 的分项计数与聚合状态；定向 TDD 验证权限、严格确认、三锁版本、负责人失效、归档、重复开工、共享目录和审计。
- [x] 资产前端：列表入口、分项确认、状态数量和有界刷新；真实 Vue 组件测试覆盖取消/确认、权限交集、一个分项开工其他不动、分项混合状态、重复点击、切换上下文迟到响应。
- [x] 制作端：移除资产自开工按钮和请求链，等待/状态文案与轮询统一；保留版本提交本人门禁，相关测试覆盖管理端放行后的更新。
- [x] PostgreSQL 集成验证：使用隔离测试资源验证同资产多分项、同分项并发、不同分项共享唯一目录操作、Worker 不推进待开工分项；不得写入用户开发业务数据或访问真实 NAS。
- [x] 同步根/后端/前端 AGENTS、正式契约、需求与用户使用说明；审查完整最终调用结构，记录实际测试、未执行 E2E 和发布边界。

## 预检记录

| 任务交界 | 已核对的约束 |
| --- | --- |
| 后端与资产 UI | 三份版本和 startConfirmed 的字段一致；父级入口不等于整资产开工；itemStatusCounts 的键不做 camelCase 改写 |
| 后端与制作端 | start 权限统一归管理人，version.add/preflight/create/retry 仍限定当前制作人 |
| 资产 UI 与制作端 | 共用有界轮询但各自上下文隔离；资产 UI 文件由资产任务负责，任务/工作台由主代理负责 |
| 后端与 PostgreSQL 验证 | 测试仅使用隔离数据库/表；共享目录幂等与只推进 preparing 必须有真实 SQL 证据 |

实现前代码事实：资产 Service `_item_status` 尚缺 preparing，DAO 也将 preparing 回落为 not_started；本轮须同时修复，不能仅换按钮。

## 审查发现与修复

目录完成与另一分项开工存在交错窗口：真实PG已复现目录成功但新分项永久 preparing。成功回写补充项目协调锁，顺序为 project → operation → task/storage；仍在事务外执行 NAS I/O，并保持 owner + attempt fencing。定向回归已从 RED 转为 GREEN；最终 22 项真实 PostgreSQL 集中验证通过，22 个临时库全部清理。独立范围复审通过。

## 本地人工验收

1. 确认前后端已加载本轮代码；开发前端刷新页面，后端未启用热重载时重启原启动进程。本次资产规则不新增迁移，也不需要重启 PostgreSQL/Redis；已有镜头开工迁移仍按原部署要求处理。
2. 使用项目管理人账号及 `shotgrid:task:start` 权限，选择一个测试资产，准备三个活动分项：前两个分别分配制作人员，第三个不分配。应显示待开工 2、待分配 1。
3. 制作人员打开本人待开工任务：可查看要求，没有开始按钮，也不能上传提交版本。
4. 管理人从资产列表“选择分项开工”打开详情，在第一个分项核对资产、分项、负责人和线下条件；先取消确认，状态应不变，再由测试人员自行决定是否正式确认。
5. 确认后只推进第一个分项。若目录尚未就绪，显示目录准备中；有效目录 Worker 完成后自动更新为制作中。第二分项继续待开工、第三分项继续待分配；制作人刷新或等待自动查询后才看到提交入口。
6. 之后确认第二分项；共享目录已就绪时应直接进入制作中，不重复创建目录。目录 Worker 未启用、NAS 不可达或权限异常时应检查目录任务，不能通过重复开工或手改数据库强行跳过。

以上是人工验收步骤，不表示已在用户业务数据上执行；本轮浏览器只验证了查看与取消确认。

## 验证记录

- 后端权限/投影及既有版本门禁：242 项定向测试通过；Worker 锁修复后相关 DAO/Worker/task 78 项通过。两组存在重叠，不相加。
- PostgreSQL 14.22 隔离测试：22 项通过（48.13 秒），含同分项竞争、共享目录、人工确认/三版本/有效负责人、审计错误回滚、SQL计数和目录完成交错；22 个测试数据库均清理，额外前缀查询残留为0。
- 制作端 taskViews/taskPresentation 34项及 versionWorkspace 7项通过，改动文件ESLint通过。
- 资产前端初版45项通过，lint和生产构建通过；保留既有PURE注释及大包警告。编辑快照/409恢复修复后52项资产定向通过，改动文件ESLint通过；未重复生产构建。普通刷新保留旧稿/旧锁，冲突刷新关闭旧上下文并要求重新核对，开工后刷新再次复核代次。
- 未执行真实NAS/SMB或完整系统E2E；浏览器仅做真实查看/取消确认。此前shotViews的旧拖拽列测试仍有既有失败，不称全量测试通过。

## 实际验证命令

后端目录使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/module_shot_grid/test_task_vo.py tests/module_shot_grid/test_task_dao.py tests/module_shot_grid/test_task_service.py tests/module_shot_grid/test_task_router.py tests/module_shot_grid/test_asset_crud_vo.py tests/module_shot_grid/test_asset_crud_dao.py tests/module_shot_grid/test_asset_crud_service.py tests/module_shot_grid/test_shot_crud_service.py tests/module_shot_grid/test_version_submission_service.py tests/module_shot_grid/test_storage_operation_dao.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/module_shot_grid/test_storage_operation_dao.py tests/module_shot_grid/test_storage_worker_service.py tests/module_shot_grid/test_task_service.py -q --tb=short
$env:SHOT_GRID_RUN_PG_TESTS='1'
.\.venv\Scripts\python.exe -m pytest -q tests/module_shot_grid/test_asset_manager_start_pg.py --tb=short -s
Remove-Item Env:SHOT_GRID_RUN_PG_TESTS
```

前端目录：

```powershell
npm.cmd test -- --run tests/unit/assetPresentation.spec.js tests/unit/assetViews.spec.js
npm.cmd test -- --run tests/unit/taskViews.spec.js tests/unit/taskPresentation.spec.js --reporter=dot
npm.cmd test -- --run tests/unit/versionWorkspace.spec.js --reporter=dot
npm.cmd run lint
npm.cmd run build:prod
```

资产局部修复后仅追加改动文件 ESLint，不重复构建；后端改动文件 Ruff/format 检查通过。仓库根目录最终 `git diff --check` 通过。上述命令对应本节所列定向结果，不代表全工程测试通过；完整 E2E 和真实 NAS 未执行。首次系统 Python 缺 pytest 时未执行，随后改用上述项目虚拟环境。

## 最终审查与交付状态

后端并发修复、资产编辑快照修复、制作端及跨前后端最终审查均通过，未留下本轮 Critical/Important 问题。未提交、合并或推送；保留当前工作树和已有无关修改供本地手测。未以定向测试或只读浏览器检查冒充完整 E2E/真实 NAS/发布验收。
