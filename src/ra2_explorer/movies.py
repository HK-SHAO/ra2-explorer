"""把过场视频按线索排序、统一规格，拼成一支 HEVC 影片并生成 BV 引用清单。

排序线索（从可靠到弱）：归属 MIX 决定战役；文件名
`<阵营><任务号>_<段类型><序号><语言>` 决定任务与段落；同一视频存于多个
MIX 时按 CRC 去重。分段统一到 640x480@15fps 后各自 HEVC 编码一次，
最后 concat 无损拼接。全程只有一次有损编码。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from ra2_explorer.api import Services
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.video import extract_poster_frame

CANVAS = (640, 480)
FPS = 15
QUALITY = 60
GROUP_ORDER = (
    "intro", "ra2-ally", "ra2-soviet", "yr-ally", "yr-soviet", "world", "promo", "unknown",
)
INTRO_ORDER = {"WESTLOGO.BIK": 0, "EA_WWLOGO.BIK": 1, "RA2TS_L.BIK": 2, "RA2TS_S.BIK": 3}
NAME_PATTERN = re.compile(r"([AS])(\d{2})_([FP])(\d{2})([A-Z]*)\.BIK")


def classify(mixes: list[str], name: str) -> tuple[str, str]:
    upper = name.upper()
    if upper in INTRO_ORDER or upper.startswith(("WESTLOGO", "EA_WWLOGO", "RA2TS")):
        return "intro", f"{INTRO_ORDER.get(upper, 9):02d}-{name}"
    if upper.startswith("EMPRTRLR"):
        return "promo", f"00-{name}"
    if "WDT.MIX" in mixes:
        return "world", f"00-{name}"
    match = NAME_PATTERN.match(upper)
    if match:
        side, mission, kind, index, lang = match.groups()
        if {"MOVIES01.MIX", "MOVIES02.MIX"} & set(mixes):
            group = "ra2-ally" if side == "A" else "ra2-soviet"
        elif "movmd03.mix" in mixes:
            group = "yr-ally" if side == "A" else "yr-soviet"
        else:
            group = "unknown"
        return group, f"{side}-{mission}-{kind}{index}-{lang}-{name}"
    return "unknown", f"99-{name}"


def _unique_videos(services: Services, source_id: str) -> list[dict[str, object]]:
    assets = services.database.list_assets(
        source_id=source_id, asset_format="video", limit=300
    )["items"]
    merged: dict[int, dict[str, object]] = {}
    for asset in assets:
        identity = int(asset["crc"])
        entry = merged.setdefault(identity, {**asset, "mixes": [str(asset["virtual_path"])]})
        virtual = str(asset["virtual_path"])
        if virtual not in entry["mixes"]:
            entry["mixes"].append(virtual)
    ordered = []
    for entry in merged.values():
        mixes = [str(item).split("::", 1)[0].rsplit("/", 1)[-1] for item in entry["mixes"]]
        group, key = classify(mixes, str(entry["display_name"]))
        ordered.append({**entry, "group": group, "group_key": key})
    ordered.sort(key=lambda item: (
        GROUP_ORDER.index(item["group"]), item["group_key"], str(item["display_name"])
    ))
    return ordered


def _extract_poster(ffmpeg: str, part: Path, output: Path) -> None:
    """抽一帧存为 WebP 预览图；抽帧含暗帧检测与首帧回退。"""
    temporary = output.with_suffix(".tmp.png")
    try:
        ok, _ = extract_poster_frame(ffmpeg, part, temporary)
        if not ok:
            return
        with Image.open(temporary) as image:
            image.save(output, format="WEBP", quality=75, method=4)
    except OSError:
        pass
    finally:
        temporary.unlink(missing_ok=True)


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _encode_part(ffmpeg: str, services: Services, asset_id: str, out_path: Path) -> None:
    _, data = services.reader.read(asset_id)
    with tempfile.NamedTemporaryFile(suffix=".bik", delete=False) as handle:
        handle.write(data)
        source = Path(handle.name)
    width, height = CANVAS
    try:
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS}"
        )
        command = [
            ffmpeg, "-y", "-i", str(source),
            "-filter_complex",
            f"[0:v]{video_filter}[v];[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "hevc_videotoolbox", "-q:v", str(QUALITY), "-tag:v", "hvc1",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            str(out_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0 or not out_path.is_file():
            raise Ra2ExplorerError(f"分片编码失败：{result.stderr[-400:] or '未知错误'}")
    finally:
        source.unlink(missing_ok=True)


def build_movie_compilation(
    services: Services,
    source_id: str,
    *,
    output_dir: Path,
    bvid: str = "",
    skip_encode: bool = False,
    overwrite: bool = False,
) -> dict[str, object]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise Ra2ExplorerError("未找到 FFmpeg；请安装后重试")
    output_dir = output_dir.resolve()
    parts_dir = output_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    ordered = _unique_videos(services, source_id)
    if not ordered:
        raise Ra2ExplorerError("资料库中没有可用的过场视频")
    for index, item in enumerate(ordered, 1):
        item["part"] = f"part-{index:03d}.mov"

    failures: list[str] = []
    if not skip_encode:
        for index, item in enumerate(ordered, 1):
            out_path = parts_dir / str(item["part"])
            if out_path.is_file() and out_path.stat().st_size > 0:
                continue
            try:
                _encode_part(ffmpeg, services, str(item["id"]), out_path)
                print(f"  [{index:03d}/{len(ordered)}] {item['display_name']} ✓", flush=True)
            except (Ra2ExplorerError, OSError, RuntimeError):
                failures.append(str(item["display_name"]))
                print(f"  [{index:03d}/{len(ordered)}] {item['display_name']} ✗", flush=True)

    items: list[dict[str, object]] = []
    part_names: list[str] = []
    posters_dir = output_dir / "posters"
    posters_dir.mkdir(parents=True, exist_ok=True)
    start = 0.0
    for item in ordered:
        part = parts_dir / str(item["part"])
        if not part.is_file():
            continue
        poster = posters_dir / f"{item['id']}.webp"
        if not poster.is_file():
            _extract_poster(ffmpeg, part, poster)
        item["poster"] = f"movies/{item['id']}.webp" if poster.is_file() else None
        duration = _probe_duration(part)
        part_names.append(f"parts/{item['part']}")
        items.append({
            "asset_id": str(item["id"]),
            "name": str(item["display_name"]),
            "crc": int(item["crc"]),
            "size": int(item["size"]),
            "group": item["group"],
            "start": round(start, 2),
            "duration": round(duration, 2),
            "poster": item["poster"],
        })
        start += duration

    manifest = {
        "bvid": bvid,
        "canvas": list(CANVAS),
        "fps": FPS,
        "total_duration": round(start, 2),
        "items": items,
    }
    manifest_path = output_dir / "movies.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    final = output_dir / "RA2-过场影片合集-HEVC.mov"
    encoded = 0
    if not skip_encode:
        concat = output_dir / "concat.txt"
        lines = [f"file '{name}'" for name in part_names]
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
             "-c", "copy", "-movflags", "+faststart", str(final)],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            raise Ra2ExplorerError(f"影片拼接失败：{result.stderr[-400:]}")
        encoded = 1
    if failures:
        raise Ra2ExplorerError(f"有 {len(failures)} 段编码失败：{'、'.join(failures)}")
    return {
        "manifest": str(manifest_path),
        "items": len(items),
        "total_duration": round(start, 2),
        "bvid": bvid,
        "film": str(final) if encoded else None,
    }
