from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any


class AuthorityStrategyMatrixError(RuntimeError):
    """Base failure for strategy authority matrix construction."""


class AuthorityStrategyRegistryError(AuthorityStrategyMatrixError):
    """An input registry is malformed or internally contradictory."""


class AuthorityStrategyAliasError(AuthorityStrategyRegistryError):
    """An alias resolves ambiguously or conflicts with its canonical lane."""


class AuthorityStrategyReconciliationError(AuthorityStrategyMatrixError):
    """The input registries do not describe the same canonical lane set."""


_NO_TRADE_STATUS = "NO_TRADE_FILTER"
_MULTI_ASSET_CATEGORIES = frozenset({"cross_asset", "multi_asset"})
_MULTI_ASSET_LANES = frozenset({"CONSTITUENT_LEAD_LAG", "CONSTITUENT_BREADTH"})
_CAUSAL_ONLY = "CAUSAL_ONLY"
_SIGNAL_AUTHORITY_CONCLUSIONS = frozenset(
    {
        "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER",
        "VALID_PRECOMPUTED_SIGNALS_WITH_LIMITATIONS",
        "INSUFFICIENT_PROVENANCE",
        "POST_OUTCOME_OR_TUNED",
        "HOLDOUT_CONTAMINATED",
        "INVALIDATED_HISTORICAL_EVIDENCE",
        "INVALID_SIGNAL_LEDGER",
    }
)
_EXECUTABLE_SIGNAL_AUTHORITIES = frozenset(
    {
        "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER",
        "VALID_PRECOMPUTED_SIGNALS_WITH_LIMITATIONS",
        "NOT_APPLICABLE",
    }
)


def _require_rows(name: str, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(rows, (str, bytes, Mapping)):
        raise AuthorityStrategyRegistryError(f"registry_not_row_sequence registry={name}")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise AuthorityStrategyRegistryError(
                f"registry_row_not_mapping registry={name} index={index}"
            )
        result.append(deepcopy(dict(row)))
    return result


def _require_id(row: Mapping[str, Any], *, registry: str, index: int) -> str:
    lane_id = row.get("canonical_strategy_id")
    if not isinstance(lane_id, str) or not lane_id.strip():
        raise AuthorityStrategyRegistryError(
            f"missing_canonical_strategy_id registry={registry} index={index}"
        )
    return lane_id.strip()


def _alias_key(value: str) -> str:
    return "_".join(value.strip().upper().replace("-", " ").split())


def _build_alias_authority(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], set[str]]:
    alias_to_canonical: dict[str, str] = {}
    aliases_by_canonical: dict[str, tuple[str, ...]] = {}
    canonical_ids: set[str] = set()
    for index, row in enumerate(rows):
        canonical = _require_id(row, registry="strategy_alias_registry", index=index)
        if canonical in canonical_ids:
            raise AuthorityStrategyAliasError(
                f"duplicate_canonical_alias_row canonical_strategy_id={canonical}"
            )
        aliases = row.get("aliases")
        if not isinstance(aliases, list) or any(
            not isinstance(alias, str) or not alias.strip() for alias in aliases
        ):
            raise AuthorityStrategyAliasError(
                f"invalid_aliases canonical_strategy_id={canonical}"
            )
        ordered_aliases = tuple(dict.fromkeys([canonical, *(alias.strip() for alias in aliases)]))
        canonical_ids.add(canonical)
        aliases_by_canonical[canonical] = ordered_aliases
        for alias in ordered_aliases:
            key = _alias_key(alias)
            owner = alias_to_canonical.get(key)
            if owner is not None and owner != canonical:
                raise AuthorityStrategyAliasError(
                    f"alias_collision alias={alias!r} owners={owner},{canonical}"
                )
            alias_to_canonical[key] = canonical
    return alias_to_canonical, aliases_by_canonical, canonical_ids


