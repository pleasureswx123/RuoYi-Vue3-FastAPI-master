[CmdletBinding()]
param(
    [string]$Server = 'root@192.168.10.122',
    [string]$RemotePath = '/opt/ruoyi-shot-grid',
    [string]$Branch = 'main',
    [string]$RemoteEnvFile = '/etc/ruoyi-shot-grid/production.env',
    [string]$RemoteStateDir = '/var/lib/ruoyi-shot-grid',
    [switch]$SkipBuild,
    [string]$DebianMirror = 'http://mirrors.cloud.tencent.com/debian',
    [string]$DebianSecurityMirror = 'http://mirrors.cloud.tencent.com/debian-security',
    [string]$PipIndexUrl = 'https://mirrors.aliyun.com/pypi/simple',
    [string]$NpmRegistry = 'https://registry.npmmirror.com'
)

$ErrorActionPreference = 'Stop'

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Command,
        [string[]]$CommandArguments = @()
    )

    & $Command @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command 执行失败，退出码：$LASTEXITCODE"
    }
}

foreach ($commandName in @('git', 'docker', 'ssh', 'scp', 'cmd.exe')) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "缺少本地命令：$commandName"
    }
}
if ($Server -notmatch '^[0-9A-Za-z._-]+@[0-9A-Za-z._-]+$') {
    throw 'Server 格式非法，应类似 root@192.168.10.122。'
}
foreach ($remoteValue in @($RemotePath, $RemoteEnvFile, $RemoteStateDir)) {
    if ($remoteValue -notmatch '^/[0-9A-Za-z._/-]+$') {
        throw "远程路径格式非法：$remoteValue"
    }
}
if ($Branch -notmatch '^[0-9A-Za-z._/-]+$') {
    throw 'Branch 格式非法。'
}

$repoRoot = ((& git rev-parse --show-toplevel) -join "`n").Trim()
if ($LASTEXITCODE -ne 0 -or -not $repoRoot) {
    throw '当前目录不在 Git 仓库中。'
}
$repoRoot = [System.IO.Path]::GetFullPath($repoRoot)
$localHead = ((& git -C $repoRoot rev-parse "$Branch`^{commit}") -join "`n").Trim()
if ($LASTEXITCODE -ne 0 -or $localHead -notmatch '^[0-9a-f]{40}$') {
    throw "无法解析分支：$Branch"
}
$releaseId = ((& git -C $repoRoot rev-parse --short=12 $localHead) -join "`n").Trim()
$currentHead = ((& git -C $repoRoot rev-parse HEAD) -join "`n").Trim()
if ($currentHead -ne $localHead) {
    throw "当前 HEAD 不是 $Branch 的最新提交，请先切换分支并提交代码。"
}

$dirtyCount = @(& git -C $repoRoot status --porcelain).Count
if ($dirtyCount -gt 0) {
    Write-Warning "工作区有 $dirtyCount 项未提交内容；本次只部署已提交的 $releaseId，不会包含这些内容。"
}

Write-Host '[1/7] 核对服务器仓库和生产配置'
$remoteProbe = @"
set -Eeuo pipefail
cd '$RemotePath'
test -r '$RemoteEnvFile'
test "`$(stat -c '%a' '$RemoteEnvFile')" = 600
test -z "`$(git status --porcelain)"
git rev-parse HEAD
"@
$remoteHead = ((& ssh -o BatchMode=yes $Server $remoteProbe) -join "`n").Trim()
if ($LASTEXITCODE -ne 0 -or $remoteHead -notmatch '^[0-9a-f]{40}$') {
    throw '服务器仓库、生产环境文件或 SSH 核验失败。'
}
Invoke-NativeCommand -Command git -CommandArguments @(
    '-C', $repoRoot, 'merge-base', '--is-ancestor', $remoteHead, $localHead
)

$deployRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot '.deploy'))
$releaseRoot = [System.IO.Path]::GetFullPath((Join-Path $deployRoot "release-$releaseId-$PID"))
$requiredPrefix = $deployRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $releaseRoot.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "临时发布目录越界：$releaseRoot"
}
$buildRoot = Join-Path $releaseRoot 'worktree'
$bundleFile = Join-Path $releaseRoot "release-$releaseId.bundle"
$remoteBundle = "/tmp/ruoyi-release-$releaseId.bundle"
$worktreeCreated = $false

$backendImage = "ruoyi-shot-grid-backend:$releaseId"
$adminImage = "ruoyi-shot-grid-admin-frontend:$releaseId"
$businessImage = "ruoyi-shot-grid-business-frontend:$releaseId"
$images = @($backendImage, $adminImage, $businessImage)

