from __future__ import annotations

from datetime import datetime

from config import config as cfg
from core.opportunity_engine import (
    annotate_ranked_opportunities,
    annotate_relative_opportunity_ranks,
    select_top_opportunities,
    select_best_opportunity,
)
from core.trade_schema import Trade


def _trade(
    *,
    trade_id: str,
    confidence: float,
    builder_confidence: float,
    permission_confidence: float,
    gating_final_confidence: float,
    confluence: float,
    bid: float,
    ask: float,
    ltp: float,
    volume: float,
    quote_age_sec: float,
    execution_allowed: bool,
    tradable: bool,
    execution_entry: float | None,
    execution_entry_status: str,
    execution_entry_source: str,
    display_entry: float | None,
    symbol: str = "NIFTY",
    size_mult: float = 1.0,
    rank_score: float | None = None,
) -> Trade:
    normalized_symbol = str(symbol).strip().upper() or "NIFTY"
    return Trade(
        trade_id=trade_id,
        timestamp=datetime(2026, 3, 12, 10, 0, 0),
        symbol=normalized_symbol,
        instrument="OPT",
        instrument_token=12345,
        strike=23850,
        expiry="2026-03-17",
        side="BUY",
        entry_price=121.5,
        stop_loss=110.0,
        target=145.0,
        qty=1,
        capital_at_risk=11.5,
        expected_slippage=0.2,
        confidence=confidence,
        strategy="UNIT",
        regime="TREND",
        builder_confidence=builder_confidence,
        permission_confidence=permission_confidence,
        gating_final_confidence=gating_final_confidence,
        rank_score=rank_score,
        sizing_confluence_score=confluence,
        volume=volume,
        quote_age_sec=quote_age_sec,
        execution_allowed=execution_allowed,
        tradable=tradable,
        execution_entry=execution_entry,
        execution_entry_status=execution_entry_status,
        execution_entry_source=execution_entry_source,
        display_entry=display_entry,
        display_entry_status="displayable" if display_entry is not None else "missing",
        display_entry_source="ask" if display_entry is not None else "none",
        entry_reason="unit_test",
        entry_price_source="ask",
        expected_entry=display_entry,
        expected_entry_source="ask" if display_entry is not None else "none",
        opt_bid=bid,
        opt_ask=ask,
        best_bid=bid,
        best_ask=ask,
        opt_ltp=ltp,
        current_ltp=ltp,
        size_mult=size_mult,
        option_type="CE",
        right="CE",
        instrument_type="OPT",
        tradingsymbol=f"{normalized_symbol}2631723850CE",
        instrument_id=f"{normalized_symbol}|2026-03-17|23850|CE",
    )


def test_opportunity_engine_ranks_executable_candidate_first_and_scales_size():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-EXEC-1",
                confidence=0.52,
                builder_confidence=0.52,
                permission_confidence=0.49,
                gating_final_confidence=0.46,
                confluence=0.72,
                bid=120.0,
                ask=121.44,
                ltp=121.0,
                volume=8000,
                quote_age_sec=0.5,
                execution_allowed=True,
                tradable=True,
                execution_entry=121.5,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=121.5,
            ),
            _trade(
                trade_id="T-EXEC-2",
                confidence=0.64,
                builder_confidence=0.64,
                permission_confidence=0.60,
                gating_final_confidence=0.57,
                confluence=0.85,
                bid=119.0,
                ask=119.72,
                ltp=119.5,
                volume=12000,
                quote_age_sec=0.2,
                execution_allowed=True,
                tradable=True,
                execution_entry=119.5,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=119.5,
            ),
        ],
        scope="unit:main",
        top_n=1,
    )

    assert [trade.trade_id for trade in ranked] == ["T-EXEC-2", "T-EXEC-1"]
    assert ranked[0].opportunity_rank == 1
    assert ranked[0].selected_for_execution is True
    assert ranked[0].selection_reason == "selected_top_rank"
    assert ranked[0].opportunity_score is not None
    assert ranked[0].opportunity_size_multiplier is not None
    assert ranked[0].size_mult < 1.0
    assert ranked[1].selected_for_execution is False
    assert ranked[1].selection_reason in {"rank_outside_top_n", "below_adaptive_threshold"}


