// PLaMo 論文リーダーのインストーラー（.NET Framework 4.8 / C# 5。installer\build.ps1 でビルド）。
// 管理者権限なしで %LOCALAPPDATA%\Programs\PLaMoPaperReader に入れ、必要なものをダウンロードする。
//   /silent /dir=<path> /models=0.8b,2b /cpu /noshortcuts /noregister /nolaunch  （試験・一括導入用）
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: System.Reflection.AssemblyTitle("PLaMo 論文リーダー セットアップ")]
[assembly: System.Reflection.AssemblyProduct("PLaMo 論文リーダー")]
[assembly: System.Reflection.AssemblyCompany("MLabPages")]
[assembly: System.Reflection.AssemblyVersion("1.0.2.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.0.2.0")]

static class Setup
{
    public const string Version = "1.0.2";
    public const string Tag = "v1.0.2";
    const string Repo = "MLabPages/plamo-babeldoc";
    const string LlamaBuild = "b12211";
    const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\PLaMoPaperReader";

    public static readonly string[] ModelIds = { "0.8b", "2b", "8b" };
    public static readonly string[] ModelLabels = { "0.8B（最速・約0.6GB）", "2B（標準・約1.8GB）", "8B（高品質・約5.3GB）" };

    public class Options
    {
        public string Dir;
        public List<string> Models = new List<string>();
        public bool Cpu, Shortcuts = true, Register = true, Silent;
    }

