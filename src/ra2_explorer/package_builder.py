from __future__ import annotations

import gc
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from ra2_explorer import __version__
from ra2_explorer.api import Services
from ra2_explorer.config import (
    PORTABLE_MANIFEST,
    PORTABLE_ROOT_URI,
    application_root,
    load_settings,
)
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.reference_data import sync_audio_transcript, sync_known_names

GAME_DATA_SUFFIXES = frozenset(
    {
        ".aud",
        ".bag",
        ".bik",
        ".csf",
        ".des",
        ".fnt",
        ".hva",
        ".idx",
        ".ini",
        ".lun",
        ".map",
        ".mix",
        ".mmx",
        ".mpr",
        ".pal",
        ".pcx",
        ".shp",
        ".sno",
        ".tem",
        ".tmp",
        ".txt",
        ".ubn",
        ".urb",
        ".vpl",
        ".vqa",
        ".vxl",
        ".wav",
        ".yro",
    }
)
DENIED_GAME_SUFFIXES = frozenset(
    {".bat", ".cmd", ".com", ".dll", ".exe", ".lnk", ".msi", ".pif", ".scr", ".sys"}
)
MARKER_FILE = ".ra2exp-distribution"
DistributionMode = Literal["generic", "linked", "portable"]


def _project_root(start: Path) -> Path | None:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "frontend" / "package.json"
        ).is_file():
            return candidate
    return None


def _run(command: list[str], *, cwd: Path, timeout: int) -> None:
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Ra2ExplorerError(f"发行构建命令失败：{command[0]}") from error
    if process.returncode != 0:
        detail = "\n".join(process.stdout.splitlines()[-12:]).replace(str(cwd), "<project>")
        raise Ra2ExplorerError(
            f"发行构建命令退出码为 {process.returncode}：{command[0]}\n{detail}"
        )


def _build_from_source(project_root: Path, staging: Path) -> Path:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise Ra2ExplorerError("未找到 npm；请先安装 Node.js 18 或更高版本")
    if not (project_root / "frontend" / "node_modules").is_dir():
        raise Ra2ExplorerError("前端依赖尚未安装；请先在 frontend 目录运行 npm ci")
    try:
        import PyInstaller  # noqa: F401
    except ImportError as error:
        raise Ra2ExplorerError("缺少发行依赖；请先运行 pip install -e .[release]") from error

    _run([npm, "run", "build"], cwd=project_root / "frontend", timeout=300)
    dist_path = staging / "dist"
    work_path = staging / "work"
    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(dist_path),
            "--workpath",
            str(work_path),
            str(project_root / "packaging" / "ra2_explorer.spec"),
        ],
        cwd=project_root,
        timeout=900,
    )
    package_root = dist_path / "RA2 Explorer"
    if not package_root.is_dir():
        raise Ra2ExplorerError("PyInstaller 未生成预期的发行目录")
    return package_root


def _copy_frozen_distribution(source_root: Path, staging: Path) -> Path:
    package_root = staging / "RA2 Explorer"
    ignored = shutil.ignore_patterns(".runtime", PORTABLE_MANIFEST, MARKER_FILE)
    shutil.copytree(source_root, package_root, ignore=ignored)
    return package_root


def _safe_output(output: Path, *, source_root: Path, game_root: Path | None) -> Path:
    resolved = output.resolve()
    protected = {Path(resolved.anchor).resolve(), Path.home().resolve(), source_root.resolve()}
    if game_root is not None:
        protected.add(game_root.resolve())
    if resolved in protected or any(resolved in path.parents for path in protected):
        raise Ra2ExplorerError("输出目录不能是磁盘根、用户目录、程序目录或游戏目录的上级")
    if game_root is not None and game_root.resolve() in resolved.parents:
        raise Ra2ExplorerError("输出目录不能位于游戏目录内部")
    if getattr(sys, "frozen", False) and source_root.resolve() in resolved.parents:
        raise Ra2ExplorerError("输出目录不能位于当前发行目录内部")
    return resolved


def _prepare_destination(output: Path, *, overwrite: bool) -> None:
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        return
    if not output.is_dir():
        raise Ra2ExplorerError("输出路径已经存在且不是目录")
    if not any(output.iterdir()):
        output.rmdir()
        return
    if not overwrite:
        raise Ra2ExplorerError("输出目录非空；确认后使用 --overwrite")
    if not (output / MARKER_FILE).is_file():
        raise Ra2ExplorerError("拒绝覆盖没有 RA2 Explorer 发行标记的目录")
    shutil.rmtree(output)


def iter_game_data(game_root: Path) -> Iterable[tuple[Path, Path]]:
    for source in game_root.rglob("*"):
        if not source.is_file() or source.is_symlink():
            continue
        try:
            relative = source.resolve().relative_to(game_root)
        except ValueError:
            continue
        if source.suffix.casefold() in GAME_DATA_SUFFIXES:
            yield source, relative


