// 「PLaMo 論文リーダー」の起動用プログラム。タスクマネージャーにアプリ名とアイコンで表示されるよう、
// pythonw.exe を子プロセスとして起動し、終わるまで待つ。tools\make_shortcuts.ps1 がビルドする。
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("PLaMo 論文リーダー")]
[assembly: System.Reflection.AssemblyProduct("PLaMo 論文リーダー")]
[assembly: System.Reflection.AssemblyCompany("MLabPages")]
[assembly: System.Reflection.AssemblyVersion("1.0.1.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.0.1.0")]

static class Launcher
{
    [STAThread]
    static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = Path.Combine(dir, @".venv\Scripts\pythonw.exe");
        if (!File.Exists(pythonw))
        {
            MessageBox.Show("Python 環境が見つかりません。インストーラーをもう一度実行してください。\r\n" + pythonw, "PLaMo 論文リーダー", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        string extra = "";
        foreach (var a in args) extra += " \"" + a.Replace("\"", "") + "\"";
        var psi = new ProcessStartInfo(pythonw, "\"" + Path.Combine(dir, "app.py") + "\"" + extra)
        {
            WorkingDirectory = dir,
            UseShellExecute = false,
        };
        using (var p = Process.Start(psi))
        {
            p.WaitForExit();
            return p.ExitCode;
        }
    }
}

