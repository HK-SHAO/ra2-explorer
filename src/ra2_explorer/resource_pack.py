from __future__ import annotations

import json
import os
import re
import shutil
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ra2_explorer import __version__
from ra2_explorer.derived import DERIVED_SCHEMA_VERSION, DerivedStore
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.semantic import SemanticLibrary, deserialize_semantic_catalog
from ra2_explorer.storage import Database

RESOURCE_PACK_SCHEMA = 1
RESOURCE_PACK_SUFFIX = ".ra2pack"
RESOURCE_PACK_ROOT_PREFIX = "resource-pack://"
MAX_RESOURCE_PACK_BYTES = 2 * 1024 * 1024 * 1024
MAX_RESOURCE_PACK_CONTENT_BYTES = 4 * 1024 * 1024 * 1024
MAX_RESOURCE_PACK_ENTRIES = 100_000
MAX_RESOURCE_PACK_JSON_BYTES = 128 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_PORTABLE_KINDS = {
    "audio": frozenset({".wav"}),
    "metadata": frozenset({".json"}),
    "models": frozenset({".json"}),
    "previews": frozenset({".png"}),
    "video": frozenset({".mp4"}),
}


def create_resource_pack(
    database: Database,
    semantic: SemanticLibrary,
    derived: DerivedStore,
    source_id: str,
    *,
    output: Path | None = None,
) -> dict[str, object]:
    source = database.get_source(source_id)
    revision = source.get("scanned_at")
    if not revision:
        raise Ra2ExplorerError("资源目录尚未完成扫描")
    semantic.catalog(source_id)
    catalog_path = derived.artifact_path(
        "metadata",
        source_id=source_id,
        revision=revision,
        identity=("semantic-catalog-v1",),
        extension="json",
    )
    if not catalog_path.is_file():
        raise Ra2ExplorerError("语义索引尚未准备完成")

    revision_root = derived.source_revision_root(source_id, revision)
    artifact_files = _portable_artifacts(revision_root)
    artifact_prefix = revision_root.relative_to(derived.root).as_posix()
    semantic_snapshot = catalog_path.relative_to(derived.root).as_posix()
    snapshot = database.export_source_snapshot(source_id)
    created_at = datetime.now(UTC)
    destination = (
        output.expanduser().resolve()
        if output is not None
        else _next_default_path(derived.root / "packages", str(source["name"]), created_at)
    )
    if destination.suffix.casefold() != RESOURCE_PACK_SUFFIX:
        destination = destination.with_suffix(RESOURCE_PACK_SUFFIX)
    if destination.exists():
        raise Ra2ExplorerError("资源包输出文件已经存在")
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_bytes = sum(path.stat().st_size for path in artifact_files)
    manifest = {
        "schema": RESOURCE_PACK_SCHEMA,
        "kind": "ra2-explorer-resource-pack",
        "application_version": __version__,
        "derived_schema": DERIVED_SCHEMA_VERSION,
        "created_at": created_at.isoformat(),
        "source": {
            "id": source_id,
            "name": source["name"],
            "revision": revision,
            "asset_count": source["asset_count"],
        },
        "artifact_prefix": artifact_prefix,
        "semantic_snapshot": semantic_snapshot,
        "artifact_files": len(artifact_files),
        "artifact_bytes": source_bytes,
        "contains_game_files": False,
    }
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            archive.writestr(
                "manifest.json",
                _json_bytes(manifest),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            )
            archive.writestr(
                "index.json",
                _json_bytes(snapshot),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            )
            for path in artifact_files:
                compression = (
                    zipfile.ZIP_DEFLATED
                    if path.suffix.casefold() == ".json"
                    else zipfile.ZIP_STORED
                )
                archive.write(
                    path,
                    path.relative_to(derived.root).as_posix(),
                    compress_type=compression,
                    compresslevel=6 if compression == zipfile.ZIP_DEFLATED else None,
                )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "filename": destination.name,
        "path": str(destination),
        "size": destination.stat().st_size,
        "source_id": source_id,
        "source_name": source["name"],
        "asset_count": source["asset_count"],
        "artifact_files": len(artifact_files),
        "artifact_bytes": source_bytes,
        "download_url": f"/api/resource-packs/{destination.name}",
    }


