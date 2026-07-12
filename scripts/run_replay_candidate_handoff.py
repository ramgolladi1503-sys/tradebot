#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.replay_candidate_handoff_entrypoint import run_replay_candidate_handoff


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a replay-only candidate handoff proof.")
    parser.add_argument("--source", required=True, help="Replay input JSONL file.")
    parser.add_argument("--event-id", default=None, help="Optional event id to select.")
    parser.add_argument("--row-index", type=int, default=None, help="Optional zero-based row index to select.")
    parser.add_argument("--strategy-id", default=None, help="Optional strategy id filter.")
    parser.add_argument("--run-id", default=None, help="Optional isolated run id.")
    parser.add_argument("--output-root", default=None, help="Optional isolated output root.")
    parser.add_argument("--is-oos", default=None, help="Explicit OOS flag (true/false) from replay or WFA context.")
    parser.add_argument("--oos-label", default=None, help="Explicit OOS label (IS/OOS).")
    parser.add_argument("--oos-source", default=None, help="Explicit OOS provenance source.")
    parser.add_argument("--partition-id", default=None, help="Explicit replay/WFA partition id.")
    parser.add_argument("--split-name", default=None, help="Explicit replay/WFA split name.")
    parser.add_argument(
        "--write-production-artifacts",
        action="store_true",
        help="Write production-style artifact names outside the isolated output tree.",
    )
    return parser.parse_args(argv)


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise SystemExit(f"invalid --is-oos value: {value}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_replay_candidate_handoff(
        source_path=Path(args.source),
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        event_id=args.event_id,
        row_index=args.row_index,
        strategy_id=args.strategy_id,
        write_production_artifacts=bool(args.write_production_artifacts),
        oos_context={
            "is_oos": _parse_bool(args.is_oos),
            "oos_label": args.oos_label,
            "oos_source": args.oos_source,
            "partition_id": args.partition_id,
            "split_name": args.split_name,
        },
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
    return 0 if not result.verdict.startswith("BLOCKED_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
