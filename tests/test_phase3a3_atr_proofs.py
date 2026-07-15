from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult, classify_movement_regime
from core.session_atr import calculate_session_atr_state
from core.session_bar_history import build_session_bar_history_state
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.option_pressure import generate_option_pressure_candidates
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.event_volatility_expansion import generate_event_volatility_expansion_candidates
from tests.test_captured_market_session_replay import (
    CORPUS_ROOT,
    _load_candle_rows,
    _selected_replay_corpus,
)


def _regime(primary: str = "COMPRESSION", **scores: float) -> MovementRegimeResult:
    base = {
        "TREND_UP": 0.0,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.0,
        "VOLATILITY_EXPANSION": 0.0,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base)


def _snapshot(result):
    return {
        "atr_short": result.atr_short,
        "atr_long": result.atr_long,
        "short_available": result.short_available,
        "long_available": result.long_available,
        "current_contiguous_bar_count": result.current_contiguous_bar_count,
        "continuity_status": result.continuity_status,
        "gap_count": result.gap_count,
        "source_history_hash": result.source_history_hash,
        "calculation_hash": result.calculation_hash,
        "warnings": result.warnings,
    }


def _selected_full_row(symbol: str):
    rows = _selected_replay_corpus()["rows"]
    return next(
        row
        for row in rows
        if row["symbol"] == symbol and row["suitability_classification"] == "SUITABLE_FULL_UNDERLYING_SESSION"
    )


