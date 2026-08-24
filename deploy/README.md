# 公司内网生产部署说明

本文档面向主要从事前端开发、需要维护 Shot Grid 内网生产环境的同事。目标是说明“页面后面有哪些服务、数据保存在哪里、哪些配置真正生效、以后如何一键发布”，避免依赖个人记忆。

## 1. 当前生产环境速查

| 项目 | 当前值 |
| --- | --- |
| 服务器 | `192.168.10.122`，Ubuntu 24.04 |
| 项目目录 | `/opt/ruoyi-shot-grid` |
| Compose 项目名 | `ruoyi-shot-grid-prod` |
| 管理端 | `http://192.168.10.122:12580/` |
| Shot Grid | `http://192.168.10.122:12581/shot-grid-app/` |
| API 前缀 | 两个前端都通过同域 `/prod-api/` 反向代理到后端 |
| 生产配置 | `/etc/ruoyi-shot-grid/production.env`，权限必须为 `0600` |
| 部署状态和备份 | `/var/lib/ruoyi-shot-grid` |
| 数据库 | 本项目独立 PostgreSQL 16，不映射宿主机端口 |
| Redis | 本项目独立 Redis 7，不映射宿主机端口 |
| 当前 HTTP 决策 | 仅在公司可信内网使用；传输层 Web Crypto 已关闭 |

服务器上还有其他项目。所有生产命令必须带项目名 `ruoyi-shot-grid-prod` 和本项目 Compose 文件，禁止执行全局 `docker system prune`，禁止对本项目执行 `down -v`，也不要停止或重建其他项目容器。

## 2. 从浏览器到数据的完整链路

```text
浏览器
  ├─ :12580 → 管理端 Nginx ─┐
  └─ :12581 → Shot Grid Nginx ─┤
                                └─ /prod-api/* → FastAPI backend:9099
                                                       │
                        ┌──────────────────────────────┼────────────────────────┐
                        ▼                              ▼                        ▼
                 PostgreSQL                      Redis                  backend_files
                 业务和平台数据                  登录会话/缓存           上传文件/业务文件
```

可以把它理解为：

- 前端容器只负责页面和反向代理，不保存业务数据；重建前端容器不会丢数据。
- FastAPI 后端负责登录、权限、业务规则和数据库事务，本身也不把关键数据保存在容器可写层。
- PostgreSQL 保存结构化业务数据。
- Redis 保存登录会话、验证码、缓存、限流、日志流和多 Worker 协调状态。
- `backend_files` 保存上传文件和受保护业务文件。

## 3. 服务器目录分别做什么

| 路径 | 用途 | 是否可以删除 |
| --- | --- | --- |
| `/opt/ruoyi-shot-grid` | 服务器上的 Git 代码和 Compose 文件 | 不可随意删除；一键发布会快进此仓库 |
| `/etc/ruoyi-shot-grid/production.env` | 真正生效的生产密码、端口、数据库、Redis、日志和 Worker 配置 | 不可删除，不可提交 Git |
| `/etc/ruoyi-shot-grid/bootstrap-admin-password` | 首次部署生成的 `admin` 随机密码，权限 `0600` | 完成交接并确认新密码后可人工安全移除 |
| `/var/lib/ruoyi-shot-grid/backups` | 每次迁移前的 PostgreSQL 自定义格式备份 | 按保留策略清理，不能当作唯一异机备份 |
| `/var/lib/ruoyi-shot-grid/postgres-init` | 首次建库时挂载给 PostgreSQL 的只读初始化 SQL | 不要手工改；每次发布由脚本同步 |
| `/var/lib/ruoyi-shot-grid/current-release` | 当前成功发布的 12 位提交号 | 由发布脚本维护 |
| `/var/lib/ruoyi-shot-grid/previous-release` | 上一个可回滚的应用镜像版本 | 由发布脚本维护 |
| `/var/lib/ruoyi-shot-grid/deploy.lock` | 防止两次发布同时执行的锁 | 不要在发布运行时删除 |

生产密钥和数据状态故意不放在 Git 仓库中：代码可以重新拉取，生产密码和数据不能通过 Git 恢复。

## 4. Docker 持久化卷在哪里

Docker 卷有“逻辑名称”和“宿主机物理目录”两层。平时只使用逻辑名称操作，不要直接进入 `_data` 修改文件。

