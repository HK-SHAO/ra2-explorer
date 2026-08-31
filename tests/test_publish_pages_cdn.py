from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.publish_pages_cdn import (
    PagesCdnPublishError,
    _content_digest,
    _safe_member_path,
    prepare_package,
)


def _snapshot_archive(path: Path) -> Path:
    files = {
        "ASSET-NOTICE.txt": b"notice",
        "catalog/entities.zh-CN.json": b"{}",
        "catalog/entities.zh-TW.json": b"{}",
        "catalog/media.zh-CN.json": b"{}",
        "catalog/media.zh-TW.json": b"{}",
        "previews/entity-atlases/vehicle/0-r3.webp": b"webp",
        "audio/example.ogg": b"audio",
        "assets/example.json": b"{}",
        "entities/zh-CN/example.json": b"{}",
        "entities/zh-TW/example.json": b"{}",
    }
    categories: dict[str, dict[str, int]] = {}
    for name, content in files.items():
        category = name.split("/", 1)[0]
        current = categories.setdefault(category, {"files": 0, "bytes": 0})
        current["files"] += 1
        current["bytes"] += len(content)
    manifest = {
        "schema_version": 1,
        "snapshot_id": "snapshot-test",
        "edition": "pages-slim",
        "included": ["units", "sounds"],
        "contains_original_game_files": False,
        "source": {"root_path": "pages://source"},
        "payload": {
            "files": len(files),
            "bytes": sum(len(content) for content in files.values()),
            "categories": categories,
        },
        "catalog": {"entities": 1, "audio": 1, "referenced_assets": 1},
        "stats": {
            "total_assets": 1,
            "formats": [{"format": "wav", "count": 1}],
        },
    }
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        for name, content in files.items():
            bundle.writestr(name, content)
    return path


def test_prepare_pages_cdn_package_keeps_only_startup_data(tmp_path: Path) -> None:
    archive = _snapshot_archive(tmp_path / "snapshot.zip")
    staging = tmp_path / "staging"

    lock = prepare_package(
        archive,
        staging,
        package_name="ra2-explorer-pages-data",
        version="1.2.3",
    )

    assert lock["base_url"].endswith("ra2-explorer-pages-data@1.2.3/data")
    assert lock["snapshot_id"] == "snapshot-test"
    assert (staging / "data/catalog/entities.zh-CN.json").is_file()
    assert (staging / "data/previews/entity-atlases/vehicle/0-r3.webp").is_file()
    assert not (staging / "data/audio/example.ogg").exists()
    assert not (staging / "data/assets/example.json").exists()
    package = json.loads((staging / "package.json").read_text(encoding="utf-8"))
    assert package["license"] == "SEE LICENSE IN NOTICE.txt"


def test_pages_cdn_content_digest_is_order_independent() -> None:
    left = [("b", b"2"), ("a", b"1")]
    assert _content_digest(left) == _content_digest(list(reversed(left)))


def test_pages_cdn_rejects_unsafe_member_path() -> None:
    with pytest.raises(PagesCdnPublishError, match="非法路径"):
        _safe_member_path("../token.txt")


def test_pages_cdn_rejects_existing_staging_without_confirmation(tmp_path: Path) -> None:
    archive = _snapshot_archive(tmp_path / "snapshot.zip")
    staging = tmp_path / "staging"
    staging.mkdir()
    with pytest.raises(PagesCdnPublishError, match="--overwrite"):
        prepare_package(
            archive,
            staging,
            package_name="ra2-explorer-pages-data",
            version="1.2.3",
        )
