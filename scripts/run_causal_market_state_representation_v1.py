from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.market_state import MarketStateConfig, build_market_state_frame, state_contract


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_input(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported input format: {path.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the causal market-state V1 dataset")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--medium-window", type=int, default=15)
    parser.add_argument("--long-window", type=int, default=30)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(args.input)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    config = MarketStateConfig(
        short_window=args.short_window,
        medium_window=args.medium_window,
        long_window=args.long_window,
    )
    contract = state_contract(config)
    source = _read_input(args.input)
    states = build_market_state_frame(source, config)

    dataset_path = output_dir / "market_state_dataset.parquet"
    states.to_parquet(dataset_path, index=False)

    contract_hash = _canonical_hash(contract)
    contract_payload = {**contract, "semantic_hash": contract_hash}
    (output_dir / "market_state_contract.json").write_text(
        json.dumps(contract_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    state_columns = [name for names in contract["families"].values() for name in names]
    summary = {
        "verdict": "MARKET_STATE_DATASET_BUILT_NOT_VALIDATED",
        "rows": int(len(states)),
        "sessions": int(states[config.session_col].nunique()),
        "first_timestamp": str(states[config.timestamp_col].min()),
        "last_timestamp": str(states[config.timestamp_col].max()),
        "state_columns": state_columns,
        "state_column_count": len(state_columns),
        "mean_state_reliability": float(states["state_reliability"].mean()),
        "option_observability_rate": float(states["option_observable"].mean()),
        "source_path": str(args.input.resolve()),
        "source_rows": int(len(source)),
        "contract_hash": contract_hash,
    }
    (output_dir / "dataset_build_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
