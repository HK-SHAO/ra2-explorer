from __future__ import annotations

import pytest

from scripts.fetch_pages_snapshot import SnapshotDownloadError, _snapshot_url


def test_snapshot_url_uses_pinned_space_revision() -> None:
    lock = {
        "repository": "owner/repository",
        "repository_type": "space",
        "revision": "0123456789abcdef",
        "path": "pages/data.zip",
    }

    assert _snapshot_url("https://hf-mirror.com/", lock) == (
        "https://hf-mirror.com/spaces/owner/repository/resolve/0123456789abcdef/pages/data.zip"
    )


def test_snapshot_url_rejects_untrusted_endpoint() -> None:
    lock = {
        "repository": "owner/repository",
        "repository_type": "space",
        "revision": "main",
        "path": "data.zip",
    }

    with pytest.raises(SnapshotDownloadError, match="不允许"):
        _snapshot_url("https://example.com", lock)
