from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlsplit

GITHUB_HOST = "github.com"
EXPECTED_REPOSITORY = "Hansimov/ra2-explorer"
CHUNK_SIZE = 1024 * 1024
PROGRESS_BYTES = 8 * 1024 * 1024
MAX_PARALLEL_DOWNLOADS = 4
MAX_DOWNLOAD_ATTEMPTS = 4
_PART_PATTERN = re.compile(r"^RA2-Explorer-Pages-Data\.zip\.part\d{2}$")


class SnapshotDownloadError(RuntimeError):
    pass


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _load_lock(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotDownloadError(f"无法读取 Pages 数据锁定清单：{path}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise SnapshotDownloadError("Pages 数据锁定清单版本无效")
    required = {
        "provider",
        "repository",
        "tag",
        "asset",
        "parts",
        "sha256",
        "bytes",
    }
    if required - value.keys():
        raise SnapshotDownloadError("Pages 数据锁定清单缺少必要字段")
    if value["provider"] != "github-release":
        raise SnapshotDownloadError("Pages 数据提供方必须是 GitHub Release")
    _validated_parts(value)
    return value


def _part_url(lock: dict[str, object], part: dict[str, object]) -> str:
    repository = str(lock["repository"])
    if repository != EXPECTED_REPOSITORY:
        raise SnapshotDownloadError("Pages 数据仓库不属于本项目")
    tag = quote(str(lock["tag"]), safe="")
    name = str(part["name"])
    if not _PART_PATTERN.fullmatch(name):
        raise SnapshotDownloadError("Pages 数据分片名称无效")
    expected = (
        f"https://{GITHUB_HOST}/{repository}/releases/download/{tag}/"
        f"{quote(name, safe='')}"
    )
    supplied = str(part["url"])
    parsed = urlsplit(supplied)
    if (
        parsed.scheme != "https"
        or parsed.hostname != GITHUB_HOST
        or parsed.query
        or parsed.fragment
        or supplied != expected
    ):
        raise SnapshotDownloadError("Pages 数据地址不是项目的固定 GitHub Release 资产")
    return expected


def _validated_parts(lock: dict[str, object]) -> list[dict[str, object]]:
    parts = lock["parts"]
    if not isinstance(parts, list) or not parts:
        raise SnapshotDownloadError("Pages 数据锁定清单没有分片")
    validated: list[dict[str, object]] = []
    expected_total = 0
    for index, value in enumerate(parts, start=1):
        if not isinstance(value, dict) or {"name", "bytes", "sha256", "url"} - value.keys():
            raise SnapshotDownloadError("Pages 数据分片结构无效")
        expected_name = f"{lock['asset']}.part{index:02d}"
        if value["name"] != expected_name:
            raise SnapshotDownloadError("Pages 数据分片顺序无效")
        size = value["bytes"]
        digest = str(value["sha256"])
        if not isinstance(size, int) or size <= 0:
            raise SnapshotDownloadError("Pages 数据分片大小无效")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SnapshotDownloadError("Pages 数据分片摘要无效")
        _part_url(lock, value)
        expected_total += size
        validated.append(value)
    if expected_total != lock["bytes"]:
        raise SnapshotDownloadError("Pages 数据分片总大小无效")
    return validated


def _download_once(url: str, partial: Path, expected_bytes: int, label: str) -> None:
    start = partial.stat().st_size if partial.exists() else 0
    if start > expected_bytes:
        partial.unlink()
        start = 0
    headers = {"User-Agent": "ra2-explorer-pages-builder/1"}
    if start:
        headers["Range"] = f"bytes={start}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        resumed = start > 0 and response.status == 206
        if not resumed:
            start = 0
        mode = "ab" if resumed else "wb"
        received = start
        next_progress = ((received // PROGRESS_BYTES) + 1) * PROGRESS_BYTES
        with partial.open(mode) as handle:
            while chunk := response.read(CHUNK_SIZE):
                handle.write(chunk)
                received += len(chunk)
                if received >= next_progress:
                    print(
                        f"[pages] {label} 已下载 {received / 1024 / 1024:.1f} MiB",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_progress += PROGRESS_BYTES


def _fetch_part(
    lock: dict[str, object],
    part: dict[str, object],
    destination: Path,
    index: int,
    total: int,
) -> Path:
    expected_bytes = int(part["bytes"])
    expected_sha256 = str(part["sha256"])
    if (
        destination.is_file()
        and destination.stat().st_size == expected_bytes
        and _hash_file(destination) == expected_sha256
    ):
        return destination
    url = _part_url(lock, part)
    last_error: Exception | None = None
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            _download_once(
                url,
                destination,
                expected_bytes,
                f"分片 {index}/{total}",
            )
            if destination.stat().st_size != expected_bytes:
                raise SnapshotDownloadError(f"Pages 数据分片 {index} 大小不一致")
            if _hash_file(destination) != expected_sha256:
                destination.unlink(missing_ok=True)
                raise SnapshotDownloadError(f"Pages 数据分片 {index} 摘要不一致")
            return destination
        except (OSError, urllib.error.URLError, SnapshotDownloadError) as error:
            last_error = error
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                break
            delay = min(2 ** (attempt - 1), 8)
            print(
                f"[pages] 分片 {index}/{total} 下载失败，{delay} 秒后重试 "
                f"({attempt}/{MAX_DOWNLOAD_ATTEMPTS})",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
    raise SnapshotDownloadError(
        f"Pages 数据分片 {index} 下载失败：{type(last_error).__name__}"
    ) from last_error


def fetch_snapshot(lock_path: Path, output: Path) -> dict[str, object]:
    lock = _load_lock(lock_path)
    expected_bytes = int(lock["bytes"])
    expected_sha256 = str(lock["sha256"]).casefold()
    resolved = output.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if (
        resolved.is_file()
        and resolved.stat().st_size == expected_bytes
        and _hash_file(resolved) == expected_sha256
    ):
        print(f"[pages] 使用已校验的数据包：{resolved}", file=sys.stderr)
        return lock

    parts = _validated_parts(lock)
    part_root = resolved.parent / f".{resolved.name}.parts"
    part_root.mkdir(parents=True, exist_ok=True)
    print(
        f"[pages] 从 GitHub Release 并行下载 {len(parts)} 个固定数据分片",
        file=sys.stderr,
        flush=True,
    )
    try:
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_DOWNLOADS, len(parts))) as pool:
            futures = [
                pool.submit(
                    _fetch_part,
                    lock,
                    part,
                    part_root / str(part["name"]),
                    index,
                    len(parts),
                )
                for index, part in enumerate(parts, start=1)
            ]
            local_parts = [future.result() for future in futures]
    except (OSError, urllib.error.URLError) as error:
        raise SnapshotDownloadError(
            f"GitHub Release 数据不可用：{type(error).__name__}"
        ) from error

    partial = resolved.with_name(f".{resolved.name}.partial")
    with partial.open("wb") as target:
        for local_part in local_parts:
            with local_part.open("rb") as source:
                shutil.copyfileobj(source, target, CHUNK_SIZE)
    if partial.stat().st_size != expected_bytes:
        raise SnapshotDownloadError("合并后的 Pages 数据大小不一致")
    if _hash_file(partial) != expected_sha256:
        partial.unlink(missing_ok=True)
        raise SnapshotDownloadError("合并后的 Pages 数据 SHA-256 不匹配")
    os.replace(partial, resolved)
    for local_part in local_parts:
        local_part.unlink(missing_ok=True)
    part_root.rmdir()
    return lock


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="下载固定版本的 Pages 精简数据快照")
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("packaging/pages-data.json"),
        help="数据锁定清单",
    )
    parser.add_argument("--output", type=Path, required=True, help="ZIP 输出路径")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        lock = fetch_snapshot(args.lock, args.output)
    except SnapshotDownloadError as error:
        print(f"pages snapshot download failed: {error}", file=sys.stderr)
        return 1
    print(
        "pages snapshot download passed "
        f"({lock['snapshot_id']}, {int(lock['bytes']) / 1024 / 1024:.1f} MiB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
