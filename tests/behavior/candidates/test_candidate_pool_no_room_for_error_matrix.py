# Edge-purpose matrix for candidate-pool truth under contamination and malformed inputs.
from __future__ import annotations

import pytest

from core.candidate_pool_quality import analyze_candidate_pool, pool_quality_penalty_for_row


pytestmark = [pytest.mark.behavior, pytest.mark.edge, pytest.mark.regression]


def _row(**overrides):
    row = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "movement_type": "COMPRESSION_BREAKOUT",
        "direction": "BUY_CALL",
        "option_type": "CE",
        "signal_direction": "BUY_CALL",
        "regime": "TREND",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_truth_state": "EXEMPLAR",
        "reportable_executable": True,
        "execution_allowed": True,
        "expectancy_status": "KEEP",
        "fallback_used": False,
        "edge_rank_score": 0.8,
        "rank_score": 0.7,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    "rows,expected_reason",
    [
        pytest.param([], "empty_pool", id="empty_input"),
        pytest.param([None, "bad-payload", 42], "empty_pool", id="malformed_input"),
    ],
)
def test_candidate_pool_empty_or_malformed_input_fails_closed(rows, expected_reason):
    """
    Edge purpose:
    Proves junk payloads do not become fake candidate breadth.
    Bug/risk protected:
    Non-candidate garbage being scored as a concentrated but usable pool.
    Expected behavior:
    Empty or malformed input produces an empty fail-closed report.
    """
    report = analyze_candidate_pool(rows)

    assert report.candidate_count == 0
    assert report.quality_score == 0.0
    assert report.readiness_state == "EMPTY"
    assert report.reasons == (expected_reason,)


def test_candidate_pool_detects_duplicate_trade_ids_and_penalizes_quality():
    """
    Edge purpose:
    Proves duplicate trade IDs are visible and degrade pool quality.
    Bug/risk protected:
    Downstream ranking seeing duplicated trade intents as independent edge.
    Expected behavior:
    Duplicate trade IDs are counted and penalized.
    """
    duplicate_pool = analyze_candidate_pool(
        [
            _row(candidate_id="cand-a", trade_id="dup-trade", symbol="NIFTY", strategy_family="breakout"),
            _row(candidate_id="cand-b", trade_id="dup-trade", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="BUY_PUT", option_type="PE", signal_direction="BUY_PUT"),
        ]
    )
    clean_pool = analyze_candidate_pool(
        [
            _row(candidate_id="cand-a", trade_id="trade-a", symbol="NIFTY", strategy_family="breakout"),
            _row(candidate_id="cand-b", trade_id="trade-b", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="BUY_PUT", option_type="PE", signal_direction="BUY_PUT"),
        ]
    )

    assert duplicate_pool.duplicate_trade_id_count == 1
    assert "duplicate_trade_ids" in duplicate_pool.reasons
    assert duplicate_pool.quality_score < clean_pool.quality_score

    penalty, reasons = pool_quality_penalty_for_row(
        _row(candidate_id="cand-a", trade_id="dup-trade"),
        duplicate_pool,
    )
    assert penalty > 0.0
    assert "duplicate_trade_ids" in reasons


@pytest.mark.parametrize(
    "rows,expected_bullish,expected_bearish",
    [
        pytest.param(
            [
                _row(candidate_id="ce-a", trade_id="trade-a", symbol="NIFTY", direction="BUY_CALL", option_type="CE", signal_direction="BUY_CALL"),
                _row(candidate_id="ce-b", trade_id="trade-b", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="BUY_CALL", option_type="CE", signal_direction="BUY_CALL"),
            ],
            2,
            0,
            id="ce_only",
        ),
        pytest.param(
            [
                _row(candidate_id="pe-a", trade_id="trade-a", symbol="NIFTY", direction="BUY_PUT", option_type="PE", signal_direction="BUY_PUT"),
                _row(candidate_id="pe-b", trade_id="trade-b", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="BUY_PUT", option_type="PE", signal_direction="BUY_PUT"),
            ],
            0,
            2,
            id="pe_only",
        ),
    ],
)
def test_candidate_pool_one_sided_option_skew_is_visible(rows, expected_bullish, expected_bearish):
    """
    Edge purpose:
    Proves one-sided CE-only or PE-only pools are flagged as directional skew.
    Bug/risk protected:
    Cosmetic row count being misread as balanced opportunity coverage.
    Expected behavior:
    One-sided pools retain exposure counts and one-sided reasons.
    """
    report = analyze_candidate_pool(rows)

    assert report.bullish_count == expected_bullish
    assert report.bearish_count == expected_bearish
    assert "one_sided_direction_coverage" in report.reasons


def test_candidate_pool_stale_candidates_stay_blocked_and_non_executable():
    """
    Edge purpose:
    Proves stale candidates never count as executable pool breadth.
    Bug/risk protected:
    Recovery-blocked candidates leaking into ranking as live opportunities.
    Expected behavior:
    Stale candidates increase blocked count and keep executable count at zero.
    """
    report = analyze_candidate_pool(
        [
            _row(
                candidate_id="stale-1",
                trade_id="stale-1",
                execution_truth_state="RECOVERY_BLOCKED",
                permission="BLOCK",
                final_action="BLOCK",
                execution_allowed=False,
                reportable_executable=False,
                blockers=["STALE_OPTION_LTP", "WS_DISCONNECTED"],
            )
        ]
    )

    assert report.blocked_count == 1
    assert report.executable_count == 0
    assert "no_executable_candidates" in report.reasons


def test_candidate_pool_quality_is_stable_under_input_reorder():
    """
    Edge purpose:
    Proves pool analysis is deterministic under input reorder.
    Bug/risk protected:
    Non-deterministic readiness or scoring when generators return the same rows in different order.
    Expected behavior:
    Counts, reasons, and scores remain identical.
    """
    rows = [
        _row(candidate_id="cand-a", trade_id="trade-a", symbol="NIFTY", strategy_family="breakout", direction="BUY_CALL"),
        _row(candidate_id="cand-b", trade_id="trade-b", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="BUY_PUT", option_type="PE", signal_direction="BUY_PUT"),
        _row(candidate_id="cand-c", trade_id="trade-c", symbol="FINNIFTY", strategy_family="range", direction="RANGE", signal_direction="RANGE", regime="RANGE"),
    ]

    first = analyze_candidate_pool(rows).to_dict()
    second = analyze_candidate_pool(list(reversed(rows))).to_dict()
    first.pop("generated_epoch", None)
    second.pop("generated_epoch", None)

    assert first == second
