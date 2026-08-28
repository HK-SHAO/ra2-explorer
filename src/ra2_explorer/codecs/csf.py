from __future__ import annotations

from dataclasses import dataclass

from ra2_explorer.codecs.binary import BinaryReader, checked_product
from ra2_explorer.errors import InvalidFormatError

MAX_LABELS = 100_000
MAX_STRINGS = 200_000
MAX_STRING_CHARS = 65_536


@dataclass(frozen=True, slots=True)
class CsfValue:
    text: str
    extra: str | None


@dataclass(frozen=True, slots=True)
class CsfLabel:
    name: str
    values: tuple[CsfValue, ...]


@dataclass(frozen=True, slots=True)
class CsfFile:
    version: int
    language: int
    declared_string_count: int
    labels: tuple[CsfLabel, ...]

    @property
    def string_count(self) -> int:
        return sum(len(label.values) for label in self.labels)

    def excerpt(self, *, query: str | None = None, limit: int = 400) -> dict[str, object]:
        needle = query.casefold() if query else None
        all_lines = []
        for label in self.labels:
            for value in label.values:
                suffix = f" [{value.extra}]" if value.extra else ""
                line = f"{label.name} = {value.text}{suffix}"
                if needle is None or needle in line.casefold():
                    all_lines.append(line)
        selected = all_lines[:limit]
        return {
            "text": "\n".join(selected),
            "line_count": len(all_lines),
            "returned_lines": len(selected),
            "truncated": len(selected) < len(all_lines),
        }


def parse_csf(data: bytes | bytearray | memoryview) -> CsfFile:
    reader = BinaryReader(data, format_name="CSF")
    if bytes(reader.read(4, context="header magic")) != b" FSC":
        raise InvalidFormatError("CSF: invalid header magic")
    version = reader.u32(context="version")
    label_count = reader.u32(context="label count")
    declared_string_count = reader.u32(context="string count")
    reader.u32(context="reserved field")
    language = reader.u32(context="language")
    if label_count > MAX_LABELS:
        raise InvalidFormatError(f"CSF: label count exceeds {MAX_LABELS}")
    if declared_string_count > MAX_STRINGS:
        raise InvalidFormatError(f"CSF: string count exceeds {MAX_STRINGS}")

    labels = []
    actual_strings = 0
    for label_index in range(label_count):
        if bytes(reader.read(4, context=f"label {label_index} marker")) != b" LBL":
            raise InvalidFormatError(f"CSF: invalid label marker at label {label_index}")
        value_count = reader.u32(context="label value count")
        name_length = reader.u32(context="label name length")
        if name_length > MAX_STRING_CHARS:
            raise InvalidFormatError("CSF: label name is too long")
        if value_count > MAX_STRINGS - actual_strings:
            raise InvalidFormatError("CSF: actual string count exceeds the safety limit")
        name = bytes(reader.read(name_length, context="label name")).decode(
            "ascii", errors="replace"
        )
        values = []
        for value_index in range(value_count):
            marker = bytes(reader.read(4, context="string marker"))
            if marker not in {b" RTS", b"WRTS"}:
                raise InvalidFormatError(
                    f"CSF: invalid string marker in {name!r} value {value_index}"
                )
            char_count = reader.u32(context="string character count")
            if char_count > MAX_STRING_CHARS:
                raise InvalidFormatError("CSF: string value is too long")
            byte_count = checked_product(
                (char_count, 2), limit=MAX_STRING_CHARS * 2, context="CSF string"
            )
            encoded = bytes(reader.read(byte_count, context="encoded string"))
            decoded = bytes(byte ^ 0xFF for byte in encoded).decode(
                "utf-16-le", errors="replace"
            )
            extra = None
            if marker == b"WRTS":
                extra_length = reader.u32(context="extra value length")
                if extra_length > MAX_STRING_CHARS:
                    raise InvalidFormatError("CSF: extra value is too long")
                extra = bytes(reader.read(extra_length, context="extra value")).decode(
                    "cp1252", errors="replace"
                )
            values.append(CsfValue(decoded, extra))
        actual_strings += value_count
        labels.append(CsfLabel(name, tuple(values)))
    return CsfFile(version, language, declared_string_count, tuple(labels))


__all__ = ["CsfFile", "CsfLabel", "CsfValue", "parse_csf"]
