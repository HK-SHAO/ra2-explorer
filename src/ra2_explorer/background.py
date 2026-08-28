from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn

from ra2_explorer.api import create_app
from ra2_explorer.config import DEFAULT_HOST, DEFAULT_PORT, load_settings
from ra2_explorer.errors import Ra2ExplorerError

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "RA2Explorer"
MUTEX_NAME = "Local\\RA2ExplorerBackground46120"


def service_status(*, port: int = DEFAULT_PORT, timeout: float = 0.6) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(
            f"http://{DEFAULT_HOST}:{port}/api/health",
            timeout=timeout,
        ) as response:
            payload = json.loads(response.read(65_536).decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {"running": False, "host": DEFAULT_HOST, "port": port}
    if payload.get("status") != "ok" or payload.get("name") != "ra2-explorer":
        return {
            "running": False,
            "host": DEFAULT_HOST,
            "port": port,
            "error": "端口已被其他服务占用",
        }
    return {
        "running": True,
        "host": DEFAULT_HOST,
        "port": port,
        "url": f"http://{DEFAULT_HOST}:{port}",
        "pid": payload.get("pid"),
        "version": payload.get("version"),
    }


def start_background(root: Path, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    _require_windows()
    current = service_status(port=port)
    if current["running"]:
        return current
    if current.get("error"):
        raise Ra2ExplorerError(str(current["error"]))

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise Ra2ExplorerError("当前 Python 环境缺少 pythonw.exe")
    command = [
        str(pythonw),
        "-m",
        "ra2_explorer.background",
        "--root",
        str(root.resolve()),
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        command,
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = service_status(port=port)
        if status["running"]:
            return status
        if process.poll() is not None:
            break
        time.sleep(0.15)
    raise Ra2ExplorerError("后台服务启动失败，请查看 .runtime\\logs\\background.log")


def stop_background(*, port: int = DEFAULT_PORT) -> dict[str, Any]:
    status = service_status(port=port)
    if not status["running"]:
        return status
    pid = status.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        raise Ra2ExplorerError("后台服务没有返回有效的进程编号")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not service_status(port=port)["running"]:
            return {"running": False, "host": DEFAULT_HOST, "port": port}
        time.sleep(0.1)
    raise Ra2ExplorerError("后台服务未在预期时间内退出")


def install_autostart(root: Path, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    _require_windows()
    import winreg

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    command = subprocess.list2cmdline(
        [
            str(pythonw),
            "-m",
            "ra2_explorer.background",
            "--root",
            str(root.resolve()),
            "--port",
            str(port),
        ]
    )
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)
    return {"installed": True, "scope": "current_user", "command": command}


def uninstall_autostart() -> dict[str, Any]:
    _require_windows()
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            access=winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except FileNotFoundError:
        pass
    return {"installed": False, "scope": "current_user"}


def run_server(root: Path, *, port: int = DEFAULT_PORT) -> int:
    _require_windows()
    root = root.resolve()
    os.chdir(root)
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        return 1
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.kernel32.CloseHandle(mutex)
        return 0

    settings = load_settings(working_directory=root)
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    pid_path = settings.data_dir / "background.pid"
    pid_path.write_text(str(os.getpid()), encoding="ascii")
    try:
        uvicorn.run(
            create_app(settings),
            host=DEFAULT_HOST,
            port=port,
            log_level="info",
            log_config=_log_config(log_dir / "background.log"),
            access_log=False,
        )
    finally:
        try:
            if pid_path.read_text(encoding="ascii").strip() == str(os.getpid()):
                pid_path.unlink(missing_ok=True)
        except OSError:
            pass
        ctypes.windll.kernel32.CloseHandle(mutex)
    return 0


def _log_config(path: Path) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(path),
                "maxBytes": 2_000_000,
                "backupCount": 3,
                "encoding": "utf-8",
                "formatter": "default",
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        },
    }


def _require_windows() -> None:
    if sys.platform != "win32":
        raise Ra2ExplorerError("后台自启功能当前只支持 Windows")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="pythonw -m ra2_explorer.background")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    if not 46_100 <= args.port <= 46_199:
        return 2
    return run_server(args.root, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "install_autostart",
    "run_server",
    "service_status",
    "start_background",
    "stop_background",
    "uninstall_autostart",
]
