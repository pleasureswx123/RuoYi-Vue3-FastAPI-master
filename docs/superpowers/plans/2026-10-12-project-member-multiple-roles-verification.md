# 项目成员多角色验证与交付记录

## 已实现

关联表、PostgreSQL 迁移、角色数组接口、成员/项目/任务/审核身份判断、平台角色依赖集合、成员多选与标签回显、项目创建角色合并、作用域规则和 API 契约均已更新。独立审查发现的配置刷新嵌套数组及跨项目管理员真实制作身份丢失问题已修复。

## 已执行验证

- 后端 `python -m pytest tests/module_shot_grid --ignore=tests/module_shot_grid/test_asset_manager_start_pg.py -q --tb=short`：1247 通过、97 跳过、1 失败。该次包含新 PG 两项；随后已统一到仓库显式环境开关，单独开启并重跑两项，均通过。
- PostgreSQL `SHOT_GRID_RUN_PG_TESTS=1` + `python -m pytest tests/module_shot_grid/test_member_multiple_roles_pg.py -q --tb=short`：2 通过，随机隔离库已清理。验证升级回填、双角色筛选与别名查询、跨项目角色依赖、降级拒绝及可逆单角色降级、并发撤销管理人只允许一项成功。
- 前端 `npm.cmd exec -- vitest run tests/unit/projectViews.spec.js tests/unit/projectPresentation.spec.js tests/unit/memberCandidateSelect.spec.js --reporter=dot`：37 通过；含真实 ElSelect 多选点击、保存、标签与再次编辑回显、空选择校验和配置刷新。
- 前端 `npm.cmd run test -- --reporter=dot`：779 通过、17 失败、2 个未处理错误。使用 HEAD 文件构建独立前端对照副本复跑失败的六个文件：17 项失败全部复现，失败名称一致；未处理错误为 document is not defined。
- 前端 `npm.cmd run build:prod`：通过，存在大 chunk 提示。
- 本次 Python 文件 Ruff check/format、前端改动文件 ESLint 与 `git diff --check`：通过（Git 有既有换行提示）。

## 未通过项

后端 `test_nas_mount_resolver.py::test_directory_worker_uses_mapped_unc_without_enabling_test_local_root` 报 NAS 项目目录冲突；该目录适配器未在本次修改，未将此失败掩盖或调整安全边界。

前端改动前代码同样失败的用例：

- tests/unit/batchShotStartDialog.spec.js > 镜头批量开工 > 统一补齐未排期项后保留选择，沿用成功响应的新版本确认开工
- tests/unit/batchShotStartDialog.spec.js > 镜头批量开工 > 独立排期模式不提供开工动作，部分失败保留逐项结果
- tests/unit/batchShotStartDialog.spec.js > 镜头批量开工 > 行内排期支持统一应用后逐行微调，只在最终保存时写入
- tests/unit/batchShotStartDialog.spec.js > 镜头批量开工 > 单项排期入口 single=true 只展示一个时间组件，直接校验保存
- tests/unit/batchShotStartDialog.spec.js > 镜头批量开工 > 单项排期入口 single=false 只展示一个时间组件，直接校验保存
- tests/unit/personnelSwimlane.spec.js > 人员泳道任务条 > not_started 在泳道和甘特图使用一致的状态色及文字
- tests/unit/scheduleGanttRuntime.spec.js > SVAR OSS 真实运行门禁 > 把项目主题变量桥接到真实甘特组件的背景和边框契约
- tests/unit/shotViews.spec.js > 镜头管理真实列表页 > 开工窗口展示制作人、完整内容及预期时间范围，未填写不能开工
- tests/unit/shotViews.spec.js > 镜头管理真实列表页 > 视图 切换立即清空表格选择，响应返回后不恢复旧选择
- tests/unit/shotViews.spec.js > 镜头管理真实列表页 > table 视图镜头开工先确认人工核对结果，选择 confirm 后按预期处理
- tests/unit/shotViews.spec.js > 镜头管理真实列表页 > storyboard 视图镜头开工先确认人工核对结果，选择 confirm 后按预期处理
- tests/unit/shotViews.spec.js > 镜头管理真实列表页 > 旧项目开工请求完成后不刷新或覆盖新项目镜头
- tests/unit/taskStage.spec.js > 待排期与待开工统一派生阶段 > 制作履历阶段条及当前待办跟随排期变化
- tests/unit/taskViews.spec.js > 真实任务工作台 > 任务类型、状态、截止日期、优先级与最近版本使用 ElTag 动态类型
- tests/unit/taskViews.spec.js > 任务详情、状态动作与异步上下文 > 制作人任务详情完整展示镜头制作信息，并区分任务补充要求
- tests/unit/taskViews.spec.js > 先排期再确认开工 > 未排期不能开工；单独保存后使用新版本开工且不重复提交时间
- tests/unit/taskViews.spec.js > 先排期再确认开工 > 取消改期或保存失败保留原排期和版本

