# Shot Grid 独立业务前端

`shot-grid-frontend` 是面向 AI 影视项目成员和项目总监的独立业务应用。它复用 RuoYi FastAPI 的认证、用户、权限、传输加密和 Shot Grid 业务接口，但不复制用户、角色、菜单、字典等系统管理页面。

## 当前交付范围

第一批已经实现：

- Vue 3、Vite、Pinia、Vue Router、Axios、Element Plus 和 Sass 独立工程；
- 自有登录页及真实 `GET /captchaImage`、`POST /login`、`GET /getInfo`、`POST /logout` 调用；
- `GET /shot-grid/navigation` 范围导航和六项本地白名单路由；
- 统一请求、传输加密、重复提交保护、401 会话清理和 `ApiError`；
- 独立业务布局、基础主题、403、404 和 5xx 页面；
- 项目范围列表、创建、详情与真实概览、编辑、归档、成员维护、存储状态和目录操作诊断页面；
- 健康 NAS 根目录选项、无副作用路径预览和安全平台成员候选查询；
- 镜头真实列表与项目/集/场次/状态/制作人筛选、服务端分页、表格/卡片/故事板三视图和详情深链；
- 镜头创建/编辑/归档、唯一任务首次分配/改派，以及项目内制作人安全选项；
- 镜头 Excel 模板下载、上传预检、工作簿与行级问题展示、跨 Sheet 行选择、幂等正式提交和结果回显；
- 通过统一鉴权请求获取受保护缩略图 Blob，并在取消、切换和卸载时释放 Object URL；
- `package-lock.json`、lint、单元测试和生产构建脚本；
- 多阶段 Dockerfile 和 Nginx 模板，生产页面路径为 `/shot-grid-app/`，API 入口为 `/prod-api/`。

项目管理页与镜头管理页已经调用真实后端，不在失败时回退 Mock。工作台、资产、版本审核、文件与 NAS 四个一级页面仍主要用于声明后续接入边界；资产导入、独立任务页、版本、审核和文件等业务页面尚未完成。项目管理子集和镜头管理/镜头 Excel 导入子集均已在隔离真实 PostgreSQL、Redis、平台账号和生产 Nginx 下完成浏览器旅程，但这两个子集都不等于完整系统 E2E 或真实 NAS 验收。

## 环境要求

- Node.js：`^18.0.0 || ^20.0.0 || >=22.0.0`
- npm
- 联调时需要真实启动 `ruoyi-fastapi-backend`、PostgreSQL 和 Redis

## 本地开发

```powershell
cd shot-grid-frontend
npm.cmd ci
npm.cmd run dev
```

开发服务器默认监听 `5174`。浏览器请求使用 `/dev-api` 前缀，Vite 会剥离该前缀并转发到 `VITE_APP_PROXY_TARGET`；未配置时默认使用 `http://127.0.0.1:9099`。

## 检查与构建

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run build:prod
```

截至 2026-08-11，本批已执行通过 `npm.cmd run lint`、Vitest 3.2.7 的 18 个测试文件/66 个测试和 `npm.cmd run build:prod`，生产构建处理 1757 个模块。后端 Ruff check/format 覆盖 163 个 Python 文件并通过，10 个定向测试文件为 78 passed；完整 `tests/module_shot_grid` 为 465 passed、2 skipped，跳过项源于当前 Windows 账号没有创建符号链接权限。镜头管理与镜头 Excel 导入子集也已完成真实后端、隔离 PostgreSQL/Redis、平台账号、生产 Nginx 和 Chrome 浏览器旅程；该子集证据不能外推为真实 NAS 可用或完整系统 E2E。

## 生产部署路径

生产环境变量固定：

```text
页面基路径：/shot-grid-app/
API 前缀：  /prod-api
```

仓库已提供 `Dockerfile` 与 `nginx/default.conf.template`。反向代理必须同时满足：

1. 将 `dist/` 作为 `/shot-grid-app/` 的静态内容，并让前端路由回退到 `/shot-grid-app/index.html`；
2. 将 `/prod-api/...` 代理到 RuoYi FastAPI，并剥离 `/prod-api` 前缀。

核心 Nginx 语义如下；实际模板还包含代理来源头、上传请求流式转发和超时配置，后端地址由 `BACKEND_UPSTREAM` 注入：

```nginx
location /shot-grid-app/ {
    root /srv/www;
    try_files $uri $uri/ /shot-grid-app/index.html;
}

