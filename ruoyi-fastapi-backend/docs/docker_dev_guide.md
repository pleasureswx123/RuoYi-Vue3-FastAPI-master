# 后端 Docker 本地开发指南

## 1. 目标与边界

本地开发使用根目录 `docker-compose.dev.yml` 启动后端、PostgreSQL 和 Redis。后端镜像固定为 Python 3.11.15，并内置 FFmpeg，避免依赖每台开发机的 Python 与 FFmpeg 安装状态。Docker 后端通过 `requirements-pg.lock.txt` 精确锁定 Python 依赖；`requirements-pg.txt` 继续作为直接依赖清单。

前端仍在宿主机运行，通过 Vite 将 `/dev-api` 代理到 `127.0.0.1:9099`。

Linux 后端容器不能把 Windows UNC 路径直接当成本地文件系统路径使用，因此本地开发 Compose 明确关闭目录 Worker 和版本发布 Worker，只启用读取平台私有文件的媒体派生 Worker。本拓扑不能作为真实 UNC/SMB/NAS 验收证据。公司生产 Linux 按根目录 `deploy/README.md` 使用宿主机 autofs 动态挂载 `192.168.10.64` 下的共享，并通过 `SHOT_GRID_NAS_SERVER_MOUNT_MAP` 做固定服务器级解析；普通 bind 目录、未验证的挂载点、其他 UNC 服务器或临时本地目录仍会失败关闭。

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


## 当前 Windows 本机联调入口（2026-10-27）

本机已配置真实本地 PostgreSQL、Redis 与 Windows UNC 存储，适合继续优化页面流程。业务源码目录结构保持原样，新增数据、示例媒体、日志及启动脚本位于原有 `output/local-runtime/` 运行目录。

在仓库根目录执行：

```powershell
& ./output/local-runtime/start-local.ps1
```

打开 `http://127.0.0.1:5174/projects`，刷新登录态后选择“本地流程演示”。当前 admin 在此项目兼具管理与制作角色，可测试分配、排期、开工、版本提交和审核。已有 2 个场次、4 个镜头、角色/场景/道具各 1 个资产；保留待分配、待开工、待审核和已完成内容。日期筛选示例为 2026-10-27 至 2026-10-31。

创建新项目时，选择“本地联调存储（当前电脑）”，给当前账号设置项目管理人（如需本人制作，同时选择制作人员）。其实际磁盘位置为 `D:/lqh/shot-grid-main/shot-grid/output/local-runtime/local-nas`，通过已有 `\\localhost\D$` 共享访问。不能把此本机根目录用于公司部署；服务账号或机器变更后须重新探测。

已完成的运行验证：角色和存储选项、真实项目目录初始化、业务对象创建、任务分配/排期/开工、受保护图片及 MP4 上传、版本发布、缩略图与视频代理、图片审核通过、最终文件与清单落盘、文件哈希校验、视频 206 Range。匿名文件请求被鉴权拒绝。未执行完整浏览器 E2E；前轮记录的 8 个扩展回归失败未在本轮修复。

本机 FFmpeg 通过 `python -m pip install imageio-ffmpeg` 安装到现有 .venv，并由 `.env.dev` 的 `SHOT_GRID_MEDIA_WORKER_FFMPEG_PATH` 指向实际程序；未改变生产依赖文件。目录、版本和媒体 Worker 均已开启。Redis/数据库/运行文件需一并保留，勿清理 output/local-runtime 来“重置页面”。

### 网页“服务暂时不可用”排查（2026-10-28）

本次故障由 PostgreSQL 15432 异常退出导致，其他三个服务仍在运行，单看页面或端口 9099 不能确认业务可用。数据库日志记录子进程异常码 `0xC0000135`，具体系统依赖原因尚未确认；原始日志保留在 `output/local-runtime/postgres-crash-20261028.err`。

现有启动命令已增强：复用 `pg-data`，使用 `pg_ctl` 等待数据库恢复完成，再检查数据库查询和网页代理到后端/Redis 的验证码接口。新数据库服务日志追加至 `output/local-runtime/postgres-server.log`，启动控制信息位于 `postgres-control.log` / `postgres-control.err`；重新启动其他服务前也会备份旧日志。脚本只补启动缺失服务，不清空数据、不自动结束占用端口的程序、不注册系统服务或开机任务。

本次已恢复并通过实际登录、项目列表和项目详情请求；原演示项目与媒体版本仍在。若再次提示不可用，可重新执行上述启动命令并保留输出及日志；不要删除 `pg-data`、运行 `initdb` 或手工移除数据库锁文件。此脚本是手动恢复入口，不是后台监控程序；完整浏览器 E2E 未在本次执行。
