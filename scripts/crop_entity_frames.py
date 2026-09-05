"""Crop entity frame preview webp files to their visible content.

The generated SHP/voxel frame previews are rendered on the full logical canvas,
leaving large transparent margins and pushing the subject into a corner. This
pass tightens every `previews/entities/<id>/frame/**.webp` so the subject sits
centered with a small consistent margin. Lossless WebP, in place.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

ALPHA_THRESHOLD = 4
PADDING_RATIO = 0.08


def _visible_bbox(image: Image.Image):
    if "A" not in image.getbands():
        return None
    return image.getchannel("A").getbbox()


def crop_file(path: Path) -> bool:
    image = Image.open(path).convert("RGBA")
    bbox = _visible_bbox(image)
    if bbox is None:
        return False
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return False
    padding = max(2, round(max(width, height) * PADDING_RATIO))
    crop = (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )
    cropped = image.crop(crop)
    cropped.save(path, format="WEBP", lossless=True, method=6)
    return True


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("frontend/dist-pages/data")
    files = sorted(root.rglob("previews/entities/*/frame/*/*.webp"))
    total = len(files)
    done = 0
    skipped = 0
    for index, file in enumerate(files, 1):
        if crop_file(file):
            done += 1
        else:
            skipped += 1
        if index % 200 == 0 or index == total:
            print(f"[crop] {index}/{total}  cropped={done} skipped={skipped}", flush=True)
    print(f"[crop] done: {done} cropped, {skipped} skipped, of {total}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
