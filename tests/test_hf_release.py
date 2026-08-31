from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.publish_hf_release import (
    _force_regular_upload,
    _hub_error_detail,
    build_manifest,
    build_resource_part_manifest,
    space_sync_plan,
)


def test_hf_release_script_can_run_from_file_path() -> None:
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run(
        [sys.executable, "scripts/publish_hf_release.py", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert process.returncode == 0
    assert "--resource-pack" in process.stdout
    assert "--space-bundle" in process.stdout
    assert "--force-regular-archive" in process.stdout
    assert "--repo-type" in process.stdout
    assert "--create-repository" in process.stdout


def test_regular_upload_fallback_is_explicitly_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HF_HUB_ENABLE_HF_TRANSFER", raising=False)
    from huggingface_hub import CommitOperationAdd

    archive = tmp_path / "release.zip"
    archive.write_bytes(b"release")
    operation = CommitOperationAdd(
        path_in_repo="releases/release.zip",
        path_or_fileobj=archive,
    )

    _force_regular_upload(operation)

    assert operation._upload_mode == "regular"
    assert operation._should_ignore is False


def test_hf_release_manifest_pins_archive_size_and_digest(tmp_path) -> None:
    archive = tmp_path / "RA2-Explorer-Web-x64.zip"
    archive.write_bytes(b"release archive")

    manifest = build_manifest(
        archive,
        "v0.8.0",
        published_at="2026-08-30T12:00:00Z",
        notes="Release notes",
    )

    assert manifest["version"] == "0.8.0"
    assert manifest["asset"] == {
        "name": "RA2-Explorer-Web-x64.zip",
        "size": 15,
        "digest": "sha256:ee5b3346ede73ba6ea3e552775e029195fe8722044029111b2c3c02448807b19",
        "path": "releases/v0.8.0/RA2-Explorer-Web-x64.zip",
    }


def test_hf_release_error_detail_does_not_dump_request_content() -> None:
    class ExampleError(Exception):
        response = type("Response", (), {"status_code": 503})()
        request_id = "request-123"

    assert _hub_error_detail(ExampleError("private request body")) == (
        "ExampleError · HTTP 503 · request request-123"
    )


def test_space_sync_only_replaces_managed_runtime_files(tmp_path, monkeypatch) -> None:
    bundle = tmp_path / "space"
    (bundle / "frontend").mkdir(parents=True)
    (bundle / "frontend" / "index.html").write_text("app", encoding="utf-8")
    (bundle / "Dockerfile").write_text("runtime", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.publish_hf_release.audit_space_bundle",
        lambda _bundle: None,
    )

    additions, deletions = space_sync_plan(
        bundle,
        [
            ".gitattributes",
            "Dockerfile",
            "index.html",
            "style.css",
            "frontend/assets/old.js",
            "releases/latest.json",
            "resources/default.ra2pack.parts/000-example.part",
            "resources/default.ra2pack.sha256",
        ],
    )

    assert additions == [
        ("Dockerfile", Path(bundle / "Dockerfile")),
        ("frontend/index.html", Path(bundle / "frontend" / "index.html")),
    ]
    assert deletions == ["frontend/assets/old.js", "index.html", "style.css"]


def test_resource_pack_parts_are_deterministic_and_bounded(tmp_path) -> None:
    archive = tmp_path / "sample.ra2pack"
    archive.write_bytes(b"a" * (1024 * 1024) + b"b" * 7)

    manifest, parts = build_resource_part_manifest(
        archive,
        tmp_path / "parts",
        part_bytes=1024 * 1024,
    )

    assert manifest["archive"]["size"] == archive.stat().st_size
    assert len(manifest["parts"]) == 2
    assert [path.stat().st_size for _remote, path in parts] == [1024 * 1024, 7]
    assert parts[0][0].startswith("resources/default.ra2pack.parts/000-")
    repeated, repeated_parts = build_resource_part_manifest(
        archive,
        tmp_path / "parts",
        part_bytes=1024 * 1024,
    )
    assert repeated == manifest
    assert repeated_parts == parts
