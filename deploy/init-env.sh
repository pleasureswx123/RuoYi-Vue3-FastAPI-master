#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE_FILE="$ROOT_DIR/deploy/.env.production.example"
ENV_FILE="$ROOT_DIR/deploy/.env.production"
SERVER_IP="${1:-192.168.10.122}"

if [[ -e "$ENV_FILE" ]]; then
    echo "拒绝覆盖已有生产环境文件：$ENV_FILE" >&2
    exit 1
fi

for command_name in openssl sed awk; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "缺少命令：$command_name" >&2
        exit 1
    }
done

umask 077
cp "$EXAMPLE_FILE" "$ENV_FILE"

postgres_password="$(openssl rand -hex 24)"
redis_password="$(openssl rand -hex 24)"
jwt_secret="$(openssl rand -hex 48)"
crypto_kid="prod-$(date -u +%Y%m%d%H%M%S)"
private_key="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 2>/dev/null)"
public_key="$(printf '%s\n' "$private_key" | openssl pkey -pubout 2>/dev/null)"

pem_to_env() {
    awk '{printf "%s\\n", $0}'
}

private_key_env="$(printf '%s\n' "$private_key" | pem_to_env)"
public_key_env="$(printf '%s\n' "$public_key" | pem_to_env)"
cors_origins="http://${SERVER_IP}:12580,http://${SERVER_IP}:12581"

replace_token() {
    local token="$1"
    local value="$2"
    local escaped
    escaped="$(printf '%s' "$value" | sed 's/[\\&|]/\\&/g')"
    sed -i "s|${token}|${escaped}|g" "$ENV_FILE"
}

replace_token CHANGE_ME_POSTGRES_PASSWORD "$postgres_password"
replace_token CHANGE_ME_REDIS_PASSWORD "$redis_password"
replace_token CHANGE_ME_JWT_SECRET "$jwt_secret"
replace_token CHANGE_ME_CORS_ORIGINS "$cors_origins"
replace_token CHANGE_ME_CRYPTO_KID "$crypto_kid"
replace_token CHANGE_ME_CRYPTO_PUBLIC_KEY "$public_key_env"
replace_token CHANGE_ME_CRYPTO_PRIVATE_KEY "$private_key_env"

if grep -q 'CHANGE_ME_' "$ENV_FILE"; then
    echo '生产环境文件仍包含未替换占位符，初始化失败。' >&2
    exit 1
fi

chmod 600 "$ENV_FILE"
echo "已生成：$ENV_FILE"
echo '请人工核对端口、CORS、数据库名和 Worker 边界；不要提交该文件。'
