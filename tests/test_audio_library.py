from __future__ import annotations

import struct
from pathlib import Path

from fastapi.testclient import TestClient

from ra2_explorer.api import create_app
from ra2_explorer.codecs.mix import MixHashType, build_mix
from ra2_explorer.codecs.wav import parse_wav
from ra2_explorer.config import Settings
from ra2_explorer.library import SourceLibrary
from ra2_explorer.storage import Database


def test_audio_bag_entries_are_indexed_and_streamed_as_wav(tmp_path: Path) -> None:
    pcm = struct.pack("<hhhh", -1000, 0, 1000, 0)
    ima = struct.pack("<hBB", 0, 0, 0) + bytes((0x11, 0x22, 0x34, 0x87))
    bag = pcm + ima
    index = (
        b"GABA"
        + struct.pack("<II", 2, 2)
        + struct.pack("<16sIIIII", b"voicepcm\0", 0, len(pcm), 22_050, 0x06, 0)
        + struct.pack(
            "<16sIIIII",
            b"voiceima\0",
            len(pcm),
            len(ima),
            8_000,
            0x0C,
            8,
        )
    )
    source_dir = tmp_path / "retail"
    source_dir.mkdir()
    (source_dir / "audio.mix").write_bytes(
        build_mix(
            [("audio.idx", index), ("audio.bag", bag)],
            hash_type=MixHashType.RA2,
        )
    )
    data_dir = tmp_path / "runtime"
    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "library.db",
        frontend_dir=tmp_path / "missing-frontend",
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
    )
    settings.prepare()
    database = Database(settings.database_path)
    source = SourceLibrary(database, ("audio.idx", "audio.bag")).import_source(source_dir)

    page = database.list_assets(source_id=str(source["id"]), asset_format="bag_audio")
    assert page["total"] == 2
    assert {asset["display_name"] for asset in page["items"]} == {
        "voiceima.wav",
        "voicepcm.wav",
    }

    client = TestClient(create_app(settings))
    by_name = {asset["display_name"]: asset for asset in page["items"]}
    ima_asset = by_name["voiceima.wav"]
    metadata = client.get(f"/api/assets/{ima_asset['id']}/metadata")
    assert metadata.status_code == 200
    assert metadata.json()["audio_codec"] == "ima_adpcm"
    assert metadata.json()["duration_seconds"] > 0

    media = client.get(f"/api/assets/{ima_asset['id']}/media")
    assert media.status_code == 200
    assert media.headers["content-type"] == "audio/wav"
    assert parse_wav(media.content).audio_format == 1

    exported = client.get(f"/api/assets/{ima_asset['id']}/content")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "audio/wav"
    assert exported.content.startswith(b"RIFF")
