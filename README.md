# Shot Grid｜AI 影视制作协作平台

Shot Grid 面向影视短片项目团队，统一管理项目、镜头、资产、制作任务、版本提交、审核反馈和文件交付。平台关注的是制作协作与版本闭环，不是在线视频剪辑器或 AI 内容生成器。

本项目以 RuoYi-Vue3-FastAPI 作为管理平台基座，复用其登录认证、RBAC、动态菜单、文件管理、插件运行时、日志与系统管理能力；Shot Grid 业务前端和业务域均在此基础上独立演进。

## 核心能力

- 项目结构：项目、集、场次、镜头，以及角色、场景、道具三类资产。
- 制作协作：镜头或资产制作分项对应唯一任务，支持委派、改派、开始制作和进度跟踪。
- 版本管理：版本不可变，保留提交文件、制作说明、媒体派生和完整历史。
- 审核闭环：审核问题、画面标注、退回修改、再次提交与最终版本确认。
- 文件与目录：受保护文件、业务引用、NAS 目录任务、版本发布和缩略图/代理媒体派生。
- 平台治理：用户、角色、项目成员、数据范围、权限菜单、审计日志和系统配置。

核心业务链路：

```text
项目
  ├─ 集 → 场次 → 镜头 → 唯一制作任务 ─┐
  └─ 资产 → 制作分项 → 唯一制作任务 ─┤
                                      ↓
                               不可变版本提交
                                      ↓
                              审核通过 / 退回修改
                                      ↓
                               最终版本与制作履历
```

## 技术架构

```text
浏览器
  ├─ Shot Grid 业务前端（Vue 3 / Element Plus，端口 5174）
  └─ 平台管理端（Vue 3 / Element Plus）
                │ Axios / Vite 或 Nginx 代理
                ▼
FastAPI（端口 9099）
  ├─ Controller → Service → DAO → SQLAlchemy
  ├─ PostgreSQL：业务数据、版本、审核、任务和 Outbox
  ├─ Redis：会话、缓存、限流、日志流和分布式协调
  ├─ 受保护文件：上传、引用、下载、回收和完整性校验
  └─ Worker：NAS 目录、版本发布、缩略图和代理媒体派生
```

当前主数据库是 **PostgreSQL**。仓库保留的 MySQL 文件和 Compose 仅属于兼容能力，不代表当前项目的默认运行环境。

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `shot-grid-frontend/` | Shot Grid 独立业务前端，日常业务开发的主要入口 |
| `ruoyi-fastapi-backend/` | FastAPI 后端、Shot Grid 业务模块、迁移、SQL 与 Worker |
| `ruoyi-fastapi-frontend/` | 平台管理端，用于用户、角色、菜单、文件、插件和系统配置 |
| `ruoyi-fastapi-test/` | 独立 Playwright 端到端测试工程 |
| `docker-compose.dev.yml` | 本地开发：后端、PostgreSQL、Redis |
| `docker-compose.pg.yml` | PostgreSQL 完整部署参考拓扑 |
| `docker-compose.my.yml` | 保留的 MySQL 兼容拓扑，不是当前默认路径 |

## 本地开发

### 环境要求

- Windows 10/11 + PowerShell 7
- Docker Desktop（支持 `docker compose`）
- Node.js `^18.0.0 || ^20.0.0 || >=22.0.0`
- npm
- 仅在宿主机启动后端时需要 Python `>=3.10`；团队建议使用 Python 3.11.x
- 仅在宿主机执行媒体派生时需要 FFmpeg

### 方式一：Docker 后端 + 宿主机前端（推荐）

该方式适合日常页面、接口和媒体派生开发。后端开发镜像固定 Python 3.11.15 并内置 FFmpeg。

1. 在仓库根目录启动后端、PostgreSQL 和 Redis：

```powershell
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml ps
```

2. 在新的 PowerShell 窗口启动 Shot Grid 前端：

```powershell
cd shot-grid-frontend
npm.cmd ci
npm.cmd run dev
```

3. 打开以下地址：

- Shot Grid：<http://127.0.0.1:5174>
- 后端 OpenAPI：<http://127.0.0.1:9099/openapi.json>

Vite 默认把 `/dev-api` 转发到 `http://127.0.0.1:9099`。全新本地数据库由 PostgreSQL 初始化 SQL 建立；初始化账号仅用于本地开发，首次登录后应立即修改默认密码。

全新初始化库沿用基座开发账号 `admin / admin123`。该账号不得用于共享、测试或生产环境。

需要配置平台用户、角色、菜单、权限或系统参数时，可另开窗口启动平台管理端：

