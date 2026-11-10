// Python の実行ファイルを「PLaMo 論文リーダー」として動かすためのコピーを作る。
// .venv\Scripts に pythonw.exe と DLL をコピーし（Windows の従来の venv と同じ配置）、
// 実行ファイルの説明欄とアイコンを書き換える。タスクマネージャーにアプリ名で表示される。
//   brand.exe <venvのScripts> <Pythonのhome> <icoファイル> <出力exe名> <版>
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

static class Brand
{
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] static extern IntPtr BeginUpdateResource(string file, bool deleteExisting);
    [DllImport("kernel32", SetLastError = true)] static extern bool UpdateResource(IntPtr h, IntPtr type, IntPtr name, ushort lang, byte[] data, uint size);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool UpdateResource(IntPtr h, IntPtr type, string name, ushort lang, byte[] data, uint size);
    [DllImport("kernel32", SetLastError = true)] static extern bool EndUpdateResource(IntPtr h, bool discard);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] static extern IntPtr LoadLibraryEx(string file, IntPtr reserved, uint flags);
    [DllImport("kernel32")] static extern bool FreeLibrary(IntPtr h);
    delegate bool EnumNameProc(IntPtr h, IntPtr type, IntPtr name, IntPtr param);
    delegate bool EnumLangProc(IntPtr h, IntPtr type, IntPtr name, ushort lang, IntPtr param);
    [DllImport("kernel32", SetLastError = true)] static extern bool EnumResourceNames(IntPtr h, IntPtr type, EnumNameProc cb, IntPtr param);
    [DllImport("kernel32", SetLastError = true)] static extern bool EnumResourceLanguages(IntPtr h, IntPtr type, IntPtr name, EnumLangProc cb, IntPtr param);

    const int RT_ICON = 3, RT_GROUP_ICON = 14, RT_VERSION = 16;

    class Res { public int Type; public object Name; public ushort Lang; }

    static int Main(string[] args)
    {
        if (args.Length < 5) { Console.Error.WriteLine("usage: brand <scripts> <home> <ico> <exe name> <version>"); return 2; }
        string scripts = args[0], home = args[1], ico = args[2], exeName = args[3], version = args[4];
        try
        {
            // Python 本体の DLL を同じフォルダに置く（同じ内容なら上書きしない）
            foreach (var pattern in new[] { "python3*.dll", "vcruntime*.dll" })
                foreach (var dll in Directory.GetFiles(home, pattern)) CopyIfChanged(dll, Path.Combine(scripts, Path.GetFileName(dll)));

            string target = Path.Combine(scripts, exeName);
            string tmp = target + ".tmp";
            File.Copy(Path.Combine(home, "pythonw.exe"), tmp, true);
            Rebrand(tmp, ico, version);
            CopyIfChanged(tmp, target);
            File.Delete(tmp);
            Console.WriteLine(target);
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine(e.Message); return 1; }
    }

    static void CopyIfChanged(string src, string dst)
    {
        if (File.Exists(dst) && Same(src, dst)) return;
        File.Copy(src, dst, true);   // 起動中で書き換えられないときは例外（次回の更新で反映）
    }

    static bool Same(string a, string b)
    {
        var x = File.ReadAllBytes(a); var y = File.ReadAllBytes(b);
        if (x.Length != y.Length) return false;
        for (int i = 0; i < x.Length; i++) if (x[i] != y[i]) return false;
        return true;
    }

    static void Rebrand(string exe, string ico, string version)
    {
        var existing = new List<Res>();
        IntPtr mod = LoadLibraryEx(exe, IntPtr.Zero, 0x2 | 0x20);
        if (mod == IntPtr.Zero) throw new Exception("実行ファイルを読めません: " + exe);
        try
        {
            foreach (int type in new[] { RT_ICON, RT_GROUP_ICON, RT_VERSION })
            {
                var names = new List<object>();
                EnumResourceNames(mod, (IntPtr)type, (h, t, n, p) => { names.Add(ToName(n)); return true; }, IntPtr.Zero);
                foreach (var name in names)
                {
                    IntPtr np = name is string ? Marshal.StringToHGlobalUni((string)name) : (IntPtr)(int)name;
                    try { EnumResourceLanguages(mod, (IntPtr)type, np, (h, t, n, lang, p) => { existing.Add(new Res { Type = type, Name = name, Lang = lang }); return true; }, IntPtr.Zero); }
                    finally { if (name is string) Marshal.FreeHGlobal(np); }
                }
            }
        }
        finally { FreeLibrary(mod); }

        IntPtr h2 = BeginUpdateResource(exe, false);
        if (h2 == IntPtr.Zero) throw new Exception("書き換えを開始できません。");
        foreach (var r in existing) Put(h2, r.Type, r.Name, r.Lang, null);

        // アイコン（.ico の各画像 → RT_ICON、目次 → RT_GROUP_ICON）
        byte[] icoData = File.ReadAllBytes(ico);
        int count = BitConverter.ToUInt16(icoData, 4);
        var group = new MemoryStream();
        var gw = new BinaryWriter(group);
        gw.Write((ushort)0); gw.Write((ushort)1); gw.Write((ushort)count);
        for (int i = 0; i < count; i++)
        {
            int e = 6 + 16 * i;
            int size = BitConverter.ToInt32(icoData, e + 8), offset = BitConverter.ToInt32(icoData, e + 12);
            var image = new byte[size];
            Array.Copy(icoData, offset, image, 0, size);
            Put(h2, RT_ICON, i + 1, 0, image);
            gw.Write(icoData, e, 12);          // 幅・高さ・色数・予約・プレーン・ビット数・サイズ
            gw.Write((ushort)(i + 1));         // RT_ICON の番号
        }
        Put(h2, RT_GROUP_ICON, 1, 0, group.ToArray());
        Put(h2, RT_VERSION, 1, 1033, VersionInfo(version));
        if (!EndUpdateResource(h2, false)) throw new Exception("書き換えを保存できません（" + Marshal.GetLastWin32Error() + "）。");
    }

    static object ToName(IntPtr n)
    {
        long v = n.ToInt64();
        return (v >> 16) == 0 ? (object)(int)v : Marshal.PtrToStringUni(n);
    }

    static void Put(IntPtr h, int type, object name, ushort lang, byte[] data)
    {
        uint size = data == null ? 0u : (uint)data.Length;
        bool ok = name is string ? UpdateResource(h, (IntPtr)type, (string)name, lang, data, size)
                                 : UpdateResource(h, (IntPtr)type, (IntPtr)(int)name, lang, data, size);
        if (!ok) throw new Exception("リソースを書き換えられません（" + Marshal.GetLastWin32Error() + "）。");
    }

    // ---- VS_VERSIONINFO ----
    static byte[] VersionInfo(string version)
    {
        var parts = (version + ".0.0.0").Split('.');
        ushort a = ushort.Parse(parts[0]), b = ushort.Parse(parts[1]), c = ushort.Parse(parts[2]);
        var fixedInfo = new MemoryStream();
        var f = new BinaryWriter(fixedInfo);
        uint ms = ((uint)a << 16) | b, ls = (uint)c << 16;
        foreach (uint v in new uint[] { 0xFEEF04BD, 0x00010000, ms, ls, ms, ls, 0x3F, 0, 0x00040004, 1, 0, 0, 0 }) f.Write(v);

        var strings = new List<byte[]>();
        var pairs = new[,] {
            { "CompanyName", "MLabPages" },
            { "FileDescription", "PLaMo 論文リーダー" },
            { "FileVersion", version },
            { "InternalName", "PLaMoPaperReader" },
            { "LegalCopyright", "Python runtime: Copyright Python Software Foundation (PSF License). App: AGPL-3.0" },
            { "OriginalFilename", "PLaMoPaperReader.exe" },
            { "ProductName", "PLaMo 論文リーダー" },
            { "ProductVersion", version },
        };
        for (int i = 0; i < pairs.GetLength(0); i++)
            strings.Add(Block(pairs[i, 0], 1, Encoding.Unicode.GetBytes(pairs[i, 1] + "\0"), pairs[i, 1].Length + 1, null));
        var table = Block("040904B0", 1, null, 0, strings);
        var sfi = Block("StringFileInfo", 1, null, 0, new List<byte[]> { table });
        var translation = new byte[4];
        BitConverter.GetBytes((ushort)0x0409).CopyTo(translation, 0);
        BitConverter.GetBytes((ushort)1200).CopyTo(translation, 2);
        var vfi = Block("VarFileInfo", 1, null, 0, new List<byte[]> { Block("Translation", 0, translation, 4, null) });
        return Block("VS_VERSION_INFO", 0, fixedInfo.ToArray(), 52, new List<byte[]> { sfi, vfi });
    }

    static byte[] Block(string key, ushort type, byte[] value, int valueLength, List<byte[]> children)
    {
        var s = new MemoryStream();
        var w = new BinaryWriter(s);
        w.Write((ushort)0); w.Write((ushort)valueLength); w.Write(type);
        w.Write(Encoding.Unicode.GetBytes(key + "\0"));
        Pad(w);
        if (value != null) w.Write(value);
        if (children != null) foreach (var child in children) { Pad(w); w.Write(child); }
        var bytes = s.ToArray();
        BitConverter.GetBytes((ushort)bytes.Length).CopyTo(bytes, 0);
        return bytes;
    }

    static void Pad(BinaryWriter w) { while (w.BaseStream.Position % 4 != 0) w.Write((byte)0); }
}

