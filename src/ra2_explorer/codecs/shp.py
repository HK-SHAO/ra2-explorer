from __future__ import annotations

import struct
from dataclasses import dataclass

from PIL import Image

from ra2_explorer.codecs.pal import Palette, grayscale_palette
from ra2_explorer.errors import InvalidFormatError, UnsupportedFormatError

FILE_HEADER_SIZE = 8
FRAME_HEADER_SIZE = 24
MAX_FRAMES = 4096
MAX_DIMENSION = 4096
MAX_FRAME_PIXELS = 16_777_216


@dataclass(frozen=True, slots=True)
class ShpFrame:
    index: int
    x: int
    y: int
    width: int
    height: int
    compression: int
    data_offset: int

    @property
    def empty(self) -> bool:
        return (
            self.width == 0
            or self.height == 0
            or self.data_offset in {0, 0xCCCCCCCC}
            or self.compression == 4
        )


@dataclass(frozen=True, slots=True)
class ShpFile:
    width: int
    height: int
    frames: tuple[ShpFrame, ...]
    _data: bytes

    def pixels(self, frame_index: int) -> bytes:
        try:
            frame = self.frames[frame_index]
        except IndexError as error:
            raise IndexError("SHP frame index is out of range") from error
        if frame.empty:
            return bytes(frame.width * frame.height)

        cursor = frame.data_offset
        if frame.compression in (0, 1):
            size = frame.width * frame.height
            end = cursor + size
            if end > len(self._data):
                raise InvalidFormatError(f"SHP frame {frame_index} pixel data is truncated")
            return self._data[cursor:end]
        if frame.compression == 2:
            return self._decode_scanlines(frame, compressed=False)
        if frame.compression == 3:
            return self._decode_scanlines(frame, compressed=True)
        raise UnsupportedFormatError(
            f"SHP frame {frame_index} uses compression {frame.compression}"
        )

    def _decode_scanlines(self, frame: ShpFrame, *, compressed: bool) -> bytes:
        output = bytearray(frame.width * frame.height)
        cursor = frame.data_offset
        for row in range(frame.height):
            if cursor + 2 > len(self._data):
                raise InvalidFormatError(f"SHP frame {frame.index} scanline header is truncated")
            encoded_size = struct.unpack_from("<H", self._data, cursor)[0]
            if encoded_size < 2:
                raise InvalidFormatError(f"SHP frame {frame.index} has an invalid scanline size")
            line_end = cursor + encoded_size
            cursor += 2
            if line_end > len(self._data):
                raise InvalidFormatError(f"SHP frame {frame.index} scanline is truncated")

            row_start = row * frame.width
            if not compressed:
                line = self._data[cursor:line_end]
                copy_size = min(len(line), frame.width)
                output[row_start : row_start + copy_size] = line[:copy_size]
                cursor = line_end
                continue

            column = 0
            while cursor < line_end and column < frame.width:
                value = self._data[cursor]
                cursor += 1
                if value:
                    output[row_start + column] = value
                    column += 1
                    continue
                if cursor >= line_end:
                    raise InvalidFormatError(
                        f"SHP frame {frame.index} ends inside a transparent run"
                    )
                run = self._data[cursor]
                cursor += 1
                column = min(frame.width, column + run)
            cursor = line_end
        return bytes(output)

    def render(
        self,
        frame_index: int,
        palette: Palette | None = None,
        *,
        scale: int = 1,
        shadow_frame: int | None = None,
    ) -> Image.Image:
        if scale < 1 or scale > 16:
            raise ValueError("scale must be between 1 and 16")
        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if shadow_frame is not None:
            shadow = self._render_frame(shadow_frame, palette, shadow=True)
            canvas.alpha_composite(shadow)
        canvas.alpha_composite(self._render_frame(frame_index, palette))
        if scale != 1:
            scaled_size = (self.width * scale, self.height * scale)
            canvas = canvas.resize(scaled_size, Image.Resampling.NEAREST)
        return canvas

    def paired_shadow_frame(self, frame_index: int) -> int | None:
        """Return the matching second-half Westwood shadow frame when present."""
        frame_count = len(self.frames)
        if frame_count < 2 or frame_count % 2 or frame_index >= frame_count // 2:
            return None
        candidate = frame_index + frame_count // 2
        frame = self.frames[candidate]
        if frame.empty:
            return None
        opaque_indices = {value for value in self.pixels(candidate) if value}
        return candidate if opaque_indices == {1} else None

    def render_shadow(self, frame_index: int, *, scale: int = 1) -> Image.Image:
        if scale < 1 or scale > 16:
            raise ValueError("scale must be between 1 and 16")
        image = self._render_frame(frame_index, None, shadow=True)
        if scale != 1:
            image = image.resize(
                (self.width * scale, self.height * scale),
                Image.Resampling.NEAREST,
            )
        return image

    def _render_frame(
        self,
        frame_index: int,
        palette: Palette | None,
        *,
        shadow: bool = False,
    ) -> Image.Image:
        frame = self.frames[frame_index]
        frame_pixels = self.pixels(frame_index)
        if frame.empty:
            return Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        selected_palette = palette or grayscale_palette()
        rgba = bytearray(frame.width * frame.height * 4)
        for pixel_index, palette_index in enumerate(frame_pixels):
            offset = pixel_index * 4
            rgba[offset : offset + 4] = bytes(
                (0, 0, 0, 96 if palette_index else 0)
                if shadow
                else selected_palette.rgba(palette_index)
            )

        crop = Image.frombytes("RGBA", (frame.width, frame.height), bytes(rgba))
        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        canvas.alpha_composite(crop, (frame.x, frame.y))
        return canvas


