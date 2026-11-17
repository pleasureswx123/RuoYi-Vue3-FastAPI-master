#!/usr/bin/env bash
# 执行完整发布脚本，用命令替身验证停写顺序和失败关闭，不连接真实服务。
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_dir="$(mktemp -d /tmp/sg-deploy-gate.XXXXXX)"
[[ "$test_dir" = /tmp/sg-deploy-gate.* ]] || exit 1
trap 'rm -rf -- "$test_dir"' EXIT
mkdir -p "$test_dir/bin" "$test_dir/state"
cat > "$test_dir/bin/docker" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GATE_LOG"
case "$*" in
    *'pg_dump '*) [[ "$GATE_FAILURE" != backup ]] || exit 9; printf '测试备份\n' ;;
    *'ruoyi db upgrade '*) [[ "$GATE_FAILURE" != migration ]] || exit 9 ;;
    *'ruoyi app doctor '*) [[ "$GATE_FAILURE" != doctor ]] || exit 9 ;;
    *' up -d --no-build --wait '*) [[ "$GATE_FAILURE" != switch ]] || exit 9 ;;
esac
exit 0
MOCK
for command_name in git ss curl findmnt setpriv systemctl; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$test_dir/bin/$command_name"
done
chmod +x "$test_dir/bin/"*
export PATH="$test_dir/bin:$PATH"
export RUOYI_ENV_FILE="$test_dir/env"
export RUOYI_DEPLOY_STATE_DIR="$test_dir/state"
export GATE_LOG="$test_dir/calls"
export DEPLOY_SKIP_BUILD=1 APP_RELEASE_ID_OVERRIDE=candidate
unset DEPLOY_STOP_BACKEND_FOR_MIGRATION
printf 'COMPOSE_PROJECT_NAME=sg-deploy-gate-test\nSHOT_GRID_NAS_SERVER_MOUNT_MAP="{}"\nSHOT_GRID_NAS_UNC_MOUNT_MAP="{}"\n' > "$RUOYI_ENV_FILE"
chmod 600 "$RUOYI_ENV_FILE"

for failure in none backup migration doctor switch; do
    export GATE_FAILURE="$failure"
    printf 'previous\n' > "$test_dir/state/current-release"
    : > "$GATE_LOG"
    result=0
    bash "$ROOT_DIR/deploy/deploy.sh" > "$test_dir/$failure.log" 2>&1 || result=$?
    stop_line="$(grep -n ' stop backend' "$GATE_LOG" | head -1 | cut -d: -f1)"
    backup_line="$(grep -n 'pg_dump ' "$GATE_LOG" | head -1 | cut -d: -f1)"
    [[ -n "$stop_line" && -n "$backup_line" && "$stop_line" -lt "$backup_line" ]]
    if [[ "$failure" = none ]]; then
        [[ "$result" = 0 ]]
        [[ "$(cat "$test_dir/state/current-release")" = candidate ]]
        migration_line="$(grep -n 'ruoyi db upgrade ' "$GATE_LOG" | cut -d: -f1)"
        switch_line="$(grep -n ' up -d --no-build --wait ' "$GATE_LOG" | cut -d: -f1)"
        [[ "$backup_line" -lt "$migration_line" && "$migration_line" -lt "$switch_line" ]]
    else
        [[ "$result" != 0 ]]
        [[ "$(cat "$test_dir/state/current-release")" = previous ]]
        ! grep -q 'python -m alembic -c alembic.ini current' "$GATE_LOG"
        if [[ "$failure" != switch ]]; then
            ! grep -q ' up -d --no-build --wait ' "$GATE_LOG"
        fi
    fi
done

# 禁止显式关闭停写；应在任何 Docker 操作之前退出。
: > "$GATE_LOG"
if DEPLOY_STOP_BACKEND_FOR_MIGRATION=0 bash "$ROOT_DIR/deploy/deploy.sh" > "$test_dir/unsafe.log" 2>&1; then
    echo '错误：允许不停写迁移' >&2
    exit 1
fi
! grep -q ' stop backend\|pg_dump\|ruoyi db upgrade' "$GATE_LOG"
grep -q '不允许 DEPLOY_STOP_BACKEND_FOR_MIGRATION=0' "$test_dir/unsafe.log"
echo '发布门禁：默认停写及成功顺序、备份/迁移/预检/切换失败、禁止关闭停写六种情况通过'