location /prod-api/ {
    proxy_pass http://127.0.0.1:9099/;
}
```

末尾带 `/` 的 `proxy_pass` 使 `/prod-api/getInfo` 转发为后端 `/getInfo`。页面路径 `/shot-grid-app/` 不得与后端业务 API 前缀 `/shot-grid` 混用。本批生产镜像已构建成功，真实运行时 `/shot-grid-app/` 与项目详情深链均返回 200 `text/html`，`/prod-api/captchaImage` 返回 200 JSON，证明 SPA 回退和 API 前缀剥离在该隔离环境中正确。

PostgreSQL 完整拓扑中已增加独立业务前端服务，默认映射宿主机 `12581`。在仓库根目录执行：

```powershell
docker compose -f docker-compose.pg.yml build shot-grid-frontend
docker compose -f docker-compose.pg.yml up -d shot-grid-frontend
```

待服务真实启动后，入口应为 `http://127.0.0.1:12581/shot-grid-app/`。容器启动、页面可打开或构建成功都不能替代登录、项目写入、Redis 会话、深链刷新和反向代理前缀剥离的浏览器验证。

## 项目管理接口边界

- 项目列表按成员范围查询；具备 `shotgrid:project:all` 时，只有显式选择“全部项目”才提交 `scope=all`。
- 创建项目先读取 `GET /shot-grid/storage-roots/options`，再调用 `POST /shot-grid/storage-roots/{storageRootId}/project-path-preview`。路径预览不写数据库、不创建目录，创建事务仍会重新校验根目录与冲突。
- 创建项目时从 `GET /shot-grid/member-candidates` 选择初始成员；已创建项目添加成员时改用 `GET /shot-grid/projects/{projectId}/member-candidates`。后者额外要求项目总监角色和成员添加权限；两者均应用平台 `SysUser` 数据范围，只返回有效平台账号的用户、昵称、头像和部门摘要，不返回密码、联系方式或认证字段。
- 创建请求携带 `X-Idempotency-Key`；HTTP 202 只表示项目和 NAS 初始化任务已受理，页面显示初始化中，并从项目详情/存储接口读取后续状态。
- 详情页按后端 `allowedActions`、平台权限和项目角色控制编辑、归档、成员与存储操作。普通编辑不允许修改项目代号、NAS 绑定或业务状态。
- 存储页只在后端授权时展示路径快照，并提供复制、目录操作诊断和人工重试。浏览器不承诺直接打开 UNC 路径。

数据库中人工设置或隔离测试使用的 `lastProbeStatus=healthy` 只满足项目页面选择条件，不能证明 Windows Worker 已以正式服务账号访问、创建或写入真实 SMB/UNC 共享。真实 UNC/NAS Worker、NAS/AD/共享 ACL 和故障恢复仍需独立验收。

## 镜头管理与 Excel 导入边界

