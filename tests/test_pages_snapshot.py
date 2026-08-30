from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.pages_snapshot import (
    _animation_frame_requests,
    _AnimationVariant,
    _asset_usages,
    _AssetUsage,
    _composite_entity_preview_layers,
    _directory_stats,
    _prune_reused_exports,
    _safe_filename,
    _snapshot_identity,
    archive_pages_snapshot,
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
                    frame_step=1,
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


def test_animation_frame_requests_support_interleaved_unit_actions() -> None:
    usage = _AssetUsage(
        asset={"id": "drone", "format": "shp"},
        variants=frozenset(
            {
                _AnimationVariant(
                    palette="unit",
                    start_frame=8,
                    frame_count=2,
                    facing_step=1,
                    frame_step=8,
                    shadow=False,
                )
            }
        ),
    )
    paired_shadows = {frame: frame + 32 for frame in range(8, 24)}

    requests = _animation_frame_requests(usage, 64, paired_shadows)

    assert ("unit", 8, 40) in requests
    assert ("unit", 16, 48) in requests
    assert ("unit", 9, 41) in requests
    assert ("unit", 17, 49) in requests
    assert ("unit", 24, 56) not in requests
    assert ("unit", 8, None) in requests


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


def test_pages_archive_is_complete_and_atomically_replaceable(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    (snapshot / "catalog").mkdir(parents=True)
    (snapshot / "manifest.json").write_text('{"schema_version":1}', encoding="utf-8")
    (snapshot / "catalog" / "entities.json").write_text("[]", encoding="utf-8")
    archive = tmp_path / "pages.zip"

    result = archive_pages_snapshot(snapshot, archive)

    assert result["files"] == 2
    assert result["bytes"] == archive.stat().st_size
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == ["catalog/entities.json", "manifest.json"]
    with pytest.raises(Ra2ExplorerError):
        archive_pages_snapshot(snapshot, archive)
    archive_pages_snapshot(snapshot, archive, overwrite=True)
    assert not list(tmp_path.glob(".pages.zip.building-*"))


def test_pages_building_preview_focus_includes_every_visible_main_layer() -> None:
    base = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    base.paste((255, 255, 255, 255), (40, 40, 60, 60))
    operation = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    operation.paste((255, 0, 0, 255), (150, 40, 190, 60))

    composite, focus = _composite_entity_preview_layers(
        base,
        (40, 40, 60, 60),
        [],
        [operation],
    )

    assert composite.size == (200, 100)
    assert focus == (90, 40, 190, 60)