def test_opportunity_engine_keeps_display_only_candidate_non_selected():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-DISPLAY",
                confidence=0.61,
                builder_confidence=0.61,
                permission_confidence=0.57,
                gating_final_confidence=0.53,
                confluence=0.76,
                bid=120.4,
                ask=121.6,
                ltp=121.0,
                volume=7000,
                quote_age_sec=0.7,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=121.0,
            ),
        ],
        scope="unit:display_only",
        top_n=1,
    )

    assert len(ranked) == 1
    assert ranked[0].selected_for_execution is False
    assert ranked[0].selection_reason == "not_execution_eligible"
    assert ranked[0].opportunity_rank == 1
    assert ranked[0].display_entry == 121.0
    assert ranked[0].execution_entry is None


def test_select_best_opportunity_downgrades_non_selected_execution_allowed_trade():
    best, ranked = select_best_opportunity(
        [
            _trade(
                trade_id="T-DISPLAY-BEST",
                confidence=0.61,
                builder_confidence=0.61,
                permission_confidence=0.57,
                gating_final_confidence=0.53,
                confluence=0.76,
                bid=120.4,
                ask=121.6,
                ltp=121.0,
                volume=7000,
                quote_age_sec=0.7,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=121.0,
            ),
        ],
        scope="unit:select_best",
        top_n=1,
    )

    assert best is not None
    assert ranked[0].selected_for_execution is False
    assert best.execution_allowed is False
    assert "opportunity_not_execution_eligible" in str(best.reason)


def test_relative_opportunity_ranking_supports_multiple_candidates_in_one_batch():
    ranked = annotate_relative_opportunity_ranks(
        [
            _trade(
                trade_id="T-NIFTY-ADV",
                confidence=0.79,
                builder_confidence=0.79,
                permission_confidence=0.76,
                gating_final_confidence=0.74,
                confluence=0.83,
                bid=120.0,
                ask=121.0,
                ltp=120.5,
                volume=6000,
                quote_age_sec=0.4,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=120.5,
            ),
            _trade(
                trade_id="T-BANK-EXEC",
                confidence=0.68,
                builder_confidence=0.68,
                permission_confidence=0.64,
                gating_final_confidence=0.61,
                confluence=0.70,
                bid=220.0,
                ask=221.0,
                ltp=220.5,
                volume=5000,
                quote_age_sec=0.5,
                execution_allowed=True,
                tradable=True,
                execution_entry=221.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=221.0,
                symbol="BANKNIFTY",
            ),
            _trade(
                trade_id="T-NIFTY-EXEC",
                confidence=0.60,
                builder_confidence=0.60,
                permission_confidence=0.57,
                gating_final_confidence=0.55,
                confluence=0.62,
                bid=118.0,
                ask=119.0,
                ltp=118.5,
                volume=4000,
                quote_age_sec=0.8,
                execution_allowed=True,
                tradable=True,
                execution_entry=119.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=119.0,
            ),
        ],
        scope="unit:cycle",
    )

    assert [trade.trade_id for trade in ranked] == ["T-NIFTY-ADV", "T-BANK-EXEC", "T-NIFTY-EXEC"]
    assert [trade.rank_global for trade in ranked] == [1, 2, 3]
    assert ranked[0].rank_within_symbol == 1
    assert ranked[2].rank_within_symbol == 2
    assert ranked[0].opportunity_bucket in {"TOP", "STRONG", "WATCH", "LOW"}


