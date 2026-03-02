from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

from core.analytics.daily_intel import build_day_report, load_day_events, write_day_outputs, write_day_report


def _ts_ms(day: str, minute_offset: int) -> int:
    base = datetime.fromisoformat(f"{day}T09:20:00+05:30").astimezone(timezone.utc)
    dt = base + timedelta(minutes=int(minute_offset))
    return int(dt.timestamp() * 1000.0)


def _iso_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _event(
    *,
    day: str,
    event_id: str,
    trade_key: str,
    intent: str,
    run_id: str,
    minute_offset: int,
    reject_reason: str | None = None,
    feed_state: str = "OK",
    feed_group: str = "OPT:NIFTY",
    regime: str = "TREND",
    symbol: str = "NIFTY",
    side: str = "BUY",
) -> dict:
    event_type = {
        "rejected": "REJECTED_TRADE",
        "accepted": "ACCEPTED_TRADE",
        "advisory": "ADVISORY_TRADE",
    }[intent]
    ts_ms = _ts_ms(day, minute_offset)
    payload = {
        "schema_version": 2,
        "event_type": event_type,
        "event_id": event_id,
        "trade_key": trade_key,
        "ts_utc": _iso_utc(ts_ms),
        "symbol": symbol,
        "side": side,
        "run_id": run_id,
        "desk_id": "DEFAULT",
        "gate_reasons": [reject_reason] if reject_reason else [],
        "reject_reason": reject_reason,
        "feed_state": feed_state,
        "feed_group": feed_group,
        "regime": regime,
        "quote_age_sec": 0.6 if feed_state == "OK" else 2.5,
        "spread_pct": 0.01 if feed_state == "OK" else 0.03,
        "entry": 100.0,
        "target": 106.0,
        "stop": 95.0,
    }
    return payload


