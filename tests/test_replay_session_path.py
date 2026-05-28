from core.replay_session_path import (
    EMPTY_PRICE_PATH,
    INVALID_ENTRY_PRICE,
    MISSING_CANDIDATE_ID,
    SESSION_CLOSE_RISK,
    SESSION_LATE_SESSION,
    SESSION_MIDDAY_CONTINUATION,
    SESSION_OPENING_MOMENTUM,
    SESSION_UNKNOWN,
    TOP_MOVER_OUTSIDE,
    TOP_MOVER_TOP_10,
    TOP_MOVER_TOP_25,
    TOP_MOVER_TOP_50,
    TOP_MOVER_UNKNOWN,
    build_session_path_replay_evidence,
    classify_session_window,
    classify_top_mover_bucket,
)
from core.replay_session_path_report import (
    SESSION_PATH_REPLAY_BLOCKED,
    SESSION_PATH_REPLAY_PASSED,
    build_session_path_replay_report,
)


def test_session_path_replay_calculates_mfe_mae_and_safety_flags():
    evidence = build_session_path_replay_evidence(
        candidate_id="cand-1",
        symbol="NIFTY_CE",
        entry_time="09:40",
        exit_time="15:10",
        entry_price=100,
        price_path=[100, 104, 98, 110, 103],
        target_pct=4,
        top_mover_rank=5,
        relative_strength_percentile=92.5,
        regime_at_entry="UP_HIGH_BULLISH_DEEP_OPENING",
    )

    assert evidence.valid is True
    assert evidence.reason == "OK"
    assert evidence.session_window == SESSION_OPENING_MOMENTUM
    assert evidence.exit_price == 103
    assert evidence.mfe_abs == 10
    assert evidence.mae_abs == -2
    assert evidence.mfe_pct == 10.0
    assert evidence.mae_pct == -2.0
    assert evidence.open_to_close_pct == 3.0
    assert evidence.hit_target_before_close is True
    assert evidence.gave_back_profit is True
    assert evidence.top_mover_bucket == TOP_MOVER_TOP_10
    payload = evidence.to_payload()
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False


def test_target_not_hit_does_not_raise_false_target_flag():
    evidence = build_session_path_replay_evidence(
        candidate_id="cand-2",
        symbol="BANKNIFTY_PE",
        entry_time="11:15",
        exit_time="12:00",
        entry_price=100,
        price_path=[100, 102, 103, 101],
        target_pct=4,
    )

    assert evidence.session_window == SESSION_MIDDAY_CONTINUATION
    assert evidence.mfe_pct == 3.0
    assert evidence.hit_target_before_close is False
    assert evidence.gave_back_profit is False


def test_closed_near_high_and_low_flags_are_deterministic():
    near_high = build_session_path_replay_evidence(
        candidate_id="near-high",
        symbol="NIFTY_CE",
        entry_time="14:25",
        exit_time="15:00",
        entry_price=100,
        price_path=[100, 106, 110, 109],
    )
    near_low = build_session_path_replay_evidence(
        candidate_id="near-low",
        symbol="NIFTY_CE",
        entry_time="15:22",
        exit_time="15:29",
        entry_price=100,
        price_path=[100, 96, 94, 95],
    )

    assert near_high.session_window == SESSION_LATE_SESSION
    assert near_high.closed_near_high is True
    assert near_high.closed_near_low is False
    assert near_low.session_window == SESSION_CLOSE_RISK
    assert near_low.closed_near_low is True
    assert near_low.closed_near_high is False


def test_invalid_entry_price_fails_closed():
    evidence = build_session_path_replay_evidence(
        candidate_id="bad-entry",
        symbol="NIFTY_CE",
        entry_time="09:40",
        exit_time="10:00",
        entry_price=0,
        price_path=[100, 101],
    )

    assert evidence.valid is False
    assert evidence.reason == INVALID_ENTRY_PRICE
    assert evidence.mfe_abs == 0
    assert evidence.hit_target_before_close is False
    assert evidence.read_only is True
    assert evidence.is_order_action is False