def copy_game_data(game_root: Path, target_root: Path) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    for source, relative in iter_game_data(game_root):
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        count += 1
        total_bytes += source.stat().st_size
    if count == 0:
        raise Ra2ExplorerError("指定目录中没有可识别的 RA2/YR 资产文件")
    return count, total_bytes


def _copy_reference_data(source_root: Path, package_root: Path) -> None:
    candidates = (
        (
            source_root / ".runtime" / "reference" / "known_names_ra2.txt",
            package_root / ".runtime" / "reference" / "known_names_ra2.txt",
        ),
        (
            source_root / ".runtime" / "reference" / "manifest.json",
            package_root / ".runtime" / "reference" / "manifest.json",
        ),
        (
            source_root / ".runtime" / "RA2MD-Ext" / "reference" / "ra2-audio-transcript.xlsx",
            package_root
            / ".runtime"
            / "RA2MD-Ext"
            / "reference"
            / "ra2-audio-transcript.xlsx",
        ),
        (
            source_root
            / ".runtime"
            / "RA2MD-Ext"
            / "reference"
            / "audio-transcript-manifest.json",
            package_root
            / ".runtime"
            / "RA2MD-Ext"
            / "reference"
            / "audio-transcript-manifest.json",
        ),
        (
            source_root
            / ".runtime"
            / "RA2MD-Ext"
            / "reference"
            / "mission-audio-transcript.json",
            package_root
            / ".runtime"
            / "RA2MD-Ext"
            / "reference"
            / "mission-audio-transcript.json",
        ),
    )
    for source, target in candidates:
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _seal_portable_database(database_path: Path, source_id: str) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE sources SET root_path = ? WHERE id = ?",
            (PORTABLE_ROOT_URI, source_id),
        )


