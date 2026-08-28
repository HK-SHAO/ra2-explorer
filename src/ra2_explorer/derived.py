from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from ra2_explorer.errors import Ra2ExplorerError

DERIVED_SCHEMA_VERSION = 1
_KINDS = {"audio", "extracted", "metadata", "models", "previews"}
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class DerivedStore:
    """Persistent, rebuildable artifacts kept away from the game installation."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.artifacts_root = self.root / "artifacts" / f"v{DERIVED_SCHEMA_VERSION}"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        manifest = self.root / "manifest.json"
        if not manifest.exists():
            self._atomic_write(
                manifest,
                json.dumps(
                    {
                        "schema_version": DERIVED_SCHEMA_VERSION,
                        "kind": "ra2-explorer-derived-workspace",
                        "rebuildable": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            )

    def artifact_path(
        self,
        kind: str,
        *,
        source_id: object,
        revision: object,
        identity: tuple[object, ...],
        extension: str,
    ) -> Path:
        if kind not in _KINDS:
            raise Ra2ExplorerError("未知派生产物类型")
        safe_source = _safe_part(source_id)
        safe_revision = _safe_part(revision)
        safe_identity = "__".join(_safe_part(item) for item in identity)
        safe_extension = _safe_part(extension).lstrip(".") or "bin"
        candidate = (
            self.artifacts_root
            / safe_source
            / safe_revision
            / kind
            / f"{safe_identity}.{safe_extension}"
        ).resolve()
        try:
            candidate.relative_to(self.artifacts_root)
        except ValueError as error:
            raise Ra2ExplorerError("派生产物路径越过工作区") from error
        return candidate

    @staticmethod
    def read_bytes(path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    @staticmethod
    def read_json(path: Path) -> dict[str, Any] | None:
        raw = DerivedStore.read_bytes(path)
        if raw is None:
            return None
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return result if isinstance(result, dict) else None

    def write_bytes(self, path: Path, data: bytes) -> None:
        self._validate_target(path)
        self._atomic_write(path, data)

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        self.write_bytes(
            path,
            json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def _validate_target(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self.artifacts_root)
        except ValueError as error:
            raise Ra2ExplorerError("派生产物只能写入 RA2MD-Ext") from error

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Artifacts are immutable for a source revision.  Returning an existing
        # file avoids needless writes and, importantly, avoids Windows denying
        # a concurrent replacement while another request is reading it.
        if path.is_file():
            return
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            try:
                os.replace(temporary, path)
            except OSError:
                # Two API requests can build the same artifact concurrently.
                # The first completed atomic write wins; the losing writer can
                # safely reuse it because artifact paths include the revision.
                if not path.is_file():
                    raise
        finally:
            temporary.unlink(missing_ok=True)


def _safe_part(value: object) -> str:
    cleaned = _UNSAFE_NAME.sub("-", str(value).strip()).strip(".-")
    return (cleaned or "default")[:96]


__all__ = ["DERIVED_SCHEMA_VERSION", "DerivedStore"]
