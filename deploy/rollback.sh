#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${RUOYI_ENV_FILE:-$ROOT_DIR/deploy/.env.production}"
STATE_DIR="${RUOYI_DEPLOY_STATE_DIR:-$ROOT_DIR/.deploy}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ruoyi-shot-grid-prod}"
TARGET_RELEASE="${1:-}"

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

# 发布与回滚共用一把锁，读取发布指针也必须在锁内。
mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/deploy.lock"
flock -n 9 || {
    echo '已有发布或回滚正在执行，拒绝并发回滚' >&2
    exit 1
}
if [[ -z "$TARGET_RELEASE" && -f "$STATE_DIR/previous-release" ]]; then
    TARGET_RELEASE="$(tr -d '\r\n' < "$STATE_DIR/previous-release")"
fi
[[ -n "$TARGET_RELEASE" ]] || {
    echo '用法：bash deploy/rollback.sh <release-id>' >&2
    exit 1
}
[[ "$TARGET_RELEASE" =~ ^[0-9A-Za-z._-]+$ ]] || {
    echo 'release-id 格式非法' >&2
    exit 1
}

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$PROJECT_NAME}"
export RUOYI_ENV_FILE="$ENV_FILE"
export APP_RELEASE_ID="$TARGET_RELEASE"
COMPOSE=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$ROOT_DIR/docker-compose.prod.yml")

for image_name in \
    "ruoyi-shot-grid-backend:$TARGET_RELEASE" \
    "ruoyi-shot-grid-admin-frontend:$TARGET_RELEASE" \
    "ruoyi-shot-grid-business-frontend:$TARGET_RELEASE"
do
    docker image inspect "$image_name" >/dev/null 2>&1 || {
        echo "缺少回滚镜像：$image_name" >&2
        exit 1
    }
done

current_release=''
[[ -f "$STATE_DIR/current-release" ]] && current_release="$(tr -d '\r\n' < "$STATE_DIR/current-release")"

echo '先验证目标镜像能够识别当前数据库迁移版本；预检失败时不切换应用。'
"${COMPOSE[@]}" run --rm --no-deps backend python -m alembic -c alembic.ini current || {
    echo '回滚已阻止：目标镜像无法读取当前迁移版本，请使用兼容镜像或执行已评审的数据库恢复方案。' >&2
    exit 1
}

echo "仅回滚应用镜像到 $TARGET_RELEASE；数据库不会降级。"
"${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 240 \
    backend admin-frontend shot-grid-frontend
"${COMPOSE[@]}" exec -T backend ruoyi ops health --env=production --output=json

mkdir -p "$STATE_DIR"
[[ -z "$current_release" ]] || printf '%s\n' "$current_release" > "$STATE_DIR/previous-release"
printf '%s\n' "$TARGET_RELEASE" > "$STATE_DIR/current-release"
chmod 600 "$STATE_DIR/current-release"
[[ ! -f "$STATE_DIR/previous-release" ]] || chmod 600 "$STATE_DIR/previous-release"

echo "应用镜像回滚完成：$TARGET_RELEASE"