def test_non_executable_high_quality_candidate_keeps_top_relative_rank():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-ADV-HIGH",
                confidence=0.81,
                builder_confidence=0.81,
                permission_confidence=0.79,
                gating_final_confidence=0.77,
                confluence=0.86,
                bid=120.0,
                ask=121.2,
                ltp=120.8,
                volume=9000,
                quote_age_sec=0.2,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=120.8,
            ),
            _trade(
                trade_id="T-EXEC-LOWER",
                confidence=0.63,
                builder_confidence=0.63,
                permission_confidence=0.60,
                gating_final_confidence=0.58,
                confluence=0.69,
                bid=119.0,
                ask=120.0,
                ltp=119.5,
                volume=6000,
                quote_age_sec=0.6,
                execution_allowed=True,
                tradable=True,
                execution_entry=120.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=120.0,
            ),
        ],
        scope="unit:mixed",
        top_n=1,
    )

    advisory = next(trade for trade in ranked if trade.trade_id == "T-ADV-HIGH")
    executable = next(trade for trade in ranked if trade.trade_id == "T-EXEC-LOWER")
    assert advisory.rank_global == 1
    assert advisory.selected_for_execution is False
    assert executable.selected_for_execution is True


def test_explicit_rank_score_drives_ordering_and_top_selection_when_present():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-HIGH-OPPORTUNITY-LOW-RANK",
                confidence=0.88,
                builder_confidence=0.88,
                permission_confidence=0.85,
                gating_final_confidence=0.83,
                confluence=0.90,
                bid=121.0,
                ask=121.5,
                ltp=121.2,
                volume=16000,
                quote_age_sec=0.2,
                execution_allowed=True,
                tradable=True,
                execution_entry=121.5,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=121.5,
                rank_score=0.32,
            ),
            _trade(
                trade_id="T-LOW-OPPORTUNITY-HIGH-RANK",
                confidence=0.61,
                builder_confidence=0.61,
                permission_confidence=0.58,
                gating_final_confidence=0.56,
                confluence=0.64,
                bid=120.0,
                ask=121.0,
                ltp=120.5,
                volume=7000,
                quote_age_sec=0.9,
                execution_allowed=True,
                tradable=True,
                execution_entry=121.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=121.0,
                rank_score=0.91,
            ),
        ],
        scope="unit:rank_score_priority",
        top_n=1,
    )

    assert [trade.trade_id for trade in ranked] == [
        "T-LOW-OPPORTUNITY-HIGH-RANK",
        "T-HIGH-OPPORTUNITY-LOW-RANK",
    ]
    assert ranked[0].rank_global == 1
    assert ranked[1].rank_global == 2
    assert ranked[0].selected_for_execution is True
    assert ranked[0].selection_reason == "selected_top_rank"
    assert ranked[1].selected_for_execution is False


def test_relative_opportunity_ranking_is_stable_for_deterministic_inputs():
    candidates = [
        _trade(
            trade_id="T-A",
            confidence=0.70,
            builder_confidence=0.70,
            permission_confidence=0.68,
            gating_final_confidence=0.66,
            confluence=0.75,
            bid=100.0,
            ask=101.0,
            ltp=100.5,
            volume=5000,
            quote_age_sec=0.4,
            execution_allowed=True,
            tradable=True,
            execution_entry=101.0,
            execution_entry_status="executable",
            execution_entry_source="ask",
            display_entry=101.0,
        ),
        _trade(
            trade_id="T-B",
            confidence=0.70,
            builder_confidence=0.70,
            permission_confidence=0.68,
            gating_final_confidence=0.66,
            confluence=0.75,
            bid=100.0,
            ask=101.0,
            ltp=100.5,
            volume=5000,
            quote_age_sec=0.4,
            execution_allowed=True,
            tradable=True,
            execution_entry=101.0,
            execution_entry_status="executable",
            execution_entry_source="ask",
            display_entry=101.0,
        ),
    ]

    first = annotate_relative_opportunity_ranks(candidates, scope="unit:stable")
    second = annotate_relative_opportunity_ranks(candidates, scope="unit:stable")

    assert [(trade.trade_id, trade.rank_global) for trade in first] == [(trade.trade_id, trade.rank_global) for trade in second]


