import importlib
import json
import logging
from unittest.mock import Mock

from config import config as cfg
from core.decision_dag import (
    NODE_N1_MARKET_OPEN,
    NODE_N10_DECISION_READY,
    NODE_N11_FINAL_DECISION,
    NODE_N2_FEED_FRESH,
    NODE_N3_WARMUP_DONE,
    NODE_N4_QUOTE_OK,
    NODE_N5_REGIME_OK,
    NODE_N6_RISK_OK,
    NODE_N7_GOVERNANCE_LOCKS_OK,
    NODE_N8_STRATEGY_SELECT,
    NODE_N9_STRATEGY_ELIGIBLE,
    NODE_N9_FINAL_DECISION,
    REASON_MARKET_CLOSED,
    REASON_QUOTE_INVALID,
    REASON_REGIME_UNKNOWN,
    REASON_WARMUP_INCOMPLETE,
    DecisionDAGEvaluator,
    build_market_snapshot,
    evaluate_decision,
)


def _base_market_data(now_epoch: float) -> dict:
    return {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_open": True,
        "timestamp": now_epoch,
        "ltp": 25000.0,
        "ltp_source": "live",
        "ltp_ts_epoch": now_epoch - 0.5,
        "depth_age_sec": 999.0,
        "bid": 100.0,
        "ask": 101.0,
        "quote_ok": True,
        "quote_source": "depth",
        "indicators_ok": True,
        "indicators_age_sec": 1.0,
        "system_state": "READY",
        "warmup_reasons": [],
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.9, "RANGE": 0.1},
        "regime_entropy": 0.2,
        "unstable_reasons": [],
    }


def _default_candidates(allowed: bool = True, family: str | None = "DEFINED_RISK", reasons: list[str] | None = None) -> list[dict]:
    return [
        {
            "family": family,
            "allowed": allowed,
            "reasons": reasons or [],
            "candidate_summary": {"source": "unit_test"},
        }
    ]


def test_decision_dag_module_imports_cleanly():
    mod = importlib.import_module("core.decision_dag")
    assert hasattr(mod, "_synth_index_bid_ask")
    assert callable(mod._synth_index_bid_ask)


def test_feed_stale_never_emitted_when_snapshot_is_fresh(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 1_000.0
    md = _base_market_data(now_epoch)
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.facts["feed_health"]["is_fresh"] is True
    assert "FEED_STALE" not in decision.blockers


def test_feed_fresh_uses_latest_option_tick_when_ltp_timestamp_missing(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 1_025.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "ltp_ts_epoch": None,
            "latest_option_tick_ts": now_epoch - 0.4,
            "latest_option_tick_age_sec": 0.4,
            "ws_connected": True,
            "subscribed_option_tokens_count": 68,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.facts["feed_health"]["is_fresh"] is True
    assert "FEED_STALE" not in decision.blockers


def test_feed_stale_emits_symbol_evidence_log(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "FEED_STALE_EVIDENCE_LOG_ENABLE", True, raising=False)
    now_epoch = 1_050.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "ltp_ts_epoch": now_epoch - 30.0,
            "latest_option_tick_ts": now_epoch - 45.0,
            "latest_option_tick_age_sec": 45.0,
            "option_feed_block_reason": "NO_LIVE_OPTION_FEED",
            "ws_connected": True,
            "subscribed_option_tokens_count": 70,
        }
    )
    caplog.set_level(logging.WARNING, logger="core.decision_dag")
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert "FEED_STALE" in decision.blockers
    assert "FEED_STALE_EVIDENCE symbol=NIFTY source=decision_dag" in caplog.text


def test_paper_stale_feed_is_allowed_without_offhours_relabel(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 1_100.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "PAPER", "market_open": True},
            "market_open": True,
            "ltp_ts_epoch": now_epoch - 500.0,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.allowed is True
    assert "FEED_STALE" not in decision.blockers
    feed_rows = [row for row in decision.explain if row["node"] == NODE_N2_FEED_FRESH]
    assert feed_rows and feed_rows[0]["ok"] is True
    assert feed_rows[0]["facts"]["allow_stale_quotes"] is True
    assert feed_rows[0]["facts"]["offhours_mode"] is False


def test_paper_feed_dropout_missing_ltp_timestamp_does_not_block_feed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 1_120.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "PAPER", "market_open": True},
            "market_open": True,
            "ltp": None,
            "ltp_source": "none",
            "ltp_ts_epoch": None,
            "quote_ok": True,
            "bid": None,
            "ask": None,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert "FEED_STALE" not in decision.blockers
    feed_rows = [row for row in decision.explain if row["node"] == NODE_N2_FEED_FRESH]
    assert feed_rows and feed_rows[0]["ok"] is True
    assert feed_rows[0]["facts"]["allow_stale_quotes"] is True


