# 管理平台浏览器测试

本目录使用真实 Chromium 检查管理平台的登录、页面及管理操作。当前完整应用以 PostgreSQL 为准，MySQL Compose 仅保留历史参考，不作为 Shot Grid 的有效验收环境。

## 启动独立环境

从仓库根目录执行，先设置随机测试密钥（只用于临时库）：

```powershell
$env:COMPOSE_PROJECT_NAME = 'shotgrid-ci-local'
$env:CI_DB_PASSWORD = [guid]::NewGuid().ToString('N')
$env:CI_JWT_SECRET = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
docker compose -f ruoyi-fastapi-test/docker-compose.test.pg.yml up -d --build --wait --wait-timeout 240
```

管理端默认 `http://localhost:18080`，后端默认 `http://localhost:19099`。独立 PostgreSQL/Redis 不开放宿主端口，未配置 NAS，目录、版本发布和媒体 Worker 均关闭。不要把测试连接指向生产环境。

该环境使用全新初始化 SQL 和测试专用的验证码关闭脚本，账号为初始化测试账号 `admin / admin123`。Swagger/Redoc 在本环境显式关闭，测试验证禁用提示。明文 HTTP 仅用于此本机隔离测试；这些测试不证明验证码或传输加密流程通过，也不是使用生产账号进行业务验收。

## 执行测试

使用 Python 3.11 及以上，在独立虚拟环境执行：

```powershell
python -m pip install -r ruoyi-fastapi-test/requirements.txt
python -m playwright install chromium
cd ruoyi-fastapi-test
python -m pytest -v --junitxml=test-results/results.xml
```

需要更换端口时，启动前设置 `CI_FRONTEND_PORT` / `CI_BACKEND_PORT`，测试时同时设置 `TEST_FRONTEND_URL` / `TEST_BACKEND_URL`。默认测试主机名为 localhost，认证 Cookie 与该主机匹配。

完成后仅清理上述独立 Compose 项目（会删除其临时数据库）：

```powershell
# 回到仓库根目录，保留同一个 COMPOSE_PROJECT_NAME 和测试密钥环境变量
docker compose -f ruoyi-fastapi-test/docker-compose.test.pg.yml down -v --remove-orphans
```

## GitHub 自动检查

`.github/workflows/playwright.yml` 使用生产 Dockerfile 构建测试镜像，通过 GitHub 缓存复用镜像层；每次运行使用独立 Compose 项目名和随机密钥。等待真实健康检查后执行本目录完整测试，失败时保存容器日志和 JUnit 结果，最后清理本轮环境。

多 Python 版本的后端检查由 `backend.yml` 负责，浏览器流程不再重复启动八套包含不受支持配置的环境。此流程覆盖管理平台，不等同于 Shot Grid 全部制作流程、真实 NAS 或生产部署验收。
