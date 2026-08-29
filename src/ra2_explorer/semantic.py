from __future__ import annotations

import re
import threading
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PIL import Image

from ra2_explorer.codecs.csf import CsfValue, parse_csf
from ra2_explorer.codecs.hva import parse_hva
from ra2_explorer.codecs.mix import classic_mix_hash, ra2_mix_hash
from ra2_explorer.codecs.pal import Palette, grayscale_palette
from ra2_explorer.codecs.shp import ShpFile, parse_shp
from ra2_explorer.codecs.text import parse_ini
from ra2_explorer.codecs.vxl import (
    VxlRenderPart,
    VxlScene,
    build_vxl_scene,
    parse_vxl,
    render_vxl_composite,
)
from ra2_explorer.errors import AssetNotFoundError, InvalidFormatError, Ra2ExplorerError
from ra2_explorer.library import AssetReader
from ra2_explorer.storage import Database

ENTITY_KINDS = ("vehicle", "infantry", "aircraft", "building")
_TYPE_SECTIONS = {
    "vehicle": "VehicleTypes",
    "infantry": "InfantryTypes",
    "aircraft": "AircraftTypes",
    "building": "BuildingTypes",
}
_RULE_FIELDS = {
    "category": "category",
    "owner": "owner",
    "cost": "cost",
    "strength": "strength",
    "armor": "armor",
    "speed": "speed",
    "sight": "sight",
    "tech_level": "techlevel",
    "prerequisite": "prerequisite",
    "primary": "primary",
    "secondary": "secondary",
    "elite_primary": "eliteprimary",
    "elite_secondary": "elitesecondary",
    "turret": "turret",
    "naval": "naval",
    "movement_zone": "movementzone",
}
_ART_FIELDS = {
    "cameo": "cameo",
    "alt_cameo": "altcameo",
    "turret_offset": "turretoffset",
    "primary_fire_flh": "primaryfireflh",
    "secondary_fire_flh": "secondaryfireflh",
    "remapable": "remapable",
    "voxel": "voxel",
    "new_theater": "newtheater",
    "foundation": "foundation",
    "facings": "facings",
}
_AUDIO_RULE_FIELDS = {
    "select": "voiceselect",
    "move": "voicemove",
    "attack": "voiceattack",
    "feedback": "voicefeedback",
    "special_attack": "voicespecialattack",
    "enter": "voiceenter",
    "capture": "voicecapture",
    "deploy": "voicedeploy",
    "harvest": "voiceharvest",
    "die": "diesound",
    "create": "createsound",
    "movement": "movesound",
    "deploy_sound": "deploysound",
    "undeploy": "undeploysound",
    "enter_transport": "entertransportsound",
    "leave_transport": "leavetransportsound",
    "turret_rotate": "turretrotatesound",
    "start_moving": "startmovingsound",
    "stop_moving": "stopmovingsound",
    "activate": "activatesound",
    "deactivate": "deactivatesound",
    "cloak": "cloaksound",
    "uncloak": "uncloaksound",
    "chrono_in": "chronoinsound",
    "chrono_out": "chronooutsound",
    "crashing": "crashingsound",
    "impact_land": "impactlandsound",
}
_WEAPON_FIELDS = {
    "damage": "damage",
    "rate_of_fire": "rof",
    "range": "range",
    "minimum_range": "minimumrange",
    "burst": "burst",
    "speed": "speed",
    "projectile": "projectile",
    "warhead": "warhead",
    "report": "report",
    "animation": "anim",
}
_PROJECTILE_FIELDS = {
    "image": "image",
    "arcing": "arcing",
    "invisible": "invisible",
    "proximity": "proximity",
    "rotation": "rot",
    "acceleration": "acceleration",
    "inaccurate": "inaccurate",
}
_WARHEAD_FIELDS = {
    "verses": "verses",
    "cell_spread": "cellspread",
    "percent_at_max": "percentatmax",
    "infantry_death": "infdeath",
    "animation_list": "animlist",
    "wall": "wall",
    "wood": "wood",
    "radiation": "radiation",
}
_WEAPON_SLOTS = (
    ("primary", "primary"),
    ("secondary", "secondary"),
    ("elite_primary", "eliteprimary"),
    ("elite_secondary", "elitesecondary"),
)


@dataclass(frozen=True, slots=True)
class EntityComponent:
    role: str
    expected_name: str
    asset: dict[str, Any] | None

    def as_dict(self) -> dict[str, object]:
        selected = None
        if self.asset:
            selected = {
                key: self.asset[key]
                for key in (
                    "id",
                    "display_name",
                    "format",
                    "virtual_path",
                    "size",
                    "storage_kind",
                )
            }
        return {
            "role": self.role,
            "expected_name": self.expected_name,
            "asset": selected,
        }