def _outcome_row(
    *,
    event_ref_id: str,
    trade_key: str,
    symbol: str,
    outcome: str,
    minute_offset: int,
    day: str,
    mfe: float = 8.0,
    mae: float = 3.0,
) -> dict:
    ts_ms = _ts_ms(day, minute_offset)
    return {
        "event_ref_id": event_ref_id,
        "trade_outcome": {
            "event_id": f"out_{event_ref_id}",
            "trade_key": trade_key,
            "outcome": outcome,
            "ts_epoch_ms": ts_ms,
            "symbol": symbol,
            "mfe_points": mfe,
            "mae_points": mae,
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")


def _seed_day(base: Path, day: str) -> None:
    events = [
        _event(
            day=day,
            event_id="rej_feed_hit",
            trade_key="TK_FEED_1",
            intent="rejected",
            run_id="RUN_A",
            minute_offset=0,
            reject_reason="feed_state_DEGRADED",
            feed_state="DEGRADED",
            feed_group="OPT:SENSEX",
            regime="RANGE",
        ),
        _event(
            day=day,
            event_id="rej_feed_sl",
            trade_key="TK_FEED_2",
            intent="rejected",
            run_id="RUN_A",
            minute_offset=1,
            reject_reason="feed_state_DOWN",
            feed_state="DOWN",
            feed_group="OPT:SENSEX",
            regime="RANGE",
        ),
        _event(
            day=day,
            event_id="rej_gate_hit",
            trade_key="TK_GATE_1",
            intent="rejected",
            run_id="RUN_B",
            minute_offset=2,
            reject_reason="premium_band_fail",
            feed_state="OK",
            feed_group="OPT:NIFTY",
            regime="TREND",
        ),
        _event(
            day=day,
            event_id="rej_gate_sl",
            trade_key="TK_GATE_2",
            intent="rejected",
            run_id="RUN_B",
            minute_offset=3,
            reject_reason="premium_band_fail",
            feed_state="OK",
            feed_group="OPT:NIFTY",
            regime="TREND",
        ),
        _event(
            day=day,
            event_id="acc_1",
            trade_key="TK_ACC_1",
            intent="accepted",
            run_id="RUN_B",
            minute_offset=4,
            reject_reason=None,
            feed_state="OK",
            regime="TREND",
        ),
        _event(
            day=day,
            event_id="adv_1",
            trade_key="TK_ADV_1",
            intent="advisory",
            run_id="RUN_B",
            minute_offset=5,
            reject_reason=None,
            feed_state="OK",
            regime="MID",
        ),
    ]
    outcomes = [
        _outcome_row(
            event_ref_id="rej_feed_hit",
            trade_key="TK_FEED_1",
            symbol="NIFTY",
            outcome="hit_target",
            minute_offset=10,
            day=day,
            mfe=10.0,
            mae=1.5,
        ),
        _outcome_row(
            event_ref_id="rej_feed_sl",
            trade_key="TK_FEED_2",
            symbol="NIFTY",
            outcome="hit_sl",
            minute_offset=11,
            day=day,
            mfe=2.0,
            mae=7.0,
        ),
        _outcome_row(
            event_ref_id="rej_gate_hit",
            trade_key="TK_GATE_1",
            symbol="NIFTY",
            outcome="hit_target",
            minute_offset=12,
            day=day,
            mfe=9.0,
            mae=2.0,
        ),
        _outcome_row(
            event_ref_id="rej_gate_sl",
            trade_key="TK_GATE_2",
            symbol="NIFTY",
            outcome="hit_sl",
            minute_offset=13,
            day=day,
            mfe=1.5,
            mae=8.0,
        ),
    ]
    _write_jsonl(base / day / "events.jsonl", events)
    _write_jsonl(base / "outcomes" / f"{day}.jsonl", outcomes)


def test_report_generates_top5_insights(tmp_path: Path):
    base = tmp_path / "runtime" / "analytics"
    day = "2026-02-27"
    _seed_day(base, day)

    rows = load_day_events(base, date.fromisoformat(day))
    report = build_day_report(rows, date.fromisoformat(day))

    insights = list(report.get("top_insights") or [])
    assert len(insights) == 5
    assert [item["rank"] for item in insights] == [1, 2, 3, 4, 5]


def test_feed_block_insight_present(tmp_path: Path):
    base = tmp_path / "runtime" / "analytics"
    day = "2026-02-27"
    _seed_day(base, day)

    rows = load_day_events(base, date.fromisoformat(day))
    report = build_day_report(rows, date.fromisoformat(day))

    titles = [str(item.get("title", "")) for item in report.get("top_insights", [])]
    assert any(("Feed blocked" in title) or ("Feed blocks were" in title) for title in titles)


def test_suggestions_are_confidence_gated(tmp_path: Path):
    base = tmp_path / "runtime" / "analytics"
    day = "2026-02-27"
    _seed_day(base, day)

    rows = load_day_events(base, date.fromisoformat(day))
    report = build_day_report(rows, date.fromisoformat(day))

    suggestions = list(report.get("suggestions") or [])
    assert suggestions
    for item in suggestions:
        assert item["confidence_passed"] is False
        assert item["text"] == "NO SUGGESTION (insufficient confidence)"


def test_atomic_write_outputs(tmp_path: Path):
    base = tmp_path / "runtime" / "analytics"
    day = "2026-02-27"
    _seed_day(base, day)

    rows = load_day_events(base, date.fromisoformat(day))
    report = build_day_report(rows, date.fromisoformat(day))
    md_path, json_path = write_day_report(report, base / "reports")

    assert md_path.exists()
    assert json_path.exists()
    assert "Top 5 Insights" in md_path.read_text(encoding="utf-8")
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["day"] == day
    assert not any(path.suffix == ".tmp" for path in md_path.parent.glob("*"))


def test_write_day_outputs_includes_config_delta_files(tmp_path: Path):
    base = tmp_path / "runtime" / "analytics"
    day = "2026-02-27"
    _seed_day(base, day)

    rows = load_day_events(base, date.fromisoformat(day))
    report = build_day_report(rows, date.fromisoformat(day))
    md_path, json_path, proposal_md_path, proposal_json_path = write_day_outputs(report, base / "reports")

    assert md_path.exists()
    assert json_path.exists()
    assert proposal_md_path.exists()
    assert proposal_json_path.exists()
    proposal = json.loads(proposal_json_path.read_text(encoding="utf-8"))
    assert proposal["day"] == day


def test_sessions_count_across_window(tmp_path: Path):
    base = tmp_path / "runtime" / "analytics"
    day = "2026-02-27"
    prev_day = "2026-02-26"
    _seed_day(base, day)
    _write_jsonl(
        base / prev_day / "events.jsonl",
        [
            _event(
                day=prev_day,
                event_id="rej_prev",
                trade_key="TK_PREV",
                intent="rejected",
                run_id="RUN_PREV",
                minute_offset=0,
                reject_reason="risk_cap",
                feed_state="OK",
                feed_group="OPT:NIFTY",
                regime="MID",
            )
        ],
    )

    rows = load_day_events(base, date.fromisoformat(day), window_days=2)
    report = build_day_report(rows, date.fromisoformat(day))

    assert int(report["summary"]["sessions_count"]) >= 3