| 逻辑卷名 | 宿主机物理目录 | 保存内容 |
| --- | --- | --- |
| `ruoyi-shot-grid-prod_postgres_data` | `/var/lib/docker/volumes/ruoyi-shot-grid-prod_postgres_data/_data` | PostgreSQL 数据文件 |
| `ruoyi-shot-grid-prod_redis_data` | `/var/lib/docker/volumes/ruoyi-shot-grid-prod_redis_data/_data` | Redis AOF 持久化文件 |
| `ruoyi-shot-grid-prod_backend_files` | `/var/lib/docker/volumes/ruoyi-shot-grid-prod_backend_files/_data` | 上传、下载、私有文件、回收站和隔离区 |

查看卷的真实位置：

```bash
docker volume inspect \
  ruoyi-shot-grid-prod_postgres_data \
  ruoyi-shot-grid-prod_redis_data \
  ruoyi-shot-grid-prod_backend_files \
  --format '{{.Name}} -> {{.Mountpoint}}'
```

重要说明：

- PostgreSQL 不能通过复制正在运行的 `_data` 目录代替数据库备份，正式备份使用 `pg_dump -Fc`。
- `backend_files` 需要单独做文件级或卷级异机备份，数据库备份不包含上传文件内容。
- Redis 主要保存可重建缓存和会话，但 AOF 仍由独立卷持久化，不能复用服务器旧项目的 Redis。
- 任何恢复操作都应先在克隆环境演练，不要直接覆盖生产卷。

## 5. 服务器上有哪些 `.env`，谁真正生效

### 5.1 真正的生产配置

`/etc/ruoyi-shot-grid/production.env` 是生产唯一事实来源。Compose 会把它注入 PostgreSQL、Redis 和 FastAPI 容器。文件属于 `root:root`，权限必须为 `0600`。

主要配置组：

| 配置组 | 关键变量 | 作用 |
| --- | --- | --- |
| Compose/端口 | `COMPOSE_PROJECT_NAME`、`ADMIN_PORT`、`SHOT_GRID_PORT` | 保证项目名和 `12580/12581` 不漂移 |
| PostgreSQL | `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` | 初始化和连接本项目独立数据库 |
| Redis | `REDIS_PASSWORD`、`REDIS_DATABASE` | 会话、验证码、缓存和协调 |
| FastAPI | `APP_WORKERS`、`APP_ROOT_PATH`、`APP_CORS_ALLOWED_ORIGINS` | 后端进程和反向代理边界 |
| JWT | `JWT_SECRET_KEY`、过期时间 | 登录令牌签名；修改会让旧令牌失效 |
| 连接池 | `DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_TIMEOUT` | 控制数据库并发连接和等待时间 |
| 日志 | `DB_ECHO=false`、`LOG_FILE_ENABLED=false` | 关闭大量 SQL 回显和容器内文件日志 |
| Worker | `SHOT_GRID_*_WORKER_ENABLED` | 控制媒体、NAS 目录和版本发布 Worker |
| 传输策略 | `TRANSPORT_CRYPTO_ENABLED=false`、`TRANSPORT_CRYPTO_MODE=off` | 当前公司内网 HTTP 的明确配置 |

不要在聊天、截图、Git、Issue 或 CI 日志中输出该文件内容。

### 5.2 仓库里的环境文件

| 文件 | 用途 | 是否直接用于当前生产 |
| --- | --- | --- |
| `deploy/.env.production.example` | 生产配置模板和变量说明，不含真实密钥 | 用于初始化，不直接作为生产密钥文件 |
| `ruoyi-fastapi-backend/.env.dev` | Windows/宿主机本地开发 | 否 |
| `ruoyi-fastapi-backend/.env.dockerpg` | 历史 PostgreSQL Compose 参考配置 | 否 |
| `ruoyi-fastapi-backend/.env.dockermy` | 历史 MySQL Compose 参考配置 | 否 |
| `ruoyi-fastapi-backend/.env.prod` | 后端旧的独立 `prod` 运行配置 | 当前生产使用 `APP_ENV=production` 和服务器环境变量，因此不以它为事实来源 |
| `ruoyi-fastapi-frontend/.env.production` | 管理端 Vite 构建时写入 `/prod-api` 等公开配置 | 是，但只能包含公开前端配置 |
| `shot-grid-frontend/.env.production` | Shot Grid Vite 构建时写入子路径和 `/prod-api` | 是，但只能包含公开前端配置 |

