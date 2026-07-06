#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.execution_grade_firewall import assess_execution_grade
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.ranking_orchestrator import build_ranked_opportunity_report

DEFAULT_FIXTURE_DIR = Path("tests/fixtures/option_data_quality_candidate_proof_pack")


def _context(payload: dict[str, Any]) -> StrategyContext:
    return StrategyContext(**payload)


def _regime(payload: dict[str, Any]) -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=int(payload.get("schema_version", 1)),
        primary_regime=str(payload.get("primary_regime") or "TREND_UP"),
        scores=dict(payload.get("scores") or {}),
    )


def _candidate(payload: dict[str, Any]) -> StrategyCandidate:
    return StrategyCandidate(**payload)


def load_fixture(fixture_dir: Path, name: str) -> dict[str, Any]:
    path = fixture_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    context = _context(scenario["context"])
    regime = _regime(scenario["regime"])
    candidate_payload = scenario["candidate"]
    candidate = _candidate(candidate_payload)

    def _generator(_ctx: StrategyContext, _regime: MovementRegimeResult):
        return (candidate,)

    report = build_ranked_opportunity_report(
        context,
        regime,
        candidate_generators=[_generator],
        include_strategy_id_in_normalization_key=True,
    )
    execution_grade = assess_execution_grade(
        candidate,
        context,
        contract_resolution=scenario.get("contract_resolution"),
    )

    return {
        "scenario": scenario["scenario"],
        "candidate_status": candidate.status,
        "blockers": list(candidate.blockers),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "counts": {
            "raw_candidate_count": report.raw_candidate_count,
            "normalized_candidate_count": report.normalized_candidate_count,
            "ranked_candidate_count": report.ranked_candidate_count,
            "executable_rank_count": report.executable_rank_count,
            "near_executable_rank_count": report.near_executable_rank_count,
            "advisory_rank_count": report.advisory_rank_count,
            "suppressed_rank_count": report.suppressed_rank_count,
            "no_trade_rank_count": report.no_trade_rank_count,
        },
        "ranking": {
            "top_rank_strategy_id": report.top_rank_strategy_id,
            "ranks": [
                {
                    "rank": rank.rank,
                    "strategy_id": rank.strategy_id,
                    "bucket": rank.bucket,
                    "score_eligibility": rank.score_eligibility,
                    "executable_candidate": rank.executable_candidate,
                    "final_score": rank.final_score,
                }
                for rank in report.ranking.ranks
            ],
        },
        "execution_grade": execution_grade.to_dict(),
        "report": report.to_dict(),
    }


def build_proof_pack(fixture_dir: Path) -> dict[str, Any]:
    fixture = load_fixture(fixture_dir, "option_data_quality_proof_pack")
    return {
        "fixture": "option_data_quality_proof_pack",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "scenarios": [_run_scenario(scenario) for scenario in fixture["scenarios"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", default=str(DEFAULT_FIXTURE_DIR))
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    proof_pack = build_proof_pack(Path(args.fixture_dir))
    payload = json.dumps(proof_pack, indent=2, sort_keys=True, default=str)
    if args.output_json:
        Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
