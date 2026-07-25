from __future__ import annotations

from .source_contract import SourceContract


def build_strategy_source_registry() -> dict[str, SourceContract]:
    strategies = [
        "COMPRESSION_BREAKOUT",
        "EVENT_VOLATILITY_EXPANSION",
        "EXHAUSTION_REVERSAL",
        "FAILED_BREAKOUT_TRAP",
        "HTF_OPENING_DRIVE_CONT",
        "LATE_DAY_MOMENTUM",
        "MEAN_REVERSION_EXTENSION",
        "NO_TRADE_CHOP",
        "OPENING_DRIVE",
        "OPENING_RANGE_BREAKOUT",
        "OPTION_PRESSURE",
        "PAIRS_ARBITRAGE",
        "SIMPLE_ORB",
        "TREND_PULLBACK",
        "VOLATILITY_TREND",
        "VWAP_ORB",
        "VWAP_RECLAIM",
        "ZERO_HERO",
    ]
    registry: dict[str, SourceContract] = {}
    for strategy in strategies:
        registry[strategy] = SourceContract(
            strategy_or_hypothesis_id=strategy,
            canonical_alias_group=strategy,
            economic_family="strategy" if strategy != "NO_TRADE_CHOP" else "filter",
            directional_eligibility="directional" if strategy not in {"NO_TRADE_CHOP", "PAIRS_ARBITRAGE"} else "non_directional_or_helper",
            current_implementation_paths=("research/option_e2e_recertification_v4/signal_ledgers_v4_7",),
            historical_branch_candidates=("origin/main", "HEAD"),
            historical_commit_candidates=(),
            signal_artifact_patterns=("signal", "ledger", "candidate"),
            candidate_state_patterns=("candidate", "state"),
            required_underlying_dataset_patterns=("runtime/market_data/upstox",),
            expected_required_columns=("timestamp", "strategy_or_hypothesis_id", "direction", "signal_ts"),
            known_evidence_roots=("runtime/market_data/upstox", "runtime/upstox_candidate_replay", "runtime/upstox_instruments"),
            contract_paths=(),
            development_holdout_policy="fail_closed",
            source_resolution_status="SOURCE_REGISTRY_ONLY",
            source_domain="CURRENT_MASTER_DIAGNOSTIC",
        )
    return registry
