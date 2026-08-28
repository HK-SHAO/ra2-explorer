from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    database_path: Path
    frontend_dir: Path
    known_names_path: Path

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.known_names_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings(*, working_directory: Path | None = None) -> Settings:
    workspace = (working_directory or Path.cwd()).resolve()
    data_dir = Path(os.environ.get("RA2_EXPLORER_DATA_DIR", workspace / ".runtime")).resolve()
    default_frontend = workspace / "frontend" / "dist"
    frontend_dir = Path(os.environ.get("RA2_EXPLORER_FRONTEND_DIR", default_frontend)).resolve()
    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "ra2-explorer.db",
        frontend_dir=frontend_dir,
        known_names_path=data_dir / "reference" / "known_names_ra2.txt",
    )
    settings.prepare()
    return settings


__all__ = ["Settings", "load_settings"]