- 镜头列表通过同一个 `GET /shot-grid/projects/{projectId}/shots` 响应驱动表格、卡片和故事板；项目切换、集/场次联动、状态、制作人、关键字、排序和服务端分页不为不同视图复制数据源。切换项目会取消旧请求、关闭创建/导入弹窗，并清空旧项目的预检 Token、幂等键、选中行和问题明细。创建、导入、编辑和分配操作还用 `operationGeneration` 区分每次弹窗实例；同一 ID 切走再返回并重开时，旧实例迟到事件不得关闭新弹窗或触发新上下文刷新。
- `GET /shot-grid/projects/{projectId}/shot-assignee-options` 使用 `pageNum/pageSize/keyword` 分页，只返回后端判定可分配的活动项目成员安全摘要；前端候选列表和按钮显隐不替代写接口权限、项目角色和成员状态复核。
- 镜头详情聚合基础字段、关联资产、唯一任务、最新版本/反馈和后端 `allowedActions`；创建/编辑、首次分配/改派、归档均调用真实接口并保留乐观锁字段。
- 缩略图只接受 `/shot-grid/versions/{versionId}/files/{fileId}/download` 形式的受保护相对路径，通过统一请求层获取 Blob；403/404 显示安全占位，取消、切换或组件卸载时中止请求并释放临时 Object URL，不把鉴权 URL 当公开图片地址。
- 模板由鉴权 `GET /shot-grid/imports/shots/template` 返回 XLSX 二进制和 `X-Shot-Grid-Template-Version: shot-v1`。后端匿名副本 SHA-256 为 `F6370BBB14548B645782ABF0734E930EC10470565821BA6C8FD1B6A2D9D96EE0`：只改动 workbook、sharedStrings 和 3 个 docProps XML，删除 `x15ac:absPath`，把 88 条共享字符串替换为表头、合法编号、制作人 A-C 和示例文本，匿名化作者/应用属性并清空自定义属性；其余 13 个条目（含两个 Sheet、styles、theme）字节不变，解析仍为 total 24、valid 24、warning 0、error 0、2 集、8 场、24 镜头。
- 上传 `.xlsx` 后先调用 preview。弹窗按 Sheet 展示工作簿级与行级错误/警告，只允许勾选 `canImport=true` 行；commit 使用 `selectedRows[{sheetName,rowNumber}]` 和当前弹窗内稳定的 `X-Idempotency-Key`，展示后端耐久提交结果。明文预检 Token 与幂等键只留在组件内存，不写 localStorage、日志或 URL。
- 项目为 `completed` 或 `archived` 时，前端隐藏集、场次、镜头和镜头导入写入口；后端对应路径返回 HTTP 409 / `SG_INVALID_STATE_TRANSITION`。当前终态治理只明确覆盖项目自身、集、场次、镜头与镜头导入，不能外推为资产、成员、任务、版本、审核、文件或目录操作等全域写接口均已治理。
- 镜头创建和导入仍要求项目 `storageStatus=ready`。隔离测试中的逻辑 ready 只解除业务 Service 门禁；当目录 Worker 关闭时，它不证明真实 UNC/NAS 目录存在、可写，也不验证 Windows 服务账号或共享 ACL。

## 2026-08-11 项目管理子集验证

本批使用由当前 PostgreSQL 初始化基线创建的隔离数据库（Alembic head `20260811_06`）、隔离 Redis DB 15、真实 FastAPI 后端、真实平台 `admin` 账号和生产 Nginx 镜像完成以下浏览器旅程：

```text
登录
→ 六项业务导航
→ 健康根目录选项与路径预览
→ 创建项目，HTTP 202
→ 项目详情与真实概览
→ 项目详情深链刷新
→ 编辑项目，HTTP 200
→ 查询成员候选
→ 添加、修改、软移除成员，均 HTTP 200
→ 查看存储操作详情
→ 归档项目，HTTP 200
→ 归档列表回查
→ 退出，HTTP 200
→ 再访问详情深链时回到带 redirect 的登录页
```

数据库终态为：项目 `archived`、`lockVersion=2`；管理员成员仍为 `active`；测试制作人员已软移除且最后制作人缩写为 `NG2`；项目存储仍为 `initializing`，`initialize_project` 操作仍为 `pending`；项目与成员写操作产生 6 条同事务审计记录。退出后 Redis DB 15 中 `access_token:*` 为 0。

