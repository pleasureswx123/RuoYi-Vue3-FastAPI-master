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

"${COMPOSE[@]}" ps
echo
"${COMPOSE[@]}" exec -T backend ruoyi ops health --env=production --output=json
echo
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${ADMIN_PORT:-12580}/healthz"
echo
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${SHOT_GRID_PORT:-12581}/healthz"
echo
