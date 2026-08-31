from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from ra2_explorer import __version__
from ra2_explorer.config import application_root
from ra2_explorer.errors import Ra2ExplorerError

UPDATE_REPOSITORY = "Hansimov/ra2-explorer"
UPDATE_ASSET_NAME = "RA2-Explorer-Web-x64.zip"
LATEST_RELEASE_API = f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest"
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"
OFFICIAL_HF_ENDPOINT = "https://huggingface.co"
UPDATE_CHANNEL_FILE = "update-channel.json"
MAX_RELEASE_RESPONSE_BYTES = 2 * 1024 * 1024
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_HF_REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
)


class _UpdateNetworkError(Ra2ExplorerError):
    pass


def check_for_updates(
    *,
    current_version: str = __version__,
    timeout: float = 8.0,
    opener: Callable[..., Any] = urlopen,
    hf_repository: str | None = None,
    hf_endpoint: str | None = None,
    hf_repository_type: str | None = None,
) -> dict[str, object]:
    channel = load_public_update_channel()
    repository = (
        str(channel.get("hf_space_repo") or "")
        if hf_repository is None and channel
        else hf_repository or ""
    )
    endpoint = (
        str(channel.get("hf_endpoint") or DEFAULT_HF_ENDPOINT)
        if hf_endpoint is None and channel
        else hf_endpoint or DEFAULT_HF_ENDPOINT
    )
    repository_type = (
        str(channel.get("hf_repo_type") or "space")
        if hf_repository_type is None and hf_repository is None and channel
        else hf_repository_type or "space"
    )
    mirror_error: _UpdateNetworkError | None = None
    if repository:
        try:
            return _check_hugging_face(
                repository,
                endpoint=endpoint,
                repository_type=repository_type,
                current_version=current_version,
                timeout=timeout,
                opener=opener,
            )
        except _UpdateNetworkError as error:
            mirror_error = error
    try:
        return _check_github(
            current_version=current_version,
            timeout=timeout,
            opener=opener,
        )
    except _UpdateNetworkError as error:
        if mirror_error is not None:
            raise Ra2ExplorerError("无法连接 Hugging Face 镜像与 GitHub 检查更新") from error
        raise Ra2ExplorerError(str(error)) from error


