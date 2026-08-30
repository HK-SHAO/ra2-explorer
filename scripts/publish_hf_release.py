from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from ra2_explorer.resource_pack import validate_resource_pack
from ra2_explorer.updates import (
    OFFICIAL_HF_ENDPOINT,
    UPDATE_ASSET_NAME,
    UPDATE_REPOSITORY,
)

if __package__:
    from scripts.prepare_hf_space import audit_space_bundle
else:
    from prepare_hf_space import audit_space_bundle

_VERSION_PATTERN = re.compile(r"^v?(\d+\.\d+\.\d+)$")
_SPACE_MANAGED_ROOT_FILES = frozenset(
    {".dockerignore", "Dockerfile", "LICENSE", "README.md"}
)
_SPACE_MANAGED_PREFIXES = ("app/", "config/", "frontend/")
_SPACE_LEGACY_FILES = frozenset({"index.html", "style.css"})
_RESOURCE_PART_BYTES = 4 * 1024 * 1024
_RESOURCE_UPLOAD_BATCH = 3
_RESOURCE_PARTS_PREFIX = "resources/default.ra2pack.parts/"
_RESOURCE_PARTS_MANIFEST = "resources/default.ra2pack.parts.json"
_RESOURCE_CHECKSUM = "resources/default.ra2pack.sha256"


def build_manifest(
    archive: Path,
    version: str,
    *,
    published_at: str | None = None,
    notes: str = "",
) -> dict[str, object]:
    match = _VERSION_PATTERN.fullmatch(version.strip())
    if match is None:
        raise ValueError("version must use semantic versioning")
    normalized = match.group(1)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {
        "schema": 1,
        "channel": "stable",
        "version": normalized,
        "published_at": published_at or datetime.now(UTC).isoformat(),
        "notes": notes[:8_000],
        "release_url": (
            f"https://github.com/{UPDATE_REPOSITORY}/releases/tag/v{normalized}"
        ),
        "asset": {
            "name": UPDATE_ASSET_NAME,
            "size": archive.stat().st_size,
            "digest": f"sha256:{digest.hexdigest()}",
            "path": f"releases/v{normalized}/{UPDATE_ASSET_NAME}",
        },
    }


def publish_release(
    archive: Path,
    version: str,
    *,
    notes: str = "",
    space_bundle: Path | None = None,
    force_regular_archive: bool = False,
) -> None:
    _load_local_release_environment(Path.cwd() / ".secrets" / "local.env")
    token = os.environ.get("HF_TOKEN_RELEASE", "").strip()
    repository = os.environ.get("HF_SPACE_RELEASE_REPO", "").strip()
    if not token or not repository:
        raise RuntimeError("HF release credentials are not configured")
    if archive.name != UPDATE_ASSET_NAME or not archive.is_file():
        raise FileNotFoundError(f"expected release archive: {UPDATE_ASSET_NAME}")

    manifest = build_manifest(archive, version, notes=notes)
    normalized = str(manifest["version"])
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    _prepare_hf_environment()
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

    api = HfApi(endpoint=OFFICIAL_HF_ENDPOINT, token=token)
    archive_operation = CommitOperationAdd(
        path_in_repo=f"releases/v{normalized}/{UPDATE_ASSET_NAME}",
        path_or_fileobj=archive,
    )
    if force_regular_archive:
        _force_regular_upload(archive_operation)
    operations = [
        archive_operation,
        CommitOperationAdd(
            path_in_repo=f"releases/v{normalized}/manifest.json",
            path_or_fileobj=io.BytesIO(encoded),
        ),
        CommitOperationAdd(
            path_in_repo="releases/latest.json",
            path_or_fileobj=io.BytesIO(encoded),
        ),
    ]
    if space_bundle is not None:
        additions, deletions = space_sync_plan(
            space_bundle,
            api.list_repo_files(repo_id=repository, repo_type="space"),
        )
        operations.extend(
            CommitOperationAdd(path_in_repo=path, path_or_fileobj=local_path)
            for path, local_path in additions
        )
        operations.extend(
            CommitOperationDelete(path_in_repo=path)
            for path in deletions
        )
    api.create_commit(
        repo_id=repository,
        repo_type="space",
        operations=operations,
        commit_message=f"Publish RA2 Explorer {normalized}",
    )
    print("Hugging Face release synchronization completed")


