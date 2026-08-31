from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 46_120
PORTABLE_MANIFEST = "ra2-explorer-portable.json"
PORTABLE_ROOT_URI = "portable://RA2MD"


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    database_path: Path
    frontend_dir: Path
    known_names_path: Path
    derived_dir: Path | None = None
    hosted: bool = False

    @property
    def derived_root(self) -> Path:
        return (self.derived_dir or self.data_dir / "RA2MD-Ext").resolve()

    @property
    def audio_transcript_path(self) -> Path:
        return self.derived_root / "reference" / "ra2-audio-transcript.xlsx"

    @property
    def mission_audio_transcript_path(self) -> Path:
        return self.derived_root / "reference" / "mission-audio-transcript.json"

    @property
    def english_voice_transcript_path(self) -> Path:
        return self.derived_root / "reference" / "english-voice-transcript.json"

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.derived_root.mkdir(parents=True, exist_ok=True)
        self.known_names_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings(*, working_directory: Path | None = None) -> Settings:
    workspace = application_root(working_directory)
    data_dir = Path(os.environ.get("RA2_EXPLORER_DATA_DIR", workspace / ".runtime")).resolve()
    derived_dir = Path(
        os.environ.get("RA2_EXPLORER_DERIVED_DIR", data_dir / "RA2MD-Ext")
    ).resolve()
    bundle_root = Path(getattr(sys, "_MEIPASS", workspace)).resolve()
    default_frontend = bundle_root / "frontend" / "dist"
    frontend_dir = Path(os.environ.get("RA2_EXPLORER_FRONTEND_DIR", default_frontend)).resolve()
    settings = Settings(
        data_dir=data_dir,
        database_path=derived_dir / "index" / "ra2-explorer.db",
        frontend_dir=frontend_dir,
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
        derived_dir=derived_dir,
        hosted=os.environ.get("RA2_EXPLORER_HOSTED", "").strip().casefold()
        in {"1", "true", "yes"},
    )
    settings.prepare()
    _migrate_legacy_database(data_dir / "ra2-explorer.db", settings.database_path)
    _relocate_portable_database(workspace, settings.database_path)
    return settings


def application_root(working_directory: Path | None = None) -> Path:
    if working_directory is not None:
        return working_directory.resolve()
    configured = os.environ.get("RA2_EXPLORER_HOME")
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def _migrate_legacy_database(legacy_path: Path, target_path: Path) -> None:
    if target_path.exists() or not legacy_path.is_file():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(legacy_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)


def _relocate_portable_database(workspace: Path, database_path: Path) -> None:
    manifest_path = workspace / PORTABLE_MANIFEST
    if not manifest_path.is_file() or not database_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_id = str(manifest["source_id"])
        relative_path = Path(str(manifest["game_path"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return
    game_path = (workspace / relative_path).resolve()
    try:
        game_path.relative_to(workspace)
    except ValueError:
        return
    if not game_path.is_dir():
        return
    try:
        with sqlite3.connect(database_path) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sources'"
            ).fetchone()
            if table:
                connection.execute(
                    "UPDATE sources SET root_path = ? WHERE id = ? AND root_path != ?",
                    (str(game_path), source_id, str(game_path)),
                )
    except sqlite3.DatabaseError:
        return


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "PORTABLE_MANIFEST",
    "PORTABLE_ROOT_URI",
    "Settings",
    "application_root",
    "load_settings",
]
