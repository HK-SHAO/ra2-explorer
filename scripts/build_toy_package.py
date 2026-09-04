#!/usr/bin/env python3
"""把静态前端与派生快照合并压缩为可发布到 Toy 的单文件 ZIP。

前置条件：
  1. `ra2exp pages export` 已导出派生快照；
  2. 快照数据已放入 `frontend/dist-pages/data`（根目录有 `data/manifest.json`）；
  3. `npm run build:pages` 已产出 `frontend/dist-pages/index.html`。

用法：
  python scripts/build_toy_package.py --output toy.zip --overwrite
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = ROOT / "frontend" / "dist-pages"
DEFAULT_OUTPUT = ROOT / ".outputs" / "toy.zip"


def build_package(output: Path, *, overwrite: bool) -> dict[str, object]:
    root = PACKAGE_ROOT
    if not (root / "index.html").is_file() or not (root / "data" / "manifest.json").is_file():
        raise RuntimeError(
            "包根缺少 index.html 或 data/manifest.json：请先运行 "
            "`ra2exp pages export` 与 `npm run build:pages`"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 Toy 静态网页包")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        result = build_package(args.output, overwrite=args.overwrite)
    except (OSError, RuntimeError) as error:
        print(f"toy package build failed: {error}", file=sys.stderr)
        return 1
    print(
        f"toy.zip 就绪：{result['path']}\n"
        f"  {result['files']:,} 个文件，{int(result['bytes']) / 1e6:.1f} MB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
