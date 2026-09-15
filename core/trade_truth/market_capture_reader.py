"""Market Capture Reader for Level-C Causal Replay.

Reads stitched Upstox tick parquets from live market capture directories,
streaming ticks in strict chronological order with depth parsing and token filtering.
Guaranteed read-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import pyarrow.parquet as pq


@dataclass(frozen=True)
class MarketCaptureTick:
    ts: float
    token: str
    symbol: str
    ltp: float
    bid: float
    ask: float
    vol: float
    oi: float
    depth_raw: str

    @property
    def is_index(self) -> bool:
        return "INDEX" in self.token or "INDEX" in self.symbol or self.symbol == "SENSEX"

    def parse_depth(self) -> dict[str, list[dict[str, Any]]]:
        if not self.depth_raw or self.depth_raw == "{}":
            return {"bids": [], "asks": []}
        try:
            return json.loads(self.depth_raw)
        except Exception:
            return {"bids": [], "asks": []}


def iter_market_capture_ticks(
    parquet_path: str | Path,
    *,
    token_filter: Sequence[str] | set[str] | None = None,
    start_ts: float | None = None,
    end_ts: float | None = None,
    batch_size: int = 65536,
) -> Iterator[MarketCaptureTick]:
    """Stream ticks strictly in order from a stitched parquet file.

    Zero broker calls. Zero disk writes.
    """
    path = Path(parquet_path)
    if not path.exists():
        raise FileNotFoundError(f"Market capture parquet not found: {path}")

    parquet_file = pq.ParquetFile(path)
    token_set = set(token_filter) if token_filter is not None else None

    for batch in parquet_file.iter_batches(
        batch_size=batch_size,
        columns=["ts", "token", "symbol", "ltp", "bid", "ask", "vol", "oi", "depth"],
    ):
        pydict = batch.to_pydict()
        ts_list = pydict["ts"]
        token_list = pydict["token"]
        symbol_list = pydict["symbol"]
        ltp_list = pydict["ltp"]
        bid_list = pydict["bid"]
        ask_list = pydict["ask"]
        vol_list = pydict["vol"]
        oi_list = pydict["oi"]
        depth_list = pydict["depth"]

        for i in range(len(ts_list)):
            t_val = ts_list[i]
            if start_ts is not None and t_val < start_ts:
                continue
            if end_ts is not None and t_val > end_ts:
                return

            tok = token_list[i]
            if token_set is not None and tok not in token_set:
                continue

            yield MarketCaptureTick(
                ts=float(t_val),
                token=str(tok),
                symbol=str(symbol_list[i]),
                ltp=float(ltp_list[i] or 0.0),
                bid=float(bid_list[i] or 0.0),
                ask=float(ask_list[i] or 0.0),
                vol=float(vol_list[i] or 0.0),
                oi=float(oi_list[i] or 0.0),
                depth_raw=str(depth_list[i] or ""),
            )
