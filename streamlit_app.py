"""Streamlit Community Cloud entrypoint.

The application package lives in ``psy-legis-monitor``. Community Cloud runs
from the repository root, so this wrapper adds the package directory to
``sys.path`` and executes the real Streamlit app.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent / "psy-legis-monitor"
APP_ENTRYPOINT = APP_ROOT / "app" / "ui" / "streamlit_app.py"

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

runpy.run_path(str(APP_ENTRYPOINT), run_name="__main__")
