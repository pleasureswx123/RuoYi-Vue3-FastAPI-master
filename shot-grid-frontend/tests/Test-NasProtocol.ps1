# 仅验证编译和纯函数，不注册协议、不访问 NAS、不弹窗或启动资源管理器。
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../public/tools/Install-ShotGridNas.ps1') -ValidateOnly
$folder = '\\192.168.10.64\共享\项目 A\V001'
if ([ShotGridNas]::ValidateFolder($folder) -cne $folder) { throw '合法路径未保持原样' }
$rsa = New-Object Security.Cryptography.RSACryptoServiceProvider 2048
$rsa.PersistKeyInCsp = $false
$key = $rsa.ToXmlString($false)
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
function New-Ticket($path, $issued = $now, $expires = ($now + 60), $audience = 'SGNAS1') {
    $data = [Text.Encoding]::UTF8.GetBytes("$audience`n$issued`n$expires`n$([Guid]::NewGuid().ToString('N'))`n$path")
    $sig = $rsa.SignData($data, [Security.Cryptography.CryptoConfig]::MapNameToOID('SHA256'))
    $body = [Convert]::ToBase64String($data).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    $signature = [Convert]::ToBase64String($sig).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    return 'shotgrid-nas://open-v1/' + $body + '.' + $signature
}
$ticket = New-Ticket $folder
if ([ShotGridNas]::Verify($ticket, $key, $now) -cne $folder) { throw '签名中文目录往返失败' }
$cache = Join-Path ([IO.Path]::GetTempPath()) ('sgnas-test-' + [Guid]::NewGuid().ToString('N'))
[ShotGridNas]::Consume($ticket, $cache)
$rejected = $false
try { [ShotGridNas]::Consume($ticket, $cache) } catch { $rejected = $true }
if (!$rejected) { throw '重放未拒绝' }
# 仅清理本测试创建的一个文件及空目录。
Get-ChildItem -LiteralPath $cache -File | Remove-Item
Remove-Item -LiteralPath $cache
$badPaths = @('C:\Windows', '\\evil\share\folder', '\\192.168.10.640\share\folder', '\\?\UNC\192.168.10.64\share\folder', '\\192.168.10.64\C$\Windows', '\\192.168.10.64\share', ($folder + '\..'), ($folder + '\.'), ($folder + '\bad '), ($folder + '\x:stream'), ($folder + '\x" /select'), ($folder + '\a/b'), ($folder + "\a`nb"), ($folder + '\%2e%2e'), ($folder + '\NUL.txt'), ($folder + '\\child'), ($folder + '\a*'), ($folder + ('a' * 2000)))
foreach ($path in $badPaths) {
    $rejected = $false
    try { [void][ShotGridNas]::ValidateFolder($path) } catch { $rejected = $true }
    if (!$rejected) { throw "非法路径未拒绝：$path" }
}
$badUris = @('https://open/a', 'shotgrid-nas://open/abc?cmd=calc', 'shotgrid-nas://open/%22', 'shotgrid-nas://open/a', 'shotgrid-nas://open/_w', ('shotgrid-nas://open/' + 'YQ' + '" extra'), ('shotgrid-nas://open/' + 'YQ' + "`n"))
foreach ($uri in $badUris) {
    $rejected = $false
    try { [void][ShotGridNas]::Decode($uri) } catch { $rejected = $true }
    if (!$rejected) { throw '非法协议未拒绝' }
}
$invalidSigned = @((New-Ticket $folder ($now - 61) ($now - 1)), (New-Ticket $folder ($now + 10) ($now + 70)), (New-Ticket $folder $now ($now + 600)), (New-Ticket $folder $now ($now + 60) 'OTHER'), (New-Ticket 'C:\Windows'), ($ticket.Substring(0, $ticket.Length - 5) + 'AAAAA'))
foreach ($value in $invalidSigned) {
    $rejected = $false
    try { [void][ShotGridNas]::Verify($value, $key, $now) } catch { $rejected = $true }
    if (!$rejected) { throw '签名安全用例未拒绝' }
}
$otherKey = New-Object Security.Cryptography.RSACryptoServiceProvider 2048
$otherKey.PersistKeyInCsp = $false
$rejected = $false
try { [void][ShotGridNas]::Verify($ticket, $otherKey.ToXmlString($false), $now) } catch { $rejected = $true }
if (!$rejected) { throw '错误公钥未拒绝' }
$rsa.Dispose()
$otherKey.Dispose()
Write-Host '签名、过期、未来时间、超长有效期、用途、危险目录、篡改、错误公钥及重放检查通过。'
Write-Host ('通过：C# 编译，中文目录往返，' + $badPaths.Count + ' 个非法路径，' + $badUris.Count + ' 个非法协议。')
