from __future__ import annotations

from fastapi.testclient import TestClient

from ra2_explorer.api import create_app
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