def import_resource_pack(
    database: Database,
    derived: DerivedStore,
    pack_path: Path,
) -> dict[str, object]:
    resolved_pack = pack_path.expanduser().resolve(strict=True)
    if not resolved_pack.is_file():
        raise Ra2ExplorerError("资源包文件不存在")
    if resolved_pack.stat().st_size > MAX_RESOURCE_PACK_BYTES:
        raise Ra2ExplorerError("资源包超过 2 GiB 限制")
    try:
        archive = zipfile.ZipFile(resolved_pack)
    except (OSError, zipfile.BadZipFile) as error:
        raise Ra2ExplorerError("资源包不是有效的 ZIP 文件") from error
    with archive:
        manifest = _read_json_entry(archive, "manifest.json")
        snapshot = _read_json_entry(archive, "index.json")
        source_id, artifact_prefix, semantic_snapshot = _validate_pack(
            archive,
            manifest,
            snapshot,
        )
        semantic_payload = _read_json_entry(archive, semantic_snapshot)
        catalog = deserialize_semantic_catalog(semantic_payload)
        if catalog.source_id != source_id:
            raise Ra2ExplorerError("资源包语义索引与资料库不匹配")

        installed_files = 0
        reused_files = 0
        installed_bytes = 0
        for info in archive.infolist():
            if not info.filename.startswith(f"{artifact_prefix}/") or info.is_dir():
                continue
            target = (derived.root / Path(*PurePosixPath(info.filename).parts)).resolve()
            try:
                target.relative_to(derived.artifacts_root)
            except ValueError as error:
                raise Ra2ExplorerError("资源包产物路径越过派生工作区") from error
            if target.is_file():
                reused_files += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            try:
                with archive.open(info) as source, temporary.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                derived.commit_file(target, temporary)
            finally:
                temporary.unlink(missing_ok=True)
            installed_files += 1
            installed_bytes += info.file_size

    source, imported = database.import_source_snapshot(
        snapshot,
        root_path=f"{RESOURCE_PACK_ROOT_PREFIX}{source_id}",
    )
    return {
        "source": source,
        "imported": imported,
        "installed_files": installed_files,
        "reused_files": reused_files,
        "installed_bytes": installed_bytes,
    }


def validate_resource_pack(pack_path: Path) -> dict[str, object]:
    """Validate a derived-only pack without installing any of its payload."""
    resolved_pack = pack_path.expanduser().resolve(strict=True)
    if not resolved_pack.is_file():
        raise Ra2ExplorerError("资源包文件不存在")
    if resolved_pack.stat().st_size > MAX_RESOURCE_PACK_BYTES:
        raise Ra2ExplorerError("资源包超过 2 GiB 限制")
    try:
        archive = zipfile.ZipFile(resolved_pack)
    except (OSError, zipfile.BadZipFile) as error:
        raise Ra2ExplorerError("资源包不是有效的 ZIP 文件") from error
    with archive:
        manifest = _read_json_entry(archive, "manifest.json")
        snapshot = _read_json_entry(archive, "index.json")
        source_id, artifact_prefix, semantic_snapshot = _validate_pack(
            archive,
            manifest,
            snapshot,
        )
        catalog = deserialize_semantic_catalog(
            _read_json_entry(archive, semantic_snapshot)
        )
        if catalog.source_id != source_id:
            raise Ra2ExplorerError("资源包语义索引与资料库不匹配")
        artifacts = [
            info
            for info in archive.infolist()
            if not info.is_dir() and info.filename.startswith(f"{artifact_prefix}/")
        ]
        artifact_bytes = sum(info.file_size for info in artifacts)
        if manifest.get("artifact_files") != len(artifacts):
            raise Ra2ExplorerError("资源包产物数量与清单不匹配")
        if manifest.get("artifact_bytes") != artifact_bytes:
            raise Ra2ExplorerError("资源包产物大小与清单不匹配")
        source = _mapping(manifest.get("source"))
        return {
            "source_id": source_id,
            "asset_count": int(source.get("asset_count") or 0),
            "artifact_files": len(artifacts),
            "artifact_bytes": artifact_bytes,
            "archive_bytes": resolved_pack.stat().st_size,
            "contains_game_files": False,
        }


