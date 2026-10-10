"""Institutional Session Regime Memory & Structural Fingerprint Store.

Causally persists daily session fingerprints:
- Kaufman Efficiency Ratio (KER)
- Opening Range (OR) width & extension ratio
- Volatility velocity (total path / high-low range)
- Setup win rates (Rejection Wicks vs Breakouts)
- Post-market forensic lessons

Provides real-time nearest-neighbor retrieval:
When an active market session exhibits similar early intraday features,
the engine retrieves matching historical sessions and adjusts playbook weights.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

MEMORY_STORE_PATH = Path("artifacts/session_regime_memory.json")


def load_session_memory() -> Dict[str, Any]:
    """Loads historical session memory bank."""
    if not MEMORY_STORE_PATH.exists():
        return {"version": 1, "sessions": {}}
    try:
        with open(MEMORY_STORE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "sessions": {}}


def record_session_fingerprint(
    date_str: str,
    open_price: float,
    close_price: float,
    day_high: float,
    day_low: float,
    or_high: float,
    or_low: float,
    total_path: float,
    ker: float,
    classified_regime: str,
    rejection_wick_win_rate: float,
    breakout_win_rate: float,
    key_lesson: str
) -> Dict[str, Any]:
    """Records a completed session fingerprint to persistent memory."""
    store = load_session_memory()
    
    fingerprint = {
        "date": date_str,
        "recorded_at": datetime.now().isoformat(),
        "open": round(open_price, 2),
        "close": round(close_price, 2),
        "day_high": round(day_high, 2),
        "day_low": round(day_low, 2),
        "total_day_range": round(day_high - day_low, 2),
        "or_high": round(or_high, 2),
        "or_low": round(or_low, 2),
        "or_width": round(or_high - or_low, 2),
        "total_path_distance": round(total_path, 2),
        "ker_efficiency_ratio": round(ker, 4),
        "classified_regime": classified_regime,
        "rejection_wick_win_rate": round(rejection_wick_win_rate, 3),
        "breakout_win_rate": round(breakout_win_rate, 3),
        "key_lesson": key_lesson
    }
    
    store["sessions"][date_str] = fingerprint
    
    MEMORY_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)
        
    return fingerprint


def find_similar_sessions(current_ker: float, current_or_width: float, top_k: int = 3) -> List[Dict[str, Any]]:
    """Retrieves top-k historical sessions matching current efficiency ratio & OR width."""
    store = load_session_memory()
    sessions = list(store.get("sessions", {}).values())
    if not sessions:
        return []
        
    def distance(s):
        # Normalized distance across KER and OR width
        d_ker = abs(s.get("ker_efficiency_ratio", 0.05) - current_ker) / 0.10
        d_or = abs(s.get("or_width", 100.0) - current_or_width) / 50.0
        return d_ker + d_or

    sorted_sessions = sorted(sessions, key=distance)
    return sorted_sessions[:top_k]

