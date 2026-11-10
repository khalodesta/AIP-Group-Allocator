from pathlib import Path

a = Analysis([str(Path(SPECPATH) / "portable_launcher.py")],
             pathex=[SPECPATH], binaries=[], datas=[], hiddenimports=[],
             excludes=["pytest", "numpy", "pandas", "ortools", "tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="allocator-launcher",
          console=True, debug=False, strip=False, upx=False)
