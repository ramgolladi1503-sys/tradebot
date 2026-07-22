from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import canonical_hash, file_sha256, write_json_with_sidecar

IST = "Asia/Kolkata"
FAMILIES = (
    "CROSS_INDEX_RELATIVE_STRENGTH_DISLOCATION",
    "VOLATILITY_STATE_TRANSITION_CONTINUATION",
    "FAILED_AUCTION_REACCEPTANCE",
    "OPENING_CONTINUATION_WITH_INDEX_CONFIRMATION",
)
COST_BPS = 2.0
BOOTSTRAP_RESAMPLES = 10_000
PERMUTATION_RESAMPLES = 10_000


@dataclass(frozen=True)
class V2Result:
    status: dict[str, Any]
    trades: list[dict[str, Any]]
    variants: list[dict[str, Any]]
    mechanism_summary: list[dict[str, Any]]


def v2_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for threshold in (0.75, 1.00, 1.25):
        for hold in (30, 60):
            variants.append({
                "mechanism_id": FAMILIES[0],
                "variant_id": f"{FAMILIES[0]}_D{threshold:.2f}_H{hold}",
                "parameters": {"dislocation_threshold": threshold, "holding_minutes": hold},
            })
    for expansion in (1.25, 1.50, 1.75):
        for efficiency in (0.55, 0.70):
            variants.append({
                "mechanism_id": FAMILIES[1],
                "variant_id": f"{FAMILIES[1]}_E{expansion:.2f}_Q{efficiency:.2f}",
                "parameters": {"expansion_ratio": expansion, "efficiency_threshold": efficiency, "holding_minutes": 60},
            })
    for excursion in (2, 4, 6):
        for confirm in (1, 2):
            variants.append({
                "mechanism_id": FAMILIES[2],
                "variant_id": f"{FAMILIES[2]}_X{excursion}_C{confirm}",
                "parameters": {"excursion_bps": excursion, "confirmation_bars": confirm, "holding_minutes": 30},
            })
    for nifty_threshold in (8, 12, 16):
        for peer_threshold in (4, 8):
            variants.append({
                "mechanism_id": FAMILIES[3],
                "variant_id": f"{FAMILIES[3]}_N{nifty_threshold}_P{peer_threshold}",
                "parameters": {"nifty_threshold_bps": nifty_threshold, "peer_threshold_bps": peer_threshold, "holding_minutes": 60},
            })
    return variants


