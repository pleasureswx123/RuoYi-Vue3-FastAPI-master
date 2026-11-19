[CmdletBinding()]
param(
    [string]$Server = 'root@192.168.10.122',
    [string]$RemotePath = '/opt/ruoyi-shot-grid',
    [string]$Branch = 'main',
    [string]$RemoteEnvFile = '/etc/ruoyi-shot-grid/production.env',
    [string]$RemoteStateDir = '/var/lib/ruoyi-shot-grid',
    [switch]$SkipBuild,
    [switch]$BuildOnly,
    [switch]$ForceBuild,
    [switch]$StopBackendForMigration = $true,
    [string]$DebianMirror = 'http://mirrors.cloud.tencent.com/debian',
    [string]$DebianSecurityMirror = 'http://mirrors.cloud.tencent.com/debian-security',
    [string]$PipIndexUrl = 'https://mirrors.aliyun.com/pypi/simple',
    [string]$NpmRegistry = 'https://registry.npmmirror.com'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'image-cache.ps1')
if ($SkipBuild -and $ForceBuild) { throw 'SkipBuild 与 ForceBuild 不能同时使用' }


if (-not $StopBackendForMigration.IsPresent) {
    throw '当前发布必须在备份与迁移期间停写，不允许关闭 StopBackendForMigration'
}

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

