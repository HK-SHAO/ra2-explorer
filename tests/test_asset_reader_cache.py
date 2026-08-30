from __future__ import annotations

from pathlib import Path

from ra2_explorer.derived import DerivedStore
from ra2_explorer.library import AssetReader, SourceLibrary
from ra2_explorer.storage import Database


def test_read_does_not_duplicate_source_but_materialize_is_explicit(tmp_path: Path) -> None:
    source_dir = tmp_path / "game"
    source_dir.mkdir()
    original = b"[General]\nName=Fixture\n"
    (source_dir / "rules.ini").write_bytes(original)
    database = Database(tmp_path / "index.db")
    source = SourceLibrary(database, ()).import_source(source_dir)
    asset = database.list_assets(source_id=str(source["id"]))["items"][0]
    store = DerivedStore(tmp_path / "RA2MD-Ext")
    reader = AssetReader(database, store)

    _, data = reader.read(str(asset["id"]))

    assert data == original
    assert store.stats()["kinds"]["extracted"]["files"] == 0

    _, materialized = reader.materialize(str(asset["id"]))

    assert materialized.read_bytes() == original
    assert store.stats()["kinds"]["extracted"] == {
        "files": 1,
        "bytes": len(original),
    }
