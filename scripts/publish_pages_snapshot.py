from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from verify_pages_snapshot import SnapshotValidationError, verify_snapshot
except ModuleNotFoundError:  # Imported as scripts.publish_pages_snapshot in tests.
    from scripts.verify_pages_snapshot import SnapshotValidationError, verify_snapshot


DEFAULT_ENDPOINTS = ["https://hf-mirror.com", "https://huggingface.co"]


class SnapshotPublishError(RuntimeError):
    pass


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.removeprefix("export ").strip()] = value.strip().strip('"').strip("'")
    return values


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_manifest(archive: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive) as bundle:
        member = next(
            (
                info
                for info in bundle.infolist()
                if PurePosixPath(info.filename.replace("\\", "/")).name == "manifest.json"
                and len(PurePosixPath(info.filename.replace("\\", "/")).parts) <= 2
            ),
            None,
        )
        if member is None:
            raise SnapshotPublishError("Pages ZIP 中没有根级 manifest.json")
        value = json.loads(bundle.read(member))
    if not isinstance(value, dict):
        raise SnapshotPublishError("Pages ZIP 清单格式无效")
    return value


def _remote_prefix(value: str) -> str:
    candidate = PurePosixPath(value.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise SnapshotPublishError("远端目录必须是安全的相对路径")
    return candidate.as_posix().strip("/")


def _data_manifest(archive: Path, snapshot: dict[str, Any]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "snapshot_id": snapshot["snapshot_id"],
        "archive": archive.name,
        "sha256": _sha256_file(archive),
        "bytes": archive.stat().st_size,
        "unpacked_bytes": snapshot["payload"]["bytes"],
        "units": snapshot["catalog"]["entities"],
        "sounds": snapshot["catalog"]["audio"],
        "contains_original_game_files": False,
    }


def _lock_manifest(
    *,
    repository: str,
    repository_type: str,
    revision: str,
    remote_path: str,
    data: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider": "huggingface",
        "repository": repository,
        "repository_type": repository_type,
        "revision": revision,
        "path": remote_path,
        "snapshot_id": data["snapshot_id"],
        "sha256": data["sha256"],
        "bytes": data["bytes"],
        "unpacked_bytes": data["unpacked_bytes"],
        "units": data["units"],
        "sounds": data["sounds"],
        "endpoints": DEFAULT_ENDPOINTS,
    }


def publish_snapshot(
    archive: Path,
    *,
    repository: str,
    repository_type: str,
    remote_prefix: str,
    auth_value: str,
    write_lock: Path | None,
) -> dict[str, object]:
    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError as error:
        raise SnapshotPublishError("请先安装项目的 release 可选依赖") from error

    resolved = archive.resolve()
    print("[pages] 审计待发布数据包", file=sys.stderr, flush=True)
    try:
        verify_snapshot(resolved)
    except SnapshotValidationError as error:
        raise SnapshotPublishError(str(error)) from error
    snapshot = _snapshot_manifest(resolved)
    data = _data_manifest(resolved, snapshot)
    prefix = _remote_prefix(remote_prefix)
    remote_archive = f"{prefix}/{resolved.name}"
    remote_manifest = f"{prefix}/manifest.json"
    api = HfApi(endpoint="https://huggingface.co", token=auth_value)
    try:
        commit = api.create_commit(
            repo_id=repository,
            repo_type=repository_type,
            commit_message=f"Publish Pages data {snapshot['snapshot_id']}",
            operations=[
                CommitOperationAdd(
                    path_in_repo=remote_manifest,
                    path_or_fileobj=(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
                    ).encode(),
                ),
                CommitOperationAdd(path_in_repo=remote_archive, path_or_fileobj=resolved),
            ],
        )
    except Exception as error:
        raise SnapshotPublishError(
            f"Hugging Face 发布失败：{type(error).__name__}"
        ) from error
    if not commit.oid:
        raise SnapshotPublishError("Hugging Face 没有返回数据提交 ID")
    lock = _lock_manifest(
        repository=repository,
        repository_type=repository_type,
        revision=commit.oid,
        remote_path=remote_archive,
        data=data,
    )
    if write_lock:
        write_lock.parent.mkdir(parents=True, exist_ok=True)
        write_lock.write_text(
            json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return lock


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="发布固定版本的 Pages 精简数据快照")
    parser.add_argument("archive", type=Path, help="通过审计的 Pages ZIP")
    parser.add_argument("--repository", help="Hugging Face 仓库，例如 owner/repository")
    parser.add_argument(
        "--repo-type",
        choices=("space", "dataset", "model"),
        default="space",
        help="Hugging Face 仓库类型",
    )
    parser.add_argument(
        "--remote-prefix",
        default="pages-data/pages-data-v1",
        help="仓库内稳定目录",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".secrets/local.env"),
        help="只在本机读取的凭据文件",
    )
    parser.add_argument(
        "--write-lock",
        type=Path,
        default=Path("packaging/pages-data.json"),
        help="写入供 CI 使用的小型锁定清单",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    values = _load_env_file(args.env_file)
    repository = args.repository or os.environ.get("HF_SPACE_RELEASE_REPO") or values.get(
        "HF_SPACE_RELEASE_REPO", ""
    )
    auth_value = os.environ.get("HF_TOKEN_RELEASE") or values.get("HF_TOKEN_RELEASE", "")
    if not repository or not auth_value:
        print(
            "pages snapshot publish failed: 缺少 HF_SPACE_RELEASE_REPO 或 HF_TOKEN_RELEASE",
            file=sys.stderr,
        )
        return 1
    try:
        result = publish_snapshot(
            args.archive,
            repository=repository,
            repository_type=args.repo_type,
            remote_prefix=args.remote_prefix,
            auth_value=auth_value,
            write_lock=args.write_lock,
        )
    except (OSError, SnapshotPublishError, ValueError, zipfile.BadZipFile) as error:
        print(f"pages snapshot publish failed: {error}", file=sys.stderr)
        return 1
    print(
        "pages snapshot publish passed "
        f"({result['snapshot_id']}, revision {str(result['revision'])[:12]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
