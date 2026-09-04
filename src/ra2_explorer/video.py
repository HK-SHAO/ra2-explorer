from __future__ import annotations

import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from PIL import Image

from ra2_explorer.derived import DerivedStore
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.library import AssetReader
from ra2_explorer.storage import Database

# Posters skip the opening seconds because these movies fade in from black,
# then walk deeper until something readable shows up. The last attempt has no
# seek at all, so even a clip shorter than every seek still gets a poster.
POSTER_SEEK_SECONDS: tuple[float, ...] = (1, 2, 4, 6, 8)
# A frame where fewer than this share of pixels are brighter than the luma
# floor counts as black and is not worth showing.
POSTER_DARK_LUMA = 16
POSTER_DARK_MAX_RATIO = 0.02


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
            identity=(asset["id"], "poster-v2"),
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
            self._capture_poster(ffmpeg, source_path, output, temporary)
        return output

    def _capture_poster(
        self,
        ffmpeg: str,
        source_path: Path,
        output: Path,
        temporary: Path,
    ) -> None:
        """Seek progressively deeper until the poster is not a black frame."""
        attempts: list[float | None] = [*POSTER_SEEK_SECONDS, None]
        detail = "FFmpeg 未生成输出"
        for seconds in attempts:
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
            if seconds is not None:
                command += ["-ss", f"{seconds:g}"]
            command += ["-i", str(source_path), "-frames:v", "1", str(temporary)]
            ok, attempt_detail = self._extract_frame(command)
            if ok and (seconds is None or not _frame_is_dark(temporary)):
                self.derived.commit_file(output, temporary)
                temporary.unlink(missing_ok=True)
                return
            temporary.unlink(missing_ok=True)
            detail = attempt_detail or detail
        raise Ra2ExplorerError(f"视频封面生成失败：{detail or '未找到可用的画面帧'}")

    def _extract_frame(self, command: list[str]) -> tuple[bool, str]:
        """Extract a single frame without publishing it."""
        try:
            result = subprocess.run(
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return False, "单帧抽取超过 120 秒已停止"
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-600:]
        if result.returncode != 0:
            return False, detail or f"FFmpeg 退出码 {result.returncode}"
        if not Path(command[-1]).is_file():
            # Seeking past the end of a very short clip yields no frame.
            return False, detail or "FFmpeg 未生成输出"
        return True, ""

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


def _frame_is_dark(path: Path) -> bool:
    """Return True when a frame is essentially black, such as a fade-in."""
    try:
        with Image.open(path) as image:
            histogram = image.convert("L").histogram()
    except OSError:
        return True
    total = sum(histogram)
    if not total:
        return True
    return sum(histogram[POSTER_DARK_LUMA:]) / total < POSTER_DARK_MAX_RATIO


__all__ = ["VideoTranscoder"]