```powershell
cd ruoyi-fastapi-frontend
npm.cmd install
npm.cmd run dev
```

平台管理端默认地址为 <http://127.0.0.1:80>。该工程当前没有提交依赖锁文件，安装结果可能随依赖版本变化；不要把一次本地安装描述为可复现构建。


常用诊断命令：

```powershell
docker compose -f docker-compose.dev.yml logs -f backend
docker compose -f docker-compose.dev.yml exec backend python --version
docker compose -f docker-compose.dev.yml exec backend ffmpeg -version
```

> Linux 后端容器会关闭 Windows NAS 目录 Worker 和版本发布 Worker，只启用媒体派生 Worker。因此该模式不能作为真实 UNC/SMB/NAS 验收证据。

### 方式二：Docker 基础设施 + Windows 宿主机后端

需要直接访问 Windows UNC/SMB/NAS、调试目录 Worker 或版本发布 Worker 时，使用该方式。

1. 只启动 PostgreSQL 和 Redis：

```powershell
docker compose -f docker-compose.dev.yml up -d postgres redis
docker compose -f docker-compose.dev.yml ps
```

2. 检查 `ruoyi-fastapi-backend/.env.dev`：

- PostgreSQL 应连接 `127.0.0.1:15432`；
- Redis 应连接 `127.0.0.1:16379`；
- 数据库名必须与实际本地库一致；
- 不要把真实密码、JWT Secret、RSA 私钥或 Provider Key 提交到仓库；
- 按需配置三个 Shot Grid Worker 和 `SHOT_GRID_MEDIA_WORKER_FFMPEG_PATH`。

3. 创建后端虚拟环境并安装 PostgreSQL 依赖：

```powershell
cd ruoyi-fastapi-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-pg.txt
python -m pip install -e .
```

4. 校验数据库和应用配置，然后启动：

```powershell
ruoyi app doctor --env=dev
ruoyi app run --env=dev
```

已有数据库升级前先备份并检查版本：

```powershell
python -m alembic current
python -m alembic heads
```

只有确认数据库已处于受支持的 Alembic 迁移链时，才执行：

```powershell
python -m alembic upgrade head
```

无版本标记的历史库不能直接 `stamp` 或升级；应先在克隆库核对结构和数据。全新本地库通常由 `ruoyi-fastapi-pg.sql` 初始化，无需重复执行增量迁移。

5. 后端健康后，按“方式一”的前端命令启动 `shot-grid-frontend`。

### 停止本地环境

```powershell
docker compose -f docker-compose.dev.yml down
```

普通 `down` 不删除 PostgreSQL 和 Redis 命名卷。除非明确要清空全部本地数据，不要执行 `down -v`。

## 常用检查

日常开发按改动范围执行最小但充分的检查。

Shot Grid 前端：

```powershell
cd shot-grid-frontend
npm.cmd run lint
npm.cmd run test
npm.cmd run build:prod
```

后端：

```powershell
python -m ruff check ruoyi-fastapi-backend ruoyi-fastapi-test
python -m ruff format ruoyi-fastapi-backend ruoyi-fastapi-test --check
cd ruoyi-fastapi-backend
python -m pytest -q
```

完整 E2E 需要真实启动前端、后端、PostgreSQL 和 Redis：

```powershell
cd ruoyi-fastapi-test
python -m pytest -v
```

构建成功、服务健康或 Swagger 可访问都不等于业务端到端验证通过。

## 数据与文件边界

- 版本文件使用平台受保护文件能力，并通过业务引用保持事务一致性。
- 文件仍被业务引用时不得直接删除；私有文件访问默认拒绝。
- NAS 目录操作由 Outbox 与 Leader Worker 协调，数据库事务中不得等待 SMB I/O。
- 缩略图和代理媒体必须由媒体 Worker 派生，不得用原始大文件冒充代理媒体。
- 真实 NAS 验收必须覆盖正式 Windows 服务账号、共享 ACL、目录创建、版本发布和故障恢复。

## 公司内网生产部署（192.168.10.122）

生产部署必须使用根目录的 `docker-compose.prod.yml`，不要使用历史参考文件 `docker-compose.pg.yml`。新生产栈固定使用独立 Compose 项目名 `ruoyi-shot-grid-prod`，不会复用、停止或重建服务器上的旧容器、网络和数据卷。

### 已核对的服务器边界

2026-08-24 已只读确认：

- Ubuntu 24.04、Docker 29.5.2、Docker Compose 5.1.4；
- 约 31 GiB 内存、190 GiB 根盘可用；
- `80/888/3000/5432/5555/6379/8000/39081/39082` 已被旧服务占用；
- `12580/12581` 当前空闲；
- 宿主机 Nginx 和全部旧容器不会被本部署修改。

