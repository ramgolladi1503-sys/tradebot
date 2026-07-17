from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ai_certification.gemini_client import GeminiClient
from core.ai_certification.research_manager import (
    CertificationResearchManager,
    GeminiPlanner,
    SQLiteResearchStore,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the durable read-only AI certification manager.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--evidence-root", type=Path, default=Path(".runtime/ai_certification/bundles"))
    parser.add_argument("--report-root", type=Path, default=Path(".runtime/ai_certification/reports"))
    parser.add_argument("--state-db", type=Path, default=Path(".runtime/ai_certification/research.sqlite3"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--planner", choices=("deterministic", "gemini"), default="deterministic")
    parser.add_argument("--approve", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    planner = None
    if args.planner == "gemini":
        planner = GeminiPlanner(GeminiClient())
    store = SQLiteResearchStore(args.state_db)
    manager = CertificationResearchManager(
        evidence_root=args.evidence_root,
        report_root=args.report_root,
        repository_root=args.repository_root,
        store=store,
        planner=planner,
    )
    try:
        run = store.load(args.run_id)
    except KeyError:
        run = manager.create_run(args.run_id, args.bundle_id)
    if args.approve:
        run = manager.approve(run.run_id)
    run = manager.run_to_completion(run.run_id)
    print(json.dumps(run.__dict__, sort_keys=True, default=str))
    return 0 if run.state == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
