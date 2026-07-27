from __future__ import annotations

from pathlib import Path

from .archive_discovery import run_archive_discovery
from .evidence_classifier import classify_evidence
from .filesystem_discovery import run_filesystem_discovery
from .git_discovery import run_git_discovery
from .historical_implementation_loader import load_historical_implementation_candidates
from .ledger_oracle import certify_ledger
from .lane_executor import execute_lane
from .lane_reconciliation import reconcile_lanes
from .repository_inventory import load_repository_inventory
from .signal_artifact_loader import load_signal_artifacts


def build_signal_ledgers(repo_root: Path):
    inventory = load_repository_inventory(repo_root)
    git_discovery = run_git_discovery(repo_root)
    filesystem_discovery = run_filesystem_discovery()
    archive_discovery = run_archive_discovery(repo_root)
    artifacts = load_signal_artifacts(repo_root)
    historical = load_historical_implementation_candidates(repo_root)
    lane_reports = []
    for entry in inventory.get("entries", []):
        lane_reports.append(
            {
                "strategy_id": entry.get("strategy_id"),
                "classification": classify_evidence(entry),
                "execution": execute_lane(entry),
            }
        )
    oracle = certify_ledger([])
    reconciliation = reconcile_lanes([])
    summary = {
        "lane_count": len(lane_reports),
        "artifact_count": len(artifacts),
        "historical_candidate_count": len(historical),
        "oracle_verdict": oracle["verdict"],
        "reconciliation_status": reconciliation["status"],
    }
    detail = {
        "inventory": inventory,
        "git_discovery": git_discovery,
        "filesystem_discovery": filesystem_discovery,
        "archive_discovery": archive_discovery,
        "artifacts": artifacts,
        "historical_candidates": historical,
        "lane_reports": lane_reports,
        "oracle": oracle,
        "reconciliation": reconciliation,
    }
    return [], summary, detail
