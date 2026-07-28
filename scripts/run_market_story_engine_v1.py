#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.market_story_engine_v1.certification import run_certification
from research.market_story_engine_v1.engine import MarketStoryEngine


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"unsupported input format: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--underlying")
    parser.add_argument("--breadth")
    parser.add_argument("--options")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--certify-synthetic", action="store_true")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if args.certify_synthetic:
        result = run_certification(output)
        summary = {
            "verdict": result["verdict"],
            "semantic_sha256": result["semantic_sha256"],
        }
        print(json.dumps(summary, sort_keys=True))
        return 0 if result["verdict"].startswith("PASS") else 1

    if not all([args.underlying, args.breadth, args.options]):
        parser.error(
            "--underlying, --breadth, and --options are required unless "
            "--certify-synthetic is used"
        )
    decisions = MarketStoryEngine().run(
        _read(Path(args.underlying)),
        _read(Path(args.breadth)),
        _read(Path(args.options)),
    )
    decisions.to_json(
        output / "decision_ledger.jsonl",
        orient="records",
        lines=True,
        date_format="iso",
    )
    print(
        json.dumps(
            {
                "rows": len(decisions),
                "terminal_decision": decisions.iloc[-1]["decision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
