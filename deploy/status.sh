#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${RUOYI_ENV_FILE:-$ROOT_DIR/deploy/.env.production}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ruoyi-shot-grid-prod}"

if [[ "$ENV_FILE" != /* ]]; then
    ENV_FILE="$ROOT_DIR/$ENV_FILE"
fi

[[ -f "$ENV_FILE" ]] || {
    echo "缺少生产环境文件：$ENV_FILE" >&2
    exit 1
}

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$PROJECT_NAME}"
export RUOYI_ENV_FILE="$ENV_FILE"
export APP_RELEASE_ID="${APP_RELEASE_ID_OVERRIDE:-${APP_RELEASE_ID:-local}}"
COMPOSE=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$ROOT_DIR/docker-compose.prod.yml")

nas_mount_map_compact="${SHOT_GRID_NAS_UNC_MOUNT_MAP:-}"
nas_mount_map_compact="${nas_mount_map_compact//[[:space:]]/}"
if [[ -n "$nas_mount_map_compact" && "$nas_mount_map_compact" != '{}' ]]; then
    nas_host_mount="${SHOT_GRID_NAS_HOST_MOUNT:-/mnt/ruoyi-shot-grid/shotgrid-main/ShotGridProd}"
    echo "后端应用身份：UID ${BACKEND_APP_UID:-100} / GID ${BACKEND_APP_GID:-101}"
    echo "NAS 挂载："
    findmnt -T "$nas_host_mount" -o TARGET,SOURCE,FSTYPE,OPTIONS || true
    echo
fi

"${COMPOSE[@]}" ps
echo
"${COMPOSE[@]}" exec -T backend ruoyi ops health --env=production --output=json
echo
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${ADMIN_PORT:-12580}/healthz"
echo
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${SHOT_GRID_PORT:-12581}/healthz"
echo
