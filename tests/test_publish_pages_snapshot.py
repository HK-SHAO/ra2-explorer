from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from scripts.publish_pages_snapshot import (
    SnapshotPublishError,
    _configure_transfer_environment,
    _data_manifest,
    _hub_error_detail,
    _lock_manifest,
    _remote_prefix,
    _snapshot_manifest,
)


def test_pages_publish_metadata_keeps_snapshot_pinned(tmp_path: Path) -> None:
    archive = tmp_path / "pages.zip"
    snapshot = {
        "snapshot_id": "snapshot-1",
        "payload": {"bytes": 1234},
        "catalog": {"entities": 12, "audio": 34},
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("./manifest.json", json.dumps(snapshot))

    loaded = _snapshot_manifest(archive)
    data = _data_manifest(archive, loaded)
    lock = _lock_manifest(
        repository="owner/repository",
        repository_type="space",
        revision="abc123",
        remote_path="pages/data.zip",
        data=data,
    )

    assert lock["revision"] == "abc123"
    assert lock["snapshot_id"] == "snapshot-1"
    assert lock["units"] == 12
    assert lock["sounds"] == 34
    assert lock["endpoints"][0] == "https://hf-mirror.com"


def test_pages_publish_rejects_parent_remote_path() -> None:
    with pytest.raises(SnapshotPublishError, match="安全"):
        _remote_prefix("../pages")


def test_pages_publish_uses_bounded_output_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HF_HUB_ENABLE_HF_TRANSFER", "1")
    monkeypatch.setenv("HF_XET_HIGH_PERFORMANCE", "1")
    monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)

    _configure_transfer_environment(platform="nt")

    assert "HF_HUB_ENABLE_HF_TRANSFER" not in os.environ
    assert "HF_XET_HIGH_PERFORMANCE" not in os.environ
    assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"


def test_pages_publish_error_detail_uses_safe_response_metadata() -> None:
    class ExampleError(Exception):
        response = type("Response", (), {"status_code": 503})()
        request_id = "request-123"
        server_message = "temporary failure"

    assert _hub_error_detail(ExampleError()) == (
        "ExampleError · HTTP 503 · request request-123 · temporary failure"
    )
