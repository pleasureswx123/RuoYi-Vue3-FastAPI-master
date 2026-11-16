# 使用 Windows PowerShell 5.1：powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\shot-grid-folder-opener.ps1
# 卸载：同一命令末尾增加 -Mode Uninstall。自检不会注册协议或打开目录：-Mode Test。
param([ValidateSet('Install', 'Uninstall', 'Test')][string]$Mode = 'Install', [string]$DemoRoot = '')
$ErrorActionPreference = 'Stop'
$appDirectory = Join-Path $env:LOCALAPPDATA 'ShotGridFolderOpener'
$exePath = Join-Path $appDirectory 'ShotGridFolderOpener.exe'
$registryPath = 'HKCU:\Software\Classes\shotgrid-folder'
$source = @'
using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Diagnostics;
using System.Windows.Forms;

public static class ShotGridFolderOpener {
    public static string DemoPath(string uri, string root) {
        bool asset = uri != null && uri.StartsWith("shotgrid-folder://demo-asset/", StringComparison.Ordinal);
        string prefix = asset ? "shotgrid-folder://demo-asset/" : "shotgrid-folder://demo/";
        string pattern = asset ? @"\Ashotgrid-folder://demo-asset/([1-9][0-9]{0,15}/){4}(0|[1-9][0-9]{0,15})/?\z" : @"\Ashotgrid-folder://demo/([1-9][0-9]{0,15}/){3}(0|[1-9][0-9]{0,15})/?\z";
        if (uri == null || !Regex.IsMatch(uri, pattern))
            throw new ArgumentException("Invalid local demo request.");
        if (String.IsNullOrEmpty(root) || !Regex.IsMatch(root, @"\A[A-Za-z]:\\") || root.Length < 4 || root != Path.GetFullPath(root).TrimEnd('\\'))
            throw new ArgumentException("Invalid local demo root.");
        string[] ids = uri.Substring(prefix.Length).TrimEnd('/').Split('/');
        foreach (string id in ids) if (Int64.Parse(id) > 9007199254740991L) throw new ArgumentException("Invalid identifier.");
        if (asset) return Path.Combine(root, "project-" + ids[0], "asset-" + ids[1], "item-" + ids[2], "version-" + ids[3], "candidate-" + ids[4]);
        return Path.Combine(root, "project-" + ids[0], "shot-" + ids[1], "version-" + ids[2], "candidate-" + ids[3]);
    }
    public static string LayoutPath(string uri, string root) {
        if (uri == null || uri.Length > 4096 || !Regex.IsMatch(uri, @"\Ashotgrid-folder://demo-layout/[A-Za-z0-9_-]+/?\z"))
            throw new ArgumentException("Invalid layout request.");
        string data = uri.Substring("shotgrid-folder://demo-layout/".Length).TrimEnd('/').Replace('-', '+').Replace('_', '/');
        data = data.PadRight((data.Length + 3) / 4 * 4, '=');
        string relative = new UTF8Encoding(false, true).GetString(Convert.FromBase64String(data));
        // 复用严格 UNC 目录段校验，但永不打开这个占位网络路径。
        string token = Convert.ToBase64String(Encoding.UTF8.GetBytes(@"\\192.168.10.64\demo\" + relative)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        Decode("shotgrid-folder://open/" + token);
        string[] parts = relative.Split('\\');
        if (parts[parts.Length - 1] == "FINAL") Array.Resize(ref parts, parts.Length - 1);
        bool legacy = parts.Length == 4 && (parts[1] == "VIDEO" || parts[1] == "ASSET");
        bool versioned = parts.Length == 6 && Regex.IsMatch(parts[5], @"\AV[0-9]{3,}\z") && (
            (parts[1] == "SHOT" && Regex.IsMatch(parts[2], @"\AEP[0-9]{2,}\z", RegexOptions.IgnoreCase) &&
                Regex.IsMatch(parts[3], @"\A[0-9]{3,}\z") && Regex.IsMatch(parts[4], @"\A[0-9]{4,}\z")) ||
            (parts[1] == "ASSET" && Regex.IsMatch(parts[2], @"\A(character|environment|prop)\z", RegexOptions.IgnoreCase) &&
                Regex.IsMatch(parts[4], @"\A.+__[1-9][0-9]*\z")));
        if (!legacy && !versioned) throw new ArgumentException("Invalid business hierarchy.");
        // 旧协议同时校验根目录配置，拒绝磁盘根及设备路径。
        DemoPath("shotgrid-folder://demo/1/1/1/0", root);
        string result = Path.GetFullPath(Path.Combine(root, relative));
        if (!result.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Invalid layout root.");
        return result;
    }
    public static void CheckPlainDirectory(string path) {
        for (DirectoryInfo dir = new DirectoryInfo(path); dir != null; dir = dir.Parent) {
            if (dir.Exists && (dir.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new ArgumentException("Local demo junctions and symbolic links are not allowed.");
        }
    }
    public static string PrepareDemo(string uri, string root) {
        string folder = uri.StartsWith("shotgrid-folder://demo-layout/", StringComparison.Ordinal) ? LayoutPath(uri, root) : DemoPath(uri, root);
        CheckPlainDirectory(folder);
        if (!Directory.Exists(root)) throw new ArgumentException("Local demo is not configured on this computer.");
        Directory.CreateDirectory(folder);
        CheckPlainDirectory(folder);
        string sample = Path.Combine(root, "sample.mp4");
        string target = Path.Combine(folder, "LOCAL_DEMO_ONLY.mp4");
        bool assetDemo = uri.StartsWith("shotgrid-folder://demo-asset/", StringComparison.Ordinal) || folder.IndexOf(@"\ASSET\", StringComparison.OrdinalIgnoreCase) >= 0;
        if (assetDemo) {
            string picture = Path.Combine(folder, "LOCAL_DEMO_ONLY.svg");
            if (!File.Exists(picture)) {
                using (var stream = new FileStream(picture, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
                    writer.Write("<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'><rect width='640' height='360' fill='#232832'/><text x='50' y='185' fill='#ffbd59' font-size='32'>LOCAL ASSET DEMO ONLY</text></svg>");
            }
        }
        if (!assetDemo && File.Exists(sample)) {
            if ((File.GetAttributes(sample) & FileAttributes.ReparsePoint) != 0) throw new ArgumentException("Invalid sample file.");
            if (!File.Exists(target)) File.Copy(sample, target, false);
        }
        string note = Path.Combine(folder, "LOCAL_DEMO_README.txt");
        if (!File.Exists(note)) {
            using (var stream = new FileStream(note, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(true))) {
                writer.WriteLine("本地文件夹功能模拟：本目录文件为演示副本，不是当前任务的正式成果。");
                writer.WriteLine("仅用于验证镜头、资产分项与版本目录；同一版本的候选文件放在一起；不连接公司 NAS，不修改业务记录。");
                writer.WriteLine(uri);
            }
        }
        return folder;
    }
    public static string Decode(string uri) {
        if (uri == null || uri.Length > 8192 || !Regex.IsMatch(uri, @"\Ashotgrid-folder://open/[A-Za-z0-9_-]+/?\z"))
            throw new ArgumentException("Invalid folder request.");
        string token = uri.Substring("shotgrid-folder://open/".Length).TrimEnd('/');
        string data = token.Replace('-', '+').Replace('_', '/');
        data = data.PadRight((data.Length + 3) / 4 * 4, '=');
        string path = new UTF8Encoding(false, true).GetString(Convert.FromBase64String(data));
        if (path.Length > 2048 || !path.StartsWith(@"\\192.168.10.64\", StringComparison.Ordinal))
            throw new ArgumentException("Only the company NAS is supported.");
        string[] parts = path.Substring(2).Split('\\');
        if (parts.Length < 2) throw new ArgumentException("Missing NAS share.");
        foreach (string part in parts) {
            if (part.Length == 0 || part == "." || part == ".." || part != part.Trim() || part.EndsWith(".") ||
                Regex.IsMatch(part, @"[\x00-\x1f\x7f/:*?""<>|]") ||
                Regex.IsMatch(part, @"\A(con|prn|aux|nul|com[0-9]|lpt[0-9])(\.|$)", RegexOptions.IgnoreCase))
                throw new ArgumentException("Invalid NAS folder.");
        }
        if (!String.Equals(Path.GetFullPath(path), path, StringComparison.Ordinal))
            throw new ArgumentException("Folder must be canonical.");
        return path;
    }
    [STAThread]
    public static void Main(string[] args) {
        try {
            if (args.Length != 1) throw new ArgumentException("Invalid folder request.");
            string folder;
            if (args[0].StartsWith("shotgrid-folder://demo-layout/", StringComparison.Ordinal) || args[0].StartsWith("shotgrid-folder://demo/", StringComparison.Ordinal) || args[0].StartsWith("shotgrid-folder://demo-asset/", StringComparison.Ordinal)) {
                string config = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ShotGridFolderOpener", "demo-root.txt");
                folder = PrepareDemo(args[0], File.ReadAllText(config, Encoding.UTF8).Trim());
            } else folder = Decode(args[0]);
            if (!Directory.Exists(folder)) {
                MessageBox.Show("Cannot access this NAS folder. Connect to the company network and check your Windows share permissions.\n\n" + folder,
                    "Shot Grid", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            // 固定程序、固定目录参数；不通过 cmd/PowerShell 执行请求内容。
            Process.Start(new ProcessStartInfo {
                FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe"),
                Arguments = "\"" + folder + "\"",
                UseShellExecute = false
            });
        } catch (Exception) {
            MessageBox.Show("Unable to open the folder. Use a valid Shot Grid NAS folder link or copy the path from Shot Grid.",
                "Shot Grid", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }
}
'@

if ($Mode -eq 'Test') {
    Add-Type -TypeDefinition $source -ReferencedAssemblies System.Windows.Forms
    function Encode-Folder([string]$Folder) {
        'shotgrid-folder://open/' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Folder)).TrimEnd('=').Replace('+','-').Replace('/','_')
    }
    $validPaths = @('\\192.168.10.64\work', '\\192.168.10.64\work\项目 空格\镜头&01')
    foreach ($folder in $validPaths) {
        if ([ShotGridFolderOpener]::Decode((Encode-Folder $folder)) -cne $folder) { throw 'Round-trip failed' }
    }
    $badPaths = @('C:\Windows', '\\other-server\work', '\\192.168.10.64.evil\work', '\\?\UNC\192.168.10.64\work',
        '\\192.168.10.64\work\..\secret', '\\192.168.10.64\work\.', '\\192.168.10.64\work\CON',
        '\\192.168.10.64\work\bad" & calc', '\\192.168.10.64\work\file:stream', '\\192.168.10.64\work\trailing.',
        '\\192.168.10.64\work\', "\\192.168.10.64\work\bad`npath")
    $rejected = 0
    foreach ($folder in $badPaths) {
        try { [void][ShotGridFolderOpener]::Decode((Encode-Folder $folder)) } catch { $rejected++ }
    }
    foreach ($uri in @('https://example.com', 'shotgrid-folder://open/@@@', 'shotgrid-folder://open/_w', 'shotgrid-folder://open/YQ?command=calc')) {
        try { [void][ShotGridFolderOpener]::Decode($uri) } catch { $rejected++ }
    }
    if ($rejected -ne ($badPaths.Count + 4)) { throw 'Unsafe folder request accepted' }
    $demo = [ShotGridFolderOpener]::DemoPath('shotgrid-folder://demo/1/2/3/4', 'C:\ShotGridDemo')
    if ($demo -cne 'C:\ShotGridDemo\project-1\shot-2\version-3\candidate-4') { throw 'Invalid demo mapping' }
    $assetDemo = [ShotGridFolderOpener]::DemoPath('shotgrid-folder://demo-asset/1/2/3/4/5', 'C:\ShotGridDemo')
    if ($assetDemo -cne 'C:\ShotGridDemo\project-1\asset-2\item-3\version-4\candidate-5') { throw 'Invalid asset mapping' }
    $badDemo = @('shotgrid-folder://demo-asset/1/2/3/4/../Windows','shotgrid-folder://demo-asset/1/0/3/4/5','shotgrid-folder://demo-asset/1/2/3/4/9007199254740992','shotgrid-folder://demo/1/2/3/../Windows','shotgrid-folder://demo/0/2/3/4','shotgrid-folder://demo/1/2/3/4?path=C:\Windows','shotgrid-folder://demo/1/2/3/%2e%2e','shotgrid-folder://demo/1/2/3/9007199254740992')
    foreach ($uri in $badDemo) {
        $blocked = $false
        try { [void][ShotGridFolderOpener]::DemoPath($uri, 'C:\ShotGridDemo') } catch { $blocked = $true }
        if (!$blocked) { throw 'Invalid local demo request accepted' }
    }
    function Encode-Layout([string]$Relative) {
        'shotgrid-folder://demo-layout/' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Relative)).TrimEnd('=').Replace('+','-').Replace('/','_')
    }
    foreach ($relative in @('项目A\SHOT\EP001\001\0001\V001\FINAL', '项目A\ASSET\Prop\宝剑\正面__7\V002\FINAL', '项目A\VIDEO\EP01\001_0001\FINAL', '项目A\SHOT\EP001\001\0001\V001', '项目A\ASSET\Prop\宝剑\正面__7\V002', '项目A\VIDEO\EP01\001_0001')) {
        $expected = Join-Path 'C:\ShotGridDemo' $relative
        if ([ShotGridFolderOpener]::LayoutPath((Encode-Layout $relative), 'C:\ShotGridDemo') -cne $expected) { throw 'Named layout mismatch' }
    }
    foreach ($relative in @('项目A\SHOT\EP001\001\0001\V001\FINAL\FINAL', '项目A\SHOT\EP001\001\0001\V001\..\FINAL', 'C:\Windows', '..\SHOT\EP001\001\0001\V001', '项目A\SHOT\EP001\001', '项目A\ASSET\Prop\剑\CON\V001', '项目A\ASSET\Prop\剑\正面\V001')) {
        $blocked = $false
        try { [void][ShotGridFolderOpener]::LayoutPath((Encode-Layout $relative), 'C:\ShotGridDemo') } catch { $blocked = $true }
        if (!$blocked) { throw 'Unsafe named layout accepted' }
    }
    Write-Output 'PASS: 6 named layouts including FINAL; 7 unsafe layouts rejected.'
    Write-Output "PASS: 2 valid folders; $rejected invalid requests rejected; no Explorer process started."
    Write-Output 'PASS: local demo mapping; 8 unsafe demo requests rejected; no local folders created.'
    exit 0
}

if ($Mode -eq 'Uninstall') {
    $registered = (Get-ItemProperty -LiteralPath "$registryPath\shell\open\command" -ErrorAction SilentlyContinue).'(default)'
    if ($registered -and $registered -ne ('"' + $exePath + '" "%1"')) { throw 'This protocol is owned by another installation.' }
    if (Test-Path -LiteralPath $registryPath) { Remove-Item -LiteralPath $registryPath -Recurse }
    if (Test-Path -LiteralPath $exePath) { Remove-Item -LiteralPath $exePath }
    Write-Output 'Shot Grid folder opener uninstalled for the current Windows user.'
    exit 0
}

$existing = (Get-ItemProperty -LiteralPath "$registryPath\shell\open\command" -ErrorAction SilentlyContinue).'(default)'
if ($existing -and $existing -ne ('"' + $exePath + '" "%1"')) { throw 'This protocol is already registered by another application.' }
[void](New-Item -ItemType Directory -Path $appDirectory -Force)
if ($DemoRoot) {
    $DemoRoot = [IO.Path]::GetFullPath($DemoRoot).TrimEnd('\')
    if ($DemoRoot -notmatch '^[A-Za-z]:\\' -or $DemoRoot.Length -lt 4) { throw 'DemoRoot must be a dedicated local directory.' }
    for ($taskDirectory = [IO.DirectoryInfo]$DemoRoot; $null -ne $taskDirectory; $taskDirectory = $taskDirectory.Parent) {
        if ($taskDirectory.Exists -and ($taskDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'DemoRoot must not contain junctions or symbolic links.' }
    }
    [void](New-Item -ItemType Directory -Path $DemoRoot -Force)
    [IO.File]::WriteAllText((Join-Path $appDirectory 'demo-root.txt'), $DemoRoot, [Text.Encoding]::UTF8)
}
$temporaryExe = Join-Path $appDirectory ('ShotGridFolderOpener-' + [Guid]::NewGuid().ToString('N') + '.exe')
try {
    Add-Type -TypeDefinition $source -ReferencedAssemblies System.Windows.Forms -OutputAssembly $temporaryExe -OutputType WindowsApplication
    Move-Item -LiteralPath $temporaryExe -Destination $exePath -Force
} finally {
    if (Test-Path -LiteralPath $temporaryExe) { Remove-Item -LiteralPath $temporaryExe }
}
[void](New-Item -Path "$registryPath\shell\open\command" -Force)
Set-Item -LiteralPath $registryPath -Value 'URL:Shot Grid NAS Folder'
[void](New-ItemProperty -LiteralPath $registryPath -Name 'URL Protocol' -Value '' -PropertyType String -Force)
Set-Item -LiteralPath "$registryPath\shell\open\command" -Value ('"' + $exePath + '" "%1"')
Write-Output 'Shot Grid folder opener installed for the current Windows user. NAS validation retained; local demo requires an explicitly configured root.'