def test_paper_hist_fetch_failed_is_degraded_not_blocking(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 1_125.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "PAPER", "market_open": True},
            "market_open": True,
            "system_state": "DEGRADED",
            "warmup_reasons": ["HIST_FETCH_FAILED"],
            "indicators_ok": False,
            "indicators_age_sec": 1e9,
            "primary_regime": "UNKNOWN",
            "regime_probs": {},
            "regime_entropy": 0.0,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.allowed is True
    assert "WARMUP_INCOMPLETE" not in decision.blockers
    assert "REGIME_UNKNOWN" not in decision.blockers
    n3 = next(row for row in decision.explain if row["node"] == NODE_N3_WARMUP_DONE)
    n5 = next(row for row in decision.explain if row["node"] == NODE_N5_REGIME_OK)
    assert n3["ok"] is True
    assert n5["ok"] is True


def test_paper_market_closed_with_hist_fetch_failed_and_missing_depth_is_degraded_not_blocking(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "DECISION_DAG_ALLOW_NON_LIVE_MARKET_CLOSED", True, raising=False)
    monkeypatch.setattr(cfg, "DECISION_DAG_ALLOW_NON_LIVE_OPTION_QUOTE_MISSING", True, raising=False)
    now_epoch = 1_126.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "PAPER", "market_open": False},
            "market_open": False,
            "system_state": "DEGRADED",
            "warmup_reasons": ["HIST_FETCH_FAILED"],
            "indicators_ok": False,
            "indicators_age_sec": 1e9,
            "primary_regime": "UNKNOWN",
            "regime_probs": {},
            "regime_entropy": 0.0,
            "quote_ok": False,
            "quote_source": "missing_depth",
            "bid": None,
            "ask": None,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.allowed is True
    assert REASON_MARKET_CLOSED not in decision.blockers
    assert REASON_QUOTE_INVALID not in decision.blockers
    assert REASON_WARMUP_INCOMPLETE not in decision.blockers
    assert REASON_REGIME_UNKNOWN not in decision.blockers
    n1 = next(row for row in decision.explain if row["node"] == NODE_N1_MARKET_OPEN)
    n4 = next(row for row in decision.explain if row["node"] == NODE_N4_QUOTE_OK)
    assert n1["ok"] is True
    assert n1["facts"]["market_closed_degraded"] is True
    assert n4["ok"] is True
    assert n4["facts"]["quote_degraded"] is True


def test_market_closed_blocks_when_non_live_relaxation_is_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "DECISION_DAG_ALLOW_NON_LIVE_MARKET_CLOSED", False, raising=False)
    now_epoch = 1_127.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "LIVE", "market_open": False},
            "market_open": False,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.allowed is False
    assert REASON_MARKET_CLOSED in decision.blockers


def test_live_future_ltp_timestamp_clock_skew_does_not_false_block_feed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 1_130.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "ltp_ts_epoch": now_epoch + 300.0,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert "FEED_STALE" not in decision.blockers
    feed_rows = [row for row in decision.explain if row["node"] == NODE_N2_FEED_FRESH]
    assert feed_rows and feed_rows[0]["ok"] is True
    assert float(feed_rows[0]["facts"]["ltp_age_sec"]) == 0.0


def test_strategy_select_node_emits_predicate_facts_when_no_candidate_is_constructed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 1_140.0
    md = _base_market_data(now_epoch)

    decision = evaluate_decision(md, strategy_candidates=(), now_epoch=now_epoch)
    n8_rows = [row for row in decision.explain if row["node"] == NODE_N8_STRATEGY_SELECT]

    assert decision.allowed is False
    assert list(decision.blockers) == ["NO_STRATEGY_QUALIFIED"]
    assert n8_rows
    facts = n8_rows[0]["facts"]
    assert facts["predicate_node"] == NODE_N8_STRATEGY_SELECT
    assert facts["trade_builder_reached"] is True
    assert facts["candidate_family_considered"] is None
    assert facts["no_candidate_constructed"] is True
    assert facts["strategy_reasons"] == []


