from __future__ import annotations

from pathlib import Path

from ra2_explorer.codecs.mix import build_mix
from ra2_explorer.codecs.sniff import sniff_format
from ra2_explorer.library import SourceLibrary
from ra2_explorer.storage import Database


def test_unnamed_encrypted_nested_mix_is_traversed(tmp_path: Path) -> None:
    source_dir = tmp_path / "game"
    source_dir.mkdir()
    inner = build_mix(
        (
            ("fixtone.wav", b"\x00" * 64),
            ("fixture.ini", b"[General]\nName=Fixture\n"),
        ),
        encrypted=True,
    )
    decoy = b"A" * 2048
    outer = build_mix((("sideblob.dat", inner), ("decoy.bin", decoy)))
    (source_dir / "outer.mix").write_bytes(outer)

    database = Database(tmp_path / "index.db")
    source = SourceLibrary(
        database, ("fixtone.wav", "fixture.ini")
    ).import_source(source_dir)
    items = database.list_assets(source_id=str(source["id"]), limit=500)["items"]

    formats = {asset["display_name"]: asset["format"] for asset in items}
    assert formats["fixtone.wav"] == "wav"
    assert formats["fixture.ini"] == "ini"
    # The decoy has no resolvable name and must not be mistaken for a MIX.
    assert sum(asset_format == "binary" for asset_format in formats.values()) == 1
    nested_mix_names = [
        name for name, asset_format in formats.items()
        if asset_format == "mix" and name.startswith("crc_")
    ]
    assert len(nested_mix_names) == 1


def test_sniff_detects_bink_video() -> None:
    assert sniff_format(b"BIKi" + b"\x00" * 64, None) == "video"


def test_unnamed_audio_bag_pair_is_expanded(tmp_path: Path) -> None:
    import struct

    source_dir = tmp_path / "game"
    source_dir.mkdir()
    bag_payload = b"\x00" * 64
    idx_payload = b"GABA" + struct.pack(
        "<II16sIIIII", 2, 1, b"vaposea", 0, len(bag_payload), 22050, 0x02, 0
    )
    outer = build_mix((("audio.idx", idx_payload), ("audio.bag", bag_payload)))
    (source_dir / "audio.mix").write_bytes(outer)

    database = Database(tmp_path / "index.db")
    source = SourceLibrary(database, ()).import_source(source_dir)
    items = database.list_assets(source_id=str(source["id"]), limit=500)["items"]

    bag_audio = [asset for asset in items if asset["format"] == "bag_audio"]
    assert len(bag_audio) == 1
    assert bag_audio[0]["display_name"] == "vaposea.wav"