    public static string DefaultDir()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\PLaMoPaperReader");
    }

    public static bool HasVulkan()
    {
        return File.Exists(Path.Combine(Environment.SystemDirectory, "vulkan-1.dll"));
    }

    [STAThread]
    static int Main(string[] args)
    {
        ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072 | (SecurityProtocolType)12288;
        var o = new Options { Dir = DefaultDir(), Cpu = !HasVulkan() };
        foreach (var a in args)
        {
            var s = a.ToLowerInvariant();
            if (s == "/silent") o.Silent = true;
            else if (s == "/cpu") o.Cpu = true;
            else if (s == "/noshortcuts") o.Shortcuts = false;
            else if (s == "/noregister") o.Register = false;
            else if (s.StartsWith("/dir=")) o.Dir = Path.GetFullPath(a.Substring(5).Trim('"'));
            else if (s.StartsWith("/models=")) o.Models.AddRange(s.Substring(8).Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries));
        }
        if (o.Models.Count == 0) o.Models.Add("2b");
        if (o.Silent)
        {
            Directory.CreateDirectory(o.Dir);
            using (var log = new StreamWriter(Path.Combine(o.Dir, "install.log"), false, new UTF8Encoding(false)))
            {
                try
                {
                    Run(o, (msg, pct) => { log.WriteLine("[" + pct + "%] " + msg); log.Flush(); });
                    log.WriteLine("OK");
                    return 0;
                }
                catch (Exception e) { log.WriteLine("ERROR: " + e); return 1; }
            }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SetupForm(o));
        return 0;
    }

    // ---------- 本体 ----------
    public static void Run(Options o, Action<string, int> report)
    {
        string dir = o.Dir;
        Directory.CreateDirectory(dir);
        string tmp = Path.Combine(Path.GetTempPath(), "PLaMoPaperReaderSetup");
        Directory.CreateDirectory(tmp);

        report("アプリ本体をダウンロードしています", 2);
        string srcZip = Path.Combine(tmp, "source-" + Tag + ".zip");
        Download("https://github.com/" + Repo + "/archive/refs/tags/" + Tag + ".zip", srcZip, null);
        string srcDir = Path.Combine(tmp, "source");
        if (Directory.Exists(srcDir)) Directory.Delete(srcDir, true);
        ZipFile.ExtractToDirectory(srcZip, srcDir);
        string[] tops = Directory.GetDirectories(srcDir);
        CopyTree(tops.Length == 1 ? tops[0] : srcDir, dir);   // 翻訳済みの論文（library）やモデルは残す

        report("Python の管理ツール（uv）を準備しています", 8);
        string uvDir = Path.Combine(dir, @"tools\uv");
        string uv = Path.Combine(uvDir, "uv.exe");
        if (!File.Exists(uv))
        {
            string uvZip = Path.Combine(tmp, "uv.zip");
            Download("https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip", uvZip, null);
            ExtractFlat(uvZip, uvDir, "uv.exe");
        }

        var env = new Dictionary<string, string>();
        env["UV_PYTHON_INSTALL_DIR"] = Path.Combine(dir, "python");
        env["UV_CACHE_DIR"] = Path.Combine(dir, ".uv-cache");
        env["UV_PYTHON_PREFERENCE"] = "only-managed";
        string py = Path.Combine(dir, @".venv\Scripts\python.exe");
        if (!File.Exists(py))
        {
            report("Python 3.11 を準備しています", 12);
            Exec(uv, "venv --python 3.11 \"" + Path.Combine(dir, ".venv") + "\"", dir, env);
        }
        report("必要なパッケージを入れています（数分かかります）", 16);
        Exec(uv, "pip install --python \"" + py + "\" -r \"" + Path.Combine(dir, "requirements.txt") + "\"", dir, env);

        string llamaDir = Path.Combine(dir, "llama");
        if (!File.Exists(Path.Combine(llamaDir, "llama-server.exe")))
        {
            report("翻訳エンジン（llama.cpp）をダウンロードしています", 30);
            string kind = o.Cpu ? "cpu" : "vulkan";
            string lz = Path.Combine(tmp, "llama-" + LlamaBuild + "-" + kind + ".zip");
            Download("https://github.com/ggml-org/llama.cpp/releases/download/" + LlamaBuild + "/llama-" + LlamaBuild + "-bin-win-" + kind + "-x64.zip", lz, null);
            ExtractFlat(lz, llamaDir, "llama-server.exe");
        }

        string modelDir = Path.Combine(dir, "models");
        Directory.CreateDirectory(modelDir);
        int i = 0;
        foreach (var m in o.Models)
        {
            string file = "plamo-3-translate-" + m + "-Q4_K_M.gguf";
            string dest = Path.Combine(modelDir, file);
            int start = 35 + 55 * i / o.Models.Count, span = 55 / o.Models.Count;
            i++;
            if (File.Exists(dest)) continue;
            string label = "PLaMo 3 Translate " + m.ToUpperInvariant() + " をダウンロードしています";
            report(label, start);
            Download("https://huggingface.co/pfnet/plamo-3-translate-" + m + "-GGUF/resolve/main/" + file, dest,
                (done, total) => report(label + "（" + (done >> 20) + " / " + (total >> 20) + " MB）", start + (int)(span * done / Math.Max(total, 1))));
        }

        // タスクマネージャーにアプリ名で出るよう、説明欄とアイコンを変えた Python で動かす
        report("アプリ名の実行ファイルを準備しています", 91);
        Exec("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(dir, @"tools\brand.ps1") + "\"", dir, null);
        try { File.Delete(Path.Combine(dir, "PLaMoPaperReader.exe")); } catch { }   // 1.0.1 の起動用プログラム

        if (o.Shortcuts)
        {
            report("ショートカットを作っています", 92);
            Exec("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(dir, @"tools\make_shortcuts.ps1") + "\"", dir, null);
        }
        if (o.Register)
        {
            report("アンインストール情報を登録しています", 96);
            using (var k = Registry.CurrentUser.CreateSubKey(UninstallKey))
            {
                k.SetValue("DisplayName", "PLaMo 論文リーダー");
                k.SetValue("DisplayVersion", Version);
                k.SetValue("Publisher", "MLabPages");
                k.SetValue("InstallLocation", dir);
                k.SetValue("DisplayIcon", Path.Combine(dir, @"assets\app.ico"));
                k.SetValue("URLInfoAbout", "https://github.com/" + Repo);
                k.SetValue("UninstallString", "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + Path.Combine(dir, @"tools\uninstall.ps1") + "\"");
                k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                k.SetValue("EstimatedSize", (int)(DirSize(dir) / 1024), RegistryValueKind.DWord);
            }
        }
        try { Directory.Delete(tmp, true); } catch { }
        report("完了しました", 100);
    }

    public static void LaunchApp(string dir)
    {
        string exe = Path.Combine(dir, @".venv\Scripts\PLaMoPaperReader.exe");
        if (!File.Exists(exe)) exe = Path.Combine(dir, @".venv\Scripts\pythonw.exe");
        Process.Start(new ProcessStartInfo(exe, "\"" + Path.Combine(dir, "app.py") + "\"") { WorkingDirectory = dir, UseShellExecute = false });
    }

    // ---------- 補助 ----------
    static void Download(string url, string dest, Action<long, long> progress)
    {
        string part = dest + ".part";
        for (int attempt = 1; ; attempt++)
        {
            try
            {
                long have = File.Exists(part) ? new FileInfo(part).Length : 0;
                var req = (HttpWebRequest)WebRequest.Create(url);
                req.UserAgent = "PLaMoPaperReaderSetup/" + Version;
                req.Timeout = 30000;
                req.ReadWriteTimeout = 60000;
                if (have > 0) req.AddRange(have);
                using (var res = (HttpWebResponse)req.GetResponse())
                {
                    bool resumed = res.StatusCode == HttpStatusCode.PartialContent;
                    if (!resumed) have = 0;
                    long total = res.ContentLength > 0 ? res.ContentLength + have : 0;
                    using (var input = res.GetResponseStream())
                    using (var output = new FileStream(part, resumed ? FileMode.Append : FileMode.Create))
                    {
                        var buf = new byte[1 << 16];
                        long done = have, last = 0;
                        int n;
                        while ((n = input.Read(buf, 0, buf.Length)) > 0)
                        {
                            output.Write(buf, 0, n);
                            done += n;
                            if (progress != null && done - last > (4 << 20)) { last = done; progress(done, total); }
                        }
                    }
                }
                if (File.Exists(dest)) File.Delete(dest);
                File.Move(part, dest);
                return;
            }
            catch (Exception e)
            {
                if (attempt >= 4 || !(e is WebException || e is IOException))
                    throw new Exception("ダウンロードに失敗しました: " + url + "（" + e.Message + "）", e);
                Thread.Sleep(2000 * attempt);
            }
        }
    }

    static void ExtractFlat(string zip, string destDir, string marker)
    {
        string tmp = destDir + ".extract";
        if (Directory.Exists(tmp)) Directory.Delete(tmp, true);
        ZipFile.ExtractToDirectory(zip, tmp);
        string[] hits = Directory.GetFiles(tmp, marker, SearchOption.AllDirectories);
        if (hits.Length == 0) throw new Exception(marker + " が見つかりませんでした。");
        CopyTree(Path.GetDirectoryName(hits[0]), destDir);
        Directory.Delete(tmp, true);
    }

    static void CopyTree(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var f in Directory.GetFiles(src)) File.Copy(f, Path.Combine(dst, Path.GetFileName(f)), true);
        foreach (var d in Directory.GetDirectories(src)) CopyTree(d, Path.Combine(dst, Path.GetFileName(d)));
    }

    static long DirSize(string dir)
    {
        long n = 0;
        try { foreach (var f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories)) n += new FileInfo(f).Length; } catch { }
        return n;
    }

    static void Exec(string exe, string args, string cwd, Dictionary<string, string> env)
    {
        var psi = new ProcessStartInfo(exe, args)
        {
            WorkingDirectory = cwd, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        };
        if (env != null) foreach (var kv in env) psi.EnvironmentVariables[kv.Key] = kv.Value;
        var tail = new Queue<string>();
        DataReceivedEventHandler h = (s, e) =>
        {
            if (string.IsNullOrWhiteSpace(e.Data)) return;
            lock (tail) { tail.Enqueue(e.Data); if (tail.Count > 15) tail.Dequeue(); }
        };
        using (var p = new Process { StartInfo = psi })
        {
            p.OutputDataReceived += h;
            p.ErrorDataReceived += h;
            p.Start();
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            p.WaitForExit();
            if (p.ExitCode != 0)
                throw new Exception(Path.GetFileName(exe) + " が失敗しました。\r\n" + string.Join("\r\n", tail.ToArray()));
        }
    }
}

