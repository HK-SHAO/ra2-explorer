from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ra2_explorer.codecs.mix import (
    MixHashType,
    classic_mix_hash,
    parse_local_mix_database,
    parse_mix,
    ra2_mix_hash,
)
from ra2_explorer.codecs.sniff import KNOWN_FORMATS, format_from_name, sniff_format
from ra2_explorer.errors import AssetNotFoundError, Ra2ExplorerError
from ra2_explorer.storage import ArchiveRecord, AssetRecord, Database

ARCHIVE_EXTENSIONS = {".mix", ".mmx", ".yro"}
MAX_ARCHIVE_SIZE = 1_073_741_824
MAX_NESTING_DEPTH = 6
MAX_ARCHIVES_PER_SOURCE = 4096
MAX_SNIFF_BYTES = 67_108_864


class NameResolver:
    def __init__(self, names: tuple[str, ...]):
        self.ra2: dict[int, str] = {}
        self.classic: dict[int, str] = {}
        self.extend(names)

    def extend(self, names: tuple[str, ...]) -> None:
        for raw_name in names:
            name = raw_name.strip().replace("/", "\\")
            if not name or name.startswith("#"):
                continue
            try:
                self.ra2.setdefault(ra2_mix_hash(name), name)
                self.classic.setdefault(classic_mix_hash(name), name)
            except ValueError:
                continue

    def resolve(self, entry_ids: set[int]) -> tuple[MixHashType, dict[int, str]]:
        ra2_matches = {crc: name for crc, name in self.ra2.items() if crc in entry_ids}
        classic_matches = {crc: name for crc, name in self.classic.items() if crc in entry_ids}
        if len(classic_matches) > len(ra2_matches):
            return MixHashType.CLASSIC, classic_matches
        return MixHashType.RA2, ra2_matches


@dataclass(slots=True)
class ScanResult:
    archives: list[ArchiveRecord]
    assets: list[AssetRecord]
    errors: list[str]