前端 `.env.production` 会打进浏览器静态文件，所以绝对不能放数据库密码、JWT Secret、API Key 或私钥。

## 6. 为什么当前 HTTP 要关闭 Web Crypto

Chrome 等浏览器只在安全上下文中提供完整 Web Crypto API。`http://192.168.10.122:*` 即使属于公司内网，也不是浏览器认可的安全上下文，因此原来的 `required` 模式会出现：

- 管理端：“当前浏览器不支持 Web Crypto API”；
- Shot Grid：“无法连接业务服务，请检查网络或稍后重试”。

当前根据部署要求固定使用 HTTP，因此服务器配置为：

```dotenv
TRANSPORT_CRYPTO_ENABLED=false
TRANSPORT_CRYPTO_MODE=off
APP_CORS_ALLOWED_ORIGINS=http://192.168.10.122:12580,http://192.168.10.122:12581
```

这意味着账号密码和接口数据不再由应用层 RSA/AES 协议加密，安全性依赖公司内网隔离。必须同时满足：

- 不把 `12580/12581` 转发到公网；
- 不在不可信 Wi-Fi、VPN 出口或跨互联网链路使用；
- 防火墙只允许公司可信网段访问；
- 如果未来需要外部访问，先部署 HTTPS，再把传输配置恢复为 `true / required` 并重新验证登录。

## 7. 日常一键发布

### 7.1 发布前提

- 功能代码已经完成必要检查并执行 `git commit`。
- Windows 开发机可使用 Docker Desktop、Git、PowerShell、`ssh` 和 `scp`。
- `root@192.168.10.122` 已配置 SSH 密钥登录。
- 服务器生产环境文件和三个持久化卷已经初始化。
- 一键脚本只部署已提交的 `main`；本地未提交文件不会进入镜像或服务器。

### 7.2 一条命令

在仓库根目录运行：

```powershell
.\deploy\remote-deploy.ps1
```

脚本会自动完成：

1. 核对服务器 Git 工作区干净、生产配置权限正确；
2. 创建当前提交的临时干净 worktree，避免夹带本地未提交文件；
3. 在 Windows 开发机构建后端、管理端和 Shot Grid 三个生产镜像；
4. 生成只允许服务器仓库快进的 Git 增量包；
5. 通过 SSH 离线传输镜像，不依赖服务器访问 Docker Hub、npm 或 PyPI；
6. 在服务器创建数据库备份、执行 Alembic 迁移和配置预检；
7. 切换三个应用容器，等待五个服务健康；
8. 复核 `current-release`、数据库和 Redis 健康状态。

如果本地已经有当前 12 位提交号对应的三个镜像，可以使用：

```powershell
.\deploy\remote-deploy.ps1 -SkipBuild
```

`-SkipBuild` 不会跳过服务器备份、迁移和健康门禁。镜像标签缺失时脚本会失败。

发布脚本不会自动 `git push`。如果团队需要远程仓库和生产服务器保持一致，发布前仍应单独完成代码评审和 `git push origin main`。

## 8. 首次部署或重建服务器

首次部署需要先创建生产配置，后续一键发布不会覆盖它：

```bash
cd /opt/ruoyi-shot-grid
bash deploy/init-env.sh 192.168.10.122
install -d -m 0750 /etc/ruoyi-shot-grid /var/lib/ruoyi-shot-grid
install -m 0600 deploy/.env.production /etc/ruoyi-shot-grid/production.env
```

然后人工检查端口、CORS、HTTP 传输策略、Worker 开关和数据库名，再执行首次发布。初始化文件包含随机密码和密钥，不得提交 Git。

## 9. 常用运维命令

先定义公共参数，避免误操作其他项目：

```bash
cd /opt/ruoyi-shot-grid
export RUOYI_ENV_FILE=/etc/ruoyi-shot-grid/production.env
export RUOYI_DEPLOY_STATE_DIR=/var/lib/ruoyi-shot-grid
```

查看五个服务状态：

```bash
bash deploy/status.sh
```

只看本项目后端日志：

