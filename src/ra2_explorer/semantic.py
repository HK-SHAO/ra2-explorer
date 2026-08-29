from __future__ import annotations

import re
import threading
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from PIL import Image

from ra2_explorer.codecs.csf import parse_csf
from ra2_explorer.codecs.hva import parse_hva
from ra2_explorer.codecs.mix import classic_mix_hash, ra2_mix_hash
from ra2_explorer.codecs.pal import Palette, grayscale_palette
from ra2_explorer.codecs.shp import ShpFile, parse_shp
from ra2_explorer.codecs.text import parse_ini
from ra2_explorer.codecs.vpl import VplFile, parse_vpl
from ra2_explorer.codecs.vxl import (
    VxlRenderPart,
    VxlScene,
    build_vxl_scene,
    parse_vxl,
    render_vxl_composite,
)
from ra2_explorer.errors import AssetNotFoundError, InvalidFormatError, Ra2ExplorerError
from ra2_explorer.library import AssetReader
from ra2_explorer.localization import (
    DEFAULT_GAME_LANGUAGE,
    GameLanguage,
    localize_game_text,
    localized_search_match,
)
from ra2_explorer.storage import Database

ENTITY_KINDS = ("vehicle", "infantry", "aircraft", "building")
ENTITY_USAGES = ("buildable", "hero", "tech", "civilian", "scenario")
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
    "elite_primary_fire_flh": "eliteprimaryfireflh",
    "elite_secondary_fire_flh": "elitesecondaryfireflh",
    **{f"weapon_{index}_flh": f"weapon{index}flh" for index in range(1, 18)},
    "remapable": "remapable",
    "voxel": "voxel",
    "new_theater": "newtheater",
    "foundation": "foundation",
    "facings": "facings",
    "sequence": "sequence",
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
class VoiceText:
    label: str
    text: str
    original_text: str | None
    localized_text: str | None


@dataclass(frozen=True, slots=True)
class AnimationPlayback:
    start_frame: int = 0
    frame_count: int | None = None
    facing_step: int = 0
    rate_ms: int | None = None
    loop_start: int | None = None
    loop_end: int | None = None
    loop_count: int | None = None
    direction: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "start_frame": self.start_frame,
            "frame_count": self.frame_count,
            "facing_step": self.facing_step,
            "rate_ms": self.rate_ms,
            "loop_start": self.loop_start,
            "loop_end": self.loop_end,
            "loop_count": self.loop_count,
            "direction": self.direction,
        }


