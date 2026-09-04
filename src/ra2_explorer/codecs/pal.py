from __future__ import annotations

import colorsys
from dataclasses import dataclass

from PIL import Image

from ra2_explorer.errors import InvalidFormatError

PALETTE_COLORS = 256
PALETTE_BYTES = PALETTE_COLORS * 3
# RA2 unit palettes fill indices 204-239 with this marker instead of real art,
# so art painted with those indices needs a terrain palette to render.
PLACEHOLDER_MAGENTA = (252, 0, 252)
PLAYER_COLOR_PRESETS = {
    "red": (214, 59, 52),
    "blue": (61, 111, 198),
    "green": (65, 150, 91),
    "yellow": (224, 184, 54),
    "orange": (220, 120, 45),
    "purple": (143, 82, 181),
    "cyan": (55, 165, 180),
    "gray": (150, 154, 162),
}


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

    def placeholder_indices(self) -> frozenset[int]:
        """Indices filled with the magenta marker, which are never real art."""
        return frozenset(
            index
            for index in range(1, PALETTE_COLORS)
            if self.colors[index] == PLACEHOLDER_MAGENTA
        )

    def remap(
        self,
        color: tuple[int, int, int],
        *,
        start: int = 16,
        end: int = 31,
    ) -> Palette:
        if not 0 <= start <= end < PALETTE_COLORS:
            raise ValueError("palette remap range must be between 0 and 255")
        if any(component < 0 or component > 255 for component in color):
            raise ValueError("player color components must be between 0 and 255")
        hue, saturation, target_value = colorsys.rgb_to_hsv(
            color[0] / 255,
            color[1] / 255,
            color[2] / 255,
        )
        selected = self.colors[start : end + 1]
        source_values = [max(item) / 255 for item in selected]
        lowest = min(source_values)
        highest = max(source_values)
        colors = list(self.colors)
        for offset, source_value in enumerate(source_values):
            if highest - lowest > 0.05:
                brightness = (source_value - lowest) / (highest - lowest)
            elif len(source_values) > 1:
                brightness = offset / (len(source_values) - 1)
            else:
                brightness = 1.0
            red, green, blue = colorsys.hsv_to_rgb(
                hue,
                max(0.35, saturation),
                target_value * (0.22 + brightness * 0.78),
            )
            colors[start + offset] = (
                round(red * 255),
                round(green * 255),
                round(blue * 255),
            )
        return Palette(tuple(colors))

    def with_player_color(
        self,
        name: str,
        *,
        start: int = 16,
        end: int = 31,
    ) -> Palette:
        try:
            color = PLAYER_COLOR_PRESETS[name]
        except KeyError as error:
            raise ValueError(f"unknown player color: {name}") from error
        return self.remap(color, start=start, end=end)


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


__all__ = [
    "PLACEHOLDER_MAGENTA",
    "PLAYER_COLOR_PRESETS",
    "Palette",
    "grayscale_palette",
    "parse_palette",
]
