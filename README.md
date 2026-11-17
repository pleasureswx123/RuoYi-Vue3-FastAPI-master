# Shot Grid｜AI 影视制作协作平台

管理项目、镜头、资产、制作任务、版本审核和 NAS 交付；基于 RuoYi-Vue3-FastAPI，沿用原用户、部门和角色体系。

## 本地四步启动（Windows PowerShell）

适用于已安装依赖、已配置后端 `.env.dev`，且目标数据库已完成对应版本迁移的环境。先打开 Docker Desktop。下列每个终端都从**本仓库根目录**开始执行；不要进入同名的交接源码目录。

首次安装或需要 Docker 后端时，查看[本地开发详细说明](docs/本地开发详细说明.md)。

### 1. 启动 PostgreSQL 和 Redis

```powershell
docker compose -f docker-compose.dev.yml up -d postgres redis
docker compose -f docker-compose.dev.yml ps
```

### 2. 启动后端

继续在当前终端执行：

```powershell
cd .\ruoyi-fastapi-backend
.\.venv\Scripts\Activate.ps1
ruoyi app doctor --env=dev
ruoyi app run --env=dev
```

检查通过后再运行后端，并保留终端。如果此前已启动 Docker 后端，先在仓库根目录执行 `docker compose -f docker-compose.dev.yml stop backend`，避免重复占用端口。

### 3. 启动管理端

另开终端，从仓库根目录执行：

```powershell
cd .\ruoyi-fastapi-frontend
npm.cmd run dev -- --host 127.0.0.1 --port 80 --strictPort
```

### 4. 启动制作端

再开终端，从仓库根目录执行：

```powershell
cd .\shot-grid-frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

| 本地服务 | 地址 |
| --- | --- |
| 管理端 | <http://127.0.0.1:80> |
| Shot Grid 制作端 | <http://127.0.0.1:5174> |
| 后端 | <http://127.0.0.1:9099> |

两个前端代理到本地后端 9099；端口被占用时会明确退出，不自动换端口。依赖首次安装或锁文件更新后，在对应前端目录执行 `npm.cmd ci`，日常启动不必重复安装。

停止时，在三个应用终端分别按 `Ctrl+C`；需要停止数据库和 Redis 时，在仓库根目录执行：

```powershell
docker compose -f docker-compose.dev.yml stop postgres redis
```

## 启动前需要知道的配置边界

- 后端使用 `.env.dev` 中指定的数据库，启动命令不会自动切换到验收副本。升级旧库前先备份，并在隔离副本验证；不要把生产库或需要保留的原库作为本地试验库。
- 本地数据库、Redis 默认端口为 `15432`、`16379`。数据库名称和凭据以实际配置为准，不在 README 固定某个临时工作库。
- 页面能打开不代表 NAS 流程已启用。完整提交和交付还需要正确的存储路径、访问权限及相应目录、版本发布和媒体 Worker 配置；本地验收使用独立 NAS 测试目录。
- 不提交真实环境配置、密钥、数据库备份或测试文件；不要使用 `down -v` 清空现有数据卷。

## 快捷部署（与本地启动分开）

在仓库根目录执行；脚本只使用已提交的 `main` 代码，不包含未提交修改。

```powershell
# 只准备本地镜像，不连接服务器、不部署
.\deploy\remote-deploy.ps1 -BuildOnly

# 正式部署到公司服务器（需要上线时再执行）
.\deploy\remote-deploy.ps1
```

脚本按后端、管理端、制作端分别核对构建内容，未变化的模块复用镜像；变化的模块继续利用 Docker 层及 pip/npm 下载缓存。服务器已有相同内容的镜像时跳过传输。正式部署仍保留停写、数据库备份、迁移、配置预检和健康检查。

首次使用需建立内容标记；换构建电脑或清理缓存后可能重新下载。需要强制进入构建流程时使用 `-BuildOnly -ForceBuild`，仍保留层缓存；已有全部匹配镜像时可用 `-SkipBuild` 严格校验后部署。通常直接运行默认命令即可。详细规则见[部署说明](deploy/README.md)。

## 项目目录

| 目录 | 用途 |
| --- | --- |
| `shot-grid-frontend/` | 制作平台：镜头、资产、任务、审核与统计 |
| `ruoyi-fastapi-frontend/` | 管理平台：用户、部门、角色与系统配置 |
| `ruoyi-fastapi-backend/` | 共用后端、PostgreSQL 迁移和 NAS Worker |
| `deploy/` | 公司服务器部署、备份与回滚脚本 |
| `docs/` | 详细说明和按日期保存的验收记录 |

## 按需阅读

- [项目介绍、架构与界面截图](docs/项目介绍与界面预览.md)
- [首次安装、本地运行方式与检查命令](docs/本地开发详细说明.md)
- [公司服务器部署与一键上线](deploy/README.md)：一键脚本为 `deploy/remote-deploy.ps1`，会实际部署服务器，不属于本地启动步骤。
- [Shot Grid 业务前端说明](shot-grid-frontend/README.md)
- [领域模型与 API 契约](shot-grid-frontend/docs/领域模型与API契约.md)
- [后端 CLI 使用说明](ruoyi-fastapi-backend/docs/cli_usage.md)
- [文件管理接入指南](ruoyi-fastapi-backend/docs/file_management_usage_guide.md)

历史验收记录保存在 `docs/`，用于追溯当时的版本、环境和验证范围，不是当前启动指令或每次开发的必做清单。

本项目基于 [RuoYi-Vue3-FastAPI](https://github.com/insistence/RuoYi-Vue3-FastAPI) 与 [RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3)。使用或分发前请核对本仓库及上游许可证。
