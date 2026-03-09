from __future__ import annotations

import dashboard.streamlit_app_runtime as runtime


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.captions = []

    def caption(self, text):
        self.captions.append(str(text))


def test_record_tab_render_duration_updates_session_state(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime.time, "perf_counter", lambda: 20.0)
    monkeypatch.setattr(runtime.time, "time", lambda: 1000.0)

    elapsed_ms = runtime._record_tab_render_duration("Home", 19.5)

    assert round(elapsed_ms, 2) == 500.0
    assert fake_st.session_state["tab_render_durations_ms"]["Home"] == 500.0
    assert fake_st.session_state["tab_last_rendered"] == "Home"
    assert fake_st.session_state["tab_last_rendered_ts_epoch"] == 1000.0


def test_render_tab_timing_footer_shows_heavy_tab_state(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["tab_render_durations_ms"] = {
        "Home": 11.2,
        "Risk & Governance": 42.0,
    }
    monkeypatch.setattr(runtime, "st", fake_st)

    runtime._render_tab_timing_footer("Home")

    assert fake_st.captions
    assert "active=Home" in fake_st.captions[-1]
    assert "heavy_tabs_executed=False" in fake_st.captions[-1]
    assert "Home=11.2ms" in fake_st.captions[-1]


def test_render_tab_timing_footer_marks_heavy_tab(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["tab_render_durations_ms"] = {"ML/RL": 88.8}
    monkeypatch.setattr(runtime, "st", fake_st)

    runtime._render_tab_timing_footer("ML/RL")

    assert "heavy_tabs_executed=True" in fake_st.captions[-1]
