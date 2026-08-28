from __future__ import annotations

import base64
import binascii
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from Crypto.Cipher import Blowfish

from ra2_explorer.errors import InvalidFormatError

MAX_MIX_ENTRIES = 65_535
MAX_ARCHIVE_DATA = 2**32 - 1
_EXTENDED_CHECKSUM = 0x0001
_EXTENDED_ENCRYPTED = 0x0002
_KEY_SOURCE_SIZE = 80
_BLOWFISH_KEY_SIZE = 56
_PUBLIC_EXPONENT = 65_537
_PUBLIC_KEY = "AihRvNoIbTn85FZRYNZRcT+i6KpU+maCsEqr3Q5q+LDB5tH7Tz2qQ38V"


class MixHashType(StrEnum):
    RA2 = "ra2-crc32"
    CLASSIC = "classic"


@dataclass(frozen=True, slots=True)
class MixEntry:
    ordinal: int
    crc: int
    offset: int
    size: int


@dataclass(frozen=True, slots=True)
class MixIndex:
    entries: tuple[MixEntry, ...]
    data_offset: int
    data_size: int
    flags: int
    encrypted: bool
    checksum: bool

    def payload(self, data: bytes | bytearray | memoryview, entry: MixEntry) -> memoryview:
        view = memoryview(data)
        start = self.data_offset + entry.offset
        end = start + entry.size
        if start < self.data_offset or end > self.data_offset + self.data_size:
            raise InvalidFormatError("MIX entry points outside the data section")
        return view[start:end]


def parse_mix(data: bytes | bytearray | memoryview) -> MixIndex:
    view = memoryview(data)
    if len(view) < 6:
        raise InvalidFormatError("MIX header is truncated")

    first_word = struct.unpack_from("<H", view, 0)[0]
    if first_word != 0:
        return _parse_plain_header(view, header_offset=0, flags=0)

    if len(view) < 10:
        raise InvalidFormatError("extended MIX header is truncated")
    flags = struct.unpack_from("<H", view, 2)[0]
    unknown_flags = flags & ~(_EXTENDED_CHECKSUM | _EXTENDED_ENCRYPTED)
    if unknown_flags:
        raise InvalidFormatError(f"extended MIX has unknown flags 0x{unknown_flags:04X}")
    if flags & _EXTENDED_ENCRYPTED:
        return _parse_encrypted_header(view, flags)
    return _parse_plain_header(view, header_offset=4, flags=flags)


def _parse_plain_header(view: memoryview, header_offset: int, flags: int) -> MixIndex:
    count, declared_size = _read_file_header(view, header_offset)
    index_start = header_offset + 6
    index_end = index_start + count * 12
    if index_end > len(view):
        raise InvalidFormatError("MIX index is truncated")
    entries = _read_entries(view, index_start, count)
    _validate_data_section(entries, declared_size, index_end, len(view))
    return MixIndex(
        entries=entries,
        data_offset=index_end,
        data_size=declared_size,
        flags=flags,
        encrypted=False,
        checksum=bool(flags & _EXTENDED_CHECKSUM),
    )


def _parse_encrypted_header(view: memoryview, flags: int) -> MixIndex:
    encrypted_start = 4 + _KEY_SOURCE_SIZE
    if len(view) < encrypted_start + Blowfish.block_size:
        raise InvalidFormatError("encrypted MIX key or first header block is truncated")

    key_source = bytes(view[4:encrypted_start])
    cipher = Blowfish.new(_derive_blowfish_key(key_source), Blowfish.MODE_ECB)
    first_block = cipher.decrypt(bytes(view[encrypted_start : encrypted_start + 8]))
    count, declared_size = _read_file_header(memoryview(first_block), 0)
    header_size = 6 + count * 12
    encrypted_size = (header_size + 7) // 8 * 8
    encrypted_end = encrypted_start + encrypted_size
    if encrypted_end > len(view):
        raise InvalidFormatError("encrypted MIX index is truncated")

    header = memoryview(cipher.decrypt(bytes(view[encrypted_start:encrypted_end])))
    actual_count, actual_size = _read_file_header(header, 0)
    if actual_count != count or actual_size != declared_size:
        raise InvalidFormatError("encrypted MIX header changed between decrypted blocks")
    entries = _read_entries(header, 6, count)
    _validate_data_section(entries, declared_size, encrypted_end, len(view))
    return MixIndex(
        entries=entries,
        data_offset=encrypted_end,
        data_size=declared_size,
        flags=flags,
        encrypted=True,
        checksum=bool(flags & _EXTENDED_CHECKSUM),
    )


