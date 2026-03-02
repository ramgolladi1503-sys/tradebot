from __future__ import annotations

import json

from core.analytics.regime_analysis import build_regime_analysis
from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


def _event(
    *,
    event_id: str,
    trade_key: str,
    ts_ms: int,
    intent: str,
    regime: str,
    gate_name: str,
    gate_passed: bool,
    reject_reason: str | None = None,
) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent=intent,
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason=reject_reason,
        gate_decisions=(
            GateDecision(gate_name=gate_name, passed=gate_passed, reason=reject_reason if not gate_passed else None),
        ),
        metrics_snapshot={"regime": regime},
    )


def _outcome(*, event_ref_id: str, trade_key: str, ts_ms: int, outcome: str, mfe: float, mae: float) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_ref_id}",
        outcome=outcome,
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        mfe_points=mfe,
        mae_points=mae,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason=None,
    )
    return {"event_ref_id": event_ref_id, "trade_outcome": row.to_dict()}


def test_regime_analysis_grouping_and_recommendations(tmp_path, monkeypatch):
    # 2026-02-28 IST
    base_ts = 1_772_272_400_000
    events = [
        _event(
            event_id="trend_rej_win",
            trade_key="tk_trend_rej_win",
            ts_ms=base_ts,
            intent="rejected",
            regime="TREND",
            gate_name="spread_guard",
            gate_passed=False,
            reject_reason="spread_high",
        ),
        _event(
            event_id="trend_rej_lose",
            trade_key="tk_trend_rej_lose",
            ts_ms=base_ts + 10_000,
            intent="rejected",
            regime="TREND",
            gate_name="spread_guard",
            gate_passed=False,
            reject_reason="spread_high",
        ),
        _event(
            event_id="range_rej_lose_1",
            trade_key="tk_range_rej_lose_1",
            ts_ms=base_ts + 20_000,
            intent="rejected",
            regime="RANGE",
            gate_name="spread_guard",
            gate_passed=False,
            reject_reason="spread_high",
        ),
        _event(
            event_id="range_rej_lose_2",
            trade_key="tk_range_rej_lose_2",
            ts_ms=base_ts + 30_000,
            intent="rejected",
            regime="RANGE",
            gate_name="spread_guard",
            gate_passed=False,
            reject_reason="spread_high",
        ),
        _event(
            event_id="unstable_rej_neutral",
            trade_key="tk_unstable_rej_neutral",
            ts_ms=base_ts + 40_000,
            intent="rejected",
            regime="UNSTABLE",
            gate_name="quote_guard",
            gate_passed=False,
            reject_reason="stale_quote",
        ),
        _event(
            event_id="trend_acc_win",
            trade_key="tk_trend_acc_win",
            ts_ms=base_ts + 50_000,
            intent="accepted",
            regime="TREND",
            gate_name="spread_guard",
            gate_passed=True,
        ),
        _event(
            event_id="range_acc_win",
            trade_key="tk_range_acc_win",
            ts_ms=base_ts + 60_000,
            intent="accepted",
            regime="RANGE",
            gate_name="spread_guard",
            gate_passed=True,
        ),
    ]

    outcomes = [
        _outcome(
            event_ref_id="trend_rej_win",
            trade_key="tk_trend_rej_win",
            ts_ms=base_ts + 80_000,
            outcome="hit_target",
            mfe=12.0,
            mae=-2.0,
        ),
        _outcome(
            event_ref_id="trend_rej_lose",
            trade_key="tk_trend_rej_lose",
            ts_ms=base_ts + 90_000,
            outcome="hit_sl",
            mfe=4.0,
            mae=-8.0,
        ),
        _outcome(
            event_ref_id="range_rej_lose_1",
            trade_key="tk_range_rej_lose_1",
            ts_ms=base_ts + 100_000,
            outcome="hit_sl",
            mfe=3.0,
            mae=-9.0,
        ),
        _outcome(
            event_ref_id="range_rej_lose_2",
            trade_key="tk_range_rej_lose_2",
            ts_ms=base_ts + 110_000,
            outcome="hit_sl",
            mfe=2.5,
            mae=-10.0,
        ),
        _outcome(
            event_ref_id="unstable_rej_neutral",
            trade_key="tk_unstable_rej_neutral",
            ts_ms=base_ts + 120_000,
            outcome="no_hit",
            mfe=1.5,
            mae=-1.2,
        ),
        _outcome(
            event_ref_id="trend_acc_win",
            trade_key="tk_trend_acc_win",
            ts_ms=base_ts + 130_000,
            outcome="hit_target",
            mfe=14.0,
            mae=-1.0,
        ),
        _outcome(
            event_ref_id="range_acc_win",
            trade_key="tk_range_acc_win",
            ts_ms=base_ts + 140_000,
            outcome="hit_target",
            mfe=11.0,
            mae=-2.0,
        ),
    ]

    monkeypatch.setattr("core.analytics.regime_analysis.cfg.REGIME_RECOMMEND_MIN_BLOCKED_COUNT", 2, raising=False)
    monkeypatch.setattr("core.analytics.regime_analysis.cfg.REGIME_RECOMMEND_NEGATIVE_THRESHOLD", 0.0, raising=False)

    out_path = tmp_path / "runtime" / "analytics" / "reports" / "2026-02-28" / "regime_analysis.json"
    payload = build_regime_analysis(
        "2026-02-28",
        events=events,
        outcomes=outcomes,
        output_path=out_path,
    )

    splits = {row["regime"]: row for row in payload["regime_splits"]}
    assert splits["TREND"]["count"] == 3
    assert splits["TREND"]["wins"] == 2
    assert splits["TREND"]["losses"] == 1
    assert abs(float(splits["TREND"]["win_rate"]) - (2.0 / 3.0)) < 1e-9

    assert splits["RANGE"]["count"] == 3
    assert splits["RANGE"]["wins"] == 1
    assert splits["RANGE"]["losses"] == 2

    assert splits["UNSTABLE"]["count"] == 1
    assert splits["UNSTABLE"]["neutral"] == 1

    gate_rows = {
        (row["regime"], row["gate_name"]): row
        for row in payload["gate_net_edge_by_regime"]
    }
    assert gate_rows[("TREND", "spread_guard")]["blocked_count"] == 2
    assert gate_rows[("TREND", "spread_guard")]["net_edge_score"] == 0.0
    assert gate_rows[("RANGE", "spread_guard")]["blocked_count"] == 2
    assert gate_rows[("RANGE", "spread_guard")]["net_edge_score"] == -1.0

    recs = payload["regime_recommendations"]
    assert len(recs) == 1
    assert recs[0]["gate_name"] == "spread_guard"
    assert recs[0]["regime"] == "RANGE"
    assert recs[0]["positive_regimes"] == ["TREND"]

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["total_events"] == 7
    assert written["matched_outcomes"] == 7
