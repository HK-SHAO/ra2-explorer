from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

from ra2_explorer.codecs.mix import MixHashType, build_mix

FIXTURE_NAMES = (
    "conquer.mix",
    "fixture.pal",
    "fixture.shp",
    "rules.ini",
    "art.ini",
    "sound.ini",
    "fixture.csf",
    "fixture.vxl",
    "fixture.hva",
    "fixture.tem",
    "fixture.wav",
    "fixture.map",
    "infantry.shp",
    "voxels.vpl",
)


def create_fixture_installation(target: Path) -> Path:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    palette = _build_fixture_palette()
    sprite = _build_fixture_shp()
    rules = (
        b"[VehicleTypes]\r\n"
        b"0=DemoVehicle\r\n"
        b"\r\n[Countries]\r\n"
        b"0=Americans\r\n"
        b"1=Russians\r\n"
        b"\r\n[Americans]\r\n"
        b"UIName=Name:Americans\r\n"
        b"Side=GDI\r\n"
        b"\r\n[Russians]\r\n"
        b"UIName=Name:Russians\r\n"
        b"Side=Nod\r\n"
        b"\r\n[InfantryTypes]\r\n"
        b"0=DemoInfantry\r\n"
        b"\r\n[DemoVehicle]\r\n"
        b"UIName=UNIT:DemoVehicle\r\n"
        b"Name=Explorer Test Vehicle\r\n"
        b"Image=FIXTURE\r\n"
        b"Primary=DemoCannon\r\n"
        b"Secondary=none\r\n"
        b"Strength=400\r\n"
        b"Cost=800\r\n"
        b"TechLevel=2\r\n"
        b"Owner=Americans,Russians\r\n"
        b"VoiceSelect=FixtureSelect\r\n"
        b"\r\n[DemoInfantry]\r\n"
        b"UIName=UNIT:DemoInfantry\r\n"
        b"Name=Explorer Test Infantry\r\n"
        b"Image=INFANTRY\r\n"
        b"Strength=125\r\n"
        b"Cost=200\r\n"
        b"TechLevel=1\r\n"
        b"Owner=Americans\r\n"
        b"\r\n[DemoCannon]\r\n"
        b"Damage=75\r\n"
        b"ROF=50\r\n"
        b"Range=6\r\n"
        b"Projectile=DemoShell\r\n"
        b"Warhead=DemoWarhead\r\n"
        b"Report=DemoCannonFire\r\n"
        b"\r\n[DemoShell]\r\n"
        b"Arcing=yes\r\n"
        b"Image=120MM\r\n"
        b"\r\n[DemoWarhead]\r\n"
        b"Verses=100%,80%,60%\r\n"
        b"Wall=yes\r\n"
    )
    art = (
        b"[FIXTURE]\r\n"
        b"Voxel=yes\r\n"
        b"Remapable=yes\r\n"
        b"Cameo=FIXTURE\r\n"
        b"\r\n[INFANTRY]\r\n"
        b"Image=INFANTRY\r\n"
        b"Remapable=yes\r\n"
        b"Facings=8\r\n"
        b"Sequence=INFANTRYSEQ\r\n"
        b"\r\n[INFANTRYSEQ]\r\n"
        b"Ready=0,1,1\r\n"
        b"Walk=0,2,1\r\n"
    )
    sound = b"[FixtureSelect]\r\nSounds=fixture fixture\r\n"
    nested = build_mix(
        [
            ("fixture.pal", palette),
            ("fixture.shp", sprite),
            ("rules.ini", rules),
            ("art.ini", art),
            ("sound.ini", sound),
            ("fixture.csf", _build_fixture_csf()),
            ("fixture.vxl", _build_fixture_vxl(palette)),
            ("fixture.hva", _build_fixture_hva()),
            ("fixture.tem", _build_fixture_tmp()),
            ("fixture.wav", _build_fixture_wav()),
            ("fixture.map", _build_fixture_map()),
            ("infantry.shp", _build_fixture_infantry_shp()),
            ("voxels.vpl", _build_fixture_vpl(palette)),
        ],
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
    (target / "fixture-notes.ini").write_text(
        "[Demo]\nDescription=Freely generated synthetic RA2 format sample\n",
        encoding="utf-8",
    )
    return target


def _build_fixture_palette() -> bytes:
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


def _build_fixture_shp() -> bytes:
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


def _build_fixture_csf() -> bytes:
    labels = (
        ("UI:ExplorerTitle", "RA2 Explorer format sample", None),
        ("VOX:ExplorerReady", "Asset pipeline ready.", "explorer-ready"),
        ("VOX:fixture_event", "Ready for the test.", "fixture"),
        ("UNIT:DemoVehicle", "Generated test vehicle", None),
        ("UNIT:DemoInfantry", "Generated test infantry", None),
        ("Name:Americans", "United States", None),
        ("Name:Russians", "Russia", None),
    )
    output = bytearray(b" FSC")
    output.extend(struct.pack("<IIIII", 3, len(labels), len(labels), 0, 0))
    for name, text, extra in labels:
        encoded_name = name.encode("ascii")
        output.extend(b" LBL")
        output.extend(struct.pack("<II", 1, len(encoded_name)))
        output.extend(encoded_name)
        output.extend(b"WRTS" if extra else b" RTS")
        units = text.encode("utf-16-le")
        output.extend(struct.pack("<I", len(units) // 2))
        output.extend(byte ^ 0xFF for byte in units)
        if extra:
            encoded_extra = extra.encode("ascii")
            output.extend(struct.pack("<I", len(encoded_extra)))
            output.extend(encoded_extra)
    return bytes(output)


def _build_fixture_vxl(palette: bytes) -> bytes:
    size_x, size_y, size_z = 12, 8, 7
    columns: dict[tuple[int, int], list[tuple[int, int, int]]] = {}

    def add(x: int, y: int, z: int, color: int, normal: int = 20) -> None:
        columns.setdefault((x, y), []).append((z, color, normal))

    for x in range(2, 10):
        for y in range(1, 7):
            add(x, y, 1, 44)
            if 3 <= x <= 8 and 2 <= y <= 5:
                add(x, y, 2, 48)
    for x in range(4, 8):
        for y in range(3, 5):
            add(x, y, 3, 112)
    for x in range(6, 12):
        add(x, 3, 4, 28)
    for x in (2, 9):
        for y in range(1, 7):
            add(x, y, 0, 210)

    span_data = bytearray()
    starts = []
    ends = []
    for y in range(size_y):
        for x in range(size_x):
            values = sorted(columns.get((x, y), []))
            if not values:
                starts.append(-1)
                ends.append(-1)
                continue
            starts.append(len(span_data))
            cursor_z = 0
            run: list[tuple[int, int, int]] = []
            for value in values:
                if run and value[0] != run[-1][0] + 1:
                    cursor_z = _write_vxl_run(span_data, run, cursor_z)
                    run = []
                run.append(value)
            cursor_z = _write_vxl_run(span_data, run, cursor_z)
            if cursor_z < size_z:
                span_data.extend((size_z - cursor_z, 0, 0))
            ends.append(len(span_data) - 1)

    column_count = size_x * size_y
    body = bytearray()
    body.extend(struct.pack(f"<{column_count}i", *starts))
    body.extend(struct.pack(f"<{column_count}i", *ends))
    body.extend(span_data)

    embedded_palette = bytes(min(255, component * 4) for component in palette)
    output = bytearray(b"Voxel Animation\0")
    output.extend(struct.pack("<IIII", 1, 1, 1, len(body)))
    output.extend((16, 31))
    output.extend(embedded_palette)
    output.extend(b"BODY" + b"\0" * 12)
    output.extend(struct.pack("<III", 0, 0, 0))
    output.extend(body)
    output.extend(struct.pack("<III", 0, column_count * 4, column_count * 8))
    output.extend(struct.pack("<f", 1.0))
    identity = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    output.extend(struct.pack("<12f", *identity))
    output.extend(struct.pack("<3f", -6.0, -4.0, -2.0))
    output.extend(struct.pack("<3f", 6.0, 4.0, 5.0))
    output.extend(bytes((size_x, size_y, size_z, 4)))
    return bytes(output)


def _write_vxl_run(
    output: bytearray,
    run: list[tuple[int, int, int]],
    cursor_z: int,
) -> int:
    if not run:
        return cursor_z
    output.extend((run[0][0] - cursor_z, len(run)))
    for _, color, normal in run:
        output.extend((color, normal))
    output.append(len(run))
    return run[-1][0] + 1


def _build_fixture_hva() -> bytes:
    output = bytearray(b"fixture.hva" + b"\0" * 5)
    output.extend(struct.pack("<II", 4, 1))
    output.extend(b"BODY" + b"\0" * 12)
    for frame in range(4):
        transform = (
            1.0,
            0.0,
            0.0,
            frame * 0.1,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
        )
        output.extend(struct.pack("<12f", *transform))
    return bytes(output)


def _build_fixture_vpl(palette: bytes) -> bytes:
    output = bytearray(struct.pack("<IIII", 16, 31, 32, 0))
    output.extend(palette)
    for section in range(32):
        output.extend(max(0, color - (31 - section)) for color in range(256))
    return bytes(output)


def _build_fixture_tmp() -> bytes:
    tile_width, tile_height = 60, 30
    iso_size = tile_width * tile_height // 2
    colors = bytearray()
    row_width = 4
    for y in range(tile_height):
        for x in range(row_width):
            colors.append(64 + ((x + y * 3) % 52))
        row_width += 4 if y < tile_height // 2 - 1 else -4
    output = bytearray(struct.pack("<IIiiI", 1, 1, tile_width, tile_height, 20))
    output.extend(struct.pack("<iiIII", 0, 0, 0, 52 + iso_size, 0))
    output.extend(struct.pack("<iiiiI", 0, 0, 0, 0, 0))
    output.extend(bytes((0, 0, 0, 34, 80, 34, 48, 112, 48, 0, 0, 0)))
    output.extend(colors)
    output.extend(bytes(iso_size))
    return bytes(output)


def _build_fixture_wav() -> bytes:
    sample_rate = 11_025
    frame_count = sample_rate // 3
    frames = bytearray()
    for index in range(frame_count):
        envelope = max(0.0, 1.0 - index / frame_count)
        value = round(math.sin(index * 2 * math.pi * 440 / sample_rate) * envelope * 12_000)
        frames.extend(struct.pack("<h", value))
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(frames)
    return output.getvalue()


def _build_fixture_map() -> bytes:
    return (
        b"[Map]\r\nSize=0,0,64,48\r\nLocalSize=2,3,60,42\r\nTheater=TEMPERATE\r\n"
        b"[Structures]\r\n0=Americans,GAPOWR,256,12,14,0,None,0,0,1,0,0,None,None,None\r\n"
        b"[Units]\r\n0=Americans,MTNK,256,18,20,0,Guard,None,0,0,0,-1,-1,None\r\n"
        b"[Infantry]\r\n0=Americans,E1,256,17,19,0,Guard,0,None,0,0\r\n"
        b"[Waypoints]\r\n0=12014\r\n"
        b"[Terrain]\r\n15016=TREE01\r\n"
    )


def _build_fixture_infantry_shp() -> bytes:
    width, height = 24, 32
    visible = []
    for frame_index in range(3):
        pixels = bytearray(width * height)
        _fill_circle(pixels, width, height, 12, 8, 4, 42 + frame_index)
        _fill_rect(pixels, width, 9, 12, 16, 25, 112)
        visible.append(bytes(pixels))
    empty = bytes(width * height)
    return _encode_shp(width, height, [visible[0], empty, visible[1], empty, visible[2], empty])


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


__all__ = ["FIXTURE_NAMES", "create_fixture_installation"]
