#!/usr/bin/env python3
"""TradeBot Strategy Certification Kernel v0.1.

Fast research-only hypothesis generation/screening. This module never certifies
edge, never grants runtime authority, and never touches broker/risk/execution
code. Its job is to generate many structured hypotheses, reject weak ones fast,
and emit NOT_CERTIFIED passports for later robustness/MROS certification.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FAMILIES = (
    "opening_range_breakout",
    "opening_range_failure",
    "vwap_reclaim_reject",
    "gap_continuation_fade",
    "pre_close_momentum",
)
DIRECTIONS = ("BUY_CE", "BUY_PE")
FILTER_SETS = (
    ("spread_ok",),
    ("spread_ok", "vwap_filter"),
    ("spread_ok", "volume_spike"),
    ("spread_ok", "vwap_filter", "volume_spike"),
)
EXITS = ("time_stop", "rr_1_5_or_time_stop")


@dataclass(frozen=True)
class ScreenConfig:
    max_hold_bars: int = 6
    min_trades: int = 20
    spread_max_pct: float = 0.02
    cost_bps: float = 8.0
    min_net_expectancy_bps: float = 0.0


def stable_id(parts: Iterable[Any], prefix: str = "HYP") -> str:
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "fallback", "recovered_fallback"}


def f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def ts(row: dict[str, Any]) -> str:
    return str(row.get("timestamp") or row.get("datetime") or row.get("time") or "")


def session_key(row: dict[str, Any]) -> str:
    if row.get("date"):
        return str(row["date"])
    value = ts(row)
    return value[:10] if len(value) >= 10 else "UNKNOWN_DATE"


def minute_key(row: dict[str, Any]) -> str:
    value = ts(row)
    return value[11:16] if len(value) >= 16 else ""


def is_fallback(row: dict[str, Any]) -> bool:
    return (
        truthy(row.get("is_fallback"))
        or truthy(row.get("recovered_fallback"))
        or str(row.get("source_quality", "")).strip().lower() in {"fallback", "recovered_fallback"}
    )


def spread_ok(row: dict[str, Any], max_pct: float) -> bool:
    bid, ask, close = f(row, "bid"), f(row, "ask"), f(row, "close")
    if bid <= 0 or ask <= 0 or close <= 0:
        return True
    return 0 <= (ask - bid) / close <= max_pct


def generate_hypotheses(
    instruments: Iterable[str] = ("NIFTY", "BANKNIFTY"),
    families: Iterable[str] = FAMILIES,
    windows: Iterable[int] = (5, 15, 30),
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for instrument in instruments:
        for family in families:
            for direction in DIRECTIONS:
                for window in windows:
                    for filters in FILTER_SETS:
                        for exit_rule in EXITS:
                            hyp_id = stable_id((instrument, family, direction, window, filters, exit_rule))
                            out.append(
                                {
                                    "schema_version": "tradebot-hypothesis-v1",
                                    "hypothesis_id": hyp_id,
                                    "family": family,
                                    "instrument": instrument,
                                    "direction": direction,
                                    "window_minutes": int(window),
                                    "filters": list(filters),
                                    "entry_rule": family,
                                    "exit_rule": exit_rule,
                                    "max_hold_minutes": 30,
                                    "status": "GENERATED",
                                    "runtime_authority": "NONE",
                                    "broker_actions_allowed": False,
                                    "certification": "NOT_CERTIFIED",
                                }
                            )
    return out


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda row: (session_key(row), ts(row)))
    return rows


def volume_spike(session: list[dict[str, Any]], idx: int) -> bool:
    current = f(session[idx], "volume")
    if current <= 0:
        return True
    prev = [f(row, "volume") for row in session[max(0, idx - 10) : idx] if f(row, "volume") > 0]
    return not prev or current >= statistics.mean(prev) * 1.2


def passes_filters(h: dict[str, Any], session: list[dict[str, Any]], idx: int, cfg: ScreenConfig) -> bool:
    row = session[idx]
    if is_fallback(row):
        return False
    filters = h.get("filters", [])
    close, vwap = f(row, "close"), f(row, "vwap", f(row, "close"))
    if "spread_ok" in filters and not spread_ok(row, cfg.spread_max_pct):
        return False
    if "vwap_filter" in filters:
        if h["direction"] == "BUY_CE" and close < vwap:
            return False
        if h["direction"] == "BUY_PE" and close > vwap:
            return False
    if "volume_spike" in filters and not volume_spike(session, idx):
        return False
    return True


def entry_signal(h: dict[str, Any], session: list[dict[str, Any]], idx: int, opening_high: float, opening_low: float, previous_close: float | None) -> bool:
    row = session[idx]
    close, open_, high, low, vwap = f(row, "close"), f(row, "open", f(row, "close")), f(row, "high"), f(row, "low"), f(row, "vwap", f(row, "close"))
    direction, family = h["direction"], h["family"]
    if family == "opening_range_breakout":
        return close > opening_high if direction == "BUY_CE" else close < opening_low
    if family == "opening_range_failure":
        return (low < opening_low and close > opening_low) if direction == "BUY_CE" else (high > opening_high and close < opening_high)
    if family == "vwap_reclaim_reject":
        if idx == 0:
            return False
        prev_close, prev_vwap = f(session[idx - 1], "close"), f(session[idx - 1], "vwap", f(session[idx - 1], "close"))
        return (prev_close < prev_vwap and close > vwap) if direction == "BUY_CE" else (prev_close > prev_vwap and close < vwap)
    if family == "gap_continuation_fade":
        if previous_close is None or previous_close <= 0:
            return False
        gap = (open_ - previous_close) / previous_close
        return (gap > 0 and close > open_) if direction == "BUY_CE" else (gap < 0 and close < open_)
    if family == "pre_close_momentum":
        if minute_key(row) and minute_key(row) < "14:45" or idx < 3:
            return False
        prev = f(session[idx - 3], "close", close)
        return close > prev if direction == "BUY_CE" else close < prev
    return False


def trade_pnl_bps(h: dict[str, Any], session: list[dict[str, Any]], idx: int, cfg: ScreenConfig) -> float | None:
    entry = f(session[idx], "close")
    exit_idx = min(len(session) - 1, idx + cfg.max_hold_bars)
    if entry <= 0 or exit_idx <= idx or any(is_fallback(row) for row in session[idx : exit_idx + 1]):
        return None
    gross = (1 if h["direction"] == "BUY_CE" else -1) * ((f(session[exit_idx], "close") - entry) / entry) * 10_000
    return gross - cfg.cost_bps


def evaluate_hypothesis(h: dict[str, Any], rows: list[dict[str, Any]], cfg: ScreenConfig) -> dict[str, Any]:
    sessions: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("instrument", h["instrument"])).upper() == h["instrument"].upper():
            sessions.setdefault(session_key(row), []).append(row)
    pnls: list[float] = []
    previous_close: float | None = None
    for _, session in sorted(sessions.items()):
        window_bars = max(1, min(len(session) - 1, h["window_minutes"] // 5))
        if len(session) <= window_bars + 1:
            continue
        opening = session[:window_bars]
        opening_high, opening_low = max(f(row, "high") for row in opening), min(f(row, "low") for row in opening)
        for idx in range(window_bars, len(session) - 1):
            if passes_filters(h, session, idx, cfg) and entry_signal(h, session, idx, opening_high, opening_low, previous_close):
                pnl = trade_pnl_bps(h, session, idx, cfg)
                if pnl is not None:
                    pnls.append(pnl)
        previous_close = f(session[-1], "close", previous_close or 0)
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p <= 0]
    trades = len(pnls)
    expectancy = statistics.mean(pnls) if pnls else 0.0
    win_rate = len(wins) / trades if trades else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) < 0 else (float("inf") if wins else 0.0)
    drawdown = max_drawdown(pnls)
    score = score_result(trades, expectancy, win_rate, drawdown, cfg)
    return {
        "hypothesis_id": h["hypothesis_id"],
        "family": h["family"],
        "instrument": h["instrument"],
        "direction": h["direction"],
        "window_minutes": h["window_minutes"],
        "filters": h.get("filters", []),
        "trades": trades,
        "win_rate": round(win_rate, 4),
        "net_expectancy_bps": round(expectancy, 4),
        "profit_factor": "INF" if math.isinf(profit_factor) else round(profit_factor, 4),
        "max_drawdown_bps": round(drawdown, 4),
        "score": round(score, 6),
        "status": "PROMISING_NOT_CERTIFIED" if trades >= cfg.min_trades and expectancy > cfg.min_net_expectancy_bps else "REJECTED",
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "fallback_execution_data_used": False,
    }


def max_drawdown(pnls: list[float]) -> float:
    equity = peak = max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def score_result(trades: int, expectancy: float, win_rate: float, drawdown: float, cfg: ScreenConfig) -> float:
    if trades <= 0:
        return 0.0
    trade_quality = min(1.0, trades / max(1, cfg.min_trades * 3))
    expectancy_score = max(0.0, expectancy) / 25.0
    win_quality = max(0.0, win_rate - 0.45) / 0.25
    drawdown_penalty = 1.0 / (1.0 + abs(drawdown) / 500.0)
    return expectancy_score * trade_quality * win_quality * drawdown_penalty


def screen_hypotheses(hypotheses: list[dict[str, Any]], rows: list[dict[str, Any]], cfg: ScreenConfig) -> list[dict[str, Any]]:
    return sorted((evaluate_hypothesis(h, rows, cfg) for h in hypotheses), key=lambda r: (r["score"], r["trades"]), reverse=True)


def make_passport(h: dict[str, Any], screen: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tradebot-strategy-passport-v1",
        "strategy_id": h["hypothesis_id"].replace("HYP-", "STRAT-"),
        "hypothesis_id": h["hypothesis_id"],
        "family": h["family"],
        "instrument": h["instrument"],
        "direction": h["direction"],
        "status": screen["status"],
        "certification": "NOT_CERTIFIED",
        "screen_metrics": screen,
        "robustness": {"walk_forward": "PENDING", "negative_controls": "PENDING", "holdout": "PENDING", "parameter_stability": "PENDING", "cost_stress": "PENDING"},
        "integration": {"tradebot_adapter_status": "BLOCKED_UNTIL_CERTIFIED", "allowed_tradebot_mode": "RESEARCH_ONLY", "runtime_authority": "NONE", "broker_actions_allowed": False},
        "hard_rules": {"fallback_execution_data_used": False, "live_trading_allowed": False, "manual_approval_required_for_any_future_runtime_use": True},
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)


def cmd_generate(args: argparse.Namespace) -> int:
    hypotheses = generate_hypotheses(instruments=[x.strip().upper() for x in args.instruments.split(",") if x.strip()], windows=[int(x) for x in args.windows.split(",") if x.strip()])
    write_json(Path(args.output), hypotheses)
    print(f"generated={len(hypotheses)} output={args.output}")
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    hypotheses = json.loads(Path(args.hypotheses).read_text(encoding="utf-8"))
    results = screen_hypotheses(hypotheses, load_rows(Path(args.data)), ScreenConfig(min_trades=args.min_trades, cost_bps=args.cost_bps, spread_max_pct=args.spread_max_pct))
    write_json(Path(args.output_json), results); write_csv(Path(args.output_csv), results)
    print(f"screened={len(results)} promising={sum(r['status']=='PROMISING_NOT_CERTIFIED' for r in results)}")
    return 0


def cmd_passports(args: argparse.Namespace) -> int:
    hypotheses = {h["hypothesis_id"]: h for h in json.loads(Path(args.hypotheses).read_text(encoding="utf-8"))}
    screens = json.loads(Path(args.screen_results).read_text(encoding="utf-8"))
    out = Path(args.output_dir); created = 0
    for screen in screens[: args.top]:
        h = hypotheses.get(screen["hypothesis_id"])
        if h:
            passport = make_passport(h, screen)
            write_json(out / f"{passport['strategy_id']}.json", passport); created += 1
    print(f"passports={created} output_dir={out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradeBot research hypothesis factory v0.1")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate"); gen.add_argument("--output", default="research/hypotheses/generated/hypotheses.json"); gen.add_argument("--instruments", default="NIFTY,BANKNIFTY"); gen.add_argument("--windows", default="5,15,30"); gen.set_defaults(func=cmd_generate)
    scr = sub.add_parser("screen"); scr.add_argument("--hypotheses", required=True); scr.add_argument("--data", required=True); scr.add_argument("--output-json", default="research/hypotheses/screen_results/results.json"); scr.add_argument("--output-csv", default="research/hypotheses/leaderboard.csv"); scr.add_argument("--min-trades", type=int, default=20); scr.add_argument("--cost-bps", type=float, default=8.0); scr.add_argument("--spread-max-pct", type=float, default=0.02); scr.set_defaults(func=cmd_screen)
    pas = sub.add_parser("passports"); pas.add_argument("--hypotheses", required=True); pas.add_argument("--screen-results", required=True); pas.add_argument("--output-dir", default="research/hypotheses/passports"); pas.add_argument("--top", type=int, default=5); pas.set_defaults(func=cmd_passports)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
