from __future__ import annotations

import struct
from dataclasses import dataclass

from ra2_explorer.errors import InvalidFormatError

MAX_CHUNKS = 4_096
MAX_PCM_BYTES = 512 * 1024 * 1024
IMA_ADPCM_FORMAT = 0x0011


@dataclass(frozen=True, slots=True)
class WaveFile:
    audio_format: int
    channels: int
    sample_rate: int
    byte_rate: int
    block_align: int
    bits_per_sample: int
    data_size: int
    samples_per_block: int | None
    sample_count: int | None

    @property
    def duration_seconds(self) -> float:
        if self.sample_count is not None and self.sample_rate:
            return self.sample_count / self.sample_rate
        return self.data_size / self.byte_rate if self.byte_rate else 0.0

    @property
    def browser_playable(self) -> bool:
        return self.audio_format in {1, IMA_ADPCM_FORMAT}


@dataclass(frozen=True, slots=True)
class _WaveChunks:
    metadata: WaveFile
    audio_data: bytes


def parse_wav(data: bytes | bytearray | memoryview) -> WaveFile:
    return _parse_wave_chunks(data).metadata


def wav_for_browser(data: bytes | bytearray | memoryview) -> tuple[bytes, bool]:
    parsed = _parse_wave_chunks(data)
    if parsed.metadata.audio_format == 1:
        return bytes(data), False
    if parsed.metadata.audio_format != IMA_ADPCM_FORMAT:
        raise InvalidFormatError(
            f"WAV: audio codec {parsed.metadata.audio_format} is not supported for playback"
        )
    return _decode_ima_adpcm(parsed), True


def build_pcm_wav(
    audio_data: bytes | bytearray | memoryview,
    *,
    sample_rate: int,
    channels: int,
    bits_per_sample: int = 16,
) -> bytes:
    if channels not in {1, 2}:
        raise InvalidFormatError("WAV: PCM channel count must be one or two")
    if not 4_000 <= sample_rate <= 192_000:
        raise InvalidFormatError("WAV: PCM sample rate is outside the supported range")
    if bits_per_sample not in {8, 16}:
        raise InvalidFormatError("WAV: only 8-bit and 16-bit PCM are supported")
    payload = bytes(audio_data)
    if len(payload) > MAX_PCM_BYTES:
        raise InvalidFormatError("WAV: PCM data exceeds the 512 MB safety limit")
    bytes_per_sample = bits_per_sample // 8
    block_align = channels * bytes_per_sample
    if len(payload) % block_align:
        raise InvalidFormatError("WAV: PCM data is not aligned to complete samples")
    fmt = struct.pack(
        "<HHIIHH",
        1,
        channels,
        sample_rate,
        sample_rate * block_align,
        block_align,
        bits_per_sample,
    )
    return _build_wave(fmt, payload)


