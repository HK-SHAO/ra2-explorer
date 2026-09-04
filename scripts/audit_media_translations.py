from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.audit_unit_voice_translations import (
        _request_json,
        missing_translations_for_original,
        translation_format_violations,
    )
except ModuleNotFoundError:  # Direct script execution adds scripts/, not the repo root.
    from audit_unit_voice_translations import (  # type: ignore[no-redef]
        _request_json,
        missing_translations_for_original,
        translation_format_violations,
    )


def _text_values(item: dict[str, Any], field: str) -> list[str]:
    values = item.get(field)
    if not isinstance(values, list):
        return []
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )


def build_media_translation_audit(
    items: list[dict[str, Any]], source_id: str
) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    groups: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    for index, item in enumerate(items):
        asset = item.get("asset") if isinstance(item.get("asset"), dict) else {}
        asset_id = str(asset.get("id") or "")
        display_name = str(asset.get("display_name") or "")
        key = asset_id or f"{display_name}:{index}"
        item_groups = [
            value
            for value in item.get("groups", [])
            if isinstance(value, str) and value
        ]
        kind = str(item.get("kind") or "unknown")
        kinds[kind] += 1
        groups.update(item_groups or ["<none>"])
        entries[key] = {
            "asset_id": asset_id,
            "asset": display_name,
            "stem": Path(display_name).stem.casefold(),
            "kind": kind,
            "groups": item_groups,
            "events": [
                value
                for value in item.get("events", [])
                if isinstance(value, str) and value
            ],
            "original_texts": _text_values(item, "original_texts"),
            "localized_texts": _text_values(item, "localized_texts"),
            "translated_texts": _text_values(item, "translated_texts"),
        }

    missing = missing_translations_for_original(entries)
    format_violations = translation_format_violations(entries)
    return {
        "schema": 1,
        "scope": "all-media",
        "source_id": source_id,
        "summary": {
            "media_asset_count": len(entries),
            "with_original_text": sum(
                bool(entry["original_texts"]) for entry in entries.values()
            ),
            "with_game_localization": sum(
                bool(entry["localized_texts"]) for entry in entries.values()
            ),
            "with_editorial_translation": sum(
                bool(entry["translated_texts"]) for entry in entries.values()
            ),
            "missing_translation_for_original": len(missing),
            "translation_format_violation_count": len(format_violations),
            "by_kind": dict(sorted(kinds.items())),
            "by_group": dict(sorted(groups.items())),
        },
        "missing_translation_for_original": missing,
        "translation_format_violations": format_violations,
        "entries": entries,
    }


def collect_media_translation_inventory(base_url: str, source_id: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    total = 1
    while len(items) < total:
        page = _request_json(
            base_url,
            "/api/media",
            {"source_id": source_id, "limit": "500", "offset": str(len(items))},
        )
        total = int(page.get("total") or 0)
        page_items = page.get("items")
        if not isinstance(page_items, list) or not page_items:
            break
        items.extend(item for item in page_items if isinstance(item, dict))
    return build_media_translation_audit(items, source_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit editorial translation coverage for all indexed audio media."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:46120")
    parser.add_argument("--source-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-format-issues", action="store_true")
    parser.add_argument(
        "--fail-on-missing-original-translations", action="store_true"
    )
    args = parser.parse_args()

    source_id = args.source_id
    if not source_id:
        sources = _request_json(args.base_url, "/api/sources")
        ready_sources = [source for source in sources if source["state"] == "ready"]
        if len(ready_sources) != 1:
            raise SystemExit(
                "Pass --source-id when the service has zero or multiple ready sources."
            )
        source_id = ready_sources[0]["id"]

    payload = collect_media_translation_inventory(args.base_url, source_id)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if args.fail_on_format_issues and payload["translation_format_violations"]:
        raise SystemExit(1)
    if (
        args.fail_on_missing_original_translations
        and payload["missing_translation_for_original"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
