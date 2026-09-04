from __future__ import annotations

import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from ra2_explorer.derived import DerivedStore
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.library import AssetReader
from ra2_explorer.storage import Database


class VideoTranscoder:
    """Create browser-compatible video derivatives without touching game files."""

    def __init__(self, database: Database, reader: AssetReader, derived: DerivedStore):
        self.database = database
        self.reader = reader
        self.derived = derived
        self._locks: dict[Path, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def browser_video(self, asset_id: str) -> Path:
        asset = self.database.get_asset(asset_id)
        if asset["format"] != "video":
            raise Ra2ExplorerError("该资产不是可转换的视频")
        source = self.database.get_source(str(asset["source_id"]))
        output = self.derived.artifact_path(
            "video",
            source_id=source["id"],
            revision=source.get("scanned_at") or source["created_at"],
            identity=(asset["id"], "browser-h264-v1"),
            extension="mp4",
        )
        if output.is_file():
            return output
        with self._lock_for(output):
            if output.is_file():
                return output
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                raise Ra2ExplorerError("未找到 FFmpeg，无法把 BIK/VQA 转为浏览器视频")
            _, source_path = self.reader.materialize(asset_id)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp.mp4")
            self._run_ffmpeg(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source_path),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                    "-movflags",
                    "+faststart",
                    str(temporary),
                ],
                output,
                "视频转换失败",
            )
        return output

    def poster_frame(self, asset_id: str) -> Path:
        """Extract one frame so video assets can show a preview before transcoding."""
        asset = self.database.get_asset(asset_id)
        if asset["format"] != "video":
            raise Ra2ExplorerError("该资产不是可转换的视频")
        source = self.database.get_source(str(asset["source_id"]))
        output = self.derived.artifact_path(
            "video",
            source_id=source["id"],
            revision=source.get("scanned_at") or source["created_at"],
            identity=(asset["id"], "poster-v1"),
            extension="png",
        )
        if output.is_file():
            return output
        with self._lock_for(output):
            if output.is_file():
                return output
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                raise Ra2ExplorerError("未找到 FFmpeg，无法生成视频封面")
            _, source_path = self.reader.materialize(asset_id)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp.png")
            # Seek past the fade-in these movies open with, otherwise the
            # poster would be a black frame.
            self._run_ffmpeg(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source_path),
                    "-ss",
                    "1",
                    "-frames:v",
                    "1",
                    str(temporary),
                ],
                output,
                "视频封面生成失败",
            )
        return output

    def _run_ffmpeg(self, command: list[str], output: Path, failure: str) -> None:
        temporary = Path(command[-1])
        try:
            result = subprocess.run(
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=300,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0 or not temporary.is_file():
                detail = result.stderr.decode("utf-8", errors="replace").strip()[-600:]
                raise Ra2ExplorerError(f"{failure}：{detail or 'FFmpeg 未生成输出'}")
            self.derived.commit_file(output, temporary)
        except subprocess.TimeoutExpired as error:
            raise Ra2ExplorerError(f"{failure}：超过 5 分钟已停止") from error
        finally:
            temporary.unlink(missing_ok=True)

    def _lock_for(self, path: Path) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(path, threading.Lock())


__all__ = ["VideoTranscoder"]
