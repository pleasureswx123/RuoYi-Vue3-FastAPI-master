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
- `package-lock.json`、lint、单元测试和生产构建脚本；
- 多阶段 Dockerfile 和 Nginx 模板，生产页面路径为 `/shot-grid-app/`，API 入口为 `/prod-api/`。

项目管理页已经调用真实后端，不在失败时回退 Mock。工作台、镜头、资产、版本审核、文件与 NAS 五个一级页面仍主要用于声明后续接入边界；Excel 导入、任务、版本、审核与文件等业务页面尚未完成。项目页代码存在不等于真实浏览器 E2E 已通过。

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

截至 2026-08-11，本批已执行通过 `npm.cmd run lint`、Vitest 3.2.7 的 13 个测试文件/44 个测试和 `npm.cmd run build:prod`。生产构建处理 1744 个模块，主入口为 317.35 kB；仅出现第三方依赖的 `PURE` 注释构建警告，没有构建失败。锁文件更新后使用 npm 官方审计接口复核为 0 个已知依赖漏洞。该结果证明本批静态、单元和生产构建门禁通过，但不能单独证明浏览器业务链或真实 NAS 可用。

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
