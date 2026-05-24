from __future__ import annotations

import dashboard.ui as ui


class FakeStreamlit:
    def __init__(self) -> None:
        self.warning_messages: list[str] = []

    def warning(self, message: str) -> None:
        self.warning_messages.append(str(message))


class FreshnessRecorder:
    def __init__(self) -> None:
        self.seen: list[object] = []

    def render(self, st_module):
        self.seen.append(st_module)
        return {"total": 2, "fresh": 2, "warning": 0, "stale": 0, "not_fresh": 0}


def test_app_shell_calls_home_freshness_panel_only_on_home(monkeypatch):
    fake_st = FakeStreamlit()
    recorder = FreshnessRecorder()

    monkeypatch.setattr(ui, "_base_app_shell", lambda title, nav_items, default_tab, on_change=None: "Home")
    monkeypatch.setattr(ui, "_streamlit_module", lambda: fake_st)
    monkeypatch.setattr(ui, "_render_home_freshness_panel", recorder.render)

    nav = ui.app_shell("Axiom Quant Console", ["Home", "Execution"], "Home")

    assert nav == "Home"
    assert recorder.seen == [fake_st]
    assert fake_st.warning_messages == []


def test_app_shell_skips_home_freshness_panel_on_non_home(monkeypatch):
    fake_st = FakeStreamlit()
    recorder = FreshnessRecorder()

    monkeypatch.setattr(ui, "_base_app_shell", lambda title, nav_items, default_tab, on_change=None: "Execution")
    monkeypatch.setattr(ui, "_streamlit_module", lambda: fake_st)
    monkeypatch.setattr(ui, "_render_home_freshness_panel", recorder.render)

    nav = ui.app_shell("Axiom Quant Console", ["Home", "Execution"], "Home")

    assert nav == "Execution"
    assert recorder.seen == []
    assert fake_st.warning_messages == []


def test_app_shell_surfaces_home_freshness_failure_without_breaking_home(monkeypatch):
    fake_st = FakeStreamlit()

    def failing_panel(st_module):
        raise RuntimeError("boom")

    monkeypatch.setattr(ui, "_base_app_shell", lambda title, nav_items, default_tab, on_change=None: "Home")
    monkeypatch.setattr(ui, "_streamlit_module", lambda: fake_st)
    monkeypatch.setattr(ui, "_render_home_freshness_panel", failing_panel)

    nav = ui.app_shell("Axiom Quant Console", ["Home", "Execution"], "Home")

    assert nav == "Home"
    assert fake_st.warning_messages == [
        "Home latest artifact freshness unavailable. Panel error: RuntimeError."
    ]
