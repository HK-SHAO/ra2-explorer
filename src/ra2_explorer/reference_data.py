from __future__ import annotations

import json
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from ra2_explorer.errors import Ra2ExplorerError

CNC_FORMATS_REVISION = "77da596ed72a1201740e054855bf2ff60640bfa9"
KNOWN_NAMES_URL = (
    "https://raw.githubusercontent.com/iron-curtain-engine/cnc-formats/"
    f"{CNC_FORMATS_REVISION}/src/mix/known_names_ra2.txt"
)

BUILTIN_NAMES = (
    "ra2.mix",
    "language.mix",
    "multi.mix",
    "cache.mix",
    "local.mix",
    "neutral.mix",
    "conquer.mix",
    "generic.mix",
    "isogen.mix",
    "cameo.mix",
    "audio.mix",
    "rules.ini",
    "art.ini",
    "ra2.csf",
    "local mix database.dat",
    "unittem.pal",
    "uniturb.pal",
    "unitsno.pal",
    "unitdes.pal",
    "isotem.pal",
    "temperat.pal",
    "apoc.vxl",
    "apoctur.vxl",
    "apocbarl.vxl",
    "apoc.hva",
    "apoctur.hva",
    "apocbarl.hva",
    "gaweap.shp",
)


def load_known_names(path: Path) -> tuple[str, ...]:
    names = list(BUILTIN_NAMES)
    if path.is_file():
        names.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.startswith("#")
        )
    return tuple(dict.fromkeys(names))


def sync_known_names(path: Path, *, timeout: float = 30.0) -> dict[str, object]:
    request = urllib.request.Request(
        KNOWN_NAMES_URL,
        headers={"User-Agent": "ra2-explorer/0.1 reference-sync"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read(2_000_001)
    except OSError as error:
        raise Ra2ExplorerError(f"名称库下载失败：{error}") from error
    if len(content) > 2_000_000:
        raise Ra2ExplorerError("名称库超过允许的 2 MB")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Ra2ExplorerError("名称库不是有效的 UTF-8 文本") from error
    names = [line.strip() for line in text.splitlines() if line.strip()]
    if len(names) < 1000:
        raise Ra2ExplorerError("名称库内容不完整")

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)

    manifest = {
        "provider": "github",
        "repository": "iron-curtain-engine/cnc-formats",
        "revision": CNC_FORMATS_REVISION,
        "resource": "src/mix/known_names_ra2.txt",
        "url": KNOWN_NAMES_URL,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "name_count": len(names),
    }
    manifest_path = path.with_name("manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def reference_status(path: Path) -> dict[str, object]:
    manifest_path = path.with_name("manifest.json")
    if not path.is_file() or not manifest_path.is_file():
        return {"available": False, "builtin_name_count": len(BUILTIN_NAMES)}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": True, "manifest_valid": False}
    return {"available": True, "manifest_valid": True, **manifest}


__all__ = [
    "BUILTIN_NAMES",
    "CNC_FORMATS_REVISION",
    "load_known_names",
    "reference_status",
    "sync_known_names",
]
