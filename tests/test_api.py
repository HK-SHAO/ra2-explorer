from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ra2_explorer.api import create_app
from ra2_explorer.config import Settings
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
    assert source["asset_count"] == 11

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

    vxl = by_name["fixture.vxl"]
    vxl_metadata = client.get(f"/api/assets/{vxl['id']}/metadata")
    assert vxl_metadata.status_code == 200
    assert vxl_metadata.json()["voxel_count"] > 80
    assert client.get(f"/api/assets/{vxl['id']}/preview.png").content.startswith(b"\x89PNG")
    vxl_model = client.get(f"/api/assets/{vxl['id']}/model.json")
    assert vxl_model.status_code == 200
    assert vxl_model.json()["voxel_count"] > 80
    assert len(vxl_model.json()["voxels"][0]) == 7

    terrain = by_name["fixture.tem"]
    terrain_preview = client.get(f"/api/assets/{terrain['id']}/preview.png")
    assert terrain_preview.status_code == 200
    assert terrain_preview.content.startswith(b"\x89PNG")

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
    assert entity_page["total"] == 1
    assert entity_page["items"][0]["id"] == "DemoVehicle"
    assert entity_page["items"][0]["display_name"] == "Generated test vehicle"
    assert entity_page["items"][0]["renderable"] is True

    entity = client.get(f"/api/entities/{source['id']}/DemoVehicle")
    assert entity.status_code == 200
    entity_body = entity.json()
    components = {item["role"]: item for item in entity_body["components"]}
    assert components["body"]["asset"]["display_name"] == "fixture.vxl"
    assert components["body_hva"]["asset"]["display_name"] == "fixture.hva"
    assert components["cameo"]["asset"]["display_name"] == "fixture.shp"
    assert entity_body["preview"]["frame_count"] == 4
    assert entity_body["preview"]["supports_facing"] is True
    dependencies = {(item["kind"], item["id"]): item for item in entity_body["dependencies"]}
    assert len(entity_body["dependencies"]) == 3
    assert dependencies[("weapon", "DemoCannon")]["properties"]["damage"] == "75"
    assert dependencies[("projectile", "DemoShell")]["resolved"] is True
    assert dependencies[("warhead", "DemoWarhead")]["resolved"] is True

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

    diagnostics = client.get(f"/api/semantic/{source['id']}/diagnostics")
    assert diagnostics.status_code == 200
    diagnostic_body = diagnostics.json()
    assert diagnostic_body["status"] == "ready"
    assert diagnostic_body["entity_count"] == 1
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
