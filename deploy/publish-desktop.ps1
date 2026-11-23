[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){2}$')][string]$Version,
    [Parameter(Mandatory)][ValidateLength(1,2000)][string]$Notes,
    [string]$Server = 'root@192.168.10.122',
    [switch]$BuildOnly,
    [switch]$UseBuiltInstaller
)
$ErrorActionPreference = 'Stop'
function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed ($LASTEXITCODE)" }
}
if ($Server -notmatch '^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$' -or $Server.StartsWith('-')) {
    throw 'SSH 目标格式无效'
}
foreach ($part in $Version.Split('.')) {
    if ([decimal]$part -gt 65535) { throw 'Windows 版本号每段最大为 65535' }
}
$desktop = (Resolve-Path "$PSScriptRoot/../shot-grid-frontend/src-tauri").Path
$secret = (Get-Content "$env:LOCALAPPDATA/ShotGridRelease/signing-key.dpapi" -Raw).Trim() | ConvertTo-SecureString
$rsa = New-Object Security.Cryptography.RSACryptoServiceProvider (New-Object Security.Cryptography.CspParameters 24)
$rsa.PersistKeyInCsp = $false
$stage = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$utf8 = New-Object Text.UTF8Encoding $false
New-Item -ItemType Directory $stage | Out-Null
Push-Location $desktop
try {
    $rsa.FromXmlString(([pscredential]::new('release',$secret)).GetNetworkCredential().Password)
    if ($rsa.ToXmlString($false) -cne [IO.File]::ReadAllText("$desktop/update-public-key.xml").Trim()) {
        throw '签名私钥与桌面端内置公钥不匹配'
    }
    $config = Join-Path $stage 'version.json'
    [IO.File]::WriteAllText($config, (@{version=$Version} | ConvertTo-Json -Compress), $utf8)
    $installer = "$desktop/target/release/bundle/nsis/Shot Grid_${Version}_x64-setup.exe"
    if (!$UseBuiltInstaller) {
        if (!(Test-Path '../node_modules/.bin/vite.cmd')) { Invoke-Checked npm.cmd @('--prefix','..','ci') }
        if (!(Test-Path './node_modules/.bin/tauri.cmd')) { Invoke-Checked npm.cmd @('ci') }
        Invoke-Checked './node_modules/.bin/tauri.cmd' @('build','--config',$config,'--','--locked')
    }
    if ([version]([Diagnostics.FileVersionInfo]::GetVersionInfo($installer).ProductVersion) -ne [version]$Version) {
        throw '安装包内置版本号与发布版本不符'
    }
    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash
    $payload = $utf8.GetBytes(([ordered]@{version=$Version; notes=$Notes; sha256=$digest} | ConvertTo-Json -Compress))
    $signed = [ordered]@{
        payload = [Convert]::ToBase64String($payload)
        signature = [Convert]::ToBase64String($rsa.SignData($payload, 'SHA256'))
    } | ConvertTo-Json -Compress
    $manifest = "$stage/latest.json"
    [IO.File]::WriteAllText($manifest, $signed, $utf8)
    if ($BuildOnly) {
        Copy-Item $manifest "$installer.manifest.json" -Force
        Write-Output $installer
        return
    }
    $remote = '/tmp/shotgrid-release-' + [Guid]::NewGuid().ToString('N')
    Invoke-Checked ssh @($Server,"mkdir -m 700 $remote")
    try {
        Invoke-Checked scp @($installer,"${Server}:$remote/ShotGrid-setup.exe")
        Invoke-Checked scp @($manifest,"$PSScriptRoot/install-desktop-release.py","${Server}:$remote/")
        Invoke-Checked ssh @($Server,"python3 $remote/install-desktop-release.py $remote $Version $digest")
    } finally {
        Invoke-Checked ssh @($Server,"rm -f $remote/latest.json $remote/ShotGrid-setup.exe $remote/install-desktop-release.py && rmdir $remote")
    }
} finally {
    Pop-Location
    $rsa.Dispose()
    foreach ($file in @('version.json','latest.json')) {
        $temporaryFile = Join-Path $stage $file
        if (Test-Path -LiteralPath $temporaryFile) { Remove-Item -LiteralPath $temporaryFile }
    }
    Remove-Item -LiteralPath $stage
}
