from __future__ import annotations

from typing import Any

from ra2_explorer.semantic import SemanticCatalog, SemanticLibrary


class _Database:
    def get_source(self, source_id: str) -> dict[str, Any]:
        return {
            "id": source_id,
            "scanned_at": "2026-08-30T12:00:00Z",
            "asset_count": 1,
            "state": "ready",
        }


def test_cached_catalog_does_not_rewrite_snapshot(monkeypatch) -> None:
    library = SemanticLibrary(_Database(), object())  # type: ignore[arg-type]
    catalog = SemanticCatalog(
        source_id="source",
        entities=(),
        inputs={},
        warnings=(),
        audio_events={},
        eva_events=(),
        countries=(),
        media_items=(),
    )
    library._cache["source"] = (
        (
            "2026-08-30T12:00:00Z",
            1,
            "ready",
            library._voice_transcript_revision,
        ),
        catalog,
    )

    def unexpected_write(*_args: object) -> None:
        raise AssertionError("a memory cache hit must not rewrite the catalog snapshot")

    monkeypatch.setattr(library, "_store_catalog_snapshot", unexpected_write)

    assert library.catalog("source") is catalog
