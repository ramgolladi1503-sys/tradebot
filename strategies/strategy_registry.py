"""Strategy certification registry and movement-inventory integrity checks.

The legacy uppercase registry keys and file-style module paths are public
compatibility surfaces. Movement registrations are explicit so a public ID can
map to the real module, callable, runtime strategy ID, movement type, and role
without constructing names heuristically.

Full registry validation imports every registered module and resolves every
declared callable. Candidate-generator interface and inventory reconciliation
checks apply to the twelve inventory-managed movement components. Non-movement
entries are explicitly allowlisted only for inventory reconciliation because
they belong to separate execution, aggregate, helper, deferred, or test-fixture
lifecycles. Inventory-only validation remains read-only and imports no strategy
modules.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping

from core.strategy_parameter_profiles import (
    AMBIGUOUS_PROFILE,
    COMPATIBILITY_ALIAS,
    EMBEDDED_FALLBACK,
    EMBEDDED_PROFILE_DEFAULTS,
    MISSING_PROFILE,
    PROFILE_VALUE_DRIFT,
    classify_profile_resolution,
    get_default_profile,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY_PATH = REPO_ROOT / "config" / "strategy_inventory.yml"

ALLOWED_INVENTORY_ROLES = frozenset(
    {"candidate_generator", "option_confirmation", "safety_suppression"}
)


class StrategyRegistryIntegrityError(ValueError):
    """Raised when registry or inventory metadata is ambiguous or invalid."""


@dataclass
class StrategyRegistryEntry:
    strategy_id: str
    module_path: str
    strategy_kind: str
    instrument_family: str
    callable_name: str
    certification_supported: bool
    certification_track: str
    blocked_reason: str = ""
    inventory_id: str = ""
    runtime_strategy_id: str = ""
    movement_type: str = ""
    role: str = ""
    callable_init_args: tuple[Any, ...] = ()


@dataclass(frozen=True)
class StrategyProfileIntegrityRow:
    inventory_canonical_id: str
    public_compatibility_id: str
    runtime_strategy_id: str
    module_strategy_id: str
    profile_id_requested_by_generator: str
    canonical_profile_id: str
    profile_id_present_in_store: str | None
    profile_version: str
    parameter_keys: tuple[str, ...]
    embedded_default_keys: tuple[str, ...]
    effective_parameter_values: tuple[tuple[str, Any], ...]
    embedded_default_values: tuple[tuple[str, Any], ...]
    resolution_source: str | None
    compatibility_alias: str | None
    parameter_hash: str | None
    mismatch_classification: str


# These components are intentionally absent from the movement-strategy
# inventory. Their presence here is retained for certification compatibility.
# Phase 1A validates their module/callable references but does not invoke or
# certify their execution/runtime interfaces.
NON_INVENTORY_REGISTRY_ALLOWLIST: Mapping[str, str] = {
    "SIMPLE_ORB": "execution strategy outside movement inventory",
    "HTF_OPENING_DRIVE_CONT": "execution strategy outside movement inventory",
    "PRO_STRATEGY_ENGINE": "aggregate engine outside movement inventory",
    "ENSEMBLE": "deferred aggregate outside movement inventory",
    "TRADE_BUILDER": "helper module outside movement inventory",
    "RISK_MANAGER": "helper module outside movement inventory",
    "POSITION_SIZER": "helper module outside movement inventory",
    "SOFT_SIGNAL": "helper module outside movement inventory",
    "PRO_DECISION_ADAPTER": "helper module outside movement inventory",
    "NIFTY_INTRADAY": "helper module outside movement inventory",
    "BANKNIFTY_INTRADAY": "helper module outside movement inventory",
    "SENSEX_INTRADAY": "helper module outside movement inventory",
    "VWAP_ORB": "helper module outside movement inventory",
    "ZERO_HERO": "helper module outside movement inventory",
    "PAIRS_ARBITRAGE": "helper module outside movement inventory",
    "VOLATILITY_TREND": "helper module outside movement inventory",
    "TEST_STRAT": "non-production test fixture outside movement inventory",
}


_MOVEMENT_REGISTRATIONS: tuple[StrategyRegistryEntry, ...] = (
    StrategyRegistryEntry(
        strategy_id="MEAN_REVERSION_EXTENSION",
        module_path="strategies/movement/mean_reversion_extension.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_mean_reversion_extension_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="MEAN_REVERSION_EXTENSION",
        runtime_strategy_id="mean_reversion_extension_v1",
        movement_type="MEAN_REVERSION_EXTENSION",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="COMPRESSION_BREAKOUT",
        module_path="strategies/movement/compression_breakout.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_compression_breakout_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="COMPRESSION_BREAKOUT",
        runtime_strategy_id="compression_breakout_v1",
        movement_type="COMPRESSION_BREAKOUT",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="TREND_PULLBACK",
        module_path="strategies/movement/trend_pullback.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_trend_pullback_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="TREND_PULLBACK",
        runtime_strategy_id="trend_pullback_v1",
        movement_type="TREND_PULLBACK",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="VWAP_RECLAIM",
        module_path="strategies/movement/vwap_reclaim.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_vwap_reclaim_rejection_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="VWAP_RECLAIM_REJECTION",
        runtime_strategy_id="vwap_reclaim_rejection_v1",
        movement_type="VWAP_RECLAIM_REJECTION",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="OPENING_DRIVE",
        module_path="strategies/movement/opening_drive.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_opening_drive_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="OPENING_DRIVE",
        runtime_strategy_id="opening_drive_v1",
        movement_type="OPENING_DRIVE",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="FAILED_BREAKOUT_TRAP",
        module_path="strategies/movement/failed_breakout_trap.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_failed_breakout_trap_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="FAILED_BREAKOUT_TRAP",
        runtime_strategy_id="failed_breakout_trap_v1",
        movement_type="FAILED_BREAKOUT_TRAP",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="EXHAUSTION_REVERSAL",
        module_path="strategies/movement/exhaustion_reversal.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_exhaustion_reversal_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="EXHAUSTION_REVERSAL",
        runtime_strategy_id="exhaustion_reversal_v1",
        movement_type="EXHAUSTION_REVERSAL",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="EVENT_VOLATILITY_EXPANSION",
        module_path="strategies/movement/event_volatility_expansion.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_event_volatility_expansion_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="DIRECTIONAL_VOLATILITY_EXPANSION",
        runtime_strategy_id="event_volatility_expansion_v1",
        movement_type="EVENT_VOLATILITY_EXPANSION",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="LATE_DAY_MOMENTUM",
        module_path="strategies/movement/late_day_momentum.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_late_day_momentum_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="LATE_DAY_MOMENTUM",
        runtime_strategy_id="late_day_momentum_v1",
        movement_type="LATE_DAY_MOMENTUM",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="OPTION_PRESSURE",
        module_path="strategies/movement/option_pressure.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_option_pressure_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="OPTION_QUOTE_CONFIRMATION",
        runtime_strategy_id="option_pressure_confirmation_v1",
        movement_type="OPTION_PRESSURE_CONFIRMATION",
        role="option_confirmation",
    ),
    StrategyRegistryEntry(
        strategy_id="OPENING_RANGE_BREAKOUT",
        module_path="strategies/movement/opening_range_breakout.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_opening_range_retest_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="OPENING_RANGE_RETEST",
        runtime_strategy_id="opening_range_retest_v1",
        movement_type="OPENING_RANGE_RETEST",
        role="candidate_generator",
    ),
    StrategyRegistryEntry(
        strategy_id="NO_TRADE_CHOP",
        module_path="strategies/movement/no_trade_chop.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_no_trade_candidates",
        certification_supported=True,
        certification_track="candidate_generator_contract_only",
        inventory_id="NO_TRADE_CHOP",
        runtime_strategy_id="no_trade_engine_v1",
        movement_type="NO_TRADE_CHOP",
        role="safety_suppression",
    ),
)


def get_movement_strategies() -> list[str]:
    """Return legacy movement registry IDs in their original order."""

    return [entry.strategy_id for entry in _MOVEMENT_REGISTRATIONS]


def get_movement_strategy_entries() -> tuple[StrategyRegistryEntry, ...]:
    """Return the explicit movement registrations in compatibility order."""

    return tuple(replace(entry) for entry in _MOVEMENT_REGISTRATIONS)


def _non_movement_entries() -> tuple[StrategyRegistryEntry, ...]:
    entries: list[StrategyRegistryEntry] = [
        StrategyRegistryEntry(
            strategy_id="SIMPLE_ORB",
            module_path="strategies/simple_orb.py",
            strategy_kind="execution_signal_strategy",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="generate_signals",
            certification_supported=True,
            certification_track="phase_1_to_5_execution_replay",
        ),
        StrategyRegistryEntry(
            strategy_id="HTF_OPENING_DRIVE_CONT",
            module_path="core/candidate_audits/htf_strategies.py",
            strategy_kind="execution_signal_strategy",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="HTFStrategy",
            certification_supported=True,
            certification_track="phase_1_to_5_execution_replay",
            callable_init_args=("OPENING_DRIVE_CONT",),
        ),
        StrategyRegistryEntry(
            strategy_id="PRO_STRATEGY_ENGINE",
            module_path="strategies/pro_layer/pro_strategy_engine.py",
            strategy_kind="aggregate_engine",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="ProStrategyEngine.run",
            certification_supported=True,
            certification_track="aggregate_engine_certification",
        ),
        StrategyRegistryEntry(
            strategy_id="ENSEMBLE",
            module_path="strategies/ensemble.py",
            strategy_kind="deferred",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="ensemble_signal",
            certification_supported=False,
            certification_track="not_certifiable",
            blocked_reason="Ensemble strategies must wait for children.",
        ),
    ]

    helpers = (
        "TRADE_BUILDER",
        "RISK_MANAGER",
        "POSITION_SIZER",
        "SOFT_SIGNAL",
        "PRO_DECISION_ADAPTER",
        "NIFTY_INTRADAY",
        "BANKNIFTY_INTRADAY",
        "SENSEX_INTRADAY",
        "VWAP_ORB",
        "ZERO_HERO",
        "PAIRS_ARBITRAGE",
        "VOLATILITY_TREND",
    )
    for helper_id in helpers:
        entries.append(
            StrategyRegistryEntry(
                strategy_id=helper_id,
                module_path=(
                    "strategies/pro_layer/pro_decision_adapter.py"
                    if helper_id == "PRO_DECISION_ADAPTER"
                    else f"strategies/{helper_id.lower()}.py"
                ),
                strategy_kind="helper_module",
                instrument_family="N/A",
                callable_name="",
                certification_supported=False,
                certification_track="not_certifiable",
                blocked_reason="Helper module",
            )
        )

    entries.append(
        StrategyRegistryEntry(
            strategy_id="TEST_STRAT",
            module_path="strategies/strategy_registry.py",
            strategy_kind="test_fixture",
            instrument_family="N/A",
            callable_name="",
            certification_supported=False,
            certification_track="not_certifiable",
            blocked_reason=(
                "Metadata-only test fixture defined in the registry; excluded from production"
            ),
        )
    )
    return tuple(entries)


def build_strategy_registry(
    entries: Iterable[StrategyRegistryEntry],
) -> Dict[str, StrategyRegistryEntry]:
    """Build a registry and fail closed on duplicate or inconsistent IDs."""

    registry: Dict[str, StrategyRegistryEntry] = {}
    for entry in entries:
        if not isinstance(entry, StrategyRegistryEntry):
            raise StrategyRegistryIntegrityError("registry_entry_invalid")
        strategy_id = str(entry.strategy_id or "").strip()
        if not strategy_id:
            raise StrategyRegistryIntegrityError("registry_id_missing")
        if strategy_id in registry:
            raise StrategyRegistryIntegrityError(f"duplicate_registry_id:{strategy_id}")
        registry[strategy_id] = entry
    return registry


def load_strategy_registry() -> Dict[str, StrategyRegistryEntry]:
    """Load the registry without importing registered strategy modules."""

    non_movement = _non_movement_entries()
    movement_entries = tuple(replace(entry) for entry in _MOVEMENT_REGISTRATIONS)
    entries = non_movement[:2] + movement_entries + non_movement[2:]
    return build_strategy_registry(entries)


def load_strategy_inventory(path: Path | str = DEFAULT_INVENTORY_PATH) -> dict[str, Any]:
    """Load the JSON-compatible YAML inventory without importing strategies."""

    inventory_path = Path(path)
    try:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise StrategyRegistryIntegrityError(
            f"inventory_load_failed:{inventory_path}:{type(exc).__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise StrategyRegistryIntegrityError("inventory_root_not_object")
    return payload


def validate_strategy_inventory(
    inventory: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Validate inventory IDs/aliases and return identifier-to-item mapping."""

    required_safety_values = {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
    }
    for field_name, expected in required_safety_values.items():
        if inventory.get(field_name) is not expected:
            raise StrategyRegistryIntegrityError(
                f"inventory_safety_field_invalid:{field_name}"
            )

    raw_items = inventory.get("strategies")
    if not isinstance(raw_items, list):
        raise StrategyRegistryIntegrityError("inventory_strategies_not_list")

    canonical_ids: set[str] = set()
    runtime_ids: set[str] = set()
    identifier_index: dict[str, Mapping[str, Any]] = {}

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise StrategyRegistryIntegrityError("inventory_item_not_object")
        raw_canonical_id = raw_item.get("id")
        if not isinstance(raw_canonical_id, str):
            raise StrategyRegistryIntegrityError("inventory_id_not_string")
        canonical_id = raw_canonical_id.strip()
        if not canonical_id:
            raise StrategyRegistryIntegrityError("inventory_id_missing")
        if canonical_id in canonical_ids:
            raise StrategyRegistryIntegrityError(f"duplicate_inventory_id:{canonical_id}")
        canonical_ids.add(canonical_id)

        raw_role = raw_item.get("role")
        if not isinstance(raw_role, str):
            raise StrategyRegistryIntegrityError(
                f"inventory_role_not_string:{canonical_id}"
            )
        role = raw_role.strip()
        if role not in ALLOWED_INVENTORY_ROLES:
            raise StrategyRegistryIntegrityError(
                f"inventory_role_unknown:{canonical_id}:{role}"
            )
        if raw_item.get("execution_eligible") is not False:
            raise StrategyRegistryIntegrityError(
                f"inventory_execution_eligible_must_be_false:{canonical_id}"
            )

        raw_runtime_id = raw_item.get("runtime_strategy_id")
        if raw_runtime_id is None:
            raise StrategyRegistryIntegrityError(
                f"inventory_runtime_id_missing:{canonical_id}"
            )
        if not isinstance(raw_runtime_id, str):
            raise StrategyRegistryIntegrityError(
                f"inventory_runtime_id_not_string:{canonical_id}"
            )
        runtime_id = raw_runtime_id.strip()
        if not runtime_id:
            raise StrategyRegistryIntegrityError(
                f"inventory_runtime_id_missing:{canonical_id}"
            )
        if runtime_id in runtime_ids:
            raise StrategyRegistryIntegrityError(
                f"duplicate_inventory_runtime_id:{runtime_id}"
            )
        runtime_ids.add(runtime_id)

        raw_canonical_profile_id = raw_item.get("canonical_profile_id")
        if not isinstance(raw_canonical_profile_id, str):
            raise StrategyRegistryIntegrityError(
                f"inventory_canonical_profile_id_not_string:{canonical_id}"
            )
        canonical_profile_id = raw_canonical_profile_id.strip()
        if not canonical_profile_id:
            raise StrategyRegistryIntegrityError(
                f"inventory_canonical_profile_id_missing:{canonical_id}"
            )

        raw_profile_version = raw_item.get("profile_version")
        if not isinstance(raw_profile_version, str):
            raise StrategyRegistryIntegrityError(
                f"inventory_profile_version_not_string:{canonical_id}"
            )
        profile_version = raw_profile_version.strip()
        if not profile_version:
            raise StrategyRegistryIntegrityError(
                f"inventory_profile_version_missing:{canonical_id}"
            )
        if runtime_id.rsplit("_", 1)[-1] != profile_version:
            raise StrategyRegistryIntegrityError(
                f"inventory_profile_version_runtime_mismatch:{canonical_id}"
            )
        if canonical_profile_id.rsplit("_", 1)[-1] != profile_version:
            raise StrategyRegistryIntegrityError(
                f"inventory_profile_version_canonical_mismatch:{canonical_id}"
            )

        raw_aliases = raw_item.get("aliases", [])
        if not isinstance(raw_aliases, list):
            raise StrategyRegistryIntegrityError(
                f"inventory_aliases_not_list:{canonical_id}"
            )
        identifiers = (canonical_id, *tuple(raw_aliases))
        for raw_identifier in identifiers:
            if not isinstance(raw_identifier, str):
                raise StrategyRegistryIntegrityError(
                    f"inventory_alias_not_string:{canonical_id}"
                )
            identifier = raw_identifier.strip()
            if not identifier:
                raise StrategyRegistryIntegrityError(
                    f"inventory_alias_empty:{canonical_id}"
                )
            if identifier in identifier_index:
                other = str(identifier_index[identifier].get("id"))
                raise StrategyRegistryIntegrityError(
                    f"ambiguous_inventory_identifier:{identifier}:{other}:{canonical_id}"
                )
            identifier_index[identifier] = raw_item

    return identifier_index


