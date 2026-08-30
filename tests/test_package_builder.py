from __future__ import annotations

from pathlib import Path

import pytest

import ra2_explorer.package_builder as package_builder
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.package_builder import audit_distribution, copy_game_data


def test_copy_game_data_keeps_assets_and_excludes_executables(tmp_path: Path) -> None:
    source = tmp_path / "game"
    target = tmp_path / "portable"
    (source / "maps").mkdir(parents=True)
    (source / "ra2.mix").write_bytes(b"mix")
    (source / "maps" / "sample.map").write_bytes(b"map")
    (source / "game.exe").write_bytes(b"executable")
    (source / "renderer.dll").write_bytes(b"library")

    count, total_bytes = copy_game_data(source, target)

    assert count == 2
    assert total_bytes == 6
    assert (target / "ra2.mix").read_bytes() == b"mix"
    assert (target / "maps" / "sample.map").read_bytes() == b"map"
    assert not (target / "game.exe").exists()
    assert not (target / "renderer.dll").exists()


def test_distribution_audit_rejects_build_machine_paths(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "RA2 Explorer.exe").write_bytes(b"launcher")
    (package / "ra2exp.exe").write_bytes(b"cli")
    private_root = tmp_path / "private-workspace"
    (package / "leak.txt").write_text(str(private_root.resolve()), encoding="utf-8")

    with pytest.raises(Ra2ExplorerError, match="本机绝对路径"):
        audit_distribution(package, private_paths=(private_root,))


def test_distribution_audit_ignores_upstream_paths_in_native_dependencies(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "RA2 Explorer.exe").write_bytes(b"launcher")
    (package / "ra2exp.exe").write_bytes(b"cli")
    public_ci_root = tmp_path / "runner-home"
    (package / "third-party.pyd").write_bytes(str(public_ci_root.resolve()).encode())

    audit_distribution(package, private_paths=(public_ci_root,))


def test_distribution_audit_allows_only_linked_path_in_local_index(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "RA2 Explorer.exe").write_bytes(b"launcher")
    (package / "ra2exp.exe").write_bytes(b"cli")
    database = package / ".runtime" / "RA2MD-Ext" / "index" / "ra2-explorer.db"
    database.parent.mkdir(parents=True)
    game_root = tmp_path / "official-game"
    game_root.mkdir()
    import sqlite3

    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sources (root_path TEXT NOT NULL)")
        connection.execute("INSERT INTO sources VALUES (?)", (str(game_root.resolve()),))

    audit_distribution(
        package,
        private_paths=(game_root,),
        linked_game_root=game_root,
    )


def test_package_cli_requires_explicit_flag_to_copy_game_data() -> None:
    from ra2_explorer.cli import build_parser

    linked = build_parser().parse_args(["package", "--game-dir", "game"])
    portable = build_parser().parse_args(
        ["package", "--game-dir", "game", "--include-game-data"]
    )

    assert linked.include_game_data is False
    assert portable.include_game_data is True


def test_staging_cleanup_retries_windows_file_locks(tmp_path: Path, monkeypatch) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.db").write_bytes(b"sqlite")
    original = package_builder.shutil.rmtree
    attempts = 0

    def remove_with_one_lock(path: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporarily locked")
        original(path)

    monkeypatch.setattr(package_builder.shutil, "rmtree", remove_with_one_lock)
    monkeypatch.setattr(package_builder.time, "sleep", lambda _seconds: None)

    removed = package_builder._remove_staging(staging)

    assert removed is True
    assert attempts == 2
    assert not staging.exists()


def test_staging_cleanup_does_not_mask_a_completed_distribution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()

    def always_locked(_path: Path) -> None:
        raise PermissionError("held by indexing service")

    monkeypatch.setattr(package_builder.shutil, "rmtree", always_locked)
    monkeypatch.setattr(package_builder.time, "sleep", lambda _seconds: None)

    assert package_builder._remove_staging(staging) is False
    assert staging.exists()
