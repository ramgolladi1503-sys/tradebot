from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from research.opening_range_retest.replay_oracle import evaluate_oracle_direction
from strategies.movement.opening_range_breakout import STRATEGY_ID

IST = ZoneInfo("Asia/Kolkata")
SESSION_DATE = "2026-07-14"
SESSION_OPEN = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
OPENING_RANGE_HIGH = 22600.0
OPENING_RANGE_LOW = 22500.0

OPENING_RANGE_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (0, 22540.0, 22558.0, 22532.0, 22550.0),
    (1, 22549.0, 22560.0, 22535.0, 22545.0),
    (2, 22544.0, 22550.0, 22518.0, 22528.0),
    (3, 22527.0, 22540.0, 22510.0, 22518.0),
    (4, 22517.0, 22530.0, 22505.0, 22512.0),
    (5, 22511.0, 22524.0, 22502.0, 22515.0),
    (6, 22515.0, 22528.0, 22503.0, 22520.0),
    (7, 22520.0, 22526.0, 22500.0, 22508.0),
    (8, 22508.0, 22522.0, 22504.0, 22518.0),
    (9, 22518.0, 22535.0, 22510.0, 22529.0),
    (10, 22529.0, 22542.0, 22520.0, 22536.0),
    (11, 22536.0, 22548.0, 22524.0, 22540.0),
    (12, 22540.0, 22552.0, 22530.0, 22544.0),
    (13, 22544.0, 22560.0, 22538.0, 22552.0),
    (14, 22552.0, OPENING_RANGE_HIGH, 22540.0, 22556.0),
)

CALL_VALID_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),
    (16, 22608.0, 22609.0, 22596.0, 22600.0),
    (17, 22600.0, 22611.0, 22598.0, 22603.0),
    (18, 22603.0, 22618.0, 22601.0, 22614.0),
)

PUT_VALID_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22558.0, 22488.0, 22492.0),
    (16, 22492.0, 22494.0, 22486.0, 22490.0),
    (17, 22490.0, 22502.0, 22488.0, 22498.0),
    (18, 22498.0, 22499.0, 22482.0, 22484.0),
)


def _bar(offset_minutes: int, open_: float, high: float, low: float, close: float) -> dict[str, object]:
    start = SESSION_OPEN + timedelta(minutes=offset_minutes)
    end = start + timedelta(minutes=1)
    return {
        "symbol": "NIFTY",
        "session_date": SESSION_DATE,
        "timeframe": "1m",
        "bar_start_timestamp": start.isoformat(),
        "bar_end_timestamp": end.isoformat(),
        "ts": start.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
        "source": "unit_test",
        "source_timestamp": end.isoformat(),
        "receipt_timestamp": (end + timedelta(seconds=1)).isoformat(),
        "is_complete": True,
    }


def _bars(rows: tuple[tuple[int, float, float, float, float], ...]) -> tuple[dict[str, object], ...]:
    return tuple(_bar(*row) for row in rows)


def _expected_setup_id(
    *,
    symbol: str,
    session_date: str,
    direction: str,
    boundary_type: str,
    normalized_boundary_value: float,
    breakout_timestamp: str,
) -> str:
    payload = {
        "strategy_id": STRATEGY_ID,
        "symbol": symbol,
        "session_date": session_date,
        "direction": direction,
        "boundary_type": boundary_type,
        "normalized_boundary_value": normalized_boundary_value,
        "breakout_timestamp": breakout_timestamp,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def test_call_oracle_exposes_full_temporal_identity() -> None:
    oracle = evaluate_oracle_direction(list(_bars(OPENING_RANGE_ROWS + CALL_VALID_ROWS)), direction="BUY_CALL")
    assert oracle is not None
    assert oracle.temporal_identity() == {
        "strategy_id": STRATEGY_ID,
        "symbol": "NIFTY",
        "session_date": "2026-07-14",
        "direction": "BUY_CALL",
        "boundary_type": "ORB_HIGH",
        "normalized_boundary_value": OPENING_RANGE_HIGH,
        "breakout_timestamp": "2026-07-14T09:31:00+05:30",
        "retest_timestamp": "2026-07-14T09:32:00+05:30",
        "continuation_timestamp": "2026-07-14T09:34:00+05:30",
        "proposal_ready_at_iso": "2026-07-14T09:34:00+05:30",
        "setup_id": _expected_setup_id(
            symbol="NIFTY",
            session_date="2026-07-14",
            direction="BUY_CALL",
            boundary_type="ORB_HIGH",
            normalized_boundary_value=OPENING_RANGE_HIGH,
            breakout_timestamp="2026-07-14T09:31:00+05:30",
        ),
    }


def test_put_oracle_matches_full_temporal_identity() -> None:
    oracle = evaluate_oracle_direction(list(_bars(OPENING_RANGE_ROWS + PUT_VALID_ROWS)), direction="BUY_PUT")
    assert oracle is not None
    assert oracle.matches_setup_identity(
        {
            "strategy_id": STRATEGY_ID,
            "symbol": "NIFTY",
            "session_date": "2026-07-14",
            "direction": "BUY_PUT",
            "boundary_type": "ORB_LOW",
            "normalized_boundary_value": OPENING_RANGE_LOW,
            "breakout_timestamp": "2026-07-14T09:31:00+05:30",
            "retest_timestamp": "2026-07-14T09:33:00+05:30",
            "continuation_timestamp": "2026-07-14T09:34:00+05:30",
            "proposal_ready_at_iso": "2026-07-14T09:34:00+05:30",
            "setup_id": _expected_setup_id(
                symbol="NIFTY",
                session_date="2026-07-14",
                direction="BUY_PUT",
                boundary_type="ORB_LOW",
                normalized_boundary_value=OPENING_RANGE_LOW,
                breakout_timestamp="2026-07-14T09:31:00+05:30",
            ),
        }
    )


def test_oracle_reconciliation_rejects_backdated_breakout_with_same_proposal_timestamp() -> None:
    oracle = evaluate_oracle_direction(list(_bars(OPENING_RANGE_ROWS + CALL_VALID_ROWS)), direction="BUY_CALL")
    assert oracle is not None
    forged_identity = dict(oracle.temporal_identity())
    forged_identity["breakout_timestamp"] = "2026-07-14T09:30:00+05:30"
    assert forged_identity["proposal_ready_at_iso"] == oracle.proposal_ready_at_iso
    assert oracle.matches_setup_identity(forged_identity) is False


def test_oracle_reconciliation_rejects_setup_id_drift_even_when_timestamps_match() -> None:
    oracle = evaluate_oracle_direction(list(_bars(OPENING_RANGE_ROWS + CALL_VALID_ROWS)), direction="BUY_CALL")
    assert oracle is not None
    forged_identity = dict(oracle.temporal_identity())
    forged_identity["setup_id"] = "deadbeef"
    assert oracle.matches_setup_identity(forged_identity) is False