def _module_name_from_path(module_path: str) -> str:
    normalized = str(module_path or "").strip().replace("\\", "/")
    if not normalized.endswith(".py") or normalized.startswith("/") or ".." in normalized.split("/"):
        raise StrategyRegistryIntegrityError(f"registry_module_path_invalid:{module_path}")
    return normalized[:-3].replace("/", ".")


def _ast_literal_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _ast_literal_value(node.operand)
        if isinstance(value, (int, float)):
            return -value
    raise StrategyRegistryIntegrityError("embedded_profile_default_not_literal")


def _extract_embedded_profile_defaults(entry: StrategyRegistryEntry) -> dict[str, Any]:
    module_file = REPO_ROOT / entry.module_path
    try:
        tree = ast.parse(module_file.read_text(encoding="utf-8"), filename=str(module_file))
    except StrategyRegistryIntegrityError:
        raise
    except Exception as exc:
        raise StrategyRegistryIntegrityError(
            f"embedded_profile_defaults_parse_failed:{entry.strategy_id}:{type(exc).__name__}"
        ) from exc

    defaults: dict[str, Any] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get":
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "params":
            continue
        if len(node.args) != 2:
            continue
        key_node, value_node = node.args
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        key = str(key_node.value).strip()
        if not key:
            continue
        try:
            value = _ast_literal_value(value_node)
        except StrategyRegistryIntegrityError as exc:
            raise StrategyRegistryIntegrityError(
                f"embedded_profile_default_not_literal:{entry.strategy_id}:{key}"
            ) from exc
        if key in defaults and defaults[key] != value:
            raise StrategyRegistryIntegrityError(
                f"embedded_profile_default_ambiguous:{entry.strategy_id}:{key}"
            )
        defaults[key] = value

    return defaults


