from __future__ import annotations

from datetime import datetime
import json

from core.analytics.schema import TradeIntentEvent, TradeOutcome
from core.analytics.target_sl_calibration import build_target_sl_calibration_report


def _ts_ms_ist(day: str, hh: int, mm: int, ss: int = 0) -> int:
    dt = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+05:30")
    return int(dt.timestamp() * 1000.0)


def _event(
    *,
    event_id: str,
    trade_key: str,
    ts_ms: int,
    target_points: float,
    stop_points: float,
    atr_points: float | None = None,
) -> TradeIntentEvent:
    metrics = {"target_points": target_points, "stop_points": stop_points}
    if atr_points is not None:
        metrics["atr_points"] = atr_points
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason="unit",
        gate_decisions=(),
        metrics_snapshot=metrics,
    )


def _outcome(*, event_ref_id: str, trade_key: str, ts_ms: int, mfe: float, mae: float, outcome: str = "no_hit") -> dict:
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


def test_target_sl_calibration_metrics_empirical(tmp_path):
    date_key = "2026-02-28"
    ts0 = _ts_ms_ist(date_key, 10, 0)
    events = [
        _event(event_id="evt1", trade_key="tk1", ts_ms=ts0, target_points=10.0, stop_points=5.0),
        _event(event_id="evt2", trade_key="tk2", ts_ms=ts0 + 60_000, target_points=10.0, stop_points=5.0),
        _event(event_id="evt3", trade_key="tk3", ts_ms=ts0 + 120_000, target_points=10.0, stop_points=5.0),
    ]
    outcomes = [
        _outcome(event_ref_id="evt1", trade_key="tk1", ts_ms=ts0 + 30_000, mfe=12.0, mae=-4.0, outcome="hit_target"),
        _outcome(event_ref_id="evt2", trade_key="tk2", ts_ms=ts0 + 90_000, mfe=8.0, mae=-7.0, outcome="hit_sl"),
        _outcome(event_ref_id="evt3", trade_key="tk3", ts_ms=ts0 + 150_000, mfe=15.0, mae=-6.0, outcome="hit_target"),
    ]

    out_path = tmp_path / "runtime" / "analytics" / "reports" / date_key / "target_sl_calibration.json"
    payload = build_target_sl_calibration_report(
        date_key,
        events=events,
        outcomes=outcomes,
        output_path=out_path,
    )

    assert payload["matched_outcomes"] == 3
    assert payload["target_metrics"]["samples"] == 3
    assert abs(float(payload["target_metrics"]["pct_mfe_ge_target"]) - (2.0 / 3.0)) < 1e-9
    assert abs(float(payload["target_metrics"]["avg_left_on_table_points"]) - 3.5) < 1e-9

    assert payload["stop_metrics"]["samples"] == 3
    assert abs(float(payload["stop_metrics"]["pct_mae_ge_stop"]) - (2.0 / 3.0)) < 1e-9
    assert abs(float(payload["stop_metrics"]["avg_too_tight_points"]) - 1.5) < 1e-9

    assert payload["recommendations"]["method"] == "empirical_quantiles"
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["target_metrics"]["samples"] == 3


def test_target_sl_calibration_atr_bucket_recommendations(tmp_path):
    date_key = "2026-02-28"
    ts0 = _ts_ms_ist(date_key, 11, 0)
    atrs = [5.0, 6.0, 7.0, 10.0, 12.0, 15.0]
    events = []
    outcomes = []
    for idx, atr in enumerate(atrs, start=1):
        eid = f"evt_atr_{idx}"
        tk = f"tk_atr_{idx}"
        ts = ts0 + (idx * 60_000)
        events.append(
            _event(
                event_id=eid,
                trade_key=tk,
                ts_ms=ts,
                target_points=atr * 1.0,
                stop_points=atr * 0.5,
                atr_points=atr,
            )
        )
        outcomes.append(
            _outcome(
                event_ref_id=eid,
                trade_key=tk,
                ts_ms=ts + 30_000,
                mfe=atr * (1.1 + (0.05 * idx)),
                mae=-(atr * (0.4 + (0.03 * idx))),
                outcome="no_hit",
            )
        )

    payload = build_target_sl_calibration_report(
        date_key,
        events=events,
        outcomes=outcomes,
        output_path=tmp_path / "runtime" / "analytics" / "reports" / date_key / "target_sl_calibration.json",
    )

    rec = payload["recommendations"]
    assert rec["method"] == "atr_buckets"
    assert rec["atr_split"]["q33"] is not None
    assert rec["atr_split"]["q66"] is not None
    assert len(rec["buckets"]) >= 1
    for bucket in rec["buckets"]:
        assert bucket["target_band_points"]["count"] >= 1
        assert bucket["stop_band_points"]["count"] >= 1
