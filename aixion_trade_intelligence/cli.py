from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .certification import analyze_session, certify_analysis
from .quality import validate_session
from .report import build_report_payload, write_report
from .replay import assert_replay_deterministic
from .storage import atomic_write_json, load_events


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aixion-intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a canonical JSONL session")
    validate.add_argument("--events", required=True, type=Path)
    validate.add_argument("--output", type=Path)

    replay = subparsers.add_parser("replay", help="Calculate deterministic replay hash")
    replay.add_argument("--events", required=True, type=Path)

    certify = subparsers.add_parser("certify", help="Offline-certify evidence and outcome pipeline")
    certify.add_argument("--events", required=True, type=Path)
    certify.add_argument("--output-dir", required=True, type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    events = load_events(args.events)

    if args.command == "validate":
        manifest = validate_session(events)
        payload = manifest.to_dict()
        if args.output:
            atomic_write_json(args.output, payload)
        else:
            import json

            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if manifest.verdict == "VALID_RESEARCH_CAPTURE" else 2

    if args.command == "replay":
        result = assert_replay_deterministic(events)
        print(result.deterministic_hash)
        return 0

    if args.command == "certify":
        analysis = analyze_session(events)
        certification = certify_analysis(analysis)
        payload = build_report_payload(
            certification=certification,
            lineage=analysis.lineage,
            outcomes=analysis.outcomes,
            analytics=analysis.analytics,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.output_dir / "certification.json", certification.to_dict())
        write_report(args.output_dir, payload)
        print(certification.verdict)
        return 0 if certification.pipeline_certified else 3

    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
