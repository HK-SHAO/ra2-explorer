from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from ra2_explorer.codecs.text import IniFile, parse_ini

MAX_MAP_DIMENSION = 1_024


@dataclass(frozen=True, slots=True)
class MapObject:
    kind: str
    name: str
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class MapOverview:
    ini: IniFile
    origin_x: int
    origin_y: int
    width: int
    height: int
    theater: str | None
    objects: tuple[MapObject, ...]

    @property
    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in self.objects:
            result[item.kind] = result.get(item.kind, 0) + 1
        return result

    def render(self, scale: int = 4) -> Image.Image:
        unit = max(2, min(scale, 10))
        fit = min(
            1.0,
            1_400 / max(1, self.width * unit),
            1_000 / max(1, self.height * unit),
        )
        cell = max(2, round(unit * fit))
        padding = 24
        image = Image.new(
            "RGBA",
            (self.width * cell + padding * 2, self.height * cell + padding * 2),
            (15, 18, 22, 255),
        )
        draw = ImageDraw.Draw(image)
        bounds = (padding, padding, padding + self.width * cell, padding + self.height * cell)
        draw.rectangle(bounds, fill=(35, 44, 39, 255), outline=(111, 132, 117, 255), width=2)
        grid_step = max(5, 20 // max(1, cell))
        for x in range(0, self.width + 1, grid_step):
            px = padding + x * cell
            draw.line((px, padding, px, bounds[3]), fill=(56, 67, 60, 180))
        for y in range(0, self.height + 1, grid_step):
            py = padding + y * cell
            draw.line((padding, py, bounds[2], py), fill=(56, 67, 60, 180))

        colors = {
            "structure": (230, 184, 74, 255),
            "unit": (91, 164, 235, 255),
            "infantry": (116, 212, 148, 255),
            "aircraft": (198, 130, 235, 255),
            "terrain": (111, 137, 89, 255),
            "waypoint": (244, 96, 91, 255),
        }
        for item in self.objects:
            x = item.x - self.origin_x
            y = item.y - self.origin_y
            if not (0 <= x < self.width and 0 <= y < self.height):
                continue
            center_x = padding + x * cell + cell // 2
            center_y = padding + y * cell + cell // 2
            color = colors.get(item.kind, (210, 210, 210, 255))
            radius = max(2, cell // 2)
            if item.kind == "structure":
                draw.rectangle(
                    (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                    fill=color,
                )
            elif item.kind == "waypoint":
                draw.ellipse(
                    (
                        center_x - radius - 1,
                        center_y - radius - 1,
                        center_x + radius + 1,
                        center_y + radius + 1,
                    ),
                    outline=color,
                    width=2,
                )
            else:
                draw.ellipse(
                    (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                    fill=color,
                )
        return image


def parse_map(data: bytes | bytearray | memoryview) -> MapOverview:
    ini = parse_ini(data)
    sections = {
        section.name.casefold(): {entry.key: entry.value for entry in section.entries}
        for section in ini.sections
    }
    map_values = {key.casefold(): value for key, value in sections.get("map", {}).items()}
    origin_x, origin_y, width, height = _map_bounds(
        map_values.get("localsize") or map_values.get("size") or "0,0,100,100"
    )
    objects: list[MapObject] = []
    for section_name, kind in (
        ("structures", "structure"),
        ("units", "unit"),
        ("infantry", "infantry"),
        ("aircraft", "aircraft"),
    ):
        for value in sections.get(section_name, {}).values():
            fields = [item.strip() for item in value.split(",")]
            if len(fields) < 5:
                continue
            try:
                x, y = int(fields[3]), int(fields[4])
            except ValueError:
                continue
            objects.append(MapObject(kind, fields[1] or kind, x, y))
    for key, name in sections.get("terrain", {}).items():
        position = _packed_position(key)
        if position is not None:
            objects.append(MapObject("terrain", name, *position))
    for key, value in sections.get("waypoints", {}).items():
        position = _packed_position(value)
        if position is not None:
            objects.append(MapObject("waypoint", key, *position))
    return MapOverview(
        ini,
        origin_x,
        origin_y,
        width,
        height,
        map_values.get("theater"),
        tuple(objects),
    )


def _map_bounds(value: str) -> tuple[int, int, int, int]:
    try:
        values = [int(item.strip()) for item in value.split(",")]
    except ValueError:
        values = []
    if len(values) != 4:
        return (0, 0, 100, 100)
    x, y, width, height = values
    return (
        x,
        y,
        max(1, min(width, MAX_MAP_DIMENSION)),
        max(1, min(height, MAX_MAP_DIMENSION)),
    )


def _packed_position(value: str) -> tuple[int, int] | None:
    try:
        packed = int(value.strip())
    except ValueError:
        return None
    return packed % 1_000, packed // 1_000


__all__ = ["MapObject", "MapOverview", "parse_map"]
