from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ra2_explorer.derived import DerivedStore
from ra2_explorer.library import AssetReader, SourceLibrary
from ra2_explorer.storage import Database
from ra2_explorer.video import VideoTranscoder


def test_video_transcode_is_on_demand_cached_and_derived(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "game"
    source_dir.mkdir()
    original = b"BIK synthetic test payload"
    (source_dir / "intro.bik").write_bytes(original)
    database = Database(tmp_path / "index.db")
    source = SourceLibrary(database, ()).import_source(source_dir)
    asset = database.list_assets(
        source_id=str(source["id"]),
        asset_format="video",
    )["items"][0]
    derived = DerivedStore(tmp_path / "RA2MD-Ext")
    reader = AssetReader(database, derived)
    transcoder = VideoTranscoder(database, reader, derived)
    calls = []

    monkeypatch.setattr("ra2_explorer.video.shutil.which", lambda _name: "ffmpeg.exe")

    def run(command, **_kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"browser mp4")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("ra2_explorer.video.subprocess.run", run)

    first = transcoder.browser_video(str(asset["id"]))
    second = transcoder.browser_video(str(asset["id"]))

    assert first == second
    assert first.read_bytes() == b"browser mp4"
    assert first.is_relative_to(derived.root)
    assert (source_dir / "intro.bik").read_bytes() == original
    assert len(calls) == 1
    assert "-nostdin" in calls[0]


def test_video_poster_is_extracted_once_and_cached(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "game"
    source_dir.mkdir()
    (source_dir / "intro.bik").write_bytes(b"BIK synthetic test payload")
    database = Database(tmp_path / "index.db")
    source = SourceLibrary(database, ()).import_source(source_dir)
    asset = database.list_assets(
        source_id=str(source["id"]),
        asset_format="video",
    )["items"][0]
    derived = DerivedStore(tmp_path / "RA2MD-Ext")
    reader = AssetReader(database, derived)
    transcoder = VideoTranscoder(database, reader, derived)
    calls = []

    monkeypatch.setattr("ra2_explorer.video.shutil.which", lambda _name: "ffmpeg.exe")

    def run(command, **_kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"poster png")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("ra2_explorer.video.subprocess.run", run)

    first = transcoder.poster_frame(str(asset["id"]))
    second = transcoder.poster_frame(str(asset["id"]))

    assert first == second
    assert first.suffix == ".png"
    assert first.read_bytes() == b"poster png"
    assert first.is_relative_to(derived.root)
    assert len(calls) == 1
    # Skips the opening fade-in and stops after a single frame.
    assert calls[0][calls[0].index("-ss") + 1] == "1"
    assert calls[0][calls[0].index("-frames:v") + 1] == "1"
