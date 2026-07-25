from __future__ import annotations

from math import nan

import pytest

from research.option_e2e_recertification_v4.evidence_schema import GateRecord, GateStatus
from research.option_e2e_recertification_v4.expiry_resolver import ExpiryChoice
from research.option_e2e_recertification_v4.option_candidate_builder import build_long_option_candidate
from research.option_e2e_recertification_v4.point_in_time_contract_universe import (
    OptionContractMetadata,
    reject_current_master_as_historical_authority,
)
from research.option_e2e_recertification_v4.premium_geometry import PremiumGeometry
from research.option_e2e_recertification_v4.reconciliation import reconcile_decision_counts, reconcile_trade_pnl
from research.option_e2e_recertification_v4.replay_bridge import ExecutableQuote
from research.option_e2e_recertification_v4.signal_contract import (
    CanonicalSignal,
    Direction,
    OptionRight,
    map_direction_to_option_right,
)
from research.option_e2e_recertification_v4.strike_resolver import StrikeChoice, StrikeWrapper
from research.option_e2e_recertification_v4.wfa import WFAPartition


def test_direction_mapping_is_ce_pe_and_neutral_no_trade() -> None:
    assert map_direction_to_option_right(Direction.BULLISH) == OptionRight.CE
    assert map_direction_to_option_right(Direction.BEARISH) == OptionRight.PE
    assert map_direction_to_option_right(Direction.NO_TRADE) is None


def _valid_signal(direction: Direction = Direction.BULLISH) -> CanonicalSignal:
    return CanonicalSignal(
        strategy_id="ORB",
        signal_id="ORB:2024-01-01:1000",
        session="2024-01-01",
        feature_cutoff_ts="2024-01-01T09:59:59+05:30",
        signal_ts="2024-01-01T10:00:00+05:30",
        earliest_entry_ts="2024-01-01T10:00:01+05:30",
        direction=direction,
        signal_strength=1.0,
        params_hash="p",
        source_hash="s",
        is_oos=False,
        fold_id="dev",
    )


def _valid_contract(option_right: OptionRight = OptionRight.CE) -> OptionContractMetadata:
    return OptionContractMetadata(
        trading_symbol=f"NIFTY24JAN22000{option_right.value}",
        instrument_token="123",
        underlying="NIFTY",
        option_right=option_right,
        strike=22000,
        expiry="2024-01-25",
        tick_size=0.05,
        lot_size=50,
        listed_from="2024-01-01T09:15:00+05:30",
        listed_until="2024-01-25T15:30:00+05:30",
        provider="fixture",
        dataset_hash="hash",
        metadata_hash="meta",
        point_in_time_source="historical_master_2024-01-01",
    )


def test_signal_timing_must_be_strictly_causal() -> None:
    signal = CanonicalSignal(
        strategy_id="ORB",
        signal_id="ORB:2024-01-01:1000",
        session="2024-01-01",
        feature_cutoff_ts="2024-01-01T10:00:00+05:30",
        signal_ts="2024-01-01T10:00:00+05:30",
        earliest_entry_ts="2024-01-01T10:00:01+05:30",
        direction=Direction.BULLISH,
        signal_strength=1.0,
        params_hash="p",
        source_hash="s",
        is_oos=False,
        fold_id="dev",
    )
    with pytest.raises(ValueError, match="signal_timing_not_strictly_causal"):
        signal.validate()


def test_candidate_builder_rejects_wrong_option_type_and_no_trade_is_not_candidate() -> None:
    no_trade = build_long_option_candidate(_valid_signal(Direction.NO_TRADE), _valid_contract())
    assert no_trade.action == "NO_TRADE"
    assert no_trade.contract is None

    with pytest.raises(ValueError, match="direction_option_type_mismatch"):
        build_long_option_candidate(_valid_signal(Direction.BEARISH), _valid_contract(OptionRight.CE))


