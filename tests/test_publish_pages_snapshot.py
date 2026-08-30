from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.publish_pages_snapshot import (
    SnapshotPublishError,
    _data_manifest,
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
