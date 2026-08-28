from __future__ import annotations

import sqlite3
from pathlib import Path

from ra2_explorer.config import load_settings


def test_default_index_migrates_into_ra2md_ext(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("RA2_EXPLORER_DATA_DIR", raising=False)
    monkeypatch.delenv("RA2_EXPLORER_DERIVED_DIR", raising=False)
    runtime = tmp_path / ".runtime"
    runtime.mkdir()
    legacy = runtime / "ra2-explorer.db"
    with sqlite3.connect(legacy) as connection:
        connection.execute("CREATE TABLE proof(value TEXT NOT NULL)")
        connection.execute("INSERT INTO proof VALUES ('migrated')")

    settings = load_settings(working_directory=tmp_path)

    assert settings.derived_root == (runtime / "RA2MD-Ext").resolve()
    assert settings.database_path == settings.derived_root / "index" / "ra2-explorer.db"
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT value FROM proof").fetchone()[0] == "migrated"