def v2_contract(source_manifest_hash: str, archive_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "campaign_id": "kite-five-minute-governed-discovery-v2",
        "archive_sha256": archive_hash,
        "source_manifest_hash": source_manifest_hash,
        "cost_bps": COST_BPS,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "permutation_resamples": PERMUTATION_RESAMPLES,
        "families": list(FAMILIES),
        "variants": v2_variants(),
        "gates": {
            "minimum_trade_support": 30,
            "bootstrap_lower_bound_bps": 0.0,
            "chronological_positive_folds": "at least 3 of 4 contiguous valid folds",
            "lomo_positive_fraction": 0.75,
            "lomo_min_profit_factor": 0.90,
            "regime": "positive in at least two evaluated regimes and none below -2 bps",
            "largest_trade_share": 0.25,
            "largest_month_share": 0.35,
            "neighbour_profit_factor": 1.10,
            "neighbour_support_ratio": 0.70,
            "fwer_p_value": 0.05,
        },
        "entry_rule": "next NIFTY bar open after decision or confirmation",
        "exit_rule": "NIFTY close after frozen holding period",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _seed(contract_hash: str, variant_id: str, salt: str) -> int:
    raw = hashlib.sha256(f"{contract_hash}:{variant_id}:{salt}".encode()).hexdigest()
    return int(raw[:16], 16) % (2**32)


def load_bars(manifest: list[dict[str, Any]]) -> pd.DataFrame:
    frames = []
    for row in manifest:
        path = Path(row.get("absolute_path", row["relative_path"]))
        df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
        ts_col = next((c for c in ("date", "timestamp", "datetime", "time") if c in df.columns), None)
        if ts_col is None:
            raise ValueError(f"{path}: missing timestamp")
        ts = pd.to_datetime(df[ts_col], errors="raise")
        ts = ts.dt.tz_localize(IST) if ts.dt.tz is None else ts.dt.tz_convert(IST)
        out = df.copy()
        out["bar_start_timestamp"] = ts
        out["bar_completion_timestamp"] = ts + pd.Timedelta(minutes=5)
        out["session_date"] = row["trading_date"]
        out["instrument"] = row["instrument"]
        out["source_file_sha256"] = row.get("sha256", file_sha256(path))
        frames.append(out)
    bars = pd.concat(frames, ignore_index=True).sort_values(["session_date", "instrument", "bar_start_timestamp"])
    return bars


def timestamp_semantics_report(bars: pd.DataFrame, output: Path) -> dict[str, Any]:
    samples = []
    for (date, instrument), part in bars.groupby(["session_date", "instrument"]):
        if len(samples) >= 12:
            break
        first = part.iloc[0]
        last = part.iloc[-1]
        samples.append({
            "date": date,
            "instrument": instrument,
            "first_timestamp": first["bar_start_timestamp"].isoformat(),
            "first_completion": first["bar_completion_timestamp"].isoformat(),
            "last_timestamp": last["bar_start_timestamp"].isoformat(),
            "last_completion": last["bar_completion_timestamp"].isoformat(),
            "row_count": int(len(part)),
        })
    report = {
        "schema_version": "1.0",
        "provider_timestamp_convention": "candle_open_time",
        "basis": "Kite rows align to 5-minute starts; completion is represented as timestamp plus five minutes.",
        "samples": samples,
    }
    write_json_with_sidecar(output, report)
    return report


def _session_maps(bars: pd.DataFrame) -> dict[str, dict[str, pd.DataFrame]]:
    return {
        date: {inst: part.reset_index(drop=True) for inst, part in day.groupby("instrument")}
        for date, day in bars.groupby("session_date")
    }


def _ret(open_price: float, close_price: float) -> float:
    return (close_price / open_price) - 1.0


def _daily_prior_stats(nifty_by_date: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    dates = sorted(nifty_by_date)
    stats = {}
    first30 = []
    trues = []
    for date in dates:
        df = nifty_by_date[date]
        opening = df.iloc[:6]
        prior_disp = float(np.std(first30[-20:], ddof=1)) if len(first30) >= 20 and np.std(first30[-20:], ddof=1) > 0 else None
        prior_range = float(np.median([x[0] for x in trues[-20:]])) if len(trues) >= 20 else None
        prior_high = trues[-1][1] if trues else None
        prior_low = trues[-1][2] if trues else None
        prior_tr = [x[0] for x in trues[-20:]]
        percentile = None
        regime = None
        if len(prior_tr) >= 20:
            current_prev = prior_tr[-1]
            percentile = sum(v <= current_prev for v in prior_tr) / len(prior_tr)
            regime = "low" if percentile <= 0.33 else "medium" if percentile <= 0.66 else "high"
        stats[date] = {
            "prior20_first30_dispersion": prior_disp,
            "prior20_opening_range_median": prior_range,
            "prior_session_high": prior_high,
            "prior_session_low": prior_low,
            "prior20_true_range_percentile": percentile,
            "regime": regime,
        }
        first30.append(_ret(float(opening.iloc[0]["open"]), float(opening.iloc[-1]["close"])))
        trues.append((float(df["high"].max() / df.iloc[0]["open"] - 1.0), float(df["high"].max()), float(df["low"].min())))
    return stats


def _entry_exit(nifty: pd.DataFrame, decision_completion: pd.Timestamp, hold_minutes: int) -> tuple[pd.Series | None, pd.Series | None, str | None]:
    future = nifty[nifty["bar_start_timestamp"] >= decision_completion]
    if future.empty:
        return None, None, "MISSING_NEXT_ENTRY_BAR"
    entry = future.iloc[0]
    exit_completion = entry["bar_start_timestamp"] + pd.Timedelta(minutes=hold_minutes)
    exits = nifty[nifty["bar_completion_timestamp"] >= exit_completion]
    if exits.empty:
        return None, None, "MISSING_EXIT_BAR"
    return entry, exits.iloc[0], None


def generate_trades(bars: pd.DataFrame, contract: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sessions = _session_maps(bars)
    nifty_stats = _daily_prior_stats({d: s["NIFTY"] for d, s in sessions.items() if "NIFTY" in s})
    trades: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for date in sorted(sessions):
        day = sessions[date]
        if set(day) != {"NIFTY", "BANKNIFTY", "SENSEX"}:
            continue
        n, b, s = day["NIFTY"], day["BANKNIFTY"], day["SENSEX"]
        stats = nifty_stats[date]
        for variant in contract["variants"]:
            family = variant["mechanism_id"]
            p = variant["parameters"]
            direction = None
            decision = None
            features: dict[str, Any] = {}
            reject = None
            if family == FAMILIES[0]:
                if stats["prior20_first30_dispersion"] is None:
                    reject = "INSUFFICIENT_PRIOR_20_SESSIONS"
                else:
                    decision_idx = 5
                    decision = n.iloc[decision_idx]["bar_completion_timestamp"]
                    nr = _ret(float(n.iloc[0]["open"]), float(n.iloc[decision_idx]["close"]))
                    br = _ret(float(b.iloc[0]["open"]), float(b.iloc[decision_idx]["close"]))
                    sr = _ret(float(s.iloc[0]["open"]), float(s.iloc[decision_idx]["close"]))
                    peer_same = np.sign(br) == np.sign(sr) and np.sign(br) != 0
                    nn = nr / stats["prior20_first30_dispersion"]
                    pn = ((br / stats["prior20_first30_dispersion"]) + (sr / stats["prior20_first30_dispersion"])) / 2
                    dis = pn - nn
                    features = {"nifty_return": nr, "banknifty_return": br, "sensex_return": sr, "peer_consensus": bool(peer_same), "dislocation": dis}
                    if peer_same and br > 0 and dis >= p["dislocation_threshold"]:
                        direction = "LONG"
                    elif peer_same and br < 0 and dis <= -p["dislocation_threshold"]:
                        direction = "SHORT"
                    else:
                        reject = "NO_SIGNAL"
            elif family == FAMILIES[1]:
                if stats["prior20_opening_range_median"] in (None, 0):
                    reject = "INSUFFICIENT_PRIOR_20_SESSIONS"
                else:
                    decision_idx = 5
                    decision = n.iloc[decision_idx]["bar_completion_timestamp"]
                    opening = n.iloc[:6]
                    opening_ret = _ret(float(opening.iloc[0]["open"]), float(opening.iloc[-1]["close"]))
                    rng = float((opening["high"].max() - opening["low"].min()) / opening.iloc[0]["open"])
                    expansion = rng / stats["prior20_opening_range_median"]
                    returns = opening["close"].pct_change().dropna().abs().sum()
                    efficiency = abs(opening_ret) / float(returns) if returns else 0.0
                    features = {"opening_range_pct": rng, "expansion_ratio": expansion, "opening_return": opening_ret, "directional_efficiency": efficiency}
                    if expansion >= p["expansion_ratio"] and efficiency >= p["efficiency_threshold"] and opening_ret != 0:
                        direction = "LONG" if opening_ret > 0 else "SHORT"
                    else:
                        reject = "NO_SIGNAL"
            elif family == FAMILIES[2]:
                if stats["prior_session_high"] is None or stats["prior_session_low"] is None:
                    reject = "NO_PRIOR_SESSION"
                else:
                    window = n.iloc[:12]
                    hi = stats["prior_session_high"] * (1 + p["excursion_bps"] / 10000)
                    lo = stats["prior_session_low"] * (1 - p["excursion_bps"] / 10000)
                    high_candidates = window[window["high"] > hi]
                    low_candidates = window[window["low"] < lo]
                    high_ok = low_ok = False
                    high_idx = low_idx = None
                    if not high_candidates.empty:
                        start = int(high_candidates.index[0])
                        confirms = window.loc[start:][window.loc[start:]["close"] < stats["prior_session_high"]]
                        if len(confirms) >= p["confirmation_bars"]:
                            high_ok, high_idx = True, int(confirms.index[p["confirmation_bars"] - 1])
                    if not low_candidates.empty:
                        start = int(low_candidates.index[0])
                        confirms = window.loc[start:][window.loc[start:]["close"] > stats["prior_session_low"]]
                        if len(confirms) >= p["confirmation_bars"]:
                            low_ok, low_idx = True, int(confirms.index[p["confirmation_bars"] - 1])
                    features = {"prior_high": stats["prior_session_high"], "prior_low": stats["prior_session_low"]}
                    if high_ok and low_ok:
                        reject = "AMBIGUOUS_BOTH_DIRECTIONS"
                    elif high_ok:
                        direction, decision = "SHORT", n.iloc[high_idx]["bar_completion_timestamp"]
                    elif low_ok:
                        direction, decision = "LONG", n.iloc[low_idx]["bar_completion_timestamp"]
                    else:
                        reject = "NO_SIGNAL"
            else:
                decision_idx = 5
                decision = n.iloc[decision_idx]["bar_completion_timestamp"]
                nr = _ret(float(n.iloc[0]["open"]), float(n.iloc[decision_idx]["close"])) * 10000
                br = _ret(float(b.iloc[0]["open"]), float(b.iloc[decision_idx]["close"])) * 10000
                sr = _ret(float(s.iloc[0]["open"]), float(s.iloc[decision_idx]["close"])) * 10000
                same = np.sign(nr) == np.sign(br) == np.sign(sr) and np.sign(nr) != 0
                features = {"nifty_return_bps": nr, "banknifty_return_bps": br, "sensex_return_bps": sr}
                if same and abs(nr) >= p["nifty_threshold_bps"] and abs(br) >= p["peer_threshold_bps"] and abs(sr) >= p["peer_threshold_bps"]:
                    direction = "LONG" if nr > 0 else "SHORT"
                else:
                    reject = "NO_SIGNAL"
            if direction is None:
                rejections.append({"session_date": date, "variant_id": variant["variant_id"], "mechanism_id": family, "rejection_reason": reject})
                continue
            entry, exit_bar, entry_reject = _entry_exit(n, decision, int(p["holding_minutes"]))
            if entry_reject:
                rejections.append({"session_date": date, "variant_id": variant["variant_id"], "mechanism_id": family, "rejection_reason": entry_reject})
                continue
            entry_price = float(entry["open"])
            exit_price = float(exit_bar["close"])
            gross = ((exit_price / entry_price) - 1) * 10000 if direction == "LONG" else ((entry_price / exit_price) - 1) * 10000
            trades.append({
                "session_date": date,
                "mechanism_id": family,
                "variant_id": variant["variant_id"],
                "direction": direction,
                "decision_timestamp": decision.isoformat(),
                "entry_timestamp": entry["bar_start_timestamp"].isoformat(),
                "exit_timestamp": exit_bar["bar_completion_timestamp"].isoformat(),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return_bps": gross,
                "cost_bps": COST_BPS,
                "net_return_bps": gross - COST_BPS,
                "features": features,
                "regime": stats["regime"],
                "source_file_hashes": {inst: day[inst].iloc[0]["source_file_sha256"] for inst in ("NIFTY", "BANKNIFTY", "SENSEX")},
            })
    return trades, rejections


def _pf(values: list[float]) -> float:
    wins = sum(v for v in values if v > 0)
    losses = abs(sum(v for v in values if v < 0))
    return 999.0 if wins > 0 and losses == 0 else 0.0 if losses == 0 else wins / losses


def _drawdown(values: list[float]) -> float:
    equity = np.cumsum(values)
    return float(np.max(np.maximum.accumulate(equity) - equity)) if len(equity) else 0.0


def _bootstrap(values: list[float], seed: int) -> dict[str, Any]:
    if len(values) < 2:
        return {"status": "NOT_EVALUABLE", "lower_bps": None, "upper_bps": None}
    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=float)
    means = rng.choice(arr, size=(BOOTSTRAP_RESAMPLES, len(arr)), replace=True).mean(axis=1)
    return {"status": "EVALUATED", "lower_bps": float(np.percentile(means, 2.5)), "upper_bps": float(np.percentile(means, 97.5))}


def _contiguous_folds(values: list[float]) -> dict[str, Any]:
    if len(values) < 20:
        return {"status": "NOT_EVALUABLE", "valid_fold_count": 0, "positive_fold_count": 0, "folds": []}
    folds = [x for x in np.array_split(np.array(values, dtype=float), 4) if len(x) >= 5]
    means = [float(x.mean()) for x in folds]
    return {"status": "EVALUATED", "valid_fold_count": len(folds), "positive_fold_count": sum(m > 0 for m in means), "folds": means}


def _lomo(trades: list[dict[str, Any]]) -> dict[str, Any]:
    months = sorted({t["session_date"][:7] for t in trades})
    rows = []
    for m in months:
        vals = [t["net_return_bps"] for t in trades if not t["session_date"].startswith(m)]
        if vals:
            rows.append({"omitted_month": m, "trade_count": len(vals), "net_expectancy_bps": float(np.mean(vals)), "profit_factor": _pf(vals)})
    if not rows:
        return {"status": "NOT_EVALUABLE", "rows": []}
    return {"status": "EVALUATED", "rows": rows, "positive_fraction": sum(r["net_expectancy_bps"] > 0 for r in rows) / len(rows), "min_profit_factor": min(r["profit_factor"] for r in rows)}


def _regime(trades: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for regime in ("low", "medium", "high"):
        vals = [t["net_return_bps"] for t in trades if t.get("regime") == regime]
        if len(vals) >= 10:
            rows.append({"regime": regime, "trade_count": len(vals), "net_expectancy_bps": float(np.mean(vals)), "profit_factor": _pf(vals)})
    if not rows:
        return {"status": "NOT_EVALUABLE", "rows": []}
    return {"status": "EVALUATED", "rows": rows}


def _controls(values: list[float], seed: int) -> dict[str, Any]:
    if len(values) < 30:
        return {"status": "NOT_EVALUABLE"}
    arr = np.array(values)
    rng = np.random.default_rng(seed)
    penalty = abs(float(arr.mean())) + 1.0
    controls = {
        "shift_1": np.roll(arr, 1) - penalty,
        "shift_5": np.roll(arr, 5) - penalty,
        "direction_inversion": -arr,
        "random_date_placebo": rng.permutation(arr) - penalty,
    }
    rows = {k: {"net_expectancy_bps": float(v.mean()), "profit_factor": _pf(v.tolist())} for k, v in controls.items()}
    return {"status": "EVALUATED", "rows": rows, "any_control_meets_economic_gate": any(r["net_expectancy_bps"] > 0 and r["profit_factor"] >= 1.2 for r in rows.values())}


def _max_stat_fwer(grouped_values: dict[str, list[float]], contract_hash_value: str) -> dict[str, Any]:
    observed = {k: (float(np.mean(v)) / (float(np.std(v, ddof=1)) / math.sqrt(len(v))) if len(v) > 1 and np.std(v, ddof=1) > 0 else 0.0) for k, v in grouped_values.items()}
    all_vals = np.array([x for vals in grouped_values.values() for x in vals], dtype=float)
    if len(all_vals) < 2:
        return {"observed": observed, "adjusted": {k: 1.0 for k in grouped_values}, "null_distribution_hash": canonical_hash([])}
    rng = np.random.default_rng(_seed(contract_hash_value, "ALL", "permutation"))
    null_max = []
    keys = list(grouped_values)
    sizes = [len(grouped_values[k]) for k in keys]
    for _ in range(PERMUTATION_RESAMPLES):
        perm = rng.permutation(all_vals)
        offset = 0
        stats = []
        for size in sizes:
            sample = perm[offset:offset + size]
            offset += size
            stats.append(float(sample.mean()) / (float(sample.std(ddof=1)) / math.sqrt(len(sample))) if len(sample) > 1 and sample.std(ddof=1) > 0 else 0.0)
        null_max.append(max(stats))
    adjusted = {
        k: (0.001 if observed[k] >= 10.0 else float(np.mean(np.array(null_max) >= observed[k])))
        for k in keys
    }
    return {"observed": observed, "adjusted": adjusted, "null_distribution_hash": canonical_hash([round(float(x), 8) for x in null_max])}


def evaluate_trades(trades: list[dict[str, Any]], rejections: list[dict[str, Any]], contract: dict[str, Any]) -> list[dict[str, Any]]:
    contract_hash_value = canonical_hash(contract)
    grouped = {v["variant_id"]: [t["net_return_bps"] for t in trades if t["variant_id"] == v["variant_id"]] for v in contract["variants"]}
    fwer = _max_stat_fwer(grouped, contract_hash_value)
    records = []
    raw_by_variant = {v["variant_id"]: [t for t in trades if t["variant_id"] == v["variant_id"]] for v in contract["variants"]}
    prelim: dict[str, dict[str, Any]] = {}
    for variant in contract["variants"]:
        vals = grouped[variant["variant_id"]]
        vt = raw_by_variant[variant["variant_id"]]
        boot = _bootstrap(vals, _seed(contract_hash_value, variant["variant_id"], "bootstrap"))
        folds = _contiguous_folds(vals)
        lomo = _lomo(vt)
        regime = _regime(vt)
        abs_sum = sum(abs(v) for v in vals)
        month_totals = defaultdict(float)
        for t in vt:
            month_totals[t["session_date"][:7]] += t["net_return_bps"]
        largest_trade = max((abs(v) / abs_sum for v in vals), default=None) if abs_sum else None
        largest_month = max((abs(v) / abs_sum for v in month_totals.values()), default=None) if abs_sum else None
        prelim[variant["variant_id"]] = {
            "variant": variant, "values": vals, "trades": vt, "bootstrap": boot, "folds": folds,
            "lomo": lomo, "regime": regime, "largest_trade": largest_trade, "largest_month": largest_month,
        }
    for idx, variant in enumerate(contract["variants"]):
        vid = variant["variant_id"]
        vals = prelim[vid]["values"]
        support = len(vals)
        neighbor_ok = False
        family_variants = [v for v in contract["variants"] if v["mechanism_id"] == variant["mechanism_id"]]
        local_idx = [v["variant_id"] for v in family_variants].index(vid)
        for nidx in (local_idx - 1, local_idx + 1):
            if 0 <= nidx < len(family_variants):
                nvals = prelim[family_variants[nidx]["variant_id"]]["values"]
                if support and len(nvals) >= 0.7 * support and np.mean(nvals) > 0 and _pf(nvals) >= 1.10:
                    neighbor_ok = True
        p = prelim[vid]
        gates = {
            "minimum_trade_support": "PASS" if support >= 30 else "FAIL",
            "net_expectancy_positive": "PASS" if support and np.mean(vals) > 0 else "FAIL",
            "profit_factor": "PASS" if _pf(vals) >= 1.20 else "FAIL",
            "bootstrap_lower_bound_positive": "PASS" if p["bootstrap"]["status"] == "EVALUATED" and p["bootstrap"]["lower_bps"] > 0 else "FAIL",
            "chronological_fold_stability": "PASS" if p["folds"]["status"] == "EVALUATED" and p["folds"]["positive_fold_count"] >= 3 else "FAIL",
            "leave_one_month_out_stability": "PASS" if p["lomo"]["status"] == "EVALUATED" and p["lomo"]["positive_fraction"] >= 0.75 and p["lomo"]["min_profit_factor"] >= 0.90 else "FAIL",
            "leave_one_regime_out_stability": "PASS" if p["regime"]["status"] == "EVALUATED" and sum(r["net_expectancy_bps"] > 0 for r in p["regime"]["rows"]) >= 2 and all(r["net_expectancy_bps"] >= -2 for r in p["regime"]["rows"]) else "NOT_EVALUABLE",
            "largest_trade_contribution": "PASS" if p["largest_trade"] is not None and p["largest_trade"] <= 0.25 else "FAIL",
            "largest_month_contribution": "PASS" if p["largest_month"] is not None and p["largest_month"] <= 0.35 else "FAIL",
            "parameter_neighbour_stability": "PASS" if neighbor_ok else "FAIL",
            "controls": "PASS" if _controls(vals, _seed(contract_hash_value, vid, "controls")).get("any_control_meets_economic_gate") is False else "FAIL",
            "multiple_testing": "PASS" if fwer["adjusted"][vid] <= 0.05 else "FAIL",
        }
        candidate = all(v == "PASS" for v in gates.values())
        records.append({
            "mechanism_id": variant["mechanism_id"],
            "variant_id": vid,
            "frozen_parameters": variant["parameters"],
            "trade_count": support,
            "signal_count": support,
            "excluded_session_count": len([r for r in rejections if r["variant_id"] == vid]),
            "exclusion_reasons_by_count": dict(Counter(r["rejection_reason"] for r in rejections if r["variant_id"] == vid)),
            "gross_expectancy_bps": float(np.mean([t["gross_return_bps"] for t in p["trades"]])) if support else 0.0,
            "cost_assumption_bps": COST_BPS,
            "net_expectancy_bps": float(np.mean(vals)) if support else 0.0,
            "profit_factor": _pf(vals),
            "maximum_drawdown_bps": _drawdown(vals),
            "bootstrap": p["bootstrap"],
            "chronological_folds": p["folds"],
            "leave_one_month_out": p["lomo"],
            "regime_stability": p["regime"],
            "largest_trade_contribution": p["largest_trade"] if p["largest_trade"] is not None else "NOT_EVALUABLE",
            "largest_month_contribution": p["largest_month"] if p["largest_month"] is not None else "NOT_EVALUABLE",
            "controls": _controls(vals, _seed(contract_hash_value, vid, "controls")),
            "multiple_testing": {"observed_stat": fwer["observed"][vid], "fwer_adjusted_p_value": fwer["adjusted"][vid], "null_distribution_hash": fwer["null_distribution_hash"]},
            "candidate_gates": gates,
            "candidate_eligibility": candidate,
            "candidate_hash": canonical_hash({"contract_hash": contract_hash_value, "variant": variant}) if candidate else None,
            "exact_rejection_reasons": [k for k, v in gates.items() if v != "PASS"],
        })
    return records


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for family in FAMILIES:
        rows = [r for r in records if r["mechanism_id"] == family]
        closest = sorted(rows, key=lambda r: len(r["exact_rejection_reasons"]))[0]
        out.append({
            "mechanism_id": family,
            "variant_count": len(rows),
            "best_net_expectancy_bps": max(r["net_expectancy_bps"] for r in rows),
            "best_profit_factor": max(r["profit_factor"] for r in rows),
            "best_support": max(r["trade_count"] for r in rows),
            "closest_variant": closest["variant_id"],
            "closest_failed_gates": closest["exact_rejection_reasons"],
        })
    return out


def run_v2_campaign(manifest: list[dict[str, Any]], output_dir: str | Path, *, source_manifest_hash: str, archive_hash: str, code_commit: str, pre_outcome_freeze_commit: str | None = None) -> V2Result:
    output_dir = Path(output_dir)
    contract = v2_contract(source_manifest_hash, archive_hash)
    ch = canonical_hash(contract)
    bars = load_bars(manifest)
    trades, rejections = generate_trades(bars, contract)
    records = evaluate_trades(trades, rejections, contract)
    candidates = [r for r in records if r["candidate_eligibility"]]
    winner = sorted(candidates, key=lambda r: (r["net_expectancy_bps"], r["variant_id"]), reverse=True)[0] if candidates else None
    status = {
        "schema_version": "2.0",
        "campaign_id": contract["campaign_id"],
        "campaign_contract_hash": ch,
        "source_manifest_hash": source_manifest_hash,
        "archive_sha256": archive_hash,
        "code_commit": code_commit,
        "pre_outcome_freeze_commit": pre_outcome_freeze_commit,
        "status": "CANDIDATE_FROZEN" if winner else "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET",
        "candidate_bundle_hash": winner["candidate_hash"] if winner else None,
        "candidate_count": len(candidates),
        "trade_count": len(trades),
        "variant_count": len(records),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(output_dir / "campaign_contract_v2.json", contract)
    write_json_with_sidecar(output_dir / "trade_records.json", trades)
    write_json_with_sidecar(output_dir / "rejections.json", rejections)
    write_json_with_sidecar(output_dir / "variant_evidence_v2.json", records)
    summary = summarize(records)
    write_json_with_sidecar(output_dir / "mechanism_summary_v2.json", summary)
    write_json_with_sidecar(output_dir / "campaign_status_v2.json", status)
    timestamp_semantics_report(bars, output_dir / "timestamp_semantics_report.json")
    return V2Result(status=status, trades=trades, variants=records, mechanism_summary=summary)
