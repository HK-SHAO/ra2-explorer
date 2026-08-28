from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from ra2_explorer.codecs.binary import BinaryReader, checked_product
from ra2_explorer.codecs.pal import Palette, grayscale_palette
from ra2_explorer.errors import InvalidFormatError

FILE_HEADER_SIZE = 16
TILE_HEADER_SIZE = 52
FLAG_HAS_EXTRA = 0x01
MAX_TILES = 16_384
MAX_TILE_PIXELS = 65_536
MAX_EXTRA_PIXELS = 1_048_576


@dataclass(frozen=True, slots=True)
class TmpTile:
    index: int
    column: int
    row: int
    x: int
    y: int
    extra_x: int
    extra_y: int
    extra_width: int
    extra_height: int
    flags: int
    height: int
    terrain_type: int
    ramp_type: int
    radar_left: tuple[int, int, int]
    radar_right: tuple[int, int, int]
    iso_pixels: bytes
    depth_pixels: bytes
    extra_pixels: bytes | None
    extra_depth: bytes | None


@dataclass(frozen=True, slots=True)
class TmpFile:
    template_width: int
    template_height: int
    tile_width: int
    tile_height: int
    tiles: tuple[TmpTile | None, ...]

    @property
    def tile_count(self) -> int:
        return sum(tile is not None for tile in self.tiles)

    def render(
        self,
        tile_index: int = 0,
        *,
        palette: Palette | None = None,
        scale: int = 3,
    ) -> Image.Image:
        if not 0 <= tile_index < len(self.tiles):
            raise IndexError("TMP tile is out of range")
        tile = self.tiles[tile_index]
        if tile is None:
            return Image.new(
                "RGBA",
                (self.tile_width * max(1, scale), self.tile_height * max(1, scale)),
                (0, 0, 0, 0),
            )
        active_palette = palette or grayscale_palette()
        local_extra_x = tile.extra_x - (tile.column - tile.row) * self.tile_width // 2
        local_extra_y = tile.extra_y - (tile.column + tile.row) * self.tile_height // 2
        left = min(0, local_extra_x if tile.extra_pixels else 0)
        top = min(0, local_extra_y if tile.extra_pixels else 0)
        right = max(
            self.tile_width,
            local_extra_x + tile.extra_width if tile.extra_pixels else self.tile_width,
        )
        bottom = max(
            self.tile_height,
            local_extra_y + tile.extra_height if tile.extra_pixels else self.tile_height,
        )
        image = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
        pixels = image.load()

        cursor = 0
        row_width = 4
        for y in range(self.tile_height):
            start_x = (self.tile_width - row_width) // 2
            for x in range(row_width):
                color_index = tile.iso_pixels[cursor]
                cursor += 1
                if color_index:
                    pixels[start_x + x - left, y - top] = active_palette.rgba(color_index)
            row_width += 4 if y < self.tile_height // 2 - 1 else -4

        if tile.extra_pixels:
            cursor = 0
            for y in range(tile.extra_height):
                for x in range(tile.extra_width):
                    color_index = tile.extra_pixels[cursor]
                    cursor += 1
                    if color_index:
                        pixels[local_extra_x + x - left, local_extra_y + y - top] = (
                            active_palette.rgba(color_index)
                        )
        factor = max(1, min(scale, 8))
        if factor > 1:
            image = image.resize(
                (image.width * factor, image.height * factor),
                resample=Image.Resampling.NEAREST,
            )
        return image


def parse_tmp(data: bytes | bytearray | memoryview) -> TmpFile:
    reader = BinaryReader(data, format_name="TMP")
    template_width = reader.u32(context="template width")
    template_height = reader.u32(context="template height")
    tile_width = reader.i32(context="tile width")
    tile_height = reader.i32(context="tile height")
    if not template_width or not template_height:
        raise InvalidFormatError("TMP: template dimensions must be positive")
    if tile_width <= 0 or tile_height <= 0 or tile_width % 4 or tile_height % 2:
        raise InvalidFormatError("TMP: tile dimensions are invalid")
    tile_slots = checked_product(
        (template_width, template_height), limit=MAX_TILES, context="TMP tile count"
    )
    iso_size = checked_product(
        (tile_width, tile_height), limit=MAX_TILE_PIXELS * 2, context="TMP tile area"
    ) // 2
    if iso_size > MAX_TILE_PIXELS:
        raise InvalidFormatError("TMP: tile pixel count exceeds the safety limit")
    offsets = [reader.u32(context="tile offset") for _ in range(tile_slots)]
    tiles: list[TmpTile | None] = []
    for index, offset in enumerate(offsets):
        if offset == 0:
            tiles.append(None)
            continue
        if offset < FILE_HEADER_SIZE + tile_slots * 4:
            raise InvalidFormatError(f"TMP: tile {index} overlaps the file header")
        reader.seek(offset)
        x = reader.i32(context="tile x")
        y = reader.i32(context="tile y")
        reader.u32(context="extra data offset")
        reader.u32(context="depth data offset")
        reader.u32(context="extra depth offset")
        extra_x = reader.i32(context="extra x")
        extra_y = reader.i32(context="extra y")
        extra_width = reader.i32(context="extra width")
        extra_height = reader.i32(context="extra height")
        flags = reader.u32(context="tile flags")
        height = reader.u8(context="tile height level")
        terrain_type = reader.u8(context="terrain type")
        ramp_type = reader.u8(context="ramp type")
        radar_left = tuple(reader.u8(context="radar color") for _ in range(3))
        radar_right = tuple(reader.u8(context="radar color") for _ in range(3))
        reader.skip(3)
        if reader.position != offset + TILE_HEADER_SIZE:
            raise InvalidFormatError("TMP: internal tile header layout mismatch")
        iso_pixels = bytes(reader.read(iso_size, context="isometric pixels"))
        depth_pixels = bytes(reader.read(iso_size, context="isometric depth pixels"))
        extra_pixels = None
        extra_depth = None
        if flags & FLAG_HAS_EXTRA:
            if extra_width <= 0 or extra_height <= 0:
                raise InvalidFormatError(f"TMP: tile {index} has invalid extra dimensions")
            extra_size = checked_product(
                (extra_width, extra_height),
                limit=MAX_EXTRA_PIXELS,
                context="TMP extra pixel count",
            )
            extra_pixels = bytes(reader.read(extra_size, context="extra pixels"))
            extra_depth = bytes(reader.read(extra_size, context="extra depth pixels"))
        elif extra_width < 0 or extra_height < 0:
            raise InvalidFormatError(f"TMP: tile {index} has negative extra dimensions")
        tiles.append(
            TmpTile(
                index,
                index % template_width,
                index // template_width,
                x,
                y,
                extra_x,
                extra_y,
                extra_width,
                extra_height,
                flags,
                height,
                terrain_type,
                ramp_type,
                radar_left,  # type: ignore[arg-type]
                radar_right,  # type: ignore[arg-type]
                iso_pixels,
                depth_pixels,
                extra_pixels,
                extra_depth,
            )
        )
    return TmpFile(
        template_width,
        template_height,
        tile_width,
        tile_height,
        tuple(tiles),
    )


__all__ = ["TmpFile", "TmpTile", "parse_tmp"]
