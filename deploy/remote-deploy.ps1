param(
    [string]$Server = 'root@192.168.10.122',
    [string]$RemotePath = '/opt/ruoyi-shot-grid',
    [string]$Branch = 'main',
    [string]$RemoteEnvFile = '/etc/ruoyi-shot-grid/production.env',
    [string]$RemoteStateDir = '/var/lib/ruoyi-shot-grid'
)

$ErrorActionPreference = 'Stop'

if ($RemotePath -notmatch '^/[0-9A-Za-z._/-]+$') {
    throw 'RemotePath 必须是只包含安全字符的 Linux 绝对路径。'
}
if ($RemoteEnvFile -notmatch '^/[0-9A-Za-z._/-]+$') {
    throw 'RemoteEnvFile 必须是只包含安全字符的 Linux 绝对路径。'
}
if ($RemoteStateDir -notmatch '^/[0-9A-Za-z._/-]+$') {
    throw 'RemoteStateDir 必须是只包含安全字符的 Linux 绝对路径。'
}
if ($Branch -notmatch '^[0-9A-Za-z._/-]+$') {
    throw 'Branch 格式非法。'
}

$remoteCommand = @"
set -Eeuo pipefail
cd '$RemotePath'
if [ -n "`$(git status --porcelain)" ]; then
  echo '服务器部署目录存在未提交改动，拒绝覆盖。' >&2
  exit 1
fi
git fetch origin '$Branch'
git checkout '$Branch'
git pull --ff-only origin '$Branch'
RUOYI_ENV_FILE='$RemoteEnvFile' \
RUOYI_DEPLOY_STATE_DIR='$RemoteStateDir' \
SERVER_IP='192.168.10.122' \
bash deploy/deploy.sh
"@

ssh $Server $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "远程部署失败，SSH 退出码：$LASTEXITCODE"
}
