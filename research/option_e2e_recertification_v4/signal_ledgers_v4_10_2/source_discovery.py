from __future__ import annotations

from pathlib import Path


def discover_vwap_sources(repo_root: Path) -> dict[str, object]:
    implementation = repo_root / "strategies" / "movement" / "vwap_reclaim.py"
    runtime_report = repo_root / "runtime" / "strategy_validation" / "VWAP_RECLAIM" / "candidate_replay_report.json"
    phase_4_report = repo_root / "runtime" / "strategy_validation" / "VWAP_RECLAIM" / "phase_4_report.json"
    historical_ledger = repo_root / "research" / "option_e2e_recertification_v4" / "signal_ledgers_v4_2" / "signal_ledgers.json"
    return {
        "implementation_path": str(implementation),
        "runtime_reports": [str(runtime_report), str(phase_4_report)],
        "historical_ledger": str(historical_ledger),
        "allowed_roots": [
            str(repo_root),
            "/Users/madhuram/tradebot-data",
            "/Users/madhuram/tradebot-ml-evidence",
        ],
    }