## 生效与交付边界

- 已于 2026-10-12 备份并迁移本地开发数据库至 `20261012_37`，将四名成员原角色原样回填，未新增或改变成员身份；未部署生产、未提交 Git。
- 上线/本地业务环境启用前，备份数据库并停止旧写服务，在后端环境执行 `alembic upgrade head`（目标 `20261012_37`），同步启动新后端和新前端；不要让旧后端与新后端混跑。
- 保留用户已有 env、部署、Excel 导入等改动。完整认证业务浏览器 E2E 未执行；组件交互、隔离 PostgreSQL 与构建通过不能替代完整 E2E。

## 本地空角色问题修复

- 根因：后端重启时自动建表已创建关联表，但数据库仍为 `20260930_36`，未运行旧角色回填。
- 迁移兼容已提前创建的同构表，校验字段、主键、外键、约束及索引后，仅回填完全没有关联角色的成员，不覆盖已有角色集合。
- 定向 PostgreSQL 测试先复现重复建表失败，修复后两项通过；Ruff check 通过并已格式化。
- 备份为后端 `output/backups/member-roles-20261012-114040.dump`，已校验归档目录及 SHA-256，配套 JSON 保存迁移前角色清单。
- 已执行 `python -m alembic upgrade 20261012_37`；只读核对版本、四条新关联及旧角色投影均与备份一致。
- 实际浏览器刷新项目 16 后显示两名项目管理人、两名制作人员；打开 QZF 编辑弹窗确认原角色回显后取消，未提交真实权限修改。这是定向页面验证，不代表完整业务 E2E。


## 创建者保护增量验证（20261012_38）

- 后端：`SHOT_GRID_RUN_PG_TESTS=1` 配合 `python -m pytest tests/module_shot_grid/test_member_multiple_roles_pg.py tests/module_shot_grid/test_project_member_service.py tests/module_shot_grid/test_project_create_service.py tests/module_shot_grid/test_project_member_dao_scope.py tests/module_shot_grid/test_schema_metadata.py -q --tb=short`，40 项通过。覆盖真实迁移、创建者置顶、账号改名身份保留、默认入组及创建者不可移除/降级。
- 补充允许创建者增减制作身份及创建审计后，复跑 `python -m pytest tests/module_shot_grid/test_project_member_service.py tests/module_shot_grid/test_project_create_service.py -q --tb=short`，19 项通过。
- 前端：`npm.cmd exec -- vitest run tests/unit/projectViews.spec.js --reporter=dot`，27 项通过；真实 ElSelect 验证管理人选项禁用且不能取消，制作角色可追加保存。
- 本次文件 Ruff check、Ruff format、`npm.cmd exec -- eslint src/views/project/components/ProjectMemberPanel.vue tests/unit/projectViews.spec.js` 及 `git diff --check` 通过；未重复全量构建及全量 E2E。
- 本地备份 `ruoyi-fastapi-backend/output/backups/project-creator-20261012-131202.dump` 已验证 PGDMP、pg_restore 目录及 SHA-256 清单。执行 `python -m alembic upgrade 20261012_38` 成功；数据库只读复核项目 16 创建者为用户 110，五条原角色关系保持不变。
- 实际页面已显示 LQH 创建者置顶、隐藏移除；编辑弹窗管理人已选中且禁用，无删除标签入口。打开后取消，未保存真实角色修改。截图：后端 `output/project-creator-protection.png`。
- 变更只应用本地开发环境，未提交 Git、未部署生产；生产需独立备份并执行 38 迁移。无法唯一确认身份的历史项目保留空创建者，不自动扩权；当前本地项目已唯一匹配。


## 本次生产发布门禁

- 发布使用 `./deploy/remote-deploy.ps1 -NpmRegistry https://registry.npmjs.org -StopBackendForMigration`。该显式选项在镜像准备完成后、数据库备份前停止旧后端；迁移失败保持停写，不自动启用与新数据结构不兼容的旧写服务。默认部署行为不变。
- 发布前只读检查生产库为 `20260930_36`，两个活动项目的创建者都唯一匹配到活动管理人，满足 38 迁移条件。
- 本次后端模块全量 1249 通过、165 跳过、1 项既有 NAS 目录冲突失败；对应测试及目录适配器与 HEAD 无差异。真实 PG 迁移与创建者服务定向复测 22 通过。前端全量 ESLint 通过，48 个已暂存 Python 文件 Ruff check/format 通过。
- 未提交环境文件、Excel 导入相关改动、截图、备份或本地 output；发布只构建已提交内容。