def _profile_integrity_row(
    *,
    entry: StrategyRegistryEntry,
    inventory_item: Mapping[str, Any],
    module_strategy_id: str,
) -> StrategyProfileIntegrityRow:
    requested_profile_id = str(entry.runtime_strategy_id or "").strip()
    inventory_canonical_id = str(inventory_item.get("id") or "").strip()
    public_compatibility_id = inventory_canonical_id
    aliases = inventory_item.get("aliases", [])
    if isinstance(aliases, list) and aliases:
        first_alias = str(aliases[0] or "").strip()
        if first_alias:
            public_compatibility_id = first_alias

    canonical_profile_id = str(inventory_item.get("canonical_profile_id") or "").strip()
    profile_version = str(inventory_item.get("profile_version") or "").strip()
    profile = get_default_profile(requested_profile_id, profile_version)
    classification = classify_profile_resolution(requested_profile_id, profile_version)
    embedded_defaults = _extract_embedded_profile_defaults(entry)
    declared_embedded_defaults = EMBEDDED_PROFILE_DEFAULTS.get(requested_profile_id)
    if declared_embedded_defaults is None:
        classification = AMBIGUOUS_PROFILE
    elif dict(declared_embedded_defaults) != dict(embedded_defaults):
        classification = PROFILE_VALUE_DRIFT
        profile = None

    if profile is None:
        if classification == PROFILE_VALUE_DRIFT:
            profile_id_present_in_store = canonical_profile_id or None
            resolution_source = None
        elif classification == EMBEDDED_FALLBACK:
            profile_id_present_in_store = None
            resolution_source = EMBEDDED_FALLBACK
        elif classification == MISSING_PROFILE:
            profile_id_present_in_store = None
            resolution_source = None
        else:
            profile_id_present_in_store = None
            resolution_source = classification
        parameter_keys = tuple(sorted(str(key) for key in (declared_embedded_defaults or embedded_defaults)))
        effective_parameter_values: tuple[tuple[str, Any], ...] = ()
        parameter_hash = None
        compatibility_alias = None
    else:
        effective_params = dict(profile.params)
        if dict(embedded_defaults) != effective_params:
            classification = PROFILE_VALUE_DRIFT
            profile_id_present_in_store = canonical_profile_id or None
            resolution_source = None
            parameter_keys = tuple(sorted(str(key) for key in effective_params))
            effective_parameter_values = ()
            parameter_hash = None
            compatibility_alias = None
        else:
            profile_id_present_in_store = profile.resolved_profile_id
            resolution_source = profile.resolution_source
            parameter_keys = tuple(sorted(str(key) for key in effective_params))
            effective_parameter_values = tuple(
                (str(key), effective_params[key]) for key in sorted(effective_params)
            )
            parameter_hash = profile.parameter_hash
            compatibility_alias = (
                f"{requested_profile_id}->{profile.resolved_profile_id}"
                if profile.resolution_source == COMPATIBILITY_ALIAS
                else None
            )

    embedded_default_keys = tuple(sorted(str(key) for key in embedded_defaults))
    embedded_default_values = tuple(
        (str(key), embedded_defaults[key]) for key in sorted(embedded_defaults)
    )
    return StrategyProfileIntegrityRow(
        inventory_canonical_id=inventory_canonical_id,
        public_compatibility_id=public_compatibility_id,
        runtime_strategy_id=requested_profile_id,
        module_strategy_id=str(module_strategy_id or "").strip(),
        profile_id_requested_by_generator=requested_profile_id,
        canonical_profile_id=canonical_profile_id,
        profile_id_present_in_store=profile_id_present_in_store,
        profile_version=profile_version,
        parameter_keys=parameter_keys,
        embedded_default_keys=embedded_default_keys,
        effective_parameter_values=effective_parameter_values,
        embedded_default_values=embedded_default_values,
        resolution_source=resolution_source,
        compatibility_alias=compatibility_alias,
        parameter_hash=parameter_hash,
        mismatch_classification=classification,
    )


