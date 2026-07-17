from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ai_certification.exporter import ExportError, export_option_replay_wfa_bundle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a frozen AI certification bundle from an existing option-replay WFA output directory."
    )
    parser.add_argument("--wfa-output-dir", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument(
        "--strategy-verdict",
        required=True,
        choices=(
            "STRUCTURAL_EDGE_SUPPORTED",
            "CONDITIONALLY_SUPPORTED",
            "INSUFFICIENT_TRADES",
            "NO_STRUCTURAL_EDGE",
        ),
    )
    parser.add_argument("--negative-controls", type=Path, required=True)
    parser.add_argument("--test-results", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        bundle = export_option_replay_wfa_bundle(
            wfa_output_dir=args.wfa_output_dir,
            bundle_dir=args.bundle_dir,
            repository_commit=args.repository_commit,
            strategy_id=args.strategy_id,
            strategy_verdict=args.strategy_verdict,
            negative_controls_path=args.negative_controls,
            test_results_path=args.test_results,
        )
    except (ExportError, OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "EXPORTED", "bundle": str(bundle)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
