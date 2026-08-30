from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from ra2_explorer.updates import (
    OFFICIAL_HF_ENDPOINT,
    UPDATE_ASSET_NAME,
    UPDATE_REPOSITORY,
)

_VERSION_PATTERN = re.compile(r"^v?(\d+\.\d+\.\d+)$")


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


def publish_release(archive: Path, version: str, *, notes: str = "") -> None:
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

    from huggingface_hub import CommitOperationAdd, HfApi

    api = HfApi(endpoint=OFFICIAL_HF_ENDPOINT, token=token)
    api.create_commit(
        repo_id=repository,
        repo_type="space",
        operations=[
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
        ],
        commit_message=f"Publish RA2 Explorer {normalized}",
    )
    print("Hugging Face release synchronization completed")


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
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--notes-file", type=Path)
    args = parser.parse_args()
    notes = ""
    if args.notes_file:
        notes = args.notes_file.read_text(encoding="utf-8")
    publish_release(args.archive.resolve(), args.version, notes=notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
