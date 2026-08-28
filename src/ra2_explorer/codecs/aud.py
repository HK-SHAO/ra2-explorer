from __future__ import annotations

import struct
from dataclasses import dataclass

from ra2_explorer.codecs.wav import build_pcm_wav
from ra2_explorer.errors import InvalidFormatError

AUD_HEADER_SIZE = 12
AUD_CHUNK_HEADER_SIZE = 8
AUD_CHUNK_MAGIC = 0x0000_DEAF
WESTWOOD_COMPRESSION = 1
IMA_ADPCM_COMPRESSION = 99
MAX_AUD_BYTES = 512 * 1024 * 1024
MAX_AUD_CHUNKS = 100_000

_STEP_TABLE_2 = (-2, -1, 0, 1)
_STEP_TABLE_4 = (-9, -8, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 8)
_IMA_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8)
_IMA_STEPS = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130,
    143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)


@dataclass(frozen=True, slots=True)
class AudFile:
    sample_rate: int
    data_size: int
    output_size: int
    flags: int
    compression: int
    chunk_count: int

    @property
    def channels(self) -> int:
        return 2 if self.flags & 0x01 else 1

    @property
    def bits_per_sample(self) -> int:
        return 16 if self.flags & 0x02 else 8

    @property
    def sample_count(self) -> int:
        frame_size = self.channels * (self.bits_per_sample // 8)
        return self.output_size // frame_size

    @property
    def duration_seconds(self) -> float:
        return self.sample_count / self.sample_rate

    @property
    def codec(self) -> str:
        return "ima_adpcm" if self.compression == IMA_ADPCM_COMPRESSION else "westwood"


@dataclass(frozen=True, slots=True)
class _AudChunks:
    metadata: AudFile
    chunks: tuple[tuple[int, bytes], ...]


def parse_aud(data: bytes | bytearray | memoryview) -> AudFile:
    return _parse_aud_chunks(data).metadata


def aud_for_browser(data: bytes | bytearray | memoryview) -> bytes:
    parsed = _parse_aud_chunks(data)
    if parsed.metadata.compression == IMA_ADPCM_COMPRESSION:
        pcm = _decode_ima_chunks(parsed)
    else:
        pcm = _decode_westwood_chunks(parsed)
    return build_pcm_wav(
        pcm,
        sample_rate=parsed.metadata.sample_rate,
        channels=parsed.metadata.channels,
        bits_per_sample=parsed.metadata.bits_per_sample,
    )


def _parse_aud_chunks(data: bytes | bytearray | memoryview) -> _AudChunks:
    raw = memoryview(data)
    if len(raw) < AUD_HEADER_SIZE:
        raise InvalidFormatError("AUD: header is truncated")
    sample_rate, data_size, output_size, flags, compression = struct.unpack_from(
        "<HIIBB", raw, 0
    )
    if not 4_000 <= sample_rate <= 192_000:
        raise InvalidFormatError("AUD: invalid sample rate")
    if data_size != len(raw) - AUD_HEADER_SIZE:
        raise InvalidFormatError("AUD: compressed size does not match the file")
    if output_size > MAX_AUD_BYTES:
        raise InvalidFormatError("AUD: decoded audio exceeds the 512 MB safety limit")
    if flags & ~0x03:
        raise InvalidFormatError(f"AUD: unsupported sound flags 0x{flags:02X}")
    if compression not in {WESTWOOD_COMPRESSION, IMA_ADPCM_COMPRESSION}:
        raise InvalidFormatError(f"AUD: unsupported compression {compression}")
    if compression == WESTWOOD_COMPRESSION and flags != 0:
        raise InvalidFormatError("AUD: Westwood compression must contain mono 8-bit audio")
    if compression == IMA_ADPCM_COMPRESSION and not flags & 0x02:
        raise InvalidFormatError("AUD: IMA ADPCM must decode to 16-bit audio")

    chunks = []
    position = AUD_HEADER_SIZE
    declared_output = 0
    while position < len(raw):
        if len(chunks) >= MAX_AUD_CHUNKS:
            raise InvalidFormatError("AUD: chunk count exceeds the safety limit")
        if position + AUD_CHUNK_HEADER_SIZE > len(raw):
            raise InvalidFormatError("AUD: chunk header is truncated")
        compressed_size, chunk_output_size, magic = struct.unpack_from("<HHI", raw, position)
        position += AUD_CHUNK_HEADER_SIZE
        end = position + compressed_size
        if magic != AUD_CHUNK_MAGIC:
            raise InvalidFormatError("AUD: invalid chunk marker")
        if end > len(raw):
            raise InvalidFormatError("AUD: chunk data is truncated")
        if not chunk_output_size:
            raise InvalidFormatError("AUD: chunk has no decoded output")
        chunks.append((chunk_output_size, bytes(raw[position:end])))
        declared_output += chunk_output_size
        position = end
    if declared_output != output_size:
        raise InvalidFormatError("AUD: decoded chunk sizes do not match the header")
    metadata = AudFile(sample_rate, data_size, output_size, flags, compression, len(chunks))
    return _AudChunks(metadata, tuple(chunks))


def _decode_ima_chunks(parsed: _AudChunks) -> bytes:
    output = bytearray()
    predictor = 0
    index = 0
    for expected_size, encoded in parsed.chunks:
        if expected_size & 1:
            raise InvalidFormatError("AUD: IMA ADPCM chunk has an odd output size")
        sample_count = expected_size // 2
        if sample_count > len(encoded) * 2 + 1:
            raise InvalidFormatError("AUD: IMA ADPCM chunk output size is inconsistent")
        chunk_start = len(output)
        for sample_index in range(sample_count):
            byte_index = sample_index // 2
            value = encoded[byte_index] if byte_index < len(encoded) else 0
            nibble = value & 0x0F if sample_index % 2 == 0 else value >> 4
            predictor, index = _decode_ima_nibble(nibble, predictor, index)
            output.extend(struct.pack("<h", predictor))
        if len(output) - chunk_start != expected_size:
            raise InvalidFormatError("AUD: IMA ADPCM chunk output size is inconsistent")
    if len(output) != parsed.metadata.output_size:
        raise InvalidFormatError("AUD: IMA ADPCM output size is inconsistent")
    return bytes(output)


def _decode_ima_nibble(nibble: int, predictor: int, index: int) -> tuple[int, int]:
    value = nibble & 0x07
    step = _IMA_STEPS[index]
    delta = step >> 3
    if value & 0x01:
        delta += step >> 2
    if value & 0x02:
        delta += step >> 1
    if value & 0x04:
        delta += step
    predictor += -delta if nibble & 0x08 else delta
    predictor = max(-32_768, min(32_767, predictor))
    index = max(0, min(88, index + _IMA_INDEX[value]))
    return predictor, index


def _decode_westwood_chunks(parsed: _AudChunks) -> bytes:
    output = bytearray()
    for expected_size, encoded in parsed.chunks:
        output.extend(_decode_westwood_chunk(encoded, expected_size))
    if len(output) != parsed.metadata.output_size:
        raise InvalidFormatError("AUD: Westwood output size is inconsistent")
    return bytes(output)


def _decode_westwood_chunk(encoded: bytes, expected_size: int) -> bytes:
    if len(encoded) == expected_size:
        return encoded
    output = bytearray()
    sample = 0x80
    position = 0

    def append(value: int) -> None:
        nonlocal sample
        if len(output) >= expected_size:
            raise InvalidFormatError("AUD: Westwood chunk produces too much output")
        sample = max(0, min(255, value))
        output.append(sample)

    while position < len(encoded):
        command = encoded[position]
        position += 1
        count = command & 0x3F
        mode = command >> 6
        if mode == 0:
            for _ in range(count + 1):
                if position >= len(encoded):
                    raise InvalidFormatError("AUD: Westwood 2-bit run is truncated")
                code = encoded[position]
                position += 1
                for shift in (0, 2, 4, 6):
                    append(sample + _STEP_TABLE_2[(code >> shift) & 0x03])
        elif mode == 1:
            for _ in range(count + 1):
                if position >= len(encoded):
                    raise InvalidFormatError("AUD: Westwood 4-bit run is truncated")
                code = encoded[position]
                position += 1
                append(sample + _STEP_TABLE_4[code & 0x0F])
                append(sample + _STEP_TABLE_4[(code >> 4) & 0x0F])
        elif mode == 2 and count & 0x20:
            append(sample + count - 0x40)
        elif mode == 2:
            literal_count = count + 1
            end = position + literal_count
            if end > len(encoded):
                raise InvalidFormatError("AUD: Westwood literal run is truncated")
            for value in encoded[position:end]:
                append(value)
            position = end
        else:
            for _ in range(count + 1):
                append(sample)
    if len(output) != expected_size:
        raise InvalidFormatError("AUD: Westwood chunk output size is inconsistent")
    return bytes(output)


__all__ = [
    "AudFile",
    "IMA_ADPCM_COMPRESSION",
    "WESTWOOD_COMPRESSION",
    "aud_for_browser",
    "parse_aud",
]
