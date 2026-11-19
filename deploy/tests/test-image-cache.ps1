# 使用命令替身执行快捷发布全流程，不访问服务器、真实 Docker 或数据库。
$ErrorActionPreference = 'Stop'
$deploymentScript = Join-Path $PSScriptRoot '../remote-deploy.ps1'
. (Join-Path $PSScriptRoot '../image-cache.ps1')
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('sg-cache-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $testRoot | Out-Null
$global:cacheTest = @{ Root=$testRoot; Images=@{}; Remote=@{}; Calls=[Collections.Generic.List[string]]::new(); Trees=@{backend=('a'*40); admin=('b'*40); business=('c'*40)}; FailBuild=$false }
function Assert($Condition, $Message) { if (-not $Condition) { throw $Message } }
function git {
    $global:LASTEXITCODE=0
    $s=$args -join ' '
    if ($s -match '--show-toplevel') { return $global:cacheTest.Root }
    if ($s -match '--short=12') { return '123456789abc' }
    if ($s -match 'worktree add') {
        $frontend = Join-Path $args[-2] 'shot-grid-frontend'
        New-Item -ItemType Directory -Force -Path $frontend | Out-Null
        Copy-Item (Join-Path $PSScriptRoot '../../shot-grid-frontend/Dockerfile') $frontend
        return
    }
    if ($s -match 'rev-parse') {
        foreach ($entry in @(@('ruoyi-fastapi-backend','backend'),@('ruoyi-fastapi-frontend','admin'),@('shot-grid-frontend','business'))) {
            if ($s.Contains(':'+$entry[0])) { return $global:cacheTest.Trees[$entry[1]] }
        }
        return '1'*40
    }
}
function docker {
    $global:LASTEXITCODE=0
    $s=$args -join ' '; $global:cacheTest.Calls.Add('docker '+$s)
    if ($s -eq 'buildx inspect') { return 'Driver: docker' }
    if ($s -match '^image inspect --platform linux/amd64 .* (\S+@sha256:[0-9a-f]{64})$') {
        if ($global:cacheTest.Images.ContainsKey($Matches[1])) { return 'linux/amd64' }
        $global:LASTEXITCODE=1; return
    }
    if ($s -match '^pull --platform linux/amd64 ') { $global:cacheTest.Images[$args[-1]]=@{}; return }
    if ($s -match '^image inspect') {
        $name=$args[-1]; $item=$global:cacheTest.Images[$name]
        if (-not $item) { $global:LASTEXITCODE=1; return }
        if ($s -match '--format') { return $item.Id }
        return ConvertTo-Json -Depth 5 -InputObject @($item)
    }
    if ($s -match '^image ls') {
        $key=($args[-1] -split '=')[-1]
        return @($global:cacheTest.Images.Values | Where-Object {$_.Config.Labels.'cn.shotgrid.build-key' -eq $key} | ForEach-Object {$_.Id})
    }
    if ($s -match '^tag') { $global:cacheTest.Images[$args[2]]=$global:cacheTest.Images[$args[1]]; return }
    if ($s -match '^build') {
        if ($global:cacheTest.FailBuild) { $global:LASTEXITCODE=1; return }
        $key=($args[[Array]::IndexOf($args,'--label')+1] -split '=')[-1]
        $name=$args[[Array]::IndexOf($args,'-t')+1]
        $item=@{Id=('sha256:'+$key);Os='linux';Architecture='amd64';Config=@{Labels=@{'cn.shotgrid.build-key'=$key}}}
        $global:cacheTest.Images[$name]=$item; $global:cacheTest.Images[$item.Id]=$item
        return
    }
    throw "未模拟的 Docker 调用：$s"
}
function ssh {
    $global:LASTEXITCODE=0
    $s=$args[-1]; $global:cacheTest.Calls.Add('ssh '+$s)
    if ($s -match "docker tag '(sha256:[0-9a-f]{64})' '([^']+)'") {
        $id=$Matches[1]; $name=$Matches[2]
        if ($global:cacheTest.Remote.ContainsValue($id)) {
            $global:cacheTest.Remote[$name]=$id
            return $id
        }
        return
    }
    if ($s -match '^docker image inspect.*\x27([^\x27]+)\x27') { return $global:cacheTest.Remote[$Matches[1]] }
    if ($s -match 'stat -c') { return '1'*40 }
    if ($s -match 'bash deploy/deploy.sh') {
        Assert ($s.Contains('DEPLOY_STOP_BACKEND_FOR_MIGRATION=''1''')) '停写门禁丢失'
        Assert ($s.Contains("test `"`$(docker image inspect")) '发布前镜像内容复核丢失'
    }
}
function scp { $global:LASTEXITCODE=0; $global:cacheTest.Calls.Add('scp') }
function cmd.exe { $global:LASTEXITCODE=0; $global:cacheTest.Calls.Add('transfer '+$args[-1]) }
function Count-Calls($Pattern) { return @($global:cacheTest.Calls | Where-Object {$_ -match $Pattern}).Count }
try {
    & $deploymentScript -BuildOnly
    Assert ((Count-Calls '^docker build ') -eq 3) '首次应构建三个模块'
    Assert ((Count-Calls '^docker pull --platform linux/amd64 .*@sha256:') -eq 2) '缺少网页基础镜像时应按摘要拉取'
    Assert ((Count-Calls '^docker build .*NODE_BASE=localhost/shot-grid-base/node:.*@sha256:.*NGINX_BASE=localhost/shot-grid-base/nginx:.*@sha256:') -eq 1) '制作平台必须使用同摘要的本地基础镜像'
    Assert ((Count-Calls '^ssh |^transfer |^scp') -eq 0) 'BuildOnly 不得连接服务器'
    $global:cacheTest.Calls.Clear()
    & $deploymentScript -BuildOnly
    Assert ((Count-Calls '^docker build ') -eq 0) '相同输入不应重复构建'
    $global:cacheTest.Images.Remove('ruoyi-shot-grid-admin-frontend:123456789abc')
    $global:cacheTest.Calls.Clear()
    & $deploymentScript -BuildOnly
    Assert ((Count-Calls '^docker tag ') -eq 1) '相同模块应跨版本复用并打标签'
    Assert ((Count-Calls '^docker build ') -eq 0) '跨版本复用不应重新构建'
    $global:cacheTest.Trees.business='d'*40
    $global:cacheTest.Calls.Clear()
    & $deploymentScript -BuildOnly
    Assert ((Count-Calls '^docker build ') -eq 1) '只修改制作端只能重建一个模块'
    Assert ((Count-Calls '^docker pull ') -eq 0) '只改页面时已有基础镜像不应重新拉取'
    $global:cacheTest.Calls.Clear()
    & $deploymentScript -BuildOnly -NpmRegistry 'https://example.invalid'
    Assert ((Count-Calls '^docker build ') -eq 2) 'npm 参数变化必须使两个前端缓存失效'
    $failed=$false
    try { & $deploymentScript -BuildOnly -SkipBuild } catch { $failed=$true }
    Assert $failed 'SkipBuild 必须拒绝错误内容的同名标签'
    & $deploymentScript -BuildOnly
    foreach ($name in @($global:cacheTest.Images.Keys | Where-Object {$_ -like 'ruoyi-*'})) { $global:cacheTest.Remote[$name]=$global:cacheTest.Images[$name].Id }
    $global:cacheTest.Calls.Clear()
    & $deploymentScript
    Assert ((Count-Calls '^transfer ') -eq 0) '远端已有相同镜像时不得传输'
    Assert ((Count-Calls 'bash deploy/deploy.sh') -eq 1) '镜像全命中仍必须执行备份迁移健康门禁'
    foreach ($module in 'backend','admin-frontend') {
        $name="ruoyi-shot-grid-${module}:123456789abc"
        $global:cacheTest.Remote["ruoyi-shot-grid-${module}:previous"]=$global:cacheTest.Remote[$name]
        $global:cacheTest.Remote.Remove($name)
    }
    $global:cacheTest.Remote.Remove('ruoyi-shot-grid-business-frontend:123456789abc')
    $global:cacheTest.Calls.Clear()
    & $deploymentScript
    Assert ((Count-Calls '^transfer .*docker save ruoyi-shot-grid-business-frontend:123456789abc \|') -eq 1) '只改网页时应复用旧标签下的后端和管理端，只传网页'
    $global:cacheTest.Remote['ruoyi-shot-grid-business-frontend:123456789abc']=$global:cacheTest.Images['ruoyi-shot-grid-business-frontend:123456789abc'].Id
    $global:cacheTest.Remote.Remove('ruoyi-shot-grid-backend:previous')
    $global:cacheTest.Remote['ruoyi-shot-grid-backend:123456789abc']='sha256:'+('0'*64)
    $global:cacheTest.Calls.Clear()
    & $deploymentScript
    $transfer=@($global:cacheTest.Calls | Where-Object {$_ -match '^transfer '})
    Assert ($transfer.Count -eq 1 -and $transfer[0] -notmatch 'admin-frontend|business-frontend') '只应传输不同内容的后端镜像'
    $global:cacheTest.FailBuild=$true; $global:cacheTest.Calls.Clear(); $failed=$false
    try { & $deploymentScript -ForceBuild } catch { $failed=$true }
    Assert ($failed -and (Count-Calls '^ssh |^transfer ') -eq 0) '构建失败不得进入远端发布'
    $failed=$false
    try { & $deploymentScript -StopBackendForMigration:$false } catch { $failed=$true }
    Assert $failed '不得允许关闭停写'
    Write-Host '通过：首次构建、重复复用、跨版本复用、模块及参数失效、严格跳过、只构建隔离、差异传输、保留发布门禁和失败关闭。'
}
finally {
    # 只清理本测试创建的唯一临时目录。
    if ((Split-Path $testRoot -Leaf) -match '^sg-cache-test-[0-9a-f]{32}$' -and (Split-Path $testRoot -Parent) -eq ([IO.Path]::GetTempPath()).TrimEnd('\','/')) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
    Remove-Variable cacheTest -Scope Global
}
