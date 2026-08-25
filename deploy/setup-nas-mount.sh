#!/usr/bin/env bash
set -Eeuo pipefail

NAS_SERVER="${NAS_SERVER:-192.168.10.64}"
NAS_DYNAMIC_MOUNT_ROOT="${NAS_DYNAMIC_MOUNT_ROOT:-/mnt/ruoyi-shot-grid/dynamic}"
NAS_PROBE_SHARE="${NAS_PROBE_SHARE:-web}"
NAS_PROBE_RELATIVE_PATH="${NAS_PROBE_RELATIVE_PATH:-ShotGridProd}"
NAS_CREDENTIAL_FILE="${NAS_CREDENTIAL_FILE:-/etc/ruoyi-shot-grid/nas-credentials}"
BACKEND_APP_UID="${BACKEND_APP_UID:-100}"
BACKEND_APP_GID="${BACKEND_APP_GID:-101}"
AUTOFS_MASTER_FILE="${AUTOFS_MASTER_FILE:-/etc/auto.master.d/ruoyi-shot-grid.autofs}"
AUTOFS_MAP_FILE="${AUTOFS_MAP_FILE:-/etc/auto.ruoyi-shot-grid}"

fail() {
    echo "NAS 动态挂载配置失败：$*" >&2
    exit 1
}

[[ "$(id -u)" = 0 ]] || fail '请使用 root 执行本脚本'
for command_name in automount bash cat findmnt grep install ln mktemp mount mount.cifs openssl rm setpriv stat systemctl; do
    command -v "$command_name" >/dev/null 2>&1 || fail "缺少命令 $command_name；Ubuntu 请先安装 autofs 和 cifs-utils"
done

[[ "$NAS_SERVER" =~ ^[0-9A-Za-z.-]+$ && "$NAS_SERVER" != '.' && "$NAS_SERVER" != '..' ]] \
    || fail 'NAS_SERVER 只能是不含路径和端口的主机名或 IPv4 地址'
