#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.qa.audit_elite_e2e_coverage import build_report


def build_confidence_report(*, repo_root: Path) -> dict[str, object]:
    audit = build_report(repo_root=repo_root)
    score = int(audit["elite_audit_score"])
    caps = list(audit["hard_caps_applied"])
    return {
        "execution_guard_status": audit["execution_guard_status"],
        "confidence_score": score,
        "quality_score": score,
        "hard_caps_applied": caps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score QA confidence with conservative hard caps.")
    parser.add_argument("--threshold", type=int, default=95)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_confidence_report(repo_root=Path.cwd())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"execution_guard_status: {report['execution_guard_status']}")
        print(f"quality_score: {report['quality_score']}/100")
        print(f"confidence_score: {report['confidence_score']}/100")
        if report["hard_caps_applied"]:
            print("hard_caps_applied:")
            for cap in report["hard_caps_applied"]:
                print(f"- {cap}")
    return 0 if int(report["confidence_score"]) >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
