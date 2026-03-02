from __future__ import annotations

import importlib
import sys


def test_dashboard_renderers_import_without_state_engine_execution():
    sys.modules.pop("core.trade_state_engine", None)
    sys.modules.pop("dashboard.streamlit_app_runtime", None)
    importlib.invalidate_caches()

    mod = importlib.import_module("dashboard.renderers")

    assert mod is not None
    assert "core.trade_state_engine" not in sys.modules
    assert "dashboard.streamlit_app_runtime" not in sys.modules
