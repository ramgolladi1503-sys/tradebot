from __future__ import annotations

import json
import subprocess
import sys
import threading
from dataclasses import replace

import pytest

import core.strategy_parameter_profiles as parameter_profiles
import strategies.strategy_registry as strategy_registry
from core.strategy_parameter_profiles import (
    AMBIGUOUS_PROFILE,
    COMPATIBILITY_ALIAS,
    EXACT_PROFILE,
    EMBEDDED_FALLBACK,
    MISSING_PROFILE,
    PROFILE_VALUE_DRIFT,
    StrategyParameterProfile,
    build_profile_parameter_hash,
    build_profile_resolution_record,
    classify_profile_resolution,
    get_default_profile,
    validate_profile_alias_map,
)
from strategies.strategy_registry import (
    StrategyRegistryIntegrityError,
    build_strategy_profile_integrity_rows,
    load_strategy_inventory,
    load_strategy_registry,
    validate_strategy_inventory,
    validate_strategy_registry_integrity,
)
from strategies.movement.opening_drive import generate_opening_drive_candidates
from tests.test_opening_movement_strategies import _base_context, _regime


ALLOWED_RESOLUTION_SOURCES = {EXACT_PROFILE, COMPATIBILITY_ALIAS, EMBEDDED_FALLBACK}
ALLOWED_MISMATCH_CLASSIFICATIONS = {
    EXACT_PROFILE,
    COMPATIBILITY_ALIAS,
    EMBEDDED_FALLBACK,
    MISSING_PROFILE,
    AMBIGUOUS_PROFILE,
    PROFILE_VALUE_DRIFT,
}


def _rows_by_requested_profile():
    rows = build_strategy_profile_integrity_rows()
    return {row.profile_id_requested_by_generator: row for row in rows}


def test_every_inventory_managed_component_declares_profile_metadata():
    inventory = load_strategy_inventory()
    validate_strategy_inventory(inventory)

    assert len(inventory["strategies"]) == 12
    for item in inventory["strategies"]:
        assert isinstance(item["canonical_profile_id"], str)
        assert item["canonical_profile_id"].strip()
        assert isinstance(item["profile_version"], str)
        assert item["profile_version"].strip()
        assert item["execution_eligible"] is False


def test_every_canonical_profile_resolves_deterministically():
    rows = build_strategy_profile_integrity_rows()
    assert len(rows) == 12

    for row in rows:
        profile = get_default_profile(row.profile_id_requested_by_generator, row.profile_version)
        repeat = get_default_profile(row.profile_id_requested_by_generator, row.profile_version)

        assert profile is not None
        assert repeat is not None
        assert profile.params_hash == repeat.params_hash
        assert profile.parameter_hash == repeat.parameter_hash
        assert row.parameter_hash == profile.parameter_hash
        assert row.resolution_source in ALLOWED_RESOLUTION_SOURCES
        assert row.mismatch_classification in ALLOWED_MISMATCH_CLASSIFICATIONS
        assert tuple(sorted(row.parameter_keys)) == row.parameter_keys
        assert tuple(sorted(row.embedded_default_keys)) == row.embedded_default_keys
        assert row.effective_parameter_values == row.embedded_default_values
        assert tuple(key for key, _ in row.effective_parameter_values) == row.parameter_keys
        assert tuple(key for key, _ in row.embedded_default_values) == row.embedded_default_keys


def test_compatibility_aliases_resolve_to_one_canonical_profile():
    alias_profile = get_default_profile("opening_range_retest_v1", "v1")
    pressure_profile = get_default_profile("option_pressure_confirmation_v1", "v1")

    assert alias_profile is not None
    assert pressure_profile is not None
    assert alias_profile.requested_profile_id == "opening_range_retest_v1"
    assert alias_profile.resolved_profile_id == "opening_range_breakout_v1"
    assert pressure_profile.requested_profile_id == "option_pressure_confirmation_v1"
    assert pressure_profile.resolved_profile_id == "option_pressure_v1"
    assert alias_profile.resolution_source == COMPATIBILITY_ALIAS
    assert pressure_profile.resolution_source == COMPATIBILITY_ALIAS


