from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from ra2_explorer.errors import InvalidFormatError

PALETTE_COLORS = 256
PALETTE_BYTES = PALETTE_COLORS * 3


@dataclass(frozen=True, slots=True)
class Palette:
    colors: tuple[tuple[int, int, int], ...]

    def rgba(self, index: int, *, transparent_zero: bool = True) -> tuple[int, int, int, int]:
        if not 0 <= index < PALETTE_COLORS:
            raise IndexError("palette index must be between 0 and 255")
        red, green, blue = self.colors[index]
        return red, green, blue, 0 if transparent_zero and index == 0 else 255

    def preview(self, *, cell_size: int = 14) -> Image.Image:
        if cell_size < 1:
            raise ValueError("cell_size must be positive")
        image = Image.new("RGB", (16 * cell_size, 16 * cell_size))
        pixels = image.load()
        for index, color in enumerate(self.colors):
            origin_x = index % 16 * cell_size
            origin_y = index // 16 * cell_size
            for y in range(origin_y, origin_y + cell_size):
                for x in range(origin_x, origin_x + cell_size):
                    pixels[x, y] = color
        return image


def parse_palette(data: bytes | bytearray | memoryview) -> Palette:
    view = memoryview(data)
    if len(view) != PALETTE_BYTES:
        raise InvalidFormatError(f"PAL must contain exactly {PALETTE_BYTES} bytes")
    colors = []
    for offset in range(0, PALETTE_BYTES, 3):
        red, green, blue = view[offset : offset + 3]
        colors.append(((red & 0x3F) << 2, (green & 0x3F) << 2, (blue & 0x3F) << 2))
    return Palette(tuple(colors))


def grayscale_palette() -> Palette:
    return Palette(tuple((index, index, index) for index in range(PALETTE_COLORS)))


__all__ = ["Palette", "grayscale_palette", "parse_palette"]