def publish_resource_pack(pack_path: Path) -> None:
    _load_local_release_environment(Path.cwd() / ".secrets" / "local.env")
    token = os.environ.get("HF_TOKEN_RELEASE", "").strip()
    repository = os.environ.get("HF_SPACE_RELEASE_REPO", "").strip()
    if not token or not repository:
        raise RuntimeError("HF release credentials are not configured")
    validate_resource_pack(pack_path)
    parts_root = Path.cwd() / ".outputs" / "hf-resource-parts"
    manifest, parts = build_resource_part_manifest(pack_path, parts_root)
    encoded_manifest = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    checksum = f"{manifest['archive']['sha256']}  default.ra2pack\n".encode()

    _prepare_hf_environment(disable_xet=True)
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

    api = HfApi(endpoint=OFFICIAL_HF_ENDPOINT, token=token)
    remote_files = set(api.list_repo_files(repo_id=repository, repo_type="space"))
    pending = [part for part in parts if part[0] not in remote_files]
    batch_total = (len(pending) + _RESOURCE_UPLOAD_BATCH - 1) // _RESOURCE_UPLOAD_BATCH
    for batch_index, offset in enumerate(
        range(0, len(pending), _RESOURCE_UPLOAD_BATCH),
        start=1,
    ):
        batch = pending[offset : offset + _RESOURCE_UPLOAD_BATCH]
        first_index = parts.index(batch[0]) + 1
        last_index = parts.index(batch[-1]) + 1
        print(
            f"Uploading derived resource parts {first_index}-{last_index}/{len(parts)} "
            f"(batch {batch_index}/{batch_total})"
        )
        api.create_commit(
            repo_id=repository,
            repo_type="space",
            operations=[
                CommitOperationAdd(path_in_repo=path, path_or_fileobj=local_path)
                for path, local_path in batch
            ],
            commit_message=f"Upload derived resource batch {batch_index} of {batch_total}",
        )
        remote_files.update(path for path, _local_path in batch)
    if not pending:
        print(f"All {len(parts)} derived resource parts are already uploaded")
    current_parts = {path for path, _local_path in parts}
    stale = sorted(
        path
        for path in remote_files
        if path.startswith(_RESOURCE_PARTS_PREFIX) and path not in current_parts
    )
    if "resources/default.ra2pack" in remote_files:
        stale.append("resources/default.ra2pack")
    operations = [
        CommitOperationAdd(
            path_in_repo=_RESOURCE_PARTS_MANIFEST,
            path_or_fileobj=io.BytesIO(encoded_manifest),
        ),
        CommitOperationAdd(
            path_in_repo=_RESOURCE_CHECKSUM,
            path_or_fileobj=io.BytesIO(checksum),
        ),
        *(CommitOperationDelete(path_in_repo=path) for path in stale),
    ]
    api.create_commit(
        repo_id=repository,
        repo_type="space",
        operations=operations,
        commit_message="Activate derived RA2 Explorer resources",
    )
    print("Hugging Face derived resource synchronization completed")


def publish_space_bundle(space_bundle: Path) -> None:
    _load_local_release_environment(Path.cwd() / ".secrets" / "local.env")
    token = os.environ.get("HF_TOKEN_RELEASE", "").strip()
    repository = os.environ.get("HF_SPACE_RELEASE_REPO", "").strip()
    if not token or not repository:
        raise RuntimeError("HF release credentials are not configured")

    _prepare_hf_environment()
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

    api = HfApi(endpoint=OFFICIAL_HF_ENDPOINT, token=token)
    additions, deletions = space_sync_plan(
        space_bundle,
        api.list_repo_files(repo_id=repository, repo_type="space"),
    )
    api.create_commit(
        repo_id=repository,
        repo_type="space",
        operations=[
            *(
                CommitOperationAdd(path_in_repo=path, path_or_fileobj=local_path)
                for path, local_path in additions
            ),
            *(CommitOperationDelete(path_in_repo=path) for path in deletions),
        ],
        commit_message="Deploy RA2 Explorer Space runtime",
    )
    print("Hugging Face Space runtime synchronization completed")