def test_strike_selection_rejects_outcome_fields_and_unverified_greeks() -> None:
    choice = StrikeChoice(
        signal_id="s1",
        wrapper=StrikeWrapper.ATM_LIQUIDITY_FIRST,
        selected_strike=22000,
        atm_reference=22010,
        eligible_strikes=(21950, 22000, 22050),
        causal_liquidity_fields=("bid", "ask", "future_volume"),
        resolver_hash="r",
    )
    with pytest.raises(ValueError, match="future_or_outcome_field_in_strike_selection"):
        choice.validate()

    greeks = StrikeChoice(
        signal_id="s1",
        wrapper=StrikeWrapper.OBSERVED_DELTA_BUCKET,
        selected_strike=22000,
        atm_reference=22010,
        eligible_strikes=(22000,),
        causal_liquidity_fields=("bid", "ask", "oi"),
        resolver_hash="r",
        observed_greeks_verified=False,
    )
    with pytest.raises(ValueError, match="DATA_UNAVAILABLE_OBSERVED_GREEKS"):
        greeks.validate()


def test_executable_quote_uses_ask_for_entry_bid_for_exit_and_rejects_stale_quotes() -> None:
    quote = ExecutableQuote(
        ts="2024-01-01T10:00:02+05:30",
        bid=99.0,
        ask=100.0,
        bid_qty=50,
        ask_qty=50,
        volume=1000,
        oi=2000,
        quote_age_seconds=61.0,
        symbol="NIFTY24JAN22000CE",
    )
    with pytest.raises(ValueError, match="stale_quote_rejected"):
        quote.validate_for_long_entry("2024-01-01T10:00:01+05:30", max_quote_age_seconds=60.0)
    fresh = ExecutableQuote(
        ts="2024-01-01T10:00:02+05:30",
        bid=99.0,
        ask=100.0,
        bid_qty=50,
        ask_qty=50,
        volume=1000,
        oi=2000,
        quote_age_seconds=1.0,
        symbol="NIFTY24JAN22000CE",
    )
    fresh.validate_for_long_entry("2024-01-01T10:00:01+05:30", max_quote_age_seconds=60.0)
    assert fresh.long_entry_fill() == 100.0
    assert fresh.long_exit_fill() == 99.0


def test_gate_rejects_live_or_unexpected_upstream_hash() -> None:
    gate = GateRecord(
        gate_id="G8",
        strategy_id="ORB",
        input_manifest_hash="in",
        output_artifact_hash="out",
        status=GateStatus.PASS,
        reason_code="OPTION_REPLAY_VALID",
        upstream_gate_id="G7",
        upstream_output_hash="expected",
        allowed_for_live_execution=True,
    )
    with pytest.raises(ValueError, match="live_execution_forbidden"):
        gate.validate(expected_upstream_hash="expected")

    repaired = GateRecord(
        gate_id="G8",
        strategy_id="ORB",
        input_manifest_hash="in",
        output_artifact_hash="out",
        status=GateStatus.PASS,
        reason_code="OPTION_REPLAY_VALID",
        upstream_gate_id="G7",
        upstream_output_hash="wrong",
    )
    with pytest.raises(ValueError, match="upstream_hash_mismatch"):
        repaired.validate(expected_upstream_hash="expected")


def test_current_instrument_master_cannot_certify_expired_contract() -> None:
    with pytest.raises(ValueError, match="current_instrument_master_cannot_certify_expired_contract"):
        reject_current_master_as_historical_authority("current_instrument_master")


def test_contract_metadata_must_be_point_in_time_and_listed() -> None:
    contract = OptionContractMetadata(
        trading_symbol="NIFTY24JAN22000CE",
        instrument_token="123",
        underlying="NIFTY",
        option_right=OptionRight.CE,
        strike=22000,
        expiry="2024-01-25",
        tick_size=0.05,
        lot_size=50,
        listed_from="2024-01-20T09:15:00+05:30",
        listed_until="2024-01-25T15:30:00+05:30",
        provider="fixture",
        dataset_hash="hash",
        metadata_hash="meta",
        point_in_time_source="historical_master_2024-01-20",
    )
    with pytest.raises(ValueError, match="contract_not_listed_at_decision_ts"):
        contract.validate_at("2024-01-19T10:00:00+05:30")


