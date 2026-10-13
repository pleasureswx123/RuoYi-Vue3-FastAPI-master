# 镜头与资产强制永久删除：实施与验证记录

日期：2026-10-13。结论：代码已接通，定向检查通过；尚未在当前业务库启用，也未通过真实 NAS 完整闭环验收。没有执行真实目标删除、业务库 40 迁移、提交、推送或部署。

## 已实现

原行内“强制删除”直接采用永久删除语义，无额外模式。权限仍按镜头/资产分开。删除业务图及历史、冻结独占文件清单、写独立审计/清理队列在同一事务；NAS 与平台文件在线程 I/O 中清理。共享文件保留，路径归属不明拒绝。资产包括历史归档/删除分项，其他镜头编号保持不变。

清理完成前占用原目录和当前编号/名称，PG 触发器覆盖创建、导入和身份修改；清理成功才释放占用。列表恢复待清理状态、显示失败并允许授权重试，详情删除返回也刷新该状态。新 API 不公开存储路径。

评审发现并修复旧 I/O 接管窗口：执行态即使租约过期也不能证明 I/O 已停止；目录、版本发布、最终交付、媒体派生不再自动接管过期执行态。永久删除遇到执行态会拒绝。代价是进程崩溃后需要管理员确认旧进程和 I/O 已退出后恢复，不能仅按过期时间重置任务。

## 实际验证

后端命令均在 `ruoyi-fastapi-backend` 使用 `.venv/Scripts/python.exe`。PG 用 `SHOT_GRID_RUN_PG_TESTS=1`，随机测试库创建/清除，不使用业务数据；文件测试仅用临时目录。

- `pytest -q tests/module_shot_grid/test_force_delete_pg.py tests/module_shot_grid/test_target_purge_pg.py tests/module_shot_grid/test_target_purge_graph_pg.py tests/module_shot_grid/test_target_purge_concurrency_pg.py tests/module_shot_grid/test_target_purge_path.py tests/module_shot_grid/test_target_purge_path_adapter.py tests/module_shot_grid/test_target_purge_worker.py tests/module_shot_grid/test_target_purge_router.py tests/module_shot_grid/test_storage_operation_dao.py tests/module_task/test_shot_grid_storage_task.py`：74 通过、1 失败。失败为新增同号门禁测试错误匹配异常字符串；同时发现服务层应从异常链读取 PG constraint_name，已修正。
- 修复后 `pytest -q tests/module_shot_grid/test_force_delete_pg.py -k 'completed or running_delivery or expired_publishing'`：5 通过。包括同号禁止/释放后重建、过期媒体/交付/版本发布不接管。
- `pytest -q tests/module_shot_grid/test_force_delete_pg.py -k failed_cleanup_retry`：1 通过，验证权限拒绝、审计事务、重试与重复重试拒绝。
- `pytest -q tests/module_shot_grid/test_version_submission_dao.py tests/module_shot_grid/test_final_delivery_worker_service.py tests/module_shot_grid/test_media_derivation_service.py tests/module_shot_grid/test_version_publish_worker_service.py`：16 通过。
- `pytest -q tests/module_shot_grid/test_force_delete_contract.py`：26 通过。
- 定向 Ruff check 通过；新模块、迁移与目标清理测试 Ruff format --check：20 文件通过。`alembic heads` 显示 `20261013_40`，这只是代码迁移链，不代表业务库已升级。
- 前端 `npx.cmd eslint` 检查强删、清理状态组件/API及两列表，通过；`npx.cmd vitest run tests/unit/forceDeleteAction.spec.js tests/unit/targetPurgeStatus.spec.js`：8 通过。
- `npm.cmd run build:prod` 通过。最初误用不存在的 `build` 脚本失败，已改正确脚本；保留既有 chunk 大小及 PURE 注释警告。
- `git diff --check` 已修复本次 SQL 尾部空白后通过。

PG 测试证明业务图物理删除、共享文件引用保留、事务回滚、迁移往返/重复执行、同编号/同名称占用及释放。临时文件测试证明精确目录删除、重复清理、相邻目录保留、原路径重新写入同名文件，以及不安全清单拒绝。以上不能替代真实 NAS、权限账号和上传发布链验收。

本机 Chrome 检查时已经退出登录，停在 `/login?redirect=/shots?projectId=16`；本轮未执行登录后弹窗交互。保留已有 `lock-scroll=false` 和稳定目标键隔离，组件测试覆盖原因验证和切换目标。

## 启用步骤（尚未执行）

