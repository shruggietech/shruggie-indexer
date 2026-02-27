# shruggie-indexer-cli.spec
# PyInstaller spec file for the CLI executable.

from pathlib import Path

block_cipher = None
src_dir = Path("src")

a = Analysis(
    [str(src_dir / "shruggie_indexer" / "cli" / "main.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=["shruggie_indexer"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["customtkinter", "tkinter", "_tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="shruggie-indexer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["_uuid.pyd", "api-ms-win-core-file-l2-1-0.dll"],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
