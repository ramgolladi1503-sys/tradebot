from __future__ import annotations

from pathlib import Path

from .historical_source_discovery import discover_historical_sources
from .lane_status import build_lane_status
from .ledger_oracle import certify_ledger
from .repo_inventory import historical_hypotheses
from .strategy_source_registry import build_strategy_source_registry


def build_signal_ledgers(repo_root: Path):
    registry = build_strategy_source_registry(repo_root)
    discovery = discover_historical_sources(repo_root)
    lane_status = [build_lane_status(contract) for contract in registry.values()]
    hypotheses = historical_hypotheses(repo_root)
    oracle = certify_ledger([])
    summary = {
        "lane_count": len(registry),
        "hypothesis_count": len(hypotheses),
        "discovery_roots": discovery["searched_roots"],
        "oracle_verdict": oracle["verdict"],
    }
    return [], summary, {"lane_status": lane_status, "registry": registry, "oracle": oracle, "discovery": discovery}
