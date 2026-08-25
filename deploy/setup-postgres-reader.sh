#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${RUOYI_ENV_FILE:-/etc/ruoyi-shot-grid/production.env}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ruoyi-shot-grid-prod}"
CREDENTIAL_FILE="${POSTGRES_READER_CREDENTIAL_FILE:-/etc/ruoyi-shot-grid/navicat-reader.env}"

fail() {
    echo "PostgreSQL 只读账号配置失败：$*" >&2
    exit 1
}

[[ "$(id -u)" = 0 ]] || fail '请使用 root 执行本脚本'
for command_name in docker grep install mktemp openssl rm stat; do
    command -v "$command_name" >/dev/null 2>&1 || fail "缺少命令 $command_name"
done
docker compose version >/dev/null 2>&1 || fail 'Docker Compose 插件不可用'
[[ -f "$ENV_FILE" ]] || fail "缺少生产环境文件 $ENV_FILE"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$PROJECT_NAME}"
reader_role="${POSTGRES_READER_ROLE:-ruoyi_navicat_reader}"
reader_host="${POSTGRES_BIND_ADDRESS:-127.0.0.1}"
reader_port="${POSTGRES_PORT:-12582}"
[[ "$reader_role" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || fail 'POSTGRES_READER_ROLE 不是安全的 PostgreSQL 角色名'
[[ "$reader_port" =~ ^[0-9]+$ && "$reader_port" -ge 1 && "$reader_port" -le 65535 ]] \
    || fail 'POSTGRES_PORT 必须是 1—65535 的端口号'

export RUOYI_ENV_FILE="$ENV_FILE"
COMPOSE=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$ROOT_DIR/docker-compose.prod.yml")
"${COMPOSE[@]}" ps --status running postgres | grep -q postgres || fail 'PostgreSQL 容器尚未运行'

reader_password="$(openssl rand -hex 24)"
{
    printf "\\set reader_role '%s'\n" "$reader_role"
    printf "\\set reader_password '%s'\n" "$reader_password"
    cat <<'SQL'
\set ON_ERROR_STOP on
SELECT format('CREATE ROLE %I LOGIN', :'reader_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'reader_role')
\gexec
SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 3 PASSWORD %L',
    :'reader_role',
    :'reader_password'
)
\gexec
SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'reader_role')
\gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'reader_role', '30s')
\gexec
SELECT format('ALTER ROLE %I SET idle_in_transaction_session_timeout = %L', :'reader_role', '60s')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'reader_role')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'reader_role')
\gexec
SELECT format('GRANT SELECT ON TABLE %I.%I TO %I', schemaname, tablename, :'reader_role')
FROM pg_tables
WHERE schemaname = 'public' AND tablename LIKE 'sg\_%' ESCAPE '\'
ORDER BY tablename
\gexec
SQL
} | "${COMPOSE[@]}" exec -T postgres sh -ec 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    >/dev/null

umask 077
install -d -m 0700 "$(dirname "$CREDENTIAL_FILE")"
credential_tmp="$(mktemp "$(dirname "$CREDENTIAL_FILE")/.navicat-reader.XXXXXX")"
cleanup() {
    rm -f -- "$credential_tmp"
    unset reader_password
}
trap cleanup EXIT
{
    printf 'host=%s\n' "$reader_host"
    printf 'port=%s\n' "$reader_port"
    printf 'database=%s\n' "$POSTGRES_DB"
    printf 'username=%s\n' "$reader_role"
    printf 'password=%s\n' "$reader_password"
    printf 'sslmode=disable\n'
} > "$credential_tmp"
install -m 0600 "$credential_tmp" "$CREDENTIAL_FILE"
[[ "$(stat -c '%a' "$CREDENTIAL_FILE")" = 600 ]] || fail '只读账号凭据文件权限不是 0600'

echo "PostgreSQL Navicat 只读账号已配置：$reader_host:$reader_port / $POSTGRES_DB / $reader_role"
echo "凭据保存在：$CREDENTIAL_FILE（0600，不会输出密码）"
