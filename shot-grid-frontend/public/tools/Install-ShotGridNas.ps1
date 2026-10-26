# Windows PowerShell 5.1；仅安装到当前用户，无需管理员权限。
param([switch]$Uninstall, [switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
$source = @'
using System;
using System.Diagnostics;
using System.Security.Cryptography;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

public static class ShotGridNas {
    public static string ValidateFolder(string path) {
        const string prefix = @"\\192.168.10.64\";
        if (path == null || path.Length > 2000 || !path.StartsWith(prefix, StringComparison.Ordinal))
            throw new ArgumentException("仅支持公司 NAS 服务器 192.168.10.64。");
        string[] parts = path.Substring(prefix.Length).Split('\\');
        if (parts.Length < 2 || parts[0].EndsWith("$", StringComparison.Ordinal))
            throw new ArgumentException("不能打开共享根目录或管理共享。");
        foreach (string part in parts) {
            if (part.Length == 0 || part == "." || part == ".." || part.EndsWith(".") || part.EndsWith(" ") ||
                Regex.IsMatch(part, "[\\x00-\\x1f\\x7f<>:\"/|?*%]") ||
                Regex.IsMatch(part, @"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", RegexOptions.IgnoreCase))
                throw new ArgumentException("NAS 目录包含不安全字符或路径片段。");
        }
        return path;
    }
    const string TrustedKey = "__SHOTGRID_NAS_PUBLIC_KEY__";
    static byte[] FromBase64Url(string value) {
        string encoded = value.Replace('-', '+').Replace('_', '/');
        return Convert.FromBase64String(encoded.PadRight((encoded.Length + 3) / 4 * 4, '='));
    }
    public static string Decode(string value) {
        return Verify(value, TrustedKey, DateTimeOffset.UtcNow.ToUnixTimeSeconds());
    }
    public static string Verify(string value, string publicKey, long now) {
        if (value == null || value.Length > 14000 || !Regex.IsMatch(value, @"\Ashotgrid-nas://open-v1/[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\z"))
            throw new ArgumentException("打开请求格式无效，请更新工具后重试。");
        string[] token = value.Substring("shotgrid-nas://open-v1/".Length).Split('.');
        byte[] data = FromBase64Url(token[0]);
        using (var rsa = new RSACryptoServiceProvider()) {
            rsa.PersistKeyInCsp = false;
            rsa.FromXmlString(publicKey);
            if (rsa.KeySize < 2048 || !rsa.VerifyData(data, CryptoConfig.MapNameToOID("SHA256"), FromBase64Url(token[1])))
                throw new ArgumentException("签名校验失败，请从可信 Shot Grid 页面重新打开。");
        }
        string[] parts = new UTF8Encoding(false, true).GetString(data).Split('\n');
        long issued, expires;
        if (parts.Length != 5 || parts[0] != "SGNAS1" ||
            !long.TryParse(parts[1], out issued) || !long.TryParse(parts[2], out expires) ||
            issued < now - 60 || issued > now + 5 || expires <= now || expires - issued != 60 ||
            !Regex.IsMatch(parts[3], @"\A[a-f0-9]{32}\z"))
            throw new ArgumentException("打开凭证已过期或无效，请返回页面重试，并检查电脑时间。");
        return ValidateFolder(parts[4]);
    }
    public static void Consume(string value, string cacheRoot) {
        // 文件原子创建保证同一用户并发启动时凭证最多使用一次。
        string[] parts = new UTF8Encoding(false, true).GetString(FromBase64Url(value.Substring("shotgrid-nas://open-v1/".Length).Split('.')[0])).Split('\n');
        Directory.CreateDirectory(cacheRoot);
        foreach (string item in Directory.GetFiles(cacheRoot, "*.used")) {
            try { if (File.GetLastWriteTimeUtc(item) < DateTime.UtcNow.AddMinutes(-5)) File.Delete(item); } catch (IOException) { }
        }
        try { using (File.Open(Path.Combine(cacheRoot, parts[3] + ".used"), FileMode.CreateNew, FileAccess.Write, FileShare.None)) { } }
        catch (IOException) { throw new ArgumentException("此打开凭证已使用，请返回页面重新打开。"); }
    }
    [STAThread]
    public static void Main(string[] args) {
        try {
            if (args.Length != 1) throw new ArgumentException("只允许一个目录打开请求。");
            string path = Decode(args[0]);
            Consume(args[0], Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ShotGridNas", "used"));
            if (!Directory.Exists(path)) throw new IOException("目录不存在或当前 Windows 账号没有访问权限，请检查公司网络和 NAS 登录。");
            string explorer = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe");
            // 不经过 cmd/PowerShell；路径已拒绝引号和控制字符，且必须为目录。
            Process.Start(new ProcessStartInfo(explorer, "\"" + path + "\"") { UseShellExecute = false });
        } catch (Exception error) {
            MessageBox.Show(error.Message, "Shot Grid NAS 无法打开", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }
}
'@

# 验证模式只加载类型；不写注册表、不安装、不访问 NAS、不启动资源管理器。
if ($ValidateOnly) {
    Add-Type -TypeDefinition $source -ReferencedAssemblies System.Windows.Forms
    return
}
if (-not $Uninstall -and $source.Contains('__SHOTGRID_NAS_PUBLIC_KEY__')) { throw '请从 Shot Grid 页面下载绑定服务器公钥的安装工具。' }
$installDir = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.shotgrid-nas'
$exePath = Join-Path $installDir 'ShotGridNas.exe'
$registryPath = 'HKCU:\Software\Classes\shotgrid-nas'
$command = '"' + $exePath + '" "%1"'
if ($Uninstall) {
    if (Test-Path -LiteralPath $registryPath) {
        $existing = (Get-Item -LiteralPath ($registryPath + '\shell\open\command')).GetValue('')
        if ($existing -ne $command) { throw '协议已由其他程序接管，未修改注册表。' }
        Remove-Item -LiteralPath $registryPath -Recurse
    }
    # 仅删除本工具的可执行文件，不递归删除目录内其他内容。
    if (Test-Path -LiteralPath $exePath) { Remove-Item -LiteralPath $exePath }
    Write-Host '已卸载当前用户的 Shot Grid NAS 工具。'
    return
}
if (Test-Path -LiteralPath $registryPath) {
    $existing = (Get-Item -LiteralPath ($registryPath + '\shell\open\command')).GetValue('')
    if ($existing -ne $command -and $existing -ne ('"' + (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ShotGridNas\ShotGridNas.exe') + '" "%1"')) { throw '同名协议已被其他程序注册，请联系管理员处理。' }
}
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
$temporaryExe = Join-Path $installDir ('ShotGridNas-' + [Guid]::NewGuid().ToString('N') + '.exe')
try {
    Add-Type -TypeDefinition $source -ReferencedAssemblies System.Windows.Forms -OutputAssembly $temporaryExe -OutputType WindowsApplication
    Move-Item -LiteralPath $temporaryExe -Destination $exePath -Force
} finally {
    if (Test-Path -LiteralPath $temporaryExe) { Remove-Item -LiteralPath $temporaryExe }
}
New-Item -Path ($registryPath + '\shell\open\command') -Force | Out-Null
Set-Item -LiteralPath $registryPath -Value 'URL:Shot Grid NAS'
New-ItemProperty -LiteralPath $registryPath -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
Set-Item -LiteralPath ($registryPath + '\shell\open\command') -Value $command
Write-Host '已安装。回到 Shot Grid，右键镜头或制作分项，选择“在文件资源管理器中打开”。'
Write-Host '浏览器可能询问是否允许启动工具；有效签名请求将直接打开目录。'
Write-Host '卸载：使用相同脚本并添加 -Uninstall。'
