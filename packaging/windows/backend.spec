from PyInstaller.utils.hooks import collect_all

datas = [("frontend/backend", "backend")]
binaries = []
hiddenimports = []
for package in ("ortools", "pandas", "numpy", "openpyxl", "reportlab", "uvicorn", "fastapi", "pydantic"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    ["packaging/windows/backend_launcher.py"],
    pathex=["."],
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
