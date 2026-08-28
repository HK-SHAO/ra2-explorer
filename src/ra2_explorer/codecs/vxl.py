from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from ra2_explorer.codecs.binary import BinaryReader, checked_product
from ra2_explorer.codecs.pal import Palette, grayscale_palette
from ra2_explorer.errors import InvalidFormatError

HEADER_SIZE = 802
LIMB_HEADER_SIZE = 28
LIMB_TAILER_SIZE = 92
MAX_LIMBS = 512
MAX_BODY_SIZE = 64 * 1024 * 1024
MAX_COLUMNS = 65_025
MAX_VOXELS = 4_000_000
MAX_RENDER_VOXELS = 300_000


@dataclass(frozen=True, slots=True)
class Voxel:
    x: int
    y: int
    z: int
    color: int
    normal: int


@dataclass(frozen=True, slots=True)
class VxlLimb:
    name: str
    number: int
    scale: float
    transform: tuple[float, ...]
    min_bounds: tuple[float, float, float]
    max_bounds: tuple[float, float, float]
    size: tuple[int, int, int]
    normals_mode: int
    voxels: tuple[Voxel, ...]


@dataclass(frozen=True, slots=True)
class VxlFile:
    file_name: str
    palette_count: int
    remap_start: int
    remap_end: int
    palette: Palette
    limbs: tuple[VxlLimb, ...]

    @property
    def voxel_count(self) -> int:
        return sum(len(limb.voxels) for limb in self.limbs)

    def render(
        self,
        limb_index: int = 0,
        *,
        palette: Palette | None = None,
        scale: int = 4,
    ) -> Image.Image:
        if not 0 <= limb_index < len(self.limbs):
            raise IndexError("VXL limb is out of range")
        limb = self.limbs[limb_index]
        if len(limb.voxels) > MAX_RENDER_VOXELS:
            raise InvalidFormatError(
                f"VXL: limb has too many voxels to preview ({len(limb.voxels):,})"
            )
        if not limb.voxels:
            return Image.new("RGBA", (320, 180), (0, 0, 0, 0))

        size_x, size_y, size_z = limb.size
        requested = max(1, min(scale, 12))
        projected_width = max(1, (size_x + size_y + 2) * requested * 2)
        projected_height = max(1, (size_x + size_y + size_z * 2 + 4) * requested)
        fit = min(1.0, 1800 / projected_width, 1800 / projected_height)
        unit = max(1, int(requested * fit))
        half_width = unit * 2
        half_height = unit
        cube_height = unit * 2

        def project(voxel: Voxel) -> tuple[int, int]:
            return (
                (voxel.x - voxel.y) * half_width,
                (voxel.x + voxel.y) * half_height - voxel.z * cube_height,
            )

        projected = [project(voxel) for voxel in limb.voxels]
        min_x = min(point[0] - half_width for point in projected)
        max_x = max(point[0] + half_width for point in projected)
        min_y = min(point[1] - cube_height - half_height for point in projected)
        max_y = max(point[1] + half_height for point in projected)
        padding = max(12, unit * 3)
        width = max_x - min_x + padding * 2 + 1
        height = max_y - min_y + padding * 2 + 1
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        active_palette = palette or self.palette

        ordered = sorted(
            limb.voxels,
            key=lambda voxel: (voxel.x + voxel.y + voxel.z, voxel.z, voxel.y, voxel.x),
        )
        for voxel in ordered:
            cx, cy = project(voxel)
            cx += padding - min_x
            cy += padding - min_y
            red, green, blue, _ = active_palette.rgba(voxel.color, transparent_zero=False)
            top = _shade((red, green, blue), 1.12)
            left = _shade((red, green, blue), 0.70)
            right = _shade((red, green, blue), 0.88)
            top_points = (
                (cx, cy - cube_height - half_height),
                (cx + half_width, cy - cube_height),
                (cx, cy - cube_height + half_height),
                (cx - half_width, cy - cube_height),
            )
            left_points = (
                top_points[3],
                top_points[2],
                (cx, cy + half_height),
                (cx - half_width, cy),
            )
            right_points = (
                top_points[1],
                top_points[2],
                (cx, cy + half_height),
                (cx + half_width, cy),
            )
            draw.polygon(left_points, fill=(*left, 255))
            draw.polygon(right_points, fill=(*right, 255))
            draw.polygon(top_points, fill=(*top, 255))
        return image


