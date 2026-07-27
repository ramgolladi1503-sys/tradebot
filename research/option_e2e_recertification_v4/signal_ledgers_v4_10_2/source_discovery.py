from __future__ import annotations

from pathlib import Path


def discover_vwap_sources(repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    implementation = repo_root / "strategies" / "movement" / "vwap_reclaim.py"
    runtime_dir = repo_root / "runtime" / "strategy_validation" / "VWAP_RECLAIM"
    invalidated_ledger = (
        repo_root
        / "research"
        / "option_e2e_recertification_v4"
        / "signal_ledgers_v4_2"
        / "signal_ledgers.json"
    )
    return {
        "strategy_id": "VWAP_RECLAIM",
        "implementation": {
            "semantic_path": "strategies/movement/vwap_reclaim.py",
            "physical_path": str(implementation),
            "available": implementation.exists(),
            "evidence_domain": "STRATEGY_IMPLEMENTATION",
        },
        "legacy_option_replay_audits": [
            {
                "semantic_path": f"runtime/strategy_validation/VWAP_RECLAIM/{name}",
                "physical_path": str(runtime_dir / name),
                "available": (runtime_dir / name).exists(),
                "evidence_domain": "OPTION_REPLAY_AUDIT_ONLY",
            }
            for name in ("candidate_replay_report.json", "phase_4_report.json")
        ],
        "invalidated_historical_evidence": {
            "semantic_path": "research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json",
            "physical_path": str(invalidated_ledger),
            "available": invalidated_ledger.exists(),
            "evidence_domain": "INVALIDATED_HISTORICAL_RECORD",
            "active_for_signal_truth": False,
        },
    }
