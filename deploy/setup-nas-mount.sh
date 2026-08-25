#!/usr/bin/env bash
set -Eeuo pipefail

NAS_SERVER="${NAS_SERVER:-192.168.10.64}"
NAS_SHARE="${NAS_SHARE:-web}"
NAS_PREFIX_PATH="${NAS_PREFIX_PATH:-ShotGridProd}"
NAS_MOUNT_PATH="${NAS_MOUNT_PATH:-/mnt/ruoyi-shot-grid/shotgrid-main}"
NAS_CREDENTIAL_FILE="${NAS_CREDENTIAL_FILE:-/etc/ruoyi-shot-grid/nas-credentials}"
BACKEND_APP_UID="${BACKEND_APP_UID:-100}"
BACKEND_APP_GID="${BACKEND_APP_GID:-101}"
FSTAB_FILE='/etc/fstab'
FSTAB_BEGIN='# BEGIN ruoyi-shot-grid NAS mount'
FSTAB_END='# END ruoyi-shot-grid NAS mount'

fail() {
    echo "NAS 挂载配置失败：$*" >&2
    exit 1
}

[[ "$(id -u)" = 0 ]] || fail '请使用 root 执行本脚本'
for command_name in bash cat cp findmnt grep install ln mktemp mount mount.cifs openssl rm sed setpriv systemctl umount; do
    command -v "$command_name" >/dev/null 2>&1 || fail "缺少命令 $command_name"
done

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

[[ "$BACKEND_APP_UID" =~ ^[0-9]+$ && "$BACKEND_APP_UID" -gt 0 ]] \
    || fail 'BACKEND_APP_UID 必须是正整数'
[[ "$BACKEND_APP_GID" =~ ^[0-9]+$ && "$BACKEND_APP_GID" -gt 0 ]] \
    || fail 'BACKEND_APP_GID 必须是正整数'

umask 077
install -d -m 0700 "$(dirname "$NAS_CREDENTIAL_FILE")"
credential_tmp="$(mktemp "$(dirname "$NAS_CREDENTIAL_FILE")/.nas-credentials.XXXXXX")"
fstab_tmp="$(mktemp /etc/.fstab.ruoyi-shot-grid.XXXXXX)"
probe_file=''
probe_link=''

cleanup() {
    [[ -z "$probe_link" || ! -e "$probe_link" ]] || rm -f -- "$probe_link"
    [[ -z "$probe_file" || ! -e "$probe_file" ]] || rm -f -- "$probe_file"
    rm -f -- "$credential_tmp" "$fstab_tmp"
    unset NAS_PASSWORD
}
trap cleanup EXIT

{
    printf 'username=%s\n' "$NAS_USERNAME"
    printf 'password=%s\n' "$NAS_PASSWORD"
    [[ -z "$NAS_DOMAIN" ]] || printf 'domain=%s\n' "$NAS_DOMAIN"
} > "$credential_tmp"
chmod 600 "$credential_tmp"
install -m 0600 "$credential_tmp" "$NAS_CREDENTIAL_FILE"
grep -Fqx "username=$NAS_USERNAME" "$NAS_CREDENTIAL_FILE" \
    || fail '凭据文件中的 NAS 用户名与本次输入不一致'

install -d -m 0750 "$NAS_MOUNT_PATH"
if findmnt -rn -T "$NAS_MOUNT_PATH" -o FSTYPE | grep -Eq '^(cifs|smb3)$'; then
    umount "$NAS_MOUNT_PATH"
elif findmnt -rn -T "$NAS_MOUNT_PATH" -o TARGET | grep -Fxq "$NAS_MOUNT_PATH"; then
    fail "$NAS_MOUNT_PATH 已被其他文件系统占用"
fi

sed "/^${FSTAB_BEGIN//\//\\/}$/,/^${FSTAB_END//\//\\/}$/d" "$FSTAB_FILE" > "$fstab_tmp"
{
    cat "$fstab_tmp"
    printf '%s\n' "$FSTAB_BEGIN"
    printf '//%s/%s %s cifs credentials=%s,prefixpath=%s,vers=3.0,iocharset=utf8,rw,nosuid,nodev,noexec,_netdev,nofail,x-systemd.automount,uid=%s,gid=%s,forceuid,forcegid,file_mode=0660,dir_mode=0770 0 0\n' \
        "$NAS_SERVER" "$NAS_SHARE" "$NAS_MOUNT_PATH" "$NAS_CREDENTIAL_FILE" "$NAS_PREFIX_PATH" \
        "$BACKEND_APP_UID" "$BACKEND_APP_GID"
    printf '%s\n' "$FSTAB_END"
} > "${fstab_tmp}.new"
cp -a "$FSTAB_FILE" "${FSTAB_FILE}.before-ruoyi-shot-grid"
install -m 0644 "${fstab_tmp}.new" "$FSTAB_FILE"
rm -f -- "${fstab_tmp}.new"

systemctl daemon-reload
mount "$NAS_MOUNT_PATH"
filesystem_type="$(findmnt -rn -T "$NAS_MOUNT_PATH" -o FSTYPE)"
[[ "$filesystem_type" = cifs || "$filesystem_type" = smb3 ]] || fail '挂载结果不是 cifs/smb3'

probe_file="$NAS_MOUNT_PATH/.shotgrid-deploy-probe-$(openssl rand -hex 12).tmp"
probe_link="${probe_file}.link"
probe_payload="$(openssl rand -hex 32)"
run_as_backend() {
    setpriv --reuid="$BACKEND_APP_UID" --regid="$BACKEND_APP_GID" --clear-groups -- "$@"
}
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
echo "NAS 挂载及应用身份（UID $BACKEND_APP_UID / GID $BACKEND_APP_GID）读写删除、硬链接验证成功：//$NAS_SERVER/$NAS_SHARE/$NAS_PREFIX_PATH → $NAS_MOUNT_PATH"
