from __future__ import annotations

from pathlib import PurePath

from ra2_explorer.codecs.shp import looks_like_shp

KNOWN_FORMATS = {
    ".aud": "aud",
    ".bag": "bag",
    ".bik": "video",
    ".csf": "csf",
    ".hva": "hva",
    ".idx": "idx",
    ".ini": "ini",
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
    ".urb": "tmp",
    ".vqa": "video",
    ".vxl": "vxl",
    ".wav": "wav",
    ".yro": "mix",
}


def format_from_name(name: str | None) -> str | None:
    if not name:
        return None
    return KNOWN_FORMATS.get(PurePath(name).suffix.lower())


def sniff_format(data: bytes | bytearray | memoryview, name: str | None = None) -> str:
    named_format = format_from_name(name)
    if named_format:
        return named_format
    view = memoryview(data)
    if len(view) == 768:
        return "pal"
    if looks_like_shp(view):
        return "shp"
    sample = bytes(view[:4096])
    if sample.startswith(b"RIFF") and sample[8:12] == b"WAVE":
        return "wav"
    if b"[" in sample and b"]" in sample and b"=" in sample:
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            return "ini"
    return "binary"


__all__ = ["KNOWN_FORMATS", "format_from_name", "sniff_format"]