def build_strategy_profile_integrity_rows(
    registry: Mapping[str, StrategyRegistryEntry] | None = None,
    inventory: Mapping[str, Any] | None = None,
) -> tuple[StrategyProfileIntegrityRow, ...]:
    """Build the inventory/profile reconciliation matrix for the 12 movement components."""

    expected_registry = load_strategy_registry()
    registry_map = dict(expected_registry if registry is None else registry)
    inventory_payload = dict(load_strategy_inventory() if inventory is None else inventory)
    inventory_index = validate_strategy_inventory(inventory_payload)

    rows: list[StrategyProfileIntegrityRow] = []
    for expected_entry in get_movement_strategy_entries():
        entry = registry_map.get(expected_entry.strategy_id)
        if entry is None:
            raise StrategyRegistryIntegrityError(
                f"movement_registry_entry_missing:{expected_entry.strategy_id}"
            )
        inventory_item = inventory_index.get(entry.strategy_id)
        if inventory_item is None:
            raise StrategyRegistryIntegrityError(
                f"registry_id_not_in_inventory:{entry.strategy_id}"
            )

        module = importlib.import_module(_module_name_from_path(entry.module_path))
        rows.append(
            _profile_integrity_row(
                entry=entry,
                inventory_item=inventory_item,
                module_strategy_id=str(getattr(module, "STRATEGY_ID", "") or ""),
            )
        )

    return tuple(rows)


