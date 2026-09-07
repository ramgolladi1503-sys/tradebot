from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from research.alphatrend_mechanism_v1.campaign import run_development_campaign
from research.ml_strategy_discovery.contracts import DiscoveryConfig
from research.ml_strategy_discovery.dataset import normalize_bars


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AlphaTrend-inspired mechanism research on DEVELOPMENT bars only."
    )
    parser.add_argument("--bars", required=True, help="Development-only CSV or parquet OHLCV file")
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--timestamp-semantics", choices=("START", "END"), required=True)
    parser.add_argument("--source-timezone", default="Asia/Kolkata")
    parser.add_argument("--bar-interval-minutes", type=int, default=1)
    parser.add_argument("--strict-bar-cadence", action="store_true")
    parser.add_argument(
        "--development-only-attestation",
        action="store_true",
        help="Required acknowledgement that the supplied file contains no validation/final-holdout rows.",
    )
    return parser.parse_args()


def _read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported bars file: {path.suffix}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    if not args.development_only_attestation:
        raise SystemExit(
            "BLOCKED: --development-only-attestation is required. "
            "Do not pass a validation or final-holdout file to this runner."
        )

    source = Path(args.bars).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)
    raw = _read_frame(source)
    config = DiscoveryConfig(
        instrument=args.instrument,
        timestamp_column=args.timestamp_column,
        timestamp_semantics=args.timestamp_semantics,
        source_timezone=args.source_timezone,
        bar_interval_minutes=args.bar_interval_minutes,
        strict_bar_cadence=args.strict_bar_cadence,
        source_kind="ALPHATREND_MECHANISM_EXPLICIT_DEVELOPMENT_FILE_V1",
    )
    bars = normalize_bars(raw, config)
    campaign = run_development_campaign(bars)

    provenance = {
        "source_file": str(source),
        "source_sha256": _sha256(source),
        "input_rows": int(len(raw)),
        "normalized_rows": int(len(bars)),
        "sessions": int(bars["session_date"].nunique()),
        "start_decision_timestamp": str(bars["timestamp"].min()),
        "end_decision_timestamp": str(bars["timestamp"].max()),
        "timestamp_semantics": args.timestamp_semantics,
        "source_timezone": args.source_timezone,
        "bar_interval_minutes": args.bar_interval_minutes,
        "scope_attested": "DEVELOPMENT_ONLY",
        "validation_evaluated": False,
        "holdout_evaluated": False,
        "read_only": True,
        "broker_api_called": False,
        "order_authority": False,
        "live_execution_authorized": False,
    }
    result = {"provenance": provenance, "campaign": campaign}

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "alphatrend_mechanism_dev_v1.json"
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