生产拓扑：

```text
内网用户
  ├─ 192.168.10.122:12580 → 平台管理端 Nginx
  └─ 192.168.10.122:12581 → Shot Grid Nginx
                                  │
                                  └─ /prod-api → backend:9099
                                                       │
                        ┌──────────────────────────────┼────────────────────────┐
                        ▼                              ▼                        ▼
                 独立 PostgreSQL                独立 Redis              独立业务文件卷
                 不映射宿主端口                 不映射宿主端口          不复用旧项目数据
```

访问地址：

- 平台管理端：<http://192.168.10.122:12580>
- Shot Grid：<http://192.168.10.122:12581/shot-grid-app/>

### 首次部署

1. 在服务器准备专用目录，不要放入已有项目目录：

```bash
git clone https://github.com/pleasureswx123/RuoYi-Vue3-FastAPI-master.git /opt/ruoyi-shot-grid
cd /opt/ruoyi-shot-grid
git checkout main
```

2. 生成一次性的生产密码、JWT Secret 和 3072 位 RSA 密钥：

```bash
bash deploy/init-env.sh 192.168.10.122
sudo install -d -m 0750 /etc/ruoyi-shot-grid /var/lib/ruoyi-shot-grid
sudo install -m 0600 deploy/.env.production /etc/ruoyi-shot-grid/production.env
```

必须人工核对 `/etc/ruoyi-shot-grid/production.env` 中的端口、CORS、数据库名和 Worker 开关。该文件含真实密钥，只保留在服务器，禁止提交 Git、复制到聊天或写入 CI 日志。

3. 执行首次发布：

```bash
cd /opt/ruoyi-shot-grid
RUOYI_ENV_FILE=/etc/ruoyi-shot-grid/production.env \
RUOYI_DEPLOY_STATE_DIR=/var/lib/ruoyi-shot-grid \
SERVER_IP=192.168.10.122 \
bash deploy/deploy.sh
```

发布脚本按以下顺序失败关闭：

1. 校验密钥文件权限、占位符、候选端口和 Compose 配置；
2. 在不停止旧版本的情况下构建三个新版本镜像；
3. 只启动本项目独立 PostgreSQL/Redis 并等待健康；
4. 创建 PostgreSQL `pg_dump` 备份；
5. 使用新后端镜像执行 `ruoyi db upgrade --allow-prod --yes`；
6. 执行应用、数据库、Redis 和传输加密预检；
7. 切换应用容器并等待全部健康检查通过；
8. 校验两个前端健康端点和后端 `ruoyi ops health`。

脚本不会执行全局 Docker 清理，不会操作其他 Compose 项目，也不会执行 `down -v`。数据库迁移失败时不会切换应用镜像；切换阶段失败时会尝试恢复上一组应用镜像，但不会擅自降级数据库。

### 后续一键快速部署

代码必须先通过 CI、提交并推送到远程；本地 commit 不等于服务器可部署。

从 Windows 开发机执行：

```powershell
.\deploy\remote-deploy.ps1
```

或登录服务器执行：

```bash
cd /opt/ruoyi-shot-grid
git status --short
git pull --ff-only origin main
RUOYI_ENV_FILE=/etc/ruoyi-shot-grid/production.env \
RUOYI_DEPLOY_STATE_DIR=/var/lib/ruoyi-shot-grid \
SERVER_IP=192.168.10.122 \
bash deploy/deploy.sh
```

服务器部署目录存在未提交改动时，远程脚本会拒绝覆盖。

### GitHub Actions CD

`.github/workflows/deploy-intranet.yml` 提供手动、单并发的生产发布入口。由于 `192.168.10.122` 是内网地址，GitHub 托管 Runner 无法直接访问，必须在公司内网安装专用 self-hosted Runner，并打上标签：

```text
self-hosted, linux, x64, ruoyi-prod
```

Runner 用户必须能使用 Docker，并只读访问 `/etc/ruoyi-shot-grid/production.env`，可写 `/var/lib/ruoyi-shot-grid`。Docker 组等价于宿主机高权限，只能使用专用 Runner，不得与不可信仓库共享。建议为 GitHub Environment `intranet-production` 配置人工审批；当前 CD 只允许手动选择明确的分支、标签或提交 SHA，不会在每次 push 后未经审批自动上线。

已有后端、Ruff、Playwright 工作流已对齐实际 `main` 分支；新增前端工作流会检查两个前端和生产 Compose。管理端仍未跟踪 `package-lock.json`，因此其 `npm install` 与镜像构建仍有依赖漂移风险，不能声称完全可复现。

