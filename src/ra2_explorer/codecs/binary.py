from __future__ import annotations

import struct
from collections.abc import Iterator

from ra2_explorer.errors import InvalidFormatError


class BinaryReader:
    """Small bounds-checked little-endian reader for legacy game formats."""

    def __init__(self, data: bytes | bytearray | memoryview, *, format_name: str):
        self.data = memoryview(data)
        self.format_name = format_name
        self.position = 0

    def remaining(self) -> int:
        return len(self.data) - self.position

    def seek(self, position: int) -> None:
        if not 0 <= position <= len(self.data):
            raise InvalidFormatError(
                f"{self.format_name}: offset {position} is outside the file"
            )
        self.position = position

    def skip(self, size: int) -> None:
        self.seek(self.position + size)

    def read(self, size: int, *, context: str = "data") -> memoryview:
        if size < 0:
            raise InvalidFormatError(f"{self.format_name}: negative {context} size")
        end = self.position + size
        if end > len(self.data):
            raise InvalidFormatError(
                f"{self.format_name}: truncated {context} "
                f"(need {size} bytes, have {self.remaining()})"
            )
        result = self.data[self.position : end]
        self.position = end
        return result

    def unpack(self, format_string: str, *, context: str = "data") -> tuple[object, ...]:
        size = struct.calcsize(format_string)
        return struct.unpack(format_string, self.read(size, context=context))

    def u8(self, *, context: str = "byte") -> int:
        return int(self.read(1, context=context)[0])

    def u32(self, *, context: str = "integer") -> int:
        return int(self.unpack("<I", context=context)[0])

    def i32(self, *, context: str = "integer") -> int:
        return int(self.unpack("<i", context=context)[0])

    def f32(self, *, context: str = "float") -> float:
        return float(self.unpack("<f", context=context)[0])

    def fixed_ascii(self, size: int, *, context: str = "name") -> str:
        raw = bytes(self.read(size, context=context)).split(b"\0", 1)[0]
        return raw.decode("ascii", errors="replace")


def checked_product(values: Iterator[int] | tuple[int, ...], *, limit: int, context: str) -> int:
    result = 1
    for value in values:
        if value < 0 or (value and result > limit // value):
            raise InvalidFormatError(f"{context} exceeds the safety limit ({limit})")
        result *= value
    if result > limit:
        raise InvalidFormatError(f"{context} exceeds the safety limit ({limit})")
    return result


__all__ = ["BinaryReader", "checked_product"]
