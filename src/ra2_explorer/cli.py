from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from ra2_explorer.api import Services, create_app
from ra2_explorer.config import load_settings
from ra2_explorer.demo import create_demo_installation
from ra2_explorer.reference_data import sync_known_names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ra2-explorer")
    subcommands = parser.add_subparsers(dest="command", required=True)

    serve = subcommands.add_parser("serve", help="启动本地 API 与浏览器界面")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8742)
    serve.add_argument("--no-browser", action="store_true")

    import_command = subcommands.add_parser("import", help="导入并扫描 RA2 资源目录")
    import_command.add_argument("path", type=Path)
    import_command.add_argument("--name")

    scan = subcommands.add_parser("scan", help="重新扫描已注册目录")
    scan.add_argument("source_id")

    demo = subcommands.add_parser("demo", help="创建并导入合成演示资源")
    demo.add_argument("--path", type=Path)

    sync = subcommands.add_parser("sync-names", help="同步固定版本的 RA2 文件名库")
    sync.add_argument("--timeout", type=float, default=30.0)

    list_command = subcommands.add_parser("list", help="列出索引中的资产")
    list_command.add_argument("--source-id")
    list_command.add_argument("--query")
    list_command.add_argument("--format")
    list_command.add_argument("--limit", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    settings = load_settings()
    services = Services(settings)

    if args.command == "serve":
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            raise SystemExit("第一版仅允许监听本机回环地址")
        if not 1 <= args.port <= 65_535:
            raise SystemExit("端口必须在 1 到 65535 之间")
        url = f"http://127.0.0.1:{args.port}"
        if not args.no_browser:
            timer = threading.Timer(0.8, webbrowser.open, args=(url,))
            timer.daemon = True
            timer.start()
        uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")
        return 0

    if args.command == "import":
        source = services.library.import_source(args.path, args.name)
        print(json.dumps(source, ensure_ascii=False, indent=2))
        return 0

    if args.command == "scan":
        source = services.library.scan(args.source_id)
        print(json.dumps(source, ensure_ascii=False, indent=2))
        return 0

    if args.command == "demo":
        target = args.path or settings.data_dir / "demo-ra2"
        create_demo_installation(target)
        source = services.library.import_source(target, "RA2 Explorer 演示库")
        print(json.dumps(source, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync-names":
        manifest = sync_known_names(settings.known_names_path, timeout=args.timeout)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "list":
        result = services.database.list_assets(
            source_id=args.source_id,
            query=args.query,
            asset_format=args.format,
            limit=max(1, min(args.limit, 500)),
        )
        for asset in result["items"]:
            print(f"{asset['id']}  {asset['format']:<7}  {asset['display_name']}")
        print(f"{len(result['items'])}/{result['total']}")
        return 0
    return 2


__all__ = ["build_parser", "main"]
