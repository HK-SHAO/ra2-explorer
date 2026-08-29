from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 46_120


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    database_path: Path
    frontend_dir: Path
    known_names_path: Path
    derived_dir: Path | None = None

    @property
    def derived_root(self) -> Path:
        return (self.derived_dir or self.data_dir / "RA2MD-Ext").resolve()

    @property
    def audio_transcript_path(self) -> Path:
        return self.derived_root / "reference" / "ra2-audio-transcript.xlsx"

    @property
    def mission_audio_transcript_path(self) -> Path:
        return self.derived_root / "reference" / "mission-audio-transcript.json"

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.derived_root.mkdir(parents=True, exist_ok=True)
        self.known_names_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings(*, working_directory: Path | None = None) -> Settings:
    workspace = (working_directory or Path.cwd()).resolve()
    data_dir = Path(os.environ.get("RA2_EXPLORER_DATA_DIR", workspace / ".runtime")).resolve()
    derived_dir = Path(
        os.environ.get("RA2_EXPLORER_DERIVED_DIR", data_dir / "RA2MD-Ext")
    ).resolve()
    default_frontend = workspace / "frontend" / "dist"
    frontend_dir = Path(os.environ.get("RA2_EXPLORER_FRONTEND_DIR", default_frontend)).resolve()
    settings = Settings(
        data_dir=data_dir,
        database_path=derived_dir / "index" / "ra2-explorer.db",
        frontend_dir=frontend_dir,
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
        derived_dir=derived_dir,
    )
    settings.prepare()
    _migrate_legacy_database(data_dir / "ra2-explorer.db", settings.database_path)
    return settings


def _migrate_legacy_database(legacy_path: Path, target_path: Path) -> None:
    if target_path.exists() or not legacy_path.is_file():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(legacy_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)


__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "Settings", "load_settings"]
