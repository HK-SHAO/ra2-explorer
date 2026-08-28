from __future__ import annotations

import struct
from dataclasses import dataclass

from ra2_explorer.codecs.wav import (
    build_ima_adpcm_wav,
    build_pcm_wav,
    parse_wav,
    wav_for_browser,
)
from ra2_explorer.errors import InvalidFormatError

IDX_MAGIC = b"GABA"
IDX_VERSION = 2
IDX_HEADER_SIZE = 12
IDX_ENTRY_SIZE = 36
MAX_AUDIO_ENTRIES = 100_000
MAX_ENTRY_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class BagAudioEntry:
    name: str
    offset: int
    size: int
    sample_rate: int
    flags: int
    block_align: int

    @property
    def channels(self) -> int:
        return 2 if self.flags & 0x01 else 1

    @property
    def codec(self) -> str:
        if self.flags & 0x02:
            return "pcm16"
        if self.flags & 0x08:
            return "ima_adpcm"
        return "unknown"


@dataclass(frozen=True, slots=True)
class BagAudioIndex:
    version: int
    entries: tuple[BagAudioEntry, ...]


def parse_bag_index(
    data: bytes | bytearray | memoryview,
    *,
    bag_size: int | None = None,
) -> BagAudioIndex:
    raw = memoryview(data)
    if len(raw) < IDX_HEADER_SIZE or bytes(raw[:4]) != IDX_MAGIC:
        raise InvalidFormatError("AUDIO.IDX: invalid GABA header")
    version, entry_count = struct.unpack_from("<II", raw, 4)
    if version != IDX_VERSION:
        raise InvalidFormatError(f"AUDIO.IDX: unsupported version {version}")
    if entry_count > MAX_AUDIO_ENTRIES:
        raise InvalidFormatError(
            f"AUDIO.IDX: entry count exceeds {MAX_AUDIO_ENTRIES:,}"
        )
    expected_size = IDX_HEADER_SIZE + entry_count * IDX_ENTRY_SIZE
    if expected_size != len(raw):
        raise InvalidFormatError("AUDIO.IDX: entry table size does not match the header")

    entries = []
    names = set()
    for index in range(entry_count):
        position = IDX_HEADER_SIZE + index * IDX_ENTRY_SIZE
        name_bytes, offset, size, sample_rate, flags, block_align = struct.unpack_from(
            "<16sIIIII", raw, position
        )
        name = name_bytes.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()
        if not name:
            raise InvalidFormatError(f"AUDIO.IDX: entry {index} has an empty name")
        normalized_name = name.casefold()
        if normalized_name in names:
            raise InvalidFormatError(f"AUDIO.IDX: duplicate entry name {name}")
        names.add(normalized_name)
        if size > MAX_ENTRY_BYTES:
            raise InvalidFormatError(
                f"AUDIO.IDX: {name} exceeds the {MAX_ENTRY_BYTES // (1024 * 1024)} MB limit"
            )
        if not 4_000 <= sample_rate <= 192_000:
            raise InvalidFormatError(f"AUDIO.IDX: {name} has an invalid sample rate")
        entry = BagAudioEntry(name, offset, size, sample_rate, flags, block_align)
        if entry.codec == "unknown":
            raise InvalidFormatError(
                f"AUDIO.IDX: {name} uses unsupported flags 0x{flags:08X}"
            )
        if entry.codec == "pcm16" and block_align != 0:
            raise InvalidFormatError(f"AUDIO.IDX: {name} PCM block size must be zero")
        if entry.codec == "ima_adpcm" and block_align <= entry.channels * 4:
            raise InvalidFormatError(f"AUDIO.IDX: {name} ADPCM block size is invalid")
        if bag_size is not None and offset + size > bag_size:
            raise InvalidFormatError(f"AUDIO.IDX: {name} extends beyond AUDIO.BAG")
        entries.append(entry)
    return BagAudioIndex(version, tuple(entries))


def bag_audio_wav(data: bytes | bytearray | memoryview, entry: BagAudioEntry) -> bytes:
    payload = bytes(data)
    if len(payload) != entry.size:
        raise InvalidFormatError("AUDIO.BAG: entry data size does not match AUDIO.IDX")
    if entry.codec == "pcm16":
        return build_pcm_wav(
            payload,
            sample_rate=entry.sample_rate,
            channels=entry.channels,
            bits_per_sample=16,
        )
    if entry.codec == "ima_adpcm":
        return build_ima_adpcm_wav(
            payload,
            sample_rate=entry.sample_rate,
            channels=entry.channels,
            block_align=entry.block_align,
        )
    raise InvalidFormatError("AUDIO.BAG: unsupported audio codec")


def bag_audio_for_browser(
    data: bytes | bytearray | memoryview,
    entry: BagAudioEntry,
) -> bytes:
    encoded = bag_audio_wav(data, entry)
    playable, _ = wav_for_browser(encoded)
    return playable


def inspect_bag_audio(
    data: bytes | bytearray | memoryview,
    entry: BagAudioEntry,
) -> dict[str, object]:
    playable = bag_audio_for_browser(data, entry)
    metadata = parse_wav(playable)
    return {
        "channels": metadata.channels,
        "sample_rate": metadata.sample_rate,
        "bits_per_sample": metadata.bits_per_sample,
        "block_align": entry.block_align,
        "data_size": entry.size,
        "sample_count": metadata.sample_count,
        "duration_seconds": metadata.duration_seconds,
        "audio_codec": entry.codec,
        "browser_playable": True,
        "playback_transcodes_to_pcm": entry.codec == "ima_adpcm",
    }


__all__ = [
    "BagAudioEntry",
    "BagAudioIndex",
    "bag_audio_for_browser",
    "bag_audio_wav",
    "inspect_bag_audio",
    "parse_bag_index",
]
