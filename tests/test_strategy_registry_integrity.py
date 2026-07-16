import copy
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.candidate_pool_orchestrator import get_default_candidate_generators
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.strategy_registry import (
    NON_INVENTORY_REGISTRY_ALLOWLIST,
    StrategyRegistryIntegrityError,
    build_strategy_registry,
    get_movement_strategy_entries,
    load_strategy_inventory,
    load_strategy_registry,
    resolve_registered_callable,
    resolve_registered_module,
    validate_candidate_generator_signature,
    validate_strategy_inventory,
    validate_strategy_registry_integrity,
)


EXPECTED_CANDIDATE_POOL_ORDER = (
    "generate_opening_drive_candidates",
    "generate_opening_range_retest_candidates",
    "generate_compression_breakout_candidates",
    "generate_trend_pullback_candidates",
    "generate_vwap_reclaim_rejection_candidates",
    "generate_failed_breakout_trap_candidates",
    "generate_exhaustion_reversal_candidates",
    "generate_mean_reversion_extension_candidates",
    "generate_event_volatility_expansion_candidates",
    "generate_late_day_momentum_candidates",
)


IST = ZoneInfo("Asia/Kolkata")


def _trend_pullback_history() -> list[dict[str, object]]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    closes = (22590.0, 22630.0, 22615.0, 22635.0)
    bars: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        bar_start = start + timedelta(minutes=index)
        bar_end = bar_start + timedelta(minutes=1)
        bars.append(
            {
                "symbol": "NIFTY",
                "session_date": "2026-07-14",
                "timeframe": "1m",
                "bar_start_timestamp": bar_start.isoformat(),
                "bar_end_timestamp": bar_end.isoformat(),
                "open": close - 5.0,
                "high": close + 10.0,
                "low": close - 10.0,
                "close": close,
                "volume": 1000.0 + (index * 100.0),
                "source": "unit_test",
                "source_timestamp": bar_end.isoformat(),
                "receipt_timestamp": (bar_end + timedelta(seconds=1)).isoformat(),
                "is_complete": True,
            }
        )
    return bars


