# Shot Grid 后端对齐结论

- 版本发布使用平台私有 `sys_file_info` 和 `sys_file_reference`，不另建上传协议；初始化在
  `sg_version_submission` 冻结任务内版本号、服务端毫秒时间戳、业务文件名和幂等键。
- NAS 发布与正式短事务分离。正式事务失败只能重试原 submission，不重新分配冻结字段；NAS
  摘要冲突和同名目标存在属于不可自动覆盖的终止冲突。

- 存储目录异步执行以 PostgreSQL `sg_storage_operation` 为事实来源，使用行锁、`SKIP LOCKED` 和数据库租约；
  首版物理列 `lease_owner` / `lease_until` 在 ORM 中以 `locked_by` / `locked_until` 暴露，不修改既有数据库契约。
- `sg_storage_root.unc_root_path` 是唯一可用于执行 I/O 的管理员白名单根目录；项目完整路径快照不能替代当前根配置。
- NAS I/O 不得包含在领取或结算事务中。初始化只有对应初始化操作成功后才能将项目存储标记为 `ready`。
- 管理员诊断响应不得包含 `credential_ref`、根路径、目标路径或 Worker 标识。真实 SMB 验收必须在受控测试共享完成。
- 镜头和资产制作分项各自只允许一个正常状态制作任务；首次分配创建任务，后续分配更新原任务，
  PostgreSQL 部分唯一索引与 Service 行锁/成员校验共同维护该不变量。
- 任务负责人必须是同项目活动成员且拥有项目内唯一的有效 `producer_code`；任务只能单归属镜头或资产制作分项。
- `start` 仅允许负责人本人、项目总监或管理员；代操作必须写入 `sg_task_history` 并保留实际操作人、目标负责人和原因。
- 任务版本查询只返回业务元数据和文件用途，不返回 `storage_key`、NAS 相对路径、服务器路径、AI 参数、提示词或成本。
- Shot Grid 版本文件只从项目/任务/版本/fileId 全链路专用接口访问；平台权限、实时项目访问、`sg_version_file` 与 `sys_file_reference` 归属及平台显式 deny 必须同时通过，并复用平台 Range 与审计流。
- 版本意见使用纯文本；创建意见和状态处理仅限项目总监，活动项目成员可回复。意见必须重复携带并校验 `versionId`；时间点为整数毫秒，标注坐标归一化且保存自然尺寸，VO 限制点数和 64 KiB 标注载荷。

## 审核动作已确认契约

- 版本最终状态和任务审核状态只能由 `approve`、`reject`、`defer` 具名接口改变，普通任务分配和版本查询接口不得接受状态字段。
- 三个动作固定按任务、任务全部版本的顺序加行锁，并校验项目归属、director 项目角色、平台权限、待审核状态和版本 `lockVersion`；冲突统一使用 HTTP 409 稳定领域错误。
- `reject` 的非空意见直接绑定当前版本的不可变 `sg_review_action`，版本进入 `rejected`、任务进入 `revision`；后续提交生成新版本，不修改旧版本、旧审核单、意见、回复和动作。
- `approve` 在同一事务中将其他历史 final 清为 rejected、当前版本设为唯一 final、任务设为 completed；`defer` 只递增锁并记录 pending_review → pending_review 动作。

## 17. 已确认的人工审核单契约

- 人工审核单只能由项目总监在项目作用域内创建；候选版本必须同时属于当前项目、任务未删除，且任务与版本均为 `pending_review`。
- `sg_review_list_version` 是审核单版本集合及连续审核顺序的唯一事实来源；客户端排序必须提交完整的 `{ versionId, sortOrder }` 集合，并使用审核单 `lockVersion` 防止并发覆盖。
- 自动单版本审核单仍只允许在版本正式提交事务中创建，人工审核单接口不接受 `auto_single` 或 `autoVersionId`。

## 18. 已确认的工作台、搜索与文件发现契约

- `/shot-grid/workbench` 在后端按活动项目成员关系聚合我的任务、待审核、修改中、近期提交和项目摘要；前端不得读取全量业务表自行统计。
- `/shot-grid/search` 与 `/shot-grid/files` 统一使用 `pageNum`、`pageSize`、`keyword`、`orderByColumn`、`isAsc`，并在 SQL 查询阶段应用活动项目成员范围。
- 文件发现只返回业务文件元数据与受保护的版本文件下载入口。NAS 相对路径只向项目总监或跨项目管理员返回；没有已确认桌面协议前，客户端只允许查看和复制路径。

## 19. 已确认的制作聚合状态与概览契约

- 镜头和资产制作分项统一使用 `no_task`、`not_started`、`in_progress`、`pending_review`、`revision`、`completed` 六态；`completed` 必须同时有 completed 唯一活动任务和 final 版本。
- 资产必须由全部活动制作分项的唯一活动任务聚合，优先级为 `revision`、`pending_review`、`in_progress`、`no_task`、`not_started`；至少有一个分项且全部完成才为 `completed`。
- 概览只统计未删除、未归档的集、场、镜头、资产和制作分项，并在 PostgreSQL 内聚合；整体进度固定按镜头与制作分项等对象权重计算，列表分页不得改变总统计。
