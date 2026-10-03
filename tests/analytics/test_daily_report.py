from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.analytics.daily_report import _default_outcome_path, _ensure_outcomes_available, build_daily_intelligence_report
from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_jsonl(name: str) -> list[dict]:
    rows: list[dict] = []
    for line in (FIXTURES_DIR / name).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


def _event_from_row(row: dict, *, intent: str) -> TradeIntentEvent:
    reject_reason = row.get("reject_reason")
    gate_name = str(row.get("gate_name") or "unknown_gate")
    return TradeIntentEvent(
        trade_key=str(row["trade_key"]),
        event_id=str(row["event_id"]),
        intent=intent,  # type: ignore[arg-type]
        ts_epoch_ms=int(row["reject_ts_epoch"]),
        symbol=str(row["symbol"]),
        side=str(row["side"]),
        source="unit_test_fixture",
        reject_reason=str(reject_reason) if reject_reason is not None else None,
        gate_decisions=(
            GateDecision(
                gate_name=gate_name,
                passed=(intent == "accepted"),
                reason=str(reject_reason) if reject_reason is not None else None,
            ),
        ),
        metrics_snapshot={
            "entry": float(row["entry"]),
            "target_points": abs(float(row["target"]) - float(row["entry"])),
            "stop_points": abs(float(row["entry"]) - float(row["stop"])),
            "regime": "TREND" if row["symbol"] == "NIFTY" else "RANGE",
            "quote_age_sec": 0.6 if intent == "accepted" else 1.8,
            "spread_pct": 0.008 if intent == "accepted" else 0.022,
            "feed_state": "OK" if intent == "accepted" else "DEGRADED",
        },
    )


def _outcome_for_event(event: TradeIntentEvent, idx: int) -> dict:
    labels = ["hit_target", "hit_sl", "no_hit"]
    label = labels[idx % len(labels)]
    outcome = TradeOutcome(
        trade_key=event.trade_key,
        event_id=f"out_{event.event_id}",
        outcome=label,  # type: ignore[arg-type]
        ts_epoch_ms=int(event.ts_epoch_ms) + 60_000,
        symbol=event.symbol,
        mfe_points=6.0 if label == "hit_target" else 2.0,
        mae_points=-6.0 if label == "hit_sl" else -2.0,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test_fixture",
        reject_reason=event.reject_reason,
    )
    return {"event_ref_id": event.event_id, "trade_outcome": outcome.to_dict()}


def test_daily_report_contains_required_sections(tmp_path):
    rejected_rows = _load_jsonl("events_rejected_sample.jsonl")
    accepted_rows = _load_jsonl("events_accepted_sample.jsonl")
    events = [_event_from_row(row, intent="rejected") for row in rejected_rows] + [
        _event_from_row(row, intent="accepted") for row in accepted_rows
    ]
    outcomes = [_outcome_for_event(event, idx) for idx, event in enumerate(events)]

    date_key = "2025-02-28"
    output_dir = tmp_path / "runtime" / "analytics" / "reports" / date_key
    payload = build_daily_intelligence_report(
        date_key,
        events=events,
        outcomes=outcomes,
        attempt_outcome_replay=False,
        output_dir=output_dir,
    )

    md_path = Path(str(payload["daily_report_markdown_path"]))
    assert md_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    assert "## Section 1: What blocked edge yesterday?" in markdown
    assert "## Section 2: What saved you?" in markdown
    assert "## Section 3: Regime notes" in markdown
    assert "## Section 4: Target/SL calibration" in markdown
    assert "## Section 5: Feed quality impact" in markdown
    assert "## Action list" in markdown


def test_session_report_does_not_reuse_date_wide_outcomes(tmp_path, monkeypatch):
    from config import config as cfg

    date_key = "2026-10-01"
    session_dir = tmp_path / "sessions" / "run-a"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(cfg, "OUTCOME_REPLAY_DIR", str(tmp_path / "outcomes"), raising=False)
    date_wide = _default_outcome_path(date_key)
    date_wide.parent.mkdir(parents=True)
    date_wide.write_text("stale-other-source\n", encoding="utf-8")

    session_path = _default_outcome_path(date_key, session_dir)
    assert session_path != date_wide
    status = _ensure_outcomes_available(date_key, attempt_replay=False, session_dir=session_dir)
    assert status["exists"] is False
    assert status["attempted_replay"] is False
    assert str(session_path) == status["path"]


def test_explicit_session_report_uses_only_candidate_journal_events(tmp_path, monkeypatch):
    from core.analytics import daily_report as report_module

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    monkeypatch.setattr(report_module, "discover_session_paths", lambda **_kwargs: [session_dir])
    monkeypatch.setattr(
        report_module,
        "load_session_diagnostics",
        lambda **_kwargs: {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "source_files": [],
            "record_count": 0,
            "malformed_record_count": 0,
            "reason_counts": {},
        },
    )
    monkeypatch.setattr(report_module, "load_session_events", lambda **_kwargs: [])

    def _unexpected_workspace_load(**_kwargs):
        raise AssertionError("session-scoped reports must not load workspace-wide intents")

    monkeypatch.setattr(report_module, "load_trade_intent_events", _unexpected_workspace_load)
    monkeypatch.setattr(
        report_module,
        "_ensure_outcomes_available",
        lambda *_args, **_kwargs: {"path": "scoped.jsonl", "exists": False, "attempted_replay": False,
                                  "replay_success": False, "warning": None},
    )
    payload = build_daily_intelligence_report(
        "2026-10-01",
        session_dir=session_dir,
        output_dir=tmp_path / "report",
        attempt_outcome_replay=False,
    )
    assert payload["header"]["counts"]["events"] == 0


def test_daily_report_includes_executable_shadow_section(tmp_path, monkeypatch: pytest.MonkeyPatch):
    date_key = "2025-02-28"

    def _fake_exec_shadow(date, **kwargs):
        assert date == date_key
        out = Path(str(kwargs["output_path"]))
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": date_key,
            "scope": "executable_review_queue",
            "counts": {
                "scanned_events": 4,
                "eligible_events": 3,
                "simulated_trades": 2,
                "skipped_events": 1,
            },
            "summary": {
                "trades": 2,
                "wins": 1,
                "losses": 1,
                "total_pnl_value": 125.0,
                "ending_equity": 100125.0,
                "max_drawdown_points": 40.0,
            },
            "skip_reasons": {"no_candles": 1},
            "output_path": str(out),
        }
        out.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr("core.analytics.daily_report.build_executable_shadow_portfolio_report", _fake_exec_shadow)

    output_dir = tmp_path / "runtime" / "analytics" / "reports" / date_key
    payload = build_daily_intelligence_report(
        date_key,
        events=[],
        outcomes=[],
        attempt_outcome_replay=False,
        output_dir=output_dir,
    )

    markdown = Path(str(payload["daily_report_markdown_path"])).read_text(encoding="utf-8")
    assert "## Section 6: Executable shadow portfolio" in markdown
    assert "simulated_trades=2" in markdown
    assert "skip_reasons={'no_candles': 1}" in markdown
    assert payload["sections"]["executable_shadow_portfolio"]["simulated_trades"] == 2
    assert payload["analytics_outputs"]["executable_shadow_portfolio"].endswith("executable_shadow_portfolio.json")
