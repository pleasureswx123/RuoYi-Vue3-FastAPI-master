<h1 align="center">
    <img alt="logo" src="https://oscimg.oschina.net/oscnet/up-d3d0a9303e11d522a06cd263f3079027715.png">
</h1>
<h1 align="center" style="margin: 30px 0 30px; font-weight: bold;">RuoYi-Vue3-FastAPI</h1>
<h4 align="center">基于RuoYi-Vue3+FastAPI前后端分离的快速开发框架</h4>
<p align="center">
    <a href="https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/stargazers">
        <img alt="Gitee" src="https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/badge/star.svg?theme=dark">
    </a>
    <a href="https://github.com/insistence/RuoYi-Vue3-FastAPI">
        <img alt="Github" src="https://img.shields.io/github/stars/insistence/RuoYi-Vue3-FastAPI?style=social">
    </a>
    <a href="https://github.com/insistence/RuoYi-Vue3-FastAPI/actions?query=branch%3Amaster+event%3Apush+workflow%3A%22%22Playwright+Tests%22%22">
        <img alt="Playwright Tests" src="https://github.com/insistence/RuoYi-Vue3-FastAPI/workflows/Playwright Tests/badge.svg">
    </a>
    <a href="https://github.com/insistence/RuoYi-Vue3-FastAPI/actions?query=branch%3Amaster+event%3Apush+workflow%3A%22%22Ruff+Check%22%22">
        <img alt="Ruff Check" src="https://github.com/insistence/RuoYi-Vue3-FastAPI/workflows/Ruff Check/badge.svg">
    </a>
    <a href="https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI">
        <img alt="project version" src="https://img.shields.io/badge/version-1.10.0-brightgreen.svg">
    </a>
    <a href="https://github.com/astral-sh/ruff">
        <img alt="Ruff" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json">
    </a>
    <a href="https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/blob/master/LICENSE">
        <img alt="LICENSE" src="https://img.shields.io/github/license/mashape/apistatus.svg">
    </a>
    <img alt="node version" src="https://img.shields.io/badge/node-≥18-blue">
    <img alt="python version" src="https://img.shields.io/badge/python-≥3.10-blue">
    <img alt="mysql version" src="https://img.shields.io/badge/MySQL-≥5.7-blue">
    <img alt="redis version" src="https://img.shields.io/badge/redis-≥6.2-blue">
</p>

## 平台简介

RuoYi-Vue3-FastAPI是一套全部开源的快速开发平台，毫无保留给个人及企业免费使用。

