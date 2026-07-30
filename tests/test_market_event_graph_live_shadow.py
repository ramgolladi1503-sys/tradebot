import json

from core.market_event_graph_breadth_producer import (
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
)
from core.market_event_graph_live_shadow import (
    ACCEPTED,
    CampaignConfig,
    RuntimeState,
    classify_interval,
    independent_audit,
    run_campaign,
)


def _returns(negative_count: int, total: int = 50, value: float = 0.001):
    return [-value] * negative_count + [value] * (total - negative_count)


def _bar(ts_epoch, source_end, negative_count, index_ret1, *, completed=True, session="2026-07-30"):
    return {
        "ts_epoch": ts_epoch,
        "source_bar_end_epoch": source_end,
        "session_date": session,
        "index_ret1": index_ret1,
        "constituent_ret1": _returns(negative_count),
        "completed": completed,
    }


def _metadata():
    return {
        **frozen_threshold_metadata(),
        "market_event_graph_runtime_state": initial_market_event_graph_runtime_state("2026-07-30"),
        "expected_constituents": 50,
        "index_source_bar_end_epoch": 270.0,
        "completed_constituent_bars": [
            _bar(100.0, 90.0, 40, -0.001),
            _bar(160.0, 150.0, 25, -0.004),
            _bar(220.0, 210.0, 5, 0.001),
            _bar(280.0, 270.0, 20, 0.001),
        ],
        "nifty_level": 24950.0,
        "selected_expiry": "2026-08-06",
        "selected_ce_strike": 25000,
        "instrument_identifier": "NFO|TESTCE",
        "bid": 120.0,
        "ask": 121.0,
        "ltp": 120.5,
        "spread": 1.0,
        "spread_pct": 0.0083,
        "quote_timestamp": "2026-07-30T09:20:00+05:30",
        "quote_age": 1.0,
        "depth": 1500,
        "volume": 10000,
        "open_interest": 500000,
        "fallback_used": False,
        "quote_source": "captured_runtime",
    }


def _runtime():
    return RuntimeState(
        session_date="2026-07-30",
        producer_state=initial_market_event_graph_runtime_state("2026-07-30"),
    )


def test_classifies_completed_synchronized_interval_as_accepted():
    interval = classify_interval(_metadata(), _runtime(), CampaignConfig(session_date="2026-07-30"))

    assert interval["producer_status"] == ACCEPTED
    assert interval["valid_constituents"] == 50
    assert interval["metadata_injected"] is True
    assert interval["runtime_state_valid"] is True
    assert interval["is_order_action"] is False
    assert interval["broker_api_called"] is False
    assert interval["allowed_for_live_execution"] is False


def test_rejects_partial_insufficient_stale_and_misaligned_intervals():
    partial = _metadata()
    partial["completed_constituent_bars"][-1]["completed"] = False
    assert classify_interval(partial, _runtime(), CampaignConfig())["producer_status"] == "PARTIAL_INTERVAL"

    low_coverage = _metadata()
    low_coverage["completed_constituent_bars"][-1]["constituent_ret1"] = _returns(10, total=20)
    assert classify_interval(low_coverage, _runtime(), CampaignConfig())["producer_status"] == "INSUFFICIENT_COVERAGE"

    stale = _metadata()
    stale["stale_constituents"] = ["NIFTY_TEST"]
    assert classify_interval(stale, _runtime(), CampaignConfig())["producer_status"] == "STALE_CONSTITUENT"

    misaligned = _metadata()
    misaligned["index_source_bar_end_epoch"] = 999.0
    assert classify_interval(misaligned, _runtime(), CampaignConfig())["producer_status"] == "TIMESTAMP_MISALIGNMENT"


def test_rejects_duplicate_non_monotonic_and_session_drift():
    runtime = _runtime()
    first = classify_interval(_metadata(), runtime, CampaignConfig())
    assert first["producer_status"] == ACCEPTED
    runtime.last_ts_epoch = first["ts_epoch"]
    runtime.last_source_bar_end_epoch = first["source_bar_end_epoch"]
    runtime.accepted_interval_keys.add((first["session_date"], first["source_bar_end_epoch"]))
    assert classify_interval(_metadata(), runtime, CampaignConfig())["producer_status"] == "NON_MONOTONIC_TS"

    drift = _metadata()
    drift["completed_constituent_bars"][-1]["session_date"] = "2026-07-31"
    assert classify_interval(drift, _runtime(), CampaignConfig())["producer_status"] == "SESSION_MISMATCH"


def test_run_campaign_writes_shadow_ledgers_and_independent_audit(tmp_path):
    reports = run_campaign(
        [_metadata()],
        tmp_path,
        config=CampaignConfig(session_date="2026-07-30", observation_mode="REPLAY"),
        universe={
            "source": "test_manifest",
            "source_timestamp": "2026-07-30T00:00:00+05:30",
            "constituent_count": 50,
            "instrument_identifiers": ["NFO|TEST"] * 50,
            "index_instrument_identifier": "NSE_INDEX|Nifty 50",
            "inactive_or_missing_instruments": [],
            "universe_sha256": "test",
        },
    )

    assert reports["stage_a"]["verdict"] == "INSUFFICIENT_LIVE_BREADTH_EVIDENCE"
    assert reports["stage_b"]["verdict"] == "PASS_GRAPH_FORWARD_SHADOW_CORRECTNESS"
    assert reports["independent_audit"]["verdict"] == "PASS_STAGE_A_B_INDEPENDENT_AUDIT"

    candidate_rows = [
        json.loads(line)
        for line in (tmp_path / "candidate_stage_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {row["entered_stage"] for row in candidate_rows} >= {
        "breadth_producer",
        "TradeBuilder",
        "Phase 1",
        "Phase 2",
        "ranking",
        "UI/dashboard",
        "mock_order_intent",
        "paper_reconciliation",
    }
    assert all(row["broker_api_called"] is False for row in candidate_rows)
    assert all(row["is_order_action"] is False for row in candidate_rows)
    assert all(row["allowed_for_live_execution"] is False for row in candidate_rows)


def test_fallback_quote_is_advisory_only(tmp_path):
    metadata = _metadata()
    metadata["fallback_used"] = True
    run_campaign([metadata], tmp_path, config=CampaignConfig(session_date="2026-07-30"))

    quote = json.loads((tmp_path / "quote_observation_ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert quote["fallback_used"] is True
    assert quote["advisory"] is True
    assert quote["executable"] is False
    assert independent_audit(tmp_path)["verdict"] == "PASS_STAGE_A_B_INDEPENDENT_AUDIT"
