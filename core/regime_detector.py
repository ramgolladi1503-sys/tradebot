from __future__ import annotations

from typing import Any

from core.market_data import get_current_regime


class RegimeDetector:
    """Canonical compatibility wrapper for legacy RegimeDetector imports.

    Keep this class thin. Regime truth belongs in core.market_data.get_current_regime;
    this wrapper exists so old callers/tests do not create a second regime source.
    """

    def detect(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        symbol = "NIFTY"
        if isinstance(payload, dict):
            symbol = str(payload.get("symbol") or payload.get("underlying") or symbol).strip().upper() or symbol
        snap = get_current_regime(symbol)
        return {
            "regime": snap.get("primary_regime", "NEUTRAL"),
            **snap,
        }
