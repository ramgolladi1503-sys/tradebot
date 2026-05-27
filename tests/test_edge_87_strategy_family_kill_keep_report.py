from __future__ import annotations

import json

from core.strategy_family_kill_keep_report import (
    FAMILY_KEEP,
    FAMILY_KILL,
    FAMILY_WATCH,
    INSUFFICIENT_FAMILY_SAMPLE_REASON,
    INVALID_COST_TRUTH_REPORT_REASON,
    NEGATIVE_NET_EXPECTANCY_REASON,
    NO_NET_COST_BUCKETS_REASON,
    POSITIVE_NET_EXPECTANCY_REASON,
    STRATEGY_FAMILY_REPORT_BLOCKED,
    STRATEGY_FAMILY_REPORT_REDUCED,
    STRATEGY_FAMILY_REPORT_SOURCE,
    WEAK_NET_WIN_RATE_REASON,
    build_strategy_family_report,
)


def _bucket(
    *,
    strategy_id: str,
    regime: str = "TREND",
    closed_count: int = 10,
    net_win_count: int = 6,
    net_loss_count: int = 4,
    net_flat_count: int = 0,
    total_gross_pnl: float = 1000.0,
    total_cost: float = 200.0,
    total_net_pnl: float = 800.0,
    metadata: dict | None = None,
) -> dict:
    return {
        "strategy_id": strategy_id,
        "regime": regime,
        "closed_count": closed_count,
        "net_win_count": net_win_count,
        "net_loss_count": net_loss_count,
        "net_flat_count": net_flat_count,
        "total_gross_pnl": total_gross_pnl,
        "total_cost": total_cost,
        "total_net_pnl": total_net_pnl,
        "net_expectancy_per_trade": total_net_pnl / closed_count if closed_count else 0.0,
        "cost_drag_per_trade": total_cost / closed_count if closed_count else 0.0,
        "metadata": metadata or {},
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def _report(buckets: list[dict], *, status: str = "PAPER_SLIPPAGE_COST_REDUCED") -> dict:
    return {
        "schema_version": 1,
        "source": "paper_slippage_cost_truth_v1",
        "status": status,
        "read_only": True,
        "append": False,
        "buckets": buckets,
    }


def test_strategy_family_report_keeps_positive_net_family():
    out = build_strategy_family_report(
        _report([_bucket(strategy_id="breakout_v1", total_net_pnl=800.0, net_win_count=7, net_loss_count=3)]),
        min_closed_trades=5,
        keep_min_net_expectancy=10.0,
        keep_min_win_rate=0.5,
    )
    payload = out.to_payload()

    assert payload["status"] == STRATEGY_FAMILY_REPORT_REDUCED
    assert payload["family_count"] == 1
    assert payload["keep_count"] == 1
    rec = payload["recommendations"][0]
    assert rec["strategy_family"] == "breakout"
    assert rec["recommendation"] == FAMILY_KEEP
    assert rec["reason_code"] == POSITIVE_NET_EXPECTANCY_REASON
    assert rec["closed_count"] == 10
    assert rec["net_expectancy_per_trade"] == 80.0
    assert rec["sample_ok"] is True


def test_strategy_family_report_kills_negative_net_family():
    out = build_strategy_family_report(
        _report([_bucket(strategy_id="zero_hero_v2", total_net_pnl=-120.0, net_win_count=3, net_loss_count=7)]),
        min_closed_trades=5,
    )
    rec = out.to_payload()["recommendations"][0]

    assert rec["strategy_family"] == "zero_hero"
    assert rec["recommendation"] == FAMILY_KILL
    assert rec["reason_code"] == NEGATIVE_NET_EXPECTANCY_REASON
    assert rec["total_net_pnl"] == -120.0


def test_strategy_family_report_watches_insufficient_sample():
    out = build_strategy_family_report(
        _report([_bucket(strategy_id="vwap", closed_count=2, total_net_pnl=200.0, net_win_count=2, net_loss_count=0)]),
        min_closed_trades=5,
    )
    rec = out.to_payload()["recommendations"][0]

    assert rec["recommendation"] == FAMILY_WATCH
    assert rec["reason_code"] == INSUFFICIENT_FAMILY_SAMPLE_REASON
    assert rec["sample_ok"] is False


def test_strategy_family_report_watches_weak_win_rate_even_when_net_positive():
    out = build_strategy_family_report(
        _report([_bucket(strategy_id="mean_reversion", total_net_pnl=90.0, net_win_count=4, net_loss_count=6)]),
        min_closed_trades=5,
        keep_min_win_rate=0.5,
    )
    rec = out.to_payload()["recommendations"][0]

    assert rec["recommendation"] == FAMILY_WATCH
    assert rec["reason_code"] == WEAK_NET_WIN_RATE_REASON
    assert rec["net_win_rate"] == 0.4


def test_strategy_family_report_groups_multiple_strategy_versions_by_family():
    out = build_strategy_family_report(
        _report(
            [
                _bucket(strategy_id="breakout_v1", regime="TREND", closed_count=5, net_win_count=3, net_loss_count=2, total_net_pnl=50.0),
                _bucket(strategy_id="breakout_v2", regime="RANGE", closed_count=5, net_win_count=4, net_loss_count=1, total_net_pnl=150.0),
            ]
        ),
        min_closed_trades=5,
    )
    rec = out.to_payload()["recommendations"][0]

    assert rec["strategy_family"] == "breakout"
    assert rec["strategy_ids"] == ["breakout_v1", "breakout_v2"]
    assert rec["regimes"] == ["RANGE", "TREND"]
    assert rec["closed_count"] == 10
    assert rec["total_net_pnl"] == 200.0
    assert rec["net_expectancy_per_trade"] == 20.0


def test_strategy_family_report_uses_explicit_family_metadata():
    out = build_strategy_family_report(
        _report([_bucket(strategy_id="custom_alpha", metadata={"strategy_family": "custom_family"})])
    )

    assert out.to_payload()["recommendations"][0]["strategy_family"] == "custom_family"


def test_strategy_family_report_blocks_invalid_cost_truth_report():
    payload = build_strategy_family_report(_report([], status="PAPER_SLIPPAGE_COST_BLOCKED")).to_payload()

    assert payload["status"] == STRATEGY_FAMILY_REPORT_BLOCKED
    assert payload["reason_code"] == INVALID_COST_TRUTH_REPORT_REASON
    assert payload["cost_truth_report_valid"] is False
    assert payload["recommendations"] == []


def test_strategy_family_report_blocks_empty_net_buckets():
    payload = build_strategy_family_report(_report([])).to_payload()

    assert payload["status"] == STRATEGY_FAMILY_REPORT_BLOCKED
    assert payload["reason_code"] == NO_NET_COST_BUCKETS_REASON
    assert payload["cost_truth_report_valid"] is True
    assert payload["recommendations"] == []


def test_strategy_family_report_payload_is_json_serializable_and_non_action():
    out = build_strategy_family_report(_report([_bucket(strategy_id="breakout_v1")]))
    payload = out.to_payload()
    encoded = out.to_json()

    assert json.loads(encoded)["source"] == STRATEGY_FAMILY_REPORT_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["policy"]["is_order_action"] is False
    assert payload["recommendations"][0]["is_order_action"] is False
    assert payload["recommendations"][0]["buckets"][0]["broker_api_called"] is False
