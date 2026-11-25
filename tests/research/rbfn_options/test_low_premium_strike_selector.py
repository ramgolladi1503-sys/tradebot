"""Tests for Low-Premium Strike Selector.

Verifies:
- Accurate mapping to ladder tiers [38, 48, 58, 68, 88, 128]
- Strict point-in-time filtering (eval_time 09:19)
- Nearest expiry filtering
- Candidate dataclass invariants
"""
from __future__ import annotations

import pandas as pd
import pytest

from research.rbfn_options.core.low_premium_strike_selector import (
    PREMIUM_LADDER_TIERS,
    MultiStrikeChainRanker,
    OptionContractCandidate,
    RankedStrikeCandidate,
    select_low_premium_strike,
    select_strike_at_touch,
)


def test_candidate_dataclass_validation():
    cand = OptionContractCandidate(
        date="2026-05-07",
        expiry="2026-05-07",
        strike=22500.0,
        option_type="CE",
        premium_at_eval=58.5,
        matched_tier=58.0,
        distance_to_tier=0.5,
        lot_size=50,
    )
    cand.validate()

    with pytest.raises(ValueError, match="Strike must be positive"):
        OptionContractCandidate(
            date="2026-05-07",
            expiry="2026-05-07",
            strike=-100.0,
            option_type="CE",
            premium_at_eval=58.5,
            matched_tier=58.0,
            distance_to_tier=0.5,
            lot_size=50,
        ).validate()


def test_select_low_premium_strike_nearest_ladder_tier():
    # Synthetic option chain at 09:19
    records = [
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22400.0, "option_type": "CE", "close": 130.0, "lot_size": 50},
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22500.0, "option_type": "CE", "close": 86.5, "lot_size": 50},
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22550.0, "option_type": "CE", "close": 59.2, "lot_size": 50},
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22600.0, "option_type": "CE", "close": 46.8, "lot_size": 50},
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22650.0, "option_type": "CE", "close": 37.1, "lot_size": 50},
    ]
    df = pd.DataFrame(records)

    # 1. Ask for specific tier 58.0
    cand = select_low_premium_strike(df, date="2026-05-07", option_type="CE", target_tier=58.0)
    assert cand is not None
    assert cand.strike == 22550.0
    assert cand.matched_tier == 58.0
    assert abs(cand.premium_at_eval - 59.2) < 1e-4

    # 2. Ask for tier 48.0
    cand_48 = select_low_premium_strike(df, date="2026-05-07", option_type="CE", target_tier=48.0)
    assert cand_48 is not None
    assert cand_48.strike == 22600.0
    assert cand_48.matched_tier == 48.0

    # 3. Ask across all ladder tiers (defaults)
    cand_any = select_low_premium_strike(df, date="2026-05-07", option_type="CE")
    assert cand_any is not None
    assert cand_any.matched_tier in PREMIUM_LADDER_TIERS


def test_select_strike_at_touch_dynamic_point_in_time():
    # Option candles across time
    # Touch occurs at 10:15:00
    records = [
        # 09:19 bars
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22400.0, "option_type": "CE", "close": 120.0, "lot_size": 50},
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22500.0, "option_type": "CE", "close": 85.0, "lot_size": 50},
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22600.0, "option_type": "CE", "close": 55.0, "lot_size": 50},
        # 10:15 bars (at touch, spot has moved, premium decayed/shifted)
        {"timestamp": "2026-05-07 10:15:00", "expiry": "2026-05-07", "strike": 22400.0, "option_type": "CE", "close": 145.0, "lot_size": 50},
        {"timestamp": "2026-05-07 10:15:00", "expiry": "2026-05-07", "strike": 22500.0, "option_type": "CE", "close": 98.0, "lot_size": 50},
        {"timestamp": "2026-05-07 10:15:00", "expiry": "2026-05-07", "strike": 22600.0, "option_type": "CE", "close": 68.2, "lot_size": 50},  # Matches tier 68.0!
        {"timestamp": "2026-05-07 10:15:00", "expiry": "2026-05-07", "strike": 22700.0, "option_type": "CE", "close": 47.9, "lot_size": 50},  # Matches tier 48.0!
        # 10:16 bar (future lookahead bar - must NOT be visible!)
        {"timestamp": "2026-05-07 10:16:00", "expiry": "2026-05-07", "strike": 22700.0, "option_type": "CE", "close": 10.0, "lot_size": 50},
    ]
    df = pd.DataFrame(records)

    cand_touch_48 = select_strike_at_touch(
        contracts_df=df,
        date="2026-05-07",
        option_type="CE",
        touch_timestamp="2026-05-07 10:15:00",
        target_tier=48.0,
    )
    assert cand_touch_48 is not None
    assert cand_touch_48.strike == 22700.0
    assert abs(cand_touch_48.premium_at_eval - 47.9) < 1e-4

    cand_touch_68 = select_strike_at_touch(
        contracts_df=df,
        date="2026-05-07",
        option_type="CE",
        touch_timestamp="2026-05-07 10:15:00",
        target_tier=68.0,
    )
    assert cand_touch_68 is not None
    assert cand_touch_68.strike == 22600.0

    # Ensure future timestamp (10:14) does NOT see 10:15 data
    cand_earlier = select_strike_at_touch(
        contracts_df=df,
        date="2026-05-07",
        option_type="CE",
        touch_timestamp="2026-05-07 10:14:00",
        target_tier=48.0,
    )
    # At 10:14, strike 22700 does not exist yet!
    assert cand_earlier is not None
    assert cand_earlier.strike != 22700.0