def test_select_top_opportunities_separates_executable_and_advisory_lists():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-ADV-TOP",
                confidence=0.82,
                builder_confidence=0.82,
                permission_confidence=0.79,
                gating_final_confidence=0.77,
                confluence=0.85,
                bid=120.0,
                ask=121.0,
                ltp=120.5,
                volume=9000,
                quote_age_sec=0.2,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=120.5,
            ),
            _trade(
                trade_id="T-EXEC-TOP",
                confidence=0.71,
                builder_confidence=0.71,
                permission_confidence=0.68,
                gating_final_confidence=0.65,
                confluence=0.73,
                bid=119.0,
                ask=120.0,
                ltp=119.5,
                volume=7000,
                quote_age_sec=0.4,
                execution_allowed=True,
                tradable=True,
                execution_entry=120.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=120.0,
            ),
            _trade(
                trade_id="T-ADV-LOWER",
                confidence=0.54,
                builder_confidence=0.54,
                permission_confidence=0.52,
                gating_final_confidence=0.50,
                confluence=0.60,
                bid=118.0,
                ask=119.0,
                ltp=118.5,
                volume=4000,
                quote_age_sec=0.8,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=118.5,
            ),
        ],
        scope="unit:top_lists",
        top_n=1,
    )

    selected = select_top_opportunities(ranked, executable_top_n=1, advisory_top_n=1)

    assert [trade.trade_id for trade in selected["top_executable_opportunities"]] == ["T-EXEC-TOP"]
    assert [trade.trade_id for trade in selected["top_advisory_opportunities"]] == ["T-ADV-TOP"]
    assert selected["candidates_considered"] == 3


def test_select_top_opportunities_excludes_lower_ranked_candidates_without_mutating_inputs():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-EXEC-HIGH",
                confidence=0.74,
                builder_confidence=0.74,
                permission_confidence=0.70,
                gating_final_confidence=0.68,
                confluence=0.78,
                bid=120.0,
                ask=121.0,
                ltp=120.5,
                volume=8000,
                quote_age_sec=0.3,
                execution_allowed=True,
                tradable=True,
                execution_entry=121.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=121.0,
            ),
            _trade(
                trade_id="T-EXEC-LOW",
                confidence=0.62,
                builder_confidence=0.62,
                permission_confidence=0.59,
                gating_final_confidence=0.56,
                confluence=0.66,
                bid=118.0,
                ask=119.0,
                ltp=118.5,
                volume=5000,
                quote_age_sec=0.6,
                execution_allowed=True,
                tradable=True,
                execution_entry=119.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=119.0,
            ),
            _trade(
                trade_id="T-ADV-ONLY",
                confidence=0.69,
                builder_confidence=0.69,
                permission_confidence=0.65,
                gating_final_confidence=0.63,
                confluence=0.72,
                bid=117.0,
                ask=118.0,
                ltp=117.5,
                volume=6000,
                quote_age_sec=0.5,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=117.5,
            ),
        ],
        scope="unit:top_lists_mutation",
        top_n=1,
    )
    before = [(trade.trade_id, trade.rank_global, trade.selected_for_execution) for trade in ranked]

    selected = select_top_opportunities(ranked, executable_top_n=1, advisory_top_n=1)
    after = [(trade.trade_id, trade.rank_global, trade.selected_for_execution) for trade in ranked]

    assert before == after
    assert [trade.trade_id for trade in selected["top_executable_opportunities"]] == ["T-EXEC-HIGH"]
    assert [trade.trade_id for trade in selected["top_advisory_opportunities"]] == ["T-ADV-ONLY"]
    assert "T-EXEC-LOW" not in {
        trade.trade_id for trade in selected["top_executable_opportunities"] + selected["top_advisory_opportunities"]
    }


