from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import URLError

from fastapi.testclient import TestClient

from ra2_explorer.api import create_app
from ra2_explorer.config import Settings
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.updates import (
    DEFAULT_HF_ENDPOINT,
    UPDATE_ASSET_NAME,
    check_for_updates,
    load_public_update_channel,
)


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _release(version: str = "v0.8.0") -> bytes:
    return json.dumps(
        {
            "tag_name": version,
            "published_at": "2026-08-30T12:00:00Z",
            "body": "Faster previews",
            "assets": [
                {
                    "name": UPDATE_ASSET_NAME,
                    "size": 1234,
                    "digest": f"sha256:{'a' * 64}",
                    "browser_download_url": (
                        "https://github.com/Hansimov/ra2-explorer/releases/"
                        f"download/{version}/{UPDATE_ASSET_NAME}"
                    ),
                }
            ],
        }
    ).encode()


def _hf_manifest(version: str = "0.8.0") -> bytes:
    return json.dumps(
        {
            "schema": 1,
            "channel": "stable",
            "version": version,
            "published_at": "2026-08-30T12:00:00Z",
            "notes": "Faster previews",
            "asset": {
                "name": UPDATE_ASSET_NAME,
                "size": 1234,
                "digest": f"sha256:{'a' * 64}",
                "path": f"releases/v{version}/{UPDATE_ASSET_NAME}",
            },
        }
    ).encode()


def test_hugging_face_mirror_is_primary_update_source() -> None:
    seen = {}

    def opener(request: object, *, timeout: float) -> _Response:
        seen["url"] = request.full_url  # type: ignore[attr-defined]
        seen["timeout"] = timeout
        return _Response(_hf_manifest())

    result = check_for_updates(
        current_version="0.7.0",
        opener=opener,
        hf_repository="example/ra2-explorer",
    )

    assert result["provider"] == "huggingface"
    assert result["update_available"] is True
    assert result["asset"] == {
        "name": UPDATE_ASSET_NAME,
        "size": 1234,
        "digest": f"sha256:{'a' * 64}",
        "download_url": (
            f"{DEFAULT_HF_ENDPOINT}/spaces/example/ra2-explorer/resolve/main/"
            f"releases/v0.8.0/{UPDATE_ASSET_NAME}"
        ),
    }
    assert seen["url"] == (
        f"{DEFAULT_HF_ENDPOINT}/spaces/example/ra2-explorer/resolve/main/"
        "releases/latest.json"
    )
    assert seen["timeout"] == 8.0


def test_hugging_face_dataset_update_channel_uses_dataset_path(tmp_path: Path) -> None:
    (tmp_path / "update-channel.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "hf_space_repo": "example/ra2-explorer-releases",
                "hf_repo_type": "dataset",
            }
        ),
        encoding="utf-8",
    )
    channel = load_public_update_channel(tmp_path)
    assert channel is not None
    seen = {}

    def opener(request: object, *, timeout: float) -> _Response:
        seen["url"] = request.full_url  # type: ignore[attr-defined]
        return _Response(_hf_manifest())

    result = check_for_updates(
        current_version="0.7.0",
        opener=opener,
        hf_repository=channel["hf_space_repo"],
        hf_repository_type=channel["hf_repo_type"],
    )

    assert result["provider"] == "huggingface"
    assert "/datasets/example/ra2-explorer-releases/resolve/main/" in seen["url"]
    assert "/datasets/example/ra2-explorer-releases/resolve/main/" in result["asset"][
        "download_url"
    ]


def test_update_check_is_explicit_and_returns_release_digest() -> None:
    seen = {}

    def opener(request: object, *, timeout: float) -> _Response:
        seen["request"] = request
        seen["timeout"] = timeout
        return _Response(_release())

    result = check_for_updates(
        current_version="0.7.0",
        opener=opener,
        hf_repository="",
    )

    assert result["update_available"] is True
    assert result["latest_version"] == "0.8.0"
    assert result["provider"] == "github"
    assert result["asset"] == {
        "name": UPDATE_ASSET_NAME,
        "size": 1234,
        "digest": f"sha256:{'a' * 64}",
        "download_url": (
            "https://github.com/Hansimov/ra2-explorer/releases/"
            f"download/v0.8.0/{UPDATE_ASSET_NAME}"
        ),
    }
    assert seen["timeout"] == 8.0


def test_update_check_rejects_foreign_download_url() -> None:
    payload = json.loads(_release())
    payload["assets"][0]["browser_download_url"] = "https://example.com/update.zip"

    def opener(_request: object, *, timeout: float) -> _Response:
        assert timeout == 8.0
        return _Response(json.dumps(payload).encode())

    try:
        check_for_updates(opener=opener, hf_repository="")
    except Ra2ExplorerError as error:
        assert "不属于项目仓库" in str(error)
    else:
        raise AssertionError("foreign update URL was accepted")


def test_update_check_falls_back_to_github_when_mirror_is_unavailable() -> None:
    requested: list[str] = []

    def opener(request: object, *, timeout: float) -> _Response:
        assert timeout == 8.0
        url = request.full_url  # type: ignore[attr-defined]
        requested.append(url)
        if url.startswith(DEFAULT_HF_ENDPOINT):
            raise URLError("offline")
        return _Response(_release())

    result = check_for_updates(
        current_version="0.7.0",
        opener=opener,
        hf_repository="example/ra2-explorer",
    )

    assert result["provider"] == "github"
    assert len(requested) == 2


def test_update_channel_file_uses_hf_mirror_by_default(tmp_path: Path) -> None:
    (tmp_path / "update-channel.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "hf_space_repo": "example/ra2-explorer",
            }
        ),
        encoding="utf-8",
    )

    assert load_public_update_channel(tmp_path) == {
        "hf_space_repo": "example/ra2-explorer",
        "hf_endpoint": DEFAULT_HF_ENDPOINT,
        "hf_repo_type": "space",
    }


def test_update_api_maps_network_failure_to_bad_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "index.db",
        frontend_dir=tmp_path / "missing-frontend",
        known_names_path=tmp_path / "runtime" / "known-names.txt",
    )

    def fail() -> dict[str, object]:
        raise Ra2ExplorerError("offline")

    monkeypatch.setattr("ra2_explorer.api.check_for_updates", fail)
    response = TestClient(create_app(settings)).get("/api/updates/latest")

    assert response.status_code == 502
    assert response.json()["detail"] == "offline"
