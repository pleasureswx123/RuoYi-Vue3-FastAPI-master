#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.prod.yml"
ENV_FILE="${RUOYI_ENV_FILE:-$ROOT_DIR/deploy/.env.production}"
STATE_DIR="${RUOYI_DEPLOY_STATE_DIR:-$ROOT_DIR/.deploy}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ruoyi-shot-grid-prod}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

if [[ "$ENV_FILE" != /* ]]; then
    ENV_FILE="$ROOT_DIR/$ENV_FILE"
fi

fail() {
    echo "部署失败：$*" >&2
    exit 1
}

for command_name in docker git flock ss curl findmnt grep stat install; do
    command -v "$command_name" >/dev/null 2>&1 || fail "缺少命令 $command_name"
done

docker compose version >/dev/null 2>&1 || fail 'Docker Compose 插件不可用'
[[ -f "$ENV_FILE" ]] || fail "缺少生产环境文件 $ENV_FILE，请先运行 bash deploy/init-env.sh"
grep -q 'CHANGE_ME_' "$ENV_FILE" && fail '生产环境文件仍包含 CHANGE_ME 占位符'

env_mode="$(stat -c '%a' "$ENV_FILE")"
if (( 10#$env_mode % 100 != 0 )); then
    fail "生产环境文件权限过宽（$env_mode），请执行 chmod 600 '$ENV_FILE'"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$PROJECT_NAME}"
nas_mount_map_compact="${SHOT_GRID_NAS_UNC_MOUNT_MAP:-}"
nas_mount_map_compact="${nas_mount_map_compact//[[:space:]]/}"
if [[ -n "$nas_mount_map_compact" && "$nas_mount_map_compact" != '{}' ]]; then
    backend_app_uid="${BACKEND_APP_UID:-100}"
    backend_app_gid="${BACKEND_APP_GID:-101}"
    [[ "$backend_app_uid" =~ ^[0-9]+$ && "$backend_app_uid" -gt 0 ]] \
        || fail 'BACKEND_APP_UID 必须是正整数'
    [[ "$backend_app_gid" =~ ^[0-9]+$ && "$backend_app_gid" -gt 0 ]] \
        || fail 'BACKEND_APP_GID 必须是正整数'
    nas_host_mount="${SHOT_GRID_NAS_HOST_MOUNT:-/mnt/ruoyi-shot-grid/shotgrid-main}"
    nas_container_mount="${SHOT_GRID_NAS_CONTAINER_MOUNT:-/mnt/ruoyi-shot-grid/shotgrid-main}"
    [[ "$nas_host_mount" = /* ]] || fail 'SHOT_GRID_NAS_HOST_MOUNT 必须是宿主机绝对路径'
    [[ "$nas_container_mount" = /* ]] || fail 'SHOT_GRID_NAS_CONTAINER_MOUNT 必须是容器内绝对路径'
    nas_filesystem_type="$(findmnt -rn -T "$nas_host_mount" -o FSTYPE || true)"
    [[ "$nas_filesystem_type" = cifs || "$nas_filesystem_type" = smb3 ]] \
        || fail "NAS 目录未正确挂载为 cifs/smb3：$nas_host_mount；请先执行 bash deploy/setup-nas-mount.sh"
    nas_mount_options="$(findmnt -rn -T "$nas_host_mount" -o OPTIONS || true)"
    for required_option in "uid=$backend_app_uid" "gid=$backend_app_gid" forceuid forcegid; do
        case ",$nas_mount_options," in
            *",$required_option,"*) ;;
            *) fail "NAS 挂载缺少应用身份参数 $required_option；请重新执行 bash deploy/setup-nas-mount.sh" ;;
        esac
    done
fi

RELEASE_ID="${APP_RELEASE_ID_OVERRIDE:-$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD)}"
export APP_RELEASE_ID="$RELEASE_ID"
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
export RUOYI_ENV_FILE="$ENV_FILE"

mkdir -p "$STATE_DIR/backups"
POSTGRES_INIT_DIR="$STATE_DIR/postgres-init"
POSTGRES_INIT_SQL="$POSTGRES_INIT_DIR/10-ruoyi-fastapi-pg.sql"
install -d -m 0755 "$POSTGRES_INIT_DIR"
install -m 0644 "$ROOT_DIR/ruoyi-fastapi-backend/sql/ruoyi-fastapi-pg.sql" "$POSTGRES_INIT_SQL"
export RUOYI_POSTGRES_INIT_SQL="$POSTGRES_INIT_SQL"

exec 9>"$STATE_DIR/deploy.lock"
flock -n 9 || fail '已有部署正在执行'

COMPOSE=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
CURRENT_RELEASE_FILE="$STATE_DIR/current-release"
PREVIOUS_RELEASE_FILE="$STATE_DIR/previous-release"
previous_release=''
[[ -f "$CURRENT_RELEASE_FILE" ]] && previous_release="$(tr -d '\r\n' < "$CURRENT_RELEASE_FILE")"
switch_started=0

rollback_on_error() {
    local exit_code=$?
    trap - ERR
    echo "发布 $RELEASE_ID 未完成。当前栈状态：" >&2
    "${COMPOSE[@]}" ps >&2 || true
    if [[ "$switch_started" = 1 && -n "$previous_release" && "$previous_release" != "$RELEASE_ID" ]]; then
        echo "尝试回到上一应用镜像 $previous_release；数据库不会自动降级。" >&2
        APP_RELEASE_ID="$previous_release" "${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 240 \
            backend admin-frontend shot-grid-frontend || true
    fi
    exit "$exit_code"
}
trap rollback_on_error ERR

check_port() {
    local port="$1"
    local foreign_projects
    if ! ss -H -ltn "sport = :$port" | grep -q .; then
        return
    fi
    foreign_projects="$(docker ps --filter "publish=$port" --format '{{.Label "com.docker.compose.project"}}' | grep -vx "$PROJECT_NAME" || true)"
    [[ -z "$foreign_projects" ]] || fail "端口 $port 已被其他 Compose 项目占用"
    docker ps --filter "publish=$port" --format '{{.Label "com.docker.compose.project"}}' | grep -qx "$PROJECT_NAME" \
        || fail "端口 $port 已被非本项目进程占用"
}

check_port "${ADMIN_PORT:-12580}"
check_port "${SHOT_GRID_PORT:-12581}"

"${COMPOSE[@]}" config --quiet

build_args=()
if [[ "${DEPLOY_PULL_BASE_IMAGES:-0}" = 1 ]]; then
    build_args+=(--pull)
fi

if [[ "${DEPLOY_SKIP_BUILD:-0}" = 1 ]]; then
    echo "使用已预载的发布镜像：$RELEASE_ID"
    required_images=(
        "ruoyi-shot-grid-backend:$RELEASE_ID"
        "ruoyi-shot-grid-admin-frontend:$RELEASE_ID"
        "ruoyi-shot-grid-business-frontend:$RELEASE_ID"
    )
    for image_name in "${required_images[@]}"; do
        docker image inspect "$image_name" >/dev/null 2>&1 \
            || fail "缺少预载镜像 $image_name，不能跳过构建"
    done
else
    echo "构建发布镜像：$RELEASE_ID"
    "${COMPOSE[@]}" build "${build_args[@]}" backend admin-frontend shot-grid-frontend
fi

echo '启动并等待独立 PostgreSQL / Redis 健康'
"${COMPOSE[@]}" up -d --wait --wait-timeout 180 postgres redis

backup_file="$STATE_DIR/backups/postgres-$(date -u +%Y%m%dT%H%M%SZ)-before-${RELEASE_ID}.dump"
echo "备份数据库到：$backup_file"
if "${COMPOSE[@]}" exec -T postgres sh -ec 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_file"; then
    chmod 600 "$backup_file"
else
    rm -f "$backup_file"
    fail '数据库备份失败，已停止发布'
fi

echo '执行 PostgreSQL Alembic 增量迁移'
"${COMPOSE[@]}" run --rm --no-deps backend \
    ruoyi db upgrade --env=production --output=json --allow-prod --yes --revision=head

echo '执行生产配置、数据库、Redis 与传输加密预检'
"${COMPOSE[@]}" run --rm --no-deps backend ruoyi app doctor --env=production --output=json
"${COMPOSE[@]}" run --rm --no-deps backend ruoyi crypto validate --env=production --output=json

switch_started=1
echo '切换到新应用镜像并等待全部健康检查通过'
"${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 240

curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${ADMIN_PORT:-12580}/healthz" >/dev/null
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${SHOT_GRID_PORT:-12581}/healthz" >/dev/null
"${COMPOSE[@]}" exec -T backend ruoyi ops health --env=production --output=json

if [[ -n "$previous_release" && "$previous_release" != "$RELEASE_ID" ]]; then
    printf '%s\n' "$previous_release" > "$PREVIOUS_RELEASE_FILE"
fi
printf '%s\n' "$RELEASE_ID" > "$CURRENT_RELEASE_FILE"
chmod 600 "$CURRENT_RELEASE_FILE"
[[ ! -f "$PREVIOUS_RELEASE_FILE" ]] || chmod 600 "$PREVIOUS_RELEASE_FILE"

find "$STATE_DIR/backups" -type f -name 'postgres-*.dump' -mtime "+$BACKUP_RETENTION_DAYS" -delete

echo "发布成功：$RELEASE_ID"
echo "管理端：http://${SERVER_IP:-192.168.10.122}:${ADMIN_PORT:-12580}"
echo "Shot Grid：http://${SERVER_IP:-192.168.10.122}:${SHOT_GRID_PORT:-12581}/shot-grid-app/"
"${COMPOSE[@]}" ps
