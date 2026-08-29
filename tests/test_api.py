from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from ra2_explorer.api import create_app
from ra2_explorer.config import Settings
from ra2_explorer.semantic import _entity_usage
from tests.ra2_fixtures import FIXTURE_NAMES, create_fixture_installation


def test_fixture_library_is_browsable_and_previewable(tmp_path: Path) -> None:
    data_dir = tmp_path / "runtime"
    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "library.db",
        frontend_dir=tmp_path / "missing-frontend",
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
    )
    settings.prepare()
    settings.known_names_path.write_text("\n".join(FIXTURE_NAMES), encoding="utf-8")
    client = TestClient(create_app(settings))

    installation = create_fixture_installation(tmp_path / "fixture-installation")
    source_response = client.post(
        "/api/sources",
        json={"path": str(installation), "name": "Test fixture"},
    )
    assert source_response.status_code == 201
    source = source_response.json()
    assert source["state"] == "ready"
    assert source["archive_count"] == 2
    assert source["asset_count"] == 15

    assets_response = client.get(
        "/api/assets", params={"source_id": source["id"], "q": "fixture.shp"}
    )
    assert assets_response.status_code == 200
    assets = assets_response.json()
    assert assets["total"] == 1
    sprite = assets["items"][0]

    metadata = client.get(f"/api/assets/{sprite['id']}/shp")
    assert metadata.status_code == 200
    assert metadata.json()["frame_count"] == 6

    preview = client.get(
        f"/api/assets/{sprite['id']}/preview.png",
        params={"frame": 3, "scale": 2},
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content.startswith(b"\x89PNG")

    page = client.get("/api/assets", params={"source_id": source["id"], "limit": 100}).json()
    by_name = {asset["display_name"]: asset for asset in page["items"]}
    filtered = client.get(
        "/api/assets",
        params={"source_id": source["id"], "formats": "vxl,wav"},
    ).json()
    assert {asset["format"] for asset in filtered["items"]} == {"vxl", "wav"}
    largest_first = client.get(
        "/api/assets",
        params={"source_id": source["id"], "sort": "size_desc", "limit": 100},
    ).json()["items"]
    assert [asset["size"] for asset in largest_first] == sorted(
        (asset["size"] for asset in largest_first), reverse=True
    )
    assert client.get(
        "/api/assets", params={"source_id": source["id"], "sort": "unsupported"}
    ).status_code == 422

    vxl = by_name["fixture.vxl"]
    vxl_metadata = client.get(f"/api/assets/{vxl['id']}/metadata")
    assert vxl_metadata.status_code == 200
    assert vxl_metadata.json()["voxel_count"] > 80
    assert client.get(f"/api/assets/{vxl['id']}/preview.png").content.startswith(b"\x89PNG")
    vxl_model = client.get(f"/api/assets/{vxl['id']}/model.json")
    assert vxl_model.status_code == 200
    assert vxl_model.json()["version"] == 4
    assert vxl_model.json()["lighting"] == "westwood_vpl"
    assert vxl_model.json()["voxel_count"] > 80
    assert vxl_model.json()["visible_voxel_count"] <= vxl_model.json()["voxel_count"]
    assert len(vxl_model.json()["voxels"][0]) == 9
    assert vxl_model.json()["voxels"][0][-2:] == [20, 4]

    animation = by_name["fixture.hva"]
    animated_model = client.get(
        f"/api/assets/{animation['id']}/model.json",
        params={"frame": 3},
    )
    assert animated_model.status_code == 200
    assert animated_model.json()["frame"] == 3
    assert animated_model.json()["frame_count"] == 4
    animated_preview = client.get(
        f"/api/assets/{animation['id']}/preview.png",
        params={"frame": 3, "player_color": "blue"},
    )
    assert animated_preview.status_code == 200
    assert animated_preview.content.startswith(b"\x89PNG")

    terrain = by_name["fixture.tem"]
    terrain_preview = client.get(f"/api/assets/{terrain['id']}/preview.png")
    assert terrain_preview.status_code == 200
    assert terrain_preview.content.startswith(b"\x89PNG")

    game_map = by_name["fixture.map"]
    map_metadata = client.get(f"/api/assets/{game_map['id']}/metadata")
    assert map_metadata.status_code == 200
    assert map_metadata.json()["width"] == 60
    assert map_metadata.json()["height"] == 42
    assert map_metadata.json()["object_counts"]["structure"] == 1
    assert client.get(f"/api/assets/{game_map['id']}/preview.png").content.startswith(
        b"\x89PNG"
    )

    strings = by_name["fixture.csf"]
    text = client.get(f"/api/assets/{strings['id']}/text", params={"q": "ready"})
    assert text.status_code == 200
    assert "Asset pipeline ready" in text.json()["text"]

    sound = by_name["fixture.wav"]
    media = client.get(f"/api/assets/{sound['id']}/media")
    assert media.status_code == 200
    assert media.headers["content-type"] == "audio/wav"
    assert media.content.startswith(b"RIFF")

    entities = client.get("/api/entities", params={"source_id": source["id"]})
    assert entities.status_code == 200
    entity_page = entities.json()
    assert entity_page["total"] == 2
    entity_summaries = {item["id"]: item for item in entity_page["items"]}
    assert entity_summaries["DemoVehicle"]["display_name"] == "Generated test vehicle"
    assert entity_summaries["DemoVehicle"]["renderable"] is True
    assert entity_summaries["DemoVehicle"]["body_format"] == "vxl"
    assert entity_summaries["DemoVehicle"]["usage"] == "buildable"
    assert entity_summaries["DemoInfantry"]["usage"] == "buildable"
    assert entity_summaries["DemoInfantry"]["display_name"] == "测试步兵"
    assert entity_summaries["DemoVehicle"]["media_count"] > 0
    assert "voice" in entity_summaries["DemoVehicle"]["media_kinds"]
    assert entity_summaries["DemoVehicle"]["countries"] == ["Americans", "Russians"]
    assert entity_summaries["DemoVehicle"]["sides"] == ["GDI", "Nod"]
    assert {item["display_name"] for item in entity_page["countries"]} == {
        "United States",
        "Russia",
    }
    assert entity_page["usages"] == [{"usage": "buildable", "count": 2}]
    allied_vehicles = client.get(
        "/api/entities",
        params={
            "source_id": source["id"],
            "kind": "vehicle",
            "side": "GDI",
            "renderable": "true",
        },
    )
    assert allied_vehicles.status_code == 200
    assert allied_vehicles.json()["total"] == 1
    assert allied_vehicles.json()["items"][0]["id"] == "DemoVehicle"
    empty_side = client.get(
        "/api/entities",
        params={"source_id": source["id"], "kind": "building", "side": "GDI"},
    )
    assert empty_side.status_code == 200
    assert empty_side.json()["total"] == 0
    buildable_infantry = client.get(
        "/api/entities",
        params={
            "source_id": source["id"],
            "kind": "infantry",
            "usage": "buildable",
        },
    )
    assert buildable_infantry.status_code == 200
    assert [item["id"] for item in buildable_infantry.json()["items"]] == [
        "DemoInfantry"
    ]
    assert client.get(
        "/api/entities",
        params={"source_id": source["id"], "usage": "invalid"},
    ).status_code == 422
    simplified_name_search = client.get(
        "/api/entities",
        params={"source_id": source["id"], "q": "测试步兵"},
    )
    assert [item["id"] for item in simplified_name_search.json()["items"]] == [
        "DemoInfantry"
    ]
    traditional_name_search = client.get(
        "/api/entities",
        params={"source_id": source["id"], "q": "測試步兵", "language": "zh-TW"},
    )
    assert traditional_name_search.json()["items"][0]["display_name"] == "測試步兵"
    assert client.get(
        "/api/entities",
        params={"source_id": source["id"], "language": "english"},
    ).status_code == 422

    semantic_media = client.get(
        "/api/media",
        params={"source_id": source["id"], "kind": "voice"},
    )
    assert semantic_media.status_code == 200
    media_items = semantic_media.json()["items"]
    assert len(media_items) == 1
    assert media_items[0]["asset"]["display_name"] == "fixture.wav"
    assert media_items[0]["description"] == "Ready for the test."
    assert media_items[0]["groups"] == ["unit_voice"]
    assert media_items[0]["original_texts"] == ["Ready for the test."]
    assert media_items[0]["localized_texts"] == []
    assert {item["event_type"] for item in semantic_media.json()["event_types"]} >= {
        "select",
        "sound_event",
    }
    selected_media = client.get(
        "/api/media",
        params={"source_id": source["id"], "kind": "voice", "event_type": "select"},
    )
    assert selected_media.status_code == 200
    assert selected_media.json()["total"] == 1
    assert client.get(
        "/api/media",
        params={"source_id": source["id"], "kind": "voice", "event_type": "move"},
    ).json()["total"] == 0
    assert client.get(
        "/api/media",
        params={"source_id": source["id"], "sort": "random"},
    ).status_code == 422

    entity = client.get(f"/api/entities/{source['id']}/DemoVehicle")
    assert entity.status_code == 200
    entity_body = entity.json()
    components = {item["role"]: item for item in entity_body["components"]}
    assert components["body"]["asset"]["display_name"] == "fixture.vxl"
    assert components["body_hva"]["asset"]["display_name"] == "fixture.hva"
    assert components["cameo"]["asset"]["display_name"] == "fixture.shp"
    assert entity_body["preview"]["frame_count"] == 4
    assert entity_body["preview"]["supports_facing"] is True
    assert entity_body["preview"]["supports_player_color"] is True
    dependencies = {(item["kind"], item["id"]): item for item in entity_body["dependencies"]}
    assert len(entity_body["dependencies"]) == 3
    assert dependencies[("weapon", "DemoCannon")]["properties"]["damage"] == "75"
    assert dependencies[("projectile", "DemoShell")]["resolved"] is True
    assert dependencies[("warhead", "DemoWarhead")]["resolved"] is True
    select_voice = next(item for item in entity_body["media"] if item["slot"] == "select")
    assert select_voice["event"] == "FixtureSelect"
    assert select_voice["samples"][0]["text"] == "Ready for the test."
    assert select_voice["samples"][0]["original_text"] == "Ready for the test."
    assert select_voice["samples"][0]["localized_text"] is None
    assert select_voice["samples"][0]["text_label"] == "VOX:fixture_event"
    assert select_voice["samples"][0]["asset"]["display_name"] == "fixture.wav"
    assert select_voice["samples"][0]["weight"] == 2
    assert len(select_voice["samples"]) == 1

    associations = client.get(f"/api/assets/{sound['id']}/associations")
    assert associations.status_code == 200
    association_items = associations.json()["items"]
    assert any(
        item["entity"]["id"] == "DemoVehicle"
        and item["text"] == "Ready for the test."
        and item["original_text"] == "Ready for the test."
        and item["localized_text"] is None
        for item in association_items
        if item["entity"]
    )

    infantry = client.get(f"/api/entities/{source['id']}/DemoInfantry")
    assert infantry.status_code == 200
    infantry_preview = infantry.json()["preview"]
    assert infantry_preview["frame_count"] == 3
    assert infantry_preview["source_frame_count"] == 6
    assert infantry_preview["frame_indices"] == [0, 2, 4]
    assert infantry_preview["supports_facing"] is True
    walk_animation = next(
        item
        for item in infantry.json()["media"]
        if item["kind"] == "animation" and item["event"] == "walk"
    )
    assert walk_animation["slot"] == "body_sequence"
    assert walk_animation["samples"][0]["animation"] == {
        "start_frame": 0,
        "frame_count": 2,
        "facing_step": 1,
        "rate_ms": None,
        "loop_start": None,
        "loop_end": None,
        "loop_count": None,
        "direction": None,
    }
    infantry_image = client.get(
        f"/api/entities/{source['id']}/DemoInfantry/preview.png",
        params={"frame": 2},
    )
    assert infantry_image.status_code == 200
    assert infantry_image.content.startswith(b"\x89PNG")
    infantry_thumbnail = client.get(
        f"/api/entities/{source['id']}/DemoInfantry/preview.png",
        params={"frame": 2, "thumbnail": "true"},
    )
    with Image.open(io.BytesIO(infantry_image.content)) as full_preview, Image.open(
        io.BytesIO(infantry_thumbnail.content)
    ) as thumbnail:
        assert thumbnail.width < full_preview.width
        assert thumbnail.height < full_preview.height

    entity_preview = client.get(
        f"/api/entities/{source['id']}/DemoVehicle/preview.png",
        params={"frame": 3, "facing": 2, "player_color": "blue"},
    )
    assert entity_preview.status_code == 200
    assert entity_preview.content.startswith(b"\x89PNG")

    entity_model = client.get(
        f"/api/entities/{source['id']}/DemoVehicle/model.json",
        params={"frame": 3, "player_color": "blue"},
    )
    assert entity_model.status_code == 200
    assert entity_model.json()["frame"] == 3
    assert entity_model.json()["frame_count"] == 4
    assert entity_model.json()["part_count"] == 1
    assert entity_model.headers["cache-control"] == "private, max-age=3600"

    diagnostics = client.get(f"/api/semantic/{source['id']}/diagnostics")
    assert diagnostics.status_code == 200
    diagnostic_body = diagnostics.json()
    assert diagnostic_body["status"] == "ready"
    assert diagnostic_body["entity_count"] == 2
    assert diagnostic_body["renderable_percent"] == 100.0
    assert diagnostic_body["unresolved_dependency_count"] == 0

    colors = client.get("/api/player-colors")
    assert colors.status_code == 200
    assert {item["id"] for item in colors.json()} >= {"red", "blue", "green"}
    invalid_color = client.get(
        f"/api/entities/{source['id']}/DemoVehicle/preview.png",
        params={"player_color": "transparent"},
    )
    assert invalid_color.status_code == 422

    artifact_kinds = {
        path.parent.name
        for path in settings.derived_root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    assert settings.derived_root.joinpath("manifest.json").is_file()
    assert artifact_kinds >= {"audio", "extracted", "metadata", "models", "previews"}

    removed = client.delete(f"/api/sources/{source['id']}")
    assert removed.status_code == 200
    assert client.get("/api/sources").json() == []


def test_api_rejects_untrusted_host(tmp_path: Path) -> None:
    data_dir = tmp_path / "runtime"
    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "library.db",
        frontend_dir=tmp_path / "missing-frontend",
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
    )
    settings.prepare()
    client = TestClient(create_app(settings), base_url="http://outside.example")

    response = client.get("/api/health")

    assert response.status_code == 400


def test_retail_class_markers_do_not_fail_a_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "retail"
    source_dir.mkdir()
    (source_dir / "thememd.mix").write_bytes(b"CLASS")
    data_dir = tmp_path / "runtime"
    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "library.db",
        frontend_dir=tmp_path / "missing-frontend",
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
    )
    settings.prepare()
    client = TestClient(create_app(settings))

    response = client.post("/api/sources", json={"path": str(source_dir)})

    assert response.status_code == 201
    assert response.json()["state"] == "ready"
    assert response.json()["archive_count"] == 1


