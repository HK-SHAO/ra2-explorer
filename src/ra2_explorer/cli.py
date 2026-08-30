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
from ra2_explorer.derived import ARTIFACT_KINDS
from ra2_explorer.discovery import discover_installations
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.package_builder import build_windows_package
from ra2_explorer.reference_data import sync_audio_transcript, sync_known_names
from ra2_explorer.resource_pack import (
    create_resource_pack,
    import_resource_pack,
    list_resource_packs,
)
from ra2_explorer.semantic import ENTITY_KINDS
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

    remove_source = subcommands.add_parser("remove-source", help="从索引移除资源目录")
    remove_source.add_argument("source_id")

    sync = subcommands.add_parser("sync-names", help="同步固定版本的 RA2 文件名库")
    sync.add_argument("--timeout", type=float, default=30.0)

    sync_audio = subcommands.add_parser(
        "sync-audio-text",
        help="同步 CnCNet 社区维护的 RA2/YR 声音转录表",
    )
    sync_audio.add_argument("--timeout", type=float, default=30.0)

    subcommands.add_parser("discover", help="发现 Steam、EA App 与旧版合法安装目录")

    subcommands.add_parser("sources", help="列出已注册资源目录")

    stats = subcommands.add_parser("stats", help="显示资源格式统计")
    stats.add_argument("source_id")

    extract = subcommands.add_parser("extract", help="将资产按需解出到 RA2MD-Ext")
    extract.add_argument("source_id")
    extract.add_argument("--format", action="append")
    extract.add_argument("--limit", type=int, default=500)

    verify = subcommands.add_parser("verify", help="按格式抽样验证真实资源目录")
    verify.add_argument("source_id")
    verify.add_argument("--samples-per-format", type=int, default=12)
    verify.add_argument("--format", action="append", choices=VALIDATED_FORMATS)

    list_command = subcommands.add_parser("list", help="列出索引中的资产")
    list_command.add_argument("--source-id")
    list_command.add_argument("--query")
    list_command.add_argument("--format")
    list_command.add_argument("--limit", type=int, default=50)

    entities = subcommands.add_parser("entities", help="列出规则文件中的游戏单位")
    entities.add_argument("source_id")
    entities.add_argument("--query")
    entities.add_argument("--kind", choices=ENTITY_KINDS)
    availability = entities.add_mutually_exclusive_group()
    availability.add_argument("--renderable", action="store_true")
    availability.add_argument("--missing", action="store_true")
    entities.add_argument("--limit", type=int, default=50)

    entity = subcommands.add_parser("entity", help="检查单位规则和关联资产")
    entity.add_argument("source_id")
    entity.add_argument("entity_id")

    semantic_check = subcommands.add_parser(
        "semantic-check",
        help="检查规则实体、资源关联和武器依赖覆盖",
    )
    semantic_check.add_argument("source_id")
    semantic_check.add_argument("--limit", type=int, default=20)

    package = subcommands.add_parser(
        "package",
        help="构建以本机浏览器为界面的本地 Web 应用",
    )
    package.add_argument("--output", type=Path, default=Path(".outputs") / "RA2 Explorer")
    package.add_argument(
        "--game-dir",
        type=Path,
        help="预先索引本机游戏目录但不复制游戏文件",
    )
    package.add_argument(
        "--include-game-data",
        action="store_true",
        help="把支持的游戏数据复制进发行目录（会显著增大体积）",
    )
    package.add_argument("--sync-reference-data", action="store_true")
    package.add_argument("--overwrite", action="store_true")

    pages = subcommands.add_parser(
        "pages",
        help="构建仅含单位与声音的 GitHub Pages 静态快照",
    )
    pages_commands = pages.add_subparsers(dest="pages_action", required=True)
    pages_export = pages_commands.add_parser("export", help="导出精简静态资源快照")
    pages_export.add_argument("source_id")
    pages_export.add_argument("--output", type=Path)
    pages_export.add_argument("--archive", type=Path)
    pages_export.add_argument("--ffmpeg", type=Path)
    pages_export.add_argument("--audio-bitrate", default="24k")
    pages_export.add_argument("--workers", type=int, default=4)
    pages_export.add_argument("--overwrite", action="store_true")

    cache = subcommands.add_parser("cache", help="统计或清理可再生成的本地缓存")
    cache.add_argument("action", choices=("stats", "prune"))
    cache.add_argument("--kind", action="append", choices=sorted(ARTIFACT_KINDS))

    resource_pack = subcommands.add_parser(
        "resource-pack",
        help="导出、导入或列出不含原始游戏文件的派生资源包",
    )
    resource_pack_commands = resource_pack.add_subparsers(
        dest="resource_pack_action",
        required=True,
    )
    export_pack = resource_pack_commands.add_parser("export", help="导出派生资源包")
    export_pack.add_argument("source_id")
    export_pack.add_argument("--output", type=Path)
    import_pack = resource_pack_commands.add_parser("import", help="导入派生资源包")
    import_pack.add_argument("path", type=Path)
    resource_pack_commands.add_parser("list", help="列出本机派生资源包")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.command == "package":
        try:
            result = build_windows_package(
                args.output,
                game_dir=args.game_dir,
                include_game_data=args.include_game_data,
                sync_reference_data=args.sync_reference_data,
                overwrite=args.overwrite,
            )
        except Ra2ExplorerError as error:
            print(str(error), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    settings = load_settings()
    if args.command == "pages":
        from ra2_explorer.pages_snapshot import build_pages_snapshot

        archive = args.archive
        if archive is None:
            archive_parent = args.output.parent if args.output else settings.derived_root / "pages"
            archive = archive_parent / "RA2-Explorer-Pages-Data.zip"
        try:
            result = build_pages_snapshot(
                settings,
                args.source_id,
                output=args.output,
                archive=archive,
                ffmpeg=args.ffmpeg,
                audio_bitrate=args.audio_bitrate,
                workers=args.workers,
                overwrite=args.overwrite,
            )
        except Ra2ExplorerError as error:
            print(str(error), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    services = Services(settings)

    if args.command == "serve":
        if not settings.hosted and args.host not in {DEFAULT_HOST, "localhost", "::1"}:
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

    if args.command == "remove-source":
        source = services.database.delete_source(args.source_id)
        print(json.dumps(source, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync-names":
        manifest = sync_known_names(settings.known_names_path, timeout=args.timeout)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync-audio-text":
        manifest = sync_audio_transcript(
            settings.audio_transcript_path,
            timeout=args.timeout,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "discover":
        print(json.dumps(discover_installations(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "sources":
        for source in services.database.list_sources():
            print(
                f"{source['id']}  {source['state']:<17}  "
                f"{source['asset_count']:>6}  {source['name']}"
            )
        return 0

    if args.command == "stats":
        print(
            json.dumps(
                services.database.stats(args.source_id),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "extract":
        page = services.database.list_assets(
            source_id=args.source_id,
            asset_formats=tuple(args.format or ()),
            limit=max(1, min(args.limit, 50_000)),
        )
        extracted_bytes = 0
        for asset in page["items"]:
            _, path = services.reader.materialize(str(asset["id"]))
            data = path.read_bytes()
            extracted_bytes += len(data)
        print(
            json.dumps(
                {
                    "source_id": args.source_id,
                    "extracted": len(page["items"]),
                    "available": page["total"],
                    "bytes": extracted_bytes,
                    "derived_root": str(settings.derived_root),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "cache":
        result = (
            services.derived.stats()
            if args.action == "stats"
            else services.derived.prune(tuple(args.kind or ("extracted",)))
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "resource-pack":
        if args.resource_pack_action == "export":
            result = create_resource_pack(
                services.database,
                services.semantic,
                services.derived,
                args.source_id,
                output=args.output,
            )
        elif args.resource_pack_action == "import":
            result = import_resource_pack(
                services.database,
                services.derived,
                args.path,
            )
        else:
            result = list_resource_packs(services.derived)
        print(json.dumps(result, ensure_ascii=False, indent=2))
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

    if args.command == "entities":
        renderable = True if args.renderable else False if args.missing else None
        result = services.semantic.list_entities(
            args.source_id,
            query=args.query,
            kind=args.kind,
            renderable=renderable,
            limit=max(1, min(args.limit, 500)),
        )
        for entity in result["items"]:
            renderable = "preview" if entity["renderable"] else "missing"
            print(
                f"{entity['id']:<12}  {entity['kind']:<8}  "
                f"{renderable:<7}  {entity['display_name']}"
            )
        print(f"{len(result['items'])}/{result['total']}")
        return 0

    if args.command == "entity":
        result = services.semantic.get_entity(args.source_id, args.entity_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0


    if args.command == "semantic-check":
        result = services.semantic.diagnostics(
            args.source_id,
            limit=max(1, min(args.limit, 100)),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "ready" else 1
    return 2


__all__ = ["build_parser", "main"]