def _regime(primary="TREND_UP", **overrides):
    scores = {
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
    scores.update(overrides)
    return MovementRegimeResult(
        schema_version=1,
        primary_regime=primary,
        scores=scores,
    )


def _neutral_context():
    return StrategyContext(
        symbol="NIFTY",
        spot_ltp=100.0,
        vwap=100.0,
        vwap_slope=0.0,
        range_width_pct=0.01,
        volume_z=1.0,
        ce_spread_pct=0.01,
        pe_spread_pct=0.01,
    )


def _rich_fixed_context():
    return StrategyContext(
        symbol="NIFTY",
        spot_ltp=22620.0,
        open_price=22500.0,
        vwap=22540.0,
        day_high=22620.0,
        day_low=22460.0,
        orb_high=22600.0,
        orb_low=22460.0,
        nearest_resistance=22600.0,
        nearest_support=22590.0,
        range_width_pct=0.14,
        atr_short=35.0,
        atr_long=100.0,
        volume_z=1.5,
        option_ce_ltp=120.0,
        option_pe_ltp=90.0,
        ce_premium_change=12.0,
        pe_premium_change=0.0,
        ce_spread_pct=0.8,
        pe_spread_pct=0.8,
        ce_depth=1200.0,
        pe_depth=1200.0,
        option_ltp_age_sec=0.4,
        quote_source="live_option_tick",
        fallback_used=False,
        minutes_since_open=35,
        completed_bar_history=_trend_pullback_history(),
    )


def test_all_inventory_managed_registry_modules_and_callables_resolve():
    validated = validate_strategy_registry_integrity()

    assert validated == get_movement_strategy_entries()
    assert len(validated) == 12
    for entry in validated:
        handler = resolve_registered_callable(entry)
        assert callable(handler)
        assert handler.__module__ == entry.module_path.removesuffix(".py").replace("/", ".")
        assert handler.__name__ == entry.callable_name


def test_every_registry_module_imports_and_every_declared_callable_resolves():
    registry = load_strategy_registry()

    validate_strategy_registry_integrity(registry=registry)
    for entry in registry.values():
        module = resolve_registered_module(entry)
        assert module.__name__ == entry.module_path.removesuffix(".py").replace("/", ".")
        if entry.callable_name:
            assert callable(resolve_registered_callable(entry))


def test_non_movement_stale_references_are_truthfully_resolved():
    registry = load_strategy_registry()

    htf = registry["HTF_OPENING_DRIVE_CONT"]
    assert htf.module_path == "core/candidate_audits/htf_strategies.py"
    assert htf.callable_name == "HTFStrategy"
    htf_instance = resolve_registered_callable(htf)(*htf.callable_init_args)
    assert htf_instance.name == "HTF_OPENING_DRIVE_CONT"

    pro_engine = registry["PRO_STRATEGY_ENGINE"]
    assert pro_engine.callable_name == "ProStrategyEngine.run"
    assert callable(resolve_registered_callable(pro_engine))

    ensemble = registry["ENSEMBLE"]
    assert ensemble.callable_name == "ensemble_signal"
    assert callable(resolve_registered_callable(ensemble))

    test_fixture = registry["TEST_STRAT"]
    assert test_fixture.module_path == "strategies/strategy_registry.py"
    assert test_fixture.callable_name == ""
    assert test_fixture.strategy_kind == "test_fixture"


def test_registry_loads_fresh_mutable_entries_for_backward_compatibility():
    first = load_strategy_registry()
    first["VWAP_RECLAIM"].callable_name = "caller_local_override"

    second = load_strategy_registry()

    assert second["VWAP_RECLAIM"].callable_name == "generate_vwap_reclaim_rejection_candidates"


def test_every_movement_callable_returns_candidate_contract_for_neutral_context():
    ctx = _neutral_context()
    regime = _regime(primary="CHOP", CHOP=1.0)

    for entry in validate_strategy_registry_integrity():
        emitted = resolve_registered_callable(entry)(ctx, regime)
        assert isinstance(emitted, (list, tuple)), entry.strategy_id
        assert all(isinstance(candidate, StrategyCandidate) for candidate in emitted)


def test_candidate_interface_rejects_keyword_only_and_reversed_parameters():
    entry = get_movement_strategy_entries()[0]

    def keyword_only(*, ctx, regime):
        return ()

    def reversed_order(regime, ctx):
        return ()

    with pytest.raises(StrategyRegistryIntegrityError, match="interface_invalid"):
        validate_candidate_generator_signature(entry, keyword_only)
    with pytest.raises(StrategyRegistryIntegrityError, match="interface_invalid"):
        validate_candidate_generator_signature(entry, reversed_order)


def test_known_synthesized_name_mismatches_use_exact_compatibility_references():
    registry = load_strategy_registry()

    assert registry["VWAP_RECLAIM"].inventory_id == "VWAP_RECLAIM_REJECTION"
    assert registry["VWAP_RECLAIM"].callable_name == "generate_vwap_reclaim_rejection_candidates"
    assert registry["OPENING_RANGE_BREAKOUT"].inventory_id == "OPENING_RANGE_RETEST"
    assert registry["OPENING_RANGE_BREAKOUT"].callable_name == "generate_opening_range_retest_candidates"
    assert registry["NO_TRADE_CHOP"].role == "safety_suppression"
    assert registry["NO_TRADE_CHOP"].callable_name == "generate_no_trade_candidates"


def test_inventory_aliases_resolve_to_one_canonical_component():
    inventory = load_strategy_inventory()
    index = validate_strategy_inventory(inventory)

    expected_aliases = {
        "VWAP_RECLAIM": "VWAP_RECLAIM_REJECTION",
        "OPENING_RANGE_BREAKOUT": "OPENING_RANGE_RETEST",
        "EVENT_VOLATILITY_EXPANSION": "DIRECTIONAL_VOLATILITY_EXPANSION",
        "OPTION_PRESSURE": "OPTION_QUOTE_CONFIRMATION",
    }
    for alias, canonical_id in expected_aliases.items():
        assert index[alias]["id"] == canonical_id


def test_inventory_runtime_strategy_ids_are_unique_and_match_modules():
    inventory = load_strategy_inventory()
    items = inventory["strategies"]
    runtime_ids = [item["runtime_strategy_id"] for item in items]

    assert len(runtime_ids) == len(set(runtime_ids)) == 12
    registry_by_inventory_id = {
        entry.inventory_id: entry for entry in validate_strategy_registry_integrity()
    }
    for item in items:
        assert registry_by_inventory_id[item["id"]].runtime_strategy_id == item["runtime_strategy_id"]


def test_inventory_rejects_duplicate_canonical_ids_ambiguous_aliases_and_unknown_roles():
    duplicate = copy.deepcopy(load_strategy_inventory())
    duplicate["strategies"].append(copy.deepcopy(duplicate["strategies"][0]))
    with pytest.raises(StrategyRegistryIntegrityError, match="duplicate_inventory_id"):
        validate_strategy_inventory(duplicate)

    ambiguous = copy.deepcopy(load_strategy_inventory())
    ambiguous["strategies"][1]["aliases"] = [ambiguous["strategies"][0]["id"]]
    with pytest.raises(StrategyRegistryIntegrityError, match="ambiguous_inventory_identifier"):
        validate_strategy_inventory(ambiguous)

    unknown_role = copy.deepcopy(load_strategy_inventory())
    unknown_role["strategies"][0]["role"] = "execution_strategy"
    with pytest.raises(StrategyRegistryIntegrityError, match="inventory_role_unknown"):
        validate_strategy_inventory(unknown_role)

    missing_runtime_id = copy.deepcopy(load_strategy_inventory())
    missing_runtime_id["strategies"][0].pop("runtime_strategy_id")
    with pytest.raises(StrategyRegistryIntegrityError, match="inventory_runtime_id_missing"):
        validate_strategy_inventory(missing_runtime_id)

    aliases_not_list = copy.deepcopy(load_strategy_inventory())
    aliases_not_list["strategies"][0]["aliases"] = "AMBIGUOUS_STRING"
    with pytest.raises(StrategyRegistryIntegrityError, match="inventory_aliases_not_list"):
        validate_strategy_inventory(aliases_not_list)

    alias_not_string = copy.deepcopy(load_strategy_inventory())
    alias_not_string["strategies"][0]["aliases"] = [123]
    with pytest.raises(StrategyRegistryIntegrityError, match="inventory_alias_not_string"):
        validate_strategy_inventory(alias_not_string)

    canonical_id_not_string = copy.deepcopy(load_strategy_inventory())
    canonical_id_not_string["strategies"][0]["id"] = 123
    with pytest.raises(StrategyRegistryIntegrityError, match="inventory_id_not_string"):
        validate_strategy_inventory(canonical_id_not_string)

    runtime_id_not_string = copy.deepcopy(load_strategy_inventory())
    runtime_id_not_string["strategies"][0]["runtime_strategy_id"] = 123
    with pytest.raises(StrategyRegistryIntegrityError, match="inventory_runtime_id_not_string"):
        validate_strategy_inventory(runtime_id_not_string)


def test_registry_rejects_duplicate_ids_missing_modules_and_missing_callables():
    entry = get_movement_strategy_entries()[0]
    with pytest.raises(StrategyRegistryIntegrityError, match="duplicate_registry_id"):
        build_strategy_registry((entry, entry))

    missing_module = replace(entry, module_path="strategies/movement/does_not_exist.py")
    with pytest.raises(StrategyRegistryIntegrityError, match="registered_module_missing"):
        resolve_registered_callable(missing_module)

    missing_callable = replace(entry, callable_name="does_not_exist")
    with pytest.raises(StrategyRegistryIntegrityError, match="registered_callable_not_found"):
        resolve_registered_callable(missing_callable)

    with pytest.raises(StrategyRegistryIntegrityError, match="registry_component_missing"):
        validate_strategy_registry_integrity(registry={})


def test_non_inventory_registry_components_are_exactly_allowlisted(monkeypatch):
    registry_ids = set(load_strategy_registry())
    movement_ids = {entry.strategy_id for entry in get_movement_strategy_entries()}

    assert registry_ids - movement_ids == set(NON_INVENTORY_REGISTRY_ALLOWLIST)
    assert all(reason.strip() for reason in NON_INVENTORY_REGISTRY_ALLOWLIST.values())

    unknown = load_strategy_registry()
    unknown["UNKNOWN_COMPONENT"] = replace(
        get_movement_strategy_entries()[0],
        strategy_id="UNKNOWN_COMPONENT",
    )
    resolver_calls = []
    monkeypatch.setattr(
        "strategies.strategy_registry.resolve_registered_module",
        lambda entry: resolver_calls.append(entry.strategy_id),
    )
    with pytest.raises(
        StrategyRegistryIntegrityError,
        match="registry_component_absent_from_inventory:UNKNOWN_COMPONENT",
    ):
        validate_strategy_registry_integrity(registry=unknown)
    assert resolver_calls == []


def test_non_inventory_registry_drift_is_rejected_before_any_import(monkeypatch):
    drifted = load_strategy_registry()
    drifted["SIMPLE_ORB"] = replace(
        drifted["SIMPLE_ORB"],
        module_path="strategies/ensemble.py",
        callable_name="ensemble_signal",
    )
    resolver_calls = []
    monkeypatch.setattr(
        "strategies.strategy_registry.resolve_registered_module",
        lambda entry: resolver_calls.append(entry.strategy_id),
    )

    with pytest.raises(StrategyRegistryIntegrityError, match="registry_entry_drift:SIMPLE_ORB"):
        validate_strategy_registry_integrity(registry=drifted)
    assert resolver_calls == []


def test_candidate_pool_activation_order_is_unchanged_and_no_trade_stays_separate():
    names = tuple(generator.__name__ for generator in get_default_candidate_generators())

    assert names == EXPECTED_CANDIDATE_POOL_ORDER
    assert "generate_no_trade_candidates" not in names


def test_fixed_candidate_fingerprint_matches_phase0_baseline():
    ctx = _rich_fixed_context()
    regime = _regime(
        primary="TREND_UP",
        TREND_UP=0.8,
        COMPRESSION=0.8,
        VOLATILITY_EXPANSION=0.45,
    )

    fingerprint = []
    for generator in get_default_candidate_generators():
        for candidate in tuple(generator(ctx, regime) or ()):
            fingerprint.append(
                (
                    generator.__name__,
                    candidate.strategy_id,
                    candidate.movement_type,
                    candidate.direction,
                    candidate.status,
                    round(candidate.raw_score, 6),
                    candidate.blockers,
                )
            )

    assert fingerprint == [
        (
            "generate_compression_breakout_candidates",
            "compression_breakout_v1",
            "COMPRESSION_BREAKOUT",
            "BUY_CALL",
            "RAW_CANDIDATE",
            0.470676,
            (),
        ),
        (
            "generate_trend_pullback_candidates",
            "trend_pullback_v1",
            "TREND_PULLBACK",
            "BUY_CALL",
            "RAW_CANDIDATE",
            0.648584,
            (),
        ),
    ]


def test_quarantine_remains_metadata_only_and_every_item_stays_ineligible():
    inventory = load_strategy_inventory()
    by_id = {item["id"]: item for item in inventory["strategies"]}
    active_names = {generator.__name__ for generator in get_default_candidate_generators()}

    assert by_id["TREND_PULLBACK"]["validation_level"] == "quarantined"
    assert by_id["OPENING_RANGE_RETEST"]["validation_level"] == "quarantined"
    assert by_id["EXHAUSTION_REVERSAL"]["validation_level"] == "quarantined"
    assert "generate_trend_pullback_candidates" in active_names
    assert "generate_opening_range_retest_candidates" in active_names
    assert "generate_exhaustion_reversal_candidates" in active_names
    assert all(item["execution_eligible"] is False for item in inventory["strategies"])


def test_inventory_validation_has_no_broker_feed_risk_or_execution_import_side_effects():
    script = """
import json
import sys
from strategies.strategy_registry import load_strategy_inventory, validate_strategy_inventory
validate_strategy_inventory(load_strategy_inventory())
forbidden = (
    'credentials',
    'core.broker',
    'core.execution',
    'core.feed',
    'core.order',
    'core.risk',
    'strategies.risk_manager',
)
loaded = sorted(name for name in sys.modules if name == forbidden[0] or name.startswith(forbidden[1:]))
print(json.dumps(loaded))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []
