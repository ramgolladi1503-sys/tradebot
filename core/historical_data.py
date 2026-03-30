from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


def load_market_data(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    if path.suffix == ".csv":
        df = pd.read_csv(path)
    elif path.suffix in {".parquet", ".pq"}:
        try:
            df = pd.read_parquet(path)
        except Exception as e:
            raise RuntimeError("Parquet support requires pyarrow or fastparquet") from e
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    return normalize_market_data(df)


def normalize_market_data(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Normalize timestamp
    ts_col = None
    for c in ["timestamp", "datetime", "date", "ts"]:
        if c in out.columns:
            ts_col = c
            break
    if ts_col is None:
        raise ValueError("Missing timestamp column")

    out["timestamp"] = pd.to_datetime(out[ts_col], errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Ensure required columns
    missing = REQUIRED_COLUMNS - set(out.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Default symbol
    if "symbol" not in out.columns:
        out["symbol"] = "NIFTY"

    return out
