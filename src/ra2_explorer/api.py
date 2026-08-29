from __future__ import annotations

import io
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ra2_explorer import __version__
from ra2_explorer.codecs.aud import aud_for_browser, parse_aud
from ra2_explorer.codecs.bag import (
    BagAudioEntry,
    bag_audio_for_browser,
    inspect_bag_audio,
)
from ra2_explorer.codecs.csf import parse_csf
from ra2_explorer.codecs.hva import parse_hva
from ra2_explorer.codecs.map import parse_map
from ra2_explorer.codecs.pal import PLAYER_COLOR_PRESETS, grayscale_palette, parse_palette
from ra2_explorer.codecs.shp import parse_shp
from ra2_explorer.codecs.text import decode_legacy_text, parse_ini, text_excerpt
from ra2_explorer.codecs.tmp import parse_tmp
from ra2_explorer.codecs.vpl import parse_vpl
from ra2_explorer.codecs.vxl import (
    VxlRenderPart,
    build_vxl_scene,
    parse_vxl,
    render_vxl_composite,
)
from ra2_explorer.codecs.wav import parse_wav, wav_for_browser
from ra2_explorer.config import Settings, load_settings
from ra2_explorer.derived import DerivedStore
from ra2_explorer.discovery import discover_installations
from ra2_explorer.errors import AssetNotFoundError, InvalidFormatError, Ra2ExplorerError
from ra2_explorer.library import AssetReader, SourceLibrary
from ra2_explorer.reference_data import (
    load_audio_transcript,
    load_known_names,
    reference_status,
    sync_known_names,
)
from ra2_explorer.semantic import ENTITY_KINDS, ENTITY_USAGES, SemanticLibrary
from ra2_explorer.storage import Database
from ra2_explorer.video import VideoTranscoder

INSPECTABLE_FORMATS = {
    "aud",
    "bag_audio",
    "csf",
    "hva",
    "ini",
    "map",
    "pal",
    "pcx",
    "shp",
    "text",
    "tmp",
    "vxl",
    "vpl",
    "wav",
}


class SourceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=160)


