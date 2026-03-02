from __future__ import annotations

from datetime import datetime
import json

from core.analytics.daily_report import build_daily_intelligence_report
from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


def _ts_ms_ist(day: str, hh: int, mm: int, ss: int = 0) -> int:
    dt = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+05:30")
    return int(dt.timestamp() * 1000.0)


def _event(
    *,
    event_id: str,
    trade_key: str,
    ts_ms: int,
    intent: str,
    gate_name: str,
    gate_passed: bool,
    reject_reason: str | None,
    regime: str,
    quote_age_sec: float,
    spread_pct: float,
    feed_state: str,
    target_points: float = 10.0,
    stop_points: float = 5.0,
) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent=intent,  # type: ignore[arg-type]
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason=reject_reason,
        gate_decisions=(GateDecision(gate_name=gate_name, passed=gate_passed, reason=reject_reason),),
        metrics_snapshot={
            "regime": regime,
            "quote_age_sec": quote_age_sec,
            "spread_pct": spread_pct,
            "feed_state": feed_state,
            "target_points": target_points,
            "stop_points": stop_points,
        },
    )


def _outcome(
    *,
    event_ref_id: str,
    trade_key: str,
    ts_ms: int,
    outcome: str,
    mfe: float,
    mae: float,
) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_ref_id}",
        outcome=outcome,  # type: ignore[arg-type]
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


def _fixture_events_and_outcomes(date_key: str) -> tuple[list[TradeIntentEvent], list[dict]]:
    ts0 = _ts_ms_ist(date_key, 10, 0)
    events = [
        _event(
            event_id="rej_quote_win",
            trade_key="tk_rej_quote_win",
            ts_ms=ts0,
            intent="rejected",
            gate_name="quote_guard",
            gate_passed=False,
            reject_reason="quote_stale",
            regime="TREND",
            quote_age_sec=0.4,
            spread_pct=0.004,
            feed_state="OK",
        ),
        _event(
            event_id="rej_quote_lose_1",
            trade_key="tk_rej_quote_lose_1",
            ts_ms=ts0 + 60_000,
            intent="rejected",
            gate_name="quote_guard",
            gate_passed=False,
            reject_reason="quote_stale",
            regime="RANGE",
            quote_age_sec=2.6,
            spread_pct=0.018,
            feed_state="DOWN",
        ),
        _event(
            event_id="rej_quote_lose_2",
            trade_key="tk_rej_quote_lose_2",
            ts_ms=ts0 + 120_000,
            intent="rejected",
            gate_name="quote_guard",
            gate_passed=False,
            reject_reason="quote_stale",
            regime="RANGE",
            quote_age_sec=2.8,
            spread_pct=0.025,
            feed_state="DOWN",
        ),
        _event(
            event_id="rej_premium_lose",
            trade_key="tk_rej_premium_lose",
            ts_ms=ts0 + 180_000,
            intent="rejected",
            gate_name="premium_guard",
            gate_passed=False,
            reject_reason="premium_band",
            regime="MID",
            quote_age_sec=1.7,
            spread_pct=0.03,
            feed_state="DEGRADED",
        ),
        _event(
            event_id="rej_latency_lose",
            trade_key="tk_rej_latency_lose",
            ts_ms=ts0 + 240_000,
            intent="rejected",
            gate_name="latency_guard",
            gate_passed=False,
            reject_reason="stale_tick",
            regime="MID",
            quote_age_sec=3.1,
            spread_pct=0.012,
            feed_state="DOWN",
        ),
        _event(
            event_id="acc_spread_win",
            trade_key="tk_acc_spread_win",
            ts_ms=ts0 + 300_000,
            intent="accepted",
            gate_name="spread_guard",
            gate_passed=True,
            reject_reason=None,
            regime="TREND",
            quote_age_sec=0.5,
            spread_pct=0.006,
            feed_state="OK",
        ),
        _event(
            event_id="acc_spread_lose",
            trade_key="tk_acc_spread_lose",
            ts_ms=ts0 + 360_000,
            intent="accepted",
            gate_name="spread_guard",
            gate_passed=True,
            reject_reason=None,
            regime="RANGE",
            quote_age_sec=1.1,
            spread_pct=0.014,
            feed_state="DEGRADED",
        ),
    ]

    outcomes = [
        _outcome(
            event_ref_id="rej_quote_win",
            trade_key="tk_rej_quote_win",
            ts_ms=ts0 + 30_000,
            outcome="hit_target",
            mfe=12.0,
            mae=-1.0,
        ),
        _outcome(
            event_ref_id="rej_quote_lose_1",
            trade_key="tk_rej_quote_lose_1",
            ts_ms=ts0 + 90_000,
            outcome="hit_sl",
            mfe=2.0,
            mae=-8.0,
        ),
        _outcome(
            event_ref_id="rej_quote_lose_2",
            trade_key="tk_rej_quote_lose_2",
            ts_ms=ts0 + 150_000,
            outcome="hit_sl",
            mfe=1.5,
            mae=-9.0,
        ),
        _outcome(
            event_ref_id="rej_premium_lose",
            trade_key="tk_rej_premium_lose",
            ts_ms=ts0 + 210_000,
            outcome="hit_sl",
            mfe=1.0,
            mae=-7.0,
        ),
        _outcome(
            event_ref_id="rej_latency_lose",
            trade_key="tk_rej_latency_lose",
            ts_ms=ts0 + 270_000,
            outcome="hit_sl",
            mfe=0.5,
            mae=-6.0,
        ),
        _outcome(
            event_ref_id="acc_spread_win",
            trade_key="tk_acc_spread_win",
            ts_ms=ts0 + 330_000,
            outcome="hit_target",
            mfe=10.0,
            mae=-2.0,
        ),
        _outcome(
            event_ref_id="acc_spread_lose",
            trade_key="tk_acc_spread_lose",
            ts_ms=ts0 + 390_000,
            outcome="hit_sl",
            mfe=3.0,
            mae=-6.0,
        ),
    ]

    return events, outcomes


