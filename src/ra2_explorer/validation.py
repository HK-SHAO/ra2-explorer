from __future__ import annotations

import io
import time
from collections.abc import Callable

from PIL import Image, UnidentifiedImageError

from ra2_explorer.codecs.csf import parse_csf
from ra2_explorer.codecs.hva import parse_hva
from ra2_explorer.codecs.pal import parse_palette
from ra2_explorer.codecs.shp import parse_shp
from ra2_explorer.codecs.text import decode_legacy_text, parse_ini
from ra2_explorer.codecs.tmp import parse_tmp
from ra2_explorer.codecs.vxl import parse_vxl
from ra2_explorer.codecs.wav import parse_wav, wav_for_browser
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.library import AssetReader
from ra2_explorer.storage import Database

VALIDATED_FORMATS = (
    "pal",
    "shp",
    "vxl",
    "hva",
    "tmp",
    "csf",
    "ini",
    "map",
    "text",
    "wav",
    "pcx",
)


def validate_source(
    database: Database,
    reader: AssetReader,
    source_id: str,
    *,
    samples_per_format: int = 12,
    formats: tuple[str, ...] = VALIDATED_FORMATS,
) -> dict[str, object]:
    source = database.get_source(source_id)
    sampled = database.sample_assets(
        source_id,
        formats,
        per_format=samples_per_format,
    )
    started = time.perf_counter()
    format_results = []
    errors = []
    checked = 0
    for asset_format, assets in sampled.items():
        passed = 0
        for asset in assets:
            checked += 1
            try:
                current, data = reader.read(str(asset["id"]))
                _validate_asset(str(current["format"]), data)
            except (OSError, Ra2ExplorerError, UnidentifiedImageError, ValueError) as error:
                errors.append(
                    {
                        "asset_id": asset["id"],
                        "name": asset["display_name"],
                        "format": asset_format,
                        "virtual_path": asset["virtual_path"],
                        "error": str(error),
                    }
                )
            else:
                passed += 1
        format_results.append(
            {
                "format": asset_format,
                "sampled": len(assets),
                "passed": passed,
                "failed": len(assets) - passed,
            }
        )
    return {
        "source_id": source_id,
        "source_name": source["name"],
        "status": "passed" if not errors else "failed",
        "checked": checked,
        "samples_per_format": samples_per_format,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "formats": format_results,
        "errors": errors,
    }


def _validate_asset(asset_format: str, data: bytes) -> None:
    validators: dict[str, Callable[[bytes], object]] = {
        "pal": parse_palette,
        "hva": parse_hva,
        "csf": parse_csf,
        "ini": parse_ini,
        "map": parse_ini,
        "text": decode_legacy_text,
        "wav": parse_wav,
    }
    validator = validators.get(asset_format)
    if validator:
        validator(data)
        if asset_format == "wav":
            wav_for_browser(data)
        return
    if asset_format == "shp":
        sprite = parse_shp(data)
        if sprite.frames:
            sprite.render(0, scale=1)
        return
    if asset_format == "vxl":
        model = parse_vxl(data)
        if model.limbs:
            model.render(0, scale=1)
        return
    if asset_format == "tmp":
        template = parse_tmp(data)
        first = next((index for index, tile in enumerate(template.tiles) if tile), None)
        if first is not None:
            template.render(first, scale=1)
        return
    if asset_format == "pcx":
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 16_777_216:
                raise ValueError("PCX preview pixel count exceeds the safety limit")
            image.load()


__all__ = ["VALIDATED_FORMATS", "validate_source"]
