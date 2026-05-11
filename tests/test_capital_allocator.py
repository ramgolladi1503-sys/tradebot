from __future__ import annotations

from core.capital_allocator import allocate_capital_slots


def _candidate(
    trade_id: str,
    *,
    symbol: str = "NIFTY",
    theme: str = "breakout",
    opportunity_score: float = 0.7,
    capital_at_risk: float = 10.0,
    selected_for_execution: bool = True,
) -> dict:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "strategy": "UNIT",
        "selected_for_execution": selected_for_execution,
        "execution_allowed": True,
        "tradable": True,
        "execution_entry": 121.5,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "opportunity_score": opportunity_score,
        "capital_at_risk": capital_at_risk,
        "size_mult": 0.5,
        "opt_ltp": 121.4,
        "current_ltp": 121.4,
        "best_bid": 121.2,
        "best_ask": 121.5,
        "spread_pct": 0.0025,
        "liquidity_score": 0.82,
        "quote_age_sec": 0.3,
        "max_quote_age_sec": 2.0,
        "quote_source": "live_broker",
        "spread_source": "live_book",
        "liquidity_source": "live_book",
        "contract_exact_match": True,
        "source_flags": {
            "candidate_origin": {
                "setup_family": theme,
            }
        },
    }


def test_same_theme_candidates_do_not_all_allocate():
    allocated = allocate_capital_slots(
        [
            _candidate("T-1", theme="breakout", opportunity_score=0.82),
            _candidate("T-2", theme="breakout", opportunity_score=0.76),
            _candidate("T-3", theme="breakout", opportunity_score=0.71),
        ],
        max_slots=3,
        per_symbol_cap=3,
        per_theme_cap=1,
        capital_budget_cap=None,
        minimum_quality_threshold=0.0,
        replacement_enabled=False,
        replacement_min_delta=0.03,
    )

    assert allocated[0]["slot_id"] == "slot-1"
    assert allocated[1]["slot_id"] is None
    assert allocated[2]["slot_id"] is None
    assert allocated[1]["allocation_reason"] == "deferred_per_theme_cap"
    assert allocated[2]["allocation_reason"] == "deferred_per_theme_cap"


def test_better_late_candidate_can_replace_weaker_one():
    allocated = allocate_capital_slots(
        [
            _candidate("T-WEAK", theme="breakout", opportunity_score=0.61),
            _candidate("T-STRONG", theme="breakout", opportunity_score=0.83),
        ],
        max_slots=1,
        per_symbol_cap=1,
        per_theme_cap=1,
        capital_budget_cap=None,
        minimum_quality_threshold=0.0,
        replacement_enabled=True,
        replacement_min_delta=0.05,
    )

    assert allocated[0]["slot_id"] is None
    assert allocated[0]["allocation_reason"] == "replaced_by_better_candidate:T-STRONG"
    assert allocated[0]["selected_for_execution"] is False
    assert allocated[1]["slot_id"] == "slot-1"
    assert allocated[1]["allocation_reason"] == "allocated"
    assert allocated[1]["selected_for_execution"] is True


def test_allocation_respects_slot_and_budget_caps():
    allocated = allocate_capital_slots(
        [
            _candidate("T-A", opportunity_score=0.84, capital_at_risk=6.0),
            _candidate("T-B", symbol="BANKNIFTY", theme="pullback", opportunity_score=0.80, capital_at_risk=6.0),
            _candidate("T-C", symbol="SENSEX", theme="continuation", opportunity_score=0.78, capital_at_risk=4.0),
        ],
        max_slots=2,
        per_symbol_cap=1,
        per_theme_cap=2,
        capital_budget_cap=10.0,
        minimum_quality_threshold=0.0,
        replacement_enabled=False,
        replacement_min_delta=0.03,
    )

    assert allocated[0]["slot_id"] == "slot-1"
    assert allocated[0]["capital_assigned"] == 6.0
    assert allocated[1]["slot_id"] is None
    assert allocated[1]["allocation_reason"] == "deferred_budget_cap"
    assert allocated[2]["slot_id"] == "slot-2"
    assert allocated[2]["capital_assigned"] == 4.0
