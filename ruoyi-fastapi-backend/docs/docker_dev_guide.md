# 后端 Docker 本地开发指南

## 1. 目标与边界

本地开发使用根目录 `docker-compose.dev.yml` 启动后端、PostgreSQL 和 Redis。后端镜像固定为 Python 3.11.15，并内置 FFmpeg，避免依赖每台开发机的 Python 与 FFmpeg 安装状态。Docker 后端通过 `requirements-pg.lock.txt` 精确锁定 Python 依赖；`requirements-pg.txt` 继续作为直接依赖清单。

前端仍在宿主机运行，通过 Vite 将 `/dev-api` 代理到 `127.0.0.1:9099`。

Linux 后端容器不能把 Windows UNC 路径直接当成本地文件系统路径使用，因此本地开发 Compose 明确关闭目录 Worker 和版本发布 Worker，只启用读取平台私有文件的媒体派生 Worker。本拓扑不能作为真实 UNC/SMB/NAS 验收证据。生产 Linux 可按根目录 `deploy/README.md` 使用受保护凭据挂载 CIFS，并通过 `SHOT_GRID_NAS_UNC_MOUNT_MAP` 做显式路径映射；普通 bind 目录、未验证的挂载点或临时本地目录仍会失败关闭。

## 2. 启动

在仓库根目录执行：

```powershell
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml ps
```

查看后端日志：

```powershell
docker compose -f docker-compose.dev.yml logs -f backend
```

后端地址：

```text
http://127.0.0.1:9099
http://127.0.0.1:9099/openapi.json
```

## 3. 验证 Python 与 FFmpeg

```powershell
docker compose -f docker-compose.dev.yml exec backend python --version
docker compose -f docker-compose.dev.yml exec backend ffmpeg -version
```

预期 Python 为 `3.11.15`；FFmpeg 版本由固定基础镜像对应的 Debian 软件仓库提供，并随已构建后端镜像保持一致。

## 4. 数据和文件

- PostgreSQL 与 Redis 使用命名卷持久化。
- 后端源码以 bind mount 挂载到 `/app`，保留 Uvicorn 热更新。
- `vf_admin/` 随后端目录挂载，已有平台私有文件可被媒体派生 Worker 读取。
- `.env.dev` 仍是宿主机配置来源；Compose 只覆盖容器内的数据库、Redis 地址以及三个 Worker 开关。

## 5. 停止

```powershell
docker compose -f docker-compose.dev.yml down
```

普通停止不会删除 PostgreSQL 或 Redis 数据卷。除非明确要清空本地数据，不要执行 `down -v`。
