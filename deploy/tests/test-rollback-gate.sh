#!/usr/bin/env bash
# 使用假的 Docker 命令验证回滚控制流，不连接 Docker 或业务数据库。
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_dir="$(mktemp -d /tmp/sg-rollback-gate.XXXXXX)"
[[ "$test_dir" = /tmp/sg-rollback-gate.* ]] || exit 1
trap 'rm -rf -- "$test_dir"' EXIT
mkdir -p "$test_dir/bin" "$test_dir/state"
cat > "$test_dir/bin/docker" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GATE_LOG"
case "$*" in
    *'python -m alembic -c alembic.ini current'*) exit "$GATE_CHECK_EXIT" ;;
esac
exit 0
MOCK
chmod +x "$test_dir/bin/docker"
export PATH="$test_dir/bin:$PATH"
export RUOYI_ENV_FILE="$test_dir/env"
export RUOYI_DEPLOY_STATE_DIR="$test_dir/state"
export GATE_LOG="$test_dir/calls"
printf 'COMPOSE_PROJECT_NAME=sg-rollback-gate-test\n' > "$RUOYI_ENV_FILE"

# 持有与发布相同的锁时，必须在调用 Docker 或读取发布指针前拒绝回滚。
export GATE_CHECK_EXIT=0
: > "$GATE_LOG"
(
    exec 8>"$test_dir/state/deploy.lock"
    flock -n 8
    if bash "$ROOT_DIR/deploy/rollback.sh" previous > "$test_dir/locked.log" 2>&1; then
        echo '错误：持有发布锁时仍允许回滚' >&2
        exit 1
    fi
    grep -q '拒绝并发回滚' "$test_dir/locked.log"
    [[ ! -s "$GATE_LOG" ]]
)

# 手动回滚：失败时既不切换应用，也不改写发布指针。
export GATE_CHECK_EXIT=7
printf 'candidate\n' > "$test_dir/state/current-release"
: > "$GATE_LOG"
if bash "$ROOT_DIR/deploy/rollback.sh" previous > "$test_dir/manual-failed.log" 2>&1; then
    echo '错误：不兼容镜像被允许手动回滚' >&2
    exit 1
fi
grep -q 'python -m alembic -c alembic.ini current' "$GATE_LOG"
! grep -q ' up ' "$GATE_LOG"
[[ "$(cat "$test_dir/state/current-release")" = candidate ]]

export GATE_CHECK_EXIT=0
: > "$GATE_LOG"
bash "$ROOT_DIR/deploy/rollback.sh" previous > "$test_dir/manual-ok.log" 2>&1
grep -q ' up ' "$GATE_LOG"
[[ "$(cat "$test_dir/state/current-release")" = previous ]]

# 自动失败处理：执行正式脚本中的原函数，避免复制一份控制流作为测试对象。
awk '/^rollback_on_error\(\) \{/{copy=1} copy{print} copy && /^}/{exit}' \
    "$ROOT_DIR/deploy/deploy.sh" > "$test_dir/handler.sh"
for expected in 7 0; do
    export GATE_CHECK_EXIT="$expected"
    : > "$GATE_LOG"
    if bash -c '
        source "$1"
        COMPOSE=(docker compose)
        RELEASE_ID=candidate
        previous_release=previous
        migration_stop_started=0
        switch_started=1
        false
        rollback_on_error
    ' _ "$test_dir/handler.sh" > "$test_dir/automatic-$expected.log" 2>&1; then
        echo '错误：发布失败处理吞掉了失败退出码' >&2
        exit 1
    fi
    grep -q 'python -m alembic -c alembic.ini current' "$GATE_LOG"
    if [[ "$expected" = 7 ]]; then
        ! grep -q ' up ' "$GATE_LOG"
        grep -q ' stop backend' "$GATE_LOG"
    else
        grep -q ' up ' "$GATE_LOG"
    fi
done
echo '回滚预检控制流：并发锁及手动与自动、兼容与不兼容五种情况均通过'
