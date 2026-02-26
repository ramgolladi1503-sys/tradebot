from __future__ import annotations

from core.shadow_outcomes import build_shadow_row, evaluate_shadow_candidate


class _CandidateStub:
    candidate_id = "blk_test_1"
    timestamp_epoch = 1000.0
    symbol = "NIFTY"
    reason_code = "orb_neutral_blocked"
    direction = "BUY_CALL"
    entry = 100.0
    stop = 95.0
    target = 105.0
    contract = "NIFTY|2026-02-26|25000|CE"


def test_shadow_eval_target_hits_before_stop():
    points = [
        (1001.0, 100.2),
        (1020.0, 103.0),
        (1030.0, 105.2),  # target first
        (1045.0, 94.8),   # stop later, must not override first-hit outcome
    ]

    evaluation = evaluate_shadow_candidate(
        entry=100.0,
        stop=95.0,
        target=105.0,
        direction="BUY_CALL",
        start_ts_epoch=1000.0,
        price_points=points,
        horizons_sec=[300, 900, 1800],
    )

    assert evaluation["outcomes"][300] == "target"
    assert evaluation["outcomes"][900] == "target"
    assert evaluation["outcomes"][1800] == "target"
    assert evaluation["mfe_15m"] is not None and evaluation["mfe_15m"] > 0
    assert evaluation["mae_15m"] is not None
    assert evaluation["pnl_15m"] is not None

    row = build_shadow_row(_CandidateStub(), evaluation)
    assert row["candidate_id"] == "blk_test_1"
    assert row["reason_code"] == "orb_neutral_blocked"
    assert row["outcome_15m"] == "target"
