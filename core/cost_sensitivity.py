from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
from typing import Any

from config import config as cfg
from core.events import events_path, write_json_atomic
from core.paths import logs_dir
from core.time_utils import normalize_epoch_seconds, utc_now


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return float(default)
        return float(out)
    except Exception:
        return float(default)


def _safe_ts(value: Any) -> float:
    out = normalize_epoch_seconds(value)
    if out is None:
        return 0.0
    return float(out)


def _pct(part: float, whole: float) -> float:
    if whole == 0:
        return 0.0
    return float(part) / float(whole)


def _p95(values: list[float]) -> float:
    clean = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not clean:
        return 0.0
    idx = int(math.ceil(0.95 * len(clean))) - 1
    idx = max(0, min(idx, len(clean) - 1))
    return float(clean[idx])


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / max(len(values), 1))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


@dataclass(frozen=True)
class TradeCostInputs:
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float | None
    spread: float
    slippage: float
    fees: float
    latency_ms: float
    notional: float
    pnl_gross: float
    pnl_net: float
    strategy: str = "UNKNOWN"
    order_id: str = ""
    trade_id: str = ""
    ts: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    fee_bps: float = 0.0
    expected_cost_bps: float = 0.0
    status: str = "FILLED"
    reject_reason: str | None = None
    partial: bool = False


@dataclass(frozen=True)
class CostKPIReport:
    window: dict[str, Any]
    totals: dict[str, Any]
    by_symbol: dict[str, Any]
    by_strategy: dict[str, Any]
    distributions: dict[str, Any]
    thresholds: dict[str, Any]
    status: str
    breaches: list[dict[str, Any]]
    fix_hints: list[str]
    top_slippage_trades: list[dict[str, Any]]
    top_spread_moments: list[dict[str, Any]]
    top_reject_reasons: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _TradeCostList(list):
    def __init__(self, rows: list[TradeCostInputs], *, meta: dict[str, Any]):
        super().__init__(rows)
        self.meta = dict(meta or {})


def estimate_fees(notional: float, cfg_obj=cfg) -> float:
    brokerage_bps = float(getattr(cfg_obj, "COST_BROKERAGE_BPS", 2.0))
    exchange_bps = float(getattr(cfg_obj, "COST_EXCHANGE_BPS", 0.6))
    taxes_bps = float(getattr(cfg_obj, "COST_TAXES_BPS", 0.4))
    fixed_fee = float(getattr(cfg_obj, "COST_FIXED_FEE_PER_ORDER", 0.0))
    total_bps = max(brokerage_bps + exchange_bps + taxes_bps, 0.0)
    fee = float(notional) * (total_bps / 10000.0) + max(fixed_fee, 0.0)
    return max(fee, 0.0)


