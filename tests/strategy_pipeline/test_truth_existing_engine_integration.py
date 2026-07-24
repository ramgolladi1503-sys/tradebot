from __future__ import annotations

from datetime import date
from pathlib import Path

from core.strategy_pipeline.truth_stage_adapter import audit_exact_strategy
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_registry.strategy_manifest import StrategyManifest


def test_existing_truth_components_run_on_one_exact_manifest(tmp_path: Path):
    implementation = tmp_path / "orb_truth_fixture.py"
    implementation.write_text(
        '''VWAP = "vwap"
OHLCV = "ohlcv"


def opening_range_entry(session_time, range_high, close, confirm):
    """Entry after opening range breakout confirmation."""
    if session_time and close > range_high and confirm:
        return "candidate"
    return None


def exit_rule(price, stop, target, elapsed_minutes):
    """Exit on stop target or time stop."""
    if price < stop or price > target or elapsed_minutes > 30:
        return True
    return False
''',
        encoding="utf-8",
    )
    contract = StrategyContract(
        strategy_id="truth_fixture",
        strategy_name="ORB Truth Fixture",
        version="1.0.0",
        owner="research",
        created_date=date(2026, 7, 22),
        description="ORB opening range breakout",
        market_hypothesis="Opening range breakout continuation.",
        primary_market="NIFTY",
        supported_indices=["NIFTY"],
        supported_option_types=["CE", "PE"],
        entry_rules_summary="Entry after opening range breakout confirmation.",
        exit_rules_summary="Exit on stop target or time stop.",
        stop_logic_summary="Stop below opening range.",
        target_logic_summary="Target at fixed reward multiple.",
        time_stop="Exit after 30 minutes.",
        required_indicators=["VWAP"],
        required_market_data=["OHLCV"],
        required_option_data=["BID_ASK"],
        required_sessions=["OPEN"],
        required_liquidity="Tight spread",
        allowed_regimes=["TREND"],
        forbidden_regimes=["HALTED"],
        required_confirmations=["COMPLETED_BAR"],
        known_limitations=["Static fixture"],
        known_assumptions=["Deterministic source"],
    )
    manifest = StrategyManifest(
        contract=contract,
        file_path=str(implementation),
        module_path="fixtures.orb_truth_fixture",
    )

    verdict, payload, blockers = audit_exact_strategy(manifest, implementation)

    assert verdict in {
        "IMPLEMENTATION_VERIFIED",
        "PARTIALLY_VERIFIED",
        "IMPLEMENTATION_MISMATCH",
        "UNABLE_TO_VERIFY",
        "REQUIRES_MANUAL_REVIEW",
    }
    assert payload["verdict"] == verdict
    assert payload["source_evidence"]["strategy_id"] == "truth_fixture"
    assert isinstance(payload["rule_comparisons"], list)
    assert isinstance(payload["semantic_results"], list)
    assert isinstance(blockers, list)
