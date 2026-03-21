# shruggie-indexer-cli.spec
# PyInstaller spec file for the CLI executable.

from pathlib import Path

block_cipher = None
src_dir = Path("src")

a = Analysis(
    [str(src_dir / "shruggie_indexer" / "__main__.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "shruggie_indexer",
        "shruggie_indexer._version",
        "shruggie_indexer.app_paths",
        "shruggie_indexer.cli",
        "shruggie_indexer.cli.main",
        "shruggie_indexer.cli.rollback",
        "shruggie_indexer.config",
        "shruggie_indexer.config.defaults",
        "shruggie_indexer.config.loader",
        "shruggie_indexer.config.types",
        "shruggie_indexer.core",
        "shruggie_indexer.core.dedup",
        "shruggie_indexer.core.encoding",
        "shruggie_indexer.core.entry",
        "shruggie_indexer.core.exif",
        "shruggie_indexer.core.hashing",
        "shruggie_indexer.core.lnk_parser",
        "shruggie_indexer.core.paths",
        "shruggie_indexer.core.progress",
        "shruggie_indexer.core.rename",
        "shruggie_indexer.core.rollback",
        "shruggie_indexer.core.serializer",
        "shruggie_indexer.core.sidecar",
        "shruggie_indexer.core.timestamps",
        "shruggie_indexer.core.traversal",
        "shruggie_indexer.core._formatting",
        "shruggie_indexer.exceptions",
        "shruggie_indexer.log_file",
        "shruggie_indexer.models",
        "shruggie_indexer.models.schema",
    ],
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
