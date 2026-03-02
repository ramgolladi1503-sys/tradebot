from __future__ import annotations

import importlib
import sys


def test_dashboard_loaders_imports_without_streamlit():
    sys.modules.pop("streamlit", None)
    importlib.invalidate_caches()
    mod = importlib.import_module("dashboard.loaders")
    assert mod is not None
    assert "streamlit" not in sys.modules

