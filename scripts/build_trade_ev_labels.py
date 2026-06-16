#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_next_bar_labels import build_multi_horizon_labels, build_next_bar_labels


def _cost_bps_from_value(value: float | int | str | None) -> float:
    try:
        cost = float(value if value is not None else 10.0)
    except Exception:
        cost = 10.0
    if cost < 0:
        raise ValueError("cost_bps_must_be_non_negative")
    return cost


def _add_ev_columns(frame: pd.DataFrame, *, cost_bps: float) -> pd.DataFrame:
    out = frame.copy()
    future_cols = [col for col in out.columns if col.startswith("future_return")]
    if not future_cols:
        raise ValueError("missing_future_return_columns")
    for col in future_cols:
        suffix = col.replace("future_return", "") or ""
        ev_col = f"expected_value{suffix}"
        ev_bps_col = f"expected_value_bps{suffix}"
        label_col = f"ev_positive{suffix}"
        out[ev_col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0) - (cost_bps / 10000.0)
        out[ev_bps_col] = out[ev_col] * 10000.0
        out[label_col] = (out[ev_col] > 0).astype("Int64")
    out["cost_bps"] = float(cost_bps)
    return out


def build_trade_ev_labels(
    *,
    input_csv: str | Path,
    output_csv: str | Path,
    horizon_bars: int = 1,
    horizons_bars: list[int] | None = None,
    cost_bps: float = 10.0,
) -> dict[str, object]:
    source = Path(input_csv).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"input_csv_not_found:{source}")

    if horizons_bars:
        report = build_multi_horizon_labels(input_csv=source, output_csv=output_csv, horizons_bars=horizons_bars)
    else:
        report = build_next_bar_labels(input_csv=source, output_csv=output_csv, horizon_bars=horizon_bars)

    frame = pd.read_csv(output_csv)
    frame = _add_ev_columns(frame, cost_bps=_cost_bps_from_value(cost_bps))
    target = Path(output_csv).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)

    ev_cols = [col for col in frame.columns if col.startswith("expected_value") or col.startswith("ev_positive")]
    report["output_csv"] = str(target)
    report["ev_columns"] = ev_cols
    report["cost_bps"] = float(cost_bps)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build offline labels with an explicit trade-level EV target.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--horizon-bars", type=int, default=1)
    parser.add_argument("--multi-horizons", default="", help="Optional comma-separated horizons")
    parser.add_argument("--cost-bps", type=float, default=10.0, help="Estimated per-trade cost in bps")
    args = parser.parse_args(argv)

    horizons = [int(item.strip()) for item in str(args.multi_horizons).split(",") if item.strip()]
    report = build_trade_ev_labels(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        horizon_bars=args.horizon_bars,
        horizons_bars=horizons or None,
        cost_bps=args.cost_bps,
    )
    print(f"ev_labels_written={report['rows']} output={report['output_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
