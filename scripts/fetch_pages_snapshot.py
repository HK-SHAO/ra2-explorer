from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlsplit

ALLOWED_ENDPOINT_HOSTS = {"hf-mirror.com", "huggingface.co"}
REPOSITORY_ROUTES = {"space": "spaces", "dataset": "datasets", "model": ""}
CHUNK_SIZE = 1024 * 1024
PROGRESS_BYTES = 8 * 1024 * 1024


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
        "repository",
        "repository_type",
        "revision",
        "path",
        "sha256",
        "bytes",
        "endpoints",
    }
    if required - value.keys():
        raise SnapshotDownloadError("Pages 数据锁定清单缺少必要字段")
    if value["repository_type"] not in REPOSITORY_ROUTES:
        raise SnapshotDownloadError("Pages 数据仓库类型无效")
    return value


def _snapshot_url(endpoint: str, lock: dict[str, object]) -> str:
    normalized_endpoint = endpoint.rstrip("/")
    parsed = urlsplit(normalized_endpoint)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_ENDPOINT_HOSTS:
        raise SnapshotDownloadError(f"不允许的 Pages 数据端点：{parsed.hostname or endpoint}")
    repository_type = str(lock["repository_type"])
    route = REPOSITORY_ROUTES[repository_type]
    prefix = f"/{route}" if route else ""
    repository = quote(str(lock["repository"]), safe="/")
    revision = quote(str(lock["revision"]), safe="")
    remote_path = quote(str(lock["path"]), safe="/")
    return f"{normalized_endpoint}{prefix}/{repository}/resolve/{revision}/{remote_path}"


def _download_once(url: str, partial: Path, expected_bytes: int) -> None:
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
                        f"[pages] 已下载 {received / 1024 / 1024:.1f} / "
                        f"{expected_bytes / 1024 / 1024:.1f} MiB",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_progress += PROGRESS_BYTES


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

    partial = resolved.with_name(f".{resolved.name}.partial")
    errors: list[str] = []
    endpoints = lock["endpoints"]
    if not isinstance(endpoints, list) or not endpoints:
        raise SnapshotDownloadError("Pages 数据锁定清单没有下载端点")
    for endpoint in endpoints:
        try:
            url = _snapshot_url(str(endpoint), lock)
            print(
                f"[pages] 从 {urlsplit(url).hostname} 下载固定数据快照",
                file=sys.stderr,
                flush=True,
            )
            _download_once(url, partial, expected_bytes)
            if partial.stat().st_size != expected_bytes:
                raise SnapshotDownloadError(
                    f"下载大小不一致：{partial.stat().st_size} != {expected_bytes}"
                )
            if _hash_file(partial) != expected_sha256:
                partial.unlink(missing_ok=True)
                raise SnapshotDownloadError("下载数据的 SHA-256 不匹配")
            os.replace(partial, resolved)
            return lock
        except (OSError, SnapshotDownloadError, urllib.error.URLError) as error:
            errors.append(f"{urlsplit(str(endpoint)).hostname}: {type(error).__name__}")
    raise SnapshotDownloadError(f"所有 Pages 数据端点均不可用：{', '.join(errors)}")


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
