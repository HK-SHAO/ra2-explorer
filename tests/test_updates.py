from __future__ import annotations

import io
import json
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from ra2_explorer.api import create_app
from ra2_explorer.config import Settings
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.updates import UPDATE_ASSET_NAME, check_for_updates


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
                        "https://github.com/HK-SHAO/ra2-explorer/releases/"
                        f"download/{version}/{UPDATE_ASSET_NAME}"
                    ),
                }
            ],
        }
    ).encode()


def test_update_check_returns_github_release_digest() -> None:
    seen = {}

    def opener(request: object, *, timeout: float) -> _Response:
        seen["request"] = request
        seen["timeout"] = timeout
        return _Response(_release())

    result = check_for_updates(current_version="0.7.0", opener=opener)

    assert result["update_available"] is True
    assert result["latest_version"] == "0.8.0"
    assert result["provider"] == "github"
    assert result["asset"] == {
        "name": UPDATE_ASSET_NAME,
        "size": 1234,
        "digest": f"sha256:{'a' * 64}",
        "download_url": (
            "https://github.com/HK-SHAO/ra2-explorer/releases/"
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

    with pytest.raises(Ra2ExplorerError, match="不属于项目仓库"):
        check_for_updates(opener=opener)


def test_update_check_reports_github_network_failure() -> None:
    def opener(_request: object, *, timeout: float) -> _Response:
        assert timeout == 8.0
        raise URLError("offline")

    with pytest.raises(Ra2ExplorerError, match="无法连接 GitHub"):
        check_for_updates(opener=opener)


def test_update_api_maps_network_failure_to_bad_gateway(
    tmp_path,
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