def list_resource_packs(derived: DerivedStore) -> list[dict[str, object]]:
    package_root = derived.root / "packages"
    if not package_root.is_dir():
        return []
    packs = []
    for path in sorted(package_root.glob(f"*{RESOURCE_PACK_SUFFIX}")):
        try:
            with zipfile.ZipFile(path) as archive:
                manifest = _read_json_entry(archive, "manifest.json")
            source = _mapping(manifest.get("source"))
        except (OSError, Ra2ExplorerError, zipfile.BadZipFile):
            continue
        packs.append(
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "created_at": manifest.get("created_at"),
                "source_id": source.get("id"),
                "source_name": source.get("name"),
                "asset_count": source.get("asset_count"),
                "download_url": f"/api/resource-packs/{path.name}",
            }
        )
    return packs


def resource_pack_path(derived: DerivedStore, filename: str) -> Path:
    if Path(filename).name != filename or not filename.casefold().endswith(RESOURCE_PACK_SUFFIX):
        raise Ra2ExplorerError("资源包文件名无效")
    package_root = (derived.root / "packages").resolve()
    candidate = (package_root / filename).resolve()
    try:
        candidate.relative_to(package_root)
    except ValueError as error:
        raise Ra2ExplorerError("资源包路径越过导出目录") from error
    if not candidate.is_file():
        raise Ra2ExplorerError("资源包不存在")
    return candidate


def _portable_artifacts(revision_root: Path) -> list[Path]:
    files = []
    for kind, suffixes in _PORTABLE_KINDS.items():
        kind_root = revision_root / kind
        if not kind_root.is_dir():
            continue
        files.extend(
            path
            for path in kind_root.rglob("*")
            if path.is_file() and path.suffix.casefold() in suffixes
        )
    return sorted(files)