@dataclass(frozen=True, slots=True)
class EntityDependency:
    id: str
    kind: str
    slot: str
    parent: str | None
    resolved: bool
    properties: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "slot": self.slot,
            "parent": self.parent,
            "resolved": self.resolved,
            "properties": self.properties,
        }


@dataclass(frozen=True, slots=True)
class MediaSample:
    name: str
    text: str | None
    asset: dict[str, Any] | None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "text": self.text,
            "asset": _asset_summary(self.asset),
        }


@dataclass(frozen=True, slots=True)
class MediaAssociation:
    kind: str
    slot: str
    event: str
    source: str
    samples: tuple[MediaSample, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "slot": self.slot,
            "event": self.event,
            "source": self.source,
            "samples": [sample.as_dict() for sample in self.samples],
        }


@dataclass(frozen=True, slots=True)
class GameEntity:
    id: str
    kind: str
    display_name: str
    internal_name: str
    ui_name: str | None
    ui_name_resolved: bool
    image: str
    voxel: bool
    rules: dict[str, str]
    art: dict[str, str]
    components: tuple[EntityComponent, ...]
    dependencies: tuple[EntityDependency, ...]
    media: tuple[MediaAssociation, ...]

    @property
    def renderable(self) -> bool:
        return self.component("body") is not None

    def component(self, role: str) -> dict[str, Any] | None:
        return next(
            (component.asset for component in self.components if component.role == role),
            None,
        )

    def summary(self) -> dict[str, object]:
        body = self.component("body")
        return {
            "id": self.id,
            "kind": self.kind,
            "display_name": self.display_name,
            "internal_name": self.internal_name,
            "ui_name": self.ui_name,
            "image": self.image,
            "voxel": self.voxel,
            "renderable": self.renderable,
            "component_count": sum(component.asset is not None for component in self.components),
            "body_format": body["format"] if body else None,
            "media_kinds": sorted({association.kind for association in self.media}),
            "media_count": len(self.media),
            "cost": self.rules.get("cost"),
            "strength": self.rules.get("strength"),
            "owner": self.rules.get("owner"),
            "primary": self.rules.get("primary"),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.summary(),
            "rules": self.rules,
            "art": self.art,
            "components": [component.as_dict() for component in self.components],
            "dependencies": [dependency.as_dict() for dependency in self.dependencies],
            "media": [association.as_dict() for association in self.media],
        }


@dataclass(frozen=True, slots=True)
class SemanticCatalog:
    source_id: str
    entities: tuple[GameEntity, ...]
    inputs: dict[str, tuple[dict[str, object], ...]]
    warnings: tuple[str, ...]
    audio_events: dict[str, tuple[MediaSample, ...]]
    eva_events: tuple[MediaAssociation, ...]

    def get(self, entity_id: str) -> GameEntity:
        folded = entity_id.casefold()
        entity = next((item for item in self.entities if item.id.casefold() == folded), None)
        if entity is None:
            raise AssetNotFoundError("单位不存在")
        return entity