def _read_file_header(view: memoryview, offset: int) -> tuple[int, int]:
    if offset + 6 > len(view):
        raise InvalidFormatError("MIX file header is truncated")
    count, declared_size = struct.unpack_from("<HI", view, offset)
    if count > MAX_MIX_ENTRIES:
        raise InvalidFormatError(f"MIX entry count exceeds {MAX_MIX_ENTRIES}")
    if declared_size > MAX_ARCHIVE_DATA:
        raise InvalidFormatError("MIX data section is too large")
    return count, declared_size


def _read_entries(view: memoryview, offset: int, count: int) -> tuple[MixEntry, ...]:
    entries: list[MixEntry] = []
    for ordinal in range(count):
        entry_offset = offset + ordinal * 12
        if entry_offset + 12 > len(view):
            raise InvalidFormatError("MIX entry is truncated")
        crc, relative_offset, size = struct.unpack_from("<III", view, entry_offset)
        entries.append(MixEntry(ordinal, crc, relative_offset, size))
    return tuple(entries)


def _validate_data_section(
    entries: tuple[MixEntry, ...], declared_size: int, data_offset: int, file_size: int
) -> None:
    data_end = data_offset + declared_size
    if data_end > file_size:
        raise InvalidFormatError("MIX data section exceeds the file")
    for entry in entries:
        if entry.offset > declared_size or entry.size > declared_size:
            raise InvalidFormatError("MIX entry range exceeds the declared data section")
        if entry.offset + entry.size > declared_size:
            raise InvalidFormatError("MIX entry range exceeds the declared data section")


def _derive_blowfish_key(key_source: bytes) -> bytes:
    if len(key_source) != _KEY_SOURCE_SIZE:
        raise InvalidFormatError("encrypted MIX key source must contain 80 bytes")

    padded_key = _PUBLIC_KEY + "=" * ((4 - len(_PUBLIC_KEY) % 4) % 4)
    raw_key = base64.b64decode(padded_key)
    if len(raw_key) < 3 or raw_key[0] != 0x02:
        raise InvalidFormatError("embedded MIX public key is invalid")
    modulus_size = raw_key[1]
    modulus_bytes = raw_key[2 : 2 + modulus_size]
    if len(modulus_bytes) != modulus_size:
        raise InvalidFormatError("embedded MIX public key is truncated")

    modulus = int.from_bytes(modulus_bytes, "big")
    output_size = (modulus.bit_length() - 1) // 8
    input_size = output_size + 1
    result_width = (modulus.bit_length() + 7) // 8
    material = bytearray()
    for offset in range(0, len(key_source) - input_size + 1, input_size):
        chunk = int.from_bytes(key_source[offset : offset + input_size], "little")
        decrypted = pow(chunk, _PUBLIC_EXPONENT, modulus)
        material.extend(decrypted.to_bytes(result_width, "little")[:output_size])
        if len(material) >= _BLOWFISH_KEY_SIZE:
            break
    if len(material) < _BLOWFISH_KEY_SIZE:
        raise InvalidFormatError("encrypted MIX key derivation produced too little data")
    return bytes(material[:_BLOWFISH_KEY_SIZE])


def classic_mix_hash(filename: str) -> int:
    encoded = _ascii_upper(filename)
    encoded += b"\0" * ((4 - len(encoded) % 4) % 4)
    result = 0
    for offset in range(0, len(encoded), 4):
        word = int.from_bytes(encoded[offset : offset + 4], "little")
        result = (((result << 1) | (result >> 31)) + word) & 0xFFFFFFFF
    return result


def ra2_mix_hash(filename: str) -> int:
    encoded = bytearray(_ascii_upper(filename))
    padding = (4 - len(encoded) % 4) % 4
    if not padding:
        return binascii.crc32(encoded) & 0xFFFFFFFF

    original_length = len(encoded)
    rounded_down = original_length // 4 * 4
    encoded.extend(b"\0" * padding)
    encoded[original_length] = original_length - rounded_down
    for position in range(1, padding):
        encoded[original_length + position] = encoded[rounded_down]
    return binascii.crc32(encoded) & 0xFFFFFFFF


