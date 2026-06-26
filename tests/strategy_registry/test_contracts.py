import pytest
from datetime import date
from core.strategy_registry.registry_types import ImplementationStatus, ReplayStatus
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_registry.registry_errors import MissingMetadataError
import dataclasses


def get_valid_contract():
    return StrategyContract(
        strategy_id="test_strat_001",
        strategy_name="Test Strategy",
        version="1.0.0",
        owner="quants",
        created_date=date.today(),
        description="A test strategy",
        market_hypothesis="Testing works",
        primary_market="NSE",
        supported_indices=["NIFTY"],
        supported_option_types=["CE", "PE"],
        entry_rules_summary="Enter on green",
        exit_rules_summary="Exit on red",
        stop_logic_summary="Stop at 5%",
        target_logic_summary="Target 10%",
        time_stop="15:15",
        required_indicators=["RSI"],
        required_market_data=["NIFTY50"],
        required_option_data=["NIFTY_OPT"],
        required_sessions=["INTRADAY"],
        required_liquidity="HIGH",
        allowed_regimes=["BULL", "BEAR"],
        forbidden_regimes=["CHOP"],
        required_confirmations=["VWAP"],
        known_limitations=["Slippage"],
        known_assumptions=["Zero latency"],
        implementation_status=ImplementationStatus.IMPLEMENTED,
        replay_status=ReplayStatus.PASSED,
    )


def test_contract_immutability():
    contract = get_valid_contract()
    with pytest.raises(dataclasses.FrozenInstanceError):
        contract.version = "1.0.1"


def test_manifest_validation_success():
    contract = get_valid_contract()
    manifest = StrategyManifest(contract, "test_path.py", "test_module")
    assert manifest.contract.strategy_id == "test_strat_001"


def test_manifest_missing_metadata():
    # Create invalid contract using replace since it's frozen
    contract = get_valid_contract()
    invalid_contract = dataclasses.replace(contract, market_hypothesis="")

    with pytest.raises(MissingMetadataError) as excinfo:
        StrategyManifest(invalid_contract, "test_path.py", "test_module")

    assert "missing critical metadata: market_hypothesis" in str(excinfo.value)
