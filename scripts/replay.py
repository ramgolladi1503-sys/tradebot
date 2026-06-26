#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.replay_harness import replay_from_file


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic decision replay from recorded JSONL."
    )
    parser.add_argument(
        "--input",
        "--file",
        dest="input_path",
        required=True,
        help="Path to replay input JSONL file (session or decisions).",
    )
    parser.add_argument(
        "--mode",
        default="paper",
        help="Replay mode. Supported: paper.",
    )
    parser.add_argument(
        "--start", default=None, help="Optional lower bound ts_epoch (inclusive)."
    )
    parser.add_argument(
        "--end", default=None, help="Optional upper bound ts_epoch (inclusive)."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail non-zero when replayed decision_id/reject_reasons do not match recorded values.",
    )
    args = parser.parse_args()

    mode = str(args.mode or "paper").strip().lower()
    if mode != "paper":
        raise SystemExit(f"unsupported replay mode: {mode}; supported: paper")

    file_path = Path(args.input_path).expanduser()
    if not file_path.exists():
        raise SystemExit(f"replay file not found: {file_path}")

    start_ts = _to_float(args.start)
    end_ts = _to_float(args.end)
    rows = replay_from_file(
        file_path, start_ts=start_ts, end_ts=end_ts, strict=bool(args.strict)
    )
    matched = sum(1 for row in rows if bool(row.get("match")))
    out = {
        "file": str(file_path),
        "mode": mode,
        "rows_replayed": len(rows),
        "rows_matched": matched,
        "strict": bool(args.strict),
        "start": start_ts,
        "end": end_ts,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.strict and matched != len(rows):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
