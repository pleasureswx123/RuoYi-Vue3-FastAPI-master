# Shot Grid 独立业务前端

`shot-grid-frontend` 是面向 AI 影视项目成员和项目总监的独立业务应用。它复用 RuoYi FastAPI 的认证、用户、权限、传输加密和 Shot Grid 业务接口，但不复制用户、角色、菜单、字典等系统管理页面。

## 当前交付范围

第一批已经实现：

- Vue 3、Vite、Pinia、Vue Router、Axios、Element Plus 和 Sass 独立工程；
- 自有登录页及真实 `GET /captchaImage`、`POST /login`、`GET /getInfo`、`POST /logout` 调用；
- `GET /shot-grid/navigation` 范围导航和六项本地白名单路由；
- 统一请求、传输加密、重复提交保护、401 会话清理和 `ApiError`；
- 独立业务布局、基础主题、403、404 和 5xx 页面；
- `package-lock.json`、lint、单元测试和生产构建脚本。

工作台、项目、镜头、资产、版本审核、文件与 NAS 六个页面目前只建立路由和实施边界，页面明确显示“业务数据功能待接入、未使用 Mock 数据”。项目 CRUD、Excel 导入界面、任务、版本、审核和文件业务页面尚未完成。

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

开发服务器默认监听 `5174`。浏览器请求使用 `/dev-api` 前缀，Vite 会剥离该前缀并转发到 `http://127.0.0.1:9099`。

## 检查与构建

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run build:prod
```

截至 2026-08-11，上述三条命令已执行通过，其中单元测试为 24 个。该结果只证明静态检查、单元级契约和生产产物生成成功；尚未使用真实后端、PostgreSQL、Redis 和平台账号完成登录、刷新恢复、撤权、会话过期与退出的浏览器 E2E。

## 生产部署路径

生产环境变量固定：

```text
页面基路径：/shot-grid-app/
API 前缀：  /prod-api
```

反向代理必须同时满足：

1. 将 `dist/` 作为 `/shot-grid-app/` 的静态内容，并让前端路由回退到 `/shot-grid-app/index.html`；
2. 将 `/prod-api/...` 代理到 RuoYi FastAPI，并剥离 `/prod-api` 前缀。

示意 Nginx 配置如下；静态根目录和后端地址应按部署环境调整：

```nginx
location /shot-grid-app/ {
    root /srv/www;
    try_files $uri $uri/ /shot-grid-app/index.html;
}

location /prod-api/ {
    proxy_pass http://127.0.0.1:9099/;
}
```

末尾带 `/` 的 `proxy_pass` 使 `/prod-api/getInfo` 转发为后端 `/getInfo`。页面路径 `/shot-grid-app/` 不得与后端业务 API 前缀 `/shot-grid` 混用。该生产代理配置尚未完成真实环境验收。

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
