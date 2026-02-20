import json

from config import config as cfg
from core.decision_dag import build_market_snapshot, evaluate_decision
from core.decision_side_effects import handle_post_decision_side_effects


def _base_market_data(now_epoch: float) -> dict:
    return {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_open": True,
        "timestamp": now_epoch,
        "ltp": 25000.0,
        "ltp_source": "live",
        "ltp_ts_epoch": now_epoch - 0.5,
        "bid": 100.0,
        "ask": 101.0,
        "quote_ok": True,
        "quote_source": "depth",
        "indicators_ok": False,
        "indicators_age_sec": 1e9,
        "system_state": "WARMUP",
        "warmup_reasons": ["bars_below_min"],
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.9, "RANGE": 0.1},
        "regime_entropy": 0.2,
        "unstable_reasons": [],
    }


def _rows(path):
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_post_decision_handler_logs_blocked_candidate(monkeypatch, tmp_path):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    md = _base_market_data(10_000.0)
    decision = evaluate_decision(
        md,
        strategy_candidates=[
            {
                "family": "DEFINED_RISK",
                "allowed": True,
                "reasons": ["candidate_ok"],
                "candidate_summary": {"family": "DEFINED_RISK", "allowed": True},
            }
        ],
        now_epoch=10_000.0,
    )

    handle_post_decision_side_effects(decision, decision.explain, build_market_snapshot(md, now_epoch=10_000.0))
    blocked_path = desk_log_dir / "blocked_candidates.jsonl"
    assert blocked_path.exists()
    rows = _rows(blocked_path)
    assert rows
    last = rows[-1]
    assert last["symbol"] == "NIFTY"
    assert last["stage"] == "decision_dag"
    assert last["candidate_summary"]["family"] == "DEFINED_RISK"
    assert isinstance(last["blockers"], list)


def test_post_decision_handler_skips_without_potential_candidate(monkeypatch, tmp_path):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    md = _base_market_data(20_000.0)
    decision = evaluate_decision(
        md,
        strategy_candidates=[{"family": None, "allowed": False, "reasons": ["neutral_no_trade"]}],
        now_epoch=20_000.0,
    )

    handle_post_decision_side_effects(decision, decision.explain, build_market_snapshot(md, now_epoch=20_000.0))
    blocked_path = desk_log_dir / "blocked_candidates.jsonl"
    assert not blocked_path.exists()
