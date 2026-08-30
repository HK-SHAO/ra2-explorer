from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from ra2_explorer.api import create_app
from ra2_explorer.cli import build_parser
from ra2_explorer.config import Settings
from tests.ra2_fixtures import FIXTURE_NAMES, create_fixture_installation


def _settings(root: Path) -> Settings:
    data_dir = root / "runtime"
    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "RA2MD-Ext" / "index" / "library.db",
        frontend_dir=root / "missing-frontend",
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
        derived_dir=data_dir / "RA2MD-Ext",
    )
    settings.prepare()
    settings.known_names_path.write_text("\n".join(FIXTURE_NAMES), encoding="utf-8")
    return settings


def test_resource_pack_reuses_browser_artifacts_without_game_files(tmp_path: Path) -> None:
    original_settings = _settings(tmp_path / "original")
    original_client = TestClient(create_app(original_settings))
    installation = create_fixture_installation(tmp_path / "fixture-installation")
    source_response = original_client.post(
        "/api/sources",
        json={"path": str(installation), "name": "Fixture resources"},
    )
    assert source_response.status_code == 201
    source = source_response.json()
    source_id = source["id"]

    entities = original_client.get(
        "/api/entities", params={"source_id": source_id}
    ).json()
    assert entities["total"] == 2
    for entity_id in ("DemoVehicle", "DemoInfantry"):
        assert original_client.get(
            f"/api/entities/{source_id}/{entity_id}"
        ).status_code == 200
        assert original_client.get(
            f"/api/entities/{source_id}/{entity_id}/preview.png"
        ).status_code == 200
    assert original_client.get(
        f"/api/entities/{source_id}/DemoVehicle/model.json"
    ).status_code == 200

    media_page = original_client.get(
        "/api/media", params={"source_id": source_id, "kind": "voice"}
    ).json()
    audio_id = media_page["items"][0]["asset"]["id"]
    audio = original_client.get(f"/api/assets/{audio_id}/media")
    assert audio.status_code == 200

    exported = original_client.post(
        "/api/resource-packs/export", json={"source_id": source_id}
    )
    assert exported.status_code == 201
    export_result = exported.json()
    assert "path" not in export_result
    assert export_result["artifact_files"] >= 6
    download = original_client.get(export_result["download_url"])
    assert download.status_code == 200

    pack_path = original_settings.derived_root / "packages" / export_result["filename"]
    with zipfile.ZipFile(pack_path) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "index.json" in names
        assert not any("/extracted/" in name for name in names)
        assert not any(
            Path(name).suffix.casefold()
            in {".mix", ".shp", ".vxl", ".hva", ".ini", ".csf", ".pal", ".vpl"}
            for name in names
        )
        index = json.loads(archive.read("index.json"))
        assert "root_path" not in index["source"]

    shutil.rmtree(installation)
    imported_settings = _settings(tmp_path / "imported")
    imported_client = TestClient(create_app(imported_settings))
    imported = imported_client.post(
        "/api/resource-packs/import",
        params={"filename": export_result["filename"]},
        content=download.content,
        headers={"content-type": "application/octet-stream"},
    )
    assert imported.status_code == 201
    imported_result = imported.json()
    assert imported_result["imported"] is True
    assert imported_result["source"]["root_path"] == f"resource-pack://{source_id}"

    imported_entities = imported_client.get(
        "/api/entities", params={"source_id": source_id}
    )
    assert imported_entities.status_code == 200
    assert imported_entities.json()["total"] == 2
    assert imported_client.get(
        f"/api/entities/{source_id}/DemoVehicle"
    ).status_code == 200
    assert imported_client.get(
        f"/api/entities/{source_id}/DemoVehicle/preview.png"
    ).content.startswith(b"\x89PNG")
    assert imported_client.get(
        f"/api/entities/{source_id}/DemoVehicle/model.json"
    ).json()["version"] == 4
    assert imported_client.get(f"/api/assets/{audio_id}/media").content.startswith(b"RIFF")
    assert imported_client.post(f"/api/sources/{source_id}/scan").status_code == 400


def test_resource_pack_rejects_raw_game_payload(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "runtime-owner")
    client = TestClient(create_app(settings))
    installation = create_fixture_installation(tmp_path / "fixture-installation")
    source = client.post(
        "/api/sources", json={"path": str(installation)}
    ).json()
    exported = client.post(
        "/api/resource-packs/export", json={"source_id": source["id"]}
    ).json()
    pack_path = settings.derived_root / "packages" / exported["filename"]
    with zipfile.ZipFile(pack_path, "a") as archive:
        archive.writestr("game/ra2.mix", b"not allowed")

    response = client.post(
        "/api/resource-packs/import",
        params={"filename": pack_path.name},
        content=pack_path.read_bytes(),
    )
    assert response.status_code == 400
    assert "未知文件" in response.json()["detail"]


def test_resource_pack_cli_has_explicit_actions() -> None:
    parser = build_parser()
    exported = parser.parse_args(
        ["resource-pack", "export", "source-id", "--output", "bundle.ra2pack"]
    )
    assert exported.resource_pack_action == "export"
    assert exported.output == Path("bundle.ra2pack")
    assert parser.parse_args(
        ["resource-pack", "import", "bundle.ra2pack"]
    ).resource_pack_action == "import"
    assert parser.parse_args(["resource-pack", "list"]).resource_pack_action == "list"
