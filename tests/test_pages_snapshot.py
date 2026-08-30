from __future__ import annotations

import json
from pathlib import Path

import pytest

from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.pages_snapshot import (
    _animation_frame_requests,
    _AnimationVariant,
    _asset_usages,
    _AssetUsage,
    _directory_stats,
    _prune_reused_exports,
    _safe_filename,
    _snapshot_identity,
)


def test_pages_prune_removes_only_stale_reused_exports(tmp_path: Path) -> None:
    expected = tmp_path / "previews" / "assets" / "body" / "auto" / "0.webp"
    stale = tmp_path / "previews" / "assets" / "weapon" / "auto" / "0.webp"
    expected.parent.mkdir(parents=True)
    stale.parent.mkdir(parents=True)
    expected.write_bytes(b"expected")
    stale.write_bytes(b"stale")

    removed = _prune_reused_exports(
        tmp_path,
        asset_ids=set(),
        audio_ids=set(),
        animation_ids={"body"},
        entity_ids=set(),
    )

    assert removed == 1
    assert expected.read_bytes() == b"expected"
    assert not stale.exists()


def test_pages_asset_usages_exclude_incomplete_combat_effects() -> None:
    body_asset = {"id": "body", "format": "shp"}
    weapon_asset = {"id": "weapon", "format": "shp"}
    building_asset = {"id": "active", "format": "shp"}
    entities = [
        {
            "kind": "infantry",
            "components": [],
            "media": [
                {
                    "kind": "animation",
                    "role": "body",
                    "slot": "body_sequence",
                    "samples": [{"asset": body_asset}],
                },
                {
                    "kind": "animation",
                    "role": "weapon",
                    "slot": "primary",
                    "samples": [{"asset": weapon_asset}],
                },
            ],
        },
        {
            "kind": "building",
            "components": [],
            "media": [
                {
                    "kind": "animation",
                    "role": "operation",
                    "slot": "active_anim",
                    "samples": [{"asset": building_asset}],
                },
            ],
        },
    ]

    referenced, usages, _audio_ids = _asset_usages({"items": []}, entities)

    assert set(referenced) == {"body", "active"}
    assert set(usages) == {"body", "active"}


def test_animation_frame_requests_exports_only_configured_direction_ranges() -> None:
    usage = _AssetUsage(
        asset={"id": "demo", "format": "shp"},
        variants=frozenset(
            {
                _AnimationVariant(
                    palette="unit",
                    start_frame=0,
                    frame_count=2,
                    facing_step=2,
                    shadow=True,
                )
            }
        ),
    )

    requests = _animation_frame_requests(usage, 32)

    assert len(requests) == 17
    assert ("unit", 0, None) in requests
    assert ("unit", 0, 16) in requests
    assert ("unit", 15, 31) in requests
    assert ("unit", 16, None) not in requests


def test_snapshot_identity_excludes_local_display_values() -> None:
    source = {
        "id": "source-id",
        "scanned_at": "2026-01-02T03:04:05Z",
        "asset_count": 42,
        "name": "private name",
        "root_path": "E:/private/location",
    }

    changed = {**source, "name": "public name", "root_path": "D:/elsewhere"}

    assert _snapshot_identity(source) == _snapshot_identity(changed)


def test_static_snapshot_rejects_path_like_identifiers() -> None:
    with pytest.raises(Ra2ExplorerError):
        _safe_filename("../outside")


def test_directory_stats_can_exclude_self_describing_manifest(tmp_path) -> None:
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "entities.json").write_text("[]", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"payload": {"bytes": 1}}),
        encoding="utf-8",
    )

    stats = _directory_stats(tmp_path, exclude=frozenset({"manifest.json"}))

    assert stats == {
        "files": 1,
        "bytes": 2,
        "categories": {"catalog": {"files": 1, "bytes": 2}},
    }
