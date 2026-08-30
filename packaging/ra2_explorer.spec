from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH).parent
frontend_root = project_root / "frontend" / "dist"

a = Analysis(
    [str(project_root / "packaging" / "frozen_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(frontend_root), "frontend/dist"),
        (str(project_root / "packaging" / "README.txt"), "."),
        *collect_data_files("opencc"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

launcher = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RA2 Explorer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ra2exp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    launcher,
    cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RA2 Explorer",
)
