// Match the Windows shortcut to the app's explicit identity.
using System;
using System.Runtime.InteropServices;

public static class ShortcutIdentity
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    struct PropertyKey { public Guid Format; public uint Id; }

    [StructLayout(LayoutKind.Explicit, Size = 24)]
    struct PropVariant
    {
        [FieldOffset(0)] public ushort Type;
        [FieldOffset(8)] public IntPtr Text;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHGetPropertyStoreFromParsingName(
        string path, IntPtr bindContext, uint flags, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);

    public static void Set(string path, string appId)
    {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out store);
        var key = new PropertyKey {
            Format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), Id = 5
        };
        var value = new PropVariant { Type = 31, Text = Marshal.StringToCoTaskMemUni(appId) };
        try {
            store.SetValue(ref key, ref value);
            store.Commit();
        } finally {
            Marshal.FreeCoTaskMem(value.Text);
            Marshal.ReleaseComObject(store);
        }
    }
}
