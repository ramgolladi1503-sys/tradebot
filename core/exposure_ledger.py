from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

from config import config as cfg


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def estimate_trade_exposure(trade: Any) -> float:
    """
    Premium/notional proxy used for portfolio concentration checks.
    """
    capital_at_risk = _to_float(_get_value(trade, "capital_at_risk"), 0.0)
    if capital_at_risk > 0:
        return capital_at_risk

    entry_price = _to_float(_get_value(trade, "entry_price", _get_value(trade, "entry")), 0.0)
    if entry_price <= 0:
        return 0.0

    qty_units = _to_float(_get_value(trade, "qty_units"), 0.0)
    if qty_units > 0:
        return abs(entry_price * qty_units)

    qty = _to_float(_get_value(trade, "qty"), 0.0)
    if qty <= 0:
        return 0.0

    instrument_type = str(_get_value(trade, "instrument_type", _get_value(trade, "instrument", "OPT")) or "OPT").upper()
    symbol = str(_get_value(trade, "symbol", _get_value(trade, "underlying", "")) or "")
    lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(symbol, 1) or 1)
    qty_proxy = qty * (lot_size if instrument_type == "OPT" else 1)
    return abs(entry_price * qty_proxy)


def _infer_qty_units(trade: Any) -> float:
    qty_units = _to_float(_get_value(trade, "qty_units"), 0.0)
    if qty_units > 0:
        return qty_units
    qty = _to_float(_get_value(trade, "qty"), 0.0)
    if qty <= 0:
        return 0.0
    instrument_type = str(_get_value(trade, "instrument_type", _get_value(trade, "instrument", "OPT")) or "OPT").upper()
    symbol = str(_get_value(trade, "symbol", _get_value(trade, "underlying", "")) or "")
    lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(symbol, 1) or 1)
    if instrument_type == "OPT":
        return qty * lot_size
    return qty


def _side_sign(trade: Any) -> float:
    side = str(_get_value(trade, "side", "BUY") or "BUY").upper()
    return -1.0 if side == "SELL" else 1.0


def _days_to_expiry(expiry: Any) -> float:
    if not expiry:
        return 1.0
    try:
        if isinstance(expiry, str):
            exp_date = datetime.fromisoformat(expiry.replace("Z", "+00:00")).date()
        else:
            exp_date = expiry.date() if hasattr(expiry, "date") else None
        if exp_date is None:
            return 1.0
        delta_days = (exp_date - datetime.now(timezone.utc).date()).days
        return float(max(delta_days, 1))
    except Exception:
        return 1.0


def _as_position_greek(raw: Any, qty_units: float, side_sign: float, threshold: float) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if abs(value) <= threshold:
        return side_sign * value * qty_units
    return side_sign * value


def estimate_trade_greeks(trade: Any) -> tuple[float, float]:
    """
    Returns deterministic proxy greeks for a position:
    (delta_proxy, vega_proxy).
    Uses provided greeks when available; otherwise derives a stable heuristic.
    """
    qty_units = _infer_qty_units(trade)
    if qty_units <= 0:
        return 0.0, 0.0

    side_sign = _side_sign(trade)

    position_delta = _as_position_greek(_get_value(trade, "position_delta"), qty_units, 1.0, threshold=1e9)
    if position_delta is None:
        position_delta = _as_position_greek(_get_value(trade, "delta"), qty_units, side_sign, threshold=2.0)
    position_vega = _as_position_greek(_get_value(trade, "position_vega"), qty_units, 1.0, threshold=1e9)
    if position_vega is None:
        position_vega = _as_position_greek(_get_value(trade, "vega"), qty_units, side_sign, threshold=5.0)

    instrument_type = str(_get_value(trade, "instrument_type", _get_value(trade, "instrument", "OPT")) or "OPT").upper()
    if instrument_type == "FUT":
        return side_sign * qty_units, 0.0
    if instrument_type != "OPT":
        return 0.0, 0.0

    right = str(_get_value(trade, "right", _get_value(trade, "option_type", "CE")) or "CE").upper()
    right_sign = 1.0 if right == "CE" else -1.0

    strike = _to_float(_get_value(trade, "strike"), 0.0)
    spot = _to_float(
        _get_value(
            trade,
            "underlying_ltp",
            _get_value(
                trade,
                "spot",
                _get_value(trade, "ltp"),
            ),
        ),
        0.0,
    )
    if strike <= 0 or spot <= 0:
        moneyness_gap = 0.0
    else:
        moneyness_gap = abs(spot - strike) / max(strike, 1.0)
    atm_weight = max(0.1, 1.0 - (moneyness_gap / 0.02))

    iv = _to_float(_get_value(trade, "iv", _get_value(trade, "implied_volatility", 0.2)), 0.2)
    iv = min(max(iv, 0.05), 1.5)
    dte_days = _days_to_expiry(_get_value(trade, "expiry"))
    time_weight = min(max(math.sqrt(dte_days / 30.0), 0.35), 2.0)

    delta_unit = right_sign * (0.2 + (0.6 * atm_weight))
    vega_unit = (0.05 + (0.25 * atm_weight)) * iv * time_weight
    delta_proxy = side_sign * delta_unit * qty_units
    vega_proxy = side_sign * vega_unit * qty_units

    if position_delta is None:
        position_delta = delta_proxy
    if position_vega is None:
        position_vega = vega_proxy
    return float(position_delta), float(position_vega)


