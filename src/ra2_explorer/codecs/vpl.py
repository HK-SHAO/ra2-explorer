from __future__ import annotations

from dataclasses import dataclass

from ra2_explorer.codecs.binary import BinaryReader, checked_product
from ra2_explorer.codecs.pal import Palette, parse_palette
from ra2_explorer.errors import InvalidFormatError

PALETTE_SIZE = 768
LOOKUP_WIDTH = 256
MAX_SECTIONS = 256


@dataclass(frozen=True, slots=True)
class VplFile:
    remap_start: int
    remap_end: int
    palette: Palette
    sections: tuple[bytes, ...]

    @property
    def section_count(self) -> int:
        return len(self.sections)

    def color_index(self, section: int, color: int) -> int:
        if not self.sections:
            return color & 0xFF
        selected = max(0, min(len(self.sections) - 1, section))
        return self.sections[selected][color & 0xFF]


def parse_vpl(data: bytes | bytearray | memoryview) -> VplFile:
    reader = BinaryReader(data, format_name="VPL")
    remap_start = reader.u32(context="remap start")
    remap_end = reader.u32(context="remap end")
    section_count = reader.u32(context="section count")
    reader.u32(context="reserved value")
    if not 1 <= section_count <= MAX_SECTIONS:
        raise InvalidFormatError(f"VPL: section count must be between 1 and {MAX_SECTIONS}")
    lookup_size = checked_product(
        (section_count, LOOKUP_WIDTH),
        limit=MAX_SECTIONS * LOOKUP_WIDTH,
        context="VPL lookup table",
    )
    expected = 16 + PALETTE_SIZE + lookup_size
    if len(data) != expected:
        raise InvalidFormatError(f"VPL: expected {expected} bytes, got {len(data)}")
    palette = parse_palette(bytes(reader.read(PALETTE_SIZE, context="embedded palette")))
    sections = tuple(
        bytes(reader.read(LOOKUP_WIDTH, context=f"lighting section {index}"))
        for index in range(section_count)
    )
    return VplFile(remap_start, remap_end, palette, sections)


__all__ = ["VplFile", "parse_vpl"]
