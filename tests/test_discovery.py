from __future__ import annotations

from pathlib import Path

from ra2_explorer import discovery


def test_project_local_official_install_is_discovered(
    tmp_path: Path,
    monkeypatch,
) -> None:
    game_dir = tmp_path / ".runtime" / "RA2MD"
    game_dir.mkdir(parents=True)
    (game_dir / "ra2.mix").write_bytes(b"")
    (game_dir / "ra2md.mix").write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(discovery, "_steam_libraries", lambda: ())
    monkeypatch.setattr(discovery, "_registry_install_paths", lambda: ())
    monkeypatch.setattr(discovery, "_conventional_ea_roots", lambda: ())

    result = discovery.discover_installations()

    assert result["candidates"] == [
        {
            "path": str(game_dir.resolve()),
            "name": "红色警戒 2 + 尤里的复仇（项目本地官方安装）",
            "provider": "项目本地官方安装",
            "edition": "红色警戒 2 + 尤里的复仇",
            "markers": ("ra2.mix", "ra2md.mix"),
        }
    ]
