from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

import uvicorn

from ra2_explorer.api import Services, create_app
from ra2_explorer.background import (
    install_autostart,
    service_status,
    start_background,
    stop_background,
    uninstall_autostart,
)
from ra2_explorer.config import DEFAULT_HOST, DEFAULT_PORT, load_settings
from ra2_explorer.demo import create_demo_installation
from ra2_explorer.discovery import discover_installations
from ra2_explorer.reference_data import sync_known_names
from ra2_explorer.validation import VALIDATED_FORMATS, validate_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ra2exp")
    subcommands = parser.add_subparsers(dest="command", required=True)

    serve = subcommands.add_parser("serve", help="启动本地 API 与浏览器界面")
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--open-browser", action="store_true")

    background = subcommands.add_parser("background", help="管理 Windows 后台与登录自启")
    background.add_argument(
        "action",
        choices=("start", "stop", "status", "install", "uninstall"),
    )
    background.add_argument("--port", type=int, default=DEFAULT_PORT)

    import_command = subcommands.add_parser("import", help="导入并扫描 RA2 资源目录")
    import_command.add_argument("path", type=Path)
    import_command.add_argument("--name")

    scan = subcommands.add_parser("scan", help="重新扫描已注册目录")
    scan.add_argument("source_id")

    demo = subcommands.add_parser("demo", help="创建并导入合成演示资源")
    demo.add_argument("--path", type=Path)

    sync = subcommands.add_parser("sync-names", help="同步固定版本的 RA2 文件名库")
    sync.add_argument("--timeout", type=float, default=30.0)

    subcommands.add_parser("discover", help="发现 Steam、EA App 与旧版合法安装目录")

    verify = subcommands.add_parser("verify", help="按格式抽样验证真实资源目录")
    verify.add_argument("source_id")
    verify.add_argument("--samples-per-format", type=int, default=12)
    verify.add_argument("--format", action="append", choices=VALIDATED_FORMATS)

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
        if args.host not in {DEFAULT_HOST, "localhost", "::1"}:
            raise SystemExit("仅允许监听本机回环地址")
        if not 1 <= args.port <= 65_535:
            raise SystemExit("端口必须在 1 到 65535 之间")
        if args.open_browser:
            webbrowser.open(f"http://{DEFAULT_HOST}:{args.port}")
        uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")
        return 0

    if args.command == "background":
        if not 46_100 <= args.port <= 46_199:
            raise SystemExit("后台服务端口必须位于 46100 到 46199")
        root = Path.cwd().resolve()
        if args.action == "start":
            result = start_background(root, port=args.port)
        elif args.action == "stop":
            result = stop_background(port=args.port)
        elif args.action == "status":
            result = service_status(port=args.port)
        elif args.action == "install":
            result = install_autostart(root, port=args.port)
            result["service"] = start_background(root, port=args.port)
        else:
            result = uninstall_autostart()
        print(json.dumps(result, ensure_ascii=False, indent=2))
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

    if args.command == "discover":
        print(json.dumps(discover_installations(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "verify":
        result = validate_source(
            services.database,
            services.reader,
            args.source_id,
            samples_per_format=max(1, min(args.samples_per_format, 100)),
            formats=tuple(args.format) if args.format else VALIDATED_FORMATS,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1

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