* 前端采用Vue3、Element Plus，基于<u>[RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3)</u>前端项目修改。
* 移动端采用uni-app、Vue3、Vite，内置tailwindcss，基于<u>[RuoYi-App](https://github.com/yangzongzhuan/RuoYi-App)</u>项目修改。
* 后端采用FastAPI、sqlalchemy、MySQL（PostgreSQL）、Redis、OAuth2 & Jwt。
* 权限认证使用OAuth2 & Jwt，支持多终端认证系统。
* 支持加载动态权限菜单，多方式轻松权限控制。
* Vue2版本：
  * Gitte仓库地址：<https://gitee.com/insistence2022/RuoYi-Vue-FastAPI>
  * GitHub仓库地址：<https://github.com/insistence/RuoYi-Vue-FastAPI>
* 纯Python版本：
  * Gitte仓库地址：<https://gitee.com/insistence2022/dash-fastapi-admin>
  * GitHub仓库地址：<https://github.com/insistence/Dash-FastAPI-Admin>
* 特别鸣谢：<u>[RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3)</u>、<u>[RuoYi-App](https://github.com/yangzongzhuan/RuoYi-App)</u>

## 内置功能

1. 用户管理：用户是系统操作者，该功能主要完成系统用户配置。
2. 角色管理：角色菜单权限分配、设置角色按机构进行数据范围权限划分。
3. 菜单管理：配置系统菜单，操作权限，按钮权限标识等。
4. 部门管理：配置系统组织机构（公司、部门、小组）。
5. 岗位管理：配置系统用户所属担任职务。
6. 字典管理：对系统中经常使用的一些较为固定的数据进行维护。
7. 参数管理：对系统动态配置常用参数。
8. 通知公告：系统通知公告信息发布维护。
9. 操作日志：系统正常操作日志记录和查询；系统异常信息日志记录和查询。
10. 登录日志：系统登录日志记录查询包含登录异常。
11. 在线用户：当前系统中活跃用户状态监控。
12. 定时任务：在线（添加、修改、删除）任务调度包含执行结果日志。
13. 服务监控：监视当前系统CPU、内存、磁盘、堆栈等相关信息。
14. 缓存监控：对系统的缓存信息查询，命令统计等。
15. 传输加密：支持前后端请求加密、响应解密、公钥轮换、运行策略下发与监控统计。
16. 在线构建器：拖动表单元素生成相应的HTML代码。
17. 系统接口：根据业务代码自动生成相关的api接口文档。
18. 代码生成：配置数据库表信息一键生成前后端代码（python、sql、vue、js），支持下载。
19. AI管理：提供AI模型管理和AI对话功能。
20. 文件管理：统一管理公开文件和受保护附件，支持访问控制、业务引用保护、操作审计、回收站、保留策略及存储对账。
21. 插件系统：支持插件发现、安装、启停、升级、卸载与清理，提供依赖与配置管理、迁移与种子、定时任务、菜单权限、批量预演、健康诊断、操作审计及前后端插件脚手架。

## 演示图

<table>
    <tr>
        <td>
            <img alt="login" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/login.png">
        </td>
        <td>
            <img alt="dashboard" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/dashboard.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="user" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/user.png">
        </td>
        <td>
            <img alt="role" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/role.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="menu" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/menu.png">
        </td>
        <td>
            <img alt="dept" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/dept.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt=""post src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/post.png">
        </td>
        <td>
            <img alt="dict" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/dict.png">
        </td>
    </tr>  
    <tr>
        <td>
            <img alt="config" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/config.png">
        </td>
        <td>
            <img alt="notice" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/notice.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="operLog" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/operLog.png">
        </td>
        <td>
            <img alt="loginLog" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/loginLog.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="online" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/online.png">
        </td>
        <td>
            <img alt="job" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/job.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="server" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/server.png">
        </td>
        <td>
            <img alt="cache" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/cache.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="cacheList" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/cacheList.png">
        </td>
        <td>
            <img alt="form" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/form.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="api" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/api.png">
        </td>
        <td>
            <img alt="gen" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/gen.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="aiModel" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/aiModel.png">
        </td>
        <td>
            <img alt="aiChat" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/aiChat.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="file" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/file.png">
        </td>
        <td>
            <img alt="plugin" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/plugin.png">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="profile" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/web/profile.png">
        </td>
    </tr>
</table>

<table>
    <tr>
        <td>
            <img alt="applogin" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/app/login.png">
        </td>
        <td>
            <img alt="appWorkbench" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/app/workbench.png">
        </td>
        <td>
            <img alt="appProfile" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/vue3/app/profile.png">
        </td>
    </tr>
</table>

## 在线体验

* *账号：admin*
* *密码：admin123*
* 演示地址：<a href="https://vfadmin.insistence.tech">vfadmin管理系统<a>

## 项目开发及发布相关

### 当前项目本地启动（推荐）

当前本地开发拓扑为：Docker Compose 只启动 PostgreSQL 和 Redis，后端与前端都在 Windows 宿主机运行。这样后端代码修改后可直接由 Uvicorn 热更新，也能直接访问 Windows UNC/SMB/NAS 路径。

#### 1. 环境要求

- Docker Desktop（需要启用 Docker Compose）；
- Python `>=3.10`（建议团队统一使用 Python 3.11.x，并先执行 `python --version` 确认版本）；
- FFmpeg（启用 Shot Grid 缩略图或代理媒体 Worker 时需要，并确保 `ffmpeg` 已加入 `PATH`）；
- Node.js `^18.0.0 || ^20.0.0 || >=22.0.0`；
- npm；
- Windows PowerShell。

本地后端需要安装 Python，启用媒体派生时还需要安装 FFmpeg。Python 依赖安装在项目虚拟环境中，不会污染系统 Python；日常修改代码不需要重复安装依赖。

首次创建本地数据库时，确认 `ruoyi-fastapi-backend/.env.dev` 使用 Docker 映射到宿主机的端口。Compose 默认创建数据库 `ruoyi-fastapi`，默认开发账号为 `postgres/root`。这些默认值只允许用于本地开发，不得用于生产环境。

```dotenv
DB_TYPE = 'postgresql'
DB_HOST = '127.0.0.1'
DB_PORT = 15432
DB_USERNAME = 'postgres'
DB_PASSWORD = 'root'
DB_DATABASE = 'ruoyi-fastapi'
REDIS_HOST = '127.0.0.1'
REDIS_PORT = 16379
REDIS_DATABASE = 0
```

已有本地环境可以继续使用自己的数据库名和 Redis DB，但对应数据库必须已经存在。

#### 2. 只用 Docker 启动 PostgreSQL 和 Redis

在仓库根目录执行：

```powershell
docker compose -f docker-compose.dev.yml up -d postgres redis
docker compose -f docker-compose.dev.yml ps
```

#### 3. 在宿主机启动后端

首次启动时，在新的 PowerShell 窗口创建虚拟环境并安装 PostgreSQL 依赖：

```powershell
cd ruoyi-fastapi-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-pg.txt
```

如果 PowerShell 禁止执行激活脚本，也可以不激活虚拟环境，直接将后续命令中的 `python` 替换为 `.\.venv\Scripts\python.exe`。

首次建库或拉取到新迁移后执行：

```powershell
python -m alembic upgrade head
```

启动后端开发服务器：

```powershell
python -m uvicorn server:create_app --factory --host 127.0.0.1 --port 9099 --reload
```

`--reload` 会监控后端源码并在文件变化后自动重启进程。新增或修改 Python 依赖时才需要重新执行 `python -m pip install -r requirements-pg.txt`。

后端地址：

```text
http://127.0.0.1:9099
http://127.0.0.1:9099/docs
```

启用 Shot Grid 媒体派生 Worker 前，确认 FFmpeg 可用：

```powershell
ffmpeg -version
```

如果 FFmpeg 未加入 `PATH`，可在 `.env.dev` 中通过 `SHOT_GRID_MEDIA_WORKER_FFMPEG_PATH` 配置可执行文件的绝对路径。

#### 4. 启动 Shot Grid 前端

另开一个 PowerShell 窗口：

```powershell
cd shot-grid-frontend
npm.cmd ci
npm.cmd run dev
```

浏览器访问：

```text
http://127.0.0.1:5174
```

开发服务器会把 `/dev-api` 转发到 `http://127.0.0.1:9099`。

如需启动 RuoYi 系统管理前端，另开窗口执行：

```powershell
cd ruoyi-fastapi-frontend
npm.cmd install
npm.cmd run dev
```

#### 5. 停止本地服务

先在后端和前端窗口按 `Ctrl+C`，再在仓库根目录停止基础设施：

```powershell
docker compose -f docker-compose.dev.yml down
```

不要附加 `-v`，否则会删除本地 PostgreSQL 和 Redis 命名卷。

如需验证完整 Linux 容器拓扑，可按 [后端 Docker 本地开发指南](./ruoyi-fastapi-backend/docs/docker_dev_guide.md) 单独执行；它属于集成验证方式，不是日常本地开发的默认启动方式。Linux 容器不能直接执行 Windows UNC/SMB 目录操作，因此真实 NAS 开发与验收应使用本节的宿主机后端。

### 传输层加解密配置说明

后端密钥配置与轮换说明：[ruoyi-fastapi-backend/docs/transport_crypto_config.md](./ruoyi-fastapi-backend/docs/transport_crypto_config.md)

### 开发

```bash
# 克隆项目
git clone https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI.git

# 进入项目根目录
cd RuoYi-Vue3-FastAPI
```

#### 前端

```bash
# 进入前端目录
cd ruoyi-fastapi-frontend

# 安装依赖
npm install 或 yarn --registry=https://registry.npmmirror.com

# 建议不要直接使用 cnpm 安装依赖，会有各种诡异的 bug。可以通过如下操作解决 npm 下载速度慢的问题
npm install --registry=https://registry.npmmirror.com

# 启动服务
npm run dev 或 yarn dev
```

#### 移动端

```bash
# 进入移动端目录
cd ruoyi-fastapi-app

# 安装依赖
npm install -g pnpm
pnpm install

# 启动 H5
pnpm dev:h5

# 启动微信小程序
pnpm dev:mp-weixin
```

移动端详细文档请参考：[ruoyi-fastapi-app/README.md](./ruoyi-fastapi-app/README.md)

#### 后端

```bash
# 进入后端目录
cd ruoyi-fastapi-backend

# 如果使用的是MySQL数据库，请执行以下命令安装项目依赖环境
pip3 install -r requirements.txt
# 如果使用的是PostgreSQL数据库，请执行以下命令安装项目依赖环境
pip3 install -r requirements-pg.txt

# 安装AI插件依赖，如果不需要AI插件，可忽略此步骤
ruoyi plugin install-deps ai

# 配置环境
在.env.dev文件中配置开发环境的数据库和redis

# 运行sql文件
1.新建数据库ruoyi-fastapi(默认，可修改)
2.如果使用的是MySQL数据库，使用命令或数据库连接工具运行sql文件夹下的ruoyi-fastapi.sql；如果使用的是PostgreSQL数据库，使用命令或数据库连接工具运行sql文件夹下的ruoyi-fastapi-pg.sql

# 运行后端
ruoyi app run --env=dev
```

后端 CLI 使用说明请参考：[ruoyi-fastapi-backend/docs/cli_usage.md](./ruoyi-fastapi-backend/docs/cli_usage.md)

#### 访问

```bash
# 默认账号密码
账号：admin
密码：admin123

# 浏览器访问
地址：http://localhost:80
```

### 发布

#### 前端

```bash
# 构建测试环境
npm run build:stage 或 yarn build:stage

# 构建生产环境
npm run build:prod 或 yarn build:prod
```

#### 后端

```bash
# 配置环境
在.env.prod文件中配置生产环境的数据库和redis

# 运行后端
ruoyi app run --env=prod
```

### Docker Compose部署方式

> ⚠️ **警告：** 默认未做数据持久化配置，请注意数据备份或自行配置持久化

#### MySQL版本

```bash
docker compose -f docker-compose.my.yml up -d --build
```

#### PostgreSQL版本

```bash
docker compose -f docker-compose.pg.yml up -d --build
```

## 交流与赞助

如果有对本项目及FastAPI感兴趣的朋友，欢迎加入知识星球一起交流学习，让我们一起变得更强。如果你觉得这个项目帮助到了你，你可以请作者喝杯咖啡表示鼓励☕。扫描下面微信二维码添加微信备注VF-Admin即可进群。
<table>
    <tr>
        <td>
            <img alt="zsxq" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/common/zsxq.jpg">
        </td>
        <td>
            <img alt="zanzhu" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/common/zanzhu.jpg">
        </td>
    </tr>
    <tr>
        <td>
            <img alt="wxcode" src="https://gitee.com/insistence2022/ruoyi-fastapi-pictures/raw/master/common/wxcode.jpg">
        </td>
    </tr>
</table>