def _write_manifest(
    package_root: Path,
    source: dict[str, object] | None,
    *,
    mode: DistributionMode,
) -> None:
    marker = {
        "schema": 1,
        "version": __version__,
        "mode": mode,
        "includes_game_data": mode == "portable",
        "machine_bound": mode == "linked",
    }
    (package_root / MARKER_FILE).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if mode == "portable" and source is not None:
        manifest = {
            "schema": 1,
            "source_id": source["id"],
            "game_path": ".runtime/RA2MD",
            "name": source["name"],
            "asset_count": source["asset_count"],
        }
        (package_root / PORTABLE_MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _publish_package(package_root: Path, destination: Path) -> None:
    try:
        shutil.copytree(
            package_root,
            destination,
            ignore=shutil.ignore_patterns(MARKER_FILE),
        )
        shutil.copy2(package_root / MARKER_FILE, destination / MARKER_FILE)
    except OSError:
        if destination.exists():
            shutil.rmtree(destination)
        raise


def _remove_staging(path: Path) -> None:
    if not path.exists():
        return
    gc.collect()
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError as error:
            last_error = error
            time.sleep(0.15 * (attempt + 1))
    if last_error is not None:
        raise Ra2ExplorerError("发行目录已生成，但临时构建目录清理失败") from last_error


def _contains_bytes(path: Path, needle: bytes) -> bool:
    overlap = max(0, len(needle) - 1)
    previous = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            data = previous + chunk
            if needle in data:
                return True
            previous = data[-overlap:] if overlap else b""
    return False


def audit_distribution(
    package_root: Path,
    *,
    private_paths: Iterable[Path] = (),
    linked_game_root: Path | None = None,
) -> None:
    required = (package_root / "RA2 Explorer.exe", package_root / "ra2exp.exe")
    if not all(path.is_file() for path in required):
        raise Ra2ExplorerError("发行目录缺少 Windows 启动程序")
    game_root = package_root / ".runtime" / "RA2MD"
    if game_root.is_dir():
        denied = [
            path
            for path in game_root.rglob("*")
            if path.is_file() and path.suffix.casefold() in DENIED_GAME_SUFFIXES
        ]
        if denied:
            raise Ra2ExplorerError("游戏资料目录包含被禁止的可执行文件")
    needles: list[bytes] = []
    for private_path in private_paths:
        value = str(private_path.resolve())
        if len(value) >= 4:
            needles.extend((value.encode("utf-8"), value.encode("utf-16-le")))
    settings = load_settings(working_directory=package_root)
    allowed_private_files = (
        {settings.database_path.resolve()} if linked_game_root is not None else set()
    )
    for file_path in package_root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.resolve() in allowed_private_files:
            continue
        if any(needle and _contains_bytes(file_path, needle) for needle in needles):
            raise Ra2ExplorerError(f"发行文件包含本机绝对路径：{file_path.name}")
    manifest_path = package_root / PORTABLE_MANIFEST
    if manifest_path.is_file():
        with sqlite3.connect(settings.database_path) as connection:
            roots = {str(row[0]) for row in connection.execute("SELECT root_path FROM sources")}
        expected = str((package_root / ".runtime" / "RA2MD").resolve())
        if roots != {expected}:
            raise Ra2ExplorerError("便携索引没有正确重定位")
        _seal_portable_database(
            settings.database_path,
            str(json.loads(manifest_path.read_text(encoding="utf-8"))["source_id"]),
        )
    elif linked_game_root is not None:
        with sqlite3.connect(settings.database_path) as connection:
            roots = {str(row[0]) for row in connection.execute("SELECT root_path FROM sources")}
        if roots != {str(linked_game_root.resolve())}:
            raise Ra2ExplorerError("本地 Web 应用没有正确关联指定游戏目录")


def _directory_stats(root: Path) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_file():
            count += 1
            total_bytes += path.stat().st_size
    return count, total_bytes


def build_windows_package(
    output: Path,
    *,
    game_dir: Path | None = None,
    include_game_data: bool = False,
    sync_reference_data: bool = False,
    overwrite: bool = False,
) -> dict[str, object]:
    source_root = application_root()
    if include_game_data and game_dir is None:
        raise Ra2ExplorerError("--include-game-data 必须与 --game-dir 一起使用")
    game_root: Path | None = None
    if game_dir is not None:
        try:
            game_root = game_dir.expanduser().resolve(strict=True)
        except OSError as error:
            raise Ra2ExplorerError("游戏目录不存在") from error
        if not game_root.is_dir():
            raise Ra2ExplorerError("游戏路径必须是目录")
    destination = _safe_output(output, source_root=source_root, game_root=game_root)
    _prepare_destination(destination, overwrite=overwrite)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ra2exp-package-", dir=destination.parent))
    package_root: Path | None = None
    try:
        if getattr(sys, "frozen", False):
            package_root = _copy_frozen_distribution(source_root, staging)
        else:
            project_root = _project_root(source_root)
            if project_root is None:
                raise Ra2ExplorerError("请从 RA2 Explorer 源码目录运行发行构建")
            package_root = _build_from_source(project_root, staging)
        mode: DistributionMode = "generic"
        source: dict[str, object] | None = None
        copied_files = 0
        copied_bytes = 0
        source_files = 0
        source_bytes = 0
        _copy_reference_data(source_root, package_root)
        settings = None
        if sync_reference_data:
            settings = load_settings(working_directory=package_root)
            sync_known_names(settings.known_names_path)
            sync_audio_transcript(settings.audio_transcript_path)
        if game_root is not None:
            mode = "portable" if include_game_data else "linked"
            indexed_root = game_root
            if include_game_data:
                copied_files, copied_bytes = copy_game_data(
                    game_root,
                    package_root / ".runtime" / "RA2MD",
                )
                source_files = copied_files
                source_bytes = copied_bytes
                indexed_root = package_root / ".runtime" / "RA2MD"
            else:
                source_files, source_bytes = _directory_stats_for_game(game_root)
                if source_files == 0:
                    raise Ra2ExplorerError("指定目录中没有可识别的 RA2/YR 资产文件")
            if settings is None:
                settings = load_settings(working_directory=package_root)
            source = Services(settings).library.import_source(
                indexed_root,
                "红色警戒 2 与尤里的复仇",
            )
            if include_game_data:
                _seal_portable_database(settings.database_path, str(source["id"]))
        _write_manifest(package_root, source, mode=mode)
        audit_distribution(
            package_root,
            private_paths=(
                source_root,
                Path.home(),
                Path(sys.base_prefix),
                Path(sys.prefix),
                *((game_root,) if game_root else ()),
            ),
            linked_game_root=game_root if mode == "linked" else None,
        )
        _publish_package(package_root, destination)
        package_root = None
        distribution_files, distribution_bytes = _directory_stats(destination)
        return {
            "output": str(destination),
            "version": __version__,
            "mode": mode,
            "machine_bound": mode == "linked",
            "includes_game_data": mode == "portable",
            "copied_files": copied_files,
            "copied_bytes": copied_bytes,
            "source_files": source_files,
            "source_bytes": source_bytes,
            "distribution_files": distribution_files,
            "distribution_bytes": distribution_bytes,
            "asset_count": source["asset_count"] if source else 0,
        }
    finally:
        if package_root is not None and package_root.exists():
            _remove_staging(package_root)
        if staging.exists():
            _remove_staging(staging)


def _directory_stats_for_game(game_root: Path) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    for source, _relative in iter_game_data(game_root):
        count += 1
        total_bytes += source.stat().st_size
    return count, total_bytes


__all__ = [
    "DENIED_GAME_SUFFIXES",
    "GAME_DATA_SUFFIXES",
    "audit_distribution",
    "build_windows_package",
    "copy_game_data",
    "iter_game_data",
]
