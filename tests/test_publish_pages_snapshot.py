from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.publish_pages_snapshot import (
    SnapshotPublishError,
    _asset_url,
    _data_manifest,
    _lock_manifest,
    _snapshot_manifest,
    _validate_tag,
    build_parser,
)


def test_pages_publish_metadata_keeps_snapshot_pinned(tmp_path: Path) -> None:
    archive = tmp_path / "RA2-Explorer-Pages-Data.zip"
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
        repository="Hansimov/ra2-explorer",
        tag="pages-data-0.11.0",
        data=data,
    )

    assert lock["provider"] == "github-release"
    assert lock["tag"] == "pages-data-0.11.0"
    assert lock["snapshot_id"] == "snapshot-1"
    assert lock["units"] == 12
    assert lock["sounds"] == 34
    assert lock["parts"][0]["url"] == _asset_url(  # type: ignore[index]
        "Hansimov/ra2-explorer",
        "pages-data-0.11.0",
        "RA2-Explorer-Pages-Data.zip.part01",
    )


def test_pages_publish_rejects_application_version_tag() -> None:
    with pytest.raises(SnapshotPublishError, match="v 前缀"):
        _validate_tag("v0.11.0")


def test_pages_publish_requires_explicit_data_tag() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["snapshot.zip"])