@dataclass(frozen=True, slots=True)
class _LimbHeader:
    name: str
    number: int


@dataclass(frozen=True, slots=True)
class _LimbTailer:
    span_start: int
    span_end: int
    span_data: int
    scale: float
    transform: tuple[float, ...]
    min_bounds: tuple[float, float, float]
    max_bounds: tuple[float, float, float]
    size: tuple[int, int, int]
    normals_mode: int


def parse_vxl(data: bytes | bytearray | memoryview) -> VxlFile:
    reader = BinaryReader(data, format_name="VXL")
    magic = bytes(reader.read(16, context="header magic"))
    if not magic.startswith(b"Voxel Animation"):
        raise InvalidFormatError("VXL: invalid header magic")
    file_name = magic.split(b"\0", 1)[0].decode("ascii", errors="replace")
    palette_count = reader.u32(context="palette count")
    limb_count = reader.u32(context="limb count")
    tailer_count = reader.u32(context="tailer count")
    body_size = reader.u32(context="body size")
    remap_start = reader.u8(context="remap start")
    remap_end = reader.u8(context="remap end")
    palette_bytes = bytes(reader.read(768, context="embedded palette"))
    if reader.position != HEADER_SIZE:
        raise InvalidFormatError("VXL: internal header layout mismatch")
    if limb_count > MAX_LIMBS or tailer_count > MAX_LIMBS:
        raise InvalidFormatError(f"VXL: limb count exceeds {MAX_LIMBS}")
    if limb_count != tailer_count:
        raise InvalidFormatError("VXL: limb header and tailer counts do not match")
    if body_size > MAX_BODY_SIZE:
        raise InvalidFormatError("VXL: body exceeds the 64 MB safety limit")

    headers = []
    for index in range(limb_count):
        name = reader.fixed_ascii(16, context=f"limb {index} name")
        number = reader.u32(context="limb number")
        reader.skip(8)
        headers.append(_LimbHeader(name, number))
    body_start = reader.position
    body_end = body_start + body_size
    if body_end > len(reader.data):
        raise InvalidFormatError("VXL: declared body is truncated")
    reader.seek(body_end)

    tailers = []
    for index in range(tailer_count):
        span_start = reader.u32(context=f"limb {index} span-start offset")
        span_end = reader.u32(context=f"limb {index} span-end offset")
        span_data = reader.u32(context=f"limb {index} span-data offset")
        scale = reader.f32(context=f"limb {index} scale")
        transform = tuple(reader.f32(context="transform") for _ in range(12))
        min_bounds = tuple(reader.f32(context="minimum bound") for _ in range(3))
        max_bounds = tuple(reader.f32(context="maximum bound") for _ in range(3))
        size = tuple(reader.u8(context="limb dimension") for _ in range(3))
        normals_mode = reader.u8(context="normals mode")
        if not all(size):
            raise InvalidFormatError(f"VXL: limb {index} has a zero dimension")
        column_count = checked_product(
            (size[0], size[1]), limit=MAX_COLUMNS, context="VXL column count"
        )
        for offset_name, offset in (
            ("span start", span_start),
            ("span end", span_end),
            ("span data", span_data),
        ):
            if offset > body_size:
                raise InvalidFormatError(
                    f"VXL: limb {index} {offset_name} offset is outside the body"
                )
        if span_start + column_count * 4 > body_size:
            raise InvalidFormatError(f"VXL: limb {index} start-offset table is truncated")
        if span_end + column_count * 4 > body_size:
            raise InvalidFormatError(f"VXL: limb {index} end-offset table is truncated")
        tailers.append(
            _LimbTailer(
                span_start,
                span_end,
                span_data,
                scale,
                transform,
                min_bounds,  # type: ignore[arg-type]
                max_bounds,  # type: ignore[arg-type]
                size,  # type: ignore[arg-type]
                normals_mode,
            )
        )

    palette = _parse_embedded_palette(palette_bytes)
    limbs = []
    total_voxels = 0
    for index, (header, tailer) in enumerate(zip(headers, tailers, strict=True)):
        voxels = _read_limb_voxels(reader.data, body_start, body_end, tailer, index)
        total_voxels += len(voxels)
        if total_voxels > MAX_VOXELS:
            raise InvalidFormatError(f"VXL: total voxel count exceeds {MAX_VOXELS:,}")
        limbs.append(
            VxlLimb(
                header.name,
                header.number,
                tailer.scale,
                tailer.transform,
                tailer.min_bounds,
                tailer.max_bounds,
                tailer.size,
                tailer.normals_mode,
                voxels,
            )
        )
    return VxlFile(
        file_name,
        palette_count,
        remap_start,
        remap_end,
        palette,
        tuple(limbs),
    )


