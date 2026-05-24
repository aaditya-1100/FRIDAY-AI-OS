"""
Open http(s) URLs in the user's installed Google Chrome default profile.

Uses: chrome.exe <url> with NO --user-data-dir and NO automation flags, so Windows
attaches to the normal Chrome user profile (cookies, extensions, sessions).

If Chrome cannot be resolved, logs instructions and returns False (no Playwright fallback).
Override install location with env CHROME_PATH.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_DEVNULL = subprocess.DEVNULL


def _candidate_chrome_paths() -> list[Path]:
    out: list[Path] = []
    env = (os.environ.get("CHROME_PATH") or "").strip()
    if env:
        out.append(Path(env))
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pfx86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    out.extend(
        [
            Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(pfx86) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
    )
    return out


def resolve_chrome_executable() -> Path | None:
    for p in _candidate_chrome_paths():
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def open_url_in_chrome(url: str) -> bool:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False

    chrome = resolve_chrome_executable()
    if chrome is None:
        print(
            "[BROWSER] Google Chrome executable not found. "
            "Install Chrome or set CHROME_PATH to the full path of chrome.exe"
        )
        return False

    try:
        # Launch Chrome directly without profile-locking arguments so it attaches
        # naturally to the user's active personal Chrome session (retains cookies, sessions).
        args = [str(chrome), url]
        popen_kw = {
            "stdin": _DEVNULL,
            "stdout": _DEVNULL,
            "stderr": _DEVNULL,
            "close_fds": True,
        }
        print(f"[BROWSER] Launching URL in user's active Chrome session: '{url}'")
        if sys.platform == "win32":
            subprocess.Popen(
                args,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                **popen_kw,
            )
        else:
            subprocess.Popen(args, start_new_session=True, **popen_kw)
        return True
    except Exception as e:
        print(f"[BROWSER] Chrome launch failed: {e}")
        return False
