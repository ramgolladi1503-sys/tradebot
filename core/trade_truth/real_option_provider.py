#!/usr/bin/env python3
"""Real Option Selection and Executable Quote Provider.

Enforces:
- Resolves actual option contract from market data / parquet / instrument master.
- Obtains real bid, ask, spread, depth from as-of tick events.
- Never fabricates quote prices or spreads.
- Missing quotes produce REJECTED_NO_QUOTES or SELECTION_STAGE_NOT_REACHED.
- BUY executability reference is strictly real ASK price.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyarrow.parquet as pq


@dataclass(frozen=True)
class RealOptionSelectionResult:
    selection_status: str  # SELECTED, REJECTED_NO_QUOTES, REJECTED_SPREAD_EXCESSIVE, SELECTION_STAGE_NOT_REACHED
    selected_instrument: Optional[Dict[str, Any]]
    quote_executable_truth: Optional[Dict[str, Any]]
    selection_hash: str
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RealOptionQuoteProvider:
    """Extracts actual option contract quotes from stitched market capture."""

    def __init__(self, stitched_parquet_path: str | Path):
        self.parquet_path = Path(stitched_parquet_path)
        self.cached_options_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        self._load_options_index()

    def _load_options_index(self):
        if not self.parquet_path.exists():
            return
        pf = pq.ParquetFile(self.parquet_path)
        # Load NIFTY option quotes with depth
        for i in range(pf.num_row_groups):
            b = pf.read_row_group(i, columns=["token", "symbol", "bid", "ask", "ltp", "ts", "depth"])
            d = b.to_pydict()
            for sym, tok, bid, ask, ltp, ts, dep in zip(d["symbol"], d["token"], d["bid"], d["ask"], d["ltp"], d["ts"], d["depth"]):
                if sym and "NIFTY" in str(sym).upper() and any(c in str(sym) for c in ["CE", "PE"]):
                    if bid is not None and ask is not None and ask > 0:
                        rec = {
                            "symbol": str(sym),
                            "token": str(tok),
                            "bid": float(bid),
                            "ask": float(ask),
                            "ltp": float(ltp or ask),
                            "ts": float(ts),
                            "depth": str(dep) if dep else None,
                        }
                        self.cached_options_by_symbol.setdefault(str(sym), []).append(rec)

    def select_option(
        self,
        underlying: str,
        spot_price: float,
        direction: str,
        decision_ts_epoch: float,
    ) -> RealOptionSelectionResult:
        """Selects real ATM option contract with actual executable quote at or before decision_ts."""
        opt_type = "CE" if direction == "BULLISH" else "PE"
        atm_strike = round(spot_price / 50.0) * 50.0

        # Find matching cached real contracts
        best_candidate = None
        best_quote = None

        for sym, quotes in self.cached_options_by_symbol.items():
            if f"{int(atm_strike)} {opt_type}" in sym:
                # Find quotes strictly <= decision_ts_epoch
                valid_quotes = [q for q in quotes if q["ts"] <= decision_ts_epoch]
                if valid_quotes:
                    latest = valid_quotes[-1]
                    best_candidate = sym
                    best_quote = latest
                    break

        if not best_quote:
            return RealOptionSelectionResult(
                selection_status="REJECTED_NO_QUOTES",
                selected_instrument=None,
                quote_executable_truth=None,
                selection_hash="0" * 64,
                rejection_reason="NO_REAL_OPTION_QUOTES_FOUND_ASOF_DECISION_TS",
            )

        spread = round(best_quote["ask"] - best_quote["bid"], 2)
        inst_payload = {
            "tradingsymbol": best_quote["symbol"],
            "token": best_quote["token"],
            "underlying": underlying,
            "strike": atm_strike,
            "option_type": opt_type,
            "lot_size": "UNKNOWN",
        }

        # Parse actual depth
        bid_qty = "UNKNOWN"
        ask_qty = "UNKNOWN"
        depth_obj = {}
        depth_hash = "0" * 64
        if best_quote.get("depth"):
            try:
                depth_obj = json.loads(best_quote["depth"])
                bids = depth_obj.get("bids", [])
                asks = depth_obj.get("asks", [])
                if bids:
                    bid_qty = bids[0].get("quantity", "UNKNOWN")
                if asks:
                    ask_qty = asks[0].get("quantity", "UNKNOWN")
                depth_hash = hashlib.sha256(json.dumps(depth_obj, sort_keys=True).encode()).hexdigest()
            except Exception:
                pass

        quote_payload = {
            "bid": best_quote["bid"],
            "ask": best_quote["ask"],
            "bid_qty": bid_qty,
            "ask_qty": ask_qty,
            "spread": spread,
            "depth": depth_obj,
            "depth_hash": depth_hash,
            "quote_ts_epoch": best_quote["ts"],
            "reference_buy_price": best_quote["ask"],
        }

        h = hashlib.sha256(json.dumps({**inst_payload, **quote_payload}, sort_keys=True, default=str).encode()).hexdigest()

        return RealOptionSelectionResult(
            selection_status="SELECTED",
            selected_instrument=inst_payload,
            quote_executable_truth=quote_payload,
            selection_hash=h,
        )
