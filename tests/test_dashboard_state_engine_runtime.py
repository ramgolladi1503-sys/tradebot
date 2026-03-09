from __future__ import annotations

from dashboard.runtime.state_engine import run_state_engine_if_due


def test_state_engine_runs_even_when_ui_autorefresh_disabled():
    session_state = {
        "auto_refresh_enabled": False,
        "state_engine_enabled": True,
        "last_state_engine_ts": 0.0,
    }
    seen = []

    def _run_once(**kwargs):
        seen.append(kwargs)

    ran = run_state_engine_if_due(
        session_state=session_state,
        desk_id="DEFAULT",
        run_once=_run_once,
        refresh_sec=2.0,
        now_fn=lambda: 10.0,
    )

    assert ran is True
    assert seen and seen[0]["desk_id"] == "DEFAULT"
    assert float(session_state["last_state_engine_ts"]) == 10.0


def test_state_engine_respects_explicit_disable_flag():
    session_state = {
        "auto_refresh_enabled": True,
        "state_engine_enabled": False,
        "last_state_engine_ts": 0.0,
    }
    seen = []

    def _run_once(**kwargs):
        seen.append(kwargs)

    ran = run_state_engine_if_due(
        session_state=session_state,
        desk_id="DEFAULT",
        run_once=_run_once,
        refresh_sec=2.0,
        now_fn=lambda: 10.0,
    )

    assert ran is False
    assert seen == []
