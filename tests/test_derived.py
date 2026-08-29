from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ra2_explorer.derived import DerivedStore


def test_atomic_write_is_idempotent_for_existing_artifact(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"first")

    DerivedStore._atomic_write(target, b"second")

    assert target.read_bytes() == b"first"


def test_atomic_write_handles_concurrent_immutable_writers(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"
    payloads = [f"payload-{index}".encode() for index in range(16)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda payload: DerivedStore._atomic_write(target, payload), payloads))

    assert target.read_bytes() in payloads
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_does_not_hide_real_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "artifact.bin"

    def reject_replace(source: Path, destination: Path) -> None:
        del source, destination
        raise PermissionError("read only")

    monkeypatch.setattr(os, "replace", reject_replace)

    with pytest.raises(PermissionError, match="read only"):
        DerivedStore._atomic_write(target, b"payload")

    assert list(tmp_path.glob(".*.tmp")) == []


def test_artifact_path_compacts_long_cache_identity(tmp_path: Path) -> None:
    store = DerivedStore(tmp_path / "RA2MD-Ext")
    path = store.artifact_path(
        "previews",
        source_id="source-id",
        revision="revision",
        identity=("TESLA", *("very-long-effect-identity" for _ in range(12))),
        extension="png",
    )
    different = store.artifact_path(
        "previews",
        source_id="source-id",
        revision="revision",
        identity=("TESLA", *("different-effect-identity" for _ in range(12))),
        extension="png",
    )

    assert len(path.stem) <= 48
    assert path != different
