# 镜头与资产强制删除验证记录

日期：2026-10-13。代码已实现，未提交、未推送、未部署，未升级业务数据库或给角色授权。测试只在随机隔离 PostgreSQL 库执行删除，测试库已清理。

## 实现范围

- 独立权限 `shotgrid:shot:forceDelete`、`shotgrid:asset:forceDelete`，配套 Controller、VO、Service、DAO、allowedActions、列表/详情及批量入口。
- 保留原普通删除；强删使用显式原因、项目锁、目标版本锁、事务审计、逻辑删除与关系解绑。历史、附件引用及 NAS 文件保留，其他镜头编号不变。
- 未完成目录/版本提交/最终交付/媒体任务进入已有失败终态，清除租约并递增 attempt；旧执行凭据不能推进被删除业务。
- 自动审核唯一关系保留并归档待办；人工单移除目标版本关系、空单归档，禁止已删除任务版本重新加入/激活。
- PostgreSQL `20261013_39` 迁移及初始化 SQL 同步，AGENTS.md 与正式 API 契约已补充。

## 已执行与结果

以下 Python 命令在 `ruoyi-fastapi-backend` 执行，npm 命令在 `shot-grid-frontend` 执行。

1. `.venv/Scripts/python.exe -m pytest tests/module_shot_grid/test_force_delete_contract.py -q`：先因缺少模型失败，实现后 2 通过；包含必填原因、空白/超长原因、重复目标、空列表及批量上限。
2. `SHOT_GRID_RUN_PG_TESTS=1` 下运行 `test_force_delete_pg.py`：前 18 项集中通过，随后新增最终交付/媒体旧凭据用例单独通过，合计 19 项。基线 head 更新后菜单迁移用例另行重验通过。包括两类目标六阶段、已有目录、旧目录 Worker 回写、过期锁号、权限互不替代、审计失败回滚、暂存提交终止、自动审核历史和禁止重入审核、菜单幂等升级/降级及不隐式授予角色。
3. `.venv/Scripts/python.exe -m pytest tests/module_shot_grid/test_force_delete_contract.py tests/module_shot_grid/test_shot_crud_router.py tests/module_shot_grid/test_asset_crud_router.py tests/module_shot_grid/test_shot_crud_service.py tests/module_shot_grid/test_asset_crud_service.py tests/module_shot_grid/test_review_service.py tests/module_shot_grid/test_review_dao.py tests/module_shot_grid/test_version_publish_worker_service.py tests/module_shot_grid/test_final_delivery_worker_service.py tests/module_shot_grid/test_storage_worker_service.py -q --tb=short`：最终 **353 通过、12 跳过**。跳过不算通过。
4. `npm.cmd test -- tests/unit/forceDeleteAction.spec.js`：**3 通过**，真实挂载 Element Plus，覆盖无效/有效校验、目标版本与原因提交、切项目隔离、无动作授权不提供入口。
5. 相关页面集中验证 `npm.cmd test -- tests/unit/forceDeleteAction.spec.js tests/unit/shotViews.spec.js tests/unit/assetViews.spec.js --maxWorkers=1 ...`：**208 通过、5 失败**。资产页面和新增组件通过，失败均在镜头旧开工/视图切换用例。用测试加载插件只读取 HEAD 的 ShotListView（不覆盖工作区）重跑这些名称，得到完全相同的 **5 项失败**，另有 2 项通过、85 跳过。此对照仅确认这 5 项失败并非新强删改动引入。
6. `npm.cmd run lint`：全量通过；后续组件可见性/选择门禁改动的定向 ESLint 通过。
7. 本次新增/修改后端核心、VO、路由、审核、迁移及新增测试的 `ruff check` 通过；相关新文件已格式化。
8. `npm.cmd run build:prod`：最终构建通过；保留现有大 chunk 警告，没有上调阈值。
9. `git diff --check`：通过，仅提示部分已有文件换行符将在后续 Git 操作规范化；未改动或提交用户的 env/部署/导入等原有修改。

## 全量及环境限制

