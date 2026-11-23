using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class ShotGridUpdate
{
    const string Feed = "http://192.168.10.122:12581/desktop-updates/";
    const string Title = "Shot Grid 桌面更新";
    const long MaxPackageSize = 512L * 1024 * 1024;
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    static void Fetch(string path, Stream output, long limit)
    {
        var request = (HttpWebRequest)WebRequest.Create(Feed + path);
        request.AllowAutoRedirect = false;
        request.Proxy = null;
        request.Timeout = request.ReadWriteTimeout = 10000;
        var elapsed = Stopwatch.StartNew();
        using (var response = (HttpWebResponse)request.GetResponse())
        using (var input = response.GetResponseStream())
        {
            if (response.StatusCode != HttpStatusCode.OK || response.ContentLength > limit)
                throw new InvalidDataException("更新服务器返回的内容无效。");
            var buffer = new byte[65536];
            int count;
            while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
            {
                if (output.Length + count > limit || elapsed.Elapsed.TotalMinutes > 5)
                    throw new InvalidDataException("更新下载超出限制。");
                output.Write(buffer, 0, count);
            }
        }
    }

    internal static Dictionary<string,string> VerifyManifest(byte[] data)
    {
        var envelope = Json.Deserialize<Dictionary<string,string>>(Encoding.UTF8.GetString(data));
        var payload = Convert.FromBase64String(envelope["payload"]);
        using (var key = new RSACryptoServiceProvider(new CspParameters(24)))
        using (var reader = new StreamReader(Assembly.GetExecutingAssembly().GetManifestResourceStream("release-key")))
        {
            key.PersistKeyInCsp = false;
            key.FromXmlString(reader.ReadToEnd());
            if (!key.VerifyData(payload, "SHA256", Convert.FromBase64String(envelope["signature"])))
                throw new InvalidDataException("更新清单签名校验失败。");
        }
        var release = Json.Deserialize<Dictionary<string,string>>(Encoding.UTF8.GetString(payload));
        if (!Regex.IsMatch(release["version"], @"\A(0|[1-9]\d*)(\.(0|[1-9]\d*)){2}\z")
            || !Regex.IsMatch(release["sha256"], @"\A[0-9A-Fa-f]{64}\z"))
            throw new InvalidDataException("发布版本信息无效。");
        return release;
    }

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length != 2) return 1;
        bool manual = args[1] == "manual";
        bool notify = manual;
        bool created;
        using (var mutex = new Mutex(false, @"Local\Laputta.ShotGrid.DesktopUpdate", out created))
        {
            if (!created)
            {
                if (manual) MessageBox.Show("正在检查或下载桌面更新。", Title);
                return 0;
            }
            string package = null;
            try
            {
                Dictionary<string,string> release;
                using (var manifest = new MemoryStream())
                {
                    Fetch("latest.json", manifest, 65536);
                    release = VerifyManifest(manifest.ToArray());
                }
                string version = release["version"];
                if (new Version(version) <= new Version(args[0]))
                {
                    if (manual) MessageBox.Show("当前已是最新版本 V" + args[0] + "。", Title);
                    return 0;
                }
                if (MessageBox.Show("发现 V" + version + "（当前 V" + args[0] + "）\n\n"
                    + release["notes"] + "\n\n现在下载更新吗？", Title, MessageBoxButtons.YesNo) != DialogResult.Yes)
                    return 0;
                notify = true;
                var cache = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "ShotGridReleaseCache");
                Directory.CreateDirectory(cache);
                foreach (var old in Directory.GetFiles(cache, "update-*.exe"))
                {
                    try { File.Delete(old); } catch (IOException) { }
                }
                package = Path.Combine(cache, "update-" + Guid.NewGuid().ToString("N") + ".exe");
                using (var file = new FileStream(package, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    Fetch(version + "/ShotGrid-setup.exe", file, MaxPackageSize);
                using (var file = new FileStream(package, FileMode.Open, FileAccess.Read, FileShare.Read))
                using (var sha = SHA256.Create())
                {
                    var digest = BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "");
                    if (!String.Equals(digest, release["sha256"], StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("安装包校验失败，请重新检查更新。");
                    if (MessageBox.Show("V" + version + " 已下载。请保存工作，确认后将关闭工作台、安装并重新打开。现在安装吗？",
                        Title, MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes)
                        return 0;
                    Process.Start(new ProcessStartInfo(package, "/P /UPDATE /R") { UseShellExecute = false });
                    package = null;
                    return 42;
                }
            }
            catch (Exception ex)
            {
                if (notify) MessageBox.Show("桌面更新未完成。\n" + ex.Message, Title);
                return 1;
            }
            finally
            {
                if (package != null) { try { File.Delete(package); } catch (IOException) { } }
            }
        }
    }
}
