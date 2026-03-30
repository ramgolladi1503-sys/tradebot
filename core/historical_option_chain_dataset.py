from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


REQUIRED_BASE_COLUMNS = {"timestamp", "strike", "type", "ltp"}


@dataclass
class HistoricalOptionDatasetConfig:
    timestamp_tolerance: str = "10min"
    max_rows_per_snapshot: int = 200


class HistoricalOptionChainDataset:
    def __init__(self, path: str | Path, config: Optional[HistoricalOptionDatasetConfig] = None):
        self.path = Path(path)
        self.config = config or HistoricalOptionDatasetConfig()
        self.df = self._load()

    def _load(self) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"Option dataset not found: {self.path}")
        if self.path.suffix == ".csv":
            df = pd.read_csv(self.path)
        elif self.path.suffix in {".parquet", ".pq"}:
            df = pd.read_parquet(self.path)
        else:
            raise ValueError(f"Unsupported option dataset format: {self.path.suffix}")

        cols = set(df.columns)
        missing = REQUIRED_BASE_COLUMNS - cols
        if missing:
            raise ValueError(f"Missing required option dataset columns: {sorted(missing)}")

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        if "symbol" not in df.columns:
            df["symbol"] = "NIFTY"
        if "expiry" not in df.columns and "expiry_date" in df.columns:
            df["expiry"] = df["expiry_date"]
        if "expiry_date" not in df.columns and "expiry" in df.columns:
            df["expiry_date"] = df["expiry"]
        if "quote_source" not in df.columns:
            df["quote_source"] = "historical_option_dataset"
        if "option_ltp_source" not in df.columns:
            df["option_ltp_source"] = "historical_option_dataset"
        if "price_source" not in df.columns:
            df["price_source"] = "historical_option_dataset"
        if "quote_ok" not in df.columns:
            df["quote_ok"] = True
        if "quote_live" not in df.columns:
            df["quote_live"] = False
        if "quote_age_sec" not in df.columns:
            df["quote_age_sec"] = 0.0
        if "chain_source" not in df.columns:
            df["chain_source"] = "historical_option_dataset"
        if "planning_only" not in df.columns:
            df["planning_only"] = True
        return df

    def snapshot(self, timestamp, symbol: str = "NIFTY") -> list[dict]:
        ts = pd.Timestamp(timestamp)
        sym_df = self.df[self.df["symbol"].astype(str).str.upper() == str(symbol).upper()]
        if sym_df.empty:
            return []

        unique_ts = sym_df["timestamp"].drop_duplicates().sort_values()
        nearest_idx = unique_ts.searchsorted(ts)
        candidates = []
        if nearest_idx < len(unique_ts):
            candidates.append(unique_ts.iloc[nearest_idx])
        if nearest_idx > 0:
            candidates.append(unique_ts.iloc[nearest_idx - 1])
        if not candidates:
            return []

        best_ts = min(candidates, key=lambda x: abs(x - ts))
        max_delta = pd.Timedelta(self.config.timestamp_tolerance)
        if abs(best_ts - ts) > max_delta:
            return []

        snap = sym_df[sym_df["timestamp"] == best_ts].copy()
        if snap.empty:
            return []
        snap = snap.head(int(self.config.max_rows_per_snapshot))
        records = snap.to_dict(orient="records")
        for row in records:
            bid = row.get("bid")
            ask = row.get("ask")
            ltp = row.get("ltp")
            if row.get("best_bid") is None:
                row["best_bid"] = bid
            if row.get("best_ask") is None:
                row["best_ask"] = ask
            if row.get("mid_price") is None and bid is not None and ask is not None:
                try:
                    row["mid_price"] = (float(bid) + float(ask)) / 2.0
                except Exception:
                    pass
            if row.get("mark_price") is None:
                row["mark_price"] = row.get("mid_price") or ltp
            if row.get("last_price") is None:
                row["last_price"] = ltp
            if row.get("spread_pct") is None and bid is not None and ask is not None and ltp:
                try:
                    row["spread_pct"] = (float(ask) - float(bid)) / max(float(ltp), 1e-6)
                except Exception:
                    row["spread_pct"] = None
            if row.get("instrument_token") is None:
                row["instrument_token"] = int(abs(hash((row.get("symbol"), row.get("expiry"), row.get("strike"), row.get("type")))) % 10**9)
            if row.get("tradingsymbol") is None:
                expiry = str(row.get("expiry") or row.get("expiry_date") or "")
                row["tradingsymbol"] = f"{row.get('symbol', symbol)}{expiry.replace('-', '')}{int(float(row.get('strike', 0)))}{row.get('type', '')}"
        return records
