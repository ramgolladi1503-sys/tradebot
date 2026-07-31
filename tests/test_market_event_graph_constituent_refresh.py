import json
from types import SimpleNamespace

from core.market_event_graph_constituent_refresh import (
    refresh_market_event_graph_constituent_source,
    reset_market_event_graph_constituent_refresh_state,
)
from core.market_event_graph_runtime_observer import observe_market_event_graph_runtime
from tests.test_market_event_graph_constituent_source import (
    _instrument_rows,
    _manifest,
    _minute_end,
    _reader,
    _tick_fixture,
)


def test_refresh_creates_state_and_completed_rows_without_candidates(tmp_path):
    reset_market_event_graph_constituent_refresh_state()
    manifest = _manifest()
    fixture = _tick_fixture(manifest)
    state_path = tmp_path / "refresh_state.json"
    subscription_calls = []

    result = refresh_market_event_graph_constituent_source(
        symbol="NIFTY",
        as_of_epoch=float(_minute_end(9, 20) + 10),
        metadata={"market_event_graph_live_source_enable": True, "owner": "NIFTY"},
        state_path=state_path,
        instrument_provider=lambda: _instrument_rows(manifest),
        subscription_fn=lambda tokens: subscription_calls.append(list(tokens)) or True,
        tick_reader=_reader(fixture),
    )

    assert result["invoked"] is True
    assert result["status"] == "READY"
    assert result["producer_status"] == "READY"
    assert result["state_created"] is True
    assert result["state_persisted"] is True
    assert result["target_boundary_count"] == 5
    assert result["reader_visible_row_count"] > 0
    assert result["completed_bar_count"] == 5
    assert result["refresh_invocation_count"] == 1
    assert result["subscription_ensure_count"] == 1
    assert result["subscription_mutation_count"] == 1
    assert result["read_only"] is True
    assert result["broker_api_called"] is False
    assert len(subscription_calls) == 1
    assert state_path.is_file()
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["last_target_boundary_count"] == 5


def test_refresh_is_idempotent_within_boundary_and_rechecks_on_reconnect(tmp_path):
    reset_market_event_graph_constituent_refresh_state()
    manifest = _manifest()
    fixture = _tick_fixture(manifest)
    state_path = tmp_path / "idempotent_state.json"
    subscription_calls = []

    kwargs = {
        "symbol": "NIFTY",
        "as_of_epoch": float(_minute_end(9, 20) + 10),
        "metadata": {
            "market_event_graph_live_source_enable": True,
            "owner": "NIFTY",
            "reconnect_generation": 3,
        },
        "state_path": state_path,
        "instrument_provider": lambda: _instrument_rows(manifest),
        "subscription_fn": lambda tokens: subscription_calls.append(list(tokens)) or True,
        "tick_reader": _reader(fixture),
    }

    first = refresh_market_event_graph_constituent_source(**kwargs)
    second = refresh_market_event_graph_constituent_source(**kwargs)
    third_metadata = dict(kwargs["metadata"])
    third_metadata["reconnect_generation"] = 4
    third = refresh_market_event_graph_constituent_source(**{**kwargs, "metadata": third_metadata})

    assert first["status"] == "READY"
    assert second["status"] == "SKIPPED_SAME_BOUNDARY"
    assert second["invoked"] is False
    assert third["invoked"] is True
    assert third["subscription_ensure_count"] == 2
    assert len(subscription_calls) == 2


def test_refresh_failure_emits_explicit_fail_closed_status(tmp_path):
    reset_market_event_graph_constituent_refresh_state()

    result = refresh_market_event_graph_constituent_source(
        symbol="NIFTY",
        as_of_epoch=float(_minute_end(9, 20) + 10),
        metadata={"market_event_graph_live_source_enable": True},
        state_path=tmp_path / "failed_state.json",
        instrument_provider=lambda: (_ for _ in ()).throw(RuntimeError("instrument boom")),
        tick_reader=lambda tokens, boundaries: {},
    )

    assert result["invoked"] is True
    assert result["status"] != "NOT_EVALUATED"
    assert result["producer_status"] == "TOKEN_RESOLUTION_FAILED"
    assert result["read_only"] is True
    assert result["allowed_for_live_execution"] is False


def test_process_level_fast_cycle_refreshes_with_no_candidates(monkeypatch, tmp_path):
    reset_market_event_graph_constituent_refresh_state()
    manifest = _manifest()
    fixture = _tick_fixture(manifest)
    state_path = tmp_path / "process_state.json"

    import core.orchestrator_parts.cycle as cycle

    monkeypatch.setenv("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", "true")
    monkeypatch.setattr(cycle, "FastExecutionCore", _OneCycleCore)
    monkeypatch.setattr(cycle, "FastExecutionEngine", _NoCandidateEngine)
    original_refresh = cycle.refresh_market_event_graph_constituent_source
    refresh_results = []

    def refresh_wrapper(**kwargs):
        kwargs.update(
            {
                "state_path": state_path,
                "instrument_provider": lambda: _instrument_rows(manifest),
                "subscription_fn": lambda tokens: True,
                "tick_reader": _reader(fixture),
            }
        )
        result = original_refresh(**kwargs)
        refresh_results.append(result)
        return result

    monkeypatch.setattr(cycle, "refresh_market_event_graph_constituent_source", refresh_wrapper)

    result = cycle.run_live_monitoring(SimpleNamespace(), time_module=_Clock())

    assert result == "STOP"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(persisted["bars"]) == 5
    assert refresh_results[0]["invoked"] is True
    assert refresh_results[0]["state_created"] is True
    runtime = observe_market_event_graph_runtime(
        refresh_results[0]["producer_metadata"],
        context_ts=float(_minute_end(9, 20) + 10),
    )
    assert runtime["producer_status"] == "READY"
    assert runtime["status"] != "MISSING_SOURCE_BARS"


class _OneCycleCore:
    def __init__(self, orch):
        self.last_cycle_mono = 0.0
        self.last_feed_epoch = 0.0
        self.last_result = None

    def should_run_cycle(self, now_mono):
        return True, float(_minute_end(9, 20) + 10)

    def idle_sleep_sec(self):
        return 0.01


class _NoCandidateEngine:
    def __init__(self, orch):
        pass

    def evaluate(self):
        return SimpleNamespace(action="NOOP")

    def execute(self, decision):
        return "STOP"


class _Clock:
    def __init__(self):
        self._mono = 1.0

    def monotonic(self):
        self._mono += 1.0
        return self._mono

    def sleep(self, seconds):
        self._mono += float(seconds)
