from __future__ import annotations

import sys

import dashboard.streamlit_app as app


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.autorefresh_calls = []
        self.captions = []
        self.warnings = []

    def autorefresh(self, interval, key=None):
        self.autorefresh_calls.append((interval, key))
        return len(self.autorefresh_calls)

    def caption(self, text):
        self.captions.append(str(text))

    def warning(self, text):
        self.warnings.append(str(text))


def test_deadlock_break_triggers_when_runtime_stale_but_db_ticks_advance(monkeypatch):
    st = _FakeStreamlit()
    monkeypatch.setattr(app, "_feed_runtime_snapshot_age_sec", lambda now_ts: 999.0)
    monkeypatch.setattr(app, "_latest_db_tick_epoch", lambda: 500.0)
    now_ts = 505.0

    should_break = app._should_break_refresh_deadlock(st, now_ts)
    assert should_break is True
    assert float(st.session_state.get("last_seen_db_tick_epoch")) == 500.0

    should_break_again = app._should_break_refresh_deadlock(st, now_ts)
    assert should_break_again is False


def test_deadlock_break_ignores_recent_runtime_snapshot(monkeypatch):
    st = _FakeStreamlit()
    monkeypatch.setattr(app, "_feed_runtime_snapshot_age_sec", lambda now_ts: 2.0)
    monkeypatch.setattr(app, "_latest_db_tick_epoch", lambda: 500.0)
    assert app._should_break_refresh_deadlock(st, 505.0) is False


def test_apply_refresh_loop_policy_schedules_autorefresh_when_enabled(monkeypatch):
    st = _FakeStreamlit()
    st.session_state.update(
        {
            "auto_refresh_enabled": True,
            "trade_refresh_mode": "Market open only",
            "refresh_interval_sec": 2.0,
            "last_refresh_ts": 95.0,
            "ui_feed_status": "ACTIVE",
        }
    )

    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(app.time, "time", lambda: 100.0)
    monkeypatch.setattr(app, "_canonical_market_open", lambda: True)
    monkeypatch.setattr(app, "_should_break_refresh_deadlock", lambda _st, _now: False)

    app._apply_refresh_loop_policy()

    assert st.autorefresh_calls
    assert st.autorefresh_calls[0][0] == 2000
    assert float(st.session_state.get("last_refresh_ts")) == 100.0
    assert any("Last refreshed at:" in msg for msg in st.captions)


def test_apply_refresh_loop_policy_pauses_when_disabled(monkeypatch):
    st = _FakeStreamlit()
    st.session_state.update(
        {
            "auto_refresh_enabled": False,
            "trade_refresh_mode": "Market open only",
            "refresh_interval_sec": 2.0,
            "last_refresh_ts": 95.0,
            "ui_feed_status": "ACTIVE",
        }
    )

    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(app.time, "time", lambda: 100.0)
    monkeypatch.setattr(app, "_canonical_market_open", lambda: True)
    monkeypatch.setattr(app, "_should_break_refresh_deadlock", lambda _st, _now: False)

    app._apply_refresh_loop_policy()

    assert not st.autorefresh_calls
    assert any("Auto-refresh paused" in msg for msg in st.captions)
