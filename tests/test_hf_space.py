from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ra2_explorer.errors import Ra2ExplorerError
from scripts.prepare_hf_space import audit_space_bundle


def _fake_bundle(tmp_path):
    root = tmp_path / "space"
    root.mkdir()
    template_root = Path(__file__).resolve().parents[1] / "packaging" / "huggingface-space"
    for name in (".dockerignore", "Dockerfile", "README.md"):
        (root / name).write_bytes((template_root / name).read_bytes())
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "frontend" / "assets").mkdir(parents=True)
    (root / "frontend" / "index.html").write_text("<main></main>", encoding="utf-8")
    (root / "frontend" / "assets" / "app.js").write_text("export {};", encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "update-channel.json").write_text(
        json.dumps({"schema": 1, "hf_space_repo": "example/ra2-explorer"}),
        encoding="utf-8",
    )
    (root / "app").mkdir()
    with zipfile.ZipFile(root / "app" / "ra2_explorer-0.8.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("ra2_explorer/__init__.py", "__version__ = '0.8.0'")
    return root


def test_space_bundle_is_docker_hosted_and_excludes_development_tree(tmp_path) -> None:
    root = _fake_bundle(tmp_path)

    audit_space_bundle(root)

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "resources/default.ra2pack.parts/" in dockerfile
    assert "sha256sum -c default.ra2pack.sha256" in dockerfile
    assert "RA2_EXPLORER_HOSTED=1" in dockerfile
    assert "COPY src" not in dockerfile
    assert "COPY docs" not in dockerfile


def test_space_bundle_audit_rejects_frontend_source_map(tmp_path) -> None:
    root = _fake_bundle(tmp_path)
    (root / "frontend" / "assets" / "app.js.map").write_text("{}", encoding="utf-8")

    with pytest.raises(Ra2ExplorerError, match="开发文件"):
        audit_space_bundle(root)
