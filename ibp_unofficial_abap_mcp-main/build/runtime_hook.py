"""
PyInstaller runtime hook for sap-ibp-abap-int.

Patches importlib.resources and Path(__file__) resolution so that
bundled data files (CleanABAP.md) are found inside the frozen executable.
"""

import os
import sys

if getattr(sys, "frozen", False):
    # In a PyInstaller bundle, sys._MEIPASS points to the temp extraction dir
    # (onefile) or the application directory (onedir). Set an env var so
    # config.py can use it as a fallback for data-dir resolution.
    os.environ.setdefault("_PYINSTALLER_BASE", sys._MEIPASS)
