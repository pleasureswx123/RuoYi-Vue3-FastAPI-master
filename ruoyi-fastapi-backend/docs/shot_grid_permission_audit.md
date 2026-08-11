# Shot Grid 业务接口权限审计契约

## 结论

`module_shot_grid/controller/` 下的受保护路由统一由 `PreAuthDependency` 验证登录态，并在动作路由上声明独立的 `UserInterfaceAuthDependency`。包含 `{projectId}` 的路由还必须注入 `ProjectAccessDependency`；总监动作使用 `ProjectRoleDependency('director')`，跨项目管理员仍须拥有当前动作的平台权限。

| 接口域 | 平台权限 | 项目访问 | 项目角色/负责人 |
| --- | --- | --- | --- |
| 项目、概览、资源、任务、版本查询 | 对应 `list/query/overview` | 活动成员或 `project:all` | 活动成员可读 |
| 成员、导入、待匹配处理、审核单和审核动作 | 对应 `add/edit/remove/import/resolve/review:*` | 活动成员或 `project:all` | 仅 `director` 或管理员 |
| 任务分配/改派 | `shotgrid:task:assign` | 活动成员或 `project:all` | 仅 `director` 或管理员，记录操作人、目标负责人、原因 |
| 任务开始 | `shotgrid:task:start` | 活动成员或 `project:all` | 负责人本人；`director`/管理员可代操作并记录原因 |
| 版本提交/重试 | `shotgrid:version:submit/retry` | 活动成员或 `project:all` | 负责人本人；`director`/管理员可代提交并记录原因 |
| 版本审核 | `shotgrid:review:approve/reject/defer` | 活动成员或 `project:all` | 仅 `director` 或管理员 |
| 版本文件下载 | `shotgrid:file:download` | 实时活动成员或 `project:all` | 还须通过版本文件关系、业务引用和 ACL deny |

## ID 范围与防枚举

所有从路径或查询条件取得的 `episodeId`、`sceneId`、`shotId`、`assetId`、`assetItemId`、`taskId`、`versionId`、`reviewListId`、`fileId`，必须由 DAO 在同一查询中同时限定 `projectId`。子资源的集、场、镜头、资产或制作分项父链失效时，不能仅凭子表仍为活动状态继续返回数据。

版本文件专用下载链必须同时满足：

1. 项目、任务、版本和 `sg_version_file.file_id` 属于同一项目链；
2. 存在 `sys_file_reference.business_type = 'shot_grid_version'` 且 `business_id` 为当前版本 ID 的引用；
3. 平台文件记录有效、未删除、未过期且为私有本地文件；
4. 当前用户、角色或部门没有命中的显式 ACL `deny`。

## 拒绝响应

- **401**：Token 缺失、无效或登录态失效；
- **403**：已认证但缺少平台接口权限、活动项目成员关系、项目角色或负责人资格，ACL deny 也返回 403；
- **404**：项目/子资源不存在，或 ID 属于另一项目、父资源失效，需要防止 ID 枚举；
- **409**：项目归档、状态机冲突、重复动作、乐观锁或并发唯一性冲突；
- **422**：请求字段或代操作原因缺失等输入契约错误。

Controller 不得捕获授权和领域异常后返回空列表、`null` 或成功 envelope；领域异常保留真实 HTTP 状态并返回稳定 `errorKey`。