def test_scan_excludes_the_derived_workspace(tmp_path: Path) -> None:
    source_dir = tmp_path / "game-root"
    source_dir.mkdir()
    (source_dir / "rules.ini").write_text("[General]\n", encoding="ascii")
    data_dir = tmp_path / "runtime"
    derived_dir = source_dir / "RA2MD-Ext"
    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "library.db",
        frontend_dir=tmp_path / "missing-frontend",
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
        derived_dir=derived_dir,
    )
    settings.prepare()
    (derived_dir / "should-not-load.ini").write_text("[Derived]\n", encoding="ascii")
    client = TestClient(create_app(settings))

    source = client.post("/api/sources", json={"path": str(source_dir)}).json()
    assets = client.get("/api/assets", params={"source_id": source["id"]}).json()

    assert [item["display_name"] for item in assets["items"]] == ["rules.ini"]


def test_serve_defaults_do_not_open_external_programs() -> None:
    from ra2_explorer.cli import build_parser
    from ra2_explorer.config import DEFAULT_PORT

    args = build_parser().parse_args(["serve"])

    assert args.port == DEFAULT_PORT == 46_120
    assert args.open_browser is False


def test_canonical_cli_name_is_ra2exp() -> None:
    from ra2_explorer.cli import build_parser

    assert build_parser().prog == "ra2exp"


def test_entity_usage_distinguishes_player_structures_and_scene_objects() -> None:
    assert _entity_usage(
        "building",
        {
            "owner": "British,Americans",
            "cost": "3000",
            "techlevel": "-1",
            "constructionyard": "yes",
            "undeploysinto": "AMCV",
            "capturable": "yes",
        },
    ) == "buildable"
    assert _entity_usage(
        "building",
        {"capturable": "yes", "needsengineer": "yes"},
    ) == "tech"
    assert _entity_usage(
        "building",
        {"civilian": "yes", "nominal": "yes"},
    ) == "civilian"
    assert _entity_usage("building", {"owner": "Americans", "cost": "2800"}) == "scenario"
    assert _entity_usage(
        "infantry",
        {"owner": "Americans", "cost": "1000", "techlevel": "8", "buildlimit": "1"},
    ) == "hero"
