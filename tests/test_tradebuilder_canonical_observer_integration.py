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


def test_tradebuilder_invoked_in_canonical_observer(tmp_path: Path):
    return test_tradebuilder_invoked_with_candidates_in_canonical_observer(tmp_path)


def test_tradebuilder_invoked_with_candidates_in_canonical_observer(tmp_path: Path):
    reset_broker_write_guards()
    arm_broker_write_guards()

    cycle_id = "session_test:1:cycle_001"
    session_id = "session_test"
    candidate = {
        "candidate_id": "c1",
        "strategy_id": "s1",
        "spec_sha": SHA,
        "timestamp": "2026-09-15T09:20:00Z",
        "underlying": "NIFTY",
        "direction": "UP",
        "candidate_type": "INTRADAY",
        "confidence_raw": 0.85,
        "regime": "TRENDING",
        "reason": "breakout",
        "data_cutoff": "2026-09-15T09:19:59Z",
        "execution_status": "advisory_only",
        "ltp": 24500.0,
        "entry": 24500.0,
    }
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[candidate])

    result = run_consumer_cycle(
        runtime_outputs={"ranked_pipeline_latest": pipeline},
        output_root=tmp_path,
        session_id=session_id,
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "symbol": "NIFTY", "spot_ltp": 24500.0},
    )

    # 1. TradeBuilder consumer state recorded in result
    assert "trade_builder" in result["consumers"]
    tb_state = result["consumers"]["trade_builder"]
    assert tb_state["verdict"] == "PASS"

    # 2. Checkpoint pulse written to truth_feed/CHECKPOINT_PULSE.jsonl
    pulse_file = tmp_path / "truth_feed" / "CHECKPOINT_PULSE.jsonl"
    assert pulse_file.exists()
    pulse_lines = [json.loads(line) for line in pulse_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    tb_spans = [span for span in pulse_lines if span["stage_name"] == "TRADE_BUILDER"]
    assert len(tb_spans) >= 1
    assert tb_spans[0]["status"] == "PASS"
    assert tb_spans[0]["parent_span_id"] == f"{cycle_id}:CANDIDATE_POOL"
    assert tb_spans[0]["parent_span_id"] != "CANDIDATE_POOL"
    assert tb_spans[0]["reason_code"] == "CANONICAL_RUNTIME_OBSERVED"
    assert tb_spans[0]["trace_id"] == cycle_id

    # 3. Strictly zero broker write calls
    assert sum(CALL_COUNTS.values()) == 0
    assert result["broker_order_calls"] == 0

    reset_broker_write_guards()


def test_tradebuilder_empty_pool_skips_without_synthetic_defaults(tmp_path: Path):
    reset_broker_write_guards()
    arm_broker_write_guards()

    cycle_id = "session_test:1:cycle_001_empty"
    session_id = "session_test"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id, candidates=[])

    result = run_consumer_cycle(
        runtime_outputs={"ranked_pipeline_latest": pipeline},
        output_root=tmp_path,
        session_id=session_id,
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id},  # No synthetic symbol or price
    )

    # TradeBuilder consumer state handles empty candidates truthfully
    assert "trade_builder" in result["consumers"]
    tb_state = result["consumers"]["trade_builder"]
    assert tb_state["verdict"] == "PASS"
    assert tb_state["reason"] == "NO_ACTIVE_SYMBOLS_OR_CANDIDATES"
    assert tb_state["built_trade_count"] == 0

    # Pulse recorded as SKIPPED_NOT_APPLICABLE
    pulse_file = tmp_path / "truth_feed" / "CHECKPOINT_PULSE.jsonl"
    assert pulse_file.exists()
    pulse_lines = [json.loads(line) for line in pulse_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    tb_spans = [span for span in pulse_lines if span["stage_name"] == "TRADE_BUILDER"]
    assert len(tb_spans) >= 1
    assert tb_spans[0]["status"] == "SKIPPED_NOT_APPLICABLE"
    assert tb_spans[0]["parent_span_id"] == f"{cycle_id}:CANDIDATE_POOL"
    assert tb_spans[0]["parent_span_id"] != "CANDIDATE_POOL"
    assert tb_spans[0]["reason_code"] == "NO_ACTIVE_SYMBOLS_OR_CANDIDATES"

    assert sum(CALL_COUNTS.values()) == 0
    reset_broker_write_guards()


def test_single_candidate_selection_authority_preserved():
    """Verify core.opportunity_engine.select_best_opportunity remains the ONLY selection authority."""
    stages = build_runtime_authority_map()
    selection_authorities = [s for s in stages if s.authority == AuthorityKind.CANDIDATE_SELECTION]
    assert len(selection_authorities) == 1, "Must have exactly 1 candidate selection authority"
    assert selection_authorities[0].owner_module == "core.opportunity_engine"
    assert selection_authorities[0].callable_name == "select_best_opportunity"


def test_consumer_cycle_latest_contains_trade_builder_state(tmp_path: Path):
    cycle_id = "session_test:1:cycle_002"
    pipeline = _ranked_pipeline_fixture(cycle_id=cycle_id)

    run_consumer_cycle(
        runtime_outputs={"ranked_pipeline_latest": pipeline},
        output_root=tmp_path,
        session_id="session_test",
        source_sha=SHA,
        cycle_context={"cycle_id": cycle_id, "symbol": "BANKNIFTY"},
    )

    stored = json.loads((tmp_path / "consumer_cycle_latest.json").read_text(encoding="utf-8"))
    assert "trade_builder" in stored["consumers"]
    assert stored["consumers"]["trade_builder"]["verdict"] == "PASS"
    assert stored["read_only"] is True
    assert stored["broker_write_authority"] is False
    assert stored["order_authority"] is False
