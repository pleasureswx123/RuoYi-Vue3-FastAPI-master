"""Windows 本地排查库：python deploy/refresh-local-debug.py；--original 切回原开发后端。"""
import argparse
import hashlib
import json
import msvcrt
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "ruoyi-fastapi-backend"
ENV_FILE = ROOT / "shot-grid-frontend/.env.development.local"
REMOTE = "root@192.168.10.122"
BACKUPS = "/var/lib/ruoyi-shot-grid/backups"
DOCKER = ["docker", "--context", "desktop-linux"]
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8", REMOTE]
MARK = re.compile(rb"\n# shotgrid-debug (sg-debug-[a-z0-9-]+)\nVITE_APP_PROXY_TARGET=http://127\.0\.0\.1:\d+\n\Z")
OWNER = "cn.shotgrid.debug=" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]


def run(args, *, stdin=None, env=None):
    result = subprocess.run(args, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-1600:] or "命令执行失败：" + args[0])
    return result.stdout.decode("utf-8", "replace").strip()


def docker(*args, **kw):
    return run([*DOCKER, *args], **kw)


def write_proxy(data):
    if not data:
        ENV_FILE.unlink(missing_ok=True)
        return
    with tempfile.NamedTemporaryFile(dir=ENV_FILE.parent, delete=False) as f:
        f.write(data)
    os.replace(f.name, ENV_FILE)


def stop_snapshot(name):
    ids = docker("ps", "-q", "--filter", f"label={OWNER}", "--filter", f"label=snapshot={name}").split()
    if ids:
        docker("stop", "-t", "5", *ids)


