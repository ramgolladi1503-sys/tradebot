"""Tests proving genuine TradeBuilder integration into canonical observer runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.read_only_consumer_cycle import run_consumer_cycle
from core.trade_truth.prospective_capture_engine import (
    CALL_COUNTS,
    arm_broker_write_guards,
    reset_broker_write_guards,
    get_current_git_lineage,
)
from core.runtime_authority_contract import build_runtime_authority_map, AuthorityKind
from strategies.trade_builder import TradeBuilder

SHA, _ = get_current_git_lineage()


def _ranked_pipeline_fixture(
    cycle_id: str = "session_test:1:cycle_001",
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "cycle_provenance": {
            "cycle_id": cycle_id,
            "session_id": "session_test",
            "source_sha": SHA,
            "session_date": "2026-09-15",
        },
        "reports": [
            {
                "candidate_pool": {
                    "regime": {"primary_regime": "TRENDING"},
                    "candidates": list(candidates or []),
                }
            }
        ],
    }


def _market_snapshot_fixture(
    symbols: list[str] | None = None,
    prices: dict[str, float] | None = None,
    timestamp: str | None = "2026-09-15T09:19:59Z",
) -> dict[str, Any]:
    symbols = symbols or ["NIFTY"]
    prices = prices or {"NIFTY": 24500.0}
    symbols_payload = {}
    for symbol in symbols:
        px = prices.get(symbol, 24500.0)
        symbols_payload[symbol] = {
            "spot": px,
            "ltp": px,
            "regime": {"primary_regime": "TRENDING"},
            "feed_health": {"status": "PASS"},
            "quote_truth": {
                "symbol": symbol,
                "ltp": px,
                "last_tick_ts": timestamp,
                "is_fresh": timestamp is not None,
                "source": "TEST_FIXTURE",
            },
        }
    return {
        "generated_at": "2026-09-15T09:19:59.500000Z",
        "market_open": True,
        "symbols": symbols_payload,
    }


def _candidate(symbol: str, *, price: float = 24500.0) -> dict[str, Any]:
    return {
        "candidate_id": f"c_{symbol.lower()}",
        "strategy_id": f"s_{symbol.lower()}",
        "spec_sha": SHA,
        "timestamp": "2026-09-15T09:19:59Z",
        "underlying": symbol,
        "direction": "UP",
        "candidate_type": "INTRADAY",
        "confidence_raw": 0.85,
        "regime": "TRENDING",
        "reason": "breakout",
        "data_cutoff": "2026-09-15T09:19:59Z",
        "execution_status": "advisory_only",
        "ltp": price,
        "entry": price,
    }


def test_tradebuilder_invoked_in_canonical_observer(tmp_path: Path):
    return test_tradebuilder_invoked_with_candidates_in_canonical_observer(tmp_path)


def test_tradebuilder_invoked_with_candidates_in_canonical_observer(tmp_path: Path):
    reset_broker_write_guards()
    arm_broker_write_guards()

    cycle_id = "session_test:1:cycle_001"
    session_id = "session_test"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[_candidate("NIFTY")])
    market_snap = _market_snapshot_fixture(symbols=["NIFTY"], prices={"NIFTY": 24500.0})

    result = run_consumer_cycle(
        runtime_outputs={
            "ranked_pipeline_latest": pipeline,
            "market_snapshot": market_snap,
        },
        output_root=tmp_path,
        session_id=session_id,
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "causal_data_cutoff": "2026-09-15T09:20:00Z"},
    )

    assert "trade_builder" in result["consumers"]
    tb_state = result["consumers"]["trade_builder"]
    assert tb_state["verdict"] == "PASS"
    assert tb_state["runtime_reached"] is True
    assert tb_state["invocation_attempted"] is True

    pulse_file = tmp_path / "truth_feed" / "CHECKPOINT_PULSE.jsonl"
    assert pulse_file.exists()
    pulse_lines = [json.loads(line) for line in pulse_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    cp_spans = [span for span in pulse_lines if span["stage_name"] == "CANDIDATE_POOL"]
    assert len(cp_spans) >= 1
    cp_span = cp_spans[0]
    assert cp_span["status"] == "PASS"
    assert cp_span["span_id"]
    assert cp_span["trace_id"] == cycle_id

    tb_spans = [span for span in pulse_lines if span["stage_name"] == "TRADE_BUILDER"]
    assert len(tb_spans) >= 1
    tb_span = tb_spans[0]
    assert tb_span["status"] == "PASS"
    assert tb_span["parent_span_id"] == cp_span["span_id"]
    assert tb_span["parent_span_id"] != "CANDIDATE_POOL"
    assert tb_span["reason_code"] == "CANONICAL_RUNTIME_OBSERVED"
    assert tb_span["trace_id"] == cycle_id

    assert sum(CALL_COUNTS.values()) == 0
    assert result["broker_order_calls"] == 0

    reset_broker_write_guards()


def test_candidate_price_is_not_tradebuilder_market_truth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cycle_id = "session_test:1:cycle_price_authority"
    pipeline = _ranked_pipeline_fixture(
        cycle_id=cycle_id,
        candidates=[_candidate("NIFTY", price=11111.0)],
    )
    market_snap = _market_snapshot_fixture(symbols=["NIFTY"], prices={"NIFTY": 24500.0})

    captured: list[dict[str, Any]] = []
    original = TradeBuilder.build_with_trace

    def spy(self, market_data, *args, **kwargs):
        captured.append(dict(market_data))
        return original(self, market_data, *args, **kwargs)

    monkeypatch.setattr(TradeBuilder, "build_with_trace", spy)

    result = run_consumer_cycle(
        runtime_outputs={"ranked_pipeline_latest": pipeline, "market_snapshot": market_snap},
        output_root=tmp_path,
        session_id="session_test",
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "causal_data_cutoff": "2026-09-15T09:20:00Z"},
    )

    assert result["consumers"]["trade_builder"]["runtime_reached"] is True
    assert len(captured) == 1
    assert captured[0]["ltp"] == 24500.0
    assert captured[0]["ltp"] != 11111.0
    assert captured[0]["event_timestamp"] == "2026-09-15T09:19:59Z"
    assert captured[0]["feed_truth"]["quote_truth"]["last_tick_ts"] == "2026-09-15T09:19:59Z"


def test_missing_quote_event_timestamp_blocks_tradebuilder(tmp_path: Path):
    cycle_id = "session_test:1:cycle_missing_ts"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[_candidate("NIFTY")])
    market_snap = _market_snapshot_fixture(timestamp=None)

    result = run_consumer_cycle(
        runtime_outputs={"ranked_pipeline_latest": pipeline, "market_snapshot": market_snap},
        output_root=tmp_path,
        session_id="session_test",
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "causal_data_cutoff": "2026-09-15T09:20:00Z"},
    )

    state = result["consumers"]["trade_builder"]
    assert state["verdict"] == "BLOCKED"
    assert state["runtime_reached"] is False
    assert state["result_status"] == "BLOCKED_DATA"
    assert state["reason"].startswith("EVENT_TIMESTAMP_MISSING:NIFTY")


def test_future_quote_event_timestamp_blocks_tradebuilder(tmp_path: Path):
    cycle_id = "session_test:1:cycle_future_ts"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[_candidate("NIFTY")])
    market_snap = _market_snapshot_fixture(timestamp="2026-09-15T09:20:01Z")

    result = run_consumer_cycle(
        runtime_outputs={"ranked_pipeline_latest": pipeline, "market_snapshot": market_snap},
        output_root=tmp_path,
        session_id="session_test",
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "causal_data_cutoff": "2026-09-15T09:20:00Z"},
    )

    state = result["consumers"]["trade_builder"]
    assert state["verdict"] == "BLOCKED"
    assert state["runtime_reached"] is False
    assert state["result_status"] == "BLOCKED_DATA"
    assert state["reason"].startswith("FUTURE_EVENT_TIMESTAMP_LEAK:NIFTY")


def test_invalid_causal_cutoff_blocks_tradebuilder(tmp_path: Path):
    cycle_id = "session_test:1:cycle_bad_cutoff"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[_candidate("NIFTY")])
    market_snap = _market_snapshot_fixture()

    result = run_consumer_cycle(
        runtime_outputs={"ranked_pipeline_latest": pipeline, "market_snapshot": market_snap},
        output_root=tmp_path,
        session_id="session_test",
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "causal_data_cutoff": "not-a-time"},
    )

    state = result["consumers"]["trade_builder"]
    assert state["verdict"] == "BLOCKED"
    assert state["runtime_reached"] is False
    assert state["reason"].startswith("CAUSAL_DATA_CUTOFF_INVALID")


def test_tradebuilder_empty_pool_skips_without_synthetic_defaults(tmp_path: Path):
    reset_broker_write_guards()
    arm_broker_write_guards()

    cycle_id = "session_test:1:cycle_001_empty"
    session_id = "session_test"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[])
    market_snap = _market_snapshot_fixture()

    result = run_consumer_cycle(
        runtime_outputs={
            "ranked_pipeline_latest": pipeline,
            "market_snapshot": market_snap,
        },
        output_root=tmp_path,
        session_id=session_id,
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id},
    )

    assert "trade_builder" in result["consumers"]
    tb_state = result["consumers"]["trade_builder"]
    assert tb_state["verdict"] == "PENDING"
    assert tb_state["reason"] == "NO_ACTIVE_SYMBOLS_OR_CANDIDATES"
    assert tb_state["built_trade_count"] == 0
    assert tb_state["runtime_reached"] is False
    assert tb_state["result_status"] == "NOT_REACHED"

    pulse_file = tmp_path / "truth_feed" / "CHECKPOINT_PULSE.jsonl"
    assert pulse_file.exists()
    pulse_lines = [json.loads(line) for line in pulse_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    cp_spans = [span for span in pulse_lines if span["stage_name"] == "CANDIDATE_POOL"]
    assert len(cp_spans) >= 1
    cp_span = cp_spans[0]

    tb_spans = [span for span in pulse_lines if span["stage_name"] == "TRADE_BUILDER"]
    assert len(tb_spans) >= 1
    assert tb_spans[0]["status"] == "SKIPPED_NOT_APPLICABLE"
    assert tb_spans[0]["parent_span_id"] == cp_span["span_id"]
    assert tb_spans[0]["parent_span_id"] != "CANDIDATE_POOL"
    assert tb_spans[0]["reason_code"] == "NO_ACTIVE_SYMBOLS_OR_CANDIDATES"

    assert sum(CALL_COUNTS.values()) == 0
    reset_broker_write_guards()


def test_single_candidate_selection_authority_preserved():
    stages = build_runtime_authority_map()
    selection_authorities = [s for s in stages if s.authority == AuthorityKind.CANDIDATE_SELECTION]
    assert len(selection_authorities) == 1
    assert selection_authorities[0].owner_module == "core.opportunity_engine"
    assert selection_authorities[0].callable_name == "select_best_opportunity"


def test_consumer_cycle_latest_contains_trade_builder_state(tmp_path: Path):
    cycle_id = "session_test:1:cycle_002"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[_candidate("BANKNIFTY", price=52000.0)])
    market_snap = _market_snapshot_fixture(symbols=["BANKNIFTY"], prices={"BANKNIFTY": 52000.0})

    run_consumer_cycle(
        runtime_outputs={
            "ranked_pipeline_latest": pipeline,
            "market_snapshot": market_snap,
        },
        output_root=tmp_path,
        session_id="session_test",
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "causal_data_cutoff": "2026-09-15T09:20:00Z"},
    )

    stored = json.loads((tmp_path / "consumer_cycle_latest.json").read_text(encoding="utf-8"))
    assert "trade_builder" in stored["consumers"]
    assert stored["consumers"]["trade_builder"]["verdict"] == "PASS"
    assert stored["read_only"] is True
    assert stored["broker_write_authority"] is False
    assert stored["order_authority"] is False
