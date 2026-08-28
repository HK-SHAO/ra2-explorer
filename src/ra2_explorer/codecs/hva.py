from __future__ import annotations

from dataclasses import dataclass

from ra2_explorer.codecs.binary import BinaryReader, checked_product
from ra2_explorer.errors import InvalidFormatError

MAX_SECTIONS = 512
MAX_FRAMES = 65_536
MAX_TRANSFORMS = 1_000_000


@dataclass(frozen=True, slots=True)
class HvaFile:
    file_name: str
    frame_count: int
    section_names: tuple[str, ...]
    transforms: tuple[tuple[float, ...], ...]

    def transform(self, frame: int, section: int) -> tuple[float, ...]:
        if not 0 <= frame < self.frame_count:
            raise IndexError("HVA frame is out of range")
        if not 0 <= section < len(self.section_names):
            raise IndexError("HVA section is out of range")
        return self.transforms[frame * len(self.section_names) + section]


def parse_hva(data: bytes | bytearray | memoryview) -> HvaFile:
    reader = BinaryReader(data, format_name="HVA")
    file_name = reader.fixed_ascii(16, context="file name")
    frame_count = reader.u32(context="frame count")
    section_count = reader.u32(context="section count")
    if frame_count > MAX_FRAMES:
        raise InvalidFormatError(f"HVA: frame count exceeds {MAX_FRAMES}")
    if section_count > MAX_SECTIONS:
        raise InvalidFormatError(f"HVA: section count exceeds {MAX_SECTIONS}")
    transform_count = checked_product(
        (frame_count, section_count), limit=MAX_TRANSFORMS, context="HVA transform count"
    )
    section_names = tuple(
        reader.fixed_ascii(16, context=f"section {index} name")
        for index in range(section_count)
    )
    transforms = []
    for index in range(transform_count):
        matrix = tuple(
            reader.f32(context=f"transform {index}") for _ in range(12)
        )
        transforms.append(matrix)
    return HvaFile(file_name, frame_count, section_names, tuple(transforms))


__all__ = ["HvaFile", "parse_hva"]