def test_allocator_marks_executable_slots_without_hiding_advisory_candidates(monkeypatch):
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_MAX_SLOTS", 1, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_PER_SYMBOL_CAP", 1, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_PER_THEME_CAP", 1, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_BUDGET_CAP", 0.0, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_MIN_QUALITY_THRESHOLD", 0.0, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_REPLACEMENT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_REPLACEMENT_MIN_DELTA", 0.03, raising=False)

    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-EXEC-A",
                confidence=0.74,
                builder_confidence=0.74,
                permission_confidence=0.70,
                gating_final_confidence=0.68,
                confluence=0.78,
                bid=120.0,
                ask=121.0,
                ltp=120.5,
                volume=8000,
                quote_age_sec=0.3,
                execution_allowed=True,
                tradable=True,
                execution_entry=121.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=121.0,
            ),
            _trade(
                trade_id="T-EXEC-B",
                confidence=0.72,
                builder_confidence=0.72,
                permission_confidence=0.69,
                gating_final_confidence=0.67,
                confluence=0.76,
                bid=119.0,
                ask=120.0,
                ltp=119.5,
                volume=7600,
                quote_age_sec=0.4,
                execution_allowed=True,
                tradable=True,
                execution_entry=120.0,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=120.0,
                symbol="BANKNIFTY",
            ),
            _trade(
                trade_id="T-ADV",
                confidence=0.83,
                builder_confidence=0.83,
                permission_confidence=0.80,
                gating_final_confidence=0.78,
                confluence=0.86,
                bid=118.0,
                ask=119.0,
                ltp=118.5,
                volume=9000,
                quote_age_sec=0.2,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=118.5,
            ),
        ],
        scope="unit:allocator",
        top_n=2,
    )

    exec_a = next(trade for trade in ranked if trade.trade_id == "T-EXEC-A")
    exec_b = next(trade for trade in ranked if trade.trade_id == "T-EXEC-B")
    advisory = next(trade for trade in ranked if trade.trade_id == "T-ADV")

    assert exec_a.slot_id == "slot-1"
    assert exec_a.allocation_reason == "allocated"
    assert exec_b.slot_id is None
    assert exec_b.allocation_reason == "deferred_slot_cap"
    assert exec_b.selected_for_execution is False
    assert advisory.display_entry == 118.5
    assert advisory.selected_for_execution is False


def test_thresholds_vary_within_bounded_limits(monkeypatch):
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_EXECUTION_SCORE_BASE", 0.52, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_EXECUTION_THRESHOLD_MAX_ADJUSTMENT", 0.08, raising=False)

    ranked = annotate_ranked_opportunities(
        [
            {
                **_trade(
                    trade_id="T-THRESH-BOUND",
                    confidence=0.71,
                    builder_confidence=0.71,
                    permission_confidence=0.68,
                    gating_final_confidence=0.66,
                    confluence=0.75,
                    bid=120.0,
                    ask=121.0,
                    ltp=120.5,
                    volume=12000,
                    quote_age_sec=0.1,
                    execution_allowed=True,
                    tradable=True,
                    execution_entry=121.0,
                    execution_entry_status="executable",
                    execution_entry_source="ask",
                    display_entry=121.0,
                ).__dict__,
                "regime": "EVENT",
                "countertrend": True,
                "minutes_since_open": 5,
                "minutes_to_close": 10,
                "spread_pct": 0.05,
            }
        ],
        scope="unit:threshold_bound",
        top_n=1,
    )

    trade = ranked[0]
    assert trade["threshold_base"] == 0.52
    assert abs(float(trade["threshold_effective"]) - float(trade["threshold_base"])) <= 0.08
    assert "bounded:" in str(trade["threshold_adjustment_reason"])


