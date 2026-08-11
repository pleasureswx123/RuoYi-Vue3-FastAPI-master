# Shot Grid PostgreSQL 联调报告（2026-08-11）

## 1. 结论

本次联调**未达到可执行前置条件，因此不通过，也不视为部分 E2E 通过**。

- 执行环境未安装 `docker` 命令，无法按要求使用根目录
  `docker-compose.dev.yml` 启动 PostgreSQL 和 Redis。
- 在后端目录实际执行 `ruoyi app doctor --env=dev` 后，CLI 在建立连接前即报告当前
  Python 环境缺少 PostgreSQL 的 `asyncpg` 和 `psycopg2` 驱动。
- 因数据库、Redis 和 FastAPI 均未成功启动，未创建或修改任何联调账号和业务数据，
  也未发出登录、Shot Grid CRUD 或发现类 HTTP 请求。
- 下述账号、权限、业务 CRUD、乐观锁、唯一约束、事务回滚和父资源归档隔离项目均标记为
  **未执行**，不能以路由源码、Swagger、静态检查或单元测试替代。

## 2. 环境与实际命令

仓库路径：`/workspace/RuoYi-Vue3-FastAPI-master`

执行日期（UTC）：2026-08-11

### 2.1 基础设施启动

实际执行：

```bash
docker compose -f docker-compose.dev.yml up -d
```

结果：失败，Shell 返回 `/bin/bash: docker: command not found`。因此未执行数据库初始化 SQL，
也没有可供本次报告核验的 PostgreSQL 或 Redis 容器状态。

### 2.2 后端 CLI 诊断

实际执行：

```bash
cd ruoyi-fastapi-backend
ruoyi app doctor --env=dev
```

结果：失败。CLI 报告 PostgreSQL 模式缺少 `asyncpg（异步）` 和 `psycopg2（同步）`，并建议运行：

```bash
python -m pip install -r requirements-pg.txt
```

由于基础设施启动已经被缺失的 Docker 阻断，本次未通过临时安装 Python 依赖伪造一个与
`docker-compose.dev.yml` 不同的验收环境，也未继续执行 `ruoyi app run --env=dev`。

## 3. 验证矩阵

| 验证范围 | 状态 | 实际证据或阻断原因 |
| --- | --- | --- |
| PostgreSQL、Redis 容器启动与健康检查 | 阻断 | 环境无 `docker` 命令 |
| CLI doctor 与 FastAPI 启动 | 阻断 | doctor 缺少 PostgreSQL 驱动；基础设施未启动 |
| 管理员、项目总监、制作人员、非项目成员四类账号 | 未执行 | 未连接 PostgreSQL，不写入账号、角色、菜单或成员关系 |
| 登录、`/getInfo`、`/shot-grid/navigation`、退出、刷新恢复 | 未执行 | FastAPI 未启动，无 HTTP 请求或响应 |
| 项目创建、详情、修改、归档、成员添加、恢复、移除、角色调整 | 未执行 | 无可用 API、数据库和 Redis |
| 集、场次、镜头、资产、制作分项的列表、详情、创建、修改、排序、归档 | 未执行 | 无可用 API 和数据库 |
| `lockVersion`、HTTP 409、稳定 `errorKey` | 未执行 | 未发出并发或过期版本写请求 |
| PostgreSQL 唯一约束和事务回滚 | 未执行 | 未执行数据库写入和事务故障注入 |
| 归档父资源后的工作台、搜索、概览、任务和文件发现隔离 | 未执行 | 未建立可归档的父子资源测试数据 |

## 4. 请求、响应与持久化证据

本次没有成功启动服务，故没有可记录的业务 HTTP 请求、脱敏响应或数据库持久化结果。
为避免产生虚假通过证据，本报告不粘贴由源码推测的请求/响应，也不把已有接口定义当作实际请求。

| 证据类型 | 本次记录 |
| --- | --- |
| 实际 HTTP 请求 | 无（服务未启动） |
| 脱敏 HTTP 响应 | 无（服务未启动） |
| PostgreSQL 查询结果 | 无（数据库未启动） |
| Redis 会话结果 | 无（Redis 未启动） |

## 5. 重新联调的必要条件与顺序

1. 在具有 Docker Compose 的执行环境中，从仓库根目录执行
   `docker compose -f docker-compose.dev.yml up -d`，并保留 `docker compose ... ps` 的健康状态证据。
2. 在隔离的 Python 环境安装 `requirements-pg.txt`，执行
   `ruoyi app doctor --env=dev`，诊断通过后再执行 `ruoyi app run --env=dev`。
3. 使用专用、非生产联调账号和唯一的本次运行数据前缀；分别控制平台菜单权限与
   Shot Grid 项目成员关系，不在报告中记录明文密码或 Token。
4. 严格按本报告第 3 节的顺序发出真实 HTTP 请求，并为每项记录：请求方法与路径、
   脱敏请求体、状态码、脱敏响应、随后执行的 PostgreSQL 查询及结果。
5. 对所有写操作分别保留成功版本、过期 `lockVersion` 的 409 响应和稳定 `errorKey`；
   唯一约束与回滚必须同时用 API 响应和事务后的数据库行状态证明。
6. 最后归档父资源，再重新查询工作台、搜索、概览、任务和文件发现接口，证明子资源未被暴露。
   只有全部链路都由实际请求和持久化证据支持时，才能把本报告状态改为通过。