def load_public_update_channel(root: Path | None = None) -> dict[str, str] | None:
    environment = {
        "hf_space_repo": os.environ.get("HF_SPACE_RELEASE_REPO", "").strip(),
        "hf_endpoint": os.environ.get("HF_ENDPOINT", "").strip(),
        "hf_repo_type": os.environ.get("HF_RELEASE_REPO_TYPE", "").strip(),
    }
    if environment["hf_space_repo"]:
        return _validated_channel(environment)

    workspace = (root or application_root()).resolve()
    channel_path = workspace / UPDATE_CHANNEL_FILE
    if channel_path.is_file():
        try:
            payload = json.loads(channel_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise Ra2ExplorerError("更新通道配置无法解析") from error
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            raise Ra2ExplorerError("更新通道配置结构无效")
        return _validated_channel(payload)

    local_values = _read_local_public_environment(workspace / ".secrets" / "local.env")
    return _validated_channel(local_values) if local_values.get("hf_space_repo") else None


def _check_hugging_face(
    repository: str,
    *,
    endpoint: str,
    repository_type: str,
    current_version: str,
    timeout: float,
    opener: Callable[..., Any],
) -> dict[str, object]:
    channel = _validated_channel(
        {
            "hf_space_repo": repository,
            "hf_endpoint": endpoint,
            "hf_repo_type": repository_type,
        }
    )
    manifest_url = _hf_file_url(channel, "releases/latest.json")
    payload = _fetch_json(
        manifest_url,
        provider="Hugging Face",
        timeout=timeout,
        opener=opener,
        headers={"User-Agent": f"ra2-explorer/{current_version}"},
    )
    if payload.get("schema") != 1 or payload.get("channel") != "stable":
        raise Ra2ExplorerError("Hugging Face 更新清单结构无效")
    latest_version = str(payload.get("version") or "")
    latest_key = _version_key(latest_version)
    current_key = _version_key(current_version)
    if latest_key is None:
        raise Ra2ExplorerError("Hugging Face 更新清单没有可识别的版本号")
    if current_key is None:
        raise Ra2ExplorerError("当前应用版本号无效")
    tag = f"v{latest_version.removeprefix('v')}"
    asset = _hf_release_asset(payload.get("asset"), channel=channel, tag=tag)
    return {
        "current_version": current_version,
        "latest_version": latest_version.removeprefix("v"),
        "update_available": latest_key > current_key,
        "release_url": (
            f"https://github.com/{UPDATE_REPOSITORY}/releases/tag/{quote(tag, safe='')}"
        ),
        "published_at": payload.get("published_at"),
        "notes": str(payload.get("notes") or "")[:8_000],
        "provider": "huggingface",
        "asset": asset,
    }


def _check_github(
    *,
    current_version: str,
    timeout: float,
    opener: Callable[..., Any],
) -> dict[str, object]:
    payload = _fetch_json(
        LATEST_RELEASE_API,
        provider="GitHub",
        timeout=timeout,
        opener=opener,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ra2-explorer/{current_version}",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )
    tag = str(payload.get("tag_name") or "")
    latest_key = _version_key(tag)
    current_key = _version_key(current_version)
    if latest_key is None:
        raise Ra2ExplorerError("最新 Release 没有可识别的版本号")
    if current_key is None:
        raise Ra2ExplorerError("当前应用版本号无效")

    asset = _github_release_asset(payload.get("assets"))
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
        "provider": "github",
        "asset": asset,
    }


def _fetch_json(
    url: str,
    *,
    provider: str,
    timeout: float,
    opener: Callable[..., Any],
    headers: dict[str, str],
) -> dict[str, object]:
    request = Request(url, headers=headers)
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read(MAX_RELEASE_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise _UpdateNetworkError(f"无法连接 {provider} 检查更新") from error
    if len(raw) > MAX_RELEASE_RESPONSE_BYTES:
        raise Ra2ExplorerError(f"{provider} 更新响应超过安全限制")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Ra2ExplorerError(f"{provider} 更新响应无法解析") from error
    if not isinstance(payload, dict):
        raise Ra2ExplorerError(f"{provider} 更新响应结构无效")
    return payload


def _hf_release_asset(
    value: object,
    *,
    channel: dict[str, str],
    tag: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("name") != UPDATE_ASSET_NAME:
        raise Ra2ExplorerError("Hugging Face 更新清单缺少应用安装包")
    expected_path = f"releases/{tag}/{UPDATE_ASSET_NAME}"
    if value.get("path") != expected_path:
        raise Ra2ExplorerError("Hugging Face 安装包路径无效")
    size = value.get("size")
    if not isinstance(size, int) or size < 0:
        raise Ra2ExplorerError("Hugging Face 安装包大小无效")
    digest = str(value.get("digest") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise Ra2ExplorerError("Hugging Face 安装包摘要无效")
    return {
        "name": UPDATE_ASSET_NAME,
        "size": size,
        "digest": digest,
        "download_url": _hf_file_url(channel, expected_path),
    }


def _github_release_asset(value: object) -> dict[str, object] | None:
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


def _validated_channel(value: dict[str, object]) -> dict[str, str]:
    repository = str(value.get("hf_space_repo") or "").strip()
    if not _HF_REPOSITORY_PATTERN.fullmatch(repository):
        raise Ra2ExplorerError("Hugging Face 更新仓库配置无效")
    endpoint = str(value.get("hf_endpoint") or DEFAULT_HF_ENDPOINT).strip().rstrip("/")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() not in {"hf-mirror.com", "huggingface.co"}
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise Ra2ExplorerError("Hugging Face 更新端点配置无效")
    repository_type = str(value.get("hf_repo_type") or "space").strip().casefold()
    if repository_type not in {"dataset", "space"}:
        raise Ra2ExplorerError("Hugging Face 更新仓库类型无效")
    return {
        "hf_space_repo": repository,
        "hf_endpoint": endpoint,
        "hf_repo_type": repository_type,
    }


def _hf_file_url(channel: dict[str, str], path: str) -> str:
    if path.startswith("/") or ".." in Path(path).parts:
        raise Ra2ExplorerError("Hugging Face 更新文件路径无效")
    repository = quote(channel["hf_space_repo"], safe="/")
    file_path = quote(path, safe="/")
    repository_prefix = "datasets" if channel["hf_repo_type"] == "dataset" else "spaces"
    return f"{channel['hf_endpoint']}/{repository_prefix}/{repository}/resolve/main/{file_path}"


def _read_local_public_environment(path: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if key not in {"HF_ENDPOINT", "HF_RELEASE_REPO_TYPE", "HF_SPACE_RELEASE_REPO"}:
            continue
        parsed_value = raw_value.strip().strip('"').strip("'")
        mapped_key = {
            "HF_ENDPOINT": "hf_endpoint",
            "HF_RELEASE_REPO_TYPE": "hf_repo_type",
            "HF_SPACE_RELEASE_REPO": "hf_space_repo",
        }[key]
        values[mapped_key] = parsed_value
    return values


def _version_key(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    return tuple(int(part) for part in match.groups()) if match else None


__all__ = [
    "DEFAULT_HF_ENDPOINT",
    "LATEST_RELEASE_API",
    "OFFICIAL_HF_ENDPOINT",
    "UPDATE_ASSET_NAME",
    "UPDATE_CHANNEL_FILE",
    "UPDATE_REPOSITORY",
    "check_for_updates",
    "load_public_update_channel",
]
