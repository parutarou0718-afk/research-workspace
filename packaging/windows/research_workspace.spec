from pathlib import Path
import os


project_root = Path(SPECPATH).parents[1]
icon_path = os.environ.get("RW_PORTABLE_ICON")
if not icon_path or not Path(icon_path).is_file():
    raise SystemExit("RW_PORTABLE_ICON must name the approved PNG or ICO file")

ui_root = project_root / "src" / "research_workspace" / "presentation" / "ui"

a = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (
            str(ui_root),
            "research_workspace/presentation/ui",
        ),
    ],
    hiddenimports=["logging.config"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "comtypes",
        "piplicenses",
        "pytest",
        "pywinauto",
        "tests",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ResearchWorkspace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_path,
    contents_directory="src",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ResearchWorkspace",
)