def build_ima_adpcm_wav(
    audio_data: bytes | bytearray | memoryview,
    *,
    sample_rate: int,
    channels: int,
    block_align: int,
) -> bytes:
    if channels not in {1, 2}:
        raise InvalidFormatError("WAV: IMA ADPCM channel count must be one or two")
    if not 4_000 <= sample_rate <= 192_000:
        raise InvalidFormatError("WAV: IMA ADPCM sample rate is outside the supported range")
    header_size = channels * 4
    if block_align <= header_size or block_align > 65_535:
        raise InvalidFormatError("WAV: IMA ADPCM block size is invalid")
    payload = bytes(audio_data)
    samples_per_block = ((block_align - header_size) * 2 // channels) + 1
    if samples_per_block <= 1:
        raise InvalidFormatError("WAV: IMA ADPCM block has no encoded samples")
    sample_count = _ima_sample_count(payload, channels, block_align)
    byte_rate = max(1, sample_rate * block_align // samples_per_block)
    fmt = struct.pack(
        "<HHIIHHHH",
        IMA_ADPCM_FORMAT,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        4,
        2,
        samples_per_block,
    )
    fact = struct.pack("<I", sample_count)
    return _build_wave(fmt, payload, fact=fact)


def _build_wave(fmt: bytes, audio_data: bytes, *, fact: bytes | None = None) -> bytes:
    chunks = [b"fmt " + struct.pack("<I", len(fmt)) + fmt]
    if fact is not None:
        chunks.append(b"fact" + struct.pack("<I", len(fact)) + fact)
    data_chunk = b"data" + struct.pack("<I", len(audio_data)) + audio_data
    if len(audio_data) & 1:
        data_chunk += b"\0"
    chunks.append(data_chunk)
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _ima_sample_count(audio_data: bytes, channels: int, block_align: int) -> int:
    header_size = channels * 4
    frames = 0
    for block_start in range(0, len(audio_data), block_align):
        block_size = min(block_align, len(audio_data) - block_start)
        if block_size < header_size:
            continue
        encoded_size = block_size - header_size
        if channels == 1:
            frames += 1 + encoded_size * 2
            continue
        channel_samples = [1, 1]
        cursor = 0
        while cursor < encoded_size:
            for channel in range(channels):
                group_size = min(4, encoded_size - cursor)
                cursor += group_size
                channel_samples[channel] += group_size * 2
                if cursor >= encoded_size:
                    break
        frames += min(channel_samples)
    return frames


def _parse_wave_chunks(data: bytes | bytearray | memoryview) -> _WaveChunks:
    raw = memoryview(data)
    if len(raw) < 12 or bytes(raw[:4]) != b"RIFF" or bytes(raw[8:12]) != b"WAVE":
        raise InvalidFormatError("WAV: invalid RIFF/WAVE header")
    riff_size = struct.unpack_from("<I", raw, 4)[0]
    declared_end = min(len(raw), riff_size + 8)
    position = 12
    format_fields: tuple[int, int, int, int, int, int] | None = None
    samples_per_block: int | None = None
    sample_count: int | None = None
    audio_chunks = []
    chunks = 0
    while position + 8 <= declared_end:
        chunks += 1
        if chunks > MAX_CHUNKS:
            raise InvalidFormatError("WAV: too many RIFF chunks")
        chunk_id = bytes(raw[position : position + 4])
        chunk_size = struct.unpack_from("<I", raw, position + 4)[0]
        chunk_start = position + 8
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(raw):
            raise InvalidFormatError("WAV: chunk extends beyond the file")
        payload = raw[chunk_start:chunk_end]
        if chunk_id == b"fmt ":
            if chunk_size < 16:
                raise InvalidFormatError("WAV: fmt chunk is too short")
            format_fields = tuple(int(value) for value in struct.unpack_from("<HHIIHH", payload))
            if chunk_size >= 20:
                samples_per_block = struct.unpack_from("<H", payload, 18)[0]
        elif chunk_id == b"fact" and chunk_size >= 4:
            sample_count = struct.unpack_from("<I", payload)[0]
        elif chunk_id == b"data":
            audio_chunks.append(bytes(payload))
        position = chunk_end + (chunk_size & 1)
    if format_fields is None:
        raise InvalidFormatError("WAV: fmt chunk is missing")
    if not audio_chunks:
        raise InvalidFormatError("WAV: audio data chunk is missing")
    audio_format, channels, sample_rate, byte_rate, block_align, bits_per_sample = format_fields
    if channels not in {1, 2} or not sample_rate or not block_align:
        raise InvalidFormatError("WAV: unsupported channels or invalid sample-rate metadata")
    audio_data = b"".join(audio_chunks)
    metadata = WaveFile(
        audio_format,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        len(audio_data),
        samples_per_block,
        sample_count,
    )
    return _WaveChunks(metadata, audio_data)


_IMA_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
_IMA_STEPS = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37,
    41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173,
    190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894,
    6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289,
    16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
)


def _decode_nibble(nibble: int, predictor: int, index: int) -> tuple[int, int]:
    step = _IMA_STEPS[index]
    difference = step >> 3
    if nibble & 1:
        difference += step >> 2
    if nibble & 2:
        difference += step >> 1
    if nibble & 4:
        difference += step
    predictor += -difference if nibble & 8 else difference
    predictor = max(-32_768, min(32_767, predictor))
    index = max(0, min(88, index + _IMA_INDEX[nibble & 0x0F]))
    return predictor, index


def _decode_channel_bytes(
    encoded: bytes | memoryview, predictor: int, index: int
) -> tuple[list[int], int, int]:
    samples = []
    for value in encoded:
        predictor, index = _decode_nibble(value & 0x0F, predictor, index)
        samples.append(predictor)
        predictor, index = _decode_nibble(value >> 4, predictor, index)
        samples.append(predictor)
    return samples, predictor, index


def _decode_ima_adpcm(parsed: _WaveChunks) -> bytes:
    metadata = parsed.metadata
    block_align = metadata.block_align
    header_size = metadata.channels * 4
    if block_align <= header_size:
        raise InvalidFormatError("WAV: IMA ADPCM block size is invalid")
    frames: list[tuple[int, ...]] = []
    for block_start in range(0, len(parsed.audio_data), block_align):
        block = memoryview(parsed.audio_data)[block_start : block_start + block_align]
        if len(block) < header_size:
            break
        predictors = []
        indices = []
        for channel in range(metadata.channels):
            predictor, index, reserved = struct.unpack_from("<hBB", block, channel * 4)
            if index > 88 or reserved != 0:
                raise InvalidFormatError("WAV: invalid IMA ADPCM block header")
            predictors.append(predictor)
            indices.append(index)
        channel_samples = [[predictors[channel]] for channel in range(metadata.channels)]
        encoded = block[header_size:]
        if metadata.channels == 1:
            decoded, _, _ = _decode_channel_bytes(encoded, predictors[0], indices[0])
            channel_samples[0].extend(decoded)
        else:
            cursor = 0
            while cursor < len(encoded):
                for channel in range(2):
                    group = encoded[cursor : cursor + 4]
                    cursor += len(group)
                    decoded, predictors[channel], indices[channel] = _decode_channel_bytes(
                        group, predictors[channel], indices[channel]
                    )
                    channel_samples[channel].extend(decoded)
                    if cursor >= len(encoded):
                        break
        block_frames = min(len(samples) for samples in channel_samples)
        if metadata.samples_per_block:
            block_frames = min(block_frames, metadata.samples_per_block)
        for index in range(block_frames):
            frames.append(tuple(samples[index] for samples in channel_samples))

    if metadata.sample_count is not None:
        frames = frames[: metadata.sample_count]
    pcm_size = len(frames) * metadata.channels * 2
    if pcm_size > MAX_PCM_BYTES:
        raise InvalidFormatError("WAV: decoded PCM exceeds the 512 MB safety limit")
    pcm = bytearray(pcm_size)
    cursor = 0
    for frame in frames:
        for sample in frame:
            struct.pack_into("<h", pcm, cursor, sample)
            cursor += 2
    fmt = struct.pack(
        "<HHIIHH",
        1,
        metadata.channels,
        metadata.sample_rate,
        metadata.sample_rate * metadata.channels * 2,
        metadata.channels * 2,
        16,
    )
    riff_size = 4 + 8 + len(fmt) + 8 + len(pcm)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVEfmt " + struct.pack(
        "<I", len(fmt)
    ) + fmt + b"data" + struct.pack("<I", len(pcm)) + bytes(pcm)


__all__ = [
    "IMA_ADPCM_FORMAT",
    "WaveFile",
    "build_ima_adpcm_wav",
    "build_pcm_wav",
    "parse_wav",
    "wav_for_browser",
]
