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

    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

    api = HfApi(endpoint=OFFICIAL_HF_ENDPOINT, token=token)
    operations = [
        CommitOperationAdd(
            path_in_repo=f"releases/v{normalized}/{UPDATE_ASSET_NAME}",
            path_or_fileobj=archive,
        ),
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

    from huggingface_hub import HfApi

    api = HfApi(endpoint=OFFICIAL_HF_ENDPOINT, token=token)
    api.upload_file(
        path_or_fileobj=pack_path,
        path_in_repo="resources/default.ra2pack",
        repo_id=repository,
        repo_type="space",
        commit_message="Update derived RA2 Explorer resources",
    )
    print("Hugging Face derived resource synchronization completed")


def space_sync_plan(
    bundle: Path,
    remote_files: list[str],
) -> tuple[list[tuple[str, Path]], list[str]]:
    resolved = bundle.expanduser().resolve(strict=True)
    audit_space_bundle(resolved)
    if "resources/default.ra2pack" not in remote_files:
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
    args = parser.parse_args()
    if args.resource_pack is not None:
        publish_resource_pack(args.resource_pack.resolve())
    if args.archive is None:
        if args.resource_pack is None:
            parser.error("archive or --resource-pack is required")
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
