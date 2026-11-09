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
