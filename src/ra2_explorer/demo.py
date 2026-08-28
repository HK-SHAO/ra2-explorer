from __future__ import annotations

import struct
from pathlib import Path

from ra2_explorer.codecs.mix import MixHashType, build_mix


def create_demo_installation(target: Path) -> Path:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    palette = _build_demo_palette()
    sprite = _build_demo_shp()
    rules = (
        b"[DemoVehicle]\r\n"
        b"Name=Explorer Test Vehicle\r\n"
        b"Image=DEMO\r\n"
        b"Primary=DemoCannon\r\n"
    )
    nested = build_mix(
        [("demo.pal", palette), ("demo.shp", sprite), ("rules.ini", rules)],
        hash_type=MixHashType.RA2,
    )
    key_source = bytes((index * 37 + 11) & 0xFF for index in range(80))
    root = build_mix(
        [("conquer.mix", nested)],
        hash_type=MixHashType.RA2,
        encrypted=True,
        key_source=key_source,
    )
    (target / "ra2.mix").write_bytes(root)
    (target / "demo-notes.ini").write_text(
        "[Demo]\nDescription=Freely generated synthetic RA2 format sample\n",
        encoding="utf-8",
    )
    return target


def _build_demo_palette() -> bytes:
    colors = bytearray()
    for index in range(256):
        if index == 0:
            colors.extend((0, 0, 0))
        elif index < 64:
            colors.extend((min(63, 8 + index), max(0, index // 5), max(0, index // 9)))
        elif index < 128:
            colors.extend((index // 5, min(63, index // 2), 14))
        elif index < 192:
            colors.extend((14, index // 4, min(63, index // 3)))
        else:
            value = min(63, (index - 192) * 2)
            colors.extend((value, value, value))
    return bytes(colors)


def _build_demo_shp() -> bytes:
    width, height = 80, 56
    frames = []
    for frame_index in range(6):
        pixels = bytearray(width * height)
        _fill_rect(pixels, width, 10 + frame_index, 28, 51 + frame_index, 42, 44)
        _fill_rect(pixels, width, 18 + frame_index, 20, 43 + frame_index, 31, 112)
        _fill_rect(pixels, width, 37 + frame_index, 14, 46 + frame_index, 23, 25)
        _fill_rect(pixels, width, 45 + frame_index, 17, 65 + frame_index, 19, 31)
        _fill_rect(pixels, width, 15 + frame_index, 40, 48 + frame_index, 44, 18)
        _fill_circle(pixels, width, height, 21 + frame_index, 43, 7, 210)
        _fill_circle(pixels, width, height, 46 + frame_index, 43, 7, 210)
        _fill_circle(pixels, width, height, 21 + frame_index, 43, 3, 75)
        _fill_circle(pixels, width, height, 46 + frame_index, 43, 3, 75)
        if frame_index >= 3:
            _fill_rect(pixels, width, 66 + frame_index, 16, 73 + frame_index, 20, 57)
        frames.append(bytes(pixels))
    return _encode_shp(width, height, frames)


def _fill_rect(
    pixels: bytearray,
    stride: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: int,
) -> None:
    for y in range(top, bottom):
        row_start = y * stride
        for x in range(left, right):
            pixels[row_start + x] = color


def _fill_circle(
    pixels: bytearray,
    stride: int,
    height: int,
    center_x: int,
    center_y: int,
    radius: int,
    color: int,
) -> None:
    for y in range(max(0, center_y - radius), min(height, center_y + radius + 1)):
        for x in range(max(0, center_x - radius), min(stride, center_x + radius + 1)):
            if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius**2:
                pixels[y * stride + x] = color


def _encode_shp(width: int, height: int, frames: list[bytes]) -> bytes:
    header_size = 8 + 24 * len(frames)
    encoded_frames = [_encode_rle_frame(frame, width, height) for frame in frames]
    output = bytearray(struct.pack("<HHHH", 0, width, height, len(frames)))
    data_offset = header_size
    for encoded in encoded_frames:
        output.extend(struct.pack("<HHHHB11xI", 0, 0, width, height, 3, data_offset))
        data_offset += len(encoded)
    for encoded in encoded_frames:
        output.extend(encoded)
    return bytes(output)


def _encode_rle_frame(pixels: bytes, width: int, height: int) -> bytes:
    output = bytearray()
    for y in range(height):
        line = pixels[y * width : (y + 1) * width]
        encoded = bytearray()
        cursor = 0
        while cursor < width:
            value = line[cursor]
            if value:
                encoded.append(value)
                cursor += 1
                continue
            run = 1
            while cursor + run < width and line[cursor + run] == 0 and run < 255:
                run += 1
            encoded.extend((0, run))
            cursor += run
        output.extend(struct.pack("<H", len(encoded) + 2))
        output.extend(encoded)
    return bytes(output)


__all__ = ["create_demo_installation"]
