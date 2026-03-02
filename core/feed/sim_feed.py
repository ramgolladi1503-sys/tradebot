from __future__ import annotations

from copy import deepcopy
from typing import Any


_INDEX_SNAPSHOT = {
    "symbol": "NIFTY",
    "ltp": 22500.0,
    "bid": 22499.5,
    "ask": 22500.5,
    "ts": "2026-01-01T09:15:00Z",
}

_OPTION_SNAPSHOT = {
    "symbol": "NIFTY26FEB22500CE",
    "ltp": 120.0,
    "bid": 119.5,
    "ask": 120.5,
    "ts": "2026-01-01T09:15:00Z",
}

_DEPTH = {
    "buy": [{"price": 119.5, "qty": 50}],
    "sell": [{"price": 120.5, "qty": 40}],
}


class SimFeed:
    def get_snapshot(self, symbol: str) -> dict[str, Any]:
        text = str(symbol or "").upper()
        if "CE" in text or "PE" in text:
            row = deepcopy(_OPTION_SNAPSHOT)
        elif "NIFTY" in text or "BANKNIFTY" in text or "SENSEX" in text:
            row = deepcopy(_INDEX_SNAPSHOT)
        else:
            row = deepcopy(_OPTION_SNAPSHOT)
        row["symbol"] = str(symbol or row["symbol"])
        return row

    def get_depth(self, symbol: str) -> dict[str, Any]:
        data = deepcopy(_DEPTH)
        data["symbol"] = str(symbol or "")
        data["ts"] = "2026-01-01T09:15:00Z"
        return data