def resolve_registered_module(entry: StrategyRegistryEntry) -> Any:
    """Import one exact registered module reference or fail closed."""

    module_file = REPO_ROOT / entry.module_path
    if not module_file.is_file():
        raise StrategyRegistryIntegrityError(
            f"registered_module_missing:{entry.strategy_id}:{entry.module_path}"
        )
    try:
        return importlib.import_module(_module_name_from_path(entry.module_path))
    except Exception as exc:
        raise StrategyRegistryIntegrityError(
            f"registered_module_import_failed:{entry.strategy_id}:{type(exc).__name__}"
        ) from exc


def resolve_registered_callable(entry: StrategyRegistryEntry) -> Callable[..., Any]:
    """Resolve one exact, explicit callable reference or fail closed."""

    if not entry.callable_name:
        raise StrategyRegistryIntegrityError(
            f"registered_callable_missing:{entry.strategy_id}"
        )

    target: Any = resolve_registered_module(entry)
    for part in entry.callable_name.split("."):
        if not hasattr(target, part):
            raise StrategyRegistryIntegrityError(
                f"registered_callable_not_found:{entry.strategy_id}:{entry.callable_name}"
            )
        target = getattr(target, part)
    if not callable(target):
        raise StrategyRegistryIntegrityError(
            f"registered_target_not_callable:{entry.strategy_id}:{entry.callable_name}"
        )
    return target