def test_index_no_depth_with_fresh_ltp_live_fails_quote_gate_not_feed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "INDEX_REQUIRE_DEPTH_LIVE", True, raising=False)
    now_epoch = 2_000.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "symbol": "SENSEX",
            "instrument": "INDEX",
            "quote_ok": False,
            "quote_source": "missing_depth",
            "depth_age_sec": None,
            "bid": None,
            "ask": None,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.allowed is False
    assert "index_bidask_missing" in decision.blockers
    assert "FEED_STALE" not in decision.blockers
    feed_rows = [row for row in decision.explain if row["node"] == NODE_N2_FEED_FRESH]
    quote_rows = [row for row in decision.explain if row["node"] == NODE_N4_QUOTE_OK]
    assert feed_rows and feed_rows[0]["ok"] is True
    assert quote_rows and quote_rows[0]["ok"] is False
    assert quote_rows[0]["facts"]["quote_source"] == "missing_depth"
    assert quote_rows[0]["facts"]["quote_ok"] is False


def test_index_no_depth_with_fresh_ltp_live_passes_when_depth_not_required(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "INDEX_REQUIRE_DEPTH_LIVE", False, raising=False)
    now_epoch = 2_050.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "symbol": "SENSEX",
            "instrument": "INDEX",
            "quote_ok": False,
            "quote_source": "missing_depth",
            "depth_age_sec": None,
            "bid": None,
            "ask": None,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.allowed is True
    assert "index_bidask_missing" not in decision.blockers
    quote_rows = [row for row in decision.explain if row["node"] == NODE_N4_QUOTE_OK]
    assert quote_rows and quote_rows[0]["ok"] is True
    assert quote_rows[0]["facts"]["quote_source"] == "synthetic_index"