class Services:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings.database_path)
        self.derived = DerivedStore(settings.derived_root)
        self.library = SourceLibrary(
            self.database,
            load_known_names(settings.known_names_path),
            (settings.derived_root,),
        )
        self.reader = AssetReader(self.database, self.derived)
        self.semantic = SemanticLibrary(
            self.database,
            self.reader,
            load_audio_transcript(settings.audio_transcript_path),
        )
        self.video = VideoTranscoder(self.database, self.reader, self.derived)

    def reload_names(self) -> None:
        self.library = SourceLibrary(
            self.database,
            load_known_names(self.settings.known_names_path),
            (self.settings.derived_root,),
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
    app.add_middleware(GZipMiddleware, minimum_size=1_024)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
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

    @app.delete("/api/sources/{source_id}")
    def delete_source(source_id: str) -> dict[str, object]:
        return services.database.delete_source(source_id)

    @app.get("/api/assets")
    def assets(
        source_id: str | None = None,
        q: str | None = Query(default=None, max_length=200),
        format: str | None = Query(default=None, max_length=24),
        formats: str | None = Query(default=None, max_length=240),
        sort: str = Query(default="name_asc", max_length=20),
        limit: int = Query(default=100, ge=1, le=1_000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        selected_formats = tuple(
            item.strip().casefold()
            for item in (formats or "").split(",")
            if item.strip()
        )
        if len(selected_formats) > 20 or any(
            not item.replace("_", "").isalnum() for item in selected_formats
        ):
            raise HTTPException(status_code=422, detail="资源格式筛选无效")
        if sort not in {"name_asc", "name_desc", "size_desc", "size_asc"}:
            raise HTTPException(status_code=422, detail="资源排序方式无效")
        return services.database.list_assets(
            source_id=source_id,
            query=q,
            asset_format=format,
            asset_formats=selected_formats,
            sort_by=sort,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str) -> dict[str, object]:
        return services.database.get_asset(asset_id)

    @app.get("/api/assets/{asset_id}/associations")
    def asset_associations(asset_id: str) -> dict[str, object]:
        asset_record = services.database.get_asset(asset_id)
        return services.semantic.asset_associations(
            str(asset_record["source_id"]), asset_id
        )

    @app.get("/api/entities")
    def entities(
        source_id: str,
        q: str | None = Query(default=None, max_length=200),
        kind: str | None = Query(default=None),
        usage: str | None = Query(default=None, max_length=32),
        side: str | None = Query(default=None, max_length=64),
        renderable: bool | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1_000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        if kind is not None and kind not in ENTITY_KINDS:
            raise HTTPException(status_code=422, detail="未知单位类型")
        if usage is not None and usage not in ENTITY_USAGES:
            raise HTTPException(status_code=422, detail="未知单位分类")
        return services.semantic.list_entities(
            source_id,
            query=q,
            kind=kind,
            usage=usage,
            side=side,
            renderable=renderable,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/media")
    def media(
        source_id: str,
        q: str | None = Query(default=None, max_length=200),
        kind: str | None = Query(default=None),
        group: str | None = Query(default=None, max_length=64),
        event_type: str | None = Query(default=None, max_length=64),
        sort: str = Query(default="name_asc", max_length=24),
        limit: int = Query(default=500, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        if kind is not None and kind not in {"voice", "sound", "unknown"}:
            raise HTTPException(status_code=422, detail="未知音频类型")
        if sort not in {"name_asc", "name_desc", "description_asc"}:
            raise HTTPException(status_code=422, detail="未知音频排序方式")
        return services.semantic.list_media(
            source_id,
            query=q,
            kind=kind,
            group=group,
            event_type=event_type,
            sort=sort,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/semantic/{source_id}/diagnostics")
    def semantic_diagnostics(
        source_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return services.semantic.diagnostics(source_id, limit=limit)

    @app.get("/api/entities/{source_id}/{entity_id}")
    def entity(source_id: str, entity_id: str) -> dict[str, object]:
        return services.semantic.get_entity(source_id, entity_id)

    @app.get("/api/entities/{source_id}/{entity_id}/preview.png")
    def entity_preview(
        source_id: str,
        entity_id: str,
        frame: int = Query(default=0, ge=0),
        facing: int = Query(default=0, ge=0, le=7),
        player_color: str | None = Query(default=None, max_length=24),
        palette_id: str | None = None,
        scale: int = Query(default=4, ge=1, le=12),
    ) -> Response:
        semantic_entity = services.semantic.catalog(source_id).get(entity_id)
        body = semantic_entity.component("body")
        if body is None:
            raise HTTPException(status_code=409, detail="该单位没有可渲染的主体资产")
        palette = _select_palette(services, body, palette_id)
        player_color = _validated_player_color(player_color)
        artifact_path = _source_artifact_path(
            services,
            "previews",
            source_id,
            entity_id,
            "renderer-vpl-v1",
            f"frame-{frame}",
            f"facing-{facing}",
            f"color-{player_color or 'original'}",
            f"palette-{palette_id or 'auto'}",
            f"scale-{scale}",
            extension="png",
        )
        cached = services.derived.read_bytes(artifact_path)
        if cached is not None:
            return Response(
                content=cached,
                media_type="image/png",
                headers={"Cache-Control": "private, max-age=3600"},
            )
        _, image = services.semantic.render(
            source_id,
            entity_id,
            palette=palette,
            frame=frame,
            facing=facing,
            player_color=player_color,
            scale=scale,
        )
        output = io.BytesIO()
        image.save(output, format="PNG")
        rendered = output.getvalue()
        services.derived.write_bytes(artifact_path, rendered)
        return Response(
            content=rendered,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.get("/api/entities/{source_id}/{entity_id}/model.json")
    def entity_model(
        source_id: str,
        entity_id: str,
        frame: int = Query(default=0, ge=0),
        player_color: str | None = Query(default=None, max_length=24),
        palette_id: str | None = None,
    ) -> dict[str, object]:
        semantic_entity = services.semantic.catalog(source_id).get(entity_id)
        body = semantic_entity.component("body")
        if body is None or body["format"] != "vxl":
            raise HTTPException(status_code=409, detail="该单位不是 VXL 模型")
        palette = _select_palette(services, body, palette_id)
        player_color = _validated_player_color(player_color)
        artifact_path = _source_artifact_path(
            services,
            "models",
            source_id,
            entity_id,
            "scene-v4-vpl",
            f"frame-{frame}",
            f"color-{player_color or 'original'}",
            f"palette-{palette_id or 'auto'}",
            extension="json",
        )
        cached = services.derived.read_json(artifact_path)
        if cached is not None:
            return cached
        _, scene = services.semantic.model_scene(
            source_id,
            entity_id,
            palette=palette,
            frame=frame,
            player_color=player_color,
        )
        result = scene.as_dict()
        services.derived.write_json(artifact_path, result)
        return result

    @app.get("/api/assets/{asset_id}/content")
    def asset_content(asset_id: str) -> StreamingResponse:
        asset_record = services.database.get_asset(asset_id)
        safe_name = Path(asset_record["display_name"]).name or "asset.bin"
        media_type = "application/octet-stream"
        if asset_record["format"] == "bag_audio":
            asset_record, data, _ = _browser_audio(services, asset_id)
            media_type = "audio/wav"
        else:
            asset_record, data = services.reader.read(asset_id)
        disposition = f"attachment; filename*=UTF-8''{quote(safe_name)}"
        return StreamingResponse(
            io.BytesIO(data),
            media_type=media_type,
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

    @app.get("/api/assets/{asset_id}/model.json")
    def asset_model(
        asset_id: str,
        frame: int = Query(default=0, ge=0),
        player_color: str | None = Query(default=None, max_length=24),
        palette_id: str | None = None,
    ) -> dict[str, object]:
        asset_record = services.database.get_asset(asset_id)
        if asset_record["format"] not in {"vxl", "hva"}:
            raise HTTPException(status_code=409, detail="该资产不是 VXL/HVA 模型")
        source_id = str(asset_record["source_id"])
        stem = Path(str(asset_record["display_name"])).stem
        related = services.database.assets_named(
            source_id,
            (f"{stem}.vxl", f"{stem}.hva"),
        )
        model_asset = (
            asset_record
            if asset_record["format"] == "vxl"
            else next((item for item in related if item["format"] == "vxl"), None)
        )
        animation_asset = (
            asset_record
            if asset_record["format"] == "hva"
            else next((item for item in related if item["format"] == "hva"), None)
        )
        if model_asset is None:
            raise HTTPException(status_code=409, detail="没有找到与 HVA 同名的 VXL 模型")
        palette = _select_palette(services, model_asset, palette_id)
        player_color = _validated_player_color(player_color)
        artifact_path = _asset_artifact_path(
            services,
            "models",
            asset_record,
            "scene-v4-vpl",
            f"model-{model_asset['id']}",
            f"animation-{animation_asset['id'] if animation_asset else 'none'}",
            f"frame-{frame}",
            f"color-{player_color or 'original'}",
            f"palette-{palette_id or 'auto'}",
            extension="json",
        )
        cached = services.derived.read_json(artifact_path)
        if cached is not None:
            return cached
        _, model_data = services.reader.read(str(model_asset["id"]))
        animation = None
        if animation_asset is not None:
            _, animation_data = services.reader.read(str(animation_asset["id"]))
            animation = parse_hva(animation_data)
        scene = build_vxl_scene(
            (VxlRenderPart(parse_vxl(model_data), animation),),
            palette=palette,
            frame=frame,
            player_color=player_color,
            vpl=services.semantic.voxel_lighting(source_id),
        )
        result = scene.as_dict()
        services.derived.write_json(artifact_path, result)
        return result

    @app.get("/api/assets/{asset_id}/metadata")
    def asset_metadata(asset_id: str) -> dict[str, object]:
        asset_record = services.database.get_asset(asset_id)
        artifact_path = _asset_artifact_path(
            services,
            "metadata",
            asset_record,
            "inspection",
            extension="json",
        )
        cached = services.derived.read_json(artifact_path)
        if cached is not None:
            return cached
        if asset_record["format"] in INSPECTABLE_FORMATS:
            asset_record, data = services.reader.read(asset_id)
            result = _inspect_asset(asset_record, data)
        else:
            result = {
                "format": asset_record["format"],
                "size": asset_record["size"],
            }
        services.derived.write_json(artifact_path, result)
        return result

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
        player_color: str | None = Query(default=None, max_length=24),
        palette_id: str | None = None,
        scale: int = Query(default=4, ge=1, le=16),
    ) -> Response:
        asset_record = services.database.get_asset(asset_id)
        player_color = _validated_player_color(player_color)
        if asset_record["format"] not in {
            "pal",
            "shp",
            "vxl",
            "hva",
            "tmp",
            "pcx",
            "map",
        }:
            raise HTTPException(status_code=409, detail="该格式没有图像预览")
        artifact_path = _asset_artifact_path(
            services,
            "previews",
            asset_record,
            "renderer-vpl-v1",
            f"frame-{frame}",
            f"color-{player_color or 'original'}",
            f"palette-{palette_id or 'auto'}",
            f"scale-{scale}",
            extension="png",
        )
        cached = services.derived.read_bytes(artifact_path)
        if cached is not None:
            return Response(
                content=cached,
                media_type="image/png",
                headers={"Cache-Control": "private, max-age=3600"},
            )
        asset_record, data = services.reader.read(asset_id)
        if asset_record["format"] == "pal":
            image = parse_palette(data).preview(cell_size=max(4, scale * 3))
        elif asset_record["format"] == "shp":
            sprite = parse_shp(data)
            if frame >= len(sprite.frames):
                raise HTTPException(status_code=416, detail="帧编号超出范围")
            palette = _select_palette(services, asset_record, palette_id)
            if player_color:
                palette = (palette or grayscale_palette()).with_player_color(player_color)
            image = sprite.render(frame, palette, scale=scale)
        elif asset_record["format"] == "vxl":
            model = parse_vxl(data)
            if frame >= len(model.limbs):
                raise HTTPException(status_code=416, detail="部件编号超出范围")
            palette = _select_palette(services, asset_record, palette_id)
            image = model.render(
                frame,
                palette=palette,
                player_color=player_color,
                scale=scale,
            )
        elif asset_record["format"] == "hva":
            source_id = str(asset_record["source_id"])
            stem = Path(str(asset_record["display_name"])).stem
            related = services.database.assets_named(source_id, (f"{stem}.vxl",))
            model_asset = next((item for item in related if item["format"] == "vxl"), None)
            if model_asset is None:
                raise HTTPException(status_code=409, detail="没有找到与 HVA 同名的 VXL 模型")
            _, model_data = services.reader.read(str(model_asset["id"]))
            animation = parse_hva(data)
            if frame >= animation.frame_count:
                raise HTTPException(status_code=416, detail="帧编号超出范围")
            palette = _select_palette(services, model_asset, palette_id)
            image = render_vxl_composite(
                (VxlRenderPart(parse_vxl(model_data), animation),),
                palette=palette,
                frame=frame,
                player_color=player_color,
                vpl=services.semantic.voxel_lighting(source_id),
                scale=scale,
            )
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
        elif asset_record["format"] == "map":
            image = parse_map(data).render(scale=scale)
        else:
            raise HTTPException(status_code=409, detail="该格式没有图像预览")
        output = io.BytesIO()
        image.save(output, format="PNG")
        rendered = output.getvalue()
        services.derived.write_bytes(artifact_path, rendered)
        return Response(
            content=rendered,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.get("/api/assets/{asset_id}/media")
    def asset_media(asset_id: str) -> Response:
        _, playable_data, transcoded = _browser_audio(services, asset_id)
        headers = {"Cache-Control": "private, max-age=3600"}
        if transcoded:
            headers["X-RA2-Transcoded"] = "source-audio-to-pcm"
        return Response(
            content=playable_data,
            media_type="audio/wav",
            headers=headers,
        )

    @app.get("/api/assets/{asset_id}/video.mp4")
    def asset_video(asset_id: str) -> FileResponse:
        path = services.video.browser_video(asset_id)
        return FileResponse(
            path,
            media_type="video/mp4",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @app.get("/api/palettes")
    def palettes(source_id: str) -> list[dict[str, object]]:
        return services.database.palette_assets(source_id)

    @app.get("/api/player-colors")
    def player_colors() -> list[dict[str, object]]:
        return [
            {
                "id": name,
                "rgb": list(color),
                "hex": "#" + "".join(f"{component:02x}" for component in color),
            }
            for name, color in PLAYER_COLOR_PRESETS.items()
        ]

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


def _validated_player_color(player_color: str | None) -> str | None:
    if player_color is None:
        return None
    normalized = player_color.casefold()
    if normalized not in PLAYER_COLOR_PRESETS:
        raise HTTPException(status_code=422, detail="未知阵营颜色")
    return normalized


def _bag_entry_from_asset(asset: dict[str, object]) -> BagAudioEntry:
    channels = int(asset["channels"])
    codec = str(asset["codec"])
    flags = 0x04 | (0x01 if channels == 2 else 0)
    flags |= 0x02 if codec == "pcm16" else 0x08
    return BagAudioEntry(
        name=Path(str(asset["display_name"])).stem,
        offset=int(asset["data_offset"]),
        size=int(asset["data_size"]),
        sample_rate=int(asset["sample_rate"]),
        flags=flags,
        block_align=int(asset["block_align"]),
    )


def _asset_artifact_path(
    services: Services,
    kind: str,
    asset: dict[str, object],
    *identity: object,
    extension: str,
) -> Path:
    source = services.database.get_source(str(asset["source_id"]))
    return services.derived.artifact_path(
        kind,
        source_id=source["id"],
        revision=source.get("scanned_at") or source["created_at"],
        identity=(asset["id"], *identity),
        extension=extension,
    )


def _source_artifact_path(
    services: Services,
    kind: str,
    source_id: str,
    *identity: object,
    extension: str,
) -> Path:
    source = services.database.get_source(source_id)
    return services.derived.artifact_path(
        kind,
        source_id=source["id"],
        revision=source.get("scanned_at") or source["created_at"],
        identity=identity,
        extension=extension,
    )


def _browser_audio(
    services: Services,
    asset_id: str,
) -> tuple[dict[str, object], bytes, bool]:
    asset = services.database.get_asset(asset_id)
    if asset["format"] == "bag_audio":
        asset = {**asset, **services.database.get_asset_segment(asset_id)}
    if asset["format"] not in {"wav", "aud", "bag_audio"}:
        raise HTTPException(status_code=409, detail="该格式不能直接在浏览器中播放")
    path = _asset_artifact_path(services, "audio", asset, "browser-pcm", extension="wav")
    cached = services.derived.read_bytes(path)
    transcoded = asset["format"] == "aud" or (
        asset["format"] == "bag_audio" and str(asset["codec"]) == "ima_adpcm"
    )
    if cached is not None:
        return asset, cached, transcoded
    _, data = services.reader.read(asset_id)
    if asset["format"] == "wav":
        playable_data, transcoded = wav_for_browser(data)
    elif asset["format"] == "aud":
        playable_data = aud_for_browser(data)
    else:
        playable_data = bag_audio_for_browser(data, _bag_entry_from_asset(asset))
    services.derived.write_bytes(path, playable_data)
    return asset, playable_data, transcoded


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
    }.get(extension)
    virtual_path = str(asset.get("virtual_path") or "").casefold()
    if theater is None:
        theater = next(
            (
                code
                for marker, code in (
                    ("snow.mix", "sno"),
                    ("urbann.mix", "ubn"),
                    ("urban.mix", "urb"),
                    ("lunar.mix", "lun"),
                    ("desert.mix", "des"),
                    ("temperat.mix", "tem"),
                )
                if marker in virtual_path
            ),
            "tem",
        )
    uses_iso_palette = asset.get("format") == "tmp"
    preferred = (
        [f"iso{theater}.pal", "isotem.pal", f"unit{theater}.pal", "unittem.pal"]
        if uses_iso_palette
        else [f"unit{theater}.pal", "unittem.pal", f"iso{theater}.pal", "isotem.pal"]
    )
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
    if asset_format == "vpl":
        lighting = parse_vpl(data)
        return {
            **base,
            "remap_start": lighting.remap_start,
            "remap_end": lighting.remap_end,
            "section_count": lighting.section_count,
            "lookup_entries": lighting.section_count * 256,
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
    if asset_format == "map":
        overview = parse_map(data)
        return {
            **base,
            "encoding": overview.ini.encoding,
            "section_count": len(overview.ini.sections),
            "entry_count": overview.ini.entry_count,
            "width": overview.width,
            "height": overview.height,
            "theater": overview.theater,
            "object_counts": overview.counts,
        }
    if asset_format == "ini":
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
    if asset_format == "aud":
        audio = parse_aud(data)
        return {
            **base,
            "audio_format": audio.compression,
            "audio_codec": audio.codec,
            "channels": audio.channels,
            "sample_rate": audio.sample_rate,
            "bits_per_sample": audio.bits_per_sample,
            "data_size": audio.data_size,
            "sample_count": audio.sample_count,
            "duration_seconds": audio.duration_seconds,
            "chunk_count": audio.chunk_count,
            "browser_playable": True,
            "playback_transcodes_to_pcm": True,
        }
    if asset_format == "bag_audio":
        return {
            **base,
            **inspect_bag_audio(data, _bag_entry_from_asset(asset)),
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