[[ "$NAS_DYNAMIC_MOUNT_ROOT" = /* && "$NAS_DYNAMIC_MOUNT_ROOT" != *$'\r'* && "$NAS_DYNAMIC_MOUNT_ROOT" != *$'\n'* ]] \
    || fail 'NAS_DYNAMIC_MOUNT_ROOT 必须是无换行的绝对路径'
[[ -n "$NAS_PROBE_SHARE" && "$NAS_PROBE_SHARE" != *'/'* && "$NAS_PROBE_SHARE" != *'\'* ]] \
    || fail 'NAS_PROBE_SHARE 必须是单个共享名'
[[ -n "$NAS_PROBE_RELATIVE_PATH" && "$NAS_PROBE_RELATIVE_PATH" != /* ]] \
    || fail 'NAS_PROBE_RELATIVE_PATH 必须是共享内的相对路径'
case "/$NAS_PROBE_RELATIVE_PATH/" in
    */../*|*/./*) fail 'NAS_PROBE_RELATIVE_PATH 不能包含 . 或 .. 路径段' ;;
esac
[[ "$BACKEND_APP_UID" =~ ^[0-9]+$ && "$BACKEND_APP_UID" -gt 0 ]] \
    || fail 'BACKEND_APP_UID 必须是正整数'
[[ "$BACKEND_APP_GID" =~ ^[0-9]+$ && "$BACKEND_APP_GID" -gt 0 ]] \
    || fail 'BACKEND_APP_GID 必须是正整数'
for protected_path in "$NAS_CREDENTIAL_FILE" "$AUTOFS_MASTER_FILE" "$AUTOFS_MAP_FILE"; do
    [[ "$protected_path" = /* && "$protected_path" != *','* && "$protected_path" != *$'\r'* && "$protected_path" != *$'\n'* ]] \
        || fail "配置路径必须是不含逗号和换行的绝对路径：$protected_path"
done

umask 077
install -d -m 0700 "$(dirname "$NAS_CREDENTIAL_FILE")"
install -d -m 0755 "$(dirname "$AUTOFS_MASTER_FILE")"

credential_tmp=''
master_tmp="$(mktemp "$(dirname "$AUTOFS_MASTER_FILE")/.ruoyi-shot-grid-autofs.XXXXXX")"
map_tmp="$(mktemp "$(dirname "$AUTOFS_MAP_FILE")/.ruoyi-shot-grid-map.XXXXXX")"
probe_file=''
probe_link=''

cleanup() {
    [[ -z "$probe_link" || ! -e "$probe_link" ]] || rm -f -- "$probe_link"
    [[ -z "$probe_file" || ! -e "$probe_file" ]] || rm -f -- "$probe_file"
    [[ -z "$credential_tmp" ]] || rm -f -- "$credential_tmp"
    rm -f -- "$master_tmp" "$map_tmp"
    unset NAS_PASSWORD
}
trap cleanup EXIT

if [[ -r "$NAS_CREDENTIAL_FILE" && -z "${NAS_USERNAME+x}" && -z "${NAS_PASSWORD+x}" ]]; then
    [[ "$(stat -c '%a' "$NAS_CREDENTIAL_FILE")" = 600 ]] \
        || fail "现有 NAS 凭据文件权限必须是 600：$NAS_CREDENTIAL_FILE"
    echo "复用现有受保护 NAS 凭据文件：$NAS_CREDENTIAL_FILE"
else
    if [[ -z "${NAS_USERNAME:-}" ]]; then
        read -r -p 'NAS 用户名：' NAS_USERNAME
    fi
    [[ -n "$NAS_USERNAME" ]] || fail 'NAS 用户名不能为空'
    [[ "$NAS_USERNAME" != *$'\r'* && "$NAS_USERNAME" != *$'\n'* ]] || fail 'NAS 用户名不能包含换行符'
    printf '将使用 NAS 用户名：%s\n' "$NAS_USERNAME"

    if [[ -z "${NAS_PASSWORD:-}" ]]; then
        read -r -s -p 'NAS 密码（不会显示）：' NAS_PASSWORD
        echo
    fi
    [[ -n "$NAS_PASSWORD" ]] || fail 'NAS 密码不能为空'
    if [[ -z "${NAS_DOMAIN+x}" ]]; then
        read -r -p 'NAS 域/工作组（没有可直接回车）：' NAS_DOMAIN
    fi

    credential_tmp="$(mktemp "$(dirname "$NAS_CREDENTIAL_FILE")/.nas-credentials.XXXXXX")"
    {
        printf 'username=%s\n' "$NAS_USERNAME"
        printf 'password=%s\n' "$NAS_PASSWORD"
        [[ -z "$NAS_DOMAIN" ]] || printf 'domain=%s\n' "$NAS_DOMAIN"
    } > "$credential_tmp"
    chmod 600 "$credential_tmp"
    install -m 0600 "$credential_tmp" "$NAS_CREDENTIAL_FILE"
    grep -Fqx "username=$NAS_USERNAME" "$NAS_CREDENTIAL_FILE" \
        || fail '凭据文件中的 NAS 用户名与本次输入不一致'
fi

install -d -m 0755 "$NAS_DYNAMIC_MOUNT_ROOT"
printf '%s %s --timeout=300\n' "$NAS_DYNAMIC_MOUNT_ROOT" "$AUTOFS_MAP_FILE" > "$master_tmp"
printf '* -fstype=cifs,credentials=%s,vers=3.0,iocharset=utf8,rw,nosuid,nodev,noexec,uid=%s,gid=%s,forceuid,forcegid,file_mode=0660,dir_mode=0770 ://%s/&\n' \
    "$NAS_CREDENTIAL_FILE" "$BACKEND_APP_UID" "$BACKEND_APP_GID" "$NAS_SERVER" > "$map_tmp"
install -m 0644 "$master_tmp" "$AUTOFS_MASTER_FILE"
install -m 0600 "$map_tmp" "$AUTOFS_MAP_FILE"

automount -m >/dev/null
systemctl enable --now autofs
systemctl restart autofs
findmnt -rn -T "$NAS_DYNAMIC_MOUNT_ROOT" -o FSTYPE | grep -Fxq autofs \
    || fail "动态挂载根不是 autofs：$NAS_DYNAMIC_MOUNT_ROOT"
mount --make-rshared "$NAS_DYNAMIC_MOUNT_ROOT"
propagation="$(findmnt -rn -T "$NAS_DYNAMIC_MOUNT_ROOT" -o PROPAGATION)"
[[ "$propagation" = shared || "$propagation" = rshared ]] \
    || fail "动态挂载根没有共享子挂载传播：$NAS_DYNAMIC_MOUNT_ROOT"

probe_root="$NAS_DYNAMIC_MOUNT_ROOT/$NAS_PROBE_SHARE"
probe_path="$probe_root/$NAS_PROBE_RELATIVE_PATH"
run_as_backend() {
    setpriv --reuid="$BACKEND_APP_UID" --regid="$BACKEND_APP_GID" --clear-groups -- "$@"
}
run_as_backend test -d "$probe_path" \
    || fail "NAS 探测目录不存在或应用身份不可访问：//$NAS_SERVER/$NAS_PROBE_SHARE/$NAS_PROBE_RELATIVE_PATH"
filesystem_type="$(findmnt -rn -T "$probe_path" -o FSTYPE)"
[[ "$filesystem_type" = cifs || "$filesystem_type" = smb3 ]] || fail '动态共享挂载结果不是 cifs/smb3'

probe_file="$probe_path/.shotgrid-deploy-probe-$(openssl rand -hex 12).tmp"
probe_link="${probe_file}.link"
probe_payload="$(openssl rand -hex 32)"
run_as_backend bash -c 'set -o noclobber; printf "%s" "$1" > "$2"' \
    _ "$probe_payload" "$probe_file"
[[ "$(run_as_backend cat -- "$probe_file")" = "$probe_payload" ]] || fail 'NAS 临时文件回读不一致'
run_as_backend ln -- "$probe_file" "$probe_link"
[[ "$probe_file" -ef "$probe_link" ]] || fail 'NAS 硬链接校验失败，版本文件无法安全发布'
run_as_backend rm -f -- "$probe_link" "$probe_file"
[[ ! -e "$probe_link" && ! -e "$probe_file" ]] || fail '后端应用身份无法删除 NAS 临时文件'
probe_file=''
probe_link=''

unset NAS_PASSWORD
echo "NAS 动态共享挂载成功：\\\\$NAS_SERVER\\<共享> → $NAS_DYNAMIC_MOUNT_ROOT/<共享>"
echo "应用身份（UID $BACKEND_APP_UID / GID $BACKEND_APP_GID）已通过读写删除和硬链接验证：\\\\$NAS_SERVER\\$NAS_PROBE_SHARE\\$NAS_PROBE_RELATIVE_PATH"
