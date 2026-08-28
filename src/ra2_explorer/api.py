from __future__ import annotations

import io
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
from ra2_explorer.codecs.pal import parse_palette
from ra2_explorer.codecs.shp import parse_shp
from ra2_explorer.config import Settings, load_settings
from ra2_explorer.demo import create_demo_installation
from ra2_explorer.errors import AssetNotFoundError, Ra2ExplorerError
from ra2_explorer.library import AssetReader, SourceLibrary
from ra2_explorer.reference_data import (
    load_known_names,
    reference_status,
    sync_known_names,
)
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
        return {"status": "ok", "version": __version__}

    @app.get("/api/sources")
    def sources() -> list[dict[str, object]]:
        return services.database.list_sources()

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
        else:
            raise HTTPException(status_code=409, detail="该格式没有图像预览")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return Response(
            content=output.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
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
    priority = {
        "unittem.pal": 0,
        "uniturb.pal": 1,
        "unitsno.pal": 2,
        "unitdes.pal": 3,
        "demo.pal": 4,
    }
    palette_asset = min(
        palettes,
        key=lambda item: (
            priority.get(str(item["display_name"]).lower(), 99),
            item["display_name"],
        ),
    )
    _, palette_data = services.reader.read(palette_asset["id"])
    return parse_palette(palette_data)


app = create_app()


__all__ = ["Services", "app", "create_app"]