### 状态、日志、备份与回滚

查看状态：

```bash
cd /opt/ruoyi-shot-grid
RUOYI_ENV_FILE=/etc/ruoyi-shot-grid/production.env \
RUOYI_DEPLOY_STATE_DIR=/var/lib/ruoyi-shot-grid \
bash deploy/status.sh
```

只查看本项目后端日志：

```bash
docker compose --project-name ruoyi-shot-grid-prod \
  --env-file /etc/ruoyi-shot-grid/production.env \
  -f /opt/ruoyi-shot-grid/docker-compose.prod.yml \
  logs --tail=200 -f backend
```

生产默认设置 `DB_ECHO=false`、`LOG_FILE_ENABLED=false`，应用日志只写容器 stdout；Docker `local` 日志驱动限制为每个容器 20 MiB、最多 5 个文件。这样可以避免 SQL echo 和压缩日志持续占用磁盘/I/O，但仍应接入公司的集中日志与告警系统。

每次迁移前的 PostgreSQL 备份保存在 `/var/lib/ruoyi-shot-grid/backups/`，默认保留 14 天。业务文件、PostgreSQL 和 Redis 分别保存在本项目独立命名卷中。备份只有在执行过恢复演练后才算可用；首次正式上线前必须额外把数据库备份和业务文件备份复制到服务器外部。

回滚上一组应用镜像：

```bash
cd /opt/ruoyi-shot-grid
RUOYI_ENV_FILE=/etc/ruoyi-shot-grid/production.env \
RUOYI_DEPLOY_STATE_DIR=/var/lib/ruoyi-shot-grid \
bash deploy/rollback.sh
```

也可以显式传入 release ID。该命令只回滚后端和两个前端镜像，不自动回退数据库；涉及不向后兼容迁移时，必须按备份恢复方案单独评审，不能直接执行 Alembic downgrade。

### 稳定性与正式验收边界

- 所有服务使用 `restart: unless-stopped`、健康检查、启动依赖门禁、60 秒后端优雅停止和独立日志轮转。
- PostgreSQL、Redis、后端和两个前端均设有内存上限，避免新项目失控挤占旧项目资源。
- 后端使用两个 Worker，并继续依赖 Redis Application Leader、租约和 fencing 保证调度正确性；不能把共享状态改成进程内变量。
- 当前 Compose 是单后端服务的健康门禁发布，正常迭代切换时仍可能有数秒连接重试窗口，不等于蓝绿零停机。若业务要求发布过程零中断，需要在下一阶段增加双后端槽位和网关原子切流。
- Ubuntu 容器可运行 FFmpeg 媒体派生 Worker，但不能承担 Windows UNC/NAS 目录 Worker 和版本发布 Worker。`SHOT_GRID_STORAGE_WORKER_ENABLED` 与 `SHOT_GRID_VERSION_WORKER_ENABLED` 必须保持关闭；真实 NAS 能力需要另行部署 Windows Worker，并完成服务账号、共享 ACL、目录创建、版本发布和故障恢复验收。
- 首次上线完成不等于完整 E2E 通过。至少还要实际验证登录、权限、项目隔离、数据库写入、Redis 会话、文件上传/下载、媒体派生、版本审核、容器重启恢复和备份恢复。

当前生产页面路径约定为 `/shot-grid-app/`，API 前缀为 `/prod-api/`。更详细的反向代理和业务边界见 `shot-grid-frontend/README.md`。

## 进一步阅读

- [Shot Grid 业务前端说明](shot-grid-frontend/README.md)
- [后端 Docker 本地开发指南](ruoyi-fastapi-backend/docs/docker_dev_guide.md)
- [后端 CLI 使用说明](ruoyi-fastapi-backend/docs/cli_usage.md)
- [文件管理接入指南](ruoyi-fastapi-backend/docs/file_management_usage_guide.md)
- [插件开发说明](ruoyi-fastapi-backend/docs/plugin_development.md)
- [传输加密配置](ruoyi-fastapi-backend/docs/transport_crypto_config.md)
- [项目协作与架构约束](AGENTS.md)

## 基座与致谢

本项目基于 [RuoYi-Vue3-FastAPI](https://github.com/insistence/RuoYi-Vue3-FastAPI) 与 [RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3) 进行业务化建设。上游框架提供了重要的平台基础能力；本仓库 README 只描述当前 Shot Grid 产品、运行方式与交付边界。

使用、分发或二次开发前，请同时检查本仓库和所依赖上游项目的许可证要求。
