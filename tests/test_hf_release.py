from __future__ import annotations

from pathlib import Path

from scripts.publish_hf_release import build_manifest, space_sync_plan


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
            "resources/default.ra2pack",
        ],
    )

    assert additions == [
        ("Dockerfile", Path(bundle / "Dockerfile")),
        ("frontend/index.html", Path(bundle / "frontend" / "index.html")),
    ]
    assert deletions == ["frontend/assets/old.js", "index.html", "style.css"]
