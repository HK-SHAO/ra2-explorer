from __future__ import annotations

import hashlib
from urllib.error import URLError

import pytest

import scripts.fetch_pages_snapshot as snapshot_fetcher
from scripts.fetch_pages_snapshot import (
    SnapshotDownloadError,
    _fetch_part,
    _part_url,
    _validated_parts,
)


def _lock(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repository": "HK-SHAO/ra2-explorer",
        "tag": "pages-data-0.11.0",
        "asset": "RA2-Explorer-Pages-Data.zip",
        "bytes": 8,
        "parts": [
            {
                "name": "RA2-Explorer-Pages-Data.zip.part01",
                "bytes": 8,
                "sha256": "a" * 64,
                "url": (
                    "https://github.com/HK-SHAO/ra2-explorer/releases/download/"
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
        "https://github.com/HK-SHAO/ra2-explorer/releases/download/"
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


def test_fetch_part_retries_transient_network_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"snapshot"
    lock = _lock(
        parts=[
            {
                "name": "RA2-Explorer-Pages-Data.zip.part01",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "url": (
                    "https://github.com/HK-SHAO/ra2-explorer/releases/download/"
                    "pages-data-0.11.0/RA2-Explorer-Pages-Data.zip.part01"
                ),
            }
        ],
    )
    calls = 0

    def flaky_download(_url, destination, _expected_bytes, _label) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary")
        destination.write_bytes(payload)

    monkeypatch.setattr(snapshot_fetcher, "_download_once", flaky_download)
    monkeypatch.setattr(snapshot_fetcher.time, "sleep", lambda _delay: None)
    destination = tmp_path / "part01"

    assert _fetch_part(lock, lock["parts"][0], destination, 1, 1) == destination  # type: ignore[index]
    assert calls == 2
