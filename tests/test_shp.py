from __future__ import annotations

from pathlib import Path

import pytest

from ra2_explorer.codecs.mix import parse_mix, ra2_mix_hash
from ra2_explorer.codecs.pal import parse_palette
from ra2_explorer.codecs.shp import parse_shp
from ra2_explorer.demo import create_demo_installation
from ra2_explorer.errors import InvalidFormatError


def test_demo_sprite_decodes_and_renders(tmp_path: Path) -> None:
    installation = create_demo_installation(tmp_path / "demo")
    root_data = (installation / "ra2.mix").read_bytes()
    root = parse_mix(root_data)
    nested_entry = next(entry for entry in root.entries if entry.crc == ra2_mix_hash("conquer.mix"))
    nested_data = bytes(root.payload(root_data, nested_entry))
    nested = parse_mix(nested_data)

    sprite_entry = next(entry for entry in nested.entries if entry.crc == ra2_mix_hash("demo.shp"))
    palette_entry = next(entry for entry in nested.entries if entry.crc == ra2_mix_hash("demo.pal"))
    sprite = parse_shp(nested.payload(nested_data, sprite_entry))
    palette = parse_palette(nested.payload(nested_data, palette_entry))
    rendered = sprite.render(4, palette, scale=2)

    assert len(sprite.frames) == 6
    assert sprite.frames[0].compression == 3
    assert rendered.size == (160, 112)
    assert rendered.getbbox() is not None


def test_shp_rejects_crop_outside_canvas() -> None:
    malformed = bytearray(b"\0\0\x10\0\x10\0\x01\0")
    malformed.extend(b"\x0f\0\x0f\0\x08\0\x08\0\0" + b"\0" * 11 + b"\x20\0\0\0")
    malformed.extend(b"\0" * 64)

    with pytest.raises(InvalidFormatError, match="crop exceeds"):
        parse_shp(malformed)
