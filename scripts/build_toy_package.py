#!/usr/bin/env python3
"""把静态前端与派生快照合并压缩为可发布到 Toy 的单文件 ZIP。

用法（前置：`ra2exp pages export` 与 `npm run build:pages` 已完成）：

  python scripts/build_toy_package.py --snapshot .outputs/toy/pages-data-final.zip
  python scripts/build_toy_package.py --snapshot … --serve   # 打包后本地预览
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = ROOT / "frontend" / "dist-pages"
DEFAULT_OUTPUT = ROOT / ".outputs" / "toy.zip"
DEFAULT_MOVIES_MANIFEST = ROOT / ".outputs" / "ra2-movies" / "movies.json"


def stage_snapshot(archive: Path) -> None:
    """把快照 ZIP 解包到包内 data 目录（整目录替换）。"""
    data = PACKAGE_ROOT / "data"
    if data.is_dir():
        shutil.rmtree(data)
    data.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.namelist():
            if member.endswith("/"):
                continue
            target = data / member
            if not target.resolve().is_relative_to(data.resolve()):
                raise RuntimeError(f"快照内出现非法路径：{member}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))


def stage_movies_manifest(manifest: Path, bvid: str) -> None:
    """把影片引用清单放进包内数据目录，bvid 留空时前端显示占位。"""
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if bvid:
        payload["bvid"] = bvid
    target = PACKAGE_ROOT / "data" / "movies.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def build_package(output: Path, *, overwrite: bool) -> dict[str, object]:
    root = PACKAGE_ROOT
    if not (root / "index.html").is_file() or not (root / "data" / "manifest.json").is_file():
        raise RuntimeError(
            "包根缺少 index.html 或 data/manifest.json：请先运行 "
            "`ra2exp pages export`、`ra2exp movies build` 与 `npm run build:pages`"
        )
    destination = output.resolve()
    if destination.exists() and not overwrite:
        raise RuntimeError(f"输出已存在：{destination}；如需替换请添加 --overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    temporary = destination.parent / f".{destination.name}.building-{os.getpid()}"
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
            strict_timestamps=False,
        ) as bundle:
            for path in files:
                bundle.write(path, path.relative_to(root).as_posix())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(destination), "files": len(files), "bytes": destination.stat().st_size}


def serve(port: int) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(PACKAGE_ROOT))
    print(f"本地预览：http://127.0.0.1:{port}/（Ctrl+C 停止）", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 Toy 静态网页包")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--snapshot", type=Path, default=None,
                        help="ra2exp pages export 生成的快照 ZIP；解包进包内 data 目录")
    parser.add_argument("--movies-manifest", type=Path, default=DEFAULT_MOVIES_MANIFEST,
                        help="过场影片 BV 引用清单；不存在时跳过")
    parser.add_argument("--bvid", default="BV1cxt66dEDM", help="成片的 B 站 BV 号，写入引用清单")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--serve", nargs="?", const=8080, type=int, metavar="PORT",
                        help="打包完成后在本机启动静态预览")
    args = parser.parse_args()
    try:
        if args.snapshot:
            if not args.snapshot.is_file():
                raise RuntimeError(f"快照 ZIP 不存在：{args.snapshot}")
            stage_snapshot(args.snapshot)
        elif (PACKAGE_ROOT / "data").is_dir() and not (
            PACKAGE_ROOT / "data" / "manifest.json"
        ).is_file():
            raise RuntimeError("包内 data 目录缺少 manifest.json：请用 --snapshot 提供快照 ZIP")
        if args.movies_manifest.is_file():
            stage_movies_manifest(args.movies_manifest, args.bvid.strip())
        result = build_package(args.output, overwrite=args.overwrite)
    except (OSError, RuntimeError) as error:
        print(f"toy package build failed: {error}", file=sys.stderr)
        return 1
    print(
        f"toy.zip 就绪：{result['path']}\n"
        f"  {result['files']:,} 个文件，{int(result['bytes']) / 1e6:.1f} MB"
    )
    if args.serve:
        serve(args.serve)
    return 0


if __name__ == "__main__":
    sys.exit(main())