这是一条真实后端、数据库、Redis、账号和生产代理参与的“项目管理子集浏览器旅程”，不是完整 Shot Grid 系统 E2E。测试存储根是隔离数据库中的逻辑 `healthy` 夹具 `\\127.0.0.1\shot-grid-e2e`，目录 Worker 保持关闭；未连接真实 SMB 共享，也未使用正式 Windows/NAS 服务账号执行目录创建、写探针、ACL 或故障恢复验收。因此不能据此宣称 NAS 已可用或系统已生产就绪。

## 2026-08-11 镜头管理与镜头 Excel 导入子集验证

本批另以隔离 PostgreSQL、Redis DB 15、真实 FastAPI/平台账号、生产 Nginx 和 Chrome 执行最终 `operationGeneration` 版本的浏览器旅程：

```text
下载模板：11883 bytes，SHA-256 命中冻结值
→ preview UI：24/24，warningRows=0，errorRows=0，2 集/8 场/24 镜头
→ EP001、EP002 各 12 行，选中全部 24 行
→ commit HTTP 200：首次提交 idempotentReplay=false
→ 创建 2 集、8 场、24 镜头、24 任务、24 待匹配需求、26 条目录操作
→ 表格、卡片、故事板各显示 24 条；EP002 筛选显示 12 条
→ 场次筛选包含 000/001/002/003
→ 详情深链及刷新显示 EP002/000/S001 和“晓亮/XL”任务
→ 浏览器控制台 0 error/0 warning
→ 退出后访问详情深链，回到带 redirect 的登录页
```

数据库核验为 2 集、8 场、24 镜头、24 任务（三名制作人各 8）、24 待匹配需求、0 镜头资产关系、1 个 `committed` 导入批次、镜头时长合计 79000 ms；结果复用集/场均为 0、资产关系为 0。2 条集目录操作和 24 条镜头目录操作均为 `pending`；同事务审计恰 1 条且 `status=0`，`method` 字符串长度 79，未超过字段上限。Redis 预检键提交后为 0。

该旅程只关闭镜头管理与镜头 Excel 导入子集浏览器门禁。项目使用逻辑 `storageStatus=ready` 夹具，目录 Worker 关闭，所以未创建物理目录，也未验证真实 UNC/SMB/NAS 服务账号、共享 ACL、写探针或故障恢复。验收后已关闭浏览器和后端 PID 12996，删除临时 Nginx 容器/镜像、隔离数据库、Redis DB 15 数据及临时文件；18080/19098 端口空闲，原 9099 服务、PostgreSQL 服务及其他数据库和 Redis 其他 DB 未改动。

## 认证与导航契约

- Token Cookie 名为 `Admin-Token`，`path=/`；请求通过统一 Axios 实例添加 Bearer Token。
- `/getInfo` 后端使用不含 `password` 的专用安全用户 VO；前端 Pinia 只保存必要身份摘要、角色、权限和导航。
- 范围导航只接受以下固定映射：

| `routeKey` | 本地路径 | 页面 |
| --- | --- | --- |
| `workbench` | `/workbench` | 工作台 |
| `projects` | `/projects` | 项目 |
| `shots` | `/shots` | 镜头管理 |
| `assets` | `/assets` | 资产库管理 |
| `reviews` | `/reviews` | 版本审核 |
| `files` | `/files` | 文件与 NAS |

未知键、重复键和路径不匹配项会被拒绝，后端响应不能注入 Vue 组件路径。前端导航和按钮只改善体验，后端接口权限、项目成员、项目角色和资源归属仍是最终授权边界。

## 错误边界

统一 `ApiError` 保留 `httpStatus`、响应体 `code`、`errorKey` 和 `details`：

- 401：清理本地会话并回登录；
- 403：显示无权限，不伪装成 404；
- 404：显示资源或页面不存在；
- 409、413、416：保留可区分的冲突、超限和 Range 错误；
- 5xx 或初始化网络故障：进入服务异常页，不回退为空数据或 Mock。

业务契约和后续实施边界见 `docs/领域模型与API契约.md`、`docs/项目完成计划.md` 和 `docs/若依基座分析与实施方案.md`。
