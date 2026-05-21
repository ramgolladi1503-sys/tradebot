from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.debug_forensics.evidence_reader import load_runtime_startup_evidence
from core.debug_forensics.flow_analyzer import analyze_evidence
from core.debug_forensics.report_writer import report_exit_code, write_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only startup forensics.")
    parser.add_argument("--profile", default="startup")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--logs-dir", default=None)
    parser.add_argument("--reports-dir", default=None)
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()

    evidence = load_runtime_startup_evidence(
        profile=args.profile,
        run_id=args.run_id,
        logs_path=Path(args.logs_dir).expanduser() if args.logs_dir else None,
    )
    report = analyze_evidence(evidence)
    payload = report.to_dict()

    if not args.no_write_report:
        json_path, md_path = write_reports(
            report,
            base_dir=Path(args.reports_dir).expanduser() if args.reports_dir else None,
        )
        payload["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}

    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
