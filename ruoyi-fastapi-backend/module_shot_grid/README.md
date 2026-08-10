# Shot Grid 后端模块

## 当前边界

本模块是 Shot Grid 业务后端的 PostgreSQL 领域基础。首批交付包含：

- 22 张 `sg_` 领域表对应的 SQLAlchemy DO；
- 项目成员范围与项目角色权限依赖；
- 受平台角色菜单授权约束的 `GET /shot-grid/navigation`；
- PostgreSQL Alembic 首迁移、初始化 SQL、菜单、权限按钮和字典种子；
- 元数据、导航和项目权限的针对性测试。

当前批次不包含项目 CRUD、NAS 实际目录操作、Excel 导入、任务状态动作、版本发布和审核闭环。上述能力必须在后续批次通过 Service 事务和业务测试实现，不能直接使用通用 CRUD 绕过状态机。

## 分层

```text
controller → service → dao → entity/do
                    ↘ entity/vo

接口权限
  → PreAuthDependency
  → UserInterfaceAuthDependency
  → ProjectAccessDependency
  → ProjectRoleDependency
  → Service/DAO 资源归属复核
```

业务 API 使用 `/shot-grid` 前缀，权限码使用 `shotgrid:<resource>:<action>`。Shot Grid 表只承诺 PostgreSQL，用户和受保护文件继续复用 `sys_user`、`sys_file_info` 与 `sys_file_reference`。模块只在 `DB_TYPE=postgresql` 时把领域 DO 注册到平台 `Base.metadata`，避免 MySQL 启动链错误创建不兼容的部分索引和 PostgreSQL `CHECK`。

## 数据库交付路径

- 已有 RuoYi PostgreSQL 基线库：执行 Alembic `upgrade head`。
- 新数据库：执行同步后的 `sql/ruoyi-fastapi-pg.sql`，脚本会直接建立最新结构并写入当前 Alembic 版本。

当前仓库尚无完整平台 Alembic baseline，因此不能把 Shot Grid 增量 revision 描述为能够从真正空库独立建立全部 RuoYi 平台表。
