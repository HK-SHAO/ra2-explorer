from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ra2_explorer.config import PORTABLE_MANIFEST, PORTABLE_ROOT_URI, load_settings


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


def test_portable_index_relocates_without_preserving_build_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("RA2_EXPLORER_DATA_DIR", raising=False)
    monkeypatch.delenv("RA2_EXPLORER_DERIVED_DIR", raising=False)
    game_path = tmp_path / ".runtime" / "RA2MD"
    game_path.mkdir(parents=True)
    settings = load_settings(working_directory=tmp_path)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("CREATE TABLE sources(id TEXT PRIMARY KEY, root_path TEXT NOT NULL)")
        connection.execute("INSERT INTO sources VALUES ('portable', ?)", (PORTABLE_ROOT_URI,))
    (tmp_path / PORTABLE_MANIFEST).write_text(
        json.dumps({"source_id": "portable", "game_path": ".runtime/RA2MD"}),
        encoding="utf-8",
    )

    load_settings(working_directory=tmp_path)

    with sqlite3.connect(settings.database_path) as connection:
        root_path = connection.execute(
            "SELECT root_path FROM sources WHERE id = 'portable'"
        ).fetchone()[0]
    assert root_path == str(game_path.resolve())