def test_select_low_premium_strike_pe_and_expiry_selection():
    records = [
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-07", "strike": 22000.0, "option_type": "PE", "close": 49.0, "lot_size": 50},
        {"timestamp": "2026-05-07 09:19:00", "expiry": "2026-05-14", "strike": 22000.0, "option_type": "PE", "close": 110.0, "lot_size": 50},
    ]
    df = pd.DataFrame(records)

    # Must select nearest expiry (2026-05-07)
    cand = select_low_premium_strike(df, date="2026-05-07", option_type="PE", target_tier=48.0)
    assert cand is not None
    assert cand.expiry == "2026-05-07"
    assert cand.strike == 22000.0


def test_ranked_strike_candidate_validation():
    cand = RankedStrikeCandidate(
        date="2026-05-07",
        expiry="2026-05-07",
        strike=22500.0,
        option_type="CE",
        premium_at_eval=58.5,
        matched_tier=58.0,
        distance_to_tier=0.5,
        lot_size=50,
        bid=58.0,
        ask=59.0,
        spread=1.0,
        spread_pct=1.0 / 58.5,
        composite_score=1.0,
    )
    cand.validate()

    # Invalid bid > ask
    with pytest.raises(ValueError, match="bid.*cannot exceed ask"):
        RankedStrikeCandidate(
            date="2026-05-07",
            expiry="2026-05-07",
            strike=22500.0,
            option_type="CE",
            premium_at_eval=58.5,
            matched_tier=58.0,
            distance_to_tier=0.5,
            lot_size=50,
            bid=60.0,
            ask=58.0,
        ).validate()

    # Negative bid
    with pytest.raises(ValueError, match="bid cannot be negative"):
        RankedStrikeCandidate(
            date="2026-05-07",
            expiry="2026-05-07",
            strike=22500.0,
            option_type="CE",
            premium_at_eval=58.5,
            matched_tier=58.0,
            distance_to_tier=0.5,
            lot_size=50,
            bid=-1.0,
            ask=58.0,
        ).validate()


def test_multi_strike_chain_ranker_causal_and_scoring():
    # Multi-strike option chain snapshot with quotes at 10:15
    records = [
        # Option bars at 10:15
        {
            "timestamp": "2026-05-07 10:15:00",
            "expiry": "2026-05-07",
            "strike": 22500.0,
            "option_type": "CE",
            "close": 88.2,  # Near tier 88.0 (dist 0.2)
            "bid": 88.0,
            "ask": 88.4,    # spread = 0.4
            "lot_size": 50,
        },
        {
            "timestamp": "2026-05-07 10:15:00",
            "expiry": "2026-05-07",
            "strike": 22550.0,
            "option_type": "CE",
            "close": 58.1,  # Near tier 58.0 (dist 0.1)
            "bid": 57.0,
            "ask": 59.2,    # Wide spread = 2.2
            "lot_size": 50,
        },
        {
            "timestamp": "2026-05-07 10:15:00",
            "expiry": "2026-05-07",
            "strike": 22600.0,
            "option_type": "CE",
            "close": 48.05, # Near tier 48.0 (dist 0.05)
            "bid": 48.0,
            "ask": 48.1,    # Tight spread = 0.1
            "lot_size": 50,
        },
        # Future bar at 10:16 (must be strictly ignored by point-in-time filtering)
        {
            "timestamp": "2026-05-07 10:16:00",
            "expiry": "2026-05-07",
            "strike": 22650.0,
            "option_type": "CE",
            "close": 38.0,
            "bid": 37.95,
            "ask": 38.05,
            "lot_size": 50,
        },
    ]
    df = pd.DataFrame(records)

    ranker = MultiStrikeChainRanker(spread_penalty_weight=0.5)

    # 1. Rank chain evaluated at 10:15:00 across all tiers
    ranked = ranker.rank_chain_at_timestamp(
        contracts_df=df,
        date="2026-05-07",
        option_type="CE",
        eval_timestamp="2026-05-07 10:15:00",
        top_k=5,
    )

    # Must contain exactly 3 candidates (future bar at 10:16 excluded)
    assert len(ranked) == 3
    assert all(r.strike != 22650.0 for r in ranked)

    # Strike 22600 has dist 0.05, spread 0.1 -> comp_score = 0.05 + 0.1 * 0.5 = 0.10
    # Strike 22500 has dist 0.20, spread 0.4 -> comp_score = 0.20 + 0.4 * 0.5 = 0.40
    # Strike 22550 has dist 0.10, spread 2.2 -> comp_score = 0.10 + 2.2 * 0.5 = 1.20
    # Therefore order must be: 22600, 22500, 22550
    assert ranked[0].strike == 22600.0
    assert ranked[1].strike == 22500.0
    assert ranked[2].strike == 22550.0

    assert ranked[0].composite_score < ranked[1].composite_score < ranked[2].composite_score

    # 2. Rank with target_tier specified (e.g. 58.0)
    ranked_58 = ranker.rank_chain_at_timestamp(
        contracts_df=df,
        date="2026-05-07",
        option_type="CE",
        eval_timestamp="2026-05-07 10:15:00",
        target_tier=58.0,
        top_k=2,
    )
    assert len(ranked_58) >= 1
    # Closest to 58.0 is 22550 (dist 0.10)
    assert ranked_58[0].strike == 22550.0
    assert ranked_58[0].matched_tier == 58.0

    # 3. Spread filter: max_spread_pct = 0.02 (2%)
    # 22550 spread is 2.2 / 58.1 = ~3.78% > 2% -> must be filtered out
    ranked_tight = ranker.rank_chain_at_timestamp(
        contracts_df=df,
        date="2026-05-07",
        option_type="CE",
        eval_timestamp="2026-05-07 10:15:00",
        max_spread_pct=0.02,
    )
    assert len(ranked_tight) == 2
    assert all(r.strike != 22550.0 for r in ranked_tight)

