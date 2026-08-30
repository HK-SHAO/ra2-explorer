from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ra2_explorer.api import create_app
from ra2_explorer.cli import main
from ra2_explorer.config import Settings


def test_hosted_mode_is_read_only_and_reports_runtime_mode(tmp_path) -> None:
    runtime = tmp_path / "runtime"
    settings = Settings(
        data_dir=runtime,
        database_path=runtime / "RA2MD-Ext" / "index" / "ra2-explorer.db",
        frontend_dir=tmp_path / "missing-frontend",
        known_names_path=runtime / "reference" / "known_names.txt",
        hosted=True,
    )
    client = TestClient(create_app(settings))

    assert client.get("/api/health").json()["mode"] == "hosted"
    assert client.get("/api/discovery").json() == {
        "candidates": [],
        "checked_locations": [],
        "official_sources": [],
    }
    denied = client.post("/api/sources", json={"path": "C:\\Games\\RA2"})
    assert denied.status_code == 403
    assert denied.json()["detail"] == "在线浏览为只读模式"
    assert client.get("/api/docs").status_code == 404


def test_hosted_cli_can_listen_on_container_interface(tmp_path, monkeypatch) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "index.db",
        frontend_dir=tmp_path / "frontend",
        known_names_path=tmp_path / "known_names.txt",
        hosted=True,
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("ra2_explorer.cli.load_settings", lambda: settings)
    monkeypatch.setattr(
        "ra2_explorer.cli.uvicorn.run",
        lambda app, **options: calls.append({"app": app, **options}),
    )

    assert main(["serve", "--host", "0.0.0.0", "--port", "7860"]) == 0
    assert calls[0]["host"] == "0.0.0.0"
    assert calls[0]["port"] == 7860


def test_local_cli_still_rejects_external_interface(tmp_path, monkeypatch) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "index.db",
        frontend_dir=tmp_path / "frontend",
        known_names_path=tmp_path / "known_names.txt",
    )
    monkeypatch.setattr("ra2_explorer.cli.load_settings", lambda: settings)

    with pytest.raises(SystemExit, match="仅允许监听本机回环地址"):
        main(["serve", "--host", "0.0.0.0", "--port", "7860"])