def parse_execution_events(path: Path | None = None) -> list[TradeCostInputs]:
    target = Path(path) if path is not None else events_path()
    rows = _read_jsonl(target)
    fill_rows: list[dict[str, Any]] = []
    reject_reasons: Counter[str] = Counter()
    submitted = 0
    rejected = 0
    partial_order_ids: set[str] = set()

    for row in rows:
        event_type = str(row.get("type") or "").strip().lower()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if event_type == "order_submitted":
            submitted += 1
            continue
        if event_type == "order_open":
            partial_order_ids.add(str(payload.get("order_id") or ""))
            continue
        if event_type == "order_rejected":
            rejected += 1
            reject_reasons[str(payload.get("reason") or "unknown")] += 1
            continue
        if event_type != "fill":
            continue

        qty = max(_safe_float(payload.get("qty"), 0.0), 0.0)
        price = _safe_float(payload.get("price"), 0.0)
        if qty <= 0 or price <= 0:
            continue
        spread = _safe_float(payload.get("spread"), 0.0)
        spread_bps = _safe_float(payload.get("spread_bps"), 0.0)
        if spread <= 0 and spread_bps > 0:
            spread = price * spread_bps / 10000.0
        if spread_bps <= 0 and spread > 0 and price > 0:
            spread_bps = spread / price * 10000.0
        slippage = _safe_float(payload.get("slippage"), 0.0)
        slippage_bps = _safe_float(payload.get("slippage_bp"), 0.0)
        if slippage <= 0 and slippage_bps > 0:
            slippage = price * slippage_bps / 10000.0
        if slippage_bps <= 0 and slippage > 0 and price > 0:
            slippage_bps = slippage / price * 10000.0

        fill_rows.append(
            {
                "ts": _safe_ts(row.get("ts") or payload.get("ts")),
                "order_id": str(payload.get("order_id") or ""),
                "trade_id": str(payload.get("trade_id") or ""),
                "symbol": str(payload.get("symbol") or "UNKNOWN"),
                "side": str(payload.get("side") or "").upper(),
                "strategy": str(payload.get("strategy") or "UNKNOWN"),
                "qty": qty,
                "price": price,
                "spread": spread,
                "spread_bps": spread_bps,
                "slippage": slippage,
                "slippage_bps": slippage_bps,
                "latency_ms": _safe_float(payload.get("latency_ms"), 0.0),
                "order_type": str(payload.get("order_type") or ""),
            }
        )

    fill_rows.sort(key=lambda row: float(row.get("ts") or 0.0))

    positions: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "qty": 0.0,
            "avg_price": 0.0,
            "side": "",
            "fee_pool": 0.0,
            "strategy": "UNKNOWN",
            "symbol": "UNKNOWN",
        }
    )
    trades: list[TradeCostInputs] = []

    for fill in fill_rows:
        symbol = str(fill.get("symbol") or "UNKNOWN")
        strategy = str(fill.get("strategy") or "UNKNOWN")
        trade_id = str(fill.get("trade_id") or "")
        key = trade_id if trade_id else f"{symbol}|{strategy}"
        qty = float(fill["qty"])
        price = float(fill["price"])
        side = str(fill.get("side") or "").upper()
        if side not in {"BUY", "SELL"}:
            continue
        sign = 1.0 if side == "BUY" else -1.0
        notional = abs(price * qty)
        fill_fee = estimate_fees(notional, cfg)
        fee_per_qty = fill_fee / max(qty, 1e-9)

        state = positions[key]
        state["strategy"] = strategy
        state["symbol"] = symbol

        prev_qty = float(state["qty"])
        prev_side = str(state["side"] or "")
        prev_avg = float(state["avg_price"] or 0.0)
        prev_fee_pool = float(state["fee_pool"] or 0.0)

        if prev_qty == 0 or prev_side == side:
            new_qty = prev_qty + qty
            new_avg = ((prev_avg * prev_qty) + (price * qty)) / max(new_qty, 1e-9)
            state["qty"] = new_qty
            state["avg_price"] = new_avg
            state["side"] = side
            state["fee_pool"] = prev_fee_pool + fill_fee
            trades.append(
                TradeCostInputs(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=price,
                    exit_price=None,
                    spread=float(fill["spread"]),
                    slippage=float(fill["slippage"]),
                    fees=float(fill_fee),
                    latency_ms=float(fill["latency_ms"]),
                    notional=float(notional),
                    pnl_gross=0.0,
                    pnl_net=-float(fill_fee),
                    strategy=strategy,
                    order_id=str(fill.get("order_id") or ""),
                    trade_id=trade_id,
                    ts=float(fill["ts"]),
                    spread_bps=float(fill["spread_bps"]),
                    slippage_bps=float(fill["slippage_bps"]),
                    fee_bps=float(_pct(fill_fee, notional) * 10000.0),
                    expected_cost_bps=float(
                        (float(fill["spread_bps"]) * 0.5) + float(fill["slippage_bps"]) + (_pct(fill_fee, notional) * 10000.0)
                    ),
                    status="ENTRY_ONLY",
                    reject_reason=None,
                    partial=str(fill.get("order_id") or "") in partial_order_ids,
                )
            )
            continue

        close_qty = min(prev_qty, qty)
        entry_fee_alloc = prev_fee_pool * _pct(close_qty, prev_qty)
        close_fee = fee_per_qty * close_qty

        if prev_side == "BUY" and side == "SELL":
            pnl_gross = (price - prev_avg) * close_qty
        elif prev_side == "SELL" and side == "BUY":
            pnl_gross = (prev_avg - price) * close_qty
        else:
            pnl_gross = 0.0
        pnl_net = pnl_gross - entry_fee_alloc - close_fee

        trades.append(
            TradeCostInputs(
                symbol=symbol,
                side=side,
                qty=close_qty,
                entry_price=float(prev_avg),
                exit_price=price,
                spread=float(fill["spread"]),
                slippage=float(fill["slippage"]),
                fees=float(entry_fee_alloc + close_fee),
                latency_ms=float(fill["latency_ms"]),
                notional=float(close_qty * price),
                pnl_gross=float(pnl_gross),
                pnl_net=float(pnl_net),
                strategy=strategy,
                order_id=str(fill.get("order_id") or ""),
                trade_id=trade_id,
                ts=float(fill["ts"]),
                spread_bps=float(fill["spread_bps"]),
                slippage_bps=float(fill["slippage_bps"]),
                fee_bps=float(_pct(entry_fee_alloc + close_fee, max(close_qty * price, 1e-9)) * 10000.0),
                expected_cost_bps=float(
                    (float(fill["spread_bps"]) * 0.5)
                    + float(fill["slippage_bps"])
                    + _pct(entry_fee_alloc + close_fee, max(close_qty * price, 1e-9)) * 10000.0
                ),
                status="ROUND_TRIP",
                reject_reason=None,
                partial=str(fill.get("order_id") or "") in partial_order_ids,
            )
        )

        state["qty"] = max(prev_qty - close_qty, 0.0)
        state["fee_pool"] = max(prev_fee_pool - entry_fee_alloc, 0.0)
        if state["qty"] == 0:
            state["avg_price"] = 0.0
            state["side"] = ""

        remainder = max(qty - close_qty, 0.0)
        if remainder > 0:
            remainder_fee = fee_per_qty * remainder
            state["qty"] = state["qty"] + remainder
            state["avg_price"] = price
            state["side"] = side
            state["fee_pool"] = state["fee_pool"] + remainder_fee

    meta = {
        "events_path": str(target),
        "submitted_count": submitted,
        "rejected_count": rejected,
        "partial_order_count": len(partial_order_ids),
        "reject_reasons": dict(reject_reasons),
        "fill_count": len(fill_rows),
    }
    return _TradeCostList(trades, meta=meta)


