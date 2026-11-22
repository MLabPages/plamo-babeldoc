"""API キーなどを環境変数から読む（コードや設定ファイルには保存しない）。

Windows では setx で登録したユーザー環境変数を、アプリを再起動しなくても読めるように
レジストリ（HKCU\Environment / HKLM の System Environment）も参照する。
"""

from __future__ import annotations

import os


def get_env(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value.strip()
    try:
        import winreg

        for root, path in (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(root, path) as k:
                    v, _ = winreg.QueryValueEx(k, name)
                    if v:
                        return str(v).strip()
            except OSError:
                continue
    except ImportError:
        pass
    return ""


def env_for_child(names: list[str]) -> dict:
    """翻訳プロセスへ渡す環境変数（値はプロセス間で受け渡すだけで保存しない）。"""
    env = dict(os.environ)
    for n in names:
        v = get_env(n)
        if v:
            env[n] = v
    return env


def set_user_env(name: str, value: str | None) -> None:
    """Save (or delete when value is None) a Windows user environment variable.

    設定画面から入力した API キーを、setx と同じユーザー環境変数に保存する。
    アプリのファイルや設定には書かない。
    """
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        if value:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass
    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)  # 起動時に受け継いだ値も使わない
    try:  # 開いているほかのアプリにも変更を知らせる（WM_SETTINGCHANGE）
        import ctypes

        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 2000, ctypes.byref(result))
    except Exception:  # noqa: BLE001
        pass