```bash
docker compose --project-name ruoyi-shot-grid-prod \
  --env-file /etc/ruoyi-shot-grid/production.env \
  -f docker-compose.prod.yml \
  logs --tail=200 -f backend
```

查看当前和上一个发布版本：

```bash
cat /var/lib/ruoyi-shot-grid/current-release
cat /var/lib/ruoyi-shot-grid/previous-release
```

回滚上一组应用镜像：

```bash
bash deploy/rollback.sh
```

回滚脚本不会自动回退数据库。涉及不兼容迁移时，必须先评审数据库恢复方案。

查看备份：

```bash
find /var/lib/ruoyi-shot-grid/backups -maxdepth 1 -type f \
  -name 'postgres-*.dump' -printf '%TY-%Tm-%Td %TH:%TM %m %s %p\n' | sort
```

## 10. 修改生产 `.env` 后如何生效

修改 `/etc/ruoyi-shot-grid/production.env` 不会自动改变已经运行的容器。推荐在改动前备份文件，修改后通过下一次正式发布重建容器并执行完整健康门禁。

至少要检查：

```bash
stat -c '%a %U:%G %n' /etc/ruoyi-shot-grid/production.env
grep -n 'CHANGE_ME_' /etc/ruoyi-shot-grid/production.env
```

权限必须是 `600`，第二条命令应无输出。不要用 `docker restart` 代替重新创建容器，因为单纯 restart 不会重新读取 Compose 的 `env_file`。

## 11. 故障排查顺序

页面报错时按链路从外到内检查，不要一开始就删除容器或卷：

1. 浏览器能否访问 `http://192.168.10.122:12580/healthz` 和 `:12581/healthz`；
2. `bash deploy/status.sh` 是否显示五个容器 healthy；
3. 前端 `/prod-api/transport/crypto/frontend-config` 是否返回 200；
4. 后端日志是否有数据库、Redis、权限或迁移异常；
5. PostgreSQL 和 Redis 容器是否健康；
6. 磁盘是否充足：`df -h`、`docker system df`；
7. 只在确认精确范围后处理本项目资源。

常见现象：

| 现象 | 优先检查 |
| --- | --- |
| 页面能打开但提示业务服务不可用 | 后端健康、`/prod-api` 代理、浏览器缓存的传输策略 |
| 修改 `.env` 后没有变化 | 容器是否重新创建，而不是只 restart |
| SQL 日志过多或服务像“卡住” | 确认 `DB_ECHO=false`、`LOG_FILE_ENABLED=false` 和 Docker 日志轮转 |
| 发布中断 | 查看 `deploy/status.sh`、发布输出和 `current-release`，不要直接 `down -v` |
| 数据库迁移失败 | 保留失败现场和迁移前备份，不要手工 stamp 或直接 downgrade |

## 12. 备份与恢复边界

每次发布在迁移前自动执行 PostgreSQL `pg_dump -Fc`，默认保留 14 天。它只覆盖数据库，不覆盖 `backend_files`。

最低备份组合：

- PostgreSQL：`/var/lib/ruoyi-shot-grid/backups/*.dump`；
- 业务文件：`ruoyi-shot-grid-prod_backend_files` 的独立备份；
- 生产配置：加密保存 `/etc/ruoyi-shot-grid/production.env`；
- 恢复说明：记录数据库版本、应用 release ID 和文件备份时间点。

只有完成过克隆环境恢复演练的备份，才能作为正式恢复依据。

## 13. Windows NAS Worker 边界

Ubuntu 容器不能承担真实 Windows UNC/NAS 目录创建和版本发布。生产环境必须保持：

```dotenv
SHOT_GRID_STORAGE_WORKER_ENABLED=false
SHOT_GRID_VERSION_WORKER_ENABLED=false
```

媒体派生可以在 Linux 容器中使用 FFmpeg。真实 NAS 能力需要另行部署 Windows Worker，并验收服务账号、共享 ACL、目录创建、版本发布和失败恢复。

## 14. 当前验收与未覆盖范围

当前生产已验证：五个服务健康、PostgreSQL 迁移、事务写入、Redis、两个前端页面和 `/prod-api` 代理。

仍需按业务版本持续验证：角色权限、项目隔离、文件上传下载、媒体派生、版本审核、容器重启恢复、异机备份恢复和 Windows NAS Worker。健康检查通过不等于完整业务 E2E 通过。
