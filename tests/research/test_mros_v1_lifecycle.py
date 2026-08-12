from datetime import datetime, timezone
import pytest

from research.mros_v1.lifecycle import append_ledger, build_preopen_report, finalize_after_close, record_actual_open, run_research_schedule, score_frozen_models


def state():
    return finalize_after_close("2026-08-12", {name: {"complete": True} for name in ("NIFTY", "BANKNIFTY", "SENSEX")}, "s" * 64)


def test_after_close_scoring_reporting_and_open_binding():
    daily = state()
    scores = score_frozen_models(daily, {name: "m" * 64 for name in ("NIFTY", "BANKNIFTY", "SENSEX")})
    report = build_preopen_report(daily, scores, cutoff=datetime(2026, 8, 12, 9, tzinfo=timezone.utc))
    actual = record_actual_open(report, {name: 1.0 for name in ("NIFTY", "BANKNIFTY", "SENSEX")})
    assert actual["prediction_report_sha256"]


def test_incomplete_state_and_duplicate_ledger_fail_closed():
    with pytest.raises(ValueError, match="INCOMPLETE"):
        finalize_after_close("2026-08-12", {"NIFTY": {"complete": True}}, "s" * 64)
    entry = {"prediction_sha256": "p" * 64}
    ledger = append_ledger((), entry)
    with pytest.raises(ValueError, match="DUPLICATE"):
        append_ledger(ledger, entry)


def test_scheduler_has_no_execution_authority():
    assert run_research_schedule() == "READ_ONLY_SCHEDULE_READY"
    with pytest.raises(ValueError, match="AUTHORITY"):
        run_research_schedule(has_live_authority=True)