def _collapse_registry(
    *,
    registry: str,
    rows: list[dict[str, Any]],
    alias_to_canonical: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    collapsed: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        supplied_id = _require_id(row, registry=registry, index=index)
        canonical = alias_to_canonical.get(_alias_key(supplied_id))
        if canonical is None:
            raise AuthorityStrategyReconciliationError(
                f"unknown_strategy_lane registry={registry} lane={supplied_id}"
            )
        normalized = dict(row)
        normalized["canonical_strategy_id"] = canonical
        existing = collapsed.get(canonical)
        if existing is not None and existing != normalized:
            raise AuthorityStrategyRegistryError(
                f"conflicting_alias_rows registry={registry} canonical_strategy_id={canonical}"
            )
        collapsed[canonical] = normalized
    return collapsed


def _reconcile_exact_lanes(
    *,
    expected: set[str],
    inventory: Mapping[str, object],
    readiness: Mapping[str, object],
) -> None:
    for registry, actual in (
        ("strategy_implementation_inventory", set(inventory)),
        ("all_strategy_execution_readiness", set(readiness)),
    ):
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing or unexpected:
            raise AuthorityStrategyReconciliationError(
                f"canonical_lane_mismatch registry={registry} missing={missing} unexpected={unexpected}"
            )


def _index_signal_assessments(
    rows: list[dict[str, Any]],
    *,
    alias_to_canonical: Mapping[str, str],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        supplied_id = _require_id(row, registry="signal_ledger_assessments", index=index)
        canonical = alias_to_canonical.get(_alias_key(supplied_id))
        if canonical is None:
            raise AuthorityStrategyReconciliationError(
                f"unknown_strategy_lane registry=signal_ledger_assessments lane={supplied_id}"
            )
        ledger_id = row.get("canonical_signal_ledger_id", row.get("signal_ledger_id"))
        conclusion = row.get("authority_conclusion")
        if not isinstance(ledger_id, str) or not ledger_id.strip():
            raise AuthorityStrategyRegistryError(
                f"missing_signal_ledger_id canonical_strategy_id={canonical} index={index}"
            )
        if conclusion not in _SIGNAL_AUTHORITY_CONCLUSIONS:
            raise AuthorityStrategyRegistryError(
                f"invalid_signal_authority_conclusion canonical_strategy_id={canonical} index={index} conclusion={conclusion}"
            )
        key = (canonical, ledger_id.strip())
        normalized = dict(row)
        normalized["canonical_strategy_id"] = canonical
        normalized["canonical_signal_ledger_id"] = ledger_id.strip()
        existing = indexed.get(key)
        if existing is not None and existing != normalized:
            raise AuthorityStrategyRegistryError(
                f"conflicting_signal_assessments canonical_strategy_id={canonical} ledger_id={ledger_id.strip()}"
            )
        indexed[key] = normalized
    return indexed


def _is_multi_asset(canonical: str, inventory: Mapping[str, Any]) -> bool:
    return canonical in _MULTI_ASSET_LANES or str(inventory.get("category", "")).lower() in _MULTI_ASSET_CATEGORIES


def _build_lane(
    *,
    canonical: str,
    aliases: tuple[str, ...],
    inventory: Mapping[str, Any],
    readiness: Mapping[str, Any],
    signal_assessments: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    status = readiness.get("status")
    blocker = readiness.get("remaining_blocker")
    is_no_trade = status == _NO_TRADE_STATUS or canonical == "NO_TRADE_CHOP"
    is_multi_asset = _is_multi_asset(canonical, inventory)
    temporal_contract = inventory.get("temporal_contract")

    if is_no_trade:
        if status != _NO_TRADE_STATUS or blocker != _NO_TRADE_STATUS:
            raise AuthorityStrategyReconciliationError(
                f"invalid_no_trade_semantics canonical_strategy_id={canonical} status={status} blocker={blocker}"
            )
        lane_kind = "NO_TRADE_FILTER"
        dataset_selection: Any = None
        signal_selection: Any = None
        signal_ledger_status = "NOT_APPLICABLE"
        signal_authority = "NOT_APPLICABLE"
        execution_eligible = False
    elif is_multi_asset:
        lane_kind = "MULTI_ASSET_STRATEGY"
        dataset_selection = None
        signal_selection = None
        if temporal_contract == _CAUSAL_ONLY:
            signal_ledger_status = "NOT_APPLICABLE"
            signal_authority = "NOT_APPLICABLE"
        else:
            signal_ledger_status = "NO_SIGNAL_LEDGER"
            signal_authority = "UNRESOLVED"
        execution_eligible = False
        if not blocker:
            blocker = "MULTI_ASSET_DATASET_AUTHORITY_REQUIRED"
        if status in {"READY_FOR_CAUSAL_EXECUTION", "VALID_PRECOMPUTED_SIGNALS"}:
            status = "MULTI_ASSET_AUTHORITY_REQUIRED"
    else:
        lane_kind = "SINGLE_ASSET_STRATEGY"
        dataset_selection = readiness.get("selected_canonical_dataset")
        signal_selection = readiness.get("selected_canonical_signal_ledger")
        assessment = None
        if isinstance(signal_selection, str) and signal_selection.strip():
            signal_selection = signal_selection.strip()
            assessment = signal_assessments.get((canonical, signal_selection.strip()))
        if assessment is not None:
            signal_ledger_status = "LINKED"
            signal_authority = assessment["authority_conclusion"]
        elif temporal_contract == _CAUSAL_ONLY:
            signal_ledger_status = "NOT_APPLICABLE"
            signal_authority = "NOT_APPLICABLE"
        elif signal_selection:
            signal_ledger_status = "NO_SIGNAL_LEDGER"
            signal_authority = "UNRESOLVED"
        else:
            signal_selection = None
            signal_ledger_status = "NO_SIGNAL_LEDGER"
            signal_authority = "UNRESOLVED"
        execution_eligible = (
            status in {"READY_FOR_CAUSAL_EXECUTION", "VALID_PRECOMPUTED_SIGNALS"}
            and signal_authority in _EXECUTABLE_SIGNAL_AUTHORITIES
        )

    return {
        "canonical_strategy_id": canonical,
        "aliases": list(aliases),
        "lane_kind": lane_kind,
        "category": inventory.get("category"),
        "implementation_path": inventory.get("implementation_path"),
        "implementation_hash": inventory.get("implementation_blob_hash"),
        "working_tree_file_hash": inventory.get("working_tree_file_hash"),
        "implementation_authority": readiness.get("implementation_authority"),
        "parameter_owner": inventory.get("parameter_owner"),
        "resolved_required_parameters": list(inventory.get("resolved_required_parameters") or []),
        "parameter_authority": readiness.get("parameter_authority"),
        "temporal_contract": inventory.get("temporal_contract"),
        "required_input_data": inventory.get("required_input_data"),
        "valid_precomputed_signal_ledger": inventory.get("valid_precomputed_signal_ledger"),
        "invalidated_evidence": list(inventory.get("invalidated_evidence") or []),
        "development_split_authority": inventory.get("development_split_authority"),
        "holdout_authority": inventory.get("holdout_authority"),
        "split_authority": readiness.get("split_authority"),
        "development_session_count": readiness.get("development_session_count"),
        "holdout_session_count": readiness.get("holdout_session_count"),
        "option_data_requirements": inventory.get("option_data_requirements"),
        "option_coverage_readiness": readiness.get("option_coverage_readiness"),
        "selected_canonical_dataset": dataset_selection,
        "selected_canonical_signal_ledger": signal_selection,
        "signal_ledger_status": signal_ledger_status,
        "signal_authority": signal_authority,
        "remaining_blocker": blocker,
        "recommended_next_action": readiness.get("recommended_next_action"),
        "inventory_status": inventory.get("current_status"),
        "authority_status": status,
        "execution_eligible": execution_eligible,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def build_authority_strategy_matrix(
    *,
    strategy_implementation_inventory: Iterable[Mapping[str, Any]],
    strategy_alias_registry: Iterable[Mapping[str, Any]],
    all_strategy_execution_readiness: Iterable[Mapping[str, Any]],
    signal_ledger_assessments: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Build one authority row per exact canonical strategy lane."""

    alias_rows = _require_rows("strategy_alias_registry", strategy_alias_registry)
    inventory_rows = _require_rows(
        "strategy_implementation_inventory", strategy_implementation_inventory
    )
    readiness_rows = _require_rows(
        "all_strategy_execution_readiness", all_strategy_execution_readiness
    )
    signal_assessment_rows = _require_rows(
        "signal_ledger_assessments", signal_ledger_assessments
    )
    alias_to_canonical, aliases_by_canonical, canonical_ids = _build_alias_authority(alias_rows)
    signal_assessments = _index_signal_assessments(
        signal_assessment_rows,
        alias_to_canonical=alias_to_canonical,
    )
    inventory = _collapse_registry(
        registry="strategy_implementation_inventory",
        rows=inventory_rows,
        alias_to_canonical=alias_to_canonical,
    )
    readiness = _collapse_registry(
        registry="all_strategy_execution_readiness",
        rows=readiness_rows,
        alias_to_canonical=alias_to_canonical,
    )
    _reconcile_exact_lanes(
        expected=canonical_ids,
        inventory=inventory,
        readiness=readiness,
    )
    return [
        _build_lane(
            canonical=canonical,
            aliases=aliases_by_canonical[canonical],
            inventory=inventory[canonical],
            readiness=readiness[canonical],
            signal_assessments=signal_assessments,
        )
        for canonical in sorted(canonical_ids)
    ]


__all__ = [
    "AuthorityStrategyAliasError",
    "AuthorityStrategyMatrixError",
    "AuthorityStrategyReconciliationError",
    "AuthorityStrategyRegistryError",
    "build_authority_strategy_matrix",
]