try {
    New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

    Write-Host "[2/7] 创建提交 $releaseId 的干净构建目录"
    Invoke-NativeCommand -Command git -CommandArguments @(
        '-C', $repoRoot, 'worktree', 'add', '--detach', $buildRoot, $localHead
    )
    $worktreeCreated = $true

    if (-not $SkipBuild) {
        Write-Host '[3/7] 构建三个生产镜像（首次执行时间较长）'
        Invoke-NativeCommand -Command docker -CommandArguments @(
            'build', '--build-arg', "DEBIAN_MIRROR=$DebianMirror",
            '--build-arg', "DEBIAN_SECURITY_MIRROR=$DebianSecurityMirror",
            '--build-arg', "PIP_INSTALL_INDEX_URL=$PipIndexUrl",
            '-f', (Join-Path $buildRoot 'ruoyi-fastapi-backend/Dockerfile.prod'),
            '-t', $backendImage,
            (Join-Path $buildRoot 'ruoyi-fastapi-backend')
        )
        Invoke-NativeCommand -Command docker -CommandArguments @(
            'build', '--build-arg', "NPM_REGISTRY=$NpmRegistry",
            '-f', (Join-Path $buildRoot 'ruoyi-fastapi-frontend/Dockerfile.prod'),
            '-t', $adminImage,
            (Join-Path $buildRoot 'ruoyi-fastapi-frontend')
        )
        Invoke-NativeCommand -Command docker -CommandArguments @(
            'build', '--build-arg', "NPM_REGISTRY=$NpmRegistry",
            '-f', (Join-Path $buildRoot 'shot-grid-frontend/Dockerfile'),
            '-t', $businessImage,
            (Join-Path $buildRoot 'shot-grid-frontend')
        )
    }
    else {
        Write-Host '[3/7] 跳过构建，核对本地预载镜像'
        foreach ($imageName in $images) {
            Invoke-NativeCommand -Command docker -CommandArguments @('image', 'inspect', $imageName)
        }
    }

    Write-Host '[4/7] 生成服务器可快进的 Git 增量包'
    if ($remoteHead -ne $localHead) {
        Invoke-NativeCommand -Command git -CommandArguments @(
            '-C', $repoRoot, 'bundle', 'create', $bundleFile, $Branch, "^$remoteHead"
        )
        Invoke-NativeCommand -Command git -CommandArguments @(
            '-C', $repoRoot, 'bundle', 'verify', $bundleFile
        )
    }

    Write-Host '[5/7] 离线传输三个镜像（不会访问服务器外网）'
    $imageCommand = "docker save $($images -join ' ') | ssh -o BatchMode=yes $Server docker load"
    & cmd.exe /d /s /c $imageCommand
    if ($LASTEXITCODE -ne 0) {
        throw "镜像传输失败，退出码：$LASTEXITCODE"
    }

    if ($remoteHead -ne $localHead) {
        Invoke-NativeCommand -Command scp -CommandArguments @('-q', $bundleFile, "${Server}:$remoteBundle")
    }

    Write-Host '[6/7] 在服务器执行备份、迁移、预检和健康切换'
    $bundleApply = if ($remoteHead -ne $localHead) {
        "git fetch '$remoteBundle' '$Branch' && git merge --ff-only FETCH_HEAD"
    }
    else {
        'test "$(git rev-parse HEAD)" = ' + "'$localHead'"
    }
    $remoteDeploy = @"
set -Eeuo pipefail
trap 'rm -f "$remoteBundle"' EXIT
cd '$RemotePath'
$bundleApply
test "`$(git rev-parse HEAD)" = '$localHead'
for image_name in '$backendImage' '$adminImage' '$businessImage'; do
  docker image inspect "`$image_name" >/dev/null
done
DEPLOY_SKIP_BUILD=1 \
RUOYI_ENV_FILE='$RemoteEnvFile' \
RUOYI_DEPLOY_STATE_DIR='$RemoteStateDir' \
SERVER_IP='192.168.10.122' \
bash deploy/deploy.sh
"@
    & ssh -o BatchMode=yes $Server $remoteDeploy
    if ($LASTEXITCODE -ne 0) {
        throw "服务器发布失败，SSH 退出码：$LASTEXITCODE"
    }

    Write-Host '[7/7] 复核服务器发布版本'
    $remoteVerify = @"
set -Eeuo pipefail
test "`$(tr -d '\r\n' < '$RemoteStateDir/current-release')" = '$releaseId'
cd '$RemotePath'
test "`$(git rev-parse HEAD)" = '$localHead'
RUOYI_ENV_FILE='$RemoteEnvFile' RUOYI_DEPLOY_STATE_DIR='$RemoteStateDir' SERVER_IP='192.168.10.122' bash deploy/status.sh
"@
    & ssh -o BatchMode=yes $Server $remoteVerify
    if ($LASTEXITCODE -ne 0) {
        throw "发布后复核失败，SSH 退出码：$LASTEXITCODE"
    }

    Write-Host "发布完成：$releaseId"
    Write-Host '管理端：http://192.168.10.122:12580/'
    Write-Host 'Shot Grid：http://192.168.10.122:12581/shot-grid-app/'
}
finally {
    if ($worktreeCreated) {
        & git -C $repoRoot worktree remove --force $buildRoot | Out-Null
    }
    & git -C $repoRoot worktree prune | Out-Null
    if (Test-Path -LiteralPath $releaseRoot) {
        $resolvedReleaseRoot = [System.IO.Path]::GetFullPath($releaseRoot)
        if ($resolvedReleaseRoot.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedReleaseRoot -Recurse -Force
        }
    }
}
