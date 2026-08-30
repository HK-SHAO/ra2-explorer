from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from ra2_explorer.background import run_server, service_status
from ra2_explorer.config import DEFAULT_HOST, DEFAULT_PORT, application_root


def _browser_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    for executable in ("msedge.exe", "chrome.exe"):
        discovered = shutil.which(executable)
        if discovered:
            candidates.append(Path(discovered))
    for environment, relative_paths in (
        (
            "PROGRAMFILES(X86)",
            (
                Path("Microsoft/Edge/Application/msedge.exe"),
                Path("Google/Chrome/Application/chrome.exe"),
            ),
        ),
        (
            "PROGRAMFILES",
            (
                Path("Microsoft/Edge/Application/msedge.exe"),
                Path("Google/Chrome/Application/chrome.exe"),
            ),
        ),
        ("LOCALAPPDATA", (Path("Google/Chrome/Application/chrome.exe"),)),
    ):
        root = os.environ.get(environment)
        if root:
            candidates.extend(Path(root) / relative for relative in relative_paths)
    return tuple(dict.fromkeys(path.resolve() for path in candidates if path.is_file()))


def open_local_ui(url: str) -> bool:
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    for browser in _browser_candidates():
        try:
            subprocess.Popen(
                [str(browser), url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creation_flags,
            )
            return True
        except OSError:
            continue
    return webbrowser.open(url, new=2)


def _open_when_ready(url: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if service_status(port=DEFAULT_PORT).get("running"):
            open_local_ui(url)
            return
        time.sleep(0.15)


def _show_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "RA2 Explorer", 0x10)


def main() -> int:
    root = application_root()
    os.chdir(root)
    url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
    status = service_status(port=DEFAULT_PORT)
    if status.get("running"):
        open_local_ui(url)
        return 0
    if status.get("error"):
        _show_error(str(status["error"]))
        return 1
    threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    try:
        return run_server(root, port=DEFAULT_PORT)
    except Exception as error:
        _show_error(f"启动失败：{error}")
        return 1


__all__ = ["main", "open_local_ui"]
