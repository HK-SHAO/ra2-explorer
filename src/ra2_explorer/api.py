from __future__ import annotations

import io
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ra2_explorer import __version__
from ra2_explorer.codecs.csf import parse_csf
from ra2_explorer.codecs.hva import parse_hva
from ra2_explorer.codecs.pal import parse_palette
from ra2_explorer.codecs.shp import parse_shp
from ra2_explorer.codecs.text import decode_legacy_text, parse_ini, text_excerpt
from ra2_explorer.codecs.tmp import parse_tmp
from ra2_explorer.codecs.vxl import parse_vxl
from ra2_explorer.codecs.wav import parse_wav, wav_for_browser
from ra2_explorer.config import Settings, load_settings
from ra2_explorer.demo import create_demo_installation
from ra2_explorer.discovery import discover_installations
from ra2_explorer.errors import AssetNotFoundError, InvalidFormatError, Ra2ExplorerError
from ra2_explorer.library import AssetReader, SourceLibrary
from ra2_explorer.reference_data import (
    load_known_names,
    reference_status,
    sync_known_names,
)
from ra2_explorer.semantic import ENTITY_KINDS, SemanticLibrary
from ra2_explorer.storage import Database


class SourceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=160)


class Services:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings.database_path)
        self.library = SourceLibrary(
            self.database,
            load_known_names(settings.known_names_path),
        )
        self.reader = AssetReader(self.database)
        self.semantic = SemanticLibrary(self.database, self.reader)

    def reload_names(self) -> None:
        self.library = SourceLibrary(
            self.database,
            load_known_names(self.settings.known_names_path),
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or load_settings()
    services = Services(current_settings)
    app = FastAPI(
        title="RA2 Explorer API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.services = services
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(AssetNotFoundError)
    async def handle_not_found(_request: Request, error: AssetNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(Ra2ExplorerError)
    async def handle_domain_error(_request: Request, error: Ra2ExplorerError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "name": "ra2-explorer",
            "version": __version__,
            "pid": os.getpid(),
        }

    @app.get("/api/sources")
    def sources() -> list[dict[str, object]]:
        return services.database.list_sources()

    @app.get("/api/discovery")
    async def discovery() -> dict[str, object]:
        return await run_in_threadpool(discover_installations)

    @app.post("/api/sources", status_code=201)
    async def add_source(payload: SourceRequest) -> dict[str, object]:
        return await run_in_threadpool(
            services.library.import_source,
            Path(payload.path),
            payload.name,
        )

    @app.post("/api/sources/{source_id}/scan")
    async def scan_source(source_id: str) -> dict[str, object]:
        return await run_in_threadpool(services.library.scan, source_id)

    @app.post("/api/demo", status_code=201)
    async def create_demo() -> dict[str, object]:
        target = current_settings.data_dir / "demo-ra2"
        await run_in_threadpool(create_demo_installation, target)
        return await run_in_threadpool(
            services.library.import_source,
            target,
            "RA2 Explorer 演示库",
        )

    @app.get("/api/assets")
    def assets(
        source_id: str | None = None,
        q: str | None = Query(default=None, max_length=200),
        format: str | None = Query(default=None, max_length=24),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        return services.database.list_assets(
            source_id=source_id,
            query=q,
            asset_format=format,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str) -> dict[str, object]:
        return services.database.get_asset(asset_id)

    @app.get("/api/entities")
    def entities(
        source_id: str,
        q: str | None = Query(default=None, max_length=200),
        kind: str | None = Query(default=None),
        renderable: bool | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        if kind is not None and kind not in ENTITY_KINDS:
            raise HTTPException(status_code=422, detail="未知单位类型")
        return services.semantic.list_entities(
            source_id,
            query=q,
            kind=kind,
            renderable=renderable,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/entities/{source_id}/{entity_id}")
    def entity(source_id: str, entity_id: str) -> dict[str, object]:
        return services.semantic.get_entity(source_id, entity_id)

    @app.get("/api/entities/{source_id}/{entity_id}/preview.png")
    def entity_preview(
        source_id: str,
        entity_id: str,
        frame: int = Query(default=0, ge=0),
        palette_id: str | None = None,
        scale: int = Query(default=4, ge=1, le=12),
    ) -> Response:
        semantic_entity = services.semantic.catalog(source_id).get(entity_id)
        body = semantic_entity.component("body")
        if body is None:
            raise HTTPException(status_code=409, detail="该单位没有可渲染的主体资产")
        palette = _select_palette(services, body, palette_id)
        _, image = services.semantic.render(
            source_id,
            entity_id,
            palette=palette,
            frame=frame,
            scale=scale,
        )
        output = io.BytesIO()
        image.save(output, format="PNG")
        return Response(
            content=output.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/assets/{asset_id}/content")
    def asset_content(asset_id: str) -> StreamingResponse:
        asset_record, data = services.reader.read(asset_id)
        safe_name = Path(asset_record["display_name"]).name or "asset.bin"
        disposition = f"attachment; filename*=UTF-8''{quote(safe_name)}"
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/octet-stream",
            headers={"Content-Disposition": disposition},
        )

    @app.get("/api/assets/{asset_id}/shp")
    def shp_metadata(asset_id: str) -> dict[str, object]:
        asset_record, data = services.reader.read(asset_id)
        if asset_record["format"] != "shp":
            raise HTTPException(status_code=409, detail="该资产不是 SHP")
        sprite = parse_shp(data)
        return {
            "width": sprite.width,
            "height": sprite.height,
            "frame_count": len(sprite.frames),
            "frames": [
                {
                    "index": frame.index,
                    "x": frame.x,
                    "y": frame.y,
                    "width": frame.width,
                    "height": frame.height,
                    "compression": frame.compression,
                }
                for frame in sprite.frames
            ],
        }

    @app.get("/api/assets/{asset_id}/metadata")
    def asset_metadata(asset_id: str) -> dict[str, object]:
        asset_record, data = services.reader.read(asset_id)
        return _inspect_asset(asset_record, data)

    @app.get("/api/assets/{asset_id}/text")
    def asset_text(
        asset_id: str,
        q: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=400, ge=1, le=2_000),
    ) -> dict[str, object]:
        asset_record, data = services.reader.read(asset_id)
        asset_format = str(asset_record["format"])
        if asset_format == "csf":
            parsed = parse_csf(data)
            return {
                "format": "csf",
                "version": parsed.version,
                "language": parsed.language,
                "label_count": len(parsed.labels),
                "string_count": parsed.string_count,
                **parsed.excerpt(query=q, limit=limit),
            }
        if asset_format in {"ini", "map"}:
            parsed_ini = parse_ini(data)
            return {
                "format": asset_format,
                "encoding": parsed_ini.encoding,
                "section_count": len(parsed_ini.sections),
                "entry_count": parsed_ini.entry_count,
                **text_excerpt(parsed_ini.text, query=q, limit=limit),
            }
        if asset_format == "text":
            decoded = decode_legacy_text(data)
            return {
                "format": "text",
                "encoding": decoded.encoding,
                **text_excerpt(decoded.text, query=q, limit=limit),
            }
        raise HTTPException(status_code=409, detail="该格式不是可读取的文本资产")

    @app.get("/api/assets/{asset_id}/preview.png")
    def asset_preview(
        asset_id: str,
        frame: int = Query(default=0, ge=0),
        palette_id: str | None = None,
        scale: int = Query(default=4, ge=1, le=16),
    ) -> Response:
        asset_record, data = services.reader.read(asset_id)
        if asset_record["format"] == "pal":
            image = parse_palette(data).preview(cell_size=max(4, scale * 3))
        elif asset_record["format"] == "shp":
            sprite = parse_shp(data)
            if frame >= len(sprite.frames):
                raise HTTPException(status_code=416, detail="帧编号超出范围")
            palette = _select_palette(services, asset_record, palette_id)
            image = sprite.render(frame, palette, scale=scale)
        elif asset_record["format"] == "vxl":
            model = parse_vxl(data)
            if frame >= len(model.limbs):
                raise HTTPException(status_code=416, detail="部件编号超出范围")
            palette = _select_palette(services, asset_record, palette_id)
            image = model.render(frame, palette=palette, scale=scale)
        elif asset_record["format"] == "tmp":
            template = parse_tmp(data)
            if frame >= len(template.tiles):
                raise HTTPException(status_code=416, detail="地块编号超出范围")
            palette = _select_palette(services, asset_record, palette_id)
            image = template.render(frame, palette=palette, scale=scale)
        elif asset_record["format"] == "pcx":
            from PIL import Image, UnidentifiedImageError

            try:
                image = Image.open(io.BytesIO(data))
                image.load()
            except (OSError, UnidentifiedImageError) as error:
                raise InvalidFormatError("PCX 文件无法解码") from error
            if image.width * image.height > 16_777_216:
                raise InvalidFormatError("PCX 图像超过预览安全限制")
            image = image.convert("RGBA")
            if scale > 1:
                image = image.resize(
                    (image.width * scale, image.height * scale),
                    resample=Image.Resampling.NEAREST,
                )
        else:
            raise HTTPException(status_code=409, detail="该格式没有图像预览")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return Response(
            content=output.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/assets/{asset_id}/media")
    def asset_media(asset_id: str) -> Response:
        asset_record, data = services.reader.read(asset_id)
        if asset_record["format"] != "wav":
            raise HTTPException(status_code=409, detail="该格式不能直接在浏览器中播放")
        playable_data, transcoded = wav_for_browser(data)
        headers = {"Cache-Control": "private, max-age=3600"}
        if transcoded:
            headers["X-RA2-Transcoded"] = "ima-adpcm-to-pcm16"
        return Response(
            content=playable_data,
            media_type="audio/wav",
            headers=headers,
        )

    @app.get("/api/palettes")
    def palettes(source_id: str) -> list[dict[str, object]]:
        return services.database.palette_assets(source_id)

    @app.get("/api/stats")
    def stats(source_id: str | None = None) -> dict[str, object]:
        return services.database.stats(source_id)

    @app.get("/api/reference-data")
    def reference_data() -> dict[str, object]:
        return reference_status(current_settings.known_names_path)

    @app.post("/api/reference-data/names/sync")
    async def sync_reference_data() -> dict[str, object]:
        manifest = await run_in_threadpool(sync_known_names, current_settings.known_names_path)
        services.reload_names()
        return manifest

    if current_settings.frontend_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=current_settings.frontend_dir, html=True),
            name="frontend",
        )
    else:

        @app.get("/")
        def root() -> dict[str, str]:
            return {
                "name": "RA2 Explorer API",
                "docs": "/api/docs",
                "message": "frontend/dist 尚未构建",
            }

    return app


def _select_palette(
    services: Services,
    asset: dict[str, object],
    palette_id: str | None,
):
    palettes = services.database.palette_assets(str(asset["source_id"]))
    if palette_id:
        palette_asset = services.database.get_asset(palette_id)
        if (
            palette_asset["source_id"] != asset["source_id"]
            or palette_asset["format"] != "pal"
        ):
            raise HTTPException(status_code=409, detail="调色板不属于当前资源目录")
        _, palette_data = services.reader.read(palette_id)
        return parse_palette(palette_data)
    if not palettes:
        return None
    extension = str(asset.get("extension") or "").lower()
    theater = {
        "tem": "tem",
        "tmp": "tem",
        "urb": "urb",
        "sno": "sno",
        "des": "des",
        "ubn": "ubn",
        "lun": "lun",
    }.get(extension, "tem")
    uses_iso_palette = asset.get("format") == "tmp" or extension in {
        "tem",
        "sno",
        "urb",
        "ubn",
        "lun",
        "des",
    }
    preferred = (
        [f"iso{theater}.pal", "isotem.pal", f"unit{theater}.pal", "unittem.pal"]
        if uses_iso_palette
        else [f"unit{theater}.pal", "unittem.pal", f"iso{theater}.pal", "isotem.pal"]
    )
    preferred.append("demo.pal")
    priority = {name: index for index, name in enumerate(preferred)}
    palette_asset = min(
        palettes,
        key=lambda item: (
            priority.get(str(item["display_name"]).lower(), 99),
            item["display_name"],
        ),
    )
    _, palette_data = services.reader.read(palette_asset["id"])
    return parse_palette(palette_data)


def _inspect_asset(asset: dict[str, object], data: bytes) -> dict[str, object]:
    asset_format = str(asset["format"])
    base: dict[str, object] = {
        "format": asset_format,
        "size": len(data),
    }
    if asset_format == "shp":
        sprite = parse_shp(data)
        return {
            **base,
            "width": sprite.width,
            "height": sprite.height,
            "frame_count": len(sprite.frames),
            "frames": [
                {
                    "index": frame.index,
                    "x": frame.x,
                    "y": frame.y,
                    "width": frame.width,
                    "height": frame.height,
                    "compression": frame.compression,
                }
                for frame in sprite.frames
            ],
        }
    if asset_format == "pal":
        parse_palette(data)
        return {**base, "color_count": 256, "frame_count": 1}
    if asset_format == "vxl":
        model = parse_vxl(data)
        return {
            **base,
            "file_name": model.file_name,
            "palette_count": model.palette_count,
            "remap_range": [model.remap_start, model.remap_end],
            "frame_count": len(model.limbs),
            "limb_count": len(model.limbs),
            "voxel_count": model.voxel_count,
            "limbs": [
                {
                    "index": index,
                    "name": limb.name,
                    "number": limb.number,
                    "size": list(limb.size),
                    "voxel_count": len(limb.voxels),
                    "normals_mode": limb.normals_mode,
                    "scale": limb.scale,
                    "min_bounds": list(limb.min_bounds),
                    "max_bounds": list(limb.max_bounds),
                }
                for index, limb in enumerate(model.limbs)
            ],
        }
    if asset_format == "hva":
        animation = parse_hva(data)
        first_transform = list(animation.transforms[0]) if animation.transforms else []
        return {
            **base,
            "file_name": animation.file_name,
            "frame_count": animation.frame_count,
            "section_count": len(animation.section_names),
            "section_names": list(animation.section_names),
            "first_transform": first_transform,
        }
    if asset_format == "tmp":
        template = parse_tmp(data)
        return {
            **base,
            "width": template.tile_width,
            "height": template.tile_height,
            "template_width": template.template_width,
            "template_height": template.template_height,
            "frame_count": len(template.tiles),
            "tile_count": template.tile_count,
            "tiles": [
                None
                if tile is None
                else {
                    "index": tile.index,
                    "height": tile.height,
                    "terrain_type": tile.terrain_type,
                    "ramp_type": tile.ramp_type,
                    "has_extra": tile.extra_pixels is not None,
                }
                for tile in template.tiles
            ],
        }
    if asset_format == "csf":
        strings = parse_csf(data)
        return {
            **base,
            "version": strings.version,
            "language": strings.language,
            "label_count": len(strings.labels),
            "string_count": strings.string_count,
            "declared_string_count": strings.declared_string_count,
        }
    if asset_format in {"ini", "map"}:
        ini = parse_ini(data)
        return {
            **base,
            "encoding": ini.encoding,
            "section_count": len(ini.sections),
            "entry_count": ini.entry_count,
            "section_names": [section.name for section in ini.sections[:500]],
        }
    if asset_format == "text":
        decoded = decode_legacy_text(data)
        return {
            **base,
            "encoding": decoded.encoding,
            "line_count": len(decoded.text.splitlines()),
        }
    if asset_format == "wav":
        audio = parse_wav(data)
        return {
            **base,
            "audio_format": audio.audio_format,
            "channels": audio.channels,
            "sample_rate": audio.sample_rate,
            "bits_per_sample": audio.bits_per_sample,
            "block_align": audio.block_align,
            "data_size": audio.data_size,
            "samples_per_block": audio.samples_per_block,
            "sample_count": audio.sample_count,
            "duration_seconds": audio.duration_seconds,
            "browser_playable": audio.browser_playable,
            "playback_transcodes_to_pcm": audio.audio_format == 17,
        }
    if asset_format == "pcx":
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                mode = image.mode
        except (OSError, UnidentifiedImageError) as error:
            raise InvalidFormatError("PCX 文件无法解码") from error
        return {**base, "width": width, "height": height, "mode": mode, "frame_count": 1}
    return base


app = create_app()


__all__ = ["Services", "app", "create_app"]