def wait(check, seconds):
    deadline = time.monotonic() + seconds
    while True:
        try:
            if check():
                return
        except (OSError, ValueError, RuntimeError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("等待超时：" + check.__name__)
        time.sleep(1)


def captcha_at(url, redis):
    with urllib.request.urlopen(url + "/captchaImage", timeout=4) as response:
        payload = json.load(response)
    key = payload.get("uuid") or (payload.get("data") or {}).get("uuid")
    return bool(key) and docker("exec", redis, "redis-cli", "-n", "2", "EXISTS", f"captcha_codes:{key}") == "1"


def refresh(args):
    old = ENV_FILE.read_bytes() if ENV_FILE.exists() else b""
    match = MARK.search(old)
    original = old[:match.start()] if match else old
    previous = match[1].decode() if match else None
    if args.original:
        if previous:
            write_proxy(original)
            stop_snapshot(previous)
        print("已恢复原开发代理配置。")
        return

    endpoint = run(["docker", "context", "inspect", "desktop-linux", "--format", "{{.Endpoints.docker.Host}}"])
    if not endpoint.startswith("npipe:"):
        raise RuntimeError("目标必须是本机 Docker Desktop 命名管道")
    latest = run([*SSH, f"find {BACKUPS} -maxdepth 1 -type f -name 'postgres-*.dump' -printf '%T@ %f\\n' | sort -nr | head -1"])
    name = latest.partition(" ")[2]
    if not re.fullmatch(r"postgres-[0-9]{8}T[0-9]{6}Z-[A-Za-z0-9_.-]+\.dump", name):
        raise RuntimeError("没有找到完整的正式备份")
    remote_file = BACKUPS + "/" + name
    checksum = run([*SSH, "sha256sum " + remote_file]).split()[0]
    print("生产备份：" + name, flush=True)
    snap = "sg-debug-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    db = snap.replace("-", "_")
    pg, redis, api = [snap + "-" + part for part in ("pg", "redis", "api")]
    labels = ["--label", OWNER, "--label", "snapshot=" + snap]
    env = dict(os.environ, POSTGRES_PASSWORD=secrets.token_hex(32), JWT_SECRET_KEY=secrets.token_hex(48))
    env["DB_PASSWORD"] = env["POSTGRES_PASSWORD"]
    switched = False
    with tempfile.TemporaryDirectory(prefix="shotgrid-backup-") as temp:
        dump = Path(temp) / name
        run(["scp", "-q", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", REMOTE + ":" + remote_file, str(dump)])
        with dump.open("rb") as f:
            if f.read(5) != b"PGDMP":
                raise RuntimeError("备份格式错误")
            f.seek(0)
            if hashlib.file_digest(f, "sha256").hexdigest() != checksum:
                raise RuntimeError("备份 SHA-256 校验失败")
        # 优先复用上次验证过的本机运行时，依赖有变动时重新构建。
        cached = docker("image", "ls", "-q", "shotgrid-debug-local:runtime")
        if not args.runtime_image and cached:
            candidate = docker("run", "--rm", "--network", "none", "--entrypoint", "cat",
                               "shotgrid-debug-local:runtime", "/app/requirements-pg.lock.txt")
            if candidate.splitlines() == (BACKEND / "requirements-pg.lock.txt").read_text(encoding="utf-8").strip().splitlines():
                args.runtime_image = "shotgrid-debug-local:runtime"
        if args.runtime_image:
            image = args.runtime_image
            locked = docker("run", "--rm", "--network", "none", "--entrypoint", "cat", image, "/app/requirements-pg.lock.txt")
            if locked.splitlines() != (BACKEND / "requirements-pg.lock.txt").read_text(encoding="utf-8").strip().splitlines():
                raise RuntimeError("本地运行时与当前后端依赖锁不一致")
        else:
            image = "shotgrid-debug-local:runtime"
            docker("build", "-f", str(BACKEND / "Dockerfile.prod"), "-t", image, str(BACKEND))
        docker("network", "create", "--internal", *labels, snap)
        common = ["--network", snap, *labels]
        try:
            docker("run", "-d", *common, "--name", pg, "--network-alias", "postgres", "-e", "POSTGRES_PASSWORD",
                   "-e", "POSTGRES_DB=" + db, "--mount", f"type=volume,src={pg},dst=/var/lib/postgresql/data",
                   "postgres:16-alpine", env=env)
            def postgres_ready():
                return docker("exec", pg, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", db).endswith("accepting connections")
            wait(postgres_ready, 70)
            with dump.open("rb") as f:
                docker("exec", "-i", pg, "pg_restore", "--single-transaction", "--exit-on-error", "--no-owner",
                       "--no-acl", "-U", "postgres", "-d", db, stdin=f)

            def sql(statement):
                return docker("exec", pg, "psql", "-XAt", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", db, "-c", statement)

            baseline = sql("select version_num from alembic_version")
            # 仅处理新副本中的调度状态，保留所有制作任务、版本和原始队列记录。
            sql("update sys_job set status='1' where status='0'; "
                "do $$ begin if to_regclass('public.apscheduler_jobs') is not null then "
                "delete from public.apscheduler_jobs; end if; end $$;")
            docker("run", "-d", *common, "--name", redis, "--network-alias", "redis", "redis:7-alpine")
            config = dict(DB_TYPE="postgresql", DB_HOST="postgres", DB_PORT="5432", DB_USERNAME="postgres",
                          DB_DATABASE=db, DB_ECHO="false", REDIS_HOST="redis", REDIS_PORT="6379", REDIS_DATABASE="2",
                          APP_IP_LOCATION_QUERY="false", APP_ROOT_PATH="/dev-api", TRANSPORT_CRYPTO_ENABLED="false",
                          TRANSPORT_CRYPTO_MODE="off", SHOT_GRID_STORAGE_WORKER_ENABLED="false",
                          SHOT_GRID_VERSION_WORKER_ENABLED="false", SHOT_GRID_MEDIA_WORKER_ENABLED="false",
                          SHOT_GRID_NAS_UNC_MOUNT_MAP="{}", SHOT_GRID_NAS_SERVER_MOUNT_MAP="{}",
                          SHOT_GRID_NAS_SIGNING_KEY_FILE="/disabled/no-signing-key", PYTHONPATH="/app")
            backend_args = [*common, "-e", "DB_PASSWORD", "-e", "JWT_SECRET_KEY"]
            for k, v in config.items():
                backend_args.extend(["-e", k + "=" + v])
            # 逐项挂载源码，不把本机 .env、上传目录、NAS 或 Docker 套接字交给容器。
            sources = ("alembic alembic.ini app.py assets cli common config exceptions middlewares module_admin "
                       "module_generator module_plugin module_realtime module_shot_grid module_task plugins server.py "
                       "sql sub_applications utils").split()
            for src in sources:
                backend_args.extend(["--mount", f"type=bind,src={BACKEND / src},dst=/app/{src},readonly"])
            docker("run", "--rm", *backend_args, image, "python", "-m", "alembic", "upgrade", "head", env=env)
            head = sql("select version_num from alembic_version")
            counts = sql("select (select count(*) from sg_project),(select count(*) from sg_shot),"
                         "(select count(*) from sg_task),(select count(*) from sg_asset)")
            docker("run", "-d", *backend_args, "--name", api, "--network-alias", "backend", image, "python", "-m",
                   "uvicorn", "server:create_app", "--factory", "--host", "0.0.0.0", "--port", "9099", env=env)
            # internal 网络禁止发布端口，使用仅转发到本副本的回环入口。
            edge = snap + "-entry"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            gateway = Path(temp) / "default.conf"
            gateway.write_text("""map $http_upgrade $connection_upgrade { default upgrade; '' close; }
server {
    listen 80;
    client_max_body_size 100m;
    resolver 127.0.0.11 valid=5s;
    location / {
        set $local_backend backend:9099;
        proxy_pass http://$local_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 300s;
        proxy_request_buffering off;
        proxy_buffering off;
    }
}
""", encoding="utf-8")
            docker("create", *labels, "--name", edge, "--network", "bridge", "-p", f"127.0.0.1:{port}:80",
                   "nginx:1.30.6-alpine")
            docker("cp", str(gateway), edge + ":/etc/nginx/conf.d/default.conf")
            docker("network", "connect", snap, edge)
            docker("start", edge)
            target = f"http://127.0.0.1:{port}"
            wait(lambda: captcha_at(target, redis), 90)
            if (ENV_FILE.read_bytes() if ENV_FILE.exists() else b"") != old:
                raise RuntimeError("本地代理配置在恢复期间被修改，已取消切换")
            write_proxy(original + f"\n# shotgrid-debug {snap}\nVITE_APP_PROXY_TARGET={target}\n".encode())
            switched = True
            wait(lambda: captcha_at("http://127.0.0.1:5174/dev-api", redis), 35)
            docker("update", "--restart", "unless-stopped", pg, redis, api, edge)
        except BaseException:
            if switched:
                write_proxy(old)
            stop_snapshot(snap)
            print("失败副本已留在本机供排查：" + snap, file=sys.stderr)
            raise
    if previous:
        stop_snapshot(previous)
    print(f"已验证 5174 → {target} → {db}\n迁移 {baseline} → {head}；项目|镜头|任务|资产：{counts}\nSHA-256 {checksum}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", action="store_true", help="切回原开发后端，保留排查数据卷")
    parser.add_argument("--runtime-image", help="复用本机已构建的项目后端依赖镜像，仍加载当前源码")
    args = parser.parse_args()
    lock = Path(tempfile.gettempdir()) / (OWNER.split("=")[1] + "-shotgrid-refresh.lock")
    try:
        with lock.open("a+b") as handle:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            refresh(args)
    except (RuntimeError, OSError) as error:
        sys.exit(str(error))
