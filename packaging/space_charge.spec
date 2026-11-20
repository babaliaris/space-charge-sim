# PyInstaller recipe of the GUI.  Build from the repository root:
#     pyinstaller packaging/space_charge.spec --noconfirm
# Output: dist/SpaceChargeSimulator/ (a folder with the executable and its libraries).
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "app", "icon.png"), "app"), (os.path.join(ROOT, "LICENSE"), ".")],
    hiddenimports=["matplotlib.backends.backend_qtagg"],
    excludes=["tkinter", "_tkinter", "matplotlib.backends._backend_tk", "IPython", "pytest", "sphinx",
              "PyQt5.QtWebEngine", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets", "PyQt5.QtQml",
              "PyQt5.QtQuick", "PyQt5.QtMultimedia", "PyQt5.QtBluetooth", "PyQt5.QtSql", "PyQt5.QtNetwork",
              "PyQt5.QtDesigner", "PyQt5.QtTest", "PyQt5.Qt3DCore", "PyQt5.QtLocation", "PyQt5.QtPositioning"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SpaceChargeSimulator",
    console=False,                       # no terminal window
    icon=os.path.join(SPECPATH, "icon.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SpaceChargeSimulator", upx=False)