def test_empty_price_path_fails_closed():
    evidence = build_session_path_replay_evidence(
        candidate_id="empty-path",
        symbol="NIFTY_CE",
        entry_time="09:40",
        exit_time="10:00",
        entry_price=100,
        price_path=[],
    )

    assert evidence.valid is False
    assert evidence.reason == EMPTY_PRICE_PATH
    assert evidence.entry_price == 100
    assert evidence.exit_price == 0


def test_missing_candidate_id_fails_closed():
    evidence = build_session_path_replay_evidence(
        candidate_id="",
        symbol="NIFTY_CE",
        entry_time="09:40",
        exit_time="10:00",
        entry_price=100,
        price_path=[100, 101],
    )

    assert evidence.valid is False
    assert evidence.reason == MISSING_CANDIDATE_ID
    assert evidence.candidate_id == ""


def test_session_window_classification_boundaries():
    assert classify_session_window("09:40") == SESSION_OPENING_MOMENTUM
    assert classify_session_window("11:15") == SESSION_MIDDAY_CONTINUATION
    assert classify_session_window("14:25") == SESSION_LATE_SESSION
    assert classify_session_window("15:22") == SESSION_CLOSE_RISK
    assert classify_session_window(None) == SESSION_UNKNOWN
    assert classify_session_window("not-a-time") == SESSION_UNKNOWN


def test_top_mover_bucket_classification():
    assert classify_top_mover_bucket(5) == TOP_MOVER_TOP_10
    assert classify_top_mover_bucket(20) == TOP_MOVER_TOP_25
    assert classify_top_mover_bucket(45) == TOP_MOVER_TOP_50
    assert classify_top_mover_bucket(80) == TOP_MOVER_OUTSIDE
    assert classify_top_mover_bucket(None) == TOP_MOVER_UNKNOWN


def test_session_path_report_wires_replay_rows_without_ranking_or_execution():
    report = build_session_path_replay_report(
        [
            {
                "candidate_id": "cand-a",
                "symbol": "NIFTY_CE",
                "entry_timestamp": "2026-05-28T09:45:00+05:30",
                "exit_timestamp": "2026-05-28T15:10:00+05:30",
                "entry_ltp": 100,
                "prices_after_entry": [100, 104, 98, 110, 103],
                "top_mover_rank": 7,
                "regime": "UP_HIGH_BULLISH_DEEP_OPENING",
                "strategy": "breakout",
            }
        ],
        metadata={"source": "unit-test"},
    )

    assert report.status == SESSION_PATH_REPLAY_PASSED
    assert report.candidate_count == 1
    assert report.valid_candidate_count == 1
    assert report.invalid_candidate_count == 0
    assert report.metadata["does_not_rank_candidates"] is True
    assert report.metadata["does_not_change_execution"] is True
    payload = report.to_payload()
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["evidence"][0]["metadata"]["strategy"] == "breakout"
    assert payload["evidence"][0]["mfe_abs"] == 10


def test_session_path_report_blocks_invalid_rows_with_reasons():
    report = build_session_path_replay_report(
        [
            {
                "candidate_id": "",
                "symbol": "NIFTY_CE",
                "entry_time": "09:45",
                "entry_price": 100,
                "price_path": [100, 101],
            },
            {
                "candidate_id": "bad-path",
                "symbol": "BANKNIFTY_PE",
                "entry_time": "11:15",
                "entry_price": 100,
                "price_path": [],
            },
        ]
    )

    assert report.status == SESSION_PATH_REPLAY_BLOCKED
    assert report.candidate_count == 2
    assert report.valid_candidate_count == 0
    assert report.invalid_candidate_count == 2
    assert set(report.reasons) == {MISSING_CANDIDATE_ID, EMPTY_PRICE_PATH}
    assert report.to_payload()["is_order_action"] is False
