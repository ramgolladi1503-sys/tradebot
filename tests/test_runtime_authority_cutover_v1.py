from __future__ import annotations

import time
from types import SimpleNamespace

import pandas as pd

from config import config as cfg
from core.runtime_authority_cutover import (
    apply_runtime_authority,
    authority_allows_execution,
    partition_operator_candidates,
)


def _executable(candidate_id: str, score: float) -> dict:
    now = time.time()
    return {
        "trade_id": candidate_id,
        "symbol": "NIFTY",
        "tradingsymbol": "NIFTY26AUG25000CE",
        "option_token": 123456,
        "market_mode": "LIVE",
        "strategy_family": "MARKET_EVENT_GRAPH",
        "side": "BUY",
        "signal_score": 0.82,
        "quote_source": "LIVE",
        "spread_source": "LIVE",
        "quote_completeness": "FULL",
        "best_bid": 100.0,
        "best_ask": 101.0,
        "ltp": 100.5,
        "quote_age_sec": 0.1,
        "ltp_age_sec": 0.1,
        "bid_age_sec": 0.1,
        "ask_age_sec": 0.1,
        "chain_snapshot_age_sec": 0.1,
        "last_option_tick_epoch": now,
        "option_ltp_timestamp": now,
        "quote_ts_epoch": now,
        "option_feed_block_reason": "OK",
        "fresh_quote_ok": True,
        "spread_ok": True,
        "liquidity_ok": True,
        "execution_allowed": True,
        "eligible_for_execution": True,
        "tradable": True,
        "execution_ok": True,
        "execution_entry": 101.0,
        "execution_entry_status": "EXECUTABLE",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "candidate_status": "READY",
        "selection_score": score,
        "opportunity_score": score,
    }


def test_recovered_fallback_is_visible_advisory_never_executable_or_allocated():
    row = _executable("fallback", 0.99)
    row.update({"recovered_fallback": True, "capital_assigned": 10000.0})
    stamped = apply_runtime_authority(row, mode="LIVE")
    assert stamped["operator_bucket"] == "ADVISORY_ONLY"
    assert stamped["authority_allowed"] is False
    assert stamped["selection_score"] == 0.0
    assert stamped["capital_assigned"] == 0.0
    assert stamped["selected_for_execution"] is False
    assert stamped["permission"] == "QUEUE_ONLY"


def test_unknown_or_stale_quote_cannot_become_executable():
    unknown = _executable("unknown", 0.8)
    unknown["quote_source"] = ""
    stale = _executable("stale", 0.7)
    stale["fresh_quote_ok"] = False
    for row in (unknown, stale):
        stamped = apply_runtime_authority(row, mode="LIVE")
        assert stamped["authority_allowed"] is False
        assert stamped["selection_score"] == 0.0
        assert not authority_allows_execution(stamped)


def test_operator_partition_ranks_only_executable_by_selection_score():
    strong = _executable("strong", 0.82)
    weak = _executable("weak", 0.51)
    advisory = _executable("advisory", 0.97)
    advisory["recovered_fallback"] = True
    partition = partition_operator_candidates(
        [weak, advisory, strong],
        mode="LIVE",
    )
    assert [
        row["trade_id"] for row in partition["top_executable"]
    ] == ["strong", "weak"]
    assert [row["trade_id"] for row in partition["advisory"]] == [
        "advisory"
    ]
    assert partition["advisory"][0]["selection_score"] == 0.0


def test_actual_opportunity_selector_never_receives_advisory(monkeypatch):
    import core.opportunity_engine as engine

    captured = {}

    def fake_legacy(candidates, *args, **kwargs):
        captured["ids"] = [
            getattr(row, "trade_id", row.get("trade_id"))
            for row in candidates
        ]
        return candidates[0] if candidates else None

    monkeypatch.setattr(
        engine,
        "_RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY",
        fake_legacy,
    )
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    advisory = _executable("advisory", 0.99)
    advisory["recovered_fallback"] = True
    result = engine.select_best_opportunity(
        [advisory, _executable("valid", 0.62)],
        scope="unit",
    )
    assert captured["ids"] == ["valid"]
    assert getattr(result, "trade_id", result.get("trade_id")) == "valid"


def test_execution_router_authority_firewall_runs_before_order_or_approval():
    from core.execution_router import ExecutionRouter

    trade = SimpleNamespace(
        **apply_runtime_authority(
            {
                **_executable("blocked-router", 0.9),
                "recovered_fallback": True,
            },
            mode="LIVE",
        )
    )
    router = object.__new__(ExecutionRouter)
    filled, price, report = router.execute(
        trade,
        bid=100.0,
        ask=101.0,
        volume=1000,
    )
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith(
        "runtime_authority_blocked:"
    )
    assert report["runtime_authority"]["allowed"] is False


def test_dashboard_model_separates_operator_truth_and_zeroes_selection_score(
    monkeypatch,
):
    from dashboard.ui.table_model import normalize_df

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    frame = pd.DataFrame(
        [
            {
                **_executable("ui-valid", 0.73),
                "timestamp": "2026-08-03T10:00:00+05:30",
                "instrument_type": "OPT",
                "option_type": "CE",
                "strike": 25000,
                "expiry_date": "2026-08-04",
                "side": "BUY",
                "status": "READY",
            },
            {
                **_executable("ui-advisory", 0.95),
                "recovered_fallback": True,
                "timestamp": "2026-08-03T10:00:00+05:30",
                "instrument_type": "OPT",
                "option_type": "CE",
                "strike": 25100,
                "expiry_date": "2026-08-04",
                "side": "BUY",
                "status": "ADVISORY_ONLY",
            },
        ]
    )
    out = normalize_df(frame)
    valid = out.loc[out["trade_id"] == "ui-valid"].iloc[0]
    advisory = out.loc[out["trade_id"] == "ui-advisory"].iloc[0]
    assert valid["operator_bucket"] == "TOP_EXECUTABLE"
    assert float(valid["selection_score"]) == 0.73
    assert advisory["operator_bucket"] == "ADVISORY_ONLY"
    assert float(advisory["selection_score"]) == 0.0