def _kpi_thresholds(cfg_obj=cfg) -> dict[str, float]:
    return {
        "MAX_REJECT_RATE": float(getattr(cfg_obj, "MAX_REJECT_RATE", 0.35)),
        "MAX_P95_SLIPPAGE_BPS": float(getattr(cfg_obj, "MAX_P95_SLIPPAGE_BPS", 15.0)),
        "MAX_P95_SPREAD_BPS": float(getattr(cfg_obj, "MAX_P95_SPREAD_BPS", 25.0)),
        "MIN_NET_EDGE_RATIO": float(getattr(cfg_obj, "MIN_NET_EDGE_RATIO", 0.60)),
        "MIN_NET_WINRATE": float(getattr(cfg_obj, "MIN_NET_WINRATE", 0.0)),
    }


def _build_breakdown(rows: list[TradeCostInputs], key_name: str) -> dict[str, Any]:
    groups: dict[str, list[TradeCostInputs]] = defaultdict(list)
    for row in rows:
        value = getattr(row, key_name, "UNKNOWN")
        groups[str(value or "UNKNOWN")].append(row)
    out: dict[str, Any] = {}
    for key, items in sorted(groups.items()):
        pnl_gross = sum(float(r.pnl_gross) for r in items)
        pnl_net = sum(float(r.pnl_net) for r in items)
        out[key] = {
            "count": len(items),
            "avg_slippage_bps": round(_mean([float(r.slippage_bps) for r in items]), 6),
            "p95_slippage_bps": round(_p95([float(r.slippage_bps) for r in items]), 6),
            "avg_spread_bps": round(_mean([float(r.spread_bps) for r in items]), 6),
            "p95_spread_bps": round(_p95([float(r.spread_bps) for r in items]), 6),
            "pnl_gross_total": round(float(pnl_gross), 6),
            "pnl_net_total": round(float(pnl_net), 6),
        }
    return out


