# 镜头任务由管理人员确认开工实施计划

> 执行方式：按本计划逐项实施，遵循 test-driven-development；完成后进行独立代码审查。用户已确认需求并要求开始实现，不再次等待方案审批。

**目标：** 管理人员先分配镜头任务，再在线下确认资产齐备后放行；制作人员在放行前只读，目录就绪后可提交版本。

**架构：** 复用现有任务开始接口、项目访问控制、状态机、同事务审计与 NAS 目录 Outbox。镜头与资产制作任务按 taskKind 区分开工权限，不增加审批状态或自动依赖系统。

**技术栈：** Vue 3、Element Plus、Pinia、Vue Router、Axios、FastAPI、SQLAlchemy Async、PostgreSQL。

**需求依据：** 本次对话已确认方案；正式契约 `../../领域模型与API契约.md` 第 15.2 节随实现同步更新。

## 全局约束

- 仅镜头任务改由项目管理人员或具备跨项目管理范围的管理员开工；资产任务仍由当前负责制作人员开始。
- 平台接口权限、项目范围、资源状态与后端 allowedActions 均需校验。
- 镜头开工请求为 `{ lockVersion, shotLockVersion, assetsConfirmed: true }`，两种版本分别校验任务与镜头；资产任务保持 `{ lockVersion }`。
- 分配不自动放行；不重置已开始任务，不提供撤销、暂停、批量开工。
- 未开工与目录准备中均不可提交版本；开工不授予管理员代提交权限。
- 人工确认在现有操作日志中记录操作人、时间、项目、镜头、任务、负责人和确认方式，不宣称自动检查资产。
- NAS I/O 不进入数据库事务；沿用目录幂等键、租约和 fencing。
- 保留原有工作区改动；本轮不提交环境配置、临时产物，不自动提交或推送。

## 任务 1：后端开工与列表契约

文件：`module_shot_grid/entity/vo/task_vo.py`、`service/task_service.py`、`entity/vo/shot_crud_vo.py`、`controller/shot_crud_controller.py`、`service/shot_crud_service.py` 及相应现有测试（路径均相对于后端）。

- [x] 先扩展任务测试：镜头管理人/跨项目管理范围开工成功；本人制作人被拒绝；资产本人仍可开工；无权限、过期版本、未确认、归档、成员失效与重复开工失败。
- [x] 执行测试确认新规则在原实现上失败。
- [x] 扩展请求：`assets_confirmed: StrictBool = False`、`shot_lock_version: int | None`；仅镜头任务强制人工确认与镜头版本。
- [x] 复用原事务锁序及目录分支，开始前重新校验当前负责制作人员资格；审计增加人工确认信息。
- [x] 镜头列表返回 taskId、taskLockVersion、allowedActions；列表与详情共用动作规则，task.start 要求项目可写、NAS 就绪、活动镜头及未开始任务。
- [x] 执行任务服务、VO、路由、镜头服务/DAO/VO、版本提交权限的定向测试并通过。

## 任务 2：前端入口与等待状态

文件：`src/views/shot/ShotListView.vue`、`src/views/task/TaskDetailView.vue`、两处 presentation、对应现有单测。

- [x] 先补实际组件交互测试：管理员点击行级开始、取消不请求、确认发送两个版本与人工确认；制作人无镜头开工按钮。
- [x] 新增小尺寸开始按钮及 Element Plus 确认框，显示镜头和负责人，使用现有 startTask Axios 接口。
- [x] 操作冻结项目、镜头、任务和 generation；防重复，处理取消、错误与切项目后迟到响应，不污染新上下文。
- [x] 镜头未开始展示“待开工”，制作端给出等待管理人员确认提示；资产“未开始”和本人开始保持原样。
- [x] 扩展现有任务状态轮询：等待开工时较低频刷新，目录准备仍使用原频率，失败有上限且卸载/换路由中止；开放版本提交由后端新状态控制。
- [x] 执行任务/镜头视图、展示、API 的定向测试，覆盖取消、禁用、等待转制作与上下文隔离。

## 任务 3：权限交付、文档与验收

- [x] 权限码保持 shotgrid:task:start；菜单改为“开始任务”，同步 PostgreSQL 基线与增量迁移，仅更名而不暗中扩大角色权限。
- [x] 使用说明明确管理员在平台管理端为 shotgrid_admin 配置开工权限并刷新权限缓存/会话；creator 保留该权限供资产任务使用，不能因此开工镜头任务。
- [x] 更新根/前后端 AGENTS、正式契约、需求规则与使用说明，清除与新流程冲突的当前规则，历史验证记录保留历史标记。
- [x] 运行改动文件 Ruff/ESLint、相关测试、git diff --check；权限与并发测试不得省略。
- [x] 独立审查后逐项核对需求；运行环境允许时验证核心页面交互。明确报告静态/单测与真实 NAS/E2E 的证据边界。

## 进度与证据

- 开始：工作区保留既有环境配置、部署模板和临时文件变化，功能分支 codex/manager-shot-start。

