// chimiPack single-file launcher for Electron apps.
// Layout of the finished .exe:  [this program][Electron runtime zip][app zip][trailer]
// First launch: unpacks the runtime once into %LOCALAPPDATA%\chimiPack\runtime (shared by all
// chimiPack apps), then builds the app folder from hard links (no extra disk space) and starts it.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("%%NAME%%")]
[assembly: AssemblyProduct("%%NAME%%")]
[assembly: AssemblyDescription("%%NAME%%")]
[assembly: AssemblyCompany("%%PUBLISHER%%")]
[assembly: AssemblyVersion("%%VERSION4%%")]
[assembly: AssemblyFileVersion("%%VERSION4%%")]

static class Stub
{
    const string AppName = "%%NAME%%";
    const string AppId = "%%APPID%%";
    const string ExeName = "%%EXENAME%%";
    const string RuntimeKey = "%%RTKEY%%";
    const string AppKey = "%%APPKEY%%";
    const string Magic = "CHIMIPK1";

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateHardLink(string newFile, string existingFile, IntPtr security);

    static string baseDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "chimiPack");
    static string runtimeDir = Path.Combine(baseDir, "runtime", RuntimeKey);
    static string appRoot = Path.Combine(baseDir, "apps", AppId);
    static string appDir = Path.Combine(appRoot, AppKey);

    [STAThread]
    static void Main(string[] args)
    {
        try
        {
            if (!File.Exists(Path.Combine(appDir, ".complete")))
            {
                Exception error = null;
                Application.EnableVisualStyles();
                Form splash = MakeSplash();
                var worker = new Thread(() =>
                {
                    try { Setup(); } catch (Exception e) { error = e; }
                    try { splash.Invoke(new Action(splash.Close)); } catch { }
                });
                splash.Shown += (s, e) => worker.Start();
                Application.Run(splash);
                worker.Join();
                if (error != null) throw error;
            }
            var sb = new StringBuilder();
            foreach (string a in args) sb.Append(" \"").Append(a.Replace("\"", "\\\"")).Append('"');
            Process.Start(new ProcessStartInfo(Path.Combine(appDir, ExeName), sb.ToString())
            {
                UseShellExecute = false,
                WorkingDirectory = appDir
            });
        }
        catch (Exception e)
        {
            MessageBox.Show("Sorry, " + AppName + " couldn't start.\n\n" + e.Message, AppName,
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    static Form MakeSplash()
    {
        var f = new Form
        {
            Text = AppName, FormBorderStyle = FormBorderStyle.FixedDialog, StartPosition = FormStartPosition.CenterScreen,
            ClientSize = new Size(380, 110), MaximizeBox = false, MinimizeBox = false, ShowInTaskbar = true,
            BackColor = Color.White, Font = new Font("Segoe UI", 10f)
        };
        try { f.Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location); } catch { }
        var label = new Label { Text = "Setting up " + AppName + "...\nThis only happens the first time.", AutoSize = false,
            Location = new Point(20, 16), Size = new Size(340, 44) };
        var bar = new ProgressBar { Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 25,
            Location = new Point(20, 68), Size = new Size(340, 18) };
        f.Controls.Add(label);
        f.Controls.Add(bar);
        return f;
    }

    static void Setup()
    {
        string self = Assembly.GetExecutingAssembly().Location;
        long rtOff, rtLen, appOff, appLen;
        using (var fs = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            var br = new BinaryReader(fs);
            fs.Seek(-40, SeekOrigin.End);
            rtOff = br.ReadInt64(); rtLen = br.ReadInt64(); appOff = br.ReadInt64(); appLen = br.ReadInt64();
            if (Encoding.ASCII.GetString(br.ReadBytes(8)) != Magic) throw new Exception("This file is damaged (missing app data).");

            using (var mutex = new Mutex(false, "chimiPack_runtime_" + RuntimeKey))
            {
                mutex.WaitOne();
                try
                {
                    if (!File.Exists(Path.Combine(runtimeDir, ".complete")))
                    {
                        string tmp = runtimeDir + ".tmp" + Process.GetCurrentProcess().Id;
                        Extract(fs, rtOff, rtLen, tmp);
                        if (Directory.Exists(runtimeDir)) Directory.Delete(runtimeDir, true);
                        Directory.Move(tmp, runtimeDir);
                        File.WriteAllText(Path.Combine(runtimeDir, ".complete"), "");
                    }
                }
                finally { mutex.ReleaseMutex(); }
            }

            string tmpApp = appDir + ".tmp" + Process.GetCurrentProcess().Id;
            if (Directory.Exists(tmpApp)) Directory.Delete(tmpApp, true);
            foreach (string src in Directory.GetFiles(runtimeDir, "*", SearchOption.AllDirectories))
            {
                string rel = src.Substring(runtimeDir.Length + 1);
                if (rel == ".complete") continue;
                if (rel.Equals("electron.exe", StringComparison.OrdinalIgnoreCase)) rel = ExeName;
                string dst = Path.Combine(tmpApp, rel);
                Directory.CreateDirectory(Path.GetDirectoryName(dst));
                if (!CreateHardLink(dst, src, IntPtr.Zero)) File.Copy(src, dst, true);
            }
            Extract(fs, appOff, appLen, Path.Combine(tmpApp, "resources", "app"));
            if (Directory.Exists(appDir)) Directory.Delete(appDir, true);
            Directory.Move(tmpApp, appDir);
            File.WriteAllText(Path.Combine(appDir, ".complete"), "");
        }
        // Remove older versions of this app (ignore ones still in use).
        foreach (string old in Directory.GetDirectories(appRoot))
            if (!old.Equals(appDir, StringComparison.OrdinalIgnoreCase))
                try { Directory.Delete(old, true); } catch { }
    }

    static void Extract(FileStream fs, long off, long len, string dest)
    {
        using (var zip = new ZipArchive(new SubStream(fs, off, len), ZipArchiveMode.Read))
        {
            string root = Path.GetFullPath(dest) + Path.DirectorySeparatorChar;
            foreach (ZipArchiveEntry e in zip.Entries)
            {
                string target = Path.GetFullPath(Path.Combine(dest, e.FullName));
                if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;
                if (e.FullName.EndsWith("/")) { Directory.CreateDirectory(target); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                using (Stream s = e.Open())
                using (var o = new FileStream(target, FileMode.Create, FileAccess.Write))
                    s.CopyTo(o, 1 << 16);
            }
        }
    }

    // Read-only window onto part of the exe file.
    class SubStream : Stream
    {
        readonly FileStream fs; readonly long start, length; long pos;
        public SubStream(FileStream fs, long start, long length) { this.fs = fs; this.start = start; this.length = length; }
        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return length; } }
        public override long Position { get { return pos; } set { pos = value; } }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count)
        {
            long remaining = length - pos;
            if (remaining <= 0) return 0;
            if (count > remaining) count = (int)remaining;
            fs.Position = start + pos;
            int n = fs.Read(buffer, offset, count);
            pos += n;
            return n;
        }
        public override long Seek(long offset, SeekOrigin origin)
        {
            pos = origin == SeekOrigin.Begin ? offset : origin == SeekOrigin.Current ? pos + offset : length + offset;
            return pos;
        }
        public override void SetLength(long value) { throw new NotSupportedException(); }
        public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
    }
}