def compute_cost_kpis(trades: list[TradeCostInputs], cfg_obj=cfg) -> CostKPIReport:
    trade_rows = list(trades or [])
    meta = dict(getattr(trades, "meta", {}) or {})
    thresholds = _kpi_thresholds(cfg_obj)

    window_trades = int(getattr(cfg_obj, "COST_GATE_WINDOW_TRADES", 50))
    if window_trades > 0 and len(trade_rows) > window_trades:
        trade_rows = trade_rows[-window_trades:]

    slippage_abs = [abs(float(r.slippage)) for r in trade_rows]
    slippage_bps = [abs(float(r.slippage_bps)) for r in trade_rows]
    spread_bps = [abs(float(r.spread_bps)) for r in trade_rows]
    fee_bps = [abs(float(r.fee_bps)) for r in trade_rows]
    expected_cost_bps = [abs(float(r.expected_cost_bps)) for r in trade_rows]
    round_trips = [r for r in trade_rows if str(r.status) == "ROUND_TRIP" and r.exit_price is not None]

    pnl_gross_total = float(sum(float(r.pnl_gross) for r in round_trips))
    pnl_net_total = float(sum(float(r.pnl_net) for r in round_trips))
    gross_profitable = sum(1 for r in round_trips if float(r.pnl_gross) > 0)
    net_profitable = sum(1 for r in round_trips if float(r.pnl_net) > 0)

    submitted_count = int(meta.get("submitted_count") or 0)
    rejected_count = int(meta.get("rejected_count") or 0)
    partial_count = int(meta.get("partial_order_count") or 0)
    fill_count = int(meta.get("fill_count") or len(trade_rows))
    reject_rate = _pct(rejected_count, max(submitted_count, rejected_count + fill_count))
    partial_rate = _pct(partial_count, max(submitted_count, fill_count))

    gross_base = max(abs(pnl_gross_total), 1.0)
    net_edge_ratio = float(pnl_net_total / gross_base)
    edge_erosion = float((pnl_gross_total - pnl_net_total) / gross_base)
    net_winrate = _pct(net_profitable, len(round_trips))
    gross_winrate = _pct(gross_profitable, len(round_trips))

    totals = {
        "trades_considered": len(trade_rows),
        "round_trips": len(round_trips),
        "avg_slippage_abs": round(_mean(slippage_abs), 6),
        "p95_slippage_abs": round(_p95(slippage_abs), 6),
        "avg_slippage_bps": round(_mean(slippage_bps), 6),
        "p95_slippage_bps": round(_p95(slippage_bps), 6),
        "reject_rate": round(float(reject_rate), 6),
        "partial_fill_rate": round(float(partial_rate), 6),
        "avg_spread_bps": round(_mean(spread_bps), 6),
        "p95_spread_bps": round(_p95(spread_bps), 6),
        "avg_fee_bps": round(_mean(fee_bps), 6),
        "pnl_gross_total": round(float(pnl_gross_total), 6),
        "pnl_net_total": round(float(pnl_net_total), 6),
        "net_edge_ratio": round(float(net_edge_ratio), 6),
        "gross_profitable_rate": round(float(gross_winrate), 6),
        "net_profitable_rate": round(float(net_winrate), 6),
        "edge_erosion": round(float(edge_erosion), 6),
        "entry_expected_cost_bps_avg": round(_mean(expected_cost_bps), 6),
        "entry_expected_cost_bps_p95": round(_p95(expected_cost_bps), 6),
    }

    breaches: list[dict[str, Any]] = []
    if totals["reject_rate"] > thresholds["MAX_REJECT_RATE"]:
        breaches.append(
            {
                "code": "MAX_REJECT_RATE",
                "value": totals["reject_rate"],
                "threshold": thresholds["MAX_REJECT_RATE"],
                "fix_hint": "High reject rate: relax over-strict gates carefully or improve feed/quote stability.",
            }
        )
    if totals["p95_slippage_bps"] > thresholds["MAX_P95_SLIPPAGE_BPS"]:
        breaches.append(
            {
                "code": "MAX_P95_SLIPPAGE_BPS",
                "value": totals["p95_slippage_bps"],
                "threshold": thresholds["MAX_P95_SLIPPAGE_BPS"],
                "fix_hint": "High slippage: reduce market-order usage, tighten price bands, reduce size versus depth.",
            }
        )
    if totals["p95_spread_bps"] > thresholds["MAX_P95_SPREAD_BPS"]:
        breaches.append(
            {
                "code": "MAX_P95_SPREAD_BPS",
                "value": totals["p95_spread_bps"],
                "threshold": thresholds["MAX_P95_SPREAD_BPS"],
                "fix_hint": "Wide spreads: avoid illiquid strikes, require depth presence, tighten entry windows.",
            }
        )
    if len(round_trips) > 0 and totals["net_edge_ratio"] < thresholds["MIN_NET_EDGE_RATIO"]:
        breaches.append(
            {
                "code": "MIN_NET_EDGE_RATIO",
                "value": totals["net_edge_ratio"],
                "threshold": thresholds["MIN_NET_EDGE_RATIO"],
                "fix_hint": "Costs erase edge: reduce slippage exposure, constrain order aggressiveness, improve liquidity filters.",
            }
        )
    if len(round_trips) > 0 and thresholds["MIN_NET_WINRATE"] > 0 and totals["net_profitable_rate"] < thresholds["MIN_NET_WINRATE"]:
        breaches.append(
            {
                "code": "MIN_NET_WINRATE",
                "value": totals["net_profitable_rate"],
                "threshold": thresholds["MIN_NET_WINRATE"],
                "fix_hint": "Net winrate below threshold: reassess strategy quality under realistic fills and fees.",
            }
        )

    status = "PASS" if not breaches else "FAIL"
    distributions = {
        "slippage_bps": {
            "min": round(min(slippage_bps), 6) if slippage_bps else 0.0,
            "p50": round(_p95(sorted(slippage_bps)[: max(1, len(slippage_bps) // 2)]) if slippage_bps else 0.0, 6),
            "p95": round(_p95(slippage_bps), 6),
            "max": round(max(slippage_bps), 6) if slippage_bps else 0.0,
        },
        "spread_bps": {
            "min": round(min(spread_bps), 6) if spread_bps else 0.0,
            "p95": round(_p95(spread_bps), 6),
            "max": round(max(spread_bps), 6) if spread_bps else 0.0,
        },
        "expected_cost_bps": {
            "avg": round(_mean(expected_cost_bps), 6),
            "p95": round(_p95(expected_cost_bps), 6),
        },
    }

    top_slippage = sorted(
        trade_rows,
        key=lambda row: abs(float(row.slippage_bps)),
        reverse=True,
    )[:5]
    top_spreads = sorted(
        trade_rows,
        key=lambda row: abs(float(row.spread_bps)),
        reverse=True,
    )[:5]
    top_rejects = sorted(
        (meta.get("reject_reasons") or {}).items(),
        key=lambda item: int(item[1]),
        reverse=True,
    )[:5]

    fix_hints = [str(item.get("fix_hint")) for item in breaches]

    return CostKPIReport(
        window={
            "window_trades": int(window_trades),
            "events_path": str(meta.get("events_path") or events_path()),
            "generated_ts": utc_now().isoformat().replace("+00:00", "Z"),
        },
        totals=totals,
        by_symbol=_build_breakdown(trade_rows, "symbol"),
        by_strategy=_build_breakdown(trade_rows, "strategy"),
        distributions=distributions,
        thresholds=thresholds,
        status=status,
        breaches=breaches,
        fix_hints=fix_hints,
        top_slippage_trades=[
            {
                "symbol": row.symbol,
                "strategy": row.strategy,
                "order_id": row.order_id,
                "slippage_bps": round(float(row.slippage_bps), 6),
                "spread_bps": round(float(row.spread_bps), 6),
                "qty": round(float(row.qty), 6),
            }
            for row in top_slippage
        ],
        top_spread_moments=[
            {
                "symbol": row.symbol,
                "strategy": row.strategy,
                "order_id": row.order_id,
                "spread_bps": round(float(row.spread_bps), 6),
                "slippage_bps": round(float(row.slippage_bps), 6),
                "qty": round(float(row.qty), 6),
            }
            for row in top_spreads
        ],
        top_reject_reasons=[{"reason": str(reason), "count": int(count)} for reason, count in top_rejects],
    )


def _write_text_atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return path


def _render_md(report: CostKPIReport) -> str:
    data = report.to_dict()
    totals = data["totals"]
    lines = [
        "# Cost Sensitivity KPIs",
        "",
        f"- status: {data.get('status')}",
        f"- window_trades: {data.get('window', {}).get('window_trades')}",
        f"- generated_ts: {data.get('window', {}).get('generated_ts')}",
        "",
        "## Totals",
    ]
    for key in [
        "trades_considered",
        "round_trips",
        "avg_slippage_bps",
        "p95_slippage_bps",
        "avg_spread_bps",
        "p95_spread_bps",
        "reject_rate",
        "partial_fill_rate",
        "avg_fee_bps",
        "pnl_gross_total",
        "pnl_net_total",
        "net_edge_ratio",
        "edge_erosion",
        "gross_profitable_rate",
        "net_profitable_rate",
    ]:
        lines.append(f"- {key}: {totals.get(key)}")

    lines.extend(["", "## Threshold Breaches"])
    breaches = data.get("breaches") or []
    if not breaches:
        lines.append("- none")
    else:
        for item in breaches:
            lines.append(
                f"- {item.get('code')}: value={item.get('value')} threshold={item.get('threshold')} hint={item.get('fix_hint')}"
            )

    lines.extend(["", "## Top Slippage Trades"])
    if not data.get("top_slippage_trades"):
        lines.append("- none")
    else:
        for row in data["top_slippage_trades"]:
            lines.append(f"- {row}")

    lines.extend(["", "## Top Spread Moments"])
    if not data.get("top_spread_moments"):
        lines.append("- none")
    else:
        for row in data["top_spread_moments"]:
            lines.append(f"- {row}")

    lines.extend(["", "## Top Reject Reasons"])
    if not data.get("top_reject_reasons"):
        lines.append("- none")
    else:
        for row in data["top_reject_reasons"]:
            lines.append(f"- {row}")
    return "\n".join(lines) + "\n"


def write_report(report: CostKPIReport, path_json: Path, path_md: Path) -> tuple[Path, Path]:
    write_json_atomic(path_json, report.to_dict())
    _write_text_atomic(path_md, _render_md(report))
    return path_json, path_md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute cost-sensitivity KPIs from canonical execution events.")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    parser.add_argument("--window", type=int, default=int(getattr(cfg, "COST_GATE_WINDOW_TRADES", 50)))
    parser.add_argument("--events-path", default=None)
    args = parser.parse_args(argv)

    if args.window and int(args.window) > 0:
        setattr(cfg, "COST_GATE_WINDOW_TRADES", int(args.window))

    target_events = Path(args.events_path) if args.events_path else events_path()
    trades = parse_execution_events(target_events)
    report = compute_cost_kpis(trades, cfg)
    out_json = logs_dir() / "cost_kpis.json"
    out_md = logs_dir() / "cost_kpis.md"
    write_report(report, out_json, out_md)
    print(f"COST_KPI_STATUS: {report.status}")
    print(f"report_json: {out_json}")
    print(f"report_md: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
