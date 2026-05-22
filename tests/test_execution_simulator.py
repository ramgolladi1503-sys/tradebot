from __future__ import annotations

from config import config as cfg
from core.execution_simulator import simulate_execution
from core.sim_outcomes import build_sim_outcome_record


def _candidate(**overrides):
    base = {
        "trade_id": "SIM-1",
        "symbol": "NIFTY",
        "side": "BUY",
        "qty": 1,
        "entry_price": 100.0,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "stop_loss": 95.0,
        "target": 110.0,
        "market_mode": "SIM",
        "strategy_family": "continuation",
        "direction_family": "bullish",
        "candidate_class": "EXECUTABLE",
        "selector_outcome": "EXECUTE_TOP",
        "signal_score": 0.72,
        "execution_score": 0.66,
        "priority_score": 0.69,
        "final_score": 0.69,
        "selection_probability": 0.61,
        "data_state": "DATA_OK",
        "fresh_quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "quote_age_sec": 0.5,
        "best_bid": 99.9,
        "best_ask": 100.1,
        "ltp": 100.0,
        "quote_completeness": "FULL",
        "spread_source": "live_quote",
    }
    base.update(overrides)
    return base


def test_execution_sim_rejects_when_quote_turns_stale(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)

    result = simulate_execution(
        _candidate(),
        market_snapshot={"bid": 99.8, "ask": 100.2, "quote_age_sec": 0.5, "volume": 5000},
        revalidated_snapshot={"bid": 99.9, "ask": 100.3, "quote_age_sec": 3.5, "volume": 5000},
        simulated_delay_sec=2.0,
    )

    assert result.status == "SIM_REJECTED"
    assert result.reason == "stale_at_order_time"


def test_execution_sim_rejects_when_spread_widens_beyond_limit(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_MAX_SPREAD_WIDEN_MULT", 1.5, raising=False)

    result = simulate_execution(
        _candidate(),
        market_snapshot={"bid": 100.0, "ask": 100.5, "quote_age_sec": 0.2, "volume": 5000},
        revalidated_snapshot={"bid": 99.0, "ask": 101.5, "quote_age_sec": 0.4, "volume": 5000},
    )

    assert result.status == "SIM_REJECTED"
    assert result.reason == "spread_widened"


def test_execution_sim_reprices_or_cancels_when_rr_collapses(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_MAX_RR_COLLAPSE_PCT", 0.20, raising=False)

    result = simulate_execution(
        _candidate(),
        market_snapshot={"bid": 99.9, "ask": 100.1, "quote_age_sec": 0.3, "volume": 5000},
        revalidated_snapshot={"bid": 106.8, "ask": 107.0, "quote_age_sec": 0.4, "volume": 5000},
    )

    assert result.status in {"SIM_REPRICED", "SIM_CANCELLED"}
    assert "rr_collapsed" in result.reason


def test_execution_sim_handles_broker_reject_cleanly(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True, raising=False)

    result = simulate_execution(
        _candidate(),
        market_snapshot={"bid": 99.8, "ask": 100.2, "quote_age_sec": 0.1, "volume": 5000},
        broker_behavior="reject",
    )

    assert result.status == "SIM_REJECTED"
    assert result.reason == "broker_reject"
    assert result.broker_status == "REJECTED"


def test_execution_sim_with_seed_is_deterministic(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_RANDOMNESS_ENABLE", True, raising=False)

    first = simulate_execution(
        _candidate(qty=5),
        market_snapshot={"bid": 99.8, "ask": 100.2, "quote_age_sec": 0.1, "volume": 5000, "ask_qty": 6},
        random_seed=17,
    ).to_dict()
    second = simulate_execution(
        _candidate(qty=5),
        market_snapshot={"bid": 99.8, "ask": 100.2, "quote_age_sec": 0.1, "volume": 5000, "ask_qty": 6},
        random_seed=17,
    ).to_dict()

    assert first == second


def test_execution_sim_can_model_partial_fill(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_PARTIAL_FILL_MIN_RATIO", 0.1, raising=False)

    result = simulate_execution(
        _candidate(qty=10, execution_entry=100.3, entry_price=100.3),
        market_snapshot={"bid": 99.8, "ask": 100.2, "quote_age_sec": 0.1, "volume": 5000, "ask_qty": 4},
        allow_partial_fill=True,
    )

    assert result.status == "SIM_PARTIAL_FILL"
    assert result.fill_qty is not None and result.fill_qty < result.requested_qty


def test_execution_sim_jitter_can_change_fill_outcome(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_EXECUTION_SIM_RANDOMNESS_ENABLE", True, raising=False)

    first = simulate_execution(
        _candidate(qty=5),
        market_snapshot={"bid": 99.8, "ask": 100.2, "quote_age_sec": 0.1, "volume": 5000, "ask_qty": 5},
        random_seed=1,
    ).to_dict()
    second = simulate_execution(
        _candidate(qty=5),
        market_snapshot={"bid": 99.8, "ask": 100.2, "quote_age_sec": 0.1, "volume": 5000, "ask_qty": 5},
        random_seed=2,
    ).to_dict()

    assert first != second


def test_build_sim_outcome_record_keeps_expected_shape():
    record = build_sim_outcome_record(
        _candidate(),
        {"status": "FILLED", "fill_status": "FILLED", "fill_price": 100.1},
        timestamp="2026-05-22T00:00:00+05:30",
    )

    assert record["trade_id"] == "SIM-1"
    assert record["simulation_status"] == "FILLED"
    assert record["timestamp"] == "2026-05-22T00:00:00+05:30"
