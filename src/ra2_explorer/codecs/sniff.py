from __future__ import annotations

import struct
from pathlib import PurePath

from ra2_explorer.codecs.shp import looks_like_shp

KNOWN_FORMATS = {
    ".aud": "aud",
    ".bag": "bag",
    ".bik": "video",
    ".csf": "csf",
    ".des": "tmp",
    ".fnt": "fnt",
    ".hva": "hva",
    ".idx": "idx",
    ".ini": "ini",
    ".lun": "tmp",
    ".map": "map",
    ".mix": "mix",
    ".mmx": "mix",
    ".mpr": "map",
    ".pal": "pal",
    ".pcx": "pcx",
    ".shp": "shp",
    ".sno": "tmp",
    ".tem": "tmp",
    ".tmp": "tmp",
    ".txt": "text",
    ".ubn": "tmp",
    ".urb": "tmp",
    ".vqa": "video",
    ".vpl": "vpl",
    ".vxl": "vxl",
    ".wav": "wav",
    ".yro": "mix",
}

AMBIGUOUS_EXTENSIONS = {".des", ".lun", ".sno", ".tem", ".tmp", ".ubn", ".urb"}


def format_from_name(name: str | None) -> str | None:
    if not name:
        return None
    extension = PurePath(name).suffix.lower()
    if extension in AMBIGUOUS_EXTENSIONS:
        return None
    return KNOWN_FORMATS.get(extension)


def sniff_format(data: bytes | bytearray | memoryview, name: str | None = None) -> str:
    extension = PurePath(name).suffix.lower() if name else ""
    named_format = KNOWN_FORMATS.get(extension)
    if named_format and extension not in AMBIGUOUS_EXTENSIONS:
        return named_format
    view = memoryview(data)
    if len(view) == 768:
        return "pal"
    if len(view) >= 4 and bytes(view[:4]) == b" FSC":
        return "csf"
    if len(view) >= 16 and bytes(view[:16]).startswith(b"Voxel Animation"):
        return "vxl"
    if looks_like_shp(view):
        return "shp"
    sample = bytes(view[:4096])
    if sample.startswith(b"BIK"):
        return "video"
    if sample.startswith(b"RIFF") and sample[8:12] == b"WAVE":
        return "wav"
    if sample.startswith(b"GABA"):
        return "idx"
    if _looks_like_aud(view):
        return "aud"
    if len(view) >= 128 and sample[:1] == b"\x0a" and sample[2:3] == b"\x01":
        return "pcx"
    if _looks_like_hva(view):
        return "hva"
    if _looks_like_tmp(view):
        return "tmp"
    if b"[" in sample and b"]" in sample and b"=" in sample:
        return "ini"
    return named_format or "binary"


def _looks_like_hva(data: memoryview) -> bool:
    if len(data) < 24:
        return False
    frame_count, section_count = struct.unpack_from("<II", data, 16)
    if not 0 < frame_count <= 65_536 or not 0 < section_count <= 512:
        return False
    expected = 24 + 16 * section_count + 48 * frame_count * section_count
    if expected != len(data):
        return False
    name = bytes(data[:16]).split(b"\0", 1)[0]
    return bool(name) and all(32 <= byte < 127 for byte in name)


def _looks_like_aud(data: memoryview) -> bool:
    if len(data) < 20:
        return False
    sample_rate, data_size, output_size, flags, compression = struct.unpack_from(
        "<HIIBB", data, 0
    )
    if not 4_000 <= sample_rate <= 192_000 or data_size != len(data) - 12:
        return False
    if not output_size or flags & ~0x03 or compression not in {1, 99}:
        return False
    return struct.unpack_from("<I", data, 16)[0] == 0xDEAF


def _looks_like_tmp(data: memoryview) -> bool:
    if len(data) < 20:
        return False
    template_width, template_height, tile_width, tile_height = struct.unpack_from(
        "<IIii", data, 0
    )
    if not (0 < template_width <= 128 and 0 < template_height <= 128):
        return False
    if tile_width <= 0 or tile_height <= 0 or tile_width % 4 or tile_height % 2:
        return False
    tile_count = template_width * template_height
    table_end = 16 + tile_count * 4
    if table_end > len(data):
        return False
    offsets = struct.unpack_from(f"<{tile_count}I", data, 16)
    first = next((offset for offset in offsets if offset), None)
    if first is None or first + 52 > len(data):
        return False
    depth_offset = struct.unpack_from("<I", data, first + 12)[0]
    return depth_offset == tile_width * tile_height // 2 + 52


__all__ = ["AMBIGUOUS_EXTENSIONS", "KNOWN_FORMATS", "format_from_name", "sniff_format"]