1. 安排维护窗口，停止并排空全部旧后端/目录、版本、交付、媒体 Worker，确认旧进程及其 I/O 完全退出。禁止新旧版本混跑。备份 PostgreSQL、平台文件和相关 NAS 数据；数据库备份不能恢复已删除 NAS 文件。
2. 使用既定部署配置核对数据库为目标 PostgreSQL；从后端目录执行迁移。以下是已确认目标环境后的命令，不要对未知数据库直接执行：

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade 20261013_40
.\.venv\Scripts\python.exe -m alembic current
```

3. 全部后端进程启动新代码，确认 Application Leader、Redis、NAS 服务账号和挂载。清理沿用 `SHOT_GRID_STORAGE_WORKER_ENABLED` 及目录 Worker 配置，Worker 关闭会保持 pending。生产继续走既有部署脚本及 CIFS 校验；不能把本地普通目录当作真实 NAS。Windows 默认适配器对无法保证安全递归删除的平台会拒绝，不能开启测试用 `allow_local_root` 绕过生产门禁。
4. 在明确隔离的测试项目/NAS 目录分别做镜头和资产闭环：上传旧文件 → 永久删除 → 清理期间同号/同名拒绝 → 清理成功 → 新 ID 同号/同名重建 → 重新分配开工 → 上传相同文件名，确认不冲突且邻居/共享文件保留。真实闭环尚未执行。
5. 查看 GET `/shot-grid/projects/{projectId}/target-purges?targetKind=shot`（资产用 asset）；failed/retry_wait 可从页面重试。processing 失租约不能直接重试，先确认旧执行者退出，再由管理员按精确队列记录恢复，原占用始终保留。

降级有未完成清理会拒绝；任何降级都不能恢复已删除业务与文件。旧逻辑删除记录不会被本迁移自动追溯清理。


## 本地业务库升级记录（2026-10-13 16:03）

本节更新上文“尚未执行”的本地迁移状态；真实 NAS 闭环仍未验收。

- 用户明确授权升级至 40。目标：127.0.0.1:15432 / ruoyi_fastapi_preview_20260812，升级前实际版本39。
- 升级前四类文件执行任务计数均为0；仅停止本项目已核实的后端进程树，未停止 PostgreSQL、Redis 或其他应用。
- 备份：ruoyi-fastapi-backend/output/backups/before-20261013_40-20261013-160252.dump，3658666字节，pg_restore --list 通过。
- `.venv/Scripts/python.exe -m alembic upgrade 20261013_40` 成功；SQL实查版本40，两项 purge guard 触发器均启用，清理队列及路径占用均为0。
- 按原 `ruoyi app run --env=dev` 隐藏重启后端；9099/openapi.json HTTP200，两个 target-purges 接口已加载。读取本地配置确认 STORAGE_WORKER_ENABLED=True；此项不代表真实NAS清理验收。
- 迁移模型发现提示可选AI依赖agno缺失，未阻止本次迁移或后端API启动。
- 未执行任何真实镜头/资产删除或NAS文件清理，未提交、推送或部署生产服务器。数据库备份不包括NAS文件；本次迁移没有删除NAS文件。


## Windows 实际清理故障修复与恢复

根因：Windows 的 shutil.rmtree.avoids_symlink_attacks=False，原适配器安全拒绝导致队列1、2失败；路径占用继而阻止项目删除/同号导入。镜头导入将PG触发器错误折叠成泛化冲突。

修复：Windows 持有全祖先防写入/删除共享句柄并按句柄删除，拒绝重解析点；两类导入保留明确清理原因。实现依据：[CreateFile 官方契约](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea)、[SetFileInformationByHandle 官方契约](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)。先前“Windows不支持安全清理”的部署限制由本修复替代，服务账号仍须具备所需权限。

测试先复现祖先重命名未被 FILE_READ_ATTRIBUTES 阻止，改为 GENERIC_READ 后通过；54项定向测试通过（Windows句柄、占用文件、junction、项目/目标目录清理、镜头及资产导入），Ruff通过。修正新测试的资产服务类导入名后回归通过。

实际恢复仅针对项目16已提交的队列1、2（EP01/000_0010、EP01/001_0010），精确状态条件更新并写维护审计，随后由现有Leader Worker处理，未直接删项目。实查两条均succeeded、原路径占用0，NAS目标不存在，三个独占平台文件记录清除，项目仍存在。未替用户再次导入或永久删除整个项目；同号重新上传完整闭环尚未执行。


## 提交发布前检查（2026-10-13）

本次暂存排除 .env、备份、输出、部署配置及另一个镜头导入错误行界面改动。同步修正 schema.py 的40版契约常量、两张新表/两个权限，以及新清理查询对应的测试替身。

- 隔离 PostgreSQL 核心4个测试文件：32通过。
- 契约/元数据/项目删除/镜头CRUD：134通过。
- 补齐本地测试依赖 agno 2.8.6、aiosqlite 0.21.0、docstring-parser 0.17.0（不改生产依赖）后，Shot Grid、调度、平台管理和插件套件：2043通过、198跳过、1失败。唯一失败为旧NAS目录夹具缺少归属时间，已在未修改的HEAD副本复现。
- 初次平台全量有缺包及旧CLI输出断言失败；未宣称完整套件通过。前端全量791通过、17失败；上一提交同6文件也复现完全相同17失败，涉及既有排期/开工/视图测试，非本次回归。
- 本次全部暂存Python Ruff通过；前端全量lint通过；build:prod通过；git diff --cached --check通过。
- 发布风险边界：带上述已复现的基线测试债务发布本次已定向验证的功能，不把这些失败隐藏或改成跳过。本次不修改这些无关产品行为。
- 生产发布前只读确认：上一提交46ea42f，数据库38，目录/版本/交付/媒体执行态均0。使用标准remote-deploy及StopBackendForMigration，备份后迁移39、40。
