from PyInstaller.utils.hooks import collect_all
from pathlib import Path

repo = Path(SPECPATH).parents[1]
datas = [(str(repo / "frontend" / "backend" / "data"), "backend/data")]
binaries = []
hiddenimports = []
for package in ("ortools", "pandas", "numpy", "openpyxl", "reportlab", "uvicorn", "fastapi", "pydantic"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    [str(Path(SPECPATH) / "backend_launcher.py")],
    pathex=[str(repo), str(repo / "frontend" / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "pypdf", "matplotlib", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="allocator-backend",
    console=True,
    debug=False,
    strip=False,
    upx=False,
)
