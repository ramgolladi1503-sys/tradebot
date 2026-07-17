from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ai_certification import BundleError, certify_bundle
from core.ai_certification.report import write_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Certify a frozen TradeBot strict option-replay evidence bundle."
    )
    parser.add_argument("bundle", type=Path, help="Path to the frozen certification bundle")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".runtime/ai_certification/reports"),
        help="Directory used only for generated JSON and Markdown reports",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root used for the curated policy knowledge base",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = certify_bundle(args.bundle, repository_root=args.repository_root)
        outputs = write_report(report, args.output_dir)
    except (BundleError, OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"report": report.to_dict(), "outputs": outputs}, sort_keys=True))
    return 0 if report.evidence_certification.value == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
