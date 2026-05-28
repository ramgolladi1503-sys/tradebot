from core.strategy_replay_proof_pack import (
    NO_STRATEGY_REPLAY_INPUTS,
    STRATEGY_REPLAY_PROOF_BLOCKED,
    STRATEGY_REPLAY_PROOF_PASSED,
    STRATEGY_REPLAY_PROOF_PACK_SOURCE,
    build_strategy_replay_proof_pack,
)


def healthy_feed_payload():
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


def test_strategy_replay_proof_pack_combines_all_layers_as_read_only_evidence():
    pack = build_strategy_replay_proof_pack(
        session_replay_candidates=[
            {
                "candidate_id": "cand-1",
                "symbol": "NIFTY",
                "entry_time": "09:45",
                "exit_time": "15:10",
                "entry_price": 100,
                "price_path": [100, 104, 98, 110, 103],
                "strategy": "breakout",
                "regime": "UP_HIGH_BULLISH_DEEP_OPENING",
            }
        ],
        feed_fault_scenarios=[
            {
                "scenario_id": "clear-feed",
                "candidate_id": "cand-1",
                "symbol": "NIFTY",
                "feed_payload": healthy_feed_payload(),
                "expected_block": False,
                "strategy": "breakout",
            }
        ],
        metadata={"suite": "edge-93"},
    )

    assert pack.status == STRATEGY_REPLAY_PROOF_PASSED
    assert pack.strategy_count == 1
    assert pack.passed_strategy_count == 1
    assert pack.blocked_strategy_count == 0
    assert pack.candidate_count == 1
    assert pack.valid_candidate_count == 1
    assert pack.invalid_candidate_count == 0
    assert pack.feed_blocked_count == 0
    assert pack.reasons == ()
    assert pack.metadata["does_not_rank_candidates"] is True
    assert pack.metadata["does_not_select_strategies"] is True
    assert pack.metadata["does_not_change_execution"] is True
    assert pack.metadata["does_not_wire_runtime"] is True
    assert pack.metadata["does_not_wire_dashboard"] is True

    payload = pack.to_payload()
    assert payload["source"] == STRATEGY_REPLAY_PROOF_PACK_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["regime_replay"]["read_only"] is True
    assert payload["session_path_replay"]["read_only"] is True
    assert payload["feed_fault_replay"]["read_only"] is True
    assert payload["strategy_summaries"][0]["strategy_id"] == "breakout"
    assert payload["strategy_summaries"][0]["status"] == "PASSED"
    assert payload["strategy_summaries"][0]["metadata"]["candidate_ids"] == ["cand-1"]


def test_strategy_replay_proof_pack_blocks_feed_fault_without_hiding_actual_fault():
    blocked_payload = healthy_feed_payload()
    blocked_payload["effective_ws_connected"] = False

    pack = build_strategy_replay_proof_pack(
        session_replay_candidates=[
            {
                "candidate_id": "cand-feed-blocked",
                "symbol": "NIFTY",
                "entry_time": "10:00",
                "exit_time": "15:10",
                "entry_price": 100,
                "price_path": [100, 102, 103],
                "strategy": "vwap",
            }
        ],
        feed_fault_scenarios=[
            {
                "scenario_id": "ws-disconnect",
                "candidate_id": "cand-feed-blocked",
                "symbol": "NIFTY",
                "feed_payload": blocked_payload,
                "expected_block": True,
                "strategy": "vwap",
            }
        ],
    )

    assert pack.status == STRATEGY_REPLAY_PROOF_BLOCKED
    assert pack.strategy_count == 1
    assert pack.blocked_strategy_count == 1
    assert pack.feed_blocked_count == 1
    assert "feed_fault:WEBSOCKET_DISCONNECTED" in pack.reasons

    summary = pack.strategy_summaries[0]
    assert summary.strategy_id == "vwap"
    assert summary.status == "BLOCKED"
    assert summary.feed_blocked_count == 1
    assert "feed_fault:WEBSOCKET_DISCONNECTED" in summary.reasons


def test_strategy_replay_proof_pack_blocks_invalid_session_path_rows():
    pack = build_strategy_replay_proof_pack(
        session_replay_candidates=[
            {
                "candidate_id": "bad-path",
                "symbol": "BANKNIFTY",
                "entry_time": "11:15",
                "entry_price": 100,
                "price_path": [],
                "strategy": "mean_reversion",
            }
        ],
        feed_fault_scenarios=[
            {
                "scenario_id": "clear-feed",
                "candidate_id": "bad-path",
                "symbol": "BANKNIFTY",
                "feed_payload": healthy_feed_payload(),
                "expected_block": False,
                "strategy": "mean_reversion",
            }
        ],
    )

    assert pack.status == STRATEGY_REPLAY_PROOF_BLOCKED
    assert pack.invalid_candidate_count == 1
    assert "EMPTY_PRICE_PATH" in pack.reasons
    assert pack.strategy_summaries[0].strategy_id == "mean_reversion"
    assert pack.strategy_summaries[0].status == "BLOCKED"


def test_strategy_replay_proof_pack_groups_multiple_strategies_deterministically():
    pack = build_strategy_replay_proof_pack(
        session_replay_candidates=[
            {
                "candidate_id": "cand-breakout",
                "symbol": "NIFTY",
                "entry_time": "09:45",
                "entry_price": 100,
                "price_path": [100, 105],
                "strategy": "breakout",
            },
            {
                "candidate_id": "cand-vwap",
                "symbol": "NIFTY",
                "entry_time": "11:45",
                "entry_price": 100,
                "price_path": [100, 101],
                "strategy": "vwap",
            },
        ],
        feed_fault_scenarios=[
            {
                "scenario_id": "breakout-feed",
                "candidate_id": "cand-breakout",
                "symbol": "NIFTY",
                "feed_payload": healthy_feed_payload(),
                "expected_block": False,
                "strategy": "breakout",
            },
            {
                "scenario_id": "vwap-feed",
                "candidate_id": "cand-vwap",
                "symbol": "NIFTY",
                "feed_payload": healthy_feed_payload(),
                "expected_block": False,
                "strategy": "vwap",
            },
        ],
    )

    assert [summary.strategy_id for summary in pack.strategy_summaries] == ["breakout", "vwap"]
    assert pack.strategy_count == 2
    assert pack.candidate_count == 2
    assert pack.passed_strategy_count == 2


def test_strategy_replay_proof_pack_fails_closed_without_strategy_inputs():
    pack = build_strategy_replay_proof_pack()

    assert pack.status == STRATEGY_REPLAY_PROOF_BLOCKED
    assert pack.strategy_count == 0
    assert pack.candidate_count == 0
    assert pack.reasons == (NO_STRATEGY_REPLAY_INPUTS,)
    payload = pack.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