def test_daily_report_builds_outputs_and_json_payload(tmp_path):
    date_key = "2026-02-28"
    events, outcomes = _fixture_events_and_outcomes(date_key)
    output_dir = tmp_path / "runtime" / "analytics" / "reports" / date_key

    payload = build_daily_intelligence_report(
        date_key,
        events=events,
        outcomes=outcomes,
        attempt_outcome_replay=False,
        output_dir=output_dir,
    )

    md_path = output_dir / "daily_report.md"
    json_path = output_dir / "daily_report.json"
    assert md_path.exists()
    assert json_path.exists()

    decoded = json.loads(json_path.read_text(encoding="utf-8"))
    assert decoded["date"] == date_key
    assert decoded["header"]["counts"]["events"] == len(events)
    assert decoded["header"]["counts"]["rejected"] == 5
    assert "blocked_edge" in decoded["sections"]
    assert "protective_gates" in decoded["sections"]
    assert "regime_notes" in decoded["sections"]
    assert "target_sl_calibration" in decoded["sections"]
    assert "feed_quality_impact" in decoded["sections"]
    assert len(decoded["action_list"]) == 3
    assert payload["daily_report_markdown_path"] == str(md_path)
    assert payload["daily_report_json_path"] == str(json_path)


def test_daily_report_markdown_contains_required_headings(tmp_path):
    date_key = "2026-02-28"
    events, outcomes = _fixture_events_and_outcomes(date_key)
    output_dir = tmp_path / "runtime" / "analytics" / "reports" / date_key

    build_daily_intelligence_report(
        date_key,
        events=events,
        outcomes=outcomes,
        attempt_outcome_replay=False,
        output_dir=output_dir,
    )

    content = (output_dir / "daily_report.md").read_text(encoding="utf-8")
    assert "## Section 1: What blocked edge yesterday?" in content
    assert "## Section 2: What saved you?" in content
    assert "## Section 3: Regime notes" in content
    assert "## Section 4: Target/SL calibration" in content
    assert "## Section 5: Feed quality impact" in content
    assert "## Action list" in content
