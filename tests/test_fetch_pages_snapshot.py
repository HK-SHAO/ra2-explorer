from __future__ import annotations

import pytest

from scripts.fetch_pages_snapshot import (
    SnapshotDownloadError,
    _part_url,
    _validated_parts,
)


def _lock(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repository": "Hansimov/ra2-explorer",
        "tag": "pages-data-0.11.0",
        "asset": "RA2-Explorer-Pages-Data.zip",
        "bytes": 8,
        "parts": [
            {
                "name": "RA2-Explorer-Pages-Data.zip.part01",
                "bytes": 8,
                "sha256": "a" * 64,
                "url": (
                    "https://github.com/Hansimov/ra2-explorer/releases/download/"
                    "pages-data-0.11.0/RA2-Explorer-Pages-Data.zip.part01"
                ),
            }
        ],
    }
    value.update(overrides)
    return value


def test_part_url_uses_pinned_github_release_asset() -> None:
    lock = _lock()
    part = _validated_parts(lock)[0]
    assert _part_url(lock, part) == (
        "https://github.com/Hansimov/ra2-explorer/releases/download/"
        "pages-data-0.11.0/RA2-Explorer-Pages-Data.zip.part01"
    )


def test_part_url_rejects_foreign_repository() -> None:
    lock = _lock(repository="example/repository")
    with pytest.raises(SnapshotDownloadError, match="不属于"):
        _validated_parts(lock)


def test_part_url_rejects_untrusted_address() -> None:
    lock = _lock()
    lock["parts"][0]["url"] = "https://example.com/data.zip"  # type: ignore[index]
    with pytest.raises(SnapshotDownloadError, match="固定 GitHub Release"):
        _validated_parts(lock)


def test_parts_must_cover_locked_archive_size() -> None:
    with pytest.raises(SnapshotDownloadError, match="总大小"):
        _validated_parts(_lock(bytes=9))