- `.venv/Scripts/python.exe -m pytest -q --tb=short`：收集阶段失败，环境缺少 `agno`，失败文件为 `tests/plugins/sample_plugins/test_ai_plugin.py`。未安装无关 AI 插件依赖，未调用付费 Provider。
- `npm.cmd test -- --reporter=dot`：全量 **783 通过、18 失败（6 个文件）**。未把全量计为通过，也未对其余 13 项失败作基线归因；本次相关页面已另作定向及 HEAD 对照。
- 沙箱内部分 Python 测试在日志进程通信处阻塞；同一失败定位用例在非沙箱环境通过，后续后端定向回归使用获准的非沙箱执行。隔离 PG 测试因回环网络限制也使用获准执行。
- 尚未进行真实浏览器登录后授权→强删→撤权全旅程；未进行真实 SMB 文件 I/O、全部双事务交错的穷举或生产验收。当前证据不等于完整 E2E 或发布就绪。

## 独立评审

只读评审发现并修复：仅强删权限的列表勾选门禁遗漏、自动审核关系误删、已删除版本重新进入人工审核。审核关系问题先在真实隔离 PG 复现失败，再修复通过。评审中曾提出的 storage/operation 死锁判断经核对 `FOR UPDATE OF` 后撤回，未作为确定缺陷或据此改动 Worker 锁序。

## 启用方式

部署匹配代码并按项目迁移流程升级 PostgreSQL 至 `20261013_39` 后，在角色管理勾选镜头管理下“强制删除镜头”或资产库管理下“强制删除资产”。只有具有对应项目管理范围的账号才可操作；撤销最后一处有效授权后后端拒绝请求，其他角色仍授予该权限或超级管理员全权限时不会因此撤销全部能力。

当前运行中的业务库尚未升级，新权限菜单暂不会自动出现。本次没有执行任何真实业务删除。

## 二次复查

- 修复一处入口与接口不一致：目录未就绪时接口允许强制删除，原 allowedActions 却隐藏入口。现在镜头与资产均允许在目录未就绪时显示强删，仍禁止目录迁移、完成/归档项目及非管理人员。普通编辑、分派等动作保持原目录就绪门禁。
- 新增 24 组目录状态、项目生命周期与项目角色组合测试，先复现 3 项失败，再修复通过。
- 设置 `SHOT_GRID_RUN_PG_TESTS=1`，将 `test_force_delete_pg.py` 与上述第 3 项后端定向测试合并重跑：**396 通过、12 跳过**，其中隔离 PostgreSQL 测试 19 项。未执行真实 NAS 删除。
- 重跑 `npm.cmd test -- tests/unit/forceDeleteAction.spec.js --maxWorkers=1 --reporter=dot`：**3 通过**；本轮修改的后端服务与测试 `ruff check` 通过，`git diff --check` 通过。
- 只读查询本地业务库，实际 revision 为 **20261012_38**，两个 forceDelete 菜单查询结果为空。因此代码实现和定向验证完成不等于当前系统已经启用；仍需升级匹配代码与迁移，并完成真实登录下的授权、撤权和业务验收。前述全量测试限制仍然存在。

## 本地数据库升级结果（2026-10-13）

- 用户明确要求代为升级后，对本地 127.0.0.1:15432 PostgreSQL 执行升级；没有操作生产服务器。
- 升级前以 `pg_dump -Fc` 备份完整数据库，文件为 `ruoyi-fastapi-backend/output/backups/before-20261013_39-20261013-143054.dump`（3650892 字节），并通过 `pg_restore --list` 检查归档目录包含权限表及迁移版本表；未执行恢复演练。
- 在后端目录执行 `.venv/Scripts/python.exe -m alembic upgrade 20261013_39`，退出码为 0。迁移期间模型发现提示缺少可选 AI 依赖 agno，没有阻止本次迁移。
- 升级后只读确认版本为 `20261013_39`；两个权限菜单均存在，类型为按钮、状态正常，分别归属镜头管理与资产库管理。新权限的显式角色关联数为 0，没有自动授权普通角色。
- 本地运行后端的 OpenAPI 已包含镜头与资产两个 `batch-force-delete` 接口。此项只证明接口已加载，不代替真实登录授权、撤权及业务删除验收；本次没有删除业务数据。
- 本节替代前文“当前业务库尚未升级”的环境状态记录，前述测试及其他验收限制保持不变。