def test_alias_cycles_and_ambiguous_aliases_are_rejected():
    with pytest.raises(ValueError, match="profile_alias_cycle"):
        validate_profile_alias_map({"alias_a": "alias_a"})

    with pytest.raises(ValueError, match="profile_alias_target_is_alias"):
        validate_profile_alias_map({"alias_a": "alias_b", "alias_b": "opening_drive_v1"})

    with pytest.raises(ValueError, match="profile_alias_collides_with_canonical"):
        validate_profile_alias_map({"opening_drive_v1": "opening_drive_v1"})


def test_duplicate_and_missing_alias_targets_are_rejected():
    with pytest.raises(ValueError, match="profile_alias_duplicate:alias_a"):
        validate_profile_alias_map(
            [
                ("alias_a", "opening_drive_v1"),
                ("alias_a", "trend_pullback_v1"),
            ]
        )

    with pytest.raises(ValueError, match="profile_alias_target_missing:alias_a:missing_profile_v1"):
        validate_profile_alias_map({"alias_a": "missing_profile_v1"})


def test_unknown_profile_ids_are_explicitly_classified():
    assert get_default_profile("missing_profile_v1", "v1") is None
    assert classify_profile_resolution("missing_profile_v1", "v1") == MISSING_PROFILE
    record = build_profile_resolution_record("missing_profile_v1", "v1")
    assert record["mismatch_classification"] == MISSING_PROFILE
    assert record["resolution_source"] is None


def test_resolution_source_is_never_omitted_for_inventory_rows():
    rows = build_strategy_profile_integrity_rows()
    assert all(row.resolution_source in ALLOWED_RESOLUTION_SOURCES for row in rows)
    assert all(row.profile_id_present_in_store for row in rows)
    assert all(row.canonical_profile_id for row in rows)


def test_parameter_hash_is_deterministic_and_changes_with_effective_parameters():
    base = StrategyParameterProfile(
        strategy_id="example_v1",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={"A": 1, "B": 2},
    )
    reordered = StrategyParameterProfile(
        strategy_id="example_v1",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={"B": 2, "A": 1},
    )
    changed = StrategyParameterProfile(
        strategy_id="example_v1",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={"A": 1, "B": 3},
    )

    assert base.params_hash == reordered.params_hash
    assert base.params_hash != changed.params_hash
    assert base.params_hash == build_profile_parameter_hash(
        resolved_profile_id="example_v1",
        profile_version="v1",
        params={"A": 1, "B": 2},
    )


def test_parameter_hash_is_stable_across_subprocesses_and_aliases():
    script = """
import json
from core.strategy_parameter_profiles import build_profile_parameter_hash, get_default_profile
canonical = get_default_profile("opening_range_breakout_v1", "v1")
alias = get_default_profile("opening_range_retest_v1", "v1")
payload = {
    "canonical_hash": canonical.parameter_hash,
    "alias_hash": alias.parameter_hash,
    "rebuilt_hash": build_profile_parameter_hash(
        resolved_profile_id=canonical.resolved_profile_id,
        profile_version=canonical.profile_version,
        params={"MIN_BREAKOUT_DISTANCE_PCT": 0.0008, "MAX_RETEST_DISTANCE_PCT": 0.0018, "MAX_RETEST_MINUTES": 90, "MIN_RETEST_MINUTES": 15},
    ),
}
print(json.dumps(payload, sort_keys=True))
"""
    first = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    payload_first = json.loads(first.stdout)
    payload_second = json.loads(second.stdout)
    assert payload_first == payload_second
    assert payload_first["canonical_hash"] == payload_first["alias_hash"]
    assert payload_first["canonical_hash"] == payload_first["rebuilt_hash"]


def test_registry_runtime_ids_module_ids_and_profile_ids_reconcile():
    validate_strategy_registry_integrity()
    rows = _rows_by_requested_profile()

    opening_range = rows["opening_range_retest_v1"]
    option_pressure = rows["option_pressure_confirmation_v1"]

    assert opening_range.inventory_canonical_id == "OPENING_RANGE_RETEST"
    assert opening_range.canonical_profile_id == "opening_range_breakout_v1"
    assert opening_range.profile_id_present_in_store == "opening_range_breakout_v1"
    assert opening_range.compatibility_alias == "opening_range_retest_v1->opening_range_breakout_v1"
    assert opening_range.mismatch_classification == COMPATIBILITY_ALIAS

    assert option_pressure.inventory_canonical_id == "OPTION_QUOTE_CONFIRMATION"
    assert option_pressure.canonical_profile_id == "option_pressure_v1"
    assert option_pressure.profile_id_present_in_store == "option_pressure_v1"
    assert option_pressure.compatibility_alias == "option_pressure_confirmation_v1->option_pressure_v1"
    assert option_pressure.mismatch_classification == COMPATIBILITY_ALIAS

    assert all(row.mismatch_classification in {EXACT_PROFILE, COMPATIBILITY_ALIAS} for row in rows.values())
    assert rows["no_trade_engine_v1"].effective_parameter_values == ()
    assert rows["no_trade_engine_v1"].embedded_default_values == ()