def test_geometry_requires_pre_entry_warmup_and_tick_sized_risk() -> None:
    geometry = PremiumGeometry(
        geometry_id="atr",
        entry_fill=100,
        stop_distance=0.01,
        target_distance=10,
        reward_risk=2,
        max_hold_minutes=30,
        tick_size=0.05,
        warmup_observations=10,
        source_cutoff_ts="2024-01-01T10:00:00+05:30",
    )
    with pytest.raises(ValueError, match="risk_distance_below_tick"):
        geometry.validate()


def test_decision_and_trade_accounting_reconcile_exactly() -> None:
    reconcile_decision_counts(
        {
            "signals": 3,
            "direction_rejected": 1,
            "data_blocked": 0,
            "contracts_unresolved": 1,
            "liquidity_rejected": 0,
            "entry_no_fill": 0,
            "replay_attempted": 1,
            "exit_no_fill": 0,
            "ambiguous": 0,
            "evaluated_trades": 1,
        }
    )
    reconcile_trade_pnl(
        {
            "gross_pnl": 100.0,
            "spread_cost": 5.0,
            "slippage": 2.0,
            "brokerage": 1.0,
            "statutory_charges": 3.0,
            "net_pnl": 89.0,
        }
    )
    with pytest.raises(ValueError, match="decision_count_reconciliation_failed"):
        reconcile_decision_counts(
            {
                "signals": 2,
                "direction_rejected": 0,
                "data_blocked": 0,
                "contracts_unresolved": 0,
                "liquidity_rejected": 0,
                "entry_no_fill": 0,
                "replay_attempted": 1,
                "exit_no_fill": 0,
                "ambiguous": 0,
                "evaluated_trades": 1,
            }
        )


def test_holdout_cannot_be_loaded_before_selection_freeze() -> None:
    partition = WFAPartition(
        development_start="2024-01-01",
        development_end="2024-06-01",
        validation_start="2024-06-02",
        validation_end="2024-12-01",
        holdout_start="2024-12-02",
        holdout_end="2025-01-01",
        holdout_opened=True,
    )
    with pytest.raises(ValueError, match="holdout_loaded_before_selection_freeze"):
        partition.validate_before_selection_freeze()


def test_gate_reason_codes_must_match_status_and_gate() -> None:
    pass_with_failure = GateRecord(
        gate_id="G6",
        strategy_id="ORB",
        input_manifest_hash="in",
        output_artifact_hash="out",
        status=GateStatus.PASS,
        reason_code="G9_ECONOMICS_INVALID",
    )
    with pytest.raises(ValueError, match="invalid_pass_reason_code"):
        pass_with_failure.validate()

    fail_with_success = GateRecord(
        gate_id="G6",
        strategy_id="ORB",
        input_manifest_hash="in",
        output_artifact_hash="out",
        status=GateStatus.FAIL,
        reason_code="TRADE_EVALUATED",
    )
    with pytest.raises(ValueError, match="invalid_fail_reason_code"):
        fail_with_success.validate()


def test_contract_metadata_requires_hashes_and_consistent_expiry() -> None:
    contract = _valid_contract()
    empty_hash = OptionContractMetadata(**{**contract.__dict__, "dataset_hash": "", "metadata_hash": ""})
    with pytest.raises(ValueError, match="missing_contract_hash"):
        empty_hash.validate_at("2024-01-01T10:00:00+05:30")
    mismatched = OptionContractMetadata(**{**contract.__dict__, "expiry": "2099-01-01"})
    with pytest.raises(ValueError, match="expiry_metadata_mismatch"):
        mismatched.validate_at("2024-01-01T10:00:00+05:30")


