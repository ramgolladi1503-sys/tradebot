from __future__ import annotations

from pathlib import Path

from .repo_inventory import discover_strategy_files, git_commit_for_path, load_canonical_strategy_registry, historical_hypotheses
from .source_contract import SourceContract


def build_strategy_source_registry(repo_root: Path) -> dict[str, SourceContract]:
    registry = load_canonical_strategy_registry(repo_root)
    hypothesis_claims = historical_hypotheses(repo_root)
    contracts: dict[str, SourceContract] = {}

    for strategy_id, entry in registry.items():
        module_path = str(entry.get("module_path") or "")
        current_paths = tuple(p for p in (module_path,) if p)
        impl_paths = []
        impl_hashes = []
        for path in current_paths:
            discovered_path, sha = discover_strategy_files(repo_root, path)
            if discovered_path:
                impl_paths.append(discovered_path)
                impl_hashes.append(sha)
        kind = str(entry.get("strategy_kind") or "")
        blocked_reason = str(entry.get("blocked_reason") or "")
        if strategy_id == "NO_TRADE_CHOP":
            eligibility = "NO_TRADE_FILTER"
            domain = "GENERIC_RESEARCH_REPORT"
        elif kind == "candidate_generator_strategy":
            eligibility = "DIRECTIONAL_LONG_OPTION_ELIGIBLE"
            domain = "STRATEGY_SIGNAL_ARTIFACT"
        elif strategy_id in {"PAIRS_ARBITRAGE"}:
            eligibility = "MULTI_ASSET_OR_PAIR"
            domain = "HISTORICAL_STRATEGY_IMPLEMENTATION"
        elif kind in {"helper_module", "aggregate_engine"}:
            eligibility = "HELPER_OR_AGGREGATE"
            domain = "OPTION_CONTRACT_AUTHORITY"
        elif not entry.get("module_exists_at_foundation", False):
            eligibility = "IMPLEMENTATION_MISSING"
            domain = "CURRENT_MASTER_DIAGNOSTIC"
        else:
            eligibility = "HISTORICAL_ONLY" if blocked_reason else "HELPER_OR_AGGREGATE"
            domain = "HISTORICAL_STRATEGY_IMPLEMENTATION"

        contracts[strategy_id] = SourceContract(
            strategy_or_hypothesis_id=strategy_id,
            canonical_alias_group=strategy_id,
            economic_family=_economic_family_for(strategy_id, kind),
            directional_eligibility=eligibility,
            current_implementation_paths=tuple(impl_paths),
            implementation_file_hashes=tuple(impl_hashes),
            current_implementation_commit=git_commit_for_path(repo_root, module_path) if module_path else "",
            historical_branch_candidates=("origin/main", "HEAD"),
            historical_commit_candidates=(),
            signal_artifact_patterns=_signal_patterns_for(strategy_id, kind),
                candidate_state_patterns=_candidate_state_patterns(strategy_id, kind),
                required_dataset_patterns=_required_dataset_patterns(strategy_id, kind),
                required_columns=_required_columns(strategy_id, kind),
            contract_paths=(f"strategies/{module_path}" if module_path else "",),
            contract_hashes=tuple(impl_hashes),
            known_evidence_roots=("research/option_e2e_recertification_v4", "runtime/strategy_validation", "runtime/market_data/upstox"),
            development_holdout_policy="fail_closed",
            discovery_status="DISCOVERED_FROM_REPOSITORY" if impl_paths or not blocked_reason else "BLOCKED_FROM_REPOSITORY",
            source_domain=domain,
        )

    for hypothesis_path, claim in hypothesis_claims.items():
        name = str(claim.get("path", hypothesis_path)).rsplit("/", 1)[-1]
        contracts[name] = SourceContract(
            strategy_or_hypothesis_id=name,
            canonical_alias_group=name,
            economic_family="historical_hypothesis",
            directional_eligibility="HISTORICAL_ONLY",
            current_implementation_paths=(),
            implementation_file_hashes=(),
            current_implementation_commit="",
            historical_branch_candidates=("origin/main", "HEAD"),
            historical_commit_candidates=tuple(),
            signal_artifact_patterns=(),
            candidate_state_patterns=(),
            required_dataset_patterns=(),
            required_columns=(),
            contract_paths=(hypothesis_path,),
            contract_hashes=(str(claim.get("sha256") or ""),),
            known_evidence_roots=("docs/agent_reviews",),
            development_holdout_policy="fail_closed",
            discovery_status=str(claim.get("claim_class") or "UNKNOWN"),
            source_domain="GENERIC_RESEARCH_REPORT",
        )
    return contracts


def _economic_family_for(strategy_id: str, kind: str) -> str:
    if strategy_id == "NO_TRADE_CHOP":
        return "no_trade_filter"
    if strategy_id == "PAIRS_ARBITRAGE":
        return "multi_asset_pair"
    if kind == "aggregate_engine":
        return "aggregate_engine"
    if kind == "helper_module":
        return "helper_module"
    return "directional_strategy"


def _signal_patterns_for(strategy_id: str, kind: str) -> tuple[str, ...]:
    if strategy_id in {"COMPRESSION_BREAKOUT", "EVENT_VOLATILITY_EXPANSION", "EXHAUSTION_REVERSAL", "FAILED_BREAKOUT_TRAP", "LATE_DAY_MOMENTUM", "MEAN_REVERSION_EXTENSION", "OPENING_DRIVE", "OPENING_RANGE_BREAKOUT", "OPTION_PRESSURE", "TREND_PULLBACK", "VWAP_RECLAIM"}:
        return ("generate_*_candidates", "signal", "ledger")
    if strategy_id in {"SIMPLE_ORB", "HTF_OPENING_DRIVE_CONT"}:
        return ("generate_signals", "phase_1_to_5_execution_replay")
    if kind in {"helper_module", "aggregate_engine"}:
        return ("helper", "aggregate")
    return ()


def _candidate_state_patterns(strategy_id: str, kind: str) -> tuple[str, ...]:
    if strategy_id in {"NO_TRADE_CHOP", "PAIRS_ARBITRAGE"}:
        return ("blocked", "candidate_pool")
    if kind == "aggregate_engine":
        return ("aggregate", "children")
    if kind == "helper_module":
        return ("helper",)
    return ("candidate", "state")


def _required_dataset_patterns(strategy_id: str, kind: str) -> tuple[str, ...]:
    if strategy_id == "PAIRS_ARBITRAGE":
        return ("runtime/market_data/upstox", "runtime/upstox_instruments")
    if strategy_id == "OPTION_PRESSURE":
        return ("runtime/market_data/upstox", "runtime/upstox_candidate_replay")
    return ("runtime/market_data/upstox",)


def _required_columns(strategy_id: str, kind: str) -> tuple[str, ...]:
    if strategy_id == "PAIRS_ARBITRAGE":
        return ("timestamp", "symbol", "spread", "pair_id")
    if strategy_id == "NO_TRADE_CHOP":
        return ("timestamp", "strategy_id", "blocker")
    if strategy_id in {"SIMPLE_ORB", "HTF_OPENING_DRIVE_CONT"}:
        return ("timestamp", "strategy_id", "direction", "signal_ts")
    return ("timestamp", "strategy_id", "direction", "signal_ts")
