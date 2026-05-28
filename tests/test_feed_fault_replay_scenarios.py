from core.feed_fault_replay_scenarios import (
    FEED_FAULT_REPLAY_BLOCKED,
    FEED_FAULT_REPLAY_PASSED,
    INVALID_FEED_PAYLOAD,
    MISSING_CANDIDATE_ID,
    build_feed_fault_replay_evidence,
    build_feed_fault_replay_report,
)


def healthy_payload():
    return {
        "feed_ok": True,
        "effective_ws_connected": True,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE"},
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 1.0,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
    }


def test_healthy_feed_replay_scenario_stays_clear_and_read_only():
    evidence = build_feed_fault_replay_evidence(
        scenario_id="healthy-feed",
        candidate_id="cand-1",
        symbol="NIFTY",
        feed_payload=healthy_payload(),
        expected_block=False,
    )

    assert evidence.valid is True
    assert evidence.feed_ok is True
    assert evidence.hold_active is False
    assert evidence.replay_should_block is False
    assert evidence.fault_type == "HEALTHY_FEED"
    assert evidence.is_order_action is False
    assert evidence.broker_api_called is False
    assert evidence.live_order_action is False
    assert evidence.broker_order_action is False

    payload = evidence.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_websocket_disconnect_blocks_replay_scenario():
    payload = healthy_payload()
    payload["effective_ws_connected"] = False

    evidence = build_feed_fault_replay_evidence(
        scenario_id="ws-disconnect",
        candidate_id="cand-2",
        symbol="NIFTY",
        feed_payload=payload,
        expected_block=True,
    )

    assert evidence.valid is True
    assert evidence.feed_ok is False
    assert evidence.hold_active is True
    assert evidence.replay_should_block is True
    assert evidence.fault_type == "WEBSOCKET_DISCONNECTED"
    assert "websocket_disconnected" in evidence.feed_reasons
    assert "feed_health_hold" in evidence.blockers


def test_stale_ltp_and_depth_block_replay_scenario():
    payload = healthy_payload()
    payload["last_tick_age_sec"] = 10.0
    payload["last_depth_age_sec"] = 12.0

    evidence = build_feed_fault_replay_evidence(
        scenario_id="stale-ltp-depth",
        candidate_id="cand-3",
        symbol="NIFTY",
        feed_payload=payload,
        expected_block=True,
    )

    assert evidence.valid is True
    assert evidence.replay_should_block is True
    assert "ltp_ticks_stale" in evidence.feed_reasons
    assert "depth_ticks_stale" in evidence.feed_reasons
    assert evidence.fault_type == "LTP_TICKS_STALE"


def test_option_feed_block_reason_blocks_symbol_replay():
    payload = healthy_payload()
    payload["option_feed_block_reason_by_symbol"] = {"NIFTY": "STALE_CHAIN"}
    payload["option_last_tick_age_by_symbol"] = {"NIFTY": 0.4}

    evidence = build_feed_fault_replay_evidence(
        scenario_id="option-feed-blocked",
        candidate_id="cand-4",
        symbol="NIFTY",
        feed_payload=payload,
        expected_block=True,
    )

    assert evidence.valid is True
    assert evidence.replay_should_block is True
    assert "NIFTY:option_feed_blocked" in evidence.feed_reasons
    assert evidence.fault_type == "OPTION_FEED_BLOCKED"


def test_blank_candidate_id_fails_closed():
    evidence = build_feed_fault_replay_evidence(
        scenario_id="blank-candidate",
        candidate_id="",
        symbol="NIFTY",
        feed_payload=healthy_payload(),
    )

    assert evidence.valid is False
    assert evidence.reason == MISSING_CANDIDATE_ID
    assert evidence.replay_should_block is True
    assert evidence.hold_active is True


def test_invalid_feed_payload_fails_closed():
    evidence = build_feed_fault_replay_evidence(
        scenario_id="invalid-payload",
        candidate_id="cand-5",
        symbol="NIFTY",
        feed_payload=None,
    )

    assert evidence.valid is False
    assert evidence.reason == INVALID_FEED_PAYLOAD
    assert evidence.replay_should_block is True
    assert evidence.hold_active is True


def test_expectation_mismatch_marks_invalid_without_hiding_actual_block():
    payload = healthy_payload()
    payload["feed_ok"] = False

    evidence = build_feed_fault_replay_evidence(
        scenario_id="mismatch",
        candidate_id="cand-6",
        symbol="NIFTY",
        feed_payload=payload,
        expected_block=False,
    )

    assert evidence.valid is False
    assert evidence.reason == "FEED_FAULT_EXPECTATION_MISMATCH"
    assert evidence.replay_should_block is True
    assert evidence.hold_active is True


def test_feed_fault_replay_report_summarizes_blocked_and_clear_scenarios():
    blocked_payload = healthy_payload()
    blocked_payload["effective_ws_connected"] = False

    report = build_feed_fault_replay_report(
        [
            {
                "scenario_id": "clear",
                "candidate_id": "cand-7",
                "symbol": "NIFTY",
                "feed_payload": healthy_payload(),
                "expected_block": False,
                "strategy": "breakout",
            },
            {
                "scenario_id": "blocked",
                "candidate_id": "cand-8",
                "symbol": "NIFTY",
                "feed_payload": blocked_payload,
                "expected_block": True,
            },
        ],
        metadata={"suite": "edge-92"},
    )

    assert report.status == FEED_FAULT_REPLAY_BLOCKED
    assert report.scenario_count == 2
    assert report.blocked_scenario_count == 1
    assert report.clear_scenario_count == 1
    assert report.invalid_scenario_count == 0
    assert report.metadata["does_not_rank_candidates"] is True
    assert report.metadata["does_not_change_execution"] is True

    payload = report.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["evidence"][0]["candidate_id"] == "cand-7"
    assert payload["evidence"][0]["replay_should_block"] is False
    assert payload["evidence"][1]["candidate_id"] == "cand-8"
    assert payload["evidence"][1]["replay_should_block"] is True


def test_feed_fault_replay_report_passes_when_all_scenarios_are_clear():
    report = build_feed_fault_replay_report(
        [
            {
                "scenario_id": "clear-only",
                "candidate_id": "cand-9",
                "symbol": "NIFTY",
                "feed_payload": healthy_payload(),
                "expected_block": False,
            }
        ]
    )

    assert report.status == FEED_FAULT_REPLAY_PASSED
    assert report.blocked_scenario_count == 0
    assert report.clear_scenario_count == 1
    assert report.invalid_scenario_count == 0
