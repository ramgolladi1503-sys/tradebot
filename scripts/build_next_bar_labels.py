#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def build_next_bar_labels(*, input_csv: str | Path, output_csv: str | Path, horizon_bars: int = 1) -> dict[str, object]:
    source = Path(input_csv).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"input_csv_not_found:{source}")

    frame = pd.read_csv(source)
    missing = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"missing_required_columns:{','.join(missing)}")

    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    from core.feature_builder import add_indicators

    enriched = add_indicators(out[["timestamp", "open", "high", "low", "close", "volume"]].copy())
    out["regime_tag"] = _derive_regime_tag(enriched)
    out["session_bucket"] = out["timestamp"].dt.hour.map(_session_bucket_hour)
    out["future_close"] = out["close"].shift(-int(horizon_bars))
    out["future_return"] = (out["future_close"] / out["close"]) - 1.0
    out["label_up"] = (out["future_return"] > 0).astype("Int64")
    out = out.dropna(subset=["future_close"]).reset_index(drop=True)

    target = Path(output_csv).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, index=False)
    return {
        "input_csv": str(source),
        "output_csv": str(target),
        "rows": int(len(out)),
        "horizon_bars": int(horizon_bars),
    }


def _session_bucket_hour(hour: int) -> str:
    hour = int(hour)
    if hour < 11:
        return "OPEN"
    if hour < 14:
        return "MID"
    return "CLOSE"


def _derive_regime_tag(enriched: pd.DataFrame) -> pd.Series:
    adx = pd.to_numeric(enriched.get("adx_14"), errors="coerce").fillna(0.0)
    vwap_slope = pd.to_numeric(enriched.get("vwap_slope"), errors="coerce").fillna(0.0)
    vol_z = pd.to_numeric(enriched.get("vol_z"), errors="coerce").fillna(0.0)
    close = pd.to_numeric(enriched.get("close"), errors="coerce")
    atr = pd.to_numeric(enriched.get("atr_14"), errors="coerce").fillna(0.0)
    trend = (adx >= 20.0) & (vwap_slope.abs() > 0) & (close.notna())
    volatile = (vol_z >= 1.0) | ((atr / close.replace(0, pd.NA)).fillna(0.0) >= 0.008)
    range_like = (~trend) & (~volatile)
    out = pd.Series(["UNKNOWN"] * len(enriched), index=enriched.index, dtype="object")
    out.loc[trend] = "TREND"
    out.loc[volatile & ~trend] = "VOLATILE"
    out.loc[range_like] = "RANGE"
    return out


def build_multi_horizon_labels(
    *,
    input_csv: str | Path,
    output_csv: str | Path,
    horizons_bars: list[int],
) -> dict[str, object]:
    source = Path(input_csv).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"input_csv_not_found:{source}")

    frame = pd.read_csv(source)
    missing = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"missing_required_columns:{','.join(missing)}")

    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    from core.feature_builder import add_indicators

    enriched = add_indicators(out[["timestamp", "open", "high", "low", "close", "volume"]].copy())
    out["regime_tag"] = _derive_regime_tag(enriched)
    out["session_bucket"] = out["timestamp"].dt.hour.map(_session_bucket_hour)
    label_cols: list[str] = []
    for horizon in horizons_bars:
        horizon_i = int(horizon)
        close_col = f"future_close_{horizon_i}"
        ret_col = f"future_return_{horizon_i}"
        label_col = f"label_up_{horizon_i}"
        out[close_col] = out["close"].shift(-horizon_i)
        out[ret_col] = (out[close_col] / out["close"]) - 1.0
        out[label_col] = (out[ret_col] > 0).astype("Int64")
        label_cols.append(label_col)
    out = out.dropna(subset=[f"future_close_{int(h)}" for h in horizons_bars]).reset_index(drop=True)

    target = Path(output_csv).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, index=False)
    return {
        "input_csv": str(source),
        "output_csv": str(target),
        "rows": int(len(out)),
        "horizons_bars": [int(h) for h in horizons_bars],
        "label_columns": label_cols,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a simple next-bar label dataset from canonical OHLCV CSV.")
    parser.add_argument("--input-csv", required=True, help="Canonical CSV with timestamp/open/high/low/close/volume")
    parser.add_argument("--output-csv", required=True, help="Output labeled CSV path")
    parser.add_argument("--horizon-bars", type=int, default=1, help="Bars ahead to label")
    parser.add_argument("--multi-horizons", default="", help="Optional comma-separated list of horizons for multi-label output")
    args = parser.parse_args(argv)
    if str(args.multi_horizons).strip():
        horizons = [int(item.strip()) for item in str(args.multi_horizons).split(",") if item.strip()]
        report = build_multi_horizon_labels(
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            horizons_bars=horizons,
        )
    else:
        report = build_next_bar_labels(
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            horizon_bars=args.horizon_bars,
        )
    print(f"labels_written={report['rows']} output={report['output_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
