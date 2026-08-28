from __future__ import annotations

from dataclasses import dataclass

from ra2_explorer.errors import InvalidFormatError

MAX_TEXT_BYTES = 16 * 1024 * 1024
MAX_TEXT_LINES = 250_000


@dataclass(frozen=True, slots=True)
class DecodedText:
    text: str
    encoding: str


@dataclass(frozen=True, slots=True)
class IniEntry:
    key: str
    value: str
    line: int


@dataclass(frozen=True, slots=True)
class IniSection:
    name: str
    entries: tuple[IniEntry, ...]


@dataclass(frozen=True, slots=True)
class IniFile:
    encoding: str
    sections: tuple[IniSection, ...]
    text: str

    @property
    def entry_count(self) -> int:
        return sum(len(section.entries) for section in self.sections)


def decode_legacy_text(data: bytes | bytearray | memoryview) -> DecodedText:
    raw = bytes(data)
    if len(raw) > MAX_TEXT_BYTES:
        raise InvalidFormatError("text file exceeds the 16 MB safety limit")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
        return DecodedText(raw.decode(encoding, errors="replace"), encoding)
    if raw.startswith(b"\xef\xbb\xbf"):
        return DecodedText(raw.decode("utf-8-sig", errors="replace"), "utf-8-sig")
    try:
        return DecodedText(raw.decode("utf-8"), "utf-8")
    except UnicodeDecodeError:
        pass

    # Chinese RA2 distributions and mods commonly use the Windows GBK family.
    # Prefer it only when a strict decode produces CJK text, otherwise preserve
    # the original western Windows code page behavior.
    try:
        gb_text = raw.decode("gb18030")
    except UnicodeDecodeError:
        gb_text = ""
    if gb_text and any("\u3400" <= char <= "\u9fff" for char in gb_text):
        return DecodedText(gb_text, "gb18030")
    return DecodedText(raw.decode("cp1252", errors="replace"), "windows-1252")


def parse_ini(data: bytes | bytearray | memoryview) -> IniFile:
    decoded = decode_legacy_text(data)
    lines = decoded.text.splitlines()
    if len(lines) > MAX_TEXT_LINES:
        raise InvalidFormatError("INI contains too many lines")

    section_names: list[str] = []
    entries: dict[str, list[IniEntry]] = {}
    current = ""
    entries[current] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            if current not in entries:
                section_names.append(current)
                entries[current] = []
            continue
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        entries[current].append(IniEntry(key.strip(), value.strip(), line_number))

    sections = []
    if entries[""]:
        sections.append(IniSection("", tuple(entries[""])))
    sections.extend(IniSection(name, tuple(entries[name])) for name in section_names)
    return IniFile(decoded.encoding, tuple(sections), decoded.text)


def text_excerpt(text: str, *, query: str | None = None, limit: int = 400) -> dict[str, object]:
    lines = text.splitlines()
    if query:
        needle = query.casefold()
        lines = [line for line in lines if needle in line.casefold()]
    selected = lines[:limit]
    return {
        "text": "\n".join(selected),
        "line_count": len(lines),
        "returned_lines": len(selected),
        "truncated": len(selected) < len(lines),
    }


__all__ = [
    "DecodedText",
    "IniEntry",
    "IniFile",
    "IniSection",
    "decode_legacy_text",
    "parse_ini",
    "text_excerpt",
]
