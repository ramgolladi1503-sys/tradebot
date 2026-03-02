from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import random
import time
from typing import Any

from core.events import write_json_atomic
from core.paths import logs_dir
from core.time_utils import normalize_epoch_seconds, utc_now


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


@dataclass(frozen=True)
class FillRequest:
    symbol: str
    side: str
    qty: float
    order_type: str
    limit_price: float | None
    ts: float | int | str | None
    ltp: float | None
    bid: float | None
    ask: float | None
    spread: float | None
    depth: dict[str, Any] | None
    volatility: float | None
    latency_ms: int | None


@dataclass(frozen=True)
class FillResult:
    status: str
    filled_qty: float
    avg_price: float | None
    slippage: float | None
    reject_reason: str | None
    partial_fills: list[dict[str, Any]] = field(default_factory=list)
    ts_filled: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)


class FillRealismEngine:
    """
    Deterministic paper/sim fill realism model.

    The model is intentionally conservative:
    - market orders pay touch +/- adverse slippage
    - limit orders fill only when limit crosses executable touch; optional slip veto
    - stale/wide/illiquid quotes reject instead of fantasy fills
    """

    def __init__(self, cfg: Any, rng_seed: int | None = None):
        self.cfg = cfg
        self.rng_seed = int(rng_seed if rng_seed is not None else getattr(cfg, "FILL_REALISM_SEED", 20260227))
        self._metrics_points_limit = max(100, int(getattr(cfg, "FILL_REALISM_METRICS_MAX_POINTS", 5000)))
        self._metrics_records: list[dict[str, Any]] = []

    def _request_rng(self, req: FillRequest) -> random.Random:
        stable = {
            "seed": self.rng_seed,
            "symbol": str(req.symbol or ""),
            "side": str(req.side or "").upper(),
            "qty": float(req.qty or 0.0),
            "order_type": str(req.order_type or "").upper(),
            "limit_price": _safe_float(req.limit_price),
            "ts": normalize_epoch_seconds(req.ts),
            "ltp": _safe_float(req.ltp),
            "bid": _safe_float(req.bid),
            "ask": _safe_float(req.ask),
            "spread": _safe_float(req.spread),
            "volatility": _safe_float(req.volatility),
            "latency_ms": _safe_int(req.latency_ms, int(getattr(self.cfg, "LATENCY_MS", 120))),
        }
        blob = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    @staticmethod
    def _top_of_book_depth(depth: dict[str, Any] | None, side: str) -> float:
        if not isinstance(depth, dict):
            return 0.0
        try:
            levels = depth.get("sell") if side == "BUY" else depth.get("buy")
            if isinstance(levels, list) and levels:
                qty = _safe_float(levels[0].get("quantity"))
                if qty and qty > 0:
                    return float(qty)
        except Exception:
            return 0.0
        return 0.0

    @staticmethod
    def _compute_spread(bid: float | None, ask: float | None, spread_hint: float | None) -> float | None:
        if spread_hint is not None and spread_hint >= 0:
            return float(spread_hint)
        if bid is None or ask is None:
            return None
        spread = ask - bid
        if spread < 0:
            return None
        return float(spread)

    def _spread_multiplier(self, rng: random.Random) -> float:
        raw = getattr(self.cfg, "SPREAD_MULTIPLIER_RANGE", (0.25, 1.0))
        if isinstance(raw, (tuple, list)) and len(raw) >= 2:
            lo = _safe_float(raw[0])
            hi = _safe_float(raw[1])
            if lo is not None and hi is not None:
                lo_f, hi_f = (min(lo, hi), max(lo, hi))
                if abs(hi_f - lo_f) < 1e-12:
                    return float(lo_f)
                return float(rng.uniform(lo_f, hi_f))
        val = _safe_float(raw)
        if val is not None:
            return float(max(val, 0.0))
        return 0.5

    def _quote_age_ms(self, ts_value: Any) -> float | None:
        ts_epoch = normalize_epoch_seconds(ts_value)
        if ts_epoch is None:
            return None
        age = (time.time() - float(ts_epoch)) * 1000.0
        if age < 0:
            return 0.0
        return float(age)

    def _component_slippage(
        self,
        req: FillRequest,
        *,
        mid: float,
        spread: float,
        depth_best: float,
        rng: random.Random,
    ) -> dict[str, float]:
        order_type = str(req.order_type or "LIMIT").upper()
        spread_component = 0.0
        if order_type == "MARKET":
            spread_component = max(0.0, spread) * self._spread_multiplier(rng)

        volatility = abs(_safe_float(req.volatility) or 0.0)
        vol_k = float(max(_safe_float(getattr(self.cfg, "VOL_IMPACT_K", 0.05)) or 0.0, 0.0))
        volatility_component = max(0.0, mid * vol_k * volatility * 0.001)

        depth_k = float(max(_safe_float(getattr(self.cfg, "DEPTH_IMPACT_K", 0.10)) or 0.0, 0.0))
        size_ratio = max(float(req.qty or 0.0), 0.0) / max(depth_best, 1.0)
        depth_impact_component = max(0.0, mid * depth_k * max(size_ratio - 1.0, 0.0) * 0.001)

        latency_ms = _safe_int(req.latency_ms, int(getattr(self.cfg, "LATENCY_MS", 120)))
        # deterministic adverse latency drift proxy (always non-negative in magnitude)
        latency_unit_move = mid * abs(volatility) * 0.0002
        latency_component = max(0.0, latency_unit_move * max(latency_ms, 0) / 1000.0)

        return {
            "spread_component": float(spread_component),
            "volatility_component": float(volatility_component),
            "depth_impact_component": float(depth_impact_component),
            "latency_component": float(latency_component),
        }

    def _reject(self, reason: str, debug: dict[str, Any]) -> FillResult:
        return FillResult(
            status="REJECTED",
            filled_qty=0.0,
            avg_price=None,
            slippage=None,
            reject_reason=str(reason),
            partial_fills=[],
            ts_filled=None,
            debug=dict(debug),
        )

    def _record_metrics(self, req: FillRequest, result: FillResult) -> None:
        record = {
            "symbol": str(req.symbol or ""),
            "order_type": str(req.order_type or "").upper(),
            "status": str(result.status or "").upper(),
            "slippage": _safe_float(result.slippage) or 0.0,
            "latency_ms": _safe_int(req.latency_ms, int(getattr(self.cfg, "LATENCY_MS", 120))),
            "filled_qty": float(result.filled_qty or 0.0),
            "requested_qty": float(req.qty or 0.0),
            "reject_reason": str(result.reject_reason or ""),
            "ts": utc_now().isoformat().replace("+00:00", "Z"),
        }
        self._metrics_records.append(record)
        if len(self._metrics_records) > self._metrics_points_limit:
            drop = len(self._metrics_records) - self._metrics_points_limit
            del self._metrics_records[0:drop]
        self._flush_metrics()

    @staticmethod
    def _p95(values: list[float]) -> float | None:
        clean = sorted(float(v) for v in values if _safe_float(v) is not None)
        if not clean:
            return None
        idx = int(math.ceil(0.95 * len(clean))) - 1
        idx = max(0, min(idx, len(clean) - 1))
        return float(clean[idx])

    def _bucket_summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {
                "count": 0,
                "avg_slippage": 0.0,
                "p95_slippage": 0.0,
                "reject_rate": 0.0,
                "partial_fill_rate": 0.0,
                "avg_fill_latency": 0.0,
            }
        slippages = [_safe_float(r.get("slippage")) or 0.0 for r in rows]
        fill_lat = [_safe_float(r.get("latency_ms")) or 0.0 for r in rows if str(r.get("status")) in {"FILLED", "PARTIAL"}]
        reject_count = sum(1 for r in rows if str(r.get("status")) == "REJECTED")
        partial_count = sum(1 for r in rows if str(r.get("status")) == "PARTIAL")
        return {
            "count": len(rows),
            "avg_slippage": round(sum(slippages) / max(len(slippages), 1), 6),
            "p95_slippage": round(float(self._p95(slippages) or 0.0), 6),
            "reject_rate": round(reject_count / max(len(rows), 1), 6),
            "partial_fill_rate": round(partial_count / max(len(rows), 1), 6),
            "avg_fill_latency": round(sum(fill_lat) / max(len(fill_lat), 1), 6),
        }

    def _flush_metrics(self) -> None:
        rows = list(self._metrics_records)
        by_symbol: dict[str, list[dict[str, Any]]] = {}
        by_order_type: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_symbol.setdefault(str(row.get("symbol") or "UNKNOWN"), []).append(row)
            by_order_type.setdefault(str(row.get("order_type") or "UNKNOWN"), []).append(row)
        payload = {
            "ts_utc": utc_now().isoformat().replace("+00:00", "Z"),
            "seed": self.rng_seed,
            "totals": self._bucket_summary(rows),
            "by_symbol": {k: self._bucket_summary(v) for k, v in sorted(by_symbol.items())},
            "by_order_type": {k: self._bucket_summary(v) for k, v in sorted(by_order_type.items())},
        }
        write_json_atomic(logs_dir() / "fill_realism_metrics.json", payload)

    def simulate_fill(self, req: FillRequest) -> FillResult:
        side = str(req.side or "").upper()
        if side not in {"BUY", "SELL"}:
            out = self._reject("INVALID_SIDE", {"side": side})
            self._record_metrics(req, out)
            return out
        qty = float(req.qty or 0.0)
        if qty <= 0:
            out = self._reject("INVALID_QTY", {"qty": qty})
            self._record_metrics(req, out)
            return out

        bid = _safe_float(req.bid)
        ask = _safe_float(req.ask)
        ltp = _safe_float(req.ltp)
        spread = self._compute_spread(bid, ask, _safe_float(req.spread))
        mid = ((bid + ask) / 2.0) if bid is not None and ask is not None else ltp
        if mid is None or mid <= 0:
            out = self._reject("NO_PRICE", {"bid": bid, "ask": ask, "ltp": ltp})
            self._record_metrics(req, out)
            return out

        age_ms = self._quote_age_ms(req.ts)
        max_quote_age_ms = int(getattr(self.cfg, "MAX_QUOTE_AGE_MS", 2000))
        if age_ms is not None and age_ms > max_quote_age_ms:
            out = self._reject("STALE_QUOTE", {"quote_age_ms": round(age_ms, 3), "max_quote_age_ms": max_quote_age_ms})
            self._record_metrics(req, out)
            return out

        spread_pct = None
        if spread is not None and mid > 0:
            spread_pct = spread / mid
        max_spread_pct_market = float(getattr(self.cfg, "MAX_SPREAD_PCT_FOR_MARKET", 0.015))
        order_type = str(req.order_type or "LIMIT").upper()
        if order_type == "MARKET" and spread_pct is not None and spread_pct > max_spread_pct_market:
            out = self._reject(
                "SPREAD_TOO_WIDE",
                {
                    "spread_pct": round(spread_pct, 8),
                    "max_spread_pct_for_market": max_spread_pct_market,
                },
            )
            self._record_metrics(req, out)
            return out

        if side == "BUY":
            touch_price = ask if ask is not None and ask > 0 else ltp
        else:
            touch_price = bid if bid is not None and bid > 0 else ltp
        if touch_price is None or touch_price <= 0:
            out = self._reject("NO_PRICE", {"touch_price": touch_price})
            self._record_metrics(req, out)
            return out

        rng = self._request_rng(req)
        has_depth_book = isinstance(req.depth, dict) and isinstance(
            req.depth.get("sell") if side == "BUY" else req.depth.get("buy"),
            list,
        )
        depth_best = max(self._top_of_book_depth(req.depth, side), 0.0)
        if depth_best <= 0 and not has_depth_book:
            depth_best = max(float(req.qty or 0.0), 1.0)
        components = self._component_slippage(req, mid=mid, spread=float(spread or 0.0), depth_best=depth_best, rng=rng)
        total_slippage = sum(max(v, 0.0) for v in components.values())

        if side == "BUY":
            slipped_exec_price = float(touch_price + total_slippage)
        else:
            slipped_exec_price = float(max(0.01, touch_price - total_slippage))

        limit_price = _safe_float(req.limit_price)
        crossed_touch = True
        crossed_slipped = True
        if order_type == "LIMIT":
            if limit_price is None or limit_price <= 0:
                out = self._reject("INVALID_LIMIT", {"limit_price": req.limit_price})
                self._record_metrics(req, out)
                return out
            if side == "BUY":
                crossed_touch = limit_price >= touch_price
                crossed_slipped = limit_price >= slipped_exec_price
            else:
                crossed_touch = limit_price <= touch_price
                crossed_slipped = limit_price <= slipped_exec_price
            if not crossed_touch:
                out = FillResult(
                    status="OPEN",
                    filled_qty=0.0,
                    avg_price=None,
                    slippage=0.0,
                    reject_reason="LIMIT_NOT_CROSSED",
                    partial_fills=[],
                    ts_filled=None,
                    debug={
                        "touch_price": round(float(touch_price), 6),
                        "limit_price": round(float(limit_price), 6),
                    },
                )
                self._record_metrics(req, out)
                return out
            if bool(getattr(self.cfg, "LIMIT_ORDER_REJECT_ON_SLIP", True)) and not crossed_slipped:
                out = self._reject(
                    "LIMIT_SLIPPED",
                    {
                        "limit_price": round(float(limit_price), 6),
                        "touch_price": round(float(touch_price), 6),
                        "slipped_exec_price": round(float(slipped_exec_price), 6),
                        "slippage_components": components,
                    },
                )
                self._record_metrics(req, out)
                return out
            # Conservative but limit-respecting execution price.
            exec_price = float(min(limit_price, touch_price) if side == "BUY" else max(limit_price, touch_price))
            total_slippage = abs(exec_price - float(touch_price))
        else:
            exec_price = float(slipped_exec_price)

        allow_partials = bool(getattr(self.cfg, "ALLOW_PARTIAL_FILLS", True))
        if depth_best <= 0:
            out = self._reject("INSUFFICIENT_LIQUIDITY", {"depth_best": depth_best, "qty": qty})
            self._record_metrics(req, out)
            return out
        if qty <= depth_best:
            result = FillResult(
                status="FILLED",
                filled_qty=float(qty),
                avg_price=round(exec_price, 6),
                slippage=round(float(total_slippage), 6),
                reject_reason=None,
                partial_fills=[
                    {
                        "fill_id": "fill-1",
                        "qty": float(qty),
                        "price": round(exec_price, 6),
                    }
                ],
                ts_filled=utc_now().isoformat().replace("+00:00", "Z"),
                debug={
                    "mid_price": round(float(mid), 6),
                    "touch_price": round(float(touch_price), 6),
                    "slippage_components": {k: round(float(v), 8) for k, v in components.items()},
                    "spread_pct": None if spread_pct is None else round(float(spread_pct), 8),
                    "quote_age_ms": None if age_ms is None else round(float(age_ms), 3),
                },
            )
            self._record_metrics(req, result)
            return result

        if not allow_partials:
            out = self._reject("INSUFFICIENT_LIQUIDITY", {"depth_best": depth_best, "qty": qty, "partials_allowed": False})
            self._record_metrics(req, out)
            return out

        first_fill_qty = float(max(min(depth_best, qty), 0.0))
        remaining_qty = float(max(qty - first_fill_qty, 0.0))
        partial_fills = [
            {
                "fill_id": "fill-1",
                "qty": first_fill_qty,
                "price": round(exec_price, 6),
            }
        ]
        if remaining_qty > 0 and bool(getattr(self.cfg, "FILL_REALISM_FILL_REMAINDER_AT_WORSE", False)):
            worsen = abs(total_slippage) if abs(total_slippage) > 0 else abs(float(spread or 0.0)) * 0.5
            remainder_price = exec_price + worsen if side == "BUY" else max(0.01, exec_price - worsen)
            partial_fills.append(
                {
                    "fill_id": "fill-2",
                    "qty": remaining_qty,
                    "price": round(float(remainder_price), 6),
                }
            )
            avg_price = ((first_fill_qty * exec_price) + (remaining_qty * remainder_price)) / max(qty, 1e-9)
            result = FillResult(
                status="FILLED",
                filled_qty=float(qty),
                avg_price=round(float(avg_price), 6),
                slippage=round(abs(float(avg_price) - float(touch_price)), 6),
                reject_reason=None,
                partial_fills=partial_fills,
                ts_filled=utc_now().isoformat().replace("+00:00", "Z"),
                debug={
                    "mid_price": round(float(mid), 6),
                    "touch_price": round(float(touch_price), 6),
                    "remaining_qty": 0.0,
                    "slippage_components": {k: round(float(v), 8) for k, v in components.items()},
                    "spread_pct": None if spread_pct is None else round(float(spread_pct), 8),
                    "quote_age_ms": None if age_ms is None else round(float(age_ms), 3),
                },
            )
            self._record_metrics(req, result)
            return result

        result = FillResult(
            status="PARTIAL",
            filled_qty=first_fill_qty,
            avg_price=round(exec_price, 6),
            slippage=round(float(total_slippage), 6),
            reject_reason="INSUFFICIENT_LIQUIDITY",
            partial_fills=partial_fills,
            ts_filled=utc_now().isoformat().replace("+00:00", "Z"),
            debug={
                "mid_price": round(float(mid), 6),
                "touch_price": round(float(touch_price), 6),
                "remaining_qty": round(remaining_qty, 6),
                "slippage_components": {k: round(float(v), 8) for k, v in components.items()},
                "spread_pct": None if spread_pct is None else round(float(spread_pct), 8),
                "quote_age_ms": None if age_ms is None else round(float(age_ms), 3),
            },
        )
        self._record_metrics(req, result)
        return result


__all__ = ["FillRequest", "FillResult", "FillRealismEngine"]