class SourceLibrary:
    def __init__(self, database: Database, known_names: tuple[str, ...]):
        self.database = database
        self.names = NameResolver(known_names)

    def import_source(self, root_path: Path, name: str | None = None) -> dict[str, object]:
        try:
            root = root_path.expanduser().resolve(strict=True)
        except OSError as error:
            raise Ra2ExplorerError("资源目录不存在") from error
        if not root.is_dir():
            raise Ra2ExplorerError("资源路径必须是一个目录")
        source = self.database.register_source(root, name)
        self.scan(source["id"])
        return self.database.get_source(source["id"])

    def scan(self, source_id: str) -> dict[str, object]:
        source = self.database.get_source(source_id)
        root = Path(source["root_path"])
        if not root.is_dir():
            self.database.set_source_state(source_id, "failed", "资源目录已不存在")
            raise AssetNotFoundError("资源目录已不存在")

        self.database.set_source_state(source_id, "scanning")
        result = ScanResult([], [], [])
        try:
            archive_paths = self._collect_loose_assets(source_id, root, result)
            for relative_path in archive_paths:
                archive_path = self._safe_source_path(root, relative_path)
                size = archive_path.stat().st_size
                if size > MAX_ARCHIVE_SIZE:
                    result.errors.append(f"{relative_path}: 归档超过 1 GB 限制")
                    continue
                try:
                    data = archive_path.read_bytes()
                except OSError as error:
                    result.errors.append(f"{relative_path}: 无法读取（{error}）")
                    continue
                self._index_archive(
                    source_id=source_id,
                    root_relative_path=relative_path,
                    virtual_path=PurePosixPath(relative_path).as_posix(),
                    data=data,
                    entry_chain=(),
                    parent_archive_id=None,
                    depth=0,
                    result=result,
                )
        except Exception as error:
            self.database.set_source_state(source_id, "failed", str(error))
            raise

        state = "ready_with_errors" if result.errors else "ready"
        error_summary = "\n".join(result.errors[:20]) or None
        self.database.replace_source_index(
            source_id,
            result.archives,
            result.assets,
            state=state,
            error=error_summary,
        )
        return self.database.get_source(source_id)

    def _collect_loose_assets(
        self, source_id: str, root: Path, result: ScanResult
    ) -> list[str]:
        archive_paths: list[str] = []
        source_uuid = uuid.UUID(source_id)
        for current_root, directories, filenames in os.walk(root, followlinks=False):
            directories[:] = [
                directory
                for directory in directories
                if not (Path(current_root) / directory).is_symlink()
            ]
            current_path = Path(current_root)
            for filename in filenames:
                path = current_path / filename
                if path.is_symlink():
                    continue
                try:
                    relative = path.relative_to(root).as_posix()
                    size = path.stat().st_size
                except OSError as error:
                    result.errors.append(f"{filename}: 无法读取文件信息（{error}）")
                    continue
                extension = path.suffix.lower()
                if extension in ARCHIVE_EXTENSIONS:
                    archive_paths.append(relative)
                    continue
                asset_format = KNOWN_FORMATS.get(extension)
                if not asset_format:
                    continue
                virtual_path = f"loose::{relative}"
                result.assets.append(
                    AssetRecord(
                        id=str(uuid.uuid5(source_uuid, virtual_path.casefold())),
                        source_id=source_id,
                        archive_id=None,
                        ordinal=None,
                        virtual_path=virtual_path,
                        name=filename,
                        display_name=filename,
                        crc=None,
                        size=size,
                        format=asset_format,
                        extension=extension.lstrip("."),
                        confidence="filename",
                        storage_kind="loose",
                        loose_relative_path=relative,
                    )
                )
        return sorted(archive_paths, key=str.casefold)

    def _index_archive(
        self,
        *,
        source_id: str,
        root_relative_path: str,
        virtual_path: str,
        data: bytes,
        entry_chain: tuple[int, ...],
        parent_archive_id: str | None,
        depth: int,
        result: ScanResult,
    ) -> None:
        source_uuid = uuid.UUID(source_id)
        archive_id = str(uuid.uuid5(source_uuid, f"archive:{virtual_path.casefold()}"))
        if len(result.archives) >= MAX_ARCHIVES_PER_SOURCE:
            result.errors.append("嵌套归档数量超过 4096 个")
            return
        try:
            index = parse_mix(data)
        except Ra2ExplorerError as error:
            result.archives.append(
                ArchiveRecord(
                    id=archive_id,
                    source_id=source_id,
                    parent_archive_id=parent_archive_id,
                    virtual_path=virtual_path,
                    root_relative_path=root_relative_path,
                    entry_chain=json.dumps(entry_chain),
                    file_size=len(data),
                    data_offset=None,
                    data_size=None,
                    encrypted=0,
                    hash_type=None,
                    entry_count=0,
                    error=str(error),
                )
            )
            result.errors.append(f"{virtual_path}: {error}")
            return

        entry_ids = {entry.crc for entry in index.entries}
        local_database_ids = {
            ra2_mix_hash("local mix database.dat"),
            classic_mix_hash("local mix database.dat"),
        }
        for entry in index.entries:
            if entry.crc not in local_database_ids:
                continue
            local_names = parse_local_mix_database(index.payload(data, entry))
            if local_names:
                self.names.extend(local_names)
            break
        hash_type, resolved_names = self.names.resolve(entry_ids)
        result.archives.append(
            ArchiveRecord(
                id=archive_id,
                source_id=source_id,
                parent_archive_id=parent_archive_id,
                virtual_path=virtual_path,
                root_relative_path=root_relative_path,
                entry_chain=json.dumps(entry_chain),
                file_size=len(data),
                data_offset=index.data_offset,
                data_size=index.data_size,
                encrypted=int(index.encrypted),
                hash_type=hash_type.value,
                entry_count=len(index.entries),
                error=None,
            )
        )

        for entry in index.entries:
            name = resolved_names.get(entry.crc)
            payload = index.payload(data, entry)
            asset_format = format_from_name(name)
            confidence = "name" if asset_format else "unknown"
            if not asset_format and entry.size <= MAX_SNIFF_BYTES:
                asset_format = sniff_format(payload, name)
                if asset_format != "binary":
                    confidence = "content"
            asset_format = asset_format or "binary"
            extension = Path(name).suffix.lower().lstrip(".") if name else ""
            if not extension and asset_format != "binary":
                extension = asset_format
            display_name = name or f"crc_{entry.crc:08X}.{extension or 'bin'}"
            asset_virtual_path = f"{virtual_path}::{entry.ordinal:05d}:{display_name}"
            asset_id = str(uuid.uuid5(source_uuid, f"asset:{asset_virtual_path.casefold()}"))
            result.assets.append(
                AssetRecord(
                    id=asset_id,
                    source_id=source_id,
                    archive_id=archive_id,
                    ordinal=entry.ordinal,
                    virtual_path=asset_virtual_path,
                    name=name,
                    display_name=display_name,
                    crc=entry.crc,
                    size=entry.size,
                    format=asset_format,
                    extension=extension,
                    confidence=confidence,
                    storage_kind="mix",
                    loose_relative_path=None,
                )
            )

            if asset_format != "mix" or depth >= MAX_NESTING_DEPTH:
                continue
            child_path = f"{virtual_path}/{display_name}"
            self._index_archive(
                source_id=source_id,
                root_relative_path=root_relative_path,
                virtual_path=child_path,
                data=bytes(payload),
                entry_chain=(*entry_chain, entry.ordinal),
                parent_archive_id=archive_id,
                depth=depth + 1,
                result=result,
            )

    @staticmethod
    def _safe_source_path(root: Path, relative_path: str) -> Path:
        candidate = (root / Path(relative_path)).resolve(strict=True)
        try:
            candidate.relative_to(root.resolve(strict=True))
        except ValueError as error:
            raise Ra2ExplorerError("资源路径越过了已注册目录") from error
        return candidate


class AssetReader:
    def __init__(self, database: Database):
        self.database = database

    def read(self, asset_id: str) -> tuple[dict[str, object], bytes]:
        asset = self.database.get_asset(asset_id)
        source = self.database.get_source(asset["source_id"])
        root = Path(source["root_path"])
        if asset["storage_kind"] == "loose":
            path = SourceLibrary._safe_source_path(root, asset["loose_relative_path"])
            data = path.read_bytes()
            if len(data) != asset["size"]:
                raise Ra2ExplorerError("源文件已变化，请重新扫描")
            return asset, data

        archive = self.database.get_archive(asset["archive_id"])
        root_archive_path = SourceLibrary._safe_source_path(root, archive["root_relative_path"])
        data = root_archive_path.read_bytes()
        for ordinal in json.loads(archive["entry_chain"]):
            index = parse_mix(data)
            try:
                entry = index.entries[ordinal]
            except IndexError as error:
                raise Ra2ExplorerError("源归档已变化，请重新扫描") from error
            data = bytes(index.payload(data, entry))
        index = parse_mix(data)
        ordinal = asset["ordinal"]
        try:
            entry = index.entries[ordinal]
        except (IndexError, TypeError) as error:
            raise Ra2ExplorerError("源归档已变化，请重新扫描") from error
        if entry.crc != asset["crc"] or entry.size != asset["size"]:
            raise Ra2ExplorerError("源归档已变化，请重新扫描")
        return asset, bytes(index.payload(data, entry))


__all__ = ["AssetReader", "NameResolver", "SourceLibrary"]
