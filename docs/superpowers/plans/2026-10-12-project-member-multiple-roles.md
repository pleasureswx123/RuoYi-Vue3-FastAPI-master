# 项目成员多角色实施计划

按用户“开始修改代码”的指示，在当前会话和工作区直接实施，保留既有修改，不提交或部署。

设计：../specs/2026-10-12-project-member-multiple-roles-design.md。

## 全局约束

PostgreSQL、关联表作为角色事实来源、兼容单值请求、平台权限与项目身份共同校验。中文文档和注释，沿用 Element Plus 表单与现有事务、审计、缓存边界。

## 实施步骤

- [x] 契约与数据：新增 `tests/module_shot_grid/test_member_multiple_roles.py`，先验证数组规范化、旧请求、空数组、冲突字段和访问集合；修改 `entity/vo/project_member_vo.py`、`access_vo.py` 和 `entity/do/project_do.py`；新增 PostgreSQL Alembic 迁移并同步初始化 SQL。
- [x] 后端链路：修改成员 DAO/Service、项目初始化、角色同步查询、制作人选项、任务及审核等所有单值角色判断。使用关联表 EXISTS 条件避免分页重复；同步永久删除顺序、身份响应与审计。
- [x] 前端：修改 `ProjectMemberPanel.vue` 的数组表单和标签，统一项目身份判断，覆盖项目创建、制作人选择以及任务入口。增加真实组件多选保存与回显测试。
- [x] 交付验证：运行后端角色、成员、任务/审核定向测试，前端相关单测与构建，静态检查；隔离环境可用时验证 PostgreSQL 迁移和浏览器核心路径。更新作用域 AGENTS 与正式契约。

## 审查重点

1. 双角色移除 creator 且仍有任务时必须拒绝；增加 director 不拒绝。
2. 双角色仍计入最后管理人保护。
3. 平台角色依赖跨项目合并且不能撤回外部绑定。
4. 角色关系为空时不得从旧投影恢复权限。
5. 新旧字段同时传入、已移除成员、项目初始化重合用户与降级数据丢失风险。

## 验证命令

后端使用 `.venv/Scripts/python.exe -m pytest` 指定直接相关文件；前端使用 `npm.cmd exec vitest run` 指定相关组件测试，`npm.cmd run build` 按 package.json 实际脚本执行。静态检查仅本次文件，最后执行 `git diff --check`。

验证结果及未运行边界见同目录 `2026-10-12-project-member-multiple-roles-verification.md`。
