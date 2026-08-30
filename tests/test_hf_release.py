from __future__ import annotations

from scripts.publish_hf_release import build_manifest


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
