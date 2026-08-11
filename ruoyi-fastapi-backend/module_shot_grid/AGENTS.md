# Shot Grid 后端对齐结论

- 场次列表/创建冻结为 `/projects/{projectId}/episodes/{episodeId}/scenes`；场次详情、修改和归档保持项目下的 `/scenes/{sceneId}`。
- 资产制作分项列表/创建冻结为 `/projects/{projectId}/assets/{assetId}/items`；详情、修改、归档和任务分配使用 `/asset-items/{assetItemId}`。Controller/Service 必须重新校验父资源与 `projectId` 归属，不信任请求体父 ID。
- 集、场次、镜头、资产和制作分项归档统一为 `PUT .../archive` 并携带 `lockVersion`。

- D-05 媒体边界集中在 `ShotGridVersionSubmissionConfig`：镜头为 MP4/MOV、H.264/AVC、2 GiB、3840×2160、600 秒，资产为 JPEG/PNG、50 MiB、8192×8192，MVP 不生成代理。Service 必须校验扩展名、声明 MIME、文件签名及任务媒体类型；编码、尺寸、时长与播放兼容性由受控样本集成测试门禁验证。

- 版本发布使用平台私有 `sys_file_info` 和 `sys_file_reference`，不另建上传协议；初始化在
  `sg_version_submission` 冻结任务内版本号、服务端毫秒时间戳、业务文件名和幂等键。
- NAS 发布与正式短事务分离。正式事务失败只能重试原 submission，不重新分配冻结字段；NAS
  摘要冲突和同名目标存在属于不可自动覆盖的终止冲突。

- 存储目录异步执行以 PostgreSQL `sg_storage_operation` 为事实来源，使用行锁、`SKIP LOCKED` 和数据库租约；
  首版物理列 `lease_owner` / `lease_until` 在 ORM 中以 `locked_by` / `locked_until` 暴露，不修改既有数据库契约。
- `sg_storage_root.unc_root_path` 是唯一可用于执行 I/O 的管理员白名单根目录；项目完整路径快照不能替代当前根配置。
- NAS I/O 不得包含在领取或结算事务中。初始化只有对应初始化操作成功后才能将项目存储标记为 `ready`。
- 管理员诊断响应不得包含 `credential_ref`、根路径、目标路径或 Worker 标识。真实 SMB 验收必须在受控测试共享完成。
- 项目初始化目录固定包含 `ASSET/Character`、`ASSET/Environment`、`ASSET/Prop` 和 `VIDEO`；真实 SMB 验收按 `docs/shot_grid_smb_acceptance.md` 分开记录真实共享与临时目录结果。
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
- 正式版本入库必须在一次提交内写入版本、版本文件、`sys_file_reference`、自动审核单、任务状态和平台操作日志；任一写入失败先整体回滚，再把原 submission 恢复为 `published` 供安全重试。审核动作同步完成自动审核单并追加平台操作审计。
- 任务—版本—审核 Service 事务测试通过后可标记“后端闭环完成”，但真实 PostgreSQL 并发、文件/NAS 集成和浏览器 E2E 必须继续分别标记为未验证。

## 17. 已确认的人工审核单契约

- 人工审核单只能由项目总监在项目作用域内创建；候选版本必须同时属于当前项目、任务未删除，且任务与版本均为 `pending_review`。
- `sg_review_list_version` 是审核单版本集合及连续审核顺序的唯一事实来源；客户端排序必须提交完整的 `{ versionId, sortOrder }` 集合，并使用审核单 `lockVersion` 防止并发覆盖。
- 自动单版本审核单仍只允许在版本正式提交事务中创建，人工审核单接口不接受 `auto_single` 或 `autoVersionId`。

## 18. 已确认的工作台、搜索与文件发现契约

- `/shot-grid/workbench` 在后端按活动项目成员关系聚合我的任务、待审核、修改中、近期提交和项目摘要；前端不得读取全量业务表自行统计。
- `/shot-grid/search` 与 `/shot-grid/files` 统一使用 `pageNum`、`pageSize`、`keyword`、`orderByColumn`、`isAsc`，并在 SQL 查询阶段应用活动项目成员范围。
- 文件发现只返回业务文件元数据与受保护的版本文件下载入口。NAS 相对路径只向项目总监或跨项目管理员返回；没有已确认桌面协议前，客户端只允许查看和复制路径。

## 19. 已确认的制作聚合状态与概览契约

## 20. 已确认的项目创建发现契约

- 普通业务端通过 `/shot-grid/project-creation/storage-roots`、`users` 和 `path-preview` 获取项目创建选项；三者统一要求 `shotgrid:project:add` 平台权限。
- 根目录选项只包含启用、未删除且最近探测健康的白名单根；路径预览由后端规范化并检查占用，不向前端下发根路径供其自行拼接。
- 用户候选只包含有效启用账号及有效部门；提交时仍由创建事务重新校验，不能信任前端选项缓存。

- 镜头和资产制作分项统一使用 `no_task`、`not_started`、`in_progress`、`pending_review`、`revision`、`completed` 六态；`completed` 必须同时有 completed 唯一活动任务和 final 版本。
- 资产必须由全部活动制作分项的唯一活动任务聚合，优先级为 `revision`、`pending_review`、`in_progress`、`no_task`、`not_started`；至少有一个分项且全部完成才为 `completed`。
- 概览只统计未删除、未归档的集、场、镜头、资产和制作分项，并在 PostgreSQL 内聚合；整体进度固定按镜头与制作分项等对象权重计算，列表分页不得改变总统计。
- 镜头仅在所属集、场次和镜头本身均活动时参与概览，制作分项仅在所属资产与分项本身均活动时参与概览；归档父资源不能通过仍为活动状态的子记录污染统计。
- 工作台、搜索和文件发现的项目范围由“活动成员 + 未删除且未归档项目”共同确定；任务所属镜头或制作分项失效后也必须从发现结果排除。管理员身份不会绕过接口平台权限或自动扩大工作台项目范围。

## 21. 已确认的业务接口授权与拒绝契约

- 所有项目路径业务接口同时执行登录认证、独立 `shotgrid:*` 平台接口权限和实时项目访问校验；跨项目管理员范围只扩大项目数据范围，不替代动作权限。已移除成员返回 403，不存在或跨项目子资源统一返回 404，归档项目返回 409。
- 任务分配和改派只允许管理员或 `director`；开始任务允许管理员、`director` 或负责人本人；版本提交允许管理员、`director` 或负责人本人；审核动作只允许管理员或 `director`。普通活动成员只能执行明确开放的读取和意见回复动作。
- 分配、改派以及管理员或 `director` 代开始、代提交都必须记录实际操作人、目标负责人和非空原因；负责人本人开始或提交不标记为代操作。
- `episodeId`、`sceneId`、`shotId`、`assetId`、`assetItemId`、`taskId`、`versionId`、`reviewListId` 和 `fileId` 的 DAO 查询必须从同一 SQL 查询链限定 `projectId`；父资源已删除或归档时按资源不可见处理，不接受客户端提供的父级归属作为证明。
- 版本文件下载必须依次通过 `shotgrid:file:download`、活动项目成员或明确跨项目范围、项目/任务/版本/文件关系、`sys_file_reference` 的 `shot_grid_version` 引用以及平台显式 ACL deny 校验；任一资源关系不成立返回 404，显式 deny 返回 403。
- 401 仅表示未认证，403 表示已认证但平台或项目角色拒绝，404 用于隐藏跨项目 ID 和失效资源，409 表示归档、状态机或乐观锁等业务冲突。Controller 不得捕获这些拒绝并转换为空列表或成功响应。
