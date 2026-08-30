from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from ra2_explorer import __version__
from ra2_explorer.errors import Ra2ExplorerError

UPDATE_REPOSITORY = "Hansimov/ra2-explorer"
UPDATE_ASSET_NAME = "RA2-Explorer-Web-x64.zip"
LATEST_RELEASE_API = f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest"
MAX_RELEASE_RESPONSE_BYTES = 2 * 1024 * 1024
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def check_for_updates(
    *,
    current_version: str = __version__,
    timeout: float = 8.0,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    request = Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ra2-explorer/{current_version}",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read(MAX_RELEASE_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise Ra2ExplorerError("无法连接 GitHub 检查更新，请稍后重试") from error
    if len(raw) > MAX_RELEASE_RESPONSE_BYTES:
        raise Ra2ExplorerError("GitHub 更新响应超过安全限制")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Ra2ExplorerError("GitHub 更新响应无法解析") from error
    if not isinstance(payload, dict):
        raise Ra2ExplorerError("GitHub 更新响应结构无效")

    tag = str(payload.get("tag_name") or "")
    latest_key = _version_key(tag)
    current_key = _version_key(current_version)
    if latest_key is None:
        raise Ra2ExplorerError("最新 Release 没有可识别的版本号")
    if current_key is None:
        raise Ra2ExplorerError("当前应用版本号无效")

    asset = _release_asset(payload.get("assets"))
    release_url = (
        f"https://github.com/{UPDATE_REPOSITORY}/releases/tag/"
        f"{quote(tag, safe='')}"
    )
    return {
        "current_version": current_version,
        "latest_version": tag.removeprefix("v"),
        "update_available": latest_key > current_key,
        "release_url": release_url,
        "published_at": payload.get("published_at"),
        "notes": str(payload.get("body") or "")[:8_000],
        "asset": asset,
    }


def _release_asset(value: object) -> dict[str, object] | None:
    if not isinstance(value, list):
        return None
    for candidate in value:
        if not isinstance(candidate, dict) or candidate.get("name") != UPDATE_ASSET_NAME:
            continue
        download_url = str(candidate.get("browser_download_url") or "")
        parsed = urlparse(download_url)
        expected_prefix = f"/{UPDATE_REPOSITORY}/releases/download/"
        if (
            parsed.scheme != "https"
            or parsed.netloc.casefold() != "github.com"
            or not parsed.path.startswith(expected_prefix)
        ):
            raise Ra2ExplorerError("Release 下载地址不属于项目仓库")
        size = candidate.get("size")
        if not isinstance(size, int) or size < 0:
            raise Ra2ExplorerError("Release 资产大小无效")
        digest = candidate.get("digest")
        if digest is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", str(digest)):
            raise Ra2ExplorerError("Release 资产摘要无效")
        return {
            "name": UPDATE_ASSET_NAME,
            "size": size,
            "digest": digest,
            "download_url": download_url,
        }
    return None


def _version_key(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    return tuple(int(part) for part in match.groups()) if match else None


__all__ = [
    "LATEST_RELEASE_API",
    "UPDATE_ASSET_NAME",
    "UPDATE_REPOSITORY",
    "check_for_updates",
]
