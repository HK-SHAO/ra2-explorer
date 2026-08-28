from __future__ import annotations

import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

STEAM_APP_ID = "2229850"
MAX_DISCOVERY_DIRECTORIES = 5_000
GAME_MARKERS = ("ra2.mix", "ra2md.mix")


@dataclass(frozen=True, slots=True)
class GameInstallation:
    path: str
    name: str
    provider: str
    edition: str
    markers: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def discover_installations() -> dict[str, object]:
    search_roots: list[tuple[Path, str, int]] = [
        (Path.cwd() / ".runtime" / "RA2MD", "项目本地官方安装", 1),
    ]
    for library in _steam_libraries():
        install = _steam_app_install(library)
        if install:
            search_roots.append((install, "Steam", 4))
        common = library / "steamapps" / "common"
        for folder_name in (
            "Command & Conquer Red Alert II",
            "Command and Conquer Red Alert II",
            "Command & Conquer The Ultimate Collection",
        ):
            search_roots.append((common / folder_name, "Steam", 4))

    for root in _registry_install_paths():
        search_roots.append((root, "EA App / 旧版安装", 4))
    for root in _conventional_ea_roots():
        search_roots.append((root, "EA App / Origin", 3))

    found: dict[str, GameInstallation] = {}
    checked: list[str] = []
    for root, provider, depth in search_roots:
        try:
            normalized = root.expanduser().resolve(strict=False)
        except OSError:
            continue
        normalized_key = os.path.normcase(str(normalized))
        if normalized_key not in {os.path.normcase(item) for item in checked}:
            checked.append(str(normalized))
        for game_root in _find_marker_directories(normalized, max_depth=depth):
            markers = tuple(marker for marker in GAME_MARKERS if (game_root / marker).is_file())
            if not markers:
                continue
            edition = _edition(markers)
            key = os.path.normcase(str(game_root))
            found[key] = GameInstallation(
                path=str(game_root),
                name=f"{edition}（{provider}）",
                provider=provider,
                edition=edition,
                markers=markers,
            )
    candidates = sorted(found.values(), key=lambda item: (item.provider, item.path.casefold()))
    return {
        "candidates": [candidate.as_dict() for candidate in candidates],
        "checked_locations": checked,
        "official_sources": [
            {
                "provider": "Steam",
                "url": (
                    "https://store.steampowered.com/app/2229850/"
                    "Command__Conquer_Red_Alert_2_and_Yuris_Revenge/"
                ),
            },
            {
                "provider": "EA App",
                "url": "https://www.ea.com/games/command-and-conquer",
            },
        ],
    }


def _edition(markers: tuple[str, ...]) -> str:
    if set(markers) == set(GAME_MARKERS):
        return "红色警戒 2 + 尤里的复仇"
    if "ra2md.mix" in markers:
        return "尤里的复仇"
    return "红色警戒 2"


def _steam_libraries() -> tuple[Path, ...]:
    roots = {
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Steam",
        Path("D:/Steam"),
        Path("D:/steam"),
    }
    if sys.platform == "win32":
        try:
            import winreg

            for hive, key_name in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        for value_name in ("SteamPath", "InstallPath"):
                            try:
                                value, _ = winreg.QueryValueEx(key, value_name)
                            except OSError:
                                continue
                            if isinstance(value, str) and value:
                                roots.add(Path(value))
                except OSError:
                    continue
        except (ImportError, OSError):
            pass

    libraries = set(roots)
    for root in tuple(roots):
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            content = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for value in re.findall(r'"path"\s+"([^"]+)"', content, flags=re.IGNORECASE):
            libraries.add(Path(value.replace("\\\\", "\\")))
    return tuple(sorted(libraries, key=lambda path: str(path).casefold()))


def _steam_app_install(library: Path) -> Path | None:
    manifest = library / "steamapps" / f"appmanifest_{STEAM_APP_ID}.acf"
    try:
        content = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r'"installdir"\s+"([^"]+)"', content, flags=re.IGNORECASE)
    if not match:
        return None
    return library / "steamapps" / "common" / match.group(1).replace("\\\\", "\\")


def _conventional_ea_roots() -> tuple[Path, ...]:
    program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
    return (
        program_files / "EA Games",
        program_files_x86 / "Origin Games",
        Path("D:/EA Games"),
        Path("D:/EAGames"),
        Path("D:/Origin Games"),
    )


def _registry_install_paths() -> tuple[Path, ...]:
    if sys.platform != "win32":
        return ()
    try:
        import winreg
    except ImportError:
        return ()
    roots = []
    key_specs = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EA Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EA Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Electronic Arts\EA Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Electronic Arts\EA Games"),
        (winreg.HKEY_CURRENT_USER, r"Software\Westwood\Red Alert 2"),
        (winreg.HKEY_CURRENT_USER, r"Software\Westwood\Yuri's Revenge"),
    )
    for hive, key_name in key_specs:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                roots.extend(_paths_from_registry_key(key, winreg, depth=0))
        except OSError:
            continue
    return tuple(roots)


def _paths_from_registry_key(key: object, winreg: object, *, depth: int) -> list[Path]:
    if depth > 3:
        return []
    paths = []
    try:
        subkey_count, value_count, _ = winreg.QueryInfoKey(key)
    except OSError:
        return paths
    for index in range(min(value_count, 128)):
        try:
            name, value, _ = winreg.EnumValue(key, index)
        except OSError:
            continue
        lowered = str(name).replace(" ", "").casefold()
        if isinstance(value, str) and ("install" in lowered or lowered in {"path", "folder"}):
            paths.append(Path(value))
    for index in range(min(subkey_count, 128)):
        try:
            subkey_name = winreg.EnumKey(key, index)
            with winreg.OpenKey(key, subkey_name) as subkey:
                paths.extend(_paths_from_registry_key(subkey, winreg, depth=depth + 1))
        except OSError:
            continue
    return paths


def _find_marker_directories(root: Path, *, max_depth: int) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    queue = [(root, 0)]
    visited = 0
    found = []
    while queue and visited < MAX_DISCOVERY_DIRECTORIES:
        current, depth = queue.pop(0)
        visited += 1
        try:
            if any((current / marker).is_file() for marker in GAME_MARKERS):
                found.append(current.resolve())
                continue
        except OSError:
            continue
        if depth >= max_depth:
            continue
        try:
            children = [
                Path(entry.path)
                for entry in os.scandir(current)
                if entry.is_dir(follow_symlinks=False)
            ]
        except OSError:
            continue
        queue.extend((child, depth + 1) for child in children)
    return tuple(found)


__all__ = ["GameInstallation", "discover_installations"]
