from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ra2_explorer.errors import AssetNotFoundError


@dataclass(frozen=True, slots=True)
class ArchiveRecord:
    id: str
    source_id: str
    parent_archive_id: str | None
    virtual_path: str
    root_relative_path: str
    entry_chain: str
    file_size: int
    data_offset: int | None
    data_size: int | None
    encrypted: int
    hash_type: str | None
    entry_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class AssetRecord:
    id: str
    source_id: str
    archive_id: str | None
    ordinal: int | None
    virtual_path: str
    name: str | None
    display_name: str
    crc: int | None
    size: int
    format: str
    extension: str
    confidence: str
    storage_kind: str
    loose_relative_path: str | None


@dataclass(frozen=True, slots=True)
class AssetSegmentRecord:
    asset_id: str
    container_asset_id: str
    data_offset: int
    data_size: int
    sample_rate: int
    channels: int
    codec: str
    block_align: int


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    scanned_at TEXT,
                    state TEXT NOT NULL,
                    error TEXT,
                    archive_count INTEGER NOT NULL DEFAULT 0,
                    asset_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS archives (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    parent_archive_id TEXT REFERENCES archives(id) ON DELETE CASCADE,
                    virtual_path TEXT NOT NULL,
                    root_relative_path TEXT NOT NULL,
                    entry_chain TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    data_offset INTEGER,
                    data_size INTEGER,
                    encrypted INTEGER NOT NULL,
                    hash_type TEXT,
                    entry_count INTEGER NOT NULL,
                    error TEXT,
                    UNIQUE(source_id, virtual_path)
                );
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    archive_id TEXT REFERENCES archives(id) ON DELETE CASCADE,
                    ordinal INTEGER,
                    virtual_path TEXT NOT NULL,
                    name TEXT,
                    display_name TEXT NOT NULL,
                    crc INTEGER,
                    size INTEGER NOT NULL,
                    format TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    storage_kind TEXT NOT NULL,
                    loose_relative_path TEXT,
                    UNIQUE(source_id, virtual_path)
                );
                CREATE TABLE IF NOT EXISTS asset_segments (
                    asset_id TEXT PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
                    container_asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                    data_offset INTEGER NOT NULL,
                    data_size INTEGER NOT NULL,
                    sample_rate INTEGER NOT NULL,
                    channels INTEGER NOT NULL,
                    codec TEXT NOT NULL,
                    block_align INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_archives_source ON archives(source_id);
                CREATE INDEX IF NOT EXISTS idx_assets_source_format ON assets(source_id, format);
                CREATE INDEX IF NOT EXISTS idx_assets_display_name ON assets(display_name);
                CREATE INDEX IF NOT EXISTS idx_asset_segments_container
                    ON asset_segments(container_asset_id);
                PRAGMA user_version = 2;
                """
            )

    def register_source(self, root_path: Path, name: str | None = None) -> dict[str, Any]:
        normalized = str(root_path.resolve())
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM sources WHERE root_path = ?", (normalized,)
            ).fetchone()
            if existing:
                if name and name != existing["name"]:
                    connection.execute(
                        "UPDATE sources SET name = ? WHERE id = ?",
                        (name, existing["id"]),
                    )
                    existing = connection.execute(
                        "SELECT * FROM sources WHERE id = ?", (existing["id"],)
                    ).fetchone()
                return dict(existing)
            source_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO sources(id, name, root_path, created_at, state)
                VALUES (?, ?, ?, ?, 'new')
                """,
                (source_id, name or root_path.name or normalized, normalized, now),
            )
            row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            return dict(row)

    def get_source(self, source_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            raise AssetNotFoundError("资源目录不存在")
        return dict(row)

    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sources ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_source_state(self, source_id: str, state: str, error: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE sources SET state = ?, error = ? WHERE id = ?",
                (state, error, source_id),
            )

    def replace_source_index(
        self,
        source_id: str,
        archives: Iterable[ArchiveRecord],
        assets: Iterable[AssetRecord],
        segments: Iterable[AssetSegmentRecord] = (),
        *,
        state: str,
        error: str | None,
    ) -> None:
        archive_rows = [asdict(record) for record in archives]
        asset_rows = [asdict(record) for record in assets]
        segment_rows = [asdict(record) for record in segments]
        with self.connect() as connection:
            connection.execute("DELETE FROM assets WHERE source_id = ?", (source_id,))
            connection.execute("DELETE FROM archives WHERE source_id = ?", (source_id,))
            connection.executemany(
                """
                INSERT INTO archives(
                    id, source_id, parent_archive_id, virtual_path, root_relative_path,
                    entry_chain, file_size, data_offset, data_size, encrypted, hash_type,
                    entry_count, error
                ) VALUES (
                    :id, :source_id, :parent_archive_id, :virtual_path, :root_relative_path,
                    :entry_chain, :file_size, :data_offset, :data_size, :encrypted, :hash_type,
                    :entry_count, :error
                )
                """,
                archive_rows,
            )
            connection.executemany(
                """
                INSERT INTO assets(
                    id, source_id, archive_id, ordinal, virtual_path, name, display_name,
                    crc, size, format, extension, confidence, storage_kind, loose_relative_path
                ) VALUES (
                    :id, :source_id, :archive_id, :ordinal, :virtual_path, :name, :display_name,
                    :crc, :size, :format, :extension, :confidence, :storage_kind,
                    :loose_relative_path
                )
                """,
                asset_rows,
            )
            connection.executemany(
                """
                INSERT INTO asset_segments(
                    asset_id, container_asset_id, data_offset, data_size,
                    sample_rate, channels, codec, block_align
                ) VALUES (
                    :asset_id, :container_asset_id, :data_offset, :data_size,
                    :sample_rate, :channels, :codec, :block_align
                )
                """,
                segment_rows,
            )
            connection.execute(
                """
                UPDATE sources
                SET state = ?, error = ?, scanned_at = ?, archive_count = ?, asset_count = ?
                WHERE id = ?
                """,
                (
                    state,
                    error,
                    datetime.now(UTC).isoformat(),
                    len(archive_rows),
                    len(asset_rows),
                    source_id,
                ),
            )

    def list_assets(
        self,
        *,
        source_id: str | None = None,
        query: str | None = None,
        asset_format: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses = []
        parameters: list[Any] = []
        if source_id:
            clauses.append("assets.source_id = ?")
            parameters.append(source_id)
        if query:
            clauses.append(
                "(lower(assets.display_name) LIKE ? OR lower(assets.virtual_path) LIKE ? "
                "OR printf('%08X', assets.crc) LIKE upper(?))"
            )
            pattern = f"%{query.lower()}%"
            parameters.extend((pattern, pattern, f"%{query}%"))
        if asset_format:
            clauses.append("assets.format = ?")
            parameters.append(asset_format)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM assets {where}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT assets.*, archives.virtual_path AS archive_path
                FROM assets
                LEFT JOIN archives ON archives.id = assets.archive_id
                {where}
                ORDER BY CASE WHEN assets.name IS NULL THEN 1 ELSE 0 END,
                         lower(assets.display_name), assets.virtual_path
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total}

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT assets.*, archives.virtual_path AS archive_path
                FROM assets
                LEFT JOIN archives ON archives.id = assets.archive_id
                WHERE assets.id = ?
                """,
                (asset_id,),
            ).fetchone()
        if not row:
            raise AssetNotFoundError("资产不存在")
        return dict(row)

    def get_archive(self, archive_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM archives WHERE id = ?", (archive_id,)
            ).fetchone()
        if not row:
            raise AssetNotFoundError("归档不存在")
        return dict(row)

    def get_asset_segment(self, asset_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM asset_segments WHERE asset_id = ?", (asset_id,)
            ).fetchone()
        if not row:
            raise AssetNotFoundError("资产片段不存在")
        return dict(row)

    def palette_assets(self, source_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT assets.*, archives.virtual_path AS archive_path
                FROM assets
                LEFT JOIN archives ON archives.id = assets.archive_id
                WHERE assets.source_id = ? AND assets.format = 'pal'
                ORDER BY lower(display_name)
                """,
                (source_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def assets_for_formats(
        self,
        source_id: str,
        formats: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if not formats:
            return []
        placeholders = ", ".join("?" for _ in formats)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT assets.*, archives.virtual_path AS archive_path
                FROM assets
                LEFT JOIN archives ON archives.id = assets.archive_id
                WHERE assets.source_id = ? AND assets.format IN ({placeholders})
                ORDER BY lower(assets.display_name), assets.virtual_path
                """,
                (source_id, *formats),
            ).fetchall()
        return [dict(row) for row in rows]

    def sample_assets(
        self,
        source_id: str,
        formats: tuple[str, ...],
        *,
        per_format: int,
    ) -> dict[str, list[dict[str, Any]]]:
        per_format = max(1, min(per_format, 100))
        samples: dict[str, list[dict[str, Any]]] = {}
        with self.connect() as connection:
            for asset_format in formats:
                total = connection.execute(
                    "SELECT COUNT(*) FROM assets WHERE source_id = ? AND format = ?",
                    (source_id, asset_format),
                ).fetchone()[0]
                if not total:
                    continue
                if total <= per_format:
                    offsets = range(total)
                elif per_format == 1:
                    offsets = (0,)
                else:
                    offsets = sorted(
                        {
                            round(index * (total - 1) / (per_format - 1))
                            for index in range(per_format)
                        }
                    )
                rows = []
                for offset in offsets:
                    row = connection.execute(
                        """
                        SELECT assets.*, archives.virtual_path AS archive_path
                        FROM assets
                        LEFT JOIN archives ON archives.id = assets.archive_id
                        WHERE assets.source_id = ? AND assets.format = ?
                        ORDER BY lower(assets.display_name), assets.virtual_path
                        LIMIT 1 OFFSET ?
                        """,
                        (source_id, asset_format, offset),
                    ).fetchone()
                    if row:
                        rows.append(dict(row))
                samples[asset_format] = rows
        return samples

    def stats(self, source_id: str | None = None) -> dict[str, Any]:
        where = "WHERE source_id = ?" if source_id else ""
        parameters = (source_id,) if source_id else ()
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM assets {where}", parameters
            ).fetchone()[0]
            formats = connection.execute(
                f"""
                SELECT format, COUNT(*) AS count FROM assets {where}
                GROUP BY format ORDER BY count DESC, format
                """,
                parameters,
            ).fetchall()
        return {"total_assets": total, "formats": [dict(row) for row in formats]}


__all__ = ["ArchiveRecord", "AssetRecord", "AssetSegmentRecord", "Database"]