def _read_limb_voxels(
    data: memoryview,
    body_start: int,
    body_end: int,
    tailer: _LimbTailer,
    limb_index: int,
) -> tuple[Voxel, ...]:
    size_x, size_y, size_z = tailer.size
    column_count = size_x * size_y
    table_reader = BinaryReader(data, format_name="VXL")
    table_reader.seek(body_start + tailer.span_start)
    starts = [table_reader.i32(context="column start offset") for _ in range(column_count)]
    table_reader.seek(body_start + tailer.span_end)
    ends = [table_reader.i32(context="column end offset") for _ in range(column_count)]
    data_base = body_start + tailer.span_data
    voxels = []
    for column, (start, end) in enumerate(zip(starts, ends, strict=True)):
        if start == -1 and end == -1:
            continue
        if start < 0 or end < start:
            raise InvalidFormatError(f"VXL: limb {limb_index} has an invalid column span")
        cursor = data_base + start
        column_end = data_base + end + 1
        if cursor < body_start or column_end > body_end:
            raise InvalidFormatError(f"VXL: limb {limb_index} column data is outside the body")
        x = column % size_x
        y = column // size_x
        z = 0
        run_count = 0
        while z < size_z:
            run_count += 1
            if run_count > size_z + 1:
                raise InvalidFormatError(f"VXL: limb {limb_index} column does not terminate")
            if cursor + 2 > column_end:
                raise InvalidFormatError(f"VXL: limb {limb_index} column header is truncated")
            skip = int(data[cursor])
            count = int(data[cursor + 1])
            cursor += 2
            previous_z = z
            z += skip
            needed = count * 2 + 1
            if cursor + needed > column_end:
                raise InvalidFormatError(f"VXL: limb {limb_index} voxel run is truncated")
            if z + count > size_z:
                raise InvalidFormatError(f"VXL: limb {limb_index} voxel run exceeds its grid")
            for _ in range(count):
                color = int(data[cursor])
                normal = int(data[cursor + 1])
                cursor += 2
                voxels.append(Voxel(x, y, z, color, normal))
                z += 1
            duplicate_count = int(data[cursor])
            cursor += 1
            if duplicate_count != count:
                raise InvalidFormatError(
                    f"VXL: limb {limb_index} voxel run has a mismatched trailing count"
                )
            if z == previous_z:
                raise InvalidFormatError(f"VXL: limb {limb_index} column made no progress")
    return tuple(voxels)


def _parse_embedded_palette(raw: bytes) -> Palette:
    if not raw or not any(raw):
        return grayscale_palette()
    six_bit = max(raw) <= 63
    colors = []
    for offset in range(0, 768, 3):
        components = raw[offset : offset + 3]
        if six_bit:
            colors.append(tuple(min(255, value * 4) for value in components))
        else:
            colors.append(tuple(components))
    return Palette(tuple(colors))  # type: ignore[arg-type]


def _shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(min(255, max(0, round(component * factor))) for component in color)  # type: ignore[return-value]


__all__ = ["Voxel", "VxlFile", "VxlLimb", "parse_vxl"]
