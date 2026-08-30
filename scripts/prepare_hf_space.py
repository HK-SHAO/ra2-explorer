from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from ra2_explorer import __version__
from ra2_explorer.errors import Ra2ExplorerError
from ra2_explorer.updates import load_public_update_channel

SPACE_ROOT_ENTRIES = frozenset(
    {".dockerignore", "Dockerfile", "LICENSE", "README.md", "app", "config", "frontend"}
)
DENIED_BUNDLE_SUFFIXES = frozenset(
    {".lock", ".map", ".py", ".pyc", ".spec", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
)


def prepare_space_bundle(
    output: Path,
    *,
    project_root: Path | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    destination = _safe_destination(output, root)
    frontend = root / "frontend" / "dist"
    templates = root / "packaging" / "huggingface-space"
    if not (frontend / "index.html").is_file():
        raise Ra2ExplorerError("前端尚未构建；请先运行 npm run build")
    if not (templates / "Dockerfile").is_file():
        raise Ra2ExplorerError("Hugging Face Space 模板不完整")
    channel = load_public_update_channel(root)
    if channel is None:
        raise Ra2ExplorerError("缺少公开的 Hugging Face 更新通道配置")

    if destination.exists():
        if not overwrite:
            raise Ra2ExplorerError("Space 输出目录已经存在；确认后使用 --overwrite")
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".ra2exp-space-", dir=destination.parent))
    staging = temporary / "bundle"
    try:
        shutil.copytree(templates, staging)
        shutil.copy2(root / "LICENSE", staging / "LICENSE")
        shutil.copytree(frontend, staging / "frontend")
        wheel_root = staging / "app"
        wheel_root.mkdir(parents=True)
        _build_wheel(root, wheel_root)
        config_root = staging / "config"
        config_root.mkdir(parents=True)
        (config_root / "update-channel.json").write_text(
            json.dumps({"schema": 1, **channel}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        audit_space_bundle(staging)
        shutil.move(str(staging), str(destination))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    files, size = _directory_stats(destination)
    return {
        "output": str(destination),
        "version": __version__,
        "files": files,
        "bytes": size,
    }


def audit_space_bundle(bundle: Path) -> None:
    root = bundle.resolve()
    if not root.is_dir():
        raise Ra2ExplorerError("Space 输出目录不存在")
    entries = {path.name for path in root.iterdir()}
    if entries != SPACE_ROOT_ENTRIES:
        unexpected = sorted(entries.symmetric_difference(SPACE_ROOT_ENTRIES))
        raise Ra2ExplorerError(f"Space 输出结构不完整：{', '.join(unexpected[:8])}")
    if not (root / "frontend" / "index.html").is_file():
        raise Ra2ExplorerError("Space 输出缺少前端入口")
    wheels = list((root / "app").glob("ra2_explorer-*.whl"))
    if len(wheels) != 1:
        raise Ra2ExplorerError("Space 输出必须且只能包含一个应用 wheel")
    _audit_wheel(wheels[0])
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.casefold() in DENIED_BUNDLE_SUFFIXES:
            raise Ra2ExplorerError(f"Space 输出包含开发文件：{path.relative_to(root).as_posix()}")

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    required = (
        "COPY app/*.whl",
        "COPY resources/default.ra2pack.parts/",
        "sha256sum -c default.ra2pack.sha256",
        "RA2_EXPLORER_HOSTED=1",
        '"--host", "0.0.0.0", "--port", "7860"',
        "COPY --from=seed",
    )
    if any(value not in dockerfile for value in required):
        raise Ra2ExplorerError("Space Dockerfile 缺少只读运行或派生资源配置")
    readme = (root / "README.md").read_text(encoding="utf-8")
    if any(
        value not in readme
        for value in ("sdk: docker", "app_port: 7860", "license: mit")
    ):
        raise Ra2ExplorerError("Space 元数据不是 Docker/MIT 配置")
    channel = json.loads((root / "config" / "update-channel.json").read_text(encoding="utf-8"))
    if channel.get("schema") != 1 or not channel.get("hf_space_repo"):
        raise Ra2ExplorerError("Space 更新通道配置无效")


def _build_wheel(project_root: Path, wheel_root: Path) -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(project_root),
            "--no-deps",
            "--wheel-dir",
            str(wheel_root),
        ],
        cwd=project_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if process.returncode != 0:
        detail = "\n".join(process.stdout.splitlines()[-10:]).replace(
            str(project_root), "<project>"
        )
        raise Ra2ExplorerError(f"Space wheel 构建失败\n{detail}")


def _audit_wheel(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as error:
        raise Ra2ExplorerError("Space 应用 wheel 无法读取") from error
    if not names or not any(name.startswith("ra2_explorer/") for name in names):
        raise Ra2ExplorerError("Space 应用 wheel 缺少运行模块")
    denied = ("tests/", "docs/", "scripts/", ".github/", ".agents/")
    if any(name.startswith(denied) for name in names):
        raise Ra2ExplorerError("Space 应用 wheel 包含开发目录")


def _safe_destination(output: Path, project_root: Path) -> Path:
    destination = output.expanduser().resolve()
    allowed_root = (project_root / ".outputs").resolve()
    try:
        destination.relative_to(allowed_root)
    except ValueError as error:
        raise Ra2ExplorerError("Space 输出目录必须位于项目 .outputs 中") from error
    if destination == allowed_root:
        raise Ra2ExplorerError("Space 输出目录不能直接使用 .outputs 根目录")
    return destination


def _directory_stats(root: Path) -> tuple[int, int]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 Hugging Face Docker Space 运行包")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".outputs") / "huggingface-space",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        result = prepare_space_bundle(args.output, overwrite=args.overwrite)
    except Ra2ExplorerError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