def build_resource_part_manifest(
    pack_path: Path,
    parts_root: Path,
    *,
    part_bytes: int = _RESOURCE_PART_BYTES,
) -> tuple[dict[str, object], list[tuple[str, Path]]]:
    if part_bytes < 1024 * 1024:
        raise ValueError("resource part size must be at least 1 MiB")
    resolved = pack_path.expanduser().resolve(strict=True)
    parts_root.mkdir(parents=True, exist_ok=True)
    archive_digest = hashlib.sha256()
    part_records: list[dict[str, object]] = []
    local_parts: list[tuple[str, Path]] = []
    with resolved.open("rb") as stream:
        index = 0
        while chunk := stream.read(part_bytes):
            archive_digest.update(chunk)
            digest = hashlib.sha256(chunk).hexdigest()
            name = f"{index:03d}-{digest}.part"
            local_path = parts_root / name
            if not local_path.is_file() or local_path.stat().st_size != len(chunk):
                temporary = local_path.with_suffix(".tmp")
                try:
                    temporary.write_bytes(chunk)
                    os.replace(temporary, local_path)
                finally:
                    temporary.unlink(missing_ok=True)
            path_in_repo = f"{_RESOURCE_PARTS_PREFIX}{name}"
            part_records.append(
                {"name": name, "size": len(chunk), "sha256": digest}
            )
            local_parts.append((path_in_repo, local_path))
            index += 1
    if not part_records:
        raise ValueError("resource pack is empty")
    return (
        {
            "schema": 1,
            "kind": "ra2-explorer-resource-pack-parts",
            "archive": {
                "name": "default.ra2pack",
                "size": resolved.stat().st_size,
                "sha256": archive_digest.hexdigest(),
            },
            "parts": part_records,
        },
        local_parts,
    )


def _force_regular_upload(operation: object) -> None:
    upload_info = getattr(operation, "upload_info", None)
    size = int(getattr(upload_info, "size", 0))
    if size <= 0 or size > 64 * 1024 * 1024:
        raise ValueError("regular upload fallback only supports files up to 64 MiB")
    operation._upload_mode = "regular"  # type: ignore[attr-defined]
    operation._should_ignore = False  # type: ignore[attr-defined]
    operation._remote_oid = None  # type: ignore[attr-defined]


def _prepare_hf_environment(*, disable_xet: bool = False) -> None:
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
    if disable_xet:
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def space_sync_plan(
    bundle: Path,
    remote_files: list[str],
) -> tuple[list[tuple[str, Path]], list[str]]:
    resolved = bundle.expanduser().resolve(strict=True)
    audit_space_bundle(resolved)
    has_resource_parts = any(
        path.startswith(_RESOURCE_PARTS_PREFIX) for path in remote_files
    )
    if _RESOURCE_CHECKSUM not in remote_files or not has_resource_parts:
        raise RuntimeError("Hugging Face Space derived resource pack is missing")
    additions = sorted(
        (
            path.relative_to(resolved).as_posix(),
            path,
        )
        for path in resolved.rglob("*")
        if path.is_file()
    )
    local_files = {path for path, _local_path in additions}
    deletions = sorted(
        path
        for path in remote_files
        if (
            path in _SPACE_LEGACY_FILES
            or path in _SPACE_MANAGED_ROOT_FILES
            or path.startswith(_SPACE_MANAGED_PREFIXES)
        )
        and path not in local_files
    )
    return additions, deletions


def _load_local_release_environment(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    allowed = {"HF_TOKEN_RELEASE", "HF_SPACE_RELEASE_REPO"}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if key in allowed and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("--version")
    parser.add_argument("--notes-file", type=Path)
    parser.add_argument("--space-bundle", type=Path)
    parser.add_argument("--resource-pack", type=Path)
    parser.add_argument("--force-regular-archive", action="store_true")
    args = parser.parse_args()
    if args.resource_pack is not None:
        publish_resource_pack(args.resource_pack.resolve())
    if args.archive is None:
        if args.space_bundle is not None:
            publish_space_bundle(args.space_bundle.resolve())
        elif args.resource_pack is None:
            parser.error("archive, --resource-pack or --space-bundle is required")
        return 0
    if not args.version:
        parser.error("--version is required with archive")
    notes = ""
    if args.notes_file:
        notes = args.notes_file.read_text(encoding="utf-8")
    publish_release(
        args.archive.resolve(),
        args.version,
        notes=notes,
        space_bundle=args.space_bundle.resolve() if args.space_bundle else None,
        force_regular_archive=args.force_regular_archive,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