$requiredCommands = @('git', 'docker')
if (-not $BuildOnly) { $requiredCommands += @('ssh', 'scp', 'cmd.exe') }
foreach ($commandName in $requiredCommands) {
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

    Write-Host "[1/7] 创建提交 $releaseId 的干净构建目录"
    Invoke-NativeCommand -Command git -CommandArguments @(
        '-C', $repoRoot, 'worktree', 'add', '--detach', $buildRoot, $localHead
    )
    $worktreeCreated = $true

    Write-Host '[2/7] 按模块核对并准备镜像'
    # 按模块完整 Git 树及构建参数识别内容；文档等无关提交不再触发三个镜像重建。
    $modules = @(
        @{ Name = 'backend'; Directory = 'ruoyi-fastapi-backend'; Dockerfile = 'Dockerfile.prod'; Image = $backendImage;
           Arguments = @("DEBIAN_MIRROR=$DebianMirror", "DEBIAN_SECURITY_MIRROR=$DebianSecurityMirror", "PIP_INSTALL_INDEX_URL=$PipIndexUrl") },
        @{ Name = 'admin'; Directory = 'ruoyi-fastapi-frontend'; Dockerfile = 'Dockerfile.prod'; Image = $adminImage;
           Arguments = @("NPM_REGISTRY=$NpmRegistry") },
        @{ Name = 'business'; Directory = 'shot-grid-frontend'; Dockerfile = 'Dockerfile'; Image = $businessImage;
           Arguments = @("NPM_REGISTRY=$NpmRegistry") }
    )
    foreach ($module in $modules) {
        $tree = ((& git -C $repoRoot rev-parse "${localHead}:$($module.Directory)") -join "`n").Trim()
        if ($LASTEXITCODE -ne 0 -or $tree -notmatch '^[0-9a-f]{40}$') { throw '无法读取模块 Git 树' }
        $key = Get-BuildContentKey $module.Name $tree $module.Arguments
        Build-CachedImage -Image $module.Image -Key $key -Context (Join-Path $buildRoot $module.Directory) `
            -Dockerfile $module.Dockerfile -BuildArguments $module.Arguments -SkipBuild:$SkipBuild -ForceBuild:$ForceBuild `
            -UseLocalWebBases:($module.Name -eq 'business')
    }
    if ($BuildOnly) {
        Write-Host "本地镜像准备完成：$releaseId；未连接服务器，未部署。"
        return
    }

    Write-Host '[3/7] 核对服务器仓库和生产配置'
    $remoteProbe = @"
    set -Eeuo pipefail
    cd '$RemotePath'
    test -r '$RemoteEnvFile'
    test "`$(stat -c '%a' '$RemoteEnvFile')" = 600
    test -z "`$(git status --porcelain)"
    git rev-parse HEAD
"@
    # 远端 Bash 只接受 LF，避免 Windows 工作区 CRLF 破坏命令和路径。
    $remoteHead = ((& ssh -o BatchMode=yes $Server ($remoteProbe.Replace("`r", ""))) -join "`n").Trim()
    if ($LASTEXITCODE -ne 0 -or $remoteHead -notmatch '^[0-9a-f]{40}$') {
        throw '服务器仓库、生产环境文件或 SSH 核验失败。'
    }
    Invoke-NativeCommand -Command git -CommandArguments @(
        '-C', $repoRoot, 'merge-base', '--is-ancestor', $remoteHead, $localHead
    )

    Write-Host '[4/7] 生成服务器可快进的 Git 增量包'
    if ($remoteHead -ne $localHead) {
        Invoke-NativeCommand -Command git -CommandArguments @(
            '-C', $repoRoot, 'bundle', 'create', $bundleFile, $Branch, "^$remoteHead"
        )
        Invoke-NativeCommand -Command git -CommandArguments @(
            '-C', $repoRoot, 'bundle', 'verify', $bundleFile
        )
    }

    Write-Host '[5/7] 仅传输服务器缺少或内容不同的镜像'
    $transferImages = @()
    $imageChecks = @()
    foreach ($imageName in $images) {
        $localId = Get-LocalImageId $imageName
        $remoteId = ((& ssh -o BatchMode=yes $Server "docker image inspect --format '{{.Id}}' '$imageName' 2>/dev/null || true") -join "`n").Trim()
        if ($LASTEXITCODE -ne 0) { throw '远端镜像查询失败，停止发布' }
        if ($remoteId -ne $localId) {
            # 新版本标签可能尚未创建，但同一镜像 ID 已随旧版本传到服务器。
            $reuseById = @"
set -eu
if docker image inspect '$localId' >/dev/null 2>&1; then
    docker tag '$localId' '$imageName'
    docker image inspect --format '{{.Id}}' '$imageName'
fi
"@
            $remoteId = ((& ssh -o BatchMode=yes $Server ($reuseById.Replace("`r", ""))) -join "`n").Trim()
            if ($LASTEXITCODE -ne 0) { throw "服务器复用镜像失败：$imageName" }
        }
        if ($remoteId -eq $localId) { Write-Host "服务器已有相同镜像，跳过传输：$imageName" }
        else { $transferImages += $imageName }
        $imageChecks += "test `"`$(docker image inspect --format '{{.Id}}' '$imageName')`" = '$localId'"
    }
    if ($transferImages.Count -gt 0) {
        $layerTransferDone = $false
        if (Get-Command python -ErrorAction SilentlyContinue) {
            & python (Join-Path $PSScriptRoot 'transfer-image-layers.py') $Server $releaseRoot @transferImages
            $layerTransferDone = $LASTEXITCODE -eq 0
        }
        if (-not $layerTransferDone) {
            Write-Host '按层传输不可用，使用完整镜像包'
            $imageCommand = "docker save $($transferImages -join ' ') | ssh -o BatchMode=yes $Server docker load"
            & cmd.exe /d /s /c $imageCommand
            if ($LASTEXITCODE -ne 0) { throw "镜像传输失败，退出码：$LASTEXITCODE" }
        }
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
$($imageChecks -join "`n")
DEPLOY_SKIP_BUILD=1 \
DEPLOY_STOP_BACKEND_FOR_MIGRATION='$([int]$StopBackendForMigration.IsPresent)' \
RUOYI_ENV_FILE='$RemoteEnvFile' \
RUOYI_DEPLOY_STATE_DIR='$RemoteStateDir' \
SERVER_IP='192.168.10.122' \
bash deploy/deploy.sh
"@
    & ssh -o BatchMode=yes $Server ($remoteDeploy.Replace("`r", ""))
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
    & ssh -o BatchMode=yes $Server ($remoteVerify.Replace("`r", ""))
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
