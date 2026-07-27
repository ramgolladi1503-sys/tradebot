from __future__ import annotations

from pathlib import Path

from .git_discovery import run_git_discovery
from .ledger_oracle import certify_ledger
from .lane_executor import execute_lane
from .lane_reconciliation import reconcile_lanes
from .repository_inventory import (
    load_alias_graph,
    load_historical_claim_map,
    load_historical_strategy_inventory,
    load_repository_inventory,
)
from .signal_artifact_loader import load_signal_artifacts


VERTICAL_SLICE_LANES = ("VWAP_RECLAIM", "OPENING_RANGE_BREAKOUT", "OPENING_STATE_MOMENTUM")


def _lane_entry_map(inventory: dict[str, object]) -> dict[str, dict[str, object]]:
    entries = inventory.get("entries", [])
    out: dict[str, dict[str, object]] = {}
    for entry in entries:
        strategy_id = str(entry.get("strategy_id") or "")
        if strategy_id in VERTICAL_SLICE_LANES:
            out[strategy_id] = entry
    return out


def build_signal_ledgers(repo_root: Path):
    inventory = load_repository_inventory(repo_root)
    alias_graph = load_alias_graph(repo_root)
    historical_claims = load_historical_claim_map(repo_root)
    historical_strategy_inventory = load_historical_strategy_inventory(repo_root)
    git_discovery = run_git_discovery(repo_root)
    artifacts = load_signal_artifacts(repo_root)
    lane_entries = _lane_entry_map(inventory)
    lane_reports = []
    for lane in VERTICAL_SLICE_LANES:
        entry = lane_entries.get(lane, {"strategy_id": lane, "certification_blockers": ["LANE_ENTRY_MISSING"]})
        artifact = next(
            (
                item
                for item in artifacts
                if item.get("strategy_id") == lane
                and item.get("kind") in {"candidate_replay_report", "historical_signal_ledger_record"}
            ),
            {},
        )
        hist_inventory_hits = [entity for entity in historical_strategy_inventory.get("entities", []) if isinstance(entity, dict) and entity.get("id") == lane]
        lane_reports.append(
            {
                **execute_lane(entry, artifact),
                "alias_graph_hits": [edge for edge in alias_graph.get("edges", []) if edge.get("canonical_strategy_id") == lane],
                "historical_claims": [claim for claim in historical_claims.get("claims", []) if lane in (claim.get("strategy_mentions") or [])],
                "historical_inventory_hits": hist_inventory_hits,
            }
        )
    oracle = certify_ledger(lane_reports)
    reconciliation = reconcile_lanes(lane_reports)
    summary = {
        "lane_count": len(VERTICAL_SLICE_LANES),
        "artifact_count": len(artifacts),
        "oracle_verdict": oracle["verdict"],
        "reconciliation_status": reconciliation["status"],
    }
    detail = {
        "inventory": inventory,
        "git_discovery": git_discovery,
        "artifacts": artifacts,
        "lane_reports": lane_reports,
        "oracle": oracle,
        "reconciliation": reconciliation,
    }
    return lane_reports, summary, detail
