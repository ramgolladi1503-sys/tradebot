from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(
    architecture_report: dict[str, Any],
    tick_report: dict[str, Any],
) -> dict[str, Any]:
    architecture = architecture_report.get("verdict", {})
    tick = tick_report.get("verdict", {})

    gates = {
        "candidate_corpus_present": bool(architecture.get("corpus_present")),
        "helper_parity": bool(architecture.get("helper_parity")),
        "shadow_parity": bool(architecture.get("shadow_parity")),
        "ranking_execution_authority_proven": bool(
            architecture.get("ranking_execution_authority_proven")
        ),
        "market_input_replay_usable": bool(tick.get("market_input_replay_usable")),
        "market_input_scope_truthful": tick.get("scope") == "market_input_reconstruction_only",
        "raw_tick_data_not_misrepresented_as_lifecycle": (
            tick.get("candidate_lifecycle_present") is False
            and tick.get("execution_authority_present") is False
        ),
    }

    offline_complete = all(gates.values())
    return {
        "gates": gates,
        "offline_complete": offline_complete,
        "live_validation_pending": offline_complete,
        "verdict": (
            "OFFLINE_VALIDATION_COMPLETE_LIVE_ONLY_PENDING"
            if offline_complete
            else "OFFLINE_VALIDATION_INCOMPLETE"
        ),
        "live_validation_requirements": [
            "supervised live market session with no order auto-routing",
            "capture before/after TradeBuilder candidate snapshots",
            "capture ranking, review queue, blockers and execution authority",
            "prove no candidate loss or duplication",
            "prove no advisory or blocked candidate upgrades to executable",
            "repeat across restart/reconnect and stale/fallback conditions",
        ] if offline_complete else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture-report", type=Path, required=True)
    parser.add_argument("--tick-report", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/tradebuilder_orchestrator_offline_certification.json"),
    )
    parser.add_argument("--require-live-only-pending", action="store_true")
    args = parser.parse_args()

    report = evaluate(_load(args.architecture_report), _load(args.tick_report))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"]}, sort_keys=True))
    return 0 if not args.require_live_only_pending or report["offline_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