def _validate_pack(
    archive: zipfile.ZipFile,
    manifest: dict[str, Any],
    snapshot: dict[str, Any],
) -> tuple[str, str, str]:
    if manifest.get("schema") != RESOURCE_PACK_SCHEMA:
        raise Ra2ExplorerError("资源包版本不受支持")
    if manifest.get("kind") != "ra2-explorer-resource-pack":
        raise Ra2ExplorerError("文件不是 RA2 Explorer 资源包")
    if manifest.get("contains_game_files") is not False:
        raise Ra2ExplorerError("资源包声明包含原始游戏文件")
    if manifest.get("derived_schema") != DERIVED_SCHEMA_VERSION:
        raise Ra2ExplorerError("资源包派生格式版本不兼容")
    source = _mapping(manifest.get("source"))
    source_id = str(source.get("id") or "")
    revision = str(source.get("revision") or "")
    snapshot_source = _mapping(snapshot.get("source"))
    if snapshot.get("schema") != 1 or not source_id or not revision:
        raise Ra2ExplorerError("资源包索引不完整")
    if str(snapshot_source.get("id") or "") != source_id:
        raise Ra2ExplorerError("资源包索引与资料库不匹配")
    if str(snapshot_source.get("scanned_at") or "") != revision:
        raise Ra2ExplorerError("资源包索引版本不匹配")
    for key in ("archives", "assets", "segments"):
        if not isinstance(snapshot.get(key), list):
            raise Ra2ExplorerError("资源包索引结构无效")
    archives = [_mapping(row) for row in snapshot["archives"]]
    assets = [_mapping(row) for row in snapshot["assets"]]
    segments = [_mapping(row) for row in snapshot["segments"]]
    if any(str(row.get("source_id") or "") != source_id for row in archives):
        raise Ra2ExplorerError("资源包归档索引包含其他资料库")
    if any(str(row.get("source_id") or "") != source_id for row in assets):
        raise Ra2ExplorerError("资源包资产索引包含其他资料库")
    asset_ids = {str(row.get("id") or "") for row in assets}
    if "" in asset_ids:
        raise Ra2ExplorerError("资源包资产索引缺少 ID")
    if any(str(row.get("asset_id") or "") not in asset_ids for row in segments):
        raise Ra2ExplorerError("资源包片段索引引用了未知资产")

    artifact_prefix = _safe_archive_path(str(manifest.get("artifact_prefix") or ""))
    expected_prefix = f"artifacts/v{DERIVED_SCHEMA_VERSION}/"
    if not artifact_prefix.startswith(expected_prefix):
        raise Ra2ExplorerError("资源包产物目录无效")
    semantic_snapshot = _safe_archive_path(str(manifest.get("semantic_snapshot") or ""))
    if not semantic_snapshot.startswith(f"{artifact_prefix}/metadata/"):
        raise Ra2ExplorerError("资源包缺少语义索引")

    entries = archive.infolist()
    if len(entries) > MAX_RESOURCE_PACK_ENTRIES:
        raise Ra2ExplorerError("资源包文件数量过多")
    if sum(entry.file_size for entry in entries) > MAX_RESOURCE_PACK_CONTENT_BYTES:
        raise Ra2ExplorerError("资源包解压后超过 4 GiB 限制")
    for entry in entries:
        name = _safe_archive_path(entry.filename)
        if entry.flag_bits & 1:
            raise Ra2ExplorerError("资源包不能使用加密条目")
        if (entry.external_attr >> 16) & 0o170000 == 0o120000:
            raise Ra2ExplorerError("资源包不能包含符号链接")
        if name in {"manifest.json", "index.json"} or entry.is_dir():
            continue
        if not name.startswith(f"{artifact_prefix}/"):
            raise Ra2ExplorerError("资源包包含未知文件")
        relative = PurePosixPath(name).relative_to(PurePosixPath(artifact_prefix))
        if len(relative.parts) < 2:
            raise Ra2ExplorerError("资源包产物结构无效")
        kind = relative.parts[0]
        suffix = PurePosixPath(relative.name).suffix.casefold()
        if kind not in _PORTABLE_KINDS or suffix not in _PORTABLE_KINDS[kind]:
            raise Ra2ExplorerError("资源包包含非浏览器派生产物")
    try:
        archive.getinfo(semantic_snapshot)
    except KeyError as error:
        raise Ra2ExplorerError("资源包缺少语义索引") from error
    return source_id, artifact_prefix, semantic_snapshot


def _read_json_entry(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise Ra2ExplorerError(f"资源包缺少 {name}") from error
    if info.file_size > MAX_RESOURCE_PACK_JSON_BYTES:
        raise Ra2ExplorerError("资源包索引过大")
    try:
        payload = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as error:
        raise Ra2ExplorerError("资源包索引无法解析") from error
    return _mapping(payload)


def _safe_archive_path(value: str) -> str:
    if not value or "\\" in value:
        raise Ra2ExplorerError("资源包路径无效")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise Ra2ExplorerError("资源包路径无效")
    return path.as_posix().rstrip("/")


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Ra2ExplorerError("资源包索引结构无效")
    return value


def _next_default_path(root: Path, source_name: str, created_at: datetime) -> Path:
    safe_name = _SAFE_NAME.sub("-", source_name.strip()).strip(".-") or "RA2-Resources"
    base = root / f"{safe_name[:64]}-{created_at:%Y%m%d-%H%M%S}{RESOURCE_PACK_SUFFIX}"
    if not base.exists():
        return base.resolve()
    return root.joinpath(
        f"{safe_name[:56]}-{created_at:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        f"{RESOURCE_PACK_SUFFIX}"
    ).resolve()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


__all__ = [
    "MAX_RESOURCE_PACK_BYTES",
    "RESOURCE_PACK_ROOT_PREFIX",
    "RESOURCE_PACK_SUFFIX",
    "create_resource_pack",
    "import_resource_pack",
    "list_resource_packs",
    "resource_pack_path",
    "validate_resource_pack",
]