- 后端：任务服务/VO/路由、镜头服务/VO/DAO/路由、版本提交、迁移契约和 CLI 数据库契约共 **185 项通过**；最后规范调整涉及的 4 个测试文件再次定向验证 **118 项通过**。
- 前端：开工与等待相关组件用例 **19 项通过**，涵盖表格/卡片/故事板、确认/取消、权限、双锁号、重复请求、项目切换、等待转目录准备、平台业务鉴权错误和编辑快照。
- 前端整组：taskViews、shotViews、taskPresentation、shotPresentation、taskApi 在该阶段为 **67 项通过、1 项既有失败**。失败项为“移动区间存在冻结目录时不提交重排”：HEAD 已注释拖拽列，旧测试仍断言拖拽控件存在；本次未启用该无关界面，也未删除失败断言。之后新增 5 项已由上述 19 项开工定向测试覆盖；没有将整组回归描述为通过。
- 静态检查：12 个修改/新增 Python 文件的 Ruff check 与 format --check 通过；9 个前端源文件/测试的 ESLint 通过，最后新增用例的 2 个测试文件再次通过 ESLint。
- 独立审查：后端无 Critical/Important；前端两个 Important（轮询替换编辑锁号、HTTP 200 业务 401/403 未立即停止）已复现、修复并经复核关闭。
- 真实浏览器：使用当前管理人会话，在项目 6 的 EP001 / 001 / S003 验证“待开工”、small 开始按钮、包含镜头/负责人/资产线下确认的对话框；点击“暂不开工”后仍待开工且按钮恢复可用。未确认开工、未改变该任务状态，临时页已关闭，原审核页未动。
- 交付边界：迁移文件及 PostgreSQL 基线已提供，未在现有数据库执行升级；未变更角色授权、未执行真实 PostgreSQL 双请求并发或 NAS 开工/版本发布 E2E，未运行发布级全量构建。管理员须在上线时核对/补齐 `shotgrid_admin` 的 `shotgrid:task:start` 权限并刷新会话。
- 仍保留用户原有环境配置、部署模板、临时产物等变化。本次未提交、未推送。

### 实际执行的主要命令

后端目录（`LOG_FILE_ENABLED=false`，使用项目 `.venv/Scripts/python.exe`）：

```powershell
python -m pytest -q tests/module_shot_grid/test_task_service.py tests/module_shot_grid/test_task_vo.py tests/module_shot_grid/test_task_router.py tests/module_shot_grid/test_shot_crud_service.py tests/module_shot_grid/test_shot_crud_router.py tests/module_shot_grid/test_shot_crud_vo.py tests/module_shot_grid/test_shot_crud_dao.py tests/module_shot_grid/test_version_submission_service.py tests/module_shot_grid/test_migration_contract.py tests/cli/runtime/test_db.py -p no:cacheprovider --tb=short
python -m alembic heads
```

前端目录：

```powershell
npm.cmd test -- tests/unit/taskViews.spec.js tests/unit/shotViews.spec.js tests/unit/taskPresentation.spec.js tests/unit/shotPresentation.spec.js tests/unit/taskApi.spec.js --reporter=dot
npm.cmd test -- tests/unit/taskViews.spec.js tests/unit/shotViews.spec.js -t 开工 --reporter=dot
npx.cmd eslint src/views/shot/ShotDetailView.vue src/views/shot/ShotListView.vue src/views/shot/shotPresentation.js src/views/shot/components/ShotFormDialog.vue src/views/task/TaskDetailView.vue src/views/task/taskPresentation.js src/views/workbench/WorkbenchView.vue tests/unit/shotViews.spec.js tests/unit/taskViews.spec.js
```

Ruff check 和 format --check 的范围为本次 6 个 Python 业务文件、5 个测试文件及新增迁移文件。仓库根执行 `git diff --check` 通过；`python -m alembic heads` 只读返回唯一 `20260827_23 (head)`，不是已执行数据库升级的证明。

## 手动测试反馈：列表未自动更新（2026-08-27）

- 原因：任务详情已有状态轮询，但镜头列表和工作台没有接入；数据库任务已到 `in_progress`，旧列表仍显示 `preparing`。
- 修复：两处列表复用小型 Vue composable 和原列表 API，待开工镜头每 5 秒、目录准备每 1.5 秒刷新。保留筛选、分页、有效勾选和既有内容，编辑/写入期间暂停，切项目、筛选草稿改变或卸载时中止并隔离旧响应。
- 失败边界：目录准备每轮最多 80 次，连续 3 次错误或归一化 401/403/404 停止并保留人工刷新入口；当前结果没有等待/准备任务时停止。资产任务不自动开工。
- 测试先复现两个列表不更新，再验证修复；新增 12 项回归全部通过，覆盖状态与摘要更新、筛选草稿、编辑加载快照、跨项目 ABA、卸载、请求不重叠、失败停止与人工恢复、资产边界。两个相关文件完整运行结果为 74 通过、1 项既有拖拽用例失败（拖拽列在本次修改前已被注释）；不宣称完整测试通过。
- 定向命令：`npm.cmd test -- --run tests/unit/shotViews.spec.js tests/unit/taskViews.spec.js -t 列表自动刷新 --reporter=dot`。完整相关文件命令移除 `-t 列表自动刷新`。新增 composable、两个页面和两个测试文件的 ESLint 通过。本次只涉及前端，不需要后端重启或新增数据库迁移，未修改测试业务数据。
- 浏览器只读复核：临时打开项目 7 的镜头列表，`EP001 / 001 / S001` 显示“制作中”，检查后关闭临时页，未操作原标签页或修改业务状态。该证据只证明当前页面展示正确，状态自动过渡由上述组件回归用例验证，未执行完整真实 NAS E2E。
- 独立定向审查未发现可复现的 Critical/Important。实际静态检查命令为 `npx.cmd eslint src/composables/useTaskStatePolling.js src/views/shot/ShotListView.vue src/views/workbench/WorkbenchView.vue tests/unit/shotViews.spec.js tests/unit/taskViews.spec.js`，仓库根 `git diff --check` 通过；两项检查均未替代真实 NAS 全流程验收。

手工复测：先刷新浏览器加载新代码；管理人在镜头列表对一条“待开工”任务确认开工后停留原页，目录准备完成后应自动改为“制作中”；制作人的工作台保持打开时，待开工任务也应自动更新。编辑筛选但尚未查询、打开镜头弹窗时会暂停后台刷新，结束操作后恢复。无需因本次修复重启后端。
