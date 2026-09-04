from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from ra2_explorer.derived import DerivedStore
from ra2_explorer.library import AssetReader, SourceLibrary
from ra2_explorer.storage import Database
from ra2_explorer.video import POSTER_SEEK_SECONDS, VideoTranscoder


def _transcoder_with_video(tmp_path: Path):
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
    return transcoder, str(asset["id"]), derived


def _write_frame(path: Path, luma: int) -> None:
    Image.new("L", (4, 4), luma).save(path)


def test_video_transcode_is_on_demand_cached_and_derived(tmp_path: Path, monkeypatch) -> None:
    transcoder, asset_id, derived = _transcoder_with_video(tmp_path)
    source_dir = tmp_path / "game"
    original = (source_dir / "intro.bik").read_bytes()
    calls = []

    monkeypatch.setattr("ra2_explorer.video.shutil.which", lambda _name: "ffmpeg.exe")

    def run(command, **_kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"browser mp4")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("ra2_explorer.video.subprocess.run", run)

    first = transcoder.browser_video(asset_id)
    second = transcoder.browser_video(asset_id)

    assert first == second
    assert first.read_bytes() == b"browser mp4"
    assert first.is_relative_to(derived.root)
    assert (source_dir / "intro.bik").read_bytes() == original
    assert len(calls) == 1
    assert "-nostdin" in calls[0]


def test_video_poster_is_extracted_once_and_cached(tmp_path: Path, monkeypatch) -> None:
    transcoder, asset_id, derived = _transcoder_with_video(tmp_path)
    calls = []

    monkeypatch.setattr("ra2_explorer.video.shutil.which", lambda _name: "ffmpeg.exe")

    def run(command, **_kwargs):
        calls.append(command)
        _write_frame(Path(command[-1]), 200)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("ra2_explorer.video.subprocess.run", run)

    first = transcoder.poster_frame(asset_id)
    second = transcoder.poster_frame(asset_id)

    assert first == second
    assert first.suffix == ".png"
    assert first.is_relative_to(derived.root)
    assert len(calls) == 1
    # Skips the opening fade-in and stops after a single frame.
    assert calls[0][calls[0].index("-ss") + 1] == "1"
    assert calls[0][calls[0].index("-frames:v") + 1] == "1"


def test_video_poster_walks_deeper_past_black_frames(tmp_path: Path, monkeypatch) -> None:
    transcoder, asset_id, _ = _transcoder_with_video(tmp_path)
    calls = []

    monkeypatch.setattr("ra2_explorer.video.shutil.which", lambda _name: "ffmpeg.exe")

    def run(command, **_kwargs):
        calls.append(command)
        _write_frame(Path(command[-1]), 0)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("ra2_explorer.video.subprocess.run", run)

    poster = transcoder.poster_frame(asset_id)

    # Every seek lands on a black frame, so it falls through to the unseeked
    # first frame instead of giving up.
    assert len(calls) == len(POSTER_SEEK_SECONDS) + 1
    assert all("-ss" in call for call in calls[:-1])
    assert "-ss" not in calls[-1]
    assert poster.is_file()


def test_video_poster_survives_clips_shorter_than_the_seeks(
    tmp_path: Path, monkeypatch
) -> None:
    transcoder, asset_id, _ = _transcoder_with_video(tmp_path)
    calls = []

    monkeypatch.setattr("ra2_explorer.video.shutil.which", lambda _name: "ffmpeg.exe")

    def run(command, **_kwargs):
        calls.append(command)
        if "-ss" in command:
            # Seeking past the end of a short clip produces no output.
            return SimpleNamespace(returncode=0, stderr=b"")
        _write_frame(Path(command[-1]), 200)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("ra2_explorer.video.subprocess.run", run)

    poster = transcoder.poster_frame(asset_id)

    assert all("-ss" in call for call in calls[:-1])
    assert "-ss" not in calls[-1]
    assert poster.is_file()


def test_video_poster_reports_failure_when_nothing_is_extracted(
    tmp_path: Path, monkeypatch
) -> None:
    import pytest

    transcoder, asset_id, _ = _transcoder_with_video(tmp_path)
    from ra2_explorer.errors import Ra2ExplorerError

    monkeypatch.setattr("ra2_explorer.video.shutil.which", lambda _name: "ffmpeg.exe")

    def run(command, **_kwargs):
        return SimpleNamespace(returncode=1, stderr=b"boom")

    monkeypatch.setattr("ra2_explorer.video.subprocess.run", run)

    with pytest.raises(Ra2ExplorerError, match="视频封面生成失败"):
        transcoder.poster_frame(asset_id)
