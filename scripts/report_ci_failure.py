from __future__ import annotations

import sys
from pathlib import Path


def _escape_workflow_command(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report_failure(log_path: Path, *, limit: int = 24) -> int:
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        lines = [f"无法读取构建日志：{error}"]
    meaningful = [line.strip() for line in lines if line.strip()]
    selected = meaningful[-limit:] or ["发行构建失败，但日志为空。"]
    start_line = max(1, len(lines) - len(selected) + 1)
    for offset, line in enumerate(selected):
        message = _escape_workflow_command(line)
        print(
            "::error "
            f"file={log_path.as_posix()},line={start_line + offset},"
            f"title=RA2 Explorer release build::{message}",
            flush=True,
        )
    return 1


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: report_ci_failure.py LOG_PATH", file=sys.stderr)
        return 2
    return report_failure(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