def test_executable_quote_rejects_negative_age_and_missing_bid_liquidity() -> None:
    quote = ExecutableQuote(
        ts="2024-01-01T10:00:02+05:30",
        bid=99.0,
        ask=100.0,
        bid_qty=0,
        ask_qty=1,
        volume=1,
        oi=1,
        quote_age_seconds=-1.0,
        symbol="NIFTY24JAN22000CE",
    )
    with pytest.raises(ValueError, match="negative_quote_age"):
        quote.validate_for_long_entry("2024-01-01T10:00:01+05:30", max_quote_age_seconds=60.0)
    no_bid_qty = ExecutableQuote(**{**quote.__dict__, "quote_age_seconds": 1.0})
    with pytest.raises(ValueError, match="exit_side_liquidity_unproven"):
        no_bid_qty.validate_for_long_entry("2024-01-01T10:00:01+05:30", max_quote_age_seconds=60.0)


def test_reconciliation_rejects_missing_or_negative_counts() -> None:
    with pytest.raises(ValueError, match="missing_reconciliation_count_keys"):
        reconcile_decision_counts({"signals": 0})
    with pytest.raises(ValueError, match="invalid_reconciliation_count"):
        reconcile_decision_counts(
            {
                "signals": -1,
                "direction_rejected": -1,
                "data_blocked": 0,
                "contracts_unresolved": 0,
                "liquidity_rejected": 0,
                "entry_no_fill": 0,
                "replay_attempted": 0,
                "exit_no_fill": 0,
                "ambiguous": 0,
                "evaluated_trades": 0,
            }
        )


def test_signal_rejects_non_finite_strength_and_session_mismatch() -> None:
    bad_strength = CanonicalSignal(**{**_valid_signal().__dict__, "signal_strength": nan})
    with pytest.raises(ValueError, match="non_finite_signal_strength"):
        bad_strength.validate()
    bad_session = CanonicalSignal(**{**_valid_signal().__dict__, "session": "2024-01-02"})
    with pytest.raises(ValueError, match="signal_session_date_mismatch"):
        bad_session.validate()


def test_current_master_helper_normalizes_source_kind() -> None:
    with pytest.raises(ValueError, match="current_instrument_master_cannot_certify_expired_contract"):
        reject_current_master_as_historical_authority(" Current Instrument Master ")


def test_expiry_resolver_allows_valid_expiry_day_before_cutoff_and_rejects_after_cutoff() -> None:
    choice = ExpiryChoice(
        signal_id="s1",
        selected_expiry="2024-01-25",
        min_time_to_expiry_minutes=1,
        available_expiries=("2024-01-25", "2024-02-01"),
        rejection_reasons={},
        resolver_hash="r",
    )
    choice.validate("2024-01-25T09:30:00+05:30")
    with pytest.raises(ValueError, match="expiry_not_valid_after_cutoff"):
        choice.validate("2024-01-25T15:31:00+05:30")


def test_contract_validation_uses_normalized_timestamps_not_substrings() -> None:
    contract = OptionContractMetadata(
        trading_symbol="NIFTY24JAN22000CE",
        instrument_token="123",
        underlying="NIFTY",
        option_right=OptionRight.CE,
        strike=22000,
        expiry="2024-01-25",
        tick_size=0.05,
        lot_size=50,
        listed_from="2024-01-20T09:15:00+05:30",
        listed_until="2024-01-25T15:30:00+05:30",
        provider="fixture",
        dataset_hash="hash",
        metadata_hash="meta",
        point_in_time_source="historical_master_2024-01-20",
    )
    contract.validate_at("2024-01-25T04:30:00Z")
    with pytest.raises(ValueError, match="contract_not_listed_at_decision_ts"):
        contract.validate_at("2024-01-25T10:01:00Z")
    invalid = OptionContractMetadata(**{**contract.__dict__, "listed_until": "2024-01-25T15:31:00+05:30"})
    with pytest.raises(ValueError, match="expiry_metadata_mismatch"):
        invalid.validate_at("2024-01-25T09:30:00+05:30")