def test_validation_rejects_profile_value_drift_without_silent_activation(monkeypatch):
    original_extract = strategy_registry._extract_embedded_profile_defaults

    def _drifted_defaults(entry):
        defaults = original_extract(entry)
        if entry.runtime_strategy_id == "option_pressure_confirmation_v1":
            return {"MIN_PRESSURE_SCORE": 0.99}
        return defaults

    monkeypatch.setattr(strategy_registry, "_extract_embedded_profile_defaults", _drifted_defaults)
    with pytest.raises(
        StrategyRegistryIntegrityError,
        match="profile_resolution_mismatch:OPTION_PRESSURE:PROFILE_VALUE_DRIFT",
    ):
        validate_strategy_registry_integrity()


def test_source_parsing_is_explicit_validation_only(monkeypatch):
    def _explode(*args, **kwargs):
        raise AssertionError("source parsing should not run here")

    monkeypatch.setattr(strategy_registry, "_extract_embedded_profile_defaults", _explode)
    assert load_strategy_registry()

    candidate = generate_opening_drive_candidates(
        _base_context(),
        _regime(TREND_UP=0.8, VOLATILITY_EXPANSION=0.4),
    )
    assert len(candidate) == 1


def test_profile_integrity_builder_has_no_network_or_thread_side_effects():
    before_threads = {thread.name for thread in threading.enumerate()}
    rows = build_strategy_profile_integrity_rows()
    after_threads = {thread.name for thread in threading.enumerate()}

    assert len(rows) == 12
    assert before_threads == after_threads

    script = """
import json
import socket
from strategies.strategy_registry import build_strategy_profile_integrity_rows
original = socket.create_connection
calls = []
def fail(*args, **kwargs):
    calls.append({"args": args, "kwargs": kwargs})
    raise AssertionError("network_not_allowed")
socket.create_connection = fail
try:
    rows = build_strategy_profile_integrity_rows()
finally:
    socket.create_connection = original
print(json.dumps({"row_count": len(rows), "network_calls": calls}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload == {"row_count": 12, "network_calls": []}


def test_profile_value_drift_preserves_prior_generator_behavior(monkeypatch):
    baseline_candidates = generate_opening_drive_candidates(
        _base_context(),
        _regime(TREND_UP=0.8, VOLATILITY_EXPANSION=0.4),
    )
    assert len(baseline_candidates) == 1
    baseline = baseline_candidates[0]

    original_profile = parameter_profiles.DEFAULT_PROFILES["opening_drive_v1"]
    monkeypatch.setitem(
        parameter_profiles.DEFAULT_PROFILES,
        "opening_drive_v1",
        replace(
            original_profile,
            params={
                "MAX_OPENING_DRIVE_MINUTES": 99,
                "MIN_OPEN_MOVE_PCT": 0.0099,
                "MIN_VWAP_ALIGNMENT_PCT": 0.0099,
            },
        ),
    )

    assert classify_profile_resolution("opening_drive_v1", "v1") == PROFILE_VALUE_DRIFT
    assert get_default_profile("opening_drive_v1", "v1") is None

    inventory = load_strategy_inventory()
    inventory_index = validate_strategy_inventory(inventory)
    registry = load_strategy_registry()
    row = strategy_registry._profile_integrity_row(
        entry=registry["OPENING_DRIVE"],
        inventory_item=inventory_index["OPENING_DRIVE"],
        module_strategy_id="opening_drive_v1",
    )
    assert row.mismatch_classification == PROFILE_VALUE_DRIFT
    assert row.resolution_source is None

    candidates = generate_opening_drive_candidates(
        _base_context(),
        _regime(TREND_UP=0.8, VOLATILITY_EXPANSION=0.4),
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == baseline.strategy_id
    assert candidate.direction == baseline.direction
    assert candidate.status == baseline.status
    assert round(candidate.raw_score, 6) == round(baseline.raw_score, 6)