@dataclass
class ExposureSnapshot:
    exposure_by_underlying: dict[str, float]
    exposure_by_underlying_pct: dict[str, float]
    exposure_by_expiry: dict[str, float]
    exposure_by_expiry_pct: dict[str, float]
    open_positions_count_by_underlying: dict[str, int]
    total_open_exposure: float
    total_open_exposure_pct: float
    net_delta: float
    net_vega: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "exposure_by_underlying": dict(self.exposure_by_underlying),
            "exposure_by_underlying_pct": dict(self.exposure_by_underlying_pct),
            "exposure_by_expiry": dict(self.exposure_by_expiry),
            "exposure_by_expiry_pct": dict(self.exposure_by_expiry_pct),
            "open_positions_count_by_underlying": dict(self.open_positions_count_by_underlying),
            "total_open_exposure": float(self.total_open_exposure),
            "total_open_exposure_pct": float(self.total_open_exposure_pct),
            "net_delta": float(self.net_delta),
            "net_vega": float(self.net_vega),
        }


class ExposureLedger:
    def __init__(self, total_capital: float | None = None):
        self.total_capital = _to_float(total_capital, 0.0)

    def snapshot_from_open_trades(
        self,
        open_trades: dict[str, list[Any]] | None,
        total_capital: float | None = None,
    ) -> ExposureSnapshot:
        capital = _to_float(total_capital, self.total_capital)
        exposure_by_underlying: dict[str, float] = defaultdict(float)
        exposure_by_expiry: dict[str, float] = defaultdict(float)
        count_by_underlying: dict[str, int] = defaultdict(int)
        total_open_exposure = 0.0
        net_delta = 0.0
        net_vega = 0.0

        for trades in (open_trades or {}).values():
            for trade in trades or []:
                underlying = str(_get_value(trade, "symbol", _get_value(trade, "underlying", "UNKNOWN")) or "UNKNOWN").upper()
                expiry = _get_value(trade, "expiry")
                exposure = estimate_trade_exposure(trade)
                if exposure <= 0:
                    continue
                exposure_by_underlying[underlying] += exposure
                count_by_underlying[underlying] += 1
                if expiry:
                    exposure_by_expiry[str(expiry)] += exposure
                total_open_exposure += exposure
                delta_proxy, vega_proxy = estimate_trade_greeks(trade)
                net_delta += float(delta_proxy)
                net_vega += float(vega_proxy)

        exposure_by_underlying_pct: dict[str, float] = {}
        if capital > 0:
            for key, value in exposure_by_underlying.items():
                exposure_by_underlying_pct[key] = float(value) / capital
        else:
            for key in exposure_by_underlying:
                exposure_by_underlying_pct[key] = 0.0

        exposure_by_expiry_pct: dict[str, float] = {}
        if total_open_exposure > 0:
            for key, value in exposure_by_expiry.items():
                exposure_by_expiry_pct[key] = float(value) / total_open_exposure
        else:
            for key in exposure_by_expiry:
                exposure_by_expiry_pct[key] = 0.0

        total_open_exposure_pct = (total_open_exposure / capital) if capital > 0 else 0.0
        return ExposureSnapshot(
            exposure_by_underlying=dict(exposure_by_underlying),
            exposure_by_underlying_pct=exposure_by_underlying_pct,
            exposure_by_expiry=dict(exposure_by_expiry),
            exposure_by_expiry_pct=exposure_by_expiry_pct,
            open_positions_count_by_underlying=dict(count_by_underlying),
            total_open_exposure=total_open_exposure,
            total_open_exposure_pct=total_open_exposure_pct,
            net_delta=net_delta,
            net_vega=net_vega,
        )