class SemanticLibrary:
    def __init__(self, database: Database, reader: AssetReader):
        self.database = database
        self.reader = reader
        self._cache: dict[str, tuple[tuple[object, ...], SemanticCatalog]] = {}
        self._parsed_cache: OrderedDict[str, object] = OrderedDict()
        self._shp_frame_cache: dict[str, tuple[int, ...]] = {}
        self._lock = threading.RLock()

    def catalog(self, source_id: str) -> SemanticCatalog:
        source = self.database.get_source(source_id)
        token = (source.get("scanned_at"), source.get("asset_count"), source.get("state"))
        with self._lock:
            cached = self._cache.get(source_id)
            if cached and cached[0] == token:
                return cached[1]
            self._parsed_cache.clear()
            self._shp_frame_cache.clear()
            catalog = self._build(source_id)
            self._cache[source_id] = (token, catalog)
            return catalog

    def list_entities(
        self,
        source_id: str,
        *,
        query: str | None = None,
        kind: str | None = None,
        renderable: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        catalog = self.catalog(source_id)
        entities = list(catalog.entities)
        counts = Counter(entity.kind for entity in entities)
        if kind:
            entities = [entity for entity in entities if entity.kind == kind]
        if renderable is not None:
            entities = [entity for entity in entities if entity.renderable is renderable]
        if query:
            needle = query.casefold()
            entities = [entity for entity in entities if needle in _entity_search_text(entity)]
        total = len(entities)
        selected = entities[offset : offset + limit]
        return {
            "items": [entity.summary() for entity in selected],
            "total": total,
            "kinds": [
                {"kind": entity_kind, "count": counts.get(entity_kind, 0)}
                for entity_kind in ENTITY_KINDS
            ],
            "warnings": list(catalog.warnings),
        }

    def get_entity(self, source_id: str, entity_id: str) -> dict[str, object]:
        entity = self.catalog(source_id).get(entity_id)
        return {**entity.as_dict(), "preview": self._preview_info(entity)}

    def asset_associations(self, source_id: str, asset_id: str) -> dict[str, object]:
        catalog = self.catalog(source_id)
        items: list[dict[str, object]] = []
        seen: set[tuple[str, ...]] = set()

        def append(item: dict[str, object], key: tuple[str, ...]) -> None:
            if key not in seen:
                seen.add(key)
                items.append(item)

        for entity in catalog.entities:
            for component in entity.components:
                if component.asset and component.asset["id"] == asset_id:
                    append(
                        {
                            "scope": "entity",
                            "kind": "component",
                            "slot": component.role,
                            "event": component.expected_name,
                            "entity": entity.summary(),
                            "text": None,
                        },
                        ("entity", entity.id, "component", component.role),
                    )
            for association in entity.media:
                for sample in association.samples:
                    if sample.asset and sample.asset["id"] == asset_id:
                        append(
                            {
                                "scope": "entity",
                                "kind": association.kind,
                                "slot": association.slot,
                                "event": association.event,
                                "entity": entity.summary(),
                                "text": sample.text,
                            },
                            (
                                "entity",
                                entity.id,
                                association.kind,
                                association.slot,
                                association.event.casefold(),
                            ),
                        )

        for association in catalog.eva_events:
            for sample in association.samples:
                if sample.asset and sample.asset["id"] == asset_id:
                    append(
                        {
                            "scope": "event",
                            "kind": association.kind,
                            "slot": association.slot,
                            "event": association.event,
                            "entity": None,
                            "text": sample.text,
                        },
                        (
                            "event",
                            association.slot,
                            association.event.casefold(),
                            sample.name.casefold(),
                        ),
                    )

        for event, samples in catalog.audio_events.items():
            for sample in samples:
                if sample.asset and sample.asset["id"] == asset_id:
                    append(
                        {
                            "scope": "event",
                            "kind": "sound",
                            "slot": "sound_event",
                            "event": event,
                            "entity": None,
                            "text": sample.text,
                        },
                        ("sound", event.casefold(), sample.name.casefold()),
                    )
        return {"items": items[:100], "total": len(items)}

    def diagnostics(self, source_id: str, *, limit: int = 20) -> dict[str, object]:
        catalog = self.catalog(source_id)
        entities = catalog.entities
        missing_roles = Counter(
            component.role
            for entity in entities
            for component in entity.components
            if component.asset is None
        )
        dependency_count = sum(len(entity.dependencies) for entity in entities)
        unresolved_dependencies = [
            (entity, dependency)
            for entity in entities
            for dependency in entity.dependencies
            if not dependency.resolved
        ]
        renderable_count = sum(entity.renderable for entity in entities)
        localized_count = sum(entity.ui_name_resolved for entity in entities)
        resolved_components = sum(
            component.asset is not None
            for entity in entities
            for component in entity.components
        )
        component_count = sum(len(entity.components) for entity in entities)
        return {
            "status": "ready" if entities else "empty",
            "entity_count": len(entities),
            "renderable_count": renderable_count,
            "renderable_percent": _percentage(renderable_count, len(entities)),
            "localized_count": localized_count,
            "localized_percent": _percentage(localized_count, len(entities)),
            "component_count": component_count,
            "resolved_component_count": resolved_components,
            "component_percent": _percentage(resolved_components, component_count),
            "dependency_count": dependency_count,
            "unresolved_dependency_count": len(unresolved_dependencies),
            "kinds": [
                {
                    "kind": kind,
                    "count": sum(entity.kind == kind for entity in entities),
                    "renderable_count": sum(
                        entity.kind == kind and entity.renderable for entity in entities
                    ),
                }
                for kind in ENTITY_KINDS
            ],
            "missing_components": [
                {"role": role, "count": count}
                for role, count in missing_roles.most_common()
            ],
            "samples": {
                "missing_body": [
                    {"id": entity.id, "display_name": entity.display_name}
                    for entity in entities
                    if not entity.renderable
                ][:limit],
                "unresolved_ui_name": [
                    {"id": entity.id, "ui_name": entity.ui_name}
                    for entity in entities
                    if entity.ui_name and not entity.ui_name_resolved
                ][:limit],
                "unresolved_dependencies": [
                    {
                        "entity_id": entity.id,
                        "id": dependency.id,
                        "kind": dependency.kind,
                        "slot": dependency.slot,
                    }
                    for entity, dependency in unresolved_dependencies[:limit]
                ],
            },
            "inputs": catalog.inputs,
            "warnings": list(catalog.warnings),
        }

    def render(
        self,
        source_id: str,
        entity_id: str,
        *,
        palette: Palette | None,
        frame: int,
        facing: int,
        player_color: str | None,
        scale: int,
    ) -> tuple[GameEntity, Image.Image]:
        entity = self.catalog(source_id).get(entity_id)
        body = entity.component("body")
        if body is None:
            raise InvalidFormatError("该单位没有可渲染的主体资产")
        if body["format"] == "vxl":
            parts = self._voxel_parts(entity)
            return entity, render_vxl_composite(
                parts,
                palette=palette,
                frame=frame,
                facing=facing,
                player_color=player_color,
                scale=scale,
            )
        sprite = self._parse_asset(body, parse_shp)
        if not sprite.frames:
            raise InvalidFormatError("单位 SHP 没有可渲染帧")
        visible_frames = self._visible_shp_frames(body, sprite)
        if not visible_frames:
            raise InvalidFormatError("单位 SHP 的所有帧均为空")
        active_palette = palette
        if player_color:
            active_palette = (palette or grayscale_palette()).with_player_color(player_color)
        return entity, sprite.render(
            visible_frames[frame % len(visible_frames)],
            active_palette,
            scale=scale,
        )

    def model_scene(
        self,
        source_id: str,
        entity_id: str,
        *,
        palette: Palette | None,
        frame: int,
        player_color: str | None,
    ) -> tuple[GameEntity, VxlScene]:
        entity = self.catalog(source_id).get(entity_id)
        body = entity.component("body")
        if body is None or body["format"] != "vxl":
            raise InvalidFormatError("该单位不是可交互的 VXL 模型")
        return entity, build_vxl_scene(
            self._voxel_parts(entity),
            palette=palette,
            frame=frame,
            player_color=player_color,
        )

    def _voxel_parts(self, entity: GameEntity) -> tuple[VxlRenderPart, ...]:
        parts = []
        for role, animation_role in (
            ("body", "body_hva"),
            ("turret", "turret_hva"),
            ("barrel", "barrel_hva"),
        ):
            asset = entity.component(role)
            if not asset:
                continue
            model = self._parse_asset(asset, parse_vxl)
            animation_asset = entity.component(animation_role)
            animation = None
            if animation_asset:
                animation = self._parse_asset(animation_asset, parse_hva)
            parts.append(VxlRenderPart(model, animation))
        return tuple(parts)

    def _preview_info(self, entity: GameEntity) -> dict[str, object]:
        body = entity.component("body")
        base: dict[str, object] = {
            "format": str(body["format"]) if body else None,
            "frame_count": 0 if body is None else 1,
            "facing_count": 8 if entity.voxel else _positive_int(entity.art.get("facings"), 1),
            "supports_facing": bool(body and body["format"] == "vxl"),
            "supports_player_color": _yes(entity.art.get("remapable")),
        }
        if body is None:
            return base
        warnings = []
        try:
            if body["format"] == "vxl":
                model = self._parse_asset(body, parse_vxl)
                frame_counts = []
                for role in ("body_hva", "turret_hva", "barrel_hva"):
                    asset = entity.component(role)
                    if asset:
                        animation = self._parse_asset(asset, parse_hva)
                        frame_counts.append(animation.frame_count)
                base.update(
                    {
                        "frame_count": max((1, *frame_counts)),
                        "limb_count": sum(
                            len(self._parse_asset(asset, parse_vxl).limbs)
                            for role in ("body", "turret", "barrel")
                            if (asset := entity.component(role))
                        ),
                        "voxel_count": sum(
                            self._parse_asset(asset, parse_vxl).voxel_count
                            for role in ("body", "turret", "barrel")
                            if (asset := entity.component(role))
                        ),
                        "remap_range": [model.remap_start, model.remap_end],
                    }
                )
            else:
                sprite = self._parse_asset(body, parse_shp)
                visible_frames = self._visible_shp_frames(body, sprite)
                base.update(
                    {
                        "frame_count": len(visible_frames),
                        "source_frame_count": len(sprite.frames),
                        "frame_indices": visible_frames,
                        "width": sprite.width,
                        "height": sprite.height,
                    }
                )
        except (OSError, Ra2ExplorerError, ValueError) as error:
            warnings.append(str(error))
        if warnings:
            base["warnings"] = warnings
        return base

    def _visible_shp_frames(
        self,
        asset: dict[str, Any],
        sprite: ShpFile,
    ) -> tuple[int, ...]:
        asset_id = str(asset["id"])
        with self._lock:
            cached = self._shp_frame_cache.get(asset_id)
            if cached is not None:
                return cached
        visible = tuple(
            frame.index
            for frame in sprite.frames
            if not frame.empty and any(sprite.pixels(frame.index))
        )
        with self._lock:
            self._shp_frame_cache[asset_id] = visible
        return visible

    def _parse_asset(
        self,
        asset: dict[str, Any],
        parser: Callable[[bytes], Any],
    ) -> Any:
        asset_id = str(asset["id"])
        with self._lock:
            cached = self._parsed_cache.get(asset_id)
            if cached is not None:
                self._parsed_cache.move_to_end(asset_id)
                return cached
        _, data = self.reader.read(asset_id)
        parsed = parser(data)
        with self._lock:
            self._parsed_cache[asset_id] = parsed
            self._parsed_cache.move_to_end(asset_id)
            while len(self._parsed_cache) > 24:
                self._parsed_cache.popitem(last=False)
        return parsed

    def _build(self, source_id: str) -> SemanticCatalog:
        assets = self.database.assets_for_formats(
            source_id,
            (
                "ini",
                "csf",
                "vxl",
                "hva",
                "shp",
                "bag_audio",
                "wav",
                "aud",
                "video",
                "binary",
            ),
        )
        asset_index = _index_assets(assets)

        warnings = []
        rules_assets = _named_inputs(asset_index.by_name, ("rules.ini", "rulesmd.ini"))
        art_assets = _named_inputs(asset_index.by_name, ("art.ini", "artmd.ini"))
        sound_assets = _named_inputs(asset_index.by_name, ("sound.ini", "soundmd.ini"))
        eva_assets = _named_inputs(asset_index.by_name, ("eva.ini", "evamd.ini"))
        csf_assets = sorted(
            (asset for asset in assets if asset["format"] == "csf"),
            key=_config_precedence,
        )
        rules = _merge_ini_inputs(self.reader, rules_assets, warnings)
        art = _merge_ini_inputs(self.reader, art_assets, warnings)
        sounds = _merge_ini_inputs(self.reader, sound_assets, warnings)
        eva = _merge_ini_inputs(self.reader, eva_assets, warnings)
        strings, voice_strings = _merge_csf_inputs(self.reader, csf_assets, warnings)
        audio_events = _build_audio_events(sounds, asset_index, voice_strings)
        eva_events = _build_eva_events(eva, asset_index, voice_strings)

        entities = []
        seen = set()
        for kind, type_section in _TYPE_SECTIONS.items():
            for entity_id in _type_values(rules.get(type_section.casefold(), {})):
                folded = entity_id.casefold()
                if folded in seen:
                    continue
                seen.add(folded)
                rule_values = rules.get(folded, {})
                art_key = rule_values.get("image") or entity_id
                art_values = art.get(art_key.casefold(), {})
                image = art_values.get("image") or art_key
                ui_name = rule_values.get("uiname")
                internal_name = rule_values.get("name") or entity_id
                localized_name = strings.get(ui_name.casefold()) if ui_name else None
                display_name = localized_name or internal_name
                voxel = _yes(art_values.get("voxel"))
                components, detected_voxel = _resolve_components(
                    asset_index,
                    image,
                    art_values,
                    voxel,
                    _yes(rule_values.get("turret")),
                )
                dependencies = _resolve_dependencies(rule_values, rules)
                entities.append(
                    GameEntity(
                        entity_id,
                        kind,
                        display_name,
                        internal_name,
                        ui_name,
                        localized_name is not None,
                        image,
                        voxel or detected_voxel,
                        _selected_fields(rule_values, _RULE_FIELDS),
                        _selected_fields(art_values, _ART_FIELDS),
                        components,
                        dependencies,
                        _resolve_media(
                            entity_id,
                            rule_values,
                            art_values,
                            components,
                            dependencies,
                            art,
                            asset_index,
                            audio_events,
                            voice_strings,
                        ),
                    )
                )
        entities.sort(key=lambda entity: (entity.display_name.casefold(), entity.id.casefold()))
        inputs = {
            "rules": tuple(_input_summary(asset) for asset in rules_assets),
            "art": tuple(_input_summary(asset) for asset in art_assets),
            "sound": tuple(_input_summary(asset) for asset in sound_assets),
            "eva": tuple(_input_summary(asset) for asset in eva_assets),
            "csf": tuple(_input_summary(asset) for asset in csf_assets),
        }
        if not rules_assets:
            warnings.append("未找到 rules.ini 或 rulesmd.ini")
        if not art_assets:
            warnings.append("未找到 art.ini 或 artmd.ini")
        return SemanticCatalog(
            source_id,
            tuple(entities),
            inputs,
            tuple(warnings),
            audio_events,
            eva_events,
        )


def _named_inputs(
    by_name: dict[str, list[dict[str, Any]]],
    names: tuple[str, ...],
) -> list[dict[str, Any]]:
    assets = []
    for name in names:
        assets.extend(by_name.get(name.casefold(), ()))
    return sorted(assets, key=_config_precedence)


def _merge_ini_inputs(
    reader: AssetReader,
    assets: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for asset in assets:
        try:
            _, data = reader.read(str(asset["id"]))
            parsed = parse_ini(data)
        except (OSError, Ra2ExplorerError, ValueError) as error:
            warnings.append(f"{asset['display_name']}: {error}")
            continue
        for section in parsed.sections:
            target = merged.setdefault(section.name.casefold(), {})
            for entry in section.entries:
                target[entry.key.casefold()] = _clean_value(entry.value)
    return merged


def _merge_csf_inputs(
    reader: AssetReader,
    assets: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[dict[str, str], dict[str, CsfValue]]:
    strings: dict[str, str] = {}
    voice_strings: dict[str, CsfValue] = {}
    for asset in assets:
        try:
            _, data = reader.read(str(asset["id"]))
            parsed = parse_csf(data)
        except (OSError, Ra2ExplorerError, ValueError) as error:
            warnings.append(f"{asset['display_name']}: {error}")
            continue
        for label in parsed.labels:
            if label.values:
                folded = label.name.casefold()
                strings[folded] = label.values[0].text
                if folded.startswith("vox:"):
                    voice_strings[folded[4:]] = label.values[0]
    return strings, voice_strings


@dataclass(slots=True)
class _AssetIndex:
    by_name: dict[str, list[dict[str, Any]]]
    by_crc: dict[int, list[dict[str, Any]]]


def _index_assets(assets: list[dict[str, Any]]) -> _AssetIndex:
    by_name: dict[str, list[dict[str, Any]]] = {}
    by_crc: dict[int, list[dict[str, Any]]] = {}
    for asset in assets:
        for value in (asset.get("display_name"), asset.get("name")):
            if value:
                bucket = by_name.setdefault(str(value).casefold(), [])
                if asset not in bucket:
                    bucket.append(asset)
        if isinstance(asset.get("crc"), int):
            by_crc.setdefault(int(asset["crc"]), []).append(asset)
    return _AssetIndex(by_name, by_crc)


def _asset_summary(asset: dict[str, Any] | None) -> dict[str, object] | None:
    if asset is None:
        return None
    return {
        key: asset[key]
        for key in (
            "id",
            "display_name",
            "format",
            "virtual_path",
            "size",
            "storage_kind",
        )
    }


def _build_audio_events(
    sections: dict[str, dict[str, str]],
    assets: _AssetIndex,
    voice_strings: dict[str, CsfValue],
) -> dict[str, tuple[MediaSample, ...]]:
    events = {}
    for event, values in sections.items():
        sample_names = _tokens(values.get("sounds") or values.get("sound"))
        if sample_names:
            events[event] = tuple(
                _audio_sample(name, assets, voice_strings) for name in sample_names
            )
    return events


def _build_eva_events(
    sections: dict[str, dict[str, str]],
    assets: _AssetIndex,
    voice_strings: dict[str, CsfValue],
) -> tuple[MediaAssociation, ...]:
    associations = []
    for event, values in sections.items():
        fallback_text = values.get("text")
        for faction in ("allied", "soviet", "yuri"):
            for sample_name in _tokens(values.get(faction)):
                sample = _audio_sample(sample_name, assets, voice_strings)
                if sample.text is None and fallback_text:
                    sample = MediaSample(sample.name, fallback_text, sample.asset)
                associations.append(
                    MediaAssociation("voice", f"eva_{faction}", event, "eva", (sample,))
                )
    return tuple(associations)


def _resolve_media(
    entity_id: str,
    rules: dict[str, str],
    entity_art: dict[str, str],
    components: tuple[EntityComponent, ...],
    dependencies: tuple[EntityDependency, ...],
    art_sections: dict[str, dict[str, str]],
    assets: _AssetIndex,
    audio_events: dict[str, tuple[MediaSample, ...]],
    voice_strings: dict[str, CsfValue],
) -> tuple[MediaAssociation, ...]:
    associations: list[MediaAssociation] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(association: MediaAssociation) -> None:
        key = (
            association.kind,
            association.slot,
            association.event.casefold(),
            association.source.casefold(),
        )
        if association.samples and key not in seen:
            seen.add(key)
            associations.append(association)

    for slot, field in _AUDIO_RULE_FIELDS.items():
        for event in _references(rules.get(field)):
            samples = audio_events.get(event.casefold()) or (
                _audio_sample(event, assets, voice_strings),
            )
            add(
                MediaAssociation(
                    "voice" if field.startswith("voice") else "sound",
                    slot,
                    event,
                    entity_id,
                    samples,
                )
            )

    for dependency in dependencies:
        if dependency.kind == "weapon":
            for event in _references(dependency.properties.get("report")):
                samples = audio_events.get(event.casefold()) or (
                    _audio_sample(event, assets, voice_strings),
                )
                add(MediaAssociation("sound", dependency.slot, event, dependency.id, samples))
            for animation in _references(dependency.properties.get("animation")):
                add(
                    MediaAssociation(
                        "animation",
                        dependency.slot,
                        animation,
                        dependency.id,
                        _animation_samples(animation, art_sections, assets),
                    )
                )
        elif dependency.kind == "warhead":
            for animation in _references(dependency.properties.get("animation_list")):
                add(
                    MediaAssociation(
                        "animation",
                        dependency.slot,
                        animation,
                        dependency.id,
                        _animation_samples(animation, art_sections, assets),
                    )
                )

    body = next((item for item in components if item.role == "body" and item.asset), None)
    if body and body.asset and body.asset["format"] == "shp":
        add(
            MediaAssociation(
                "animation",
                "body_animation",
                entity_id,
                entity_id,
                (MediaSample(str(body.asset["display_name"]), None, body.asset),),
            )
        )
    for component in components:
        if component.asset and component.role.endswith("_hva"):
            add(
                MediaAssociation(
                    "animation",
                    component.role,
                    component.expected_name,
                    entity_id,
                    (
                        MediaSample(
                            str(component.asset["display_name"]),
                            None,
                            component.asset,
                        ),
                    ),
                )
            )

    for field, value in entity_art.items():
        if not (field.endswith("anim") or field in {"buildup", "bibshape"}):
            continue
        for animation in _references(value):
            add(
                MediaAssociation(
                    "animation",
                    field,
                    animation,
                    entity_id,
                    _animation_samples(animation, art_sections, assets),
                )
            )
    return tuple(associations)


def _audio_sample(
    raw_name: str,
    assets: _AssetIndex,
    voice_strings: dict[str, CsfValue],
) -> MediaSample:
    name = raw_name.strip().lstrip("$")
    stem = name.rsplit(".", 1)[0]
    names = (name,) if "." in name else (f"{name}.wav", f"{name}.aud")
    asset = _find_asset(assets, names, ("bag_audio", "wav", "aud"))
    localized = voice_strings.get(stem.casefold())
    return MediaSample(name, localized.text if localized else None, asset)


def _animation_samples(
    reference: str,
    art_sections: dict[str, dict[str, str]],
    assets: _AssetIndex,
) -> tuple[MediaSample, ...]:
    values = art_sections.get(reference.casefold(), {})
    image = values.get("image") or reference
    names = (image,) if "." in image else (f"{image}.shp", f"{image}.hva")
    asset = _find_asset(assets, names, ("shp", "hva", "video"))
    return (MediaSample(image, None, asset),)


def _type_values(section: dict[str, str]) -> list[str]:
    def key(item: tuple[str, str]) -> tuple[int, object]:
        name = item[0]
        return (0, int(name)) if name.isdigit() else (1, name)

    return [value for _, value in sorted(section.items(), key=key) if value]


def _resolve_components(
    assets: _AssetIndex,
    image: str,
    art: dict[str, str],
    voxel: bool,
    has_turret: bool,
) -> tuple[tuple[EntityComponent, ...], bool]:
    body_vxl = _find_asset(assets, (f"{image}.vxl",), ("vxl",))
    detected_voxel = body_vxl is not None
    components = []
    if voxel or detected_voxel:
        components.append(EntityComponent("body", f"{image}.vxl", body_vxl))
        components.append(
            EntityComponent(
                "body_hva",
                f"{image}.hva",
                _find_asset(assets, (f"{image}.hva",), ("hva",)),
            )
        )
        for role, suffix in (("turret", "TUR"), ("barrel", "BARL")):
            asset = _find_asset(assets, (f"{image}{suffix}.vxl",), ("vxl",))
            if asset or (role == "turret" and has_turret):
                components.append(EntityComponent(role, f"{image}{suffix}.vxl", asset))
                components.append(
                    EntityComponent(
                        f"{role}_hva",
                        f"{image}{suffix}.hva",
                        _find_asset(assets, (f"{image}{suffix}.hva",), ("hva",)),
                    )
                )
    else:
        expected = f"{image}.shp"
        components.append(
            EntityComponent(
                "body",
                expected,
                _find_asset(
                    assets,
                    _theater_shp_names(image, _yes(art.get("newtheater"))),
                    ("shp",),
                ),
            )
        )

    for role, field in (("cameo", "cameo"), ("alt_cameo", "altcameo")):
        value = art.get(field)
        if value:
            expected = f"{value}.shp"
            components.append(
                EntityComponent(role, expected, _find_asset(assets, (expected,), ("shp",)))
            )
    return tuple(components), detected_voxel


def _theater_shp_names(image: str, new_theater: bool) -> tuple[str, ...]:
    names = [f"{image}.shp"]
    if new_theater and len(image) > 1:
        for theater in "ATSUNLD":
            variant = f"{image[0]}{theater}{image[2:]}.shp"
            if variant.casefold() not in {name.casefold() for name in names}:
                names.append(variant)
    return tuple(names)


def _resolve_dependencies(
    entity_rules: dict[str, str],
    sections: dict[str, dict[str, str]],
) -> tuple[EntityDependency, ...]:
    dependencies = []
    seen = set()

    def add(
        dependency_id: str,
        kind: str,
        slot: str,
        parent: str | None,
        fields: dict[str, str],
    ) -> dict[str, str]:
        values = sections.get(dependency_id.casefold(), {})
        key = (dependency_id.casefold(), kind, slot, (parent or "").casefold())
        if key not in seen:
            seen.add(key)
            dependencies.append(
                EntityDependency(
                    dependency_id,
                    kind,
                    slot,
                    parent,
                    bool(values),
                    _selected_fields(values, fields),
                )
            )
        return values

    for slot, field in _WEAPON_SLOTS:
        for weapon_id in _references(entity_rules.get(field)):
            weapon = add(weapon_id, "weapon", slot, None, _WEAPON_FIELDS)
            for projectile_id in _references(weapon.get("projectile")):
                add(projectile_id, "projectile", slot, weapon_id, _PROJECTILE_FIELDS)
            for warhead_id in _references(weapon.get("warhead")):
                add(warhead_id, "warhead", slot, weapon_id, _WARHEAD_FIELDS)
    return tuple(dependencies)


def _find_asset(
    assets: _AssetIndex,
    names: tuple[str, ...],
    formats: tuple[str, ...],
) -> dict[str, Any] | None:
    for name in names:
        candidates = [
            asset
            for asset in assets.by_name.get(name.casefold(), ())
            if asset["format"] in formats
        ]
        if candidates:
            return max(candidates, key=_asset_precedence)
        try:
            hashes = {ra2_mix_hash(name), classic_mix_hash(name)}
        except ValueError:
            continue
        candidates = [
            asset
            for crc in hashes
            for asset in assets.by_crc.get(crc, ())
            if asset["format"] in formats or asset["format"] == "binary"
        ]
        if candidates:
            selected = dict(max(candidates, key=_asset_precedence))
            display_name = name.replace("\\", "/").rsplit("/", 1)[-1]
            extension = display_name.rsplit(".", 1)[-1].casefold() if "." in display_name else ""
            expected_format = {
                "aud": "aud",
                "bik": "video",
                "hva": "hva",
                "shp": "shp",
                "vqa": "video",
                "vxl": "vxl",
                "wav": "wav",
            }.get(extension)
            selected.update(
                {
                    "name": display_name,
                    "display_name": display_name,
                    "extension": extension,
                    "confidence": "semantic",
                }
            )
            if selected["format"] == "binary" and expected_format:
                selected["format"] = expected_format
            return selected
    return None


def _asset_precedence(asset: dict[str, Any]) -> tuple[int, str]:
    path = str(asset["virtual_path"]).replace("\\", "/").casefold()
    score = 1_000_000 if asset["storage_kind"] == "loose" else 0
    for pattern, base in ((r"expandmd(\d+)", 800_000), (r"expand(\d+)", 600_000)):
        match = re.search(pattern, path)
        if match:
            score += base + int(match.group(1))
            break
    if "ra2md.mix" in path:
        score += 400_000
    elif "ra2.mix" in path:
        score += 200_000
    return score, path


def _config_precedence(asset: dict[str, Any]) -> tuple[int, str]:
    score, path = _asset_precedence(asset)
    if "md." in str(asset["display_name"]).casefold():
        score += 100_000
    return score, path


def _selected_fields(values: dict[str, str], mapping: dict[str, str]) -> dict[str, str]:
    return {
        output: values[source]
        for output, source in mapping.items()
        if values.get(source) not in {None, ""}
    }


def _input_summary(asset: dict[str, Any]) -> dict[str, object]:
    return {
        "id": asset["id"],
        "display_name": asset["display_name"],
        "virtual_path": asset["virtual_path"],
    }


def _clean_value(value: str) -> str:
    return value.split(";", 1)[0].strip()


def _references(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        item
        for raw in value.split(",")
        if (item := raw.strip()) and item.casefold() != "none"
    )


def _tokens(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        token
        for token in re.split(r"[,\s]+", value)
        if token and token.casefold() != "none"
    )


def _yes(value: str | None) -> bool:
    return bool(value and value.casefold() in {"yes", "true", "1"})


def _positive_int(value: str | None, fallback: int) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


def _percentage(selected: int, total: int) -> float:
    return round(selected * 100 / total, 1) if total else 0.0


def _entity_search_text(entity: GameEntity) -> str:
    return "\n".join(
        (
            entity.id,
            entity.display_name,
            entity.internal_name,
            entity.ui_name or "",
            entity.image,
            *entity.rules.values(),
            *(dependency.id for dependency in entity.dependencies),
            *(
                value
                for dependency in entity.dependencies
                for value in dependency.properties.values()
            ),
            *(association.event for association in entity.media),
            *(sample.name for association in entity.media for sample in association.samples),
            *(
                sample.text or ""
                for association in entity.media
                for sample in association.samples
            ),
        )
    ).casefold()


__all__ = [
    "ENTITY_KINDS",
    "EntityComponent",
    "EntityDependency",
    "GameEntity",
    "MediaAssociation",
    "MediaSample",
    "SemanticCatalog",
    "SemanticLibrary",
]
