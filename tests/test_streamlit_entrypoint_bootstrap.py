from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace


def _load_module():
    # Ensure a clean import so module-level bootstrap logic is deterministic in tests.
    sys.modules.pop("dashboard.streamlit_app", None)
    return importlib.import_module("dashboard.streamlit_app")


def test_bootstrap_runtime_executes_runtime_script(monkeypatch):
    app = _load_module()
    called = {}

    def _fake_run_path(path, run_name=None):
        called["path"] = path
        called["run_name"] = run_name
        return {}

    monkeypatch.setattr(app.runpy, "run_path", _fake_run_path)
    app._bootstrap_runtime()

    assert str(called["path"]).endswith("dashboard/streamlit_app_runtime.py")
    assert called["run_name"] == "__main__"


def test_bootstrap_runtime_renders_fallback_on_failure(monkeypatch):
    app = _load_module()
    events = []

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    fake_st = SimpleNamespace(
        error=lambda msg: events.append(("error", msg)),
        exception=lambda exc: events.append(("exception", str(exc))),
        code=lambda txt: events.append(("code", txt)),
    )

    monkeypatch.setattr(app.runpy, "run_path", _boom)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    app._bootstrap_runtime()

    assert ("error", "Dashboard render failure.") in events
    assert any(kind == "exception" and "boom" in msg for kind, msg in events)
    assert any(kind == "code" and "RuntimeError: boom" in msg for kind, msg in events)


def test_compute_refresh_gate_prefers_local_trade_fragment():
    app = _load_module()
    fake_st = SimpleNamespace(
        session_state={
            "auto_refresh_enabled": True,
            "ui_local_trade_refresh_enabled": True,
            "trade_refresh_mode": "Always refresh (UI only)",
        }
    )

    should_refresh, reason = app._compute_refresh_gate(fake_st)

    assert should_refresh is False
    assert reason == "local_trade_fragment"