class SetupForm : Form
{
    readonly Setup.Options opts;
    readonly TextBox dirBox = new TextBox();
    readonly CheckBox[] modelChecks = new CheckBox[3];
    readonly CheckBox cpuCheck = new CheckBox(), launchCheck = new CheckBox();
    readonly Button installButton = new Button(), cancelButton = new Button(), browseButton = new Button();
    readonly ProgressBar bar = new ProgressBar();
    readonly Label status = new Label();
    bool running, finished;

    public SetupForm(Setup.Options o)
    {
        opts = o;
        Text = "PLaMo 論文リーダー セットアップ " + Setup.Version;
        Font = new Font("Yu Gothic UI", 9.5f);
        AutoScaleMode = AutoScaleMode.Dpi;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        ClientSize = new Size(560, 470);
        StartPosition = FormStartPosition.CenterScreen;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

        int y = 18;
        Add(new Label { Text = "英語の論文PDFを、レイアウトを保ったまま日本語で読むアプリを入れます。", AutoSize = true }, 20, y); y += 26;
        Add(new Label { Text = "翻訳はPC内のPLaMo 3 Translateで行います（Built with PLaMo）。管理者権限は不要です。", AutoSize = true, ForeColor = Color.DimGray }, 20, y); y += 38;

        Add(new Label { Text = "インストール先", AutoSize = true }, 20, y); y += 22;
        dirBox.Text = o.Dir; dirBox.SetBounds(20, y, 430, 26); Controls.Add(dirBox);
        browseButton.Text = "参照..."; browseButton.SetBounds(458, y - 1, 82, 28); Controls.Add(browseButton);
        browseButton.Click += (s, e) =>
        {
            using (var d = new FolderBrowserDialog { SelectedPath = dirBox.Text })
                if (d.ShowDialog(this) == DialogResult.OK) dirBox.Text = Path.Combine(d.SelectedPath, "PLaMoPaperReader");
        };
        y += 42;

        Add(new Label { Text = "翻訳モデル（あとからこのセットアップで追加できます）", AutoSize = true }, 20, y); y += 24;
        for (int i = 0; i < 3; i++)
        {
            modelChecks[i] = new CheckBox { Text = Setup.ModelLabels[i], AutoSize = true, Checked = o.Models.Contains(Setup.ModelIds[i]) };
            Add(modelChecks[i], 36, y); y += 26;
        }
        y += 8;
        cpuCheck.Text = "GPUを使わない（CPU版。GPUのないPC向け、遅くなります）"; cpuCheck.AutoSize = true; cpuCheck.Checked = o.Cpu;
        Add(cpuCheck, 20, y); y += 28;
        launchCheck.Text = "終わったらアプリを開く"; launchCheck.AutoSize = true; launchCheck.Checked = true;
        Add(launchCheck, 20, y); y += 40;

        status.Text = "ダウンロードは合計で約3〜8GBです。途中で止まっても、もう一度実行すれば続きから再開します。";
        status.SetBounds(20, y, 520, 40); Controls.Add(status); y += 44;
        bar.SetBounds(20, y, 520, 20); Controls.Add(bar); y += 38;

        installButton.Text = "インストール"; installButton.SetBounds(330, y, 110, 32); Controls.Add(installButton);
        cancelButton.Text = "閉じる"; cancelButton.SetBounds(450, y, 90, 32); Controls.Add(cancelButton);
        AcceptButton = installButton;
        installButton.Click += (s, e) => { if (finished) Close(); else Start(); };
        cancelButton.Click += (s, e) => Close();
        FormClosing += (s, e) =>
        {
            if (!running) return;
            if (MessageBox.Show(this, "インストール中です。中止しますか？（次回は続きから再開します）", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes)
                e.Cancel = true;
            else Environment.Exit(1);
        };
    }

    void Add(Control c, int x, int y) { c.Location = new Point(x, y); Controls.Add(c); }

    void SetInputs(bool on)
    {
        foreach (Control c in Controls) if (c is CheckBox || c is TextBox || c == browseButton) c.Enabled = on;
        installButton.Enabled = on;
    }

    void Start()
    {
        opts.Dir = dirBox.Text.Trim();
        opts.Models.Clear();
        for (int i = 0; i < 3; i++) if (modelChecks[i].Checked) opts.Models.Add(Setup.ModelIds[i]);
        if (opts.Models.Count == 0) { MessageBox.Show(this, "翻訳モデルを1つ以上選んでください。", Text); return; }
        opts.Cpu = cpuCheck.Checked;
        SetInputs(false);
        running = true;
        var t = new Thread(() =>
        {
            try
            {
                Setup.Run(opts, (msg, pct) => BeginInvoke((Action)(() => { status.Text = msg; bar.Value = Math.Max(0, Math.Min(100, pct)); })));
                BeginInvoke((Action)Done);
            }
            catch (Exception ex)
            {
                BeginInvoke((Action)(() =>
                {
                    running = false;
                    status.Text = "インストールできませんでした。もう一度「インストール」を押すと続きから再開します。";
                    MessageBox.Show(this, ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    SetInputs(true);
                }));
            }
        });
        t.IsBackground = true;
        t.Start();
    }

    void Done()
    {
        running = false;
        finished = true;
        status.Text = "インストールが終わりました。デスクトップとスタートメニューの「PLaMo論文リーダー」から開けます。\r\n初回の翻訳では、レイアウト解析用のデータを追加でダウンロードします。";
        installButton.Text = "完了";
        installButton.Enabled = true;
        cancelButton.Visible = false;
        if (launchCheck.Checked) { try { Setup.LaunchApp(opts.Dir); } catch { } }
    }
}

