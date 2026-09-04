#!/usr/bin/env python3
"""把库里的 RA2/YR 过场视频排序、统一规格，拼成一支 HEVC 影片并生成 BV 引用清单。

排序线索（从可靠到弱）：
  1. 归属 MIX 决定战役：langmd/language=启动序列、MOVIES01=红警2盟军、
     MOVIES02=红警2苏军、movmd03=尤里的复仇、WDT=战区地图动画
  2. 文件名 <阵营><任务号>_<段类型><序号><语言>：F（简报）在 P（过场）前，数字升序
  3. 同一视频存于多个 MIX 时按 CRC 去重，只保留一份，归入最具体的战役组

产物（写入 --output-dir，均被 Git 忽略）：
  - parts/part-NNN.mov   统一规格后的分片
  - movies.json          合成影片的排序与 BV 时间戳引用清单
  - RA2-过场影片合集-HEVC.mov  无损拼接的成片

分段先统一到 640x480@15fps（等比缩放 + 居中补黑边）、音轨统一 48kHz 立体声
AAC（无音轨补静音），各自 HEVC 编码一次，最后 concat demuxer 无损拼接。
全程只有一次有损编码。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ra2_explorer.api import Services  # noqa: E402
from ra2_explorer.config import Settings, load_settings  # noqa: E402

CANVAS_W, CANVAS_H = 640, 480
FPS = 15
QUALITY = 60
GROUP_ORDER = [
    "intro", "ra2-ally", "ra2-soviet", "yr-ally", "yr-soviet", "world", "promo", "unknown",
]
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
        if any(mix in mixes for mix in ("MOVIES01.MIX", "MOVIES02.MIX")):
            group = "ra2-ally" if side == "A" else "ra2-soviet"
        elif "movmd03.mix" in mixes:
            group = "yr-ally" if side == "A" else "yr-soviet"
        else:
            group = "unknown"
        return group, f"{side}-{mission}-{kind}{index}-{lang}-{name}"
    return "unknown", f"99-{name}"


def unique_videos(services: Services, source_id: str) -> list[dict[str, object]]:
    assets = services.database.list_assets(
        source_id=source_id, asset_format="video", limit=300
    )["items"]
    merged: dict[int, dict[str, object]] = {}
    for asset in assets:
        crc = int(asset["crc"])
        entry = merged.setdefault(crc, {**asset, "mixes": [str(asset["virtual_path"])]})
        mixes = str(entry["mixes"][0])
        virtual = str(asset["virtual_path"])
        if mixes not in entry["mixes"]:
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


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def encode_part(ffmpeg: str, services: Services, asset_id: str, out_path: Path) -> None:
    _, data = services.reader.read(asset_id)
    with tempfile.NamedTemporaryFile(suffix=".bik", delete=False) as handle:
        handle.write(data)
        source = handle.name
    try:
        video_filter = (
            f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease"
            f":flags=lanczos,pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={FPS}"
        )
        command = [
            ffmpeg, "-y", "-i", source,
            "-filter_complex",
            f"[0:v]{video_filter}[v];[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "hevc_videotoolbox", "-q:v", str(QUALITY), "-tag:v", "hvc1",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            str(out_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0 or not out_path.is_file():
            raise RuntimeError(result.stderr[-500:] or "未知错误")
    finally:
        os.unlink(source)


def main() -> int:
    parser = argparse.ArgumentParser(description="合成 RA2 过场影片并生成 BV 引用清单")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".outputs" / "ra2-movies")
    parser.add_argument("--bvid", default="", help="成片上传 B 站后的 BV 号，写入引用清单")
    parser.add_argument("--skip-encode", action="store_true", help="复用已有分片，只重建清单")
    args = parser.parse_args()

    settings: Settings = load_settings(working_directory=ROOT)
    services = Services(settings)
    ffmpeg = "ffmpeg"
    output_dir = args.output_dir
    parts_dir = output_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    ordered = unique_videos(services, args.source_id)
    print(f"唯一视频 {len(ordered)} 段", flush=True)

    for index, item in enumerate(ordered, 1):
        item["part"] = f"part-{index:03d}.mov"

    if not args.skip_encode:
        for index, item in enumerate(ordered, 1):
            out_path = parts_dir / str(item["part"])
            if out_path.is_file() and out_path.stat().st_size > 0:
                name = item["display_name"]
                print(f"  [{index:03d}/{len(ordered)}] {name} 已存在，跳过", flush=True)
                continue
            try:
                encode_part(ffmpeg, services, str(item["id"]), out_path)
                print(f"  [{index:03d}/{len(ordered)}] {item['display_name']} ✓", flush=True)
            except Exception:  # noqa: BLE001
                print(f"  [{index:03d}/{len(ordered)}] {item['display_name']} ✗", flush=True)

    items = []
    start = 0.0
    missing = []
    part_names = []
    for item in ordered:
        part = parts_dir / str(item["part"])
        if not part.is_file():
            missing.append(str(item["display_name"]))
            continue
        duration = probe_duration(part)
        part_names.append(f"parts/{item['part']}")
        items.append({
            "asset_id": str(item["id"]),
            "name": str(item["display_name"]),
            "crc": int(item["crc"]),
            "size": int(item["size"]),
            "group": item["group"],
            "start": round(start, 2),
            "duration": round(duration, 2),
        })
        start += duration
    if missing:
        (output_dir / "missing.txt").write_text("\n".join(missing) + "\n", encoding="utf-8")
        print(f"缺 {len(missing)} 段分片，见 missing.txt")

    manifest = {
        "bvid": args.bvid,
        "canvas": [CANVAS_W, CANVAS_H],
        "fps": FPS,
        "total_duration": round(start, 2),
        "items": items,
    }
    (output_dir / "movies.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"引用清单：{output_dir / 'movies.json'}（{len(items)} 段，共 {start / 60:.1f} 分钟）")

    concat = output_dir / "concat.txt"
    concat.write_text(
        "\n".join(f"file '{name}'" for name in part_names) + "\n", encoding="utf-8"
    )
    if args.skip_encode:
        return 0
    final = output_dir / "RA2-过场影片合集-HEVC.mov"
    result = subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", "-movflags", "+faststart", str(final)],
        capture_output=True, text=True, timeout=3600,
    )
    if result.returncode != 0:
        print("拼接失败:", result.stderr[-500:], file=sys.stderr)
        return 1
    print(f"成片：{final}（{final.stat().st_size / 1e6:.0f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
