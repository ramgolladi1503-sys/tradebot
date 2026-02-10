from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


REQUIRED_COLUMNS = [
    "trade_id",
    "trace_id",
    "decision_trace_id",
    "timestamp_epoch",
    "symbol",
    "strategy",
    "regime_at_entry",
    "side",
    "entry_price",
    "exit_price",
    "stop_loss",
    "target",
    "qty_units",
    "hold_time_sec",
    "pnl",
    "r_multiple",
    "mae",
    "mfe",
    "label",
    "features_snapshot",
]


def _load_rows(input_dir: Path) -> list[dict]:
    files = sorted(input_dir.glob("trade_labels_*.jsonl"))
    rows: list[dict] = []
    for file in files:
        for idx, line in enumerate(file.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                raise ValueError(f"invalid_json:{file}:{idx}:{exc}") from exc
            rows.append(row)
    return rows


def _validate_rows(rows: list[dict]) -> tuple[bool, str]:
    if not rows:
        return False, "no_label_rows"
    for idx, row in enumerate(rows):
        missing = [col for col in REQUIRED_COLUMNS if col not in row]
        if missing:
            return False, f"missing_columns:row={idx}:cols={','.join(missing)}"
        if row.get("decision_trace_id") in (None, ""):
            return False, f"missing_decision_trace_id:row={idx}"
        if row.get("features_snapshot") is None:
            return False, f"missing_features_snapshot:row={idx}"
    return True, "ok"


def build_training_dataset(
    input_dir: str = "data/training",
    output_path: str = "data/training/trade_labels_training.jsonl",
) -> tuple[bool, str, int]:
    in_dir = Path(input_dir)
    if not in_dir.exists():
        return False, f"input_dir_missing:{in_dir}", 0
    rows = _load_rows(in_dir)
    ok, reason = _validate_rows(rows)
    if not ok:
        return False, reason, len(rows)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")
    return True, "ok", len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build merged training dataset from post-trade labels.")
    parser.add_argument("--input-dir", default="data/training", help="Directory containing trade_labels_*.jsonl")
    parser.add_argument(
        "--output",
        default="data/training/trade_labels_training.jsonl",
        help="Merged output JSONL path",
    )
    args = parser.parse_args()
    ok, reason, count = build_training_dataset(args.input_dir, args.output)
    if not ok:
        print(f"build_training_dataset: FAIL reason={reason} rows={count}")
        print("NEXT ACTION: run paper/live cycle to produce closed trades and trade_labels_*.jsonl")
        return 2
    print(f"build_training_dataset: OK rows={count} output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

