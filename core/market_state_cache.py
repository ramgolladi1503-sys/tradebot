"""Immutable Content-Addressed Market State Cache.

Caches normalized market state consensus snapshots (Spot + Strike OI + VIX)
using cryptographic SHA-256 fingerprinting for O(1) similarity matching
across repeating historical setups.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import numpy as np

from core.causal_synchronized_buffer import MarketStateSnapshot


class MarketStateCache:
    """Content-addressed cache for immutable historical market states."""

    def __init__(self, cache_dir: str | Path = "runtime/market_state_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_index: dict[str, dict[str, Any]] = {}

    @staticmethod
    def compute_fingerprint(snapshot: MarketStateSnapshot) -> str:
        """Generates a deterministic SHA-256 fingerprint for a given market state."""
        state_repr = {
            "spot_round": round(snapshot.spot_price / 50.0) * 50.0,
            "pcr": round(snapshot.strike_pcr, 2),
            "vix_round": round(snapshot.vix, 1),
            "top_strikes": [
                [float(s), round(c, -3), round(p, -3)]
                for s, (c, p) in sorted(snapshot.active_strikes_oi.items())
            ],
        }
        encoded = json.dumps(state_repr, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def store_snapshot(self, snapshot: MarketStateSnapshot, metadata: dict[str, Any] | None = None) -> str:
        """Stores a market state snapshot immutably by its fingerprint."""
        fingerprint = self.compute_fingerprint(snapshot)
        entry = {
            "fingerprint": fingerprint,
            "timestamp": snapshot.horizon_timestamp.isoformat(),
            "spot_price": snapshot.spot_price,
            "spot_vwap": snapshot.spot_vwap,
            "vix": snapshot.vix,
            "strike_pcr": snapshot.strike_pcr,
            "state_vector": snapshot.state_vector().tolist(),
            "metadata": metadata or {},
        }

        self._memory_index[fingerprint] = entry
        target_path = self.cache_dir / f"{fingerprint}.json"
        if not target_path.exists():
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(entry, f, indent=2)

        return fingerprint

    def lookup_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        """Retrieves historical state and past outcomes for a recurring setup."""
        if fingerprint in self._memory_index:
            return self._memory_index[fingerprint]

        target_path = self.cache_dir / f"{fingerprint}.json"
        if target_path.exists():
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._memory_index[fingerprint] = data
                return data

        return None