def _base_context(*, ts_epoch: float, **overrides) -> StrategyContext:
    payload = {
        "symbol": "NIFTY",
        "ts_epoch": ts_epoch,
        "spot_ltp": 22650.0,
        "open_price": 22500.0,
        "vwap": 22600.0,
        "vwap_slope": 0.04,
        "day_high": 22620.0,
        "day_low": 22480.0,
        "nearest_resistance": 22620.0,
        "nearest_support": 22490.0,
        "range_width_pct": 0.14,
        "atr_short": 35.0,
        "atr_long": 100.0,
        "volume_z": 1.5,
        "volatility_state": "EXPANDING",
        "option_ce_ltp": 125.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 13.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 55,
        "minutes_to_close": 195,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_future_bar_mutation_cannot_change_earlier_atr_checkpoint() -> None:
    row = _selected_full_row("NIFTY")
    rows = _load_candle_rows(CORPUS_ROOT / row["relative_path"])
    cutoff = rows[39]["ts"] + timedelta(minutes=1)

    original = calculate_session_atr_state(
        build_session_bar_history_state(
            symbol=str(row["symbol"]),
            bars=rows,
            cutoff_timestamp=cutoff,
            segment="NSE_FNO",
            source=f"captured:{row['relative_path']}",
            partial_session=False,
        )
    )

    mutated_rows = list(rows)
    for index in range(40, len(mutated_rows)):
        mutated_rows[index] = {
            **mutated_rows[index],
            "open": float(mutated_rows[index]["open"]) + 250.0,
            "high": float(mutated_rows[index]["high"]) + 250.0,
            "low": float(mutated_rows[index]["low"]) + 250.0,
            "close": float(mutated_rows[index]["close"]) + 250.0,
        }

    mutated = calculate_session_atr_state(
        build_session_bar_history_state(
            symbol=str(row["symbol"]),
            bars=mutated_rows,
            cutoff_timestamp=cutoff,
            segment="NSE_FNO",
            source=f"captured:{row['relative_path']}",
            partial_session=False,
        )
    )

    assert _snapshot(original) == _snapshot(mutated)


def test_full_source_cutoff_equals_physically_truncated_prefix() -> None:
    row = _selected_full_row("BANKNIFTY")
    rows = _load_candle_rows(CORPUS_ROOT / row["relative_path"])
    cutoff = rows[39]["ts"] + timedelta(minutes=1)
    prefix_rows = [item for item in rows if item["ts"] + timedelta(minutes=1) <= cutoff]

    from_full_source = calculate_session_atr_state(
        build_session_bar_history_state(
            symbol=str(row["symbol"]),
            bars=rows,
            cutoff_timestamp=cutoff,
            segment="NSE_FNO",
            source=f"captured:{row['relative_path']}",
            partial_session=False,
        )
    )
    from_physical_prefix = calculate_session_atr_state(
        build_session_bar_history_state(
            symbol=str(row["symbol"]),
            bars=prefix_rows,
            cutoff_timestamp=cutoff,
            segment="NSE_FNO",
            source=f"captured:{row['relative_path']}",
            partial_session=False,
        )
    )

    assert _snapshot(from_full_source) == _snapshot(from_physical_prefix)


def test_atr_warmup_and_ratio_proofs_for_strategy_consumers(caplog: pytest.LogCaptureFixture) -> None:
    timestamp_epoch = 1721028000.0
    compression_missing = _base_context(ts_epoch=timestamp_epoch, atr_long=None)
    compression_ready = _base_context(ts_epoch=timestamp_epoch)
    expansion_missing = _base_context(
        ts_epoch=timestamp_epoch,
        atr_short=None,
        atr_long=90.0,
        spot_ltp=22700.0,
        vwap=22600.0,
        vwap_slope=0.04,
        day_high=22720.0,
        day_low=22480.0,
        nearest_resistance=22740.0,
        nearest_support=22580.0,
        volume_z=2.2,
        ce_premium_change=16.0,
    )
    expansion_ready = _base_context(
        ts_epoch=timestamp_epoch,
        atr_short=150.0,
        atr_long=90.0,
        spot_ltp=22700.0,
        vwap=22600.0,
        vwap_slope=0.04,
        day_high=22720.0,
        day_low=22480.0,
        nearest_resistance=22740.0,
        nearest_support=22580.0,
        volume_z=2.2,
        volatility_state="EXPANDING",
        ce_premium_change=16.0,
    )

    with caplog.at_level(logging.WARNING, logger="strategies.movement._utils"):
        compression_missing_candidates = generate_compression_breakout_candidates(
            compression_missing,
            _regime(COMPRESSION=0.82, VOLATILITY_EXPANSION=0.45, TREND_UP=0.35),
        )
        expansion_missing_candidates = generate_event_volatility_expansion_candidates(
            expansion_missing,
            _regime(VOLATILITY_EXPANSION=0.82, TREND_UP=0.55),
        )

    compression_ready_candidates = generate_compression_breakout_candidates(
        compression_ready,
        _regime(COMPRESSION=0.82, VOLATILITY_EXPANSION=0.45, TREND_UP=0.35),
    )
    expansion_ready_candidates = generate_event_volatility_expansion_candidates(
        expansion_ready,
        _regime(VOLATILITY_EXPANSION=0.82, TREND_UP=0.55),
    )

    missing_logs = [record.message for record in caplog.records if "event=STRATEGY_EVIDENCE_BLOCKED" in record.message]

    regime_missing = _base_context(
        ts_epoch=timestamp_epoch,
        atr_long=None,
        spot_ltp=74010.0,
        vwap=74000.0,
        vwap_slope=0.0,
        day_high=74100.0,
        day_low=73920.0,
        volume_z=0.45,
        option_ltp_age_sec=0.6,
    )
    regime_ready = _base_context(
        ts_epoch=timestamp_epoch,
        atr_short=35.0,
        atr_long=100.0,
        spot_ltp=74010.0,
        vwap=74000.0,
        vwap_slope=0.0,
        day_high=74100.0,
        day_low=73920.0,
        range_width_pct=0.12,
        volume_z=0.45,
        option_ltp_age_sec=0.6,
    )

    compression_missing_regime = classify_movement_regime(regime_missing)
    compression_ready_regime = classify_movement_regime(regime_ready)
    expansion_missing_regime = classify_movement_regime(expansion_missing)
    expansion_ready_regime = classify_movement_regime(expansion_ready)

    assert compression_missing_candidates == ()
    assert expansion_missing_candidates == ()
    assert any("runtime_strategy_id=compression_breakout_v1" in message for message in missing_logs)
    assert any("missing_fields=atr_long" in message for message in missing_logs)
    assert any("runtime_strategy_id=event_volatility_expansion_v1" in message for message in missing_logs)
    assert len(compression_ready_candidates) == 1
    assert compression_ready_candidates[0].evidence["atr_short_long_ratio"] == pytest.approx(0.35)
    assert compression_ready_candidates[0].status == "RAW_CANDIDATE"
    assert len(expansion_ready_candidates) == 1
    assert expansion_ready_candidates[0].evidence["atr_short_long_ratio"] == pytest.approx(150.0 / 90.0)
    assert expansion_ready_candidates[0].status == "RAW_CANDIDATE"
    assert compression_missing_regime.evidence["atr_short_long_ratio"] is None
    assert compression_ready_regime.evidence["atr_short_long_ratio"] == pytest.approx(0.35)
    assert compression_ready_regime.scores["COMPRESSION"] >= 0.6
    assert expansion_missing_regime.evidence["atr_short_long_ratio"] is None
    assert expansion_ready_regime.evidence["atr_short_long_ratio"] == pytest.approx(150.0 / 90.0)
    assert expansion_ready_regime.scores["VOLATILITY_EXPANSION"] >= 0.4


def test_non_atr_control_and_regime_numerical_impact_remain_stable() -> None:
    control_without_atr = _base_context(
        ts_epoch=1721028600.0,
        minutes_since_open=35,
        spot_ltp=22608.0,
        vwap=22550.0,
        orb_high=22600.0,
        orb_low=22460.0,
        atr_short=None,
        atr_long=None,
    )
    control_with_atr = _base_context(
        ts_epoch=1721028600.0,
        minutes_since_open=35,
        spot_ltp=22608.0,
        vwap=22550.0,
        orb_high=22600.0,
        orb_low=22460.0,
        atr_short=35.0,
        atr_long=100.0,
    )
    regime = _regime(TREND_UP=0.6, VOLATILITY_EXPANSION=0.3)

    opening_without_atr = generate_opening_range_retest_candidates(control_without_atr, regime)
    opening_with_atr = generate_opening_range_retest_candidates(control_with_atr, regime)
    option_without_atr = generate_option_pressure_candidates(control_without_atr, regime)
    option_with_atr = generate_option_pressure_candidates(control_with_atr, regime)
    expected_opening_fingerprint = (
        "opening_range_retest_v1",
        "OPENING_RANGE_RETEST",
        "NIFTY",
        "BUY_CALL",
        "RAW_CANDIDATE",
        pytest.approx(0.42150442477876104),
        pytest.approx(0.42150442477876104),
        pytest.approx(0.42150442477876104),
        None,
        None,
        None,
        pytest.approx(0.6666666666666666),
        pytest.approx(0.45),
        pytest.approx(0.4),
        pytest.approx(0.0),
        pytest.approx(0.42150442477876104),
        "opening_range_breakout_retest_hold",
        "price_returns_inside_opening_range",
        "opening range breakout retest held",
        (),
    )

    def _opening_fingerprint(candidate):
        return (
            candidate.strategy_id,
            candidate.movement_type,
            candidate.symbol,
            candidate.direction,
            candidate.status,
            candidate.raw_score,
            candidate.confidence_score,
            candidate.price_structure_score,
            candidate.option_confirmation_score,
            candidate.liquidity_score,
            candidate.freshness_score,
            candidate.volatility_score,
            candidate.regime_alignment_score,
            candidate.timing_score,
            candidate.trap_risk_score,
            candidate.confluence_score,
            candidate.entry_trigger,
            candidate.invalid_if,
            candidate.rank_reason,
            candidate.warnings,
        )

    assert len(opening_without_atr) == len(opening_with_atr) == 1
    assert [
        (
            candidate.strategy_id,
            round(candidate.raw_score, 6),
            candidate.direction,
            candidate.status,
            candidate.entry_trigger,
            candidate.invalid_if,
            candidate.rank_reason,
            candidate.warnings,
        )
        for candidate in opening_without_atr
    ] == [
        ("opening_range_retest_v1", 0.421504, "BUY_CALL", "RAW_CANDIDATE", "opening_range_breakout_retest_hold", "price_returns_inside_opening_range", "opening range breakout retest held", ())
    ]
    assert [_opening_fingerprint(candidate) for candidate in opening_without_atr] == [expected_opening_fingerprint]
    assert [_opening_fingerprint(candidate) for candidate in opening_with_atr] == [expected_opening_fingerprint]
    assert option_without_atr == option_with_atr == ()

    regime_without_atr = classify_movement_regime(
        _base_context(
            ts_epoch=1721028000.0,
            spot_ltp=74010.0,
            vwap=74000.0,
            vwap_slope=0.0,
            day_high=74100.0,
            day_low=73920.0,
            range_width_pct=0.12,
            volume_z=0.45,
            option_ltp_age_sec=0.6,
            atr_short=None,
            atr_long=None,
        )
    )
    regime_with_atr = classify_movement_regime(
        _base_context(
            ts_epoch=1721028000.0,
            spot_ltp=74010.0,
            vwap=74000.0,
            vwap_slope=0.0,
            day_high=74100.0,
            day_low=73920.0,
            range_width_pct=0.12,
            volume_z=0.45,
            option_ltp_age_sec=0.6,
            atr_short=35.0,
            atr_long=100.0,
        )
    )

    assert regime_without_atr.primary_regime == "RANGE"
    assert regime_with_atr.primary_regime == "RANGE"
    assert regime_without_atr.evidence["atr_short_long_ratio"] is None
    assert regime_with_atr.evidence["atr_short_long_ratio"] == pytest.approx(0.35)
    assert regime_without_atr.evidence["primary_score"] == pytest.approx(0.8200000000000001)
    assert regime_with_atr.evidence["primary_score"] == pytest.approx(0.8200000000000001)
    assert regime_without_atr.scores["RANGE"] == pytest.approx(0.8200000000000001)
    assert regime_with_atr.scores["RANGE"] == pytest.approx(0.8200000000000001)
    assert regime_without_atr.scores["COMPRESSION"] == pytest.approx(0.4957142857142857)
    assert regime_with_atr.scores["COMPRESSION"] == pytest.approx(0.6823809523809523)
    assert regime_without_atr.scores["VOLATILITY_EXPANSION"] == pytest.approx(0.0)
    assert regime_with_atr.scores["VOLATILITY_EXPANSION"] == pytest.approx(0.0)
    assert regime_without_atr.warnings == ()
    assert regime_with_atr.warnings == ()
