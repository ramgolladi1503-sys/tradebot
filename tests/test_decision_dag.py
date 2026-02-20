import importlib
import json
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


def test_index_no_depth_with_fresh_ltp_live_fails_quote_gate_not_feed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
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
    assert "QUOTE_INVALID" in decision.blockers
    assert "FEED_STALE" not in decision.blockers
    feed_rows = [row for row in decision.explain if row["node"] == NODE_N2_FEED_FRESH]
    quote_rows = [row for row in decision.explain if row["node"] == NODE_N4_QUOTE_OK]
    assert feed_rows and feed_rows[0]["ok"] is True
    assert quote_rows and quote_rows[0]["ok"] is False
    assert quote_rows[0]["facts"]["quote_source"] == "missing_depth"


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
