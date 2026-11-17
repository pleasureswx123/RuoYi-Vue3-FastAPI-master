# 本地镜像复用只信任构建输入标签，不以版本标签存在作为内容正确的证明。
function Get-BuildContentKey {
    param([string]$Name, [string]$Tree, [string[]]$BuildArguments)
    $inputText = (@('v1', 'linux/amd64', $Name, $Tree) + $BuildArguments) -join "`n"
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($inputText)))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-LocalImageId {
    param([string]$Image)
    $id = ((& docker image inspect --format '{{.Id}}' $Image) -join "`n").Trim()
    if ($LASTEXITCODE -ne 0 -or $id -notmatch '^sha256:[0-9a-f]{64}$') { throw "无法校验镜像内容：$Image" }
    return $id
}

function Build-CachedImage {
    param([string]$Image, [string]$Key, [string]$Context, [string]$Dockerfile,
          [string[]]$BuildArguments, [switch]$SkipBuild, [switch]$ForceBuild)
    $label = 'cn.shotgrid.build-key'
    $metadata = (& docker image inspect $Image 2>$null) -join "`n"
    $valid = $false
    if ($LASTEXITCODE -eq 0) {
        $info = @($metadata | ConvertFrom-Json)[0]
        $valid = $info.Config.Labels.$label -eq $Key -and $info.Os -eq 'linux' -and $info.Architecture -eq 'amd64'
    }
    if ($SkipBuild) {
        if (-not $valid) { throw "预载镜像缺失或构建输入不匹配：$Image；请先正常构建，不能跳过。" }
        Write-Host "已核对预载镜像：$Image"
        return
    }
    if (-not $ForceBuild) {
        if ($valid) { Write-Host "复用当前版本镜像：$Image"; return }
        $candidates = @(& docker image ls --no-trunc --quiet --filter "label=$label=$Key")
        if ($LASTEXITCODE -ne 0) { throw '查询本地镜像缓存失败' }
        foreach ($candidate in ($candidates | Select-Object -Unique)) {
            if ($candidate -notmatch '^sha256:[0-9a-f]{64}$') { continue }
            $info = @(((& docker image inspect $candidate) -join "`n") | ConvertFrom-Json)[0]
            if ($LASTEXITCODE -ne 0) { throw '读取缓存镜像失败' }
            if ($info.Config.Labels.$label -eq $Key -and $info.Os -eq 'linux' -and $info.Architecture -eq 'amd64') {
                Invoke-NativeCommand docker @('tag', $candidate, $Image)
                Write-Host "模块内容未变，复用已有镜像：$Image"
                return
            }
        }
    }
    Write-Host "构建模块镜像（保留 Docker 层和下载缓存）：$Image"
    $arguments = @('build', '--platform', 'linux/amd64', '--label', "$label=$Key")
    foreach ($value in $BuildArguments) { $arguments += @('--build-arg', $value) }
    $arguments += @('-f', (Join-Path $Context $Dockerfile), '-t', $Image, $Context)
    Invoke-NativeCommand docker $arguments
    $null = Get-LocalImageId $Image
}