def test_regime_changes_affect_thresholds_deterministically(monkeypatch):
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", False, raising=False)

    supportive = annotate_ranked_opportunities(
        [
            {
                **_trade(
                    trade_id="T-TREND",
                    confidence=0.71,
                    builder_confidence=0.71,
                    permission_confidence=0.68,
                    gating_final_confidence=0.66,
                    confluence=0.75,
                    bid=120.0,
                    ask=120.4,
                    ltp=120.2,
                    volume=15000,
                    quote_age_sec=0.1,
                    execution_allowed=True,
                    tradable=True,
                    execution_entry=120.4,
                    execution_entry_status="executable",
                    execution_entry_source="ask",
                    display_entry=120.4,
                ).__dict__,
                "regime": "TREND",
                "minutes_since_open": 60,
                "minutes_to_close": 120,
                "spread_pct": 0.002,
            }
        ],
        scope="unit:threshold_supportive",
        top_n=1,
    )[0]

    hostile = annotate_ranked_opportunities(
        [
            {
                **_trade(
                    trade_id="T-EVENT",
                    confidence=0.71,
                    builder_confidence=0.71,
                    permission_confidence=0.68,
                    gating_final_confidence=0.66,
                    confluence=0.75,
                    bid=120.0,
                    ask=120.4,
                    ltp=120.2,
                    volume=15000,
                    quote_age_sec=0.1,
                    execution_allowed=True,
                    tradable=True,
                    execution_entry=120.4,
                    execution_entry_status="executable",
                    execution_entry_source="ask",
                    display_entry=120.4,
                ).__dict__,
                "regime": "EVENT",
                "minutes_since_open": 60,
                "minutes_to_close": 120,
                "spread_pct": 0.002,
            }
        ],
        scope="unit:threshold_hostile",
        top_n=1,
    )[0]

    assert supportive["threshold_effective"] < hostile["threshold_effective"]
    assert supportive["threshold_adjustment_reason"] == annotate_ranked_opportunities(
        [
            {
                **_trade(
                    trade_id="T-TREND-REPEAT",
                    confidence=0.71,
                    builder_confidence=0.71,
                    permission_confidence=0.68,
                    gating_final_confidence=0.66,
                    confluence=0.75,
                    bid=120.0,
                    ask=120.4,
                    ltp=120.2,
                    volume=15000,
                    quote_age_sec=0.1,
                    execution_allowed=True,
                    tradable=True,
                    execution_entry=120.4,
                    execution_entry_status="executable",
                    execution_entry_source="ask",
                    display_entry=120.4,
                ).__dict__,
                "regime": "TREND",
                "minutes_since_open": 60,
                "minutes_to_close": 120,
                "spread_pct": 0.002,
            }
        ],
        scope="unit:threshold_supportive_repeat",
        top_n=1,
    )[0]["threshold_adjustment_reason"]


def test_threshold_observability_explains_adjustments(monkeypatch):
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", False, raising=False)
    ranked = annotate_ranked_opportunities(
        [
            {
                **_trade(
                    trade_id="T-THRESH-OBS",
                    confidence=0.67,
                    builder_confidence=0.67,
                    permission_confidence=0.63,
                    gating_final_confidence=0.60,
                    confluence=0.70,
                    bid=120.0,
                    ask=122.0,
                    ltp=121.0,
                    volume=1000,
                    quote_age_sec=1.8,
                    execution_allowed=True,
                    tradable=True,
                    execution_entry=122.0,
                    execution_entry_status="executable",
                    execution_entry_source="ask",
                    display_entry=122.0,
                ).__dict__,
                "regime": "EVENT",
                "minutes_since_open": 8,
                "minutes_to_close": 25,
                "spread_pct": 0.03,
            }
        ],
        scope="unit:threshold_observability",
        top_n=1,
    )

    trade = ranked[0]
    assert trade["threshold_base"] is not None
    assert trade["threshold_effective"] is not None
    assert "hostile_regime" in str(trade["threshold_adjustment_reason"])
    assert "opening_window" in str(trade["threshold_adjustment_reason"])
    assert trade["source_flags"].get("threshold_effective") == trade["threshold_effective"]