def test_index_sim_mode_uses_synthetic_bidask_when_depth_missing(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 2_500.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "symbol": "SENSEX",
            "instrument": "INDEX",
            "quote_ok": False,
            "quote_source": "missing_depth",
            "depth_age_sec": None,
            "bid": None,
            "ask": None,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    quote_rows = [row for row in decision.explain if row["node"] == NODE_N4_QUOTE_OK]
    assert quote_rows and quote_rows[0]["ok"] is True
    assert quote_rows[0]["facts"]["quote_source"] == "synthetic_index"
    assert quote_rows[0]["facts"]["quote_ok"] is True


def test_live_option_missing_bidask_is_quote_invalid_not_feed_stale(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 3_000.0
    md = _base_market_data(now_epoch)
    md.update({"instrument": "OPT", "quote_ok": False, "quote_source": "missing_depth", "bid": None, "ask": None})
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert decision.allowed is False
    assert "QUOTE_INVALID" in decision.blockers
    assert "FEED_STALE" not in decision.blockers


def test_node_caching_executes_each_node_once(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 4_000.0
    md = _base_market_data(now_epoch)
    evaluator = DecisionDAGEvaluator(strategy_candidates=_default_candidates())
    snapshot = build_market_snapshot(md, now_epoch=now_epoch)
    decision = evaluator.evaluate(snapshot)
    call_counts = decision.facts["node_call_counts"]
    assert call_counts
    assert all(v == 1 for v in call_counts.values())


def test_same_snapshot_produces_identical_decision_report(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 4_100.0
    md = _base_market_data(now_epoch)
    md["symbol"] = "BANKNIFTY"
    snapshot = build_market_snapshot(md, now_epoch=now_epoch)
    evaluator = DecisionDAGEvaluator(strategy_candidates=_default_candidates())
    d1 = evaluator.evaluate(snapshot)
    d2 = evaluator.evaluate(snapshot)
    payload1 = json.dumps(
        {
            "allowed": d1.allowed,
            "blockers": list(d1.blockers),
            "primary_blocker": d1.primary_blocker,
            "stage": d1.stage,
            "selected_strategy": d1.selected_strategy,
            "risk_params": dict(d1.risk_params),
            "explain": list(d1.explain),
            "facts": dict(d1.facts),
        },
        sort_keys=True,
    )
    payload2 = json.dumps(
        {
            "allowed": d2.allowed,
            "blockers": list(d2.blockers),
            "primary_blocker": d2.primary_blocker,
            "stage": d2.stage,
            "selected_strategy": d2.selected_strategy,
            "risk_params": dict(d2.risk_params),
            "explain": list(d2.explain),
            "facts": dict(d2.facts),
        },
        sort_keys=True,
    )
    assert payload1 == payload2


def test_authoritative_linear_dag_wiring():
    evaluator = DecisionDAGEvaluator(strategy_candidates=_default_candidates())
    assert evaluator._nodes[NODE_N1_MARKET_OPEN].deps == ()
    assert evaluator._nodes[NODE_N2_FEED_FRESH].deps == (NODE_N1_MARKET_OPEN,)
    assert evaluator._nodes[NODE_N3_WARMUP_DONE].deps == (NODE_N2_FEED_FRESH,)
    assert evaluator._nodes[NODE_N4_QUOTE_OK].deps == (NODE_N3_WARMUP_DONE,)
    assert evaluator._nodes[NODE_N5_REGIME_OK].deps == (NODE_N4_QUOTE_OK,)
    assert evaluator._nodes[NODE_N6_RISK_OK].deps == (NODE_N5_REGIME_OK,)
    assert evaluator._nodes[NODE_N7_GOVERNANCE_LOCKS_OK].deps == (NODE_N6_RISK_OK,)
    assert evaluator._nodes[NODE_N8_STRATEGY_SELECT].deps == (NODE_N7_GOVERNANCE_LOCKS_OK,)
    assert evaluator._nodes[NODE_N9_STRATEGY_ELIGIBLE].deps == (NODE_N8_STRATEGY_SELECT,)
    assert evaluator._nodes[NODE_N10_DECISION_READY].deps == (NODE_N9_STRATEGY_ELIGIBLE,)
    assert evaluator._nodes[NODE_N11_FINAL_DECISION].deps == (NODE_N10_DECISION_READY,)
    assert NODE_N9_FINAL_DECISION == NODE_N11_FINAL_DECISION


def test_dag_does_not_invoke_strategy_eval_when_candidates_precomputed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 4_200.0
    md = _base_market_data(now_epoch)
    strategy_eval = Mock(side_effect=AssertionError("strategy_eval must not be called by DAG"))
    decision = evaluate_decision(
        md,
        strategy_eval=strategy_eval,
        strategy_candidates=_default_candidates(),
        now_epoch=now_epoch,
    )
    assert decision.allowed is True
    strategy_eval.assert_not_called()


def test_ready_state_cannot_emit_feed_stale_when_ltp_fresh(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    now_epoch = 5_000.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "system_state": "READY",
            "warmup_reasons": [],
            "depth_age_sec": 3_600.0,
            "quote_ok": False,
            "quote_source": "missing_depth",
            "bid": None,
            "ask": None,
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    assert "FEED_STALE" not in decision.blockers
    assert "QUOTE_INVALID" in decision.blockers


def test_n8_exposes_blocked_candidate_facts_when_preconditions_fail(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 6_000.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "system_state": "WARMUP",
            "warmup_reasons": ["bars_below_min"],
            "indicators_ok": False,
            "indicators_age_sec": 1e9,
        }
    )

    decision = evaluate_decision(md, strategy_candidates=_default_candidates(allowed=True, family="DEFINED_RISK", reasons=["candidate_ok"]), now_epoch=now_epoch)
    assert decision.allowed is False
    n8 = next(row for row in decision.explain if row["node"] == NODE_N8_STRATEGY_SELECT)
    assert n8["facts"]["strategy_skipped_due_to_preconditions"] is True
    assert n8["facts"]["candidate_summary"]["family"] == "DEFINED_RISK"
    assert "WARMUP_INCOMPLETE" in n8["facts"]["precondition_reasons"]


def test_n8_candidate_summary_empty_when_no_actionable_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 6_500.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "system_state": "WARMUP",
            "warmup_reasons": ["bars_below_min"],
            "indicators_ok": False,
            "indicators_age_sec": 1e9,
        }
    )

    decision = evaluate_decision(
        md,
        strategy_candidates=[{"family": None, "allowed": False, "reasons": ["neutral_no_trade"]}],
        now_epoch=now_epoch,
    )
    n8 = next(row for row in decision.explain if row["node"] == NODE_N8_STRATEGY_SELECT)
    assert n8["facts"]["candidate_summary"] == {}


def test_strategy_select_returns_precondition_reason_codes_and_facts(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    now_epoch = 7_000.0
    md = _base_market_data(now_epoch)
    md.update(
        {
            "system_state": "WARMUP",
            "indicators_ok": False,
            "indicators_age_sec": 1e9,
            "warmup_reasons": ["bars_below_min"],
        }
    )
    decision = evaluate_decision(md, strategy_candidates=_default_candidates(), now_epoch=now_epoch)
    n8 = next(row for row in decision.explain if row["node"] == NODE_N8_STRATEGY_SELECT)
    n3 = next(row for row in decision.explain if row["node"] == NODE_N3_WARMUP_DONE)
    assert n8["ok"] is True
    assert n8["reasons"] == []
    assert NODE_N3_WARMUP_DONE in n8["facts"]["precondition_failures"]
    assert n8["facts"]["strategy_skipped_due_to_preconditions"] is True
    # Reasons are propagated to final blockers and stage points to strategy node.
    assert "WARMUP_INCOMPLETE" in decision.blockers
    assert n3["ok"] is False