def _ascii_upper(filename: str) -> bytes:
    normalized = filename.replace("/", "\\").upper()
    try:
        return normalized.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("MIX filenames must be ASCII") from error


def resolve_mix_names(
    entries: Iterable[MixEntry], candidates: Iterable[str]
) -> tuple[MixHashType, dict[int, str]]:
    entry_ids = {entry.crc for entry in entries}
    ra2_matches: dict[int, str] = {}
    classic_matches: dict[int, str] = {}
    for raw_name in candidates:
        name = raw_name.strip().replace("/", "\\")
        if not name or name.startswith("#"):
            continue
        try:
            ra2_crc = ra2_mix_hash(name)
            classic_crc = classic_mix_hash(name)
        except ValueError:
            continue
        if ra2_crc in entry_ids:
            ra2_matches.setdefault(ra2_crc, name)
        if classic_crc in entry_ids:
            classic_matches.setdefault(classic_crc, name)

    if len(classic_matches) > len(ra2_matches):
        return MixHashType.CLASSIC, classic_matches
    return MixHashType.RA2, ra2_matches


def parse_local_mix_database(data: bytes | bytearray | memoryview) -> tuple[str, ...]:
    view = memoryview(data)
    if len(view) < 4:
        return ()
    count = min(struct.unpack_from("<I", view, 0)[0], MAX_MIX_ENTRIES)
    cursor = 4
    names: list[str] = []
    raw = bytes(view)
    for _ in range(count):
        name_end = raw.find(b"\0", cursor)
        if name_end < 0:
            break
        name = raw[cursor:name_end].decode("ascii", errors="ignore")
        cursor = name_end + 1
        description_end = raw.find(b"\0", cursor)
        if description_end < 0:
            break
        cursor = description_end + 1
        if name:
            names.append(name)
    return tuple(names)


def build_mix(
    files: Iterable[tuple[str, bytes]],
    *,
    hash_type: MixHashType = MixHashType.RA2,
    extended: bool = False,
    encrypted: bool = False,
    key_source: bytes | None = None,
) -> bytes:
    """Build a deterministic MIX used by synthetic test fixtures."""
    materialized = list(files)
    hash_fn = ra2_mix_hash if hash_type is MixHashType.RA2 else classic_mix_hash
    data_size = sum(len(payload) for _, payload in materialized)
    offset = 0
    entries: list[tuple[int, int, int]] = []
    for name, payload in materialized:
        entries.append((hash_fn(name), offset, len(payload)))
        offset += len(payload)
    entries.sort(key=lambda item: item[0] if item[0] < 0x80000000 else item[0] - 0x100000000)

    header = bytearray(struct.pack("<HI", len(entries), data_size))
    payload_by_hash = {hash_fn(name): payload for name, payload in materialized}
    for crc, entry_offset, size in entries:
        header.extend(struct.pack("<III", crc, entry_offset, size))
    body = b"".join(payload_by_hash[crc] for crc, _, _ in sorted(entries, key=lambda item: item[1]))

    if encrypted:
        source = key_source or bytes(range(_KEY_SOURCE_SIZE))
        if len(source) != _KEY_SOURCE_SIZE:
            raise ValueError("key_source must contain exactly 80 bytes")
        padded_header = bytes(header) + b"\0" * ((8 - len(header) % 8) % 8)
        cipher = Blowfish.new(_derive_blowfish_key(source), Blowfish.MODE_ECB)
        return struct.pack("<HH", 0, _EXTENDED_ENCRYPTED) + source + cipher.encrypt(
            padded_header
        ) + body
    if extended:
        return struct.pack("<HH", 0, 0) + bytes(header) + body
    return bytes(header) + body


__all__ = [
    "MixEntry",
    "MixHashType",
    "MixIndex",
    "build_mix",
    "classic_mix_hash",
    "parse_local_mix_database",
    "parse_mix",
    "ra2_mix_hash",
    "resolve_mix_names",
]