def parse_shp(data: bytes | bytearray | memoryview) -> ShpFile:
    raw = bytes(data)
    if len(raw) < FILE_HEADER_SIZE:
        raise InvalidFormatError("SHP header is truncated")
    reserved, width, height, frame_count = struct.unpack_from("<HHHH", raw, 0)
    if reserved != 0:
        raise InvalidFormatError("SHP is not a TS/RA2 sprite")
    if not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION:
        raise InvalidFormatError("SHP canvas dimensions are invalid")
    if not 0 < frame_count <= MAX_FRAMES:
        raise InvalidFormatError("SHP frame count is invalid")

    headers_end = FILE_HEADER_SIZE + frame_count * FRAME_HEADER_SIZE
    if headers_end > len(raw):
        raise InvalidFormatError("SHP frame headers are truncated")
    frames: list[ShpFrame] = []
    for index in range(frame_count):
        offset = FILE_HEADER_SIZE + index * FRAME_HEADER_SIZE
        x, y, frame_width, frame_height = struct.unpack_from("<HHHH", raw, offset)
        compression = raw[offset + 8]
        data_offset = struct.unpack_from("<I", raw, offset + 20)[0]
        if x + frame_width > width or y + frame_height > height:
            raise InvalidFormatError(f"SHP frame {index} crop exceeds the canvas")
        if frame_width * frame_height > MAX_FRAME_PIXELS:
            raise InvalidFormatError(f"SHP frame {index} is too large")
        empty = (
            frame_width == 0
            or frame_height == 0
            or data_offset in {0, 0xCCCCCCCC}
            or compression == 4
        )
        if compression > 3 and not empty:
            raise UnsupportedFormatError(f"SHP frame {index} uses compression {compression}")
        if (
            not empty
            and frame_width
            and frame_height
            and data_offset
            and (data_offset < headers_end or data_offset >= len(raw))
        ):
            raise InvalidFormatError(f"SHP frame {index} data offset is invalid")
        frames.append(
            ShpFrame(
                index=index,
                x=x,
                y=y,
                width=frame_width,
                height=frame_height,
                compression=compression,
                data_offset=data_offset,
            )
        )
    return ShpFile(width=width, height=height, frames=tuple(frames), _data=raw)


def looks_like_shp(data: bytes | bytearray | memoryview) -> bool:
    try:
        parse_shp(data)
    except (InvalidFormatError, UnsupportedFormatError):
        return False
    return True


__all__ = ["ShpFile", "ShpFrame", "looks_like_shp", "parse_shp"]