@dataclass(frozen=True, slots=True)
class MediaSample:
    name: str
    text: str | None
    asset: dict[str, Any] | None
    original_text: str | None = None
    localized_text: str | None = None
    text_label: str | None = None
    animation: AnimationPlayback | None = None
    weight: int = 1

    def as_dict(
        self, language: GameLanguage = DEFAULT_GAME_LANGUAGE
    ) -> dict[str, object]:
        return {
            "name": self.name,
            "text": localize_game_text(self.text, language),
            "original_text": self.original_text,
            "localized_text": localize_game_text(self.localized_text, language),
            "text_label": self.text_label,
            "asset": _asset_summary(self.asset),
            "animation": self.animation.as_dict() if self.animation else None,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class MediaAssociation:
    kind: str
    slot: str
    event: str
    source: str
    samples: tuple[MediaSample, ...]
    role: str | None = None
    aliases: tuple[str, ...] = ()

    def as_dict(
        self, language: GameLanguage = DEFAULT_GAME_LANGUAGE
    ) -> dict[str, object]:
        return {
            "kind": self.kind,
            "slot": self.slot,
            "event": self.event,
            "source": self.source,
            "role": self.role,
            "aliases": list(self.aliases),
            "samples": [sample.as_dict(language) for sample in self.samples],
        }


@dataclass(frozen=True, slots=True)
class GameEntity:
    id: str
    kind: str
    usage: str
    display_name: str
    internal_name: str
    ui_name: str | None
    ui_name_resolved: bool
    image: str
    voxel: bool
    countries: tuple[str, ...]
    sides: tuple[str, ...]
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

    def summary(
        self, language: GameLanguage = DEFAULT_GAME_LANGUAGE
    ) -> dict[str, object]:
        body = self.component("body")
        return {
            "id": self.id,
            "kind": self.kind,
            "usage": self.usage,
            "display_name": localize_game_text(self.display_name, language),
            "internal_name": self.internal_name,
            "ui_name": self.ui_name,
            "image": self.image,
            "voxel": self.voxel,
            "countries": list(self.countries),
            "sides": list(self.sides),
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

    def as_dict(
        self, language: GameLanguage = DEFAULT_GAME_LANGUAGE
    ) -> dict[str, object]:
        return {
            **self.summary(language),
            "rules": self.rules,
            "art": self.art,
            "components": [component.as_dict() for component in self.components],
            "dependencies": [dependency.as_dict() for dependency in self.dependencies],
            "media": [association.as_dict(language) for association in self.media],
        }


@dataclass(frozen=True, slots=True)
class SemanticCatalog:
    source_id: str
    entities: tuple[GameEntity, ...]
    inputs: dict[str, tuple[dict[str, object], ...]]
    warnings: tuple[str, ...]
    audio_events: dict[str, tuple[MediaSample, ...]]
    eva_events: tuple[MediaAssociation, ...]
    countries: tuple[dict[str, str], ...]
    media_items: tuple[dict[str, object], ...]

    def get(self, entity_id: str) -> GameEntity:
        folded = entity_id.casefold()
        entity = next((item for item in self.entities if item.id.casefold() == folded), None)
        if entity is None:
            raise AssetNotFoundError("单位不存在")
        return entity


class SemanticLibrary:
    def __init__(
        self,
        database: Database,
        reader: AssetReader,
        voice_transcripts: dict[str, dict[str, str]] | None = None,
    ):
        self.database = database
        self.reader = reader
        self.voice_transcripts = voice_transcripts or {}
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
        usage: str | None = None,
        side: str | None = None,
        renderable: bool | None = None,
        language: GameLanguage = DEFAULT_GAME_LANGUAGE,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        catalog = self.catalog(source_id)
        entities = list(catalog.entities)
        if renderable is not None:
            entities = [entity for entity in entities if entity.renderable is renderable]
        counts = Counter(entity.kind for entity in entities)
        if kind:
            entities = [entity for entity in entities if entity.kind == kind]
        if query:
            entities = [
                entity
                for entity in entities
                if localized_search_match(query, _entity_search_text(entity))
            ]
        usage_counts = Counter(entity.usage for entity in entities)
        if usage:
            entities = [entity for entity in entities if entity.usage == usage]
        country_counts = Counter(country for entity in entities for country in entity.countries)
        side_counts = Counter(entity_side for entity in entities for entity_side in entity.sides)
        if side:
            selected_side = side.casefold()
            entities = [
                entity
                for entity in entities
                if any(entity_side.casefold() == selected_side for entity_side in entity.sides)
            ]
        total = len(entities)
        selected = entities[offset : offset + limit]
        return {
            "items": [entity.summary(language) for entity in selected],
            "total": total,
            "kinds": [
                {"kind": entity_kind, "count": counts.get(entity_kind, 0)}
                for entity_kind in ENTITY_KINDS
            ],
            "usages": [
                {"usage": entity_usage, "count": usage_counts.get(entity_usage, 0)}
                for entity_usage in ENTITY_USAGES
                if usage_counts.get(entity_usage, 0)
            ],
            "countries": [
                {
                    **country,
                    "display_name": localize_game_text(country["display_name"], language),
                    "count": country_counts.get(country["id"], 0),
                }
                for country in catalog.countries
                if country_counts.get(country["id"], 0)
            ],
            "sides": [
                {"id": side, "count": count}
                for side, count in sorted(side_counts.items())
                if side
            ],
            "warnings": list(catalog.warnings),
        }

    def list_media(
        self,
        source_id: str,
        *,
        query: str | None = None,
        kind: str | None = None,
        group: str | None = None,
        event_type: str | None = None,
        sort: str = "name_asc",
        language: GameLanguage = DEFAULT_GAME_LANGUAGE,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, object]:
        catalog = self.catalog(source_id)
        all_items = list(catalog.media_items)
        kind_counts = Counter(str(item["kind"]) for item in all_items)
        group_counts = Counter(
            str(media_group)
            for item in all_items
            for media_group in item["groups"]  # type: ignore[union-attr]
        )
        items = all_items
        if kind:
            items = [item for item in items if item["kind"] == kind]
        if group:
            items = [item for item in items if group in item["groups"]]  # type: ignore[operator]
        if query:
            items = [
                item
                for item in items
                if localized_search_match(query, _media_search_text(item))
            ]
        event_type_counts = Counter(
            str(slot)
            for item in items
            for slot in item["slots"]  # type: ignore[union-attr]
        )
        if event_type:
            items = [item for item in items if event_type in item["slots"]]  # type: ignore[operator]
        if sort == "description_asc":
            items.sort(
                key=lambda item: (
                    item.get("description") is None,
                    str(item.get("description") or "").casefold(),
                    str(item["asset"]["display_name"]).casefold(),  # type: ignore[index]
                )
            )
        else:
            items.sort(
                key=lambda item: str(item["asset"]["display_name"]).casefold(),  # type: ignore[index]
                reverse=sort == "name_desc",
            )
        total = len(items)
        return {
            "items": [
                _localized_media_item(item, language)
                for item in items[offset : offset + limit]
            ],
            "total": total,
            "kinds": [
                {"kind": media_kind, "count": kind_counts.get(media_kind, 0)}
                for media_kind in ("voice", "sound", "unknown")
            ],
            "groups": [
                {"group": media_group, "count": count}
                for media_group, count in sorted(group_counts.items())
            ],
            "event_types": [
                {"event_type": slot, "count": count}
                for slot, count in sorted(event_type_counts.items())
            ],
        }

    def get_entity(
        self,
        source_id: str,
        entity_id: str,
        language: GameLanguage = DEFAULT_GAME_LANGUAGE,
    ) -> dict[str, object]:
        entity = self.catalog(source_id).get(entity_id)
        return {**entity.as_dict(language), "preview": self._preview_info(entity)}

    def asset_associations(
        self,
        source_id: str,
        asset_id: str,
        language: GameLanguage = DEFAULT_GAME_LANGUAGE,
    ) -> dict[str, object]:
        catalog = self.catalog(source_id)
        requested_asset = self.database.get_asset(asset_id)
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
                            "entity": entity.summary(language),
                            "text": None,
                            "original_text": None,
                            "localized_text": None,
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
                            "entity": entity.summary(language),
                            "text": localize_game_text(sample.text, language),
                            "original_text": sample.original_text,
                            "localized_text": localize_game_text(
                                sample.localized_text, language
                            ),
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
                            "text": localize_game_text(sample.text, language),
                            "original_text": sample.original_text,
                            "localized_text": localize_game_text(
                                sample.localized_text, language
                            ),
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
                    media_kind = _media_kind_for_asset(catalog.media_items, sample.asset)
                    append(
                        {
                            "scope": "event",
                            "kind": media_kind,
                            "slot": "sound_event",
                            "event": event,
                            "entity": None,
                            "text": localize_game_text(sample.text, language),
                            "original_text": sample.original_text,
                            "localized_text": localize_game_text(
                                sample.localized_text, language
                            ),
                        },
                        (media_kind, event.casefold(), sample.name.casefold()),
                    )
        requested_name = str(requested_asset["display_name"]).casefold()
        media_item = next(
            (
                item
                for item in catalog.media_items
                if str(item["asset"]["id"]) == asset_id  # type: ignore[index]
            ),
            None,
        )
        if media_item is None:
            media_item = next(
                (
                    item
                    for item in catalog.media_items
                    if str(item["asset"]["display_name"]).casefold()  # type: ignore[index]
                    == requested_name
                ),
                None,
            )
        return {
            "items": items[:100],
            "total": len(items),
            "texts": [
                localize_game_text(str(value), language)
                for value in (media_item or {}).get("texts", [])  # type: ignore[union-attr]
            ],
            "original_texts": [
                str(value)
                for value in (media_item or {}).get("original_texts", [])  # type: ignore[union-attr]
            ],
            "localized_texts": [
                localize_game_text(str(value), language)
                for value in (media_item or {}).get("localized_texts", [])  # type: ignore[union-attr]
            ],
        }

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
                vpl=self.voxel_lighting(source_id),
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
        sequence_frame = _body_sequence_preview_frame(entity, frame, facing)
        source_frame = (
            sequence_frame
            if sequence_frame is not None and sequence_frame < len(sprite.frames)
            else visible_frames[frame % len(visible_frames)]
        )
        return entity, sprite.render(
            source_frame,
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
            vpl=self.voxel_lighting(source_id),
        )

    def voxel_lighting(self, source_id: str) -> VplFile | None:
        candidates = self.database.assets_named(source_id, ("voxels.vpl",))
        if not candidates:
            return None

        def priority(asset: dict[str, Any]) -> tuple[int, int, str]:
            path = str(asset.get("virtual_path") or "").casefold()
            return (
                1 if "ra2md.mix" in path else 0,
                1 if "localmd.mix" in path else 0,
                path,
            )

        return self._parse_asset(max(candidates, key=priority), parse_vpl)

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
        sequence_facings = any(
            sample.animation and sample.animation.facing_step > 0
            for association in entity.media
            if association.slot == "body_sequence"
            for sample in association.samples
        )
        facing_count = (
            8
            if entity.voxel or sequence_facings
            else _positive_int(entity.art.get("facings"), 1)
        )
        base: dict[str, object] = {
            "format": str(body["format"]) if body else None,
            "frame_count": 0 if body is None else 1,
            "facing_count": facing_count,
            "supports_facing": bool(body and (body["format"] == "vxl" or sequence_facings)),
            # Every VXL carries an explicit remap range. Some retail ART sections omit
            # Remapable even though the renderer can apply that range (for example DDBX).
            "supports_player_color": entity.voxel or _yes(entity.art.get("remapable")),
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
        strings, voice_strings = _merge_csf_inputs(
            self.reader,
            csf_assets,
            warnings,
            self.voice_transcripts,
        )
        audio_events = _build_audio_events(sounds, asset_index, voice_strings)
        eva_events = _build_eva_events(eva, asset_index, voice_strings)
        country_definitions = _build_country_definitions(rules, strings)
        country_lookup = {
            country["id"].casefold(): country for country in country_definitions
        }

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
                # A TechnoType's body is selected by the Rules Image key.  An
                # Image value inside that ART section is meaningful to several
                # animation definitions, but retail ARTMD also uses it on
                # concrete units such as BFRT and CAML even though their own
                # BFRT.VXL/CAML.SHP bodies exist.  Following it here therefore
                # replaces those units with SREF/JOSH instead of resolving the
                # body named by the TechnoType.
                image = art_key
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
                body_asset = next(
                    (component.asset for component in components if component.role == "body"),
                    None,
                )
                countries = _references(rule_values.get("owner"))
                sides = tuple(
                    dict.fromkeys(
                        country_lookup.get(country.casefold(), {}).get("side", "")
                        for country in countries
                    )
                )
                entities.append(
                    GameEntity(
                        entity_id,
                        kind,
                        _entity_usage(kind, rule_values),
                        display_name,
                        internal_name,
                        ui_name,
                        localized_name is not None,
                        image,
                        voxel or detected_voxel,
                        countries,
                        tuple(side for side in sides if side),
                        _selected_fields(rule_values, _RULE_FIELDS),
                        _selected_fields(art_values, _ART_FIELDS),
                        components,
                        dependencies,
                        _resolve_media(
                            entity_id,
                            rule_values,
                            art_values,
                            dependencies,
                            art,
                            asset_index,
                            audio_events,
                            voice_strings,
                            body_asset,
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
        media_items = _build_media_items(
            assets,
            tuple(entities),
            audio_events,
            eva_events,
            voice_strings,
        )
        return SemanticCatalog(
            source_id,
            tuple(entities),
            inputs,
            tuple(warnings),
            audio_events,
            eva_events,
            country_definitions,
            media_items,
        )


def _build_country_definitions(
    rules: dict[str, dict[str, str]],
    strings: dict[str, str],
) -> tuple[dict[str, str], ...]:
    countries = []
    for country_id in _type_values(rules.get("countries", {})):
        values = rules.get(country_id.casefold(), {})
        ui_name = values.get("uiname")
        display_name = (
            strings.get(ui_name.casefold(), "") if ui_name else ""
        ) or values.get("name") or country_id
        countries.append(
            {
                "id": country_id,
                "display_name": display_name,
                "side": values.get("side", ""),
            }
        )
    return tuple(countries)


def _build_media_items(
    assets: list[dict[str, Any]],
    entities: tuple[GameEntity, ...],
    audio_events: dict[str, tuple[MediaSample, ...]],
    eva_events: tuple[MediaAssociation, ...],
    voice_strings: dict[str, VoiceText],
) -> tuple[dict[str, object], ...]:
    representatives: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if asset["format"] not in {"bag_audio", "wav", "aud"}:
            continue
        key = str(asset["display_name"]).casefold()
        current = representatives.get(key)
        if current is None or _asset_precedence(asset) > _asset_precedence(current):
            representatives[key] = asset

    states: dict[str, dict[str, Any]] = {
        key: {
            "asset": asset,
            "voice": False,
            "sound": False,
            "groups": set(),
            "texts": set(),
            "original_texts": set(),
            "localized_texts": set(),
            "events": set(),
            "slots": set(),
            "entities": {},
            "countries": set(),
            "sides": set(),
        }
        for key, asset in representatives.items()
    }

    def state_for(sample: MediaSample) -> dict[str, Any] | None:
        if sample.asset is None:
            return None
        return states.get(str(sample.asset["display_name"]).casefold())

    def add_sample(
        sample: MediaSample,
        *,
        kind: str,
        group: str,
        event: str,
        slot: str,
        entity: GameEntity | None = None,
    ) -> None:
        state = state_for(sample)
        if state is None:
            return
        state[kind] = True
        state["groups"].add(group)
        if sample.text:
            state["texts"].add(sample.text.strip())
        if sample.original_text:
            state["original_texts"].add(sample.original_text.strip())
        if sample.localized_text:
            state["localized_texts"].add(sample.localized_text.strip())
        if event:
            state["events"].add(event)
        if slot:
            state["slots"].add(slot)
        if entity is not None:
            state["entities"][entity.id.casefold()] = {
                "id": entity.id,
                "display_name": entity.display_name,
                "kind": entity.kind,
            }
            state["countries"].update(entity.countries)
            state["sides"].update(entity.sides)

    combat_slots = {slot for slot, _ in _WEAPON_SLOTS}
    for entity in entities:
        for association in entity.media:
            if association.kind == "animation":
                continue
            for sample in association.samples:
                is_voice = association.kind == "voice" or sample.text is not None
                if is_voice:
                    add_sample(
                        sample,
                        kind="voice",
                        group="unit_voice",
                        event=association.event,
                        slot=association.slot,
                        entity=entity,
                    )
                else:
                    group = (
                        "combat_sound"
                        if association.slot in combat_slots or association.source != entity.id
                        else "unit_sound"
                    )
                    add_sample(
                        sample,
                        kind="sound",
                        group=group,
                        event=association.event,
                        slot=association.slot,
                        entity=entity,
                    )

    for association in eva_events:
        for sample in association.samples:
            add_sample(
                sample,
                kind="voice",
                group="eva_voice",
                event=association.event,
                slot=association.slot,
            )

    for event, samples in audio_events.items():
        for sample in samples:
            if sample.text:
                add_sample(
                    sample,
                    kind="voice",
                    group="other_voice",
                    event=event,
                    slot="sound_event",
                )
                continue
            folded = f"{event} {sample.name}".casefold()
            if any(token in folded for token in ("ambient", "_amb", "bird", "wind", "water")):
                group = "ambient_sound"
            elif any(
                token in folded
                for token in ("attack", "fire", "expl", "impact", "weapon", "shot", "hit")
            ):
                group = "combat_sound"
            else:
                group = "other_sound"
            add_sample(
                sample,
                kind="sound",
                group=group,
                event=event,
                slot="sound_event",
            )

    for key, value in voice_strings.items():
        for suffix in (".wav", ".aud"):
            state = states.get(f"{key}{suffix}")
            if state is None:
                continue
            state["voice"] = True
            state["texts"].add(value.text.strip())
            if value.original_text:
                state["original_texts"].add(value.original_text.strip())
            if value.localized_text:
                state["localized_texts"].add(value.localized_text.strip())
            stem = key.casefold()
            if not any(group.endswith("_voice") for group in state["groups"]):
                state["groups"].add(
                    "mission_voice"
                    if re.match(r"^[a-z]\d{2}[_-]p\d+", stem)
                    else "other_voice"
                )

    items = []
    for state in states.values():
        kind = "voice" if state["voice"] else "sound" if state["sound"] else "unknown"
        groups = sorted(
            group
            for group in state["groups"]
            if (kind == "voice" and group.endswith("_voice"))
            or (kind == "sound" and group.endswith("_sound"))
        )
        if kind == "voice" and len(groups) > 1 and "other_voice" in groups:
            groups.remove("other_voice")
        if kind == "sound" and len(groups) > 1 and "other_sound" in groups:
            groups.remove("other_sound")
        if kind == "unknown":
            groups = ["unclassified"]
        asset_stem = str(state["asset"]["display_name"]).rsplit(".", 1)[0].casefold()
        mission_match = re.match(r"^([a-z])(\d{2})[_-]p(\d+)", asset_stem)
        if kind == "voice" and mission_match and "unit_voice" not in groups:
            if "other_voice" in groups:
                groups.remove("other_voice")
            if "mission_voice" not in groups:
                groups.append("mission_voice")
                groups.sort()
        texts = sorted(state["texts"], key=str.casefold)
        original_texts = sorted(state["original_texts"], key=str.casefold)
        localized_texts = sorted(state["localized_texts"], key=str.casefold)
        events = sorted(state["events"], key=str.casefold)
        entity_refs = sorted(
            state["entities"].values(),
            key=lambda item: (item["display_name"].casefold(), item["id"].casefold()),
        )
        description = texts[0] if texts else None
        if description is None and mission_match:
            campaign = {
                "a": "盟军",
                "s": "苏军",
                "y": "尤里",
            }.get(mission_match.group(1), "战役")
            description = (
                f"{campaign}任务 {int(mission_match.group(2))}"
                f" · 第 {int(mission_match.group(3))} 段"
            )
        elif description is None and entity_refs:
            description = str(entity_refs[0]["display_name"])
            if events:
                description += f" · {events[0]}"
        elif description is None and "eva_voice" in groups and events:
            description = f"EVA 播报 · {events[0]}"
        elif description is None and events:
            description = events[0]
        items.append(
            {
                "asset": _asset_summary(state["asset"]),
                "kind": kind,
                "groups": groups,
                "texts": texts,
                "original_texts": original_texts,
                "localized_texts": localized_texts,
                "events": events,
                "slots": sorted(state["slots"]),
                "entities": entity_refs,
                "countries": sorted(state["countries"], key=str.casefold),
                "sides": sorted(state["sides"], key=str.casefold),
                "description": description,
            }
        )
    items.sort(
        key=lambda item: str(item["asset"]["display_name"]).casefold()  # type: ignore[index]
    )
    return tuple(items)


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
    voice_transcripts: dict[str, dict[str, str]],
) -> tuple[dict[str, str], dict[str, VoiceText]]:
    strings: dict[str, str] = {}
    voice_strings: dict[str, VoiceText] = {
        key: VoiceText(
            f"TRANSCRIPT:{key}",
            transcript.get("localized_text") or transcript["text"],
            transcript.get("original_text") or transcript["text"],
            transcript.get("localized_text"),
        )
        for key, transcript in voice_transcripts.items()
        if transcript.get("text")
    }
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
                    value = label.values[0]
                    for alias in _voice_aliases(folded[4:], value.extra):
                        current = voice_strings.get(alias)
                        original_text = current.original_text if current else None
                        localized_text = current.localized_text if current else None
                        if parsed.language == 9:
                            localized_text = value.text
                        elif parsed.language == 0:
                            original_text = value.text
                        voice_strings[alias] = VoiceText(
                            label.name,
                            localized_text or original_text or value.text,
                            original_text,
                            localized_text,
                        )
    return strings, voice_strings


def _voice_aliases(label_name: str, extra: str | None) -> tuple[str, ...]:
    aliases = [label_name.casefold()]
    for raw in re.split(r"[,;|\s]+", extra or ""):
        token = raw.strip().strip("\"'").lstrip("$").replace("\\", "/")
        token = token.rsplit("/", 1)[-1]
        if "." in token:
            token = token.rsplit(".", 1)[0]
        if token:
            aliases.append(token.casefold())
    return tuple(dict.fromkeys(aliases))


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
    voice_strings: dict[str, VoiceText],
) -> dict[str, tuple[MediaSample, ...]]:
    events = {}
    for event, values in sections.items():
        sample_names = _tokens(values.get("sounds") or values.get("sound"))
        if sample_names:
            samples: list[MediaSample] = []
            positions: dict[str, int] = {}
            for name in sample_names:
                sample = _audio_sample(name, assets, voice_strings)
                identity = (
                    str(sample.asset["id"])
                    if sample.asset is not None
                    else sample.name.casefold()
                )
                position = positions.get(identity)
                if position is None:
                    positions[identity] = len(samples)
                    samples.append(sample)
                else:
                    current = samples[position]
                    samples[position] = replace(current, weight=current.weight + 1)
            events[event] = tuple(samples)
    return events


def _build_eva_events(
    sections: dict[str, dict[str, str]],
    assets: _AssetIndex,
    voice_strings: dict[str, VoiceText],
) -> tuple[MediaAssociation, ...]:
    associations = []
    for event, values in sections.items():
        fallback_text = values.get("text")
        for faction in ("allied", "soviet", "yuri"):
            for sample_name in _tokens(values.get(faction)):
                sample = _audio_sample(sample_name, assets, voice_strings)
                if sample.text is None and fallback_text:
                    sample = MediaSample(
                        sample.name,
                        fallback_text,
                        sample.asset,
                        fallback_text,
                        None,
                    )
                associations.append(
                    MediaAssociation("voice", f"eva_{faction}", event, "eva", (sample,))
                )
    return tuple(associations)


def _body_sequence_preview_frame(
    entity: GameEntity,
    frame: int,
    facing: int,
) -> int | None:
    sequences = [
        association
        for association in entity.media
        if association.slot == "body_sequence"
        and association.samples
        and association.samples[0].animation is not None
    ]
    if not sequences:
        return None
    preferred_events = ("ready", "guard", "deployed", "hover", "fly", "walk")
    sequence = next(
        (
            association
            for event in preferred_events
            for association in sequences
            if association.event.casefold() == event
        ),
        sequences[0],
    )
    playback = sequence.samples[0].animation
    if playback is None:
        return None
    frame_count = max(1, playback.frame_count or 1)
    facing_offset = (facing % 8) * playback.facing_step if playback.facing_step else 0
    return playback.start_frame + facing_offset + frame % frame_count


def _merge_duplicate_body_sequences(
    associations: list[MediaAssociation],
) -> tuple[MediaAssociation, ...]:
    merged: list[MediaAssociation] = []
    sequence_indices: dict[tuple[object, ...], int] = {}
    for association in associations:
        if (
            association.slot != "body_sequence"
            or len(association.samples) != 1
            or association.samples[0].animation is None
        ):
            merged.append(association)
            continue
        sample = association.samples[0]
        playback = sample.animation
        asset_key = sample.asset["id"] if sample.asset else sample.name.casefold()
        key = (
            association.source.casefold(),
            asset_key,
            playback.start_frame,
            playback.frame_count,
            playback.facing_step,
            playback.rate_ms,
            playback.loop_start,
            playback.loop_end,
            playback.loop_count,
            playback.direction,
        )
        existing_index = sequence_indices.get(key)
        if existing_index is None:
            sequence_indices[key] = len(merged)
            merged.append(association)
            continue
        existing = merged[existing_index]
        aliases = list(existing.aliases)
        known = {existing.event.casefold(), *(alias.casefold() for alias in aliases)}
        for alias in (association.event, *association.aliases):
            if alias.casefold() not in known:
                known.add(alias.casefold())
                aliases.append(alias)
        merged[existing_index] = replace(existing, aliases=tuple(aliases))
    return tuple(merged)


def _resolve_media(
    entity_id: str,
    rules: dict[str, str],
    entity_art: dict[str, str],
    dependencies: tuple[EntityDependency, ...],
    art_sections: dict[str, dict[str, str]],
    assets: _AssetIndex,
    audio_events: dict[str, tuple[MediaSample, ...]],
    voice_strings: dict[str, VoiceText],
    body_asset: dict[str, Any] | None,
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
            animations = tuple(dict.fromkeys(_references(dependency.properties.get("animation"))))
            if animations:
                add(
                    MediaAssociation(
                        "animation",
                        dependency.slot,
                        animations[0],
                        dependency.id,
                        tuple(
                            sample
                            for animation in animations
                            for sample in _animation_samples(
                                animation, art_sections, assets
                            )
                        ),
                        role="weapon",
                    )
                )
        elif dependency.kind == "warhead":
            animations = tuple(
                dict.fromkeys(_references(dependency.properties.get("animation_list")))
            )
            if animations:
                add(
                    MediaAssociation(
                        "animation",
                        dependency.slot,
                        animations[0],
                        dependency.id,
                        tuple(
                            sample
                            for animation in animations
                            for sample in _animation_samples(
                                animation, art_sections, assets
                            )
                        ),
                        role="impact",
                    )
                )

    for field, value in entity_art.items():
        role = _entity_animation_role(field)
        if role is None:
            continue
        for animation in _references(value):
            add(
                MediaAssociation(
                    "animation",
                    field,
                    animation,
                    entity_id,
                    _animation_samples(animation, art_sections, assets),
                    role=role,
                )
            )
    sequence_name = entity_art.get("sequence")
    if sequence_name and body_asset and body_asset.get("format") == "shp":
        for event, value in art_sections.get(sequence_name.casefold(), {}).items():
            playback = _sequence_playback(value)
            if playback is None:
                continue
            add(
                MediaAssociation(
                    "animation",
                    "body_sequence",
                    event,
                    sequence_name,
                    (
                        MediaSample(
                            str(body_asset["display_name"]),
                            None,
                            body_asset,
                            animation=playback,
                        ),
                    ),
                    role="body",
                )
            )
    return _merge_duplicate_body_sequences(associations)


def _audio_sample(
    raw_name: str,
    assets: _AssetIndex,
    voice_strings: dict[str, VoiceText],
) -> MediaSample:
    name = raw_name.strip().lstrip("$")
    stem = name.rsplit(".", 1)[0]
    names = (name,) if "." in name else (f"{name}.wav", f"{name}.aud")
    asset = _find_asset(assets, names, ("bag_audio", "wav", "aud"))
    voice_text = voice_strings.get(stem.casefold())
    return MediaSample(
        name,
        voice_text.text if voice_text else None,
        asset,
        voice_text.original_text if voice_text else None,
        voice_text.localized_text if voice_text else None,
        voice_text.label if voice_text else None,
    )


def _animation_samples(
    reference: str,
    art_sections: dict[str, dict[str, str]],
    assets: _AssetIndex,
) -> tuple[MediaSample, ...]:
    values = art_sections.get(reference.casefold(), {})
    image = values.get("image") or reference
    names = (image,) if "." in image else (f"{image}.shp", f"{image}.hva")
    asset = _find_asset(assets, names, ("shp", "hva", "video"))
    playback = _art_animation_playback(values)
    direction_match = re.search(r"-(NE|SE|SW|NW|N|E|S|W)$", reference, re.IGNORECASE)
    if direction_match:
        playback = replace(
            playback or AnimationPlayback(),
            direction=direction_match.group(1).upper(),
        )
    return (MediaSample(image, None, asset, animation=playback),)


def _entity_animation_role(field: str) -> str | None:
    normalized = field.casefold()
    if normalized == "buildup":
        return "construction"
    if normalized.startswith("anim"):
        return None
    if normalized.endswith("anim") or re.fullmatch(
        r"(?:active|idle|production|special)anim(?:two|three|four)", normalized
    ):
        return "operation"
    return None


def _art_animation_playback(values: dict[str, str]) -> AnimationPlayback | None:
    playback_fields = {"start", "loopstart", "loopend", "loopcount", "rate"}
    if not playback_fields.intersection(values):
        return None
    start = _integer(values.get("start"), 0) or 0
    loop_start = _integer(values.get("loopstart"))
    loop_end = _integer(values.get("loopend"))
    frame_count = loop_end - start if loop_end is not None and loop_end > start else None
    return AnimationPlayback(
        start_frame=max(0, start),
        frame_count=frame_count,
        rate_ms=_integer(values.get("rate")),
        loop_start=loop_start,
        loop_end=loop_end,
        loop_count=_integer(values.get("loopcount")),
    )


def _sequence_playback(value: str) -> AnimationPlayback | None:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) < 3:
        return None
    start = _integer(parts[0])
    frame_count = _integer(parts[1])
    facing_step = _integer(parts[2])
    if start is None or start < 0 or frame_count is None or frame_count <= 0 or facing_step is None:
        return None
    return AnimationPlayback(
        start_frame=start,
        frame_count=frame_count,
        facing_step=max(0, facing_step),
        direction=parts[3] if len(parts) > 3 and parts[3] else None,
    )


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


def _entity_usage(kind: str, values: dict[str, str]) -> str:
    owners = _references(values.get("owner"))
    tech_level = _integer(values.get("techlevel"))
    deployed_construction_yard = kind == "building" and (
        _yes(values.get("constructionyard")) or bool(values.get("undeploysinto"))
    )
    can_build = bool(
        owners
        and values.get("cost")
        and (
            tech_level is not None
            and tech_level >= 0
            or deployed_construction_yard
        )
    )
    if kind == "building":
        if can_build:
            return "buildable"
        if _yes(values.get("needsengineer")) or _yes(values.get("capturable")):
            return "tech"
        if any(
            _yes(values.get(field))
            for field in ("civilian", "insignificant", "nominal")
        ):
            return "civilian"
        return "scenario"
    if kind == "infantry":
        if _yes(values.get("civilian")) or _yes(values.get("nothuman")):
            return "civilian"
        if can_build and _integer(values.get("buildlimit")) == 1:
            return "hero"
        return "buildable" if can_build else "scenario"
    return "buildable" if can_build else "scenario"


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


def _integer(value: str | None, fallback: int | None = None) -> int | None:
    try:
        return int(value or "")
    except ValueError:
        return fallback


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


def _media_search_text(item: dict[str, object]) -> str:
    asset = item["asset"]
    entities = item["entities"]
    return "\n".join(
        (
            str(asset["display_name"]),  # type: ignore[index]
            str(item.get("description") or ""),
            *(str(value) for value in item["texts"]),  # type: ignore[union-attr]
            *(str(value) for value in item["original_texts"]),  # type: ignore[union-attr]
            *(str(value) for value in item["localized_texts"]),  # type: ignore[union-attr]
            *(str(value) for value in item["events"]),  # type: ignore[union-attr]
            *(str(value) for value in item["slots"]),  # type: ignore[union-attr]
            *(str(value) for value in item["countries"]),  # type: ignore[union-attr]
            *(str(value) for value in item["sides"]),  # type: ignore[union-attr]
            *(
                f"{entity['id']} {entity['display_name']}"
                for entity in entities  # type: ignore[union-attr]
            ),
        )
    ).casefold()


def _localized_media_item(
    item: dict[str, object], language: GameLanguage
) -> dict[str, object]:
    entities = item["entities"]
    return {
        **item,
        "description": localize_game_text(
            str(item["description"]) if item.get("description") is not None else None,
            language,
        ),
        "texts": [
            localize_game_text(str(value), language)
            for value in item["texts"]  # type: ignore[union-attr]
        ],
        "localized_texts": [
            localize_game_text(str(value), language)
            for value in item["localized_texts"]  # type: ignore[union-attr]
        ],
        "entities": [
            {
                **entity,
                "display_name": localize_game_text(
                    str(entity["display_name"]), language
                ),
            }
            for entity in entities  # type: ignore[union-attr]
        ],
    }


def _media_kind_for_asset(
    media_items: tuple[dict[str, object], ...],
    asset: dict[str, Any],
) -> str:
    asset_id = str(asset["id"])
    display_name = str(asset["display_name"]).casefold()
    for item in media_items:
        selected = item["asset"]
        if (
            str(selected["id"]) == asset_id  # type: ignore[index]
            or str(selected["display_name"]).casefold() == display_name  # type: ignore[index]
        ):
            return str(item["kind"])
    return "unknown"


__all__ = [
    "ENTITY_KINDS",
    "ENTITY_USAGES",
    "EntityComponent",
    "EntityDependency",
    "GameEntity",
    "MediaAssociation",
    "MediaSample",
    "VoiceText",
    "SemanticCatalog",
    "SemanticLibrary",
]