def validate_candidate_generator_signature(
    entry: StrategyRegistryEntry,
    handler: Callable[..., Any],
) -> None:
    signature = inspect.signature(handler)
    parameters = signature.parameters
    positional = [
        parameter
        for parameter in parameters.values()
        if parameter.kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    if [parameter.name for parameter in positional[:2]] != ["ctx", "regime"]:
        raise StrategyRegistryIntegrityError(
            f"candidate_generator_interface_invalid:{entry.strategy_id}"
        )
    try:
        signature.bind(object(), object())
    except TypeError as exc:
        raise StrategyRegistryIntegrityError(
            f"candidate_generator_not_positionally_invocable:{entry.strategy_id}"
        ) from exc
    required_extra = [
        name
        for name, parameter in parameters.items()
        if name not in {"ctx", "regime"}
        and parameter.default is inspect.Parameter.empty
        and parameter.kind
        not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    ]
    if required_extra:
        raise StrategyRegistryIntegrityError(
            f"candidate_generator_required_extra_args:{entry.strategy_id}:{','.join(required_extra)}"
        )


def validate_strategy_registry_integrity(
    registry: Mapping[str, StrategyRegistryEntry] | None = None,
    inventory: Mapping[str, Any] | None = None,
) -> tuple[StrategyRegistryEntry, ...]:
    """Reconcile and mechanically validate inventory-managed movement entries.

    This function imports all registered modules and resolves all declared
    callables. It applies candidate-generator interface and inventory mapping
    checks to the twelve movement components. It does not invoke generators,
    enforce quarantine, alter registry ordering, or certify non-movement runtime
    behavior.
    """

    expected_registry = load_strategy_registry()
    registry_map = dict(expected_registry if registry is None else registry)
    inventory_payload = dict(load_strategy_inventory() if inventory is None else inventory)
    inventory_index = validate_strategy_inventory(inventory_payload)

    unknown_registry_ids = set(registry_map).difference(expected_registry)
    if unknown_registry_ids:
        raise StrategyRegistryIntegrityError(
            f"registry_component_absent_from_inventory:{sorted(unknown_registry_ids)[0]}"
        )
    missing_registry_ids = set(expected_registry).difference(registry_map)
    if missing_registry_ids:
        raise StrategyRegistryIntegrityError(
            f"registry_component_missing:{sorted(missing_registry_ids)[0]}"
        )

    expected_movement_entries = get_movement_strategy_entries()
    expected_movement_ids = {entry.strategy_id for entry in expected_movement_entries}
    expected_non_inventory_ids = set(expected_registry).difference(expected_movement_ids)
    if expected_non_inventory_ids != set(NON_INVENTORY_REGISTRY_ALLOWLIST):
        raise StrategyRegistryIntegrityError("non_inventory_allowlist_drift")

    for registry_key, expected_entry in expected_registry.items():
        entry = registry_map[registry_key]
        if not isinstance(entry, StrategyRegistryEntry):
            raise StrategyRegistryIntegrityError(
                f"registry_entry_invalid:{registry_key}"
            )
        if registry_key != entry.strategy_id:
            raise StrategyRegistryIntegrityError(
                f"registry_key_id_mismatch:{registry_key}:{entry.strategy_id}"
            )
        if entry != expected_entry:
            classification = (
                "movement_registry_entry_drift"
                if registry_key in expected_movement_ids
                else "registry_entry_drift"
            )
            raise StrategyRegistryIntegrityError(f"{classification}:{registry_key}")

    for entry in registry_map.values():
        resolve_registered_module(entry)
        if entry.callable_name:
            resolve_registered_callable(entry)

    resolved_by_inventory_id: dict[str, list[str]] = {}
    validated: list[StrategyRegistryEntry] = []
    profile_rows: list[StrategyProfileIntegrityRow] = []
    for expected_entry in expected_movement_entries:
        entry = registry_map.get(expected_entry.strategy_id)
        if entry is None:
            raise StrategyRegistryIntegrityError(
                f"movement_registry_entry_missing:{expected_entry.strategy_id}"
            )
        inventory_item = inventory_index.get(entry.strategy_id)
        if inventory_item is None:
            raise StrategyRegistryIntegrityError(
                f"registry_id_not_in_inventory:{entry.strategy_id}"
            )
        canonical_id = str(inventory_item.get("id"))
        if canonical_id != entry.inventory_id:
            raise StrategyRegistryIntegrityError(
                f"registry_inventory_id_mismatch:{entry.strategy_id}:{canonical_id}:{entry.inventory_id}"
            )
        if str(inventory_item.get("role")) != entry.role:
            raise StrategyRegistryIntegrityError(
                f"registry_inventory_role_mismatch:{entry.strategy_id}"
            )
        inventory_runtime_id = str(inventory_item.get("runtime_strategy_id") or "").strip()
        if inventory_runtime_id and inventory_runtime_id != entry.runtime_strategy_id:
            raise StrategyRegistryIntegrityError(
                f"registry_runtime_id_mismatch:{entry.strategy_id}"
            )

        handler = resolve_registered_callable(entry)
        validate_candidate_generator_signature(entry, handler)
        module = importlib.import_module(_module_name_from_path(entry.module_path))
        if getattr(module, "STRATEGY_ID", None) != entry.runtime_strategy_id:
            raise StrategyRegistryIntegrityError(
                f"module_runtime_id_mismatch:{entry.strategy_id}"
            )
        if getattr(module, "MOVEMENT_TYPE", None) != entry.movement_type:
            raise StrategyRegistryIntegrityError(
                f"module_movement_type_mismatch:{entry.strategy_id}"
            )

        movement_package = importlib.import_module("strategies.movement")
        if entry.callable_name not in getattr(movement_package, "__all__", ()):
            raise StrategyRegistryIntegrityError(
                f"registered_callable_not_exported:{entry.strategy_id}:{entry.callable_name}"
            )
        if getattr(movement_package, entry.callable_name, None) is not handler:
            raise StrategyRegistryIntegrityError(
                f"registered_export_identity_mismatch:{entry.strategy_id}"
            )

        profile_row = _profile_integrity_row(
            entry=entry,
            inventory_item=inventory_item,
            module_strategy_id=str(getattr(module, "STRATEGY_ID", "") or ""),
        )
        if profile_row.profile_id_present_in_store != str(
            inventory_item.get("canonical_profile_id") or ""
        ).strip():
            raise StrategyRegistryIntegrityError(
                f"profile_resolution_canonical_mismatch:{entry.strategy_id}"
            )
        if profile_row.mismatch_classification in {MISSING_PROFILE, PROFILE_VALUE_DRIFT, AMBIGUOUS_PROFILE}:
            raise StrategyRegistryIntegrityError(
                f"profile_resolution_mismatch:{entry.strategy_id}:{profile_row.mismatch_classification}"
            )
        profile_rows.append(profile_row)
        resolved_by_inventory_id.setdefault(canonical_id, []).append(entry.strategy_id)
        validated.append(entry)

    canonical_items = {
        str(item.get("id")): item for item in inventory_payload.get("strategies", [])
    }
    for canonical_id in canonical_items:
        registry_ids = resolved_by_inventory_id.get(canonical_id, [])
        if len(registry_ids) != 1:
            raise StrategyRegistryIntegrityError(
                f"inventory_registry_mapping_count:{canonical_id}:{len(registry_ids)}"
            )
    if len(profile_rows) != len(expected_movement_entries):
        raise StrategyRegistryIntegrityError("profile_integrity_row_count_mismatch")

    return tuple(validated)


registry = load_strategy_registry()


__all__ = [
    "ALLOWED_INVENTORY_ROLES",
    "DEFAULT_INVENTORY_PATH",
    "NON_INVENTORY_REGISTRY_ALLOWLIST",
    "StrategyProfileIntegrityRow",
    "StrategyRegistryEntry",
    "StrategyRegistryIntegrityError",
    "build_strategy_registry",
    "build_strategy_profile_integrity_rows",
    "get_movement_strategies",
    "get_movement_strategy_entries",
    "load_strategy_inventory",
    "load_strategy_registry",
    "registry",
    "resolve_registered_callable",
    "resolve_registered_module",
    "validate_strategy_inventory",
    "validate_candidate_generator_signature",
    "validate_strategy_registry_integrity",
]
