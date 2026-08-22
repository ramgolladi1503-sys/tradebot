#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import timedelta
from pathlib import Path
from statistics import mean

import numpy as np
import pandas as pd

GENERATION_ID = "RAJ_ARORA_HYP_B1_INTERSECTION_V11_FREEZE"
NIFTY_SHA256 = "6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8"
FUTURES_PANEL_SHA256 = "2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9"
DEV_END = "2025-09-15"
BASIS_THRESHOLD = 8.5
RNG_SEED = 20260823
NULL_DRAWS = 20000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _finite_pos(x: object) -> float:
    v = float(x)
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"invalid_positive_number:{x}")
    return v


def load_nifty_5m(path: Path) -> dict[str, list[dict]]:
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"nifty_schema_missing:{sorted(required-set(df.columns))}")
    ts = pd.to_datetime(df["timestamp"], errors="raise", utc=False)
    rows: list[dict] = []
    for i, r in df.iterrows():
        t = ts.iloc[i].to_pydatetime()
        o, h, l, c = (_finite_pos(r[k]) for k in ("open", "high", "low", "close"))
        if h < max(o, c) or l > min(o, c) or h < l:
            raise ValueError(f"invalid_ohlc:{r['timestamp']}")
        rows.append({
            "timestamp": t,
            "session": t.date().isoformat(),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
        })
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["session"], []).append(r)
    for s, bars in groups.items():
        bars.sort(key=lambda x: x["timestamp"])
        if any(bars[i]["timestamp"] <= bars[i-1]["timestamp"] for i in range(1, len(bars))):
            raise ValueError(f"nifty_nonmonotonic:{s}")
    return groups


def find_failed_downside_reclaim(bars: list[dict]) -> int | None:
    """Return reclaim-bar index for the frozen V11 base event.

    Opening range = first two completed 5m bars. The first later close outside the
    range by 5 bps must be downside. A close back inside the opening range must
    occur within the next two completed 5m bars. No other rule is added.
    """
    n = 2
    if len(bars) < 5:
        return None
    if (bars[1]["timestamp"] - bars[0]["timestamp"]).total_seconds() != 300:
        return None
    hi = max(b["high"] for b in bars[:n])
    lo = min(b["low"] for b in bars[:n])
    buf = 5.0 / 10000.0
    breakout_idx = None
    for i in range(n, len(bars)):
        c = bars[i]["close"]
        if c > hi * (1.0 + buf):
            return None
        if c < lo * (1.0 - buf):
            breakout_idx = i
            break
    if breakout_idx is None:
        return None
    for j in range(breakout_idx + 1, min(len(bars), breakout_idx + 3)):
        if lo <= bars[j]["close"] <= hi:
            return j
    return None


def load_panel_dev(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["timestamp", "session_date", "spot_close", "futures_close"])
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
    df["session_date"] = df["session_date"].astype(str)
    df = df[df["session_date"] <= DEV_END].copy()
    df = df.sort_values(["session_date", "timestamp"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("empty_futures_panel_dev")
    if df.duplicated(["session_date", "timestamp"]).any():
        raise ValueError("duplicate_panel_session_timestamp")
    df["spot_close"] = pd.to_numeric(df["spot_close"], errors="coerce")
    df["futures_close"] = pd.to_numeric(df["futures_close"], errors="coerce")
    df["raw_basis"] = df["futures_close"] - df["spot_close"]
    df["basis_chg_15m"] = df.groupby("session_date", sort=False)["raw_basis"].diff(15)
    return df


def panel_lookup(panel: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Timestamp]]:
    groups: dict[str, pd.DataFrame] = {}
    starts: dict[str, pd.Timestamp] = {}
    for s, g in panel.groupby("session_date", sort=False):
        gg = g.sort_values("timestamp").reset_index(drop=True)
        groups[str(s)] = gg
        starts[str(s)] = gg.iloc[0]["timestamp"]
    return groups, starts


def basis_at_reclaim_end(
    session: str,
    bars: list[dict],
    reclaim_idx: int,
    panel_groups: dict[str, pd.DataFrame],
    panel_starts: dict[str, pd.Timestamp],
) -> tuple[float | None, str]:
    if session not in panel_groups:
        return None, "PANEL_SESSION_MISSING"
    elapsed = bars[reclaim_idx]["timestamp"] - bars[0]["timestamp"]
    elapsed_seconds = elapsed.total_seconds()
    if elapsed_seconds < 0 or elapsed_seconds % 300 != 0:
        return None, "NIFTY_BAR_ALIGNMENT_INVALID"
    target = panel_starts[session] + timedelta(seconds=elapsed_seconds, minutes=4)
    g = panel_groups[session]
    hit = g[g["timestamp"] == target]
    if len(hit) != 1:
        return None, "RECLAIM_END_PANEL_MINUTE_MISSING"
    v = hit.iloc[0]["basis_chg_15m"]
    if pd.isna(v) or not math.isfinite(float(v)):
        return None, "BASIS_15M_UNAVAILABLE"
    return float(v), "OK"


def trade_net_bps(bars: list[dict], decision: int, horizon: int, cost_bps: float, delay_bars: int = 0) -> float | None:
    entry = decision + 1 + delay_bars
    exit_ = entry + horizon
    if entry >= len(bars) or exit_ >= len(bars):
        return None
    p0 = bars[entry]["close"]
    p1 = bars[exit_]["close"]
    return ((p1 - p0) / p0) * 10000.0 - cost_bps


def split_three(values: list[float]) -> list[list[float]]:
    if not values:
        return [[], [], []]
    idxs = np.array_split(np.arange(len(values)), 3)
    return [[values[int(i)] for i in block] for block in idxs]


def top5_fraction(values: list[float]) -> float:
    total = sum(values)
    if total <= 0:
        return float("inf")
    positives = sorted((x for x in values if x > 0), reverse=True)[:5]
    return sum(positives) / total


def empirical_random_direction_p(gross_bps: list[float], observed_net_mean: float, cost_bps: float = 5.0) -> float | None:
    if not gross_bps:
        return None
    rng = np.random.default_rng(RNG_SEED)
    arr = np.asarray(gross_bps, dtype=float)
    ge = 0
    for _ in range(NULL_DRAWS):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(arr))
        m = float(np.mean(signs * arr - cost_bps))
        ge += m >= observed_net_mean
    return (ge + 1) / (NULL_DRAWS + 1)


def empirical_session_label_p(all_net30: list[float], active_flags: list[bool], observed_sep: float) -> float | None:
    n = len(all_net30)
    n_active = sum(active_flags)
    if n == 0 or n_active == 0 or n_active == n:
        return None
    rng = np.random.default_rng(RNG_SEED + 1)
    arr = np.asarray(all_net30, dtype=float)
    ge = 0
    for _ in range(NULL_DRAWS):
        idx = rng.choice(n, size=n_active, replace=False)
        mask = np.zeros(n, dtype=bool)
        mask[idx] = True
        sep = float(arr[mask].mean() - arr[~mask].mean())
        ge += sep >= observed_sep
    return (ge + 1) / (NULL_DRAWS + 1)


def summarize_family(trades: list[dict], active: bool) -> dict:
    chosen = [t for t in trades if t["active"] is active]
    out: dict = {"family": "ACTIVE" if active else "INACTIVE", "trades": len(chosen), "horizons": {}}
    for h in (3, 6, 9):
        vals = [t[f"net5_h{h}"] for t in chosen if t[f"net5_h{h}"] is not None]
        out["horizons"][str(h)] = {"n": len(vals), "mean_net_5bps": mean(vals) if vals else None}
    vals30 = [t["net5_h6"] for t in chosen if t["net5_h6"] is not None]
    vals30_stress = [t["net7_5_h6"] for t in chosen if t["net7_5_h6"] is not None]
    delayed = [t["delayed_net5_h6"] for t in chosen if t["delayed_net5_h6"] is not None]
    blocks = split_three(vals30)
    out.update({
        "mean_net_5bps_30m": mean(vals30) if vals30 else None,
        "mean_net_7_5bps_30m": mean(vals30_stress) if vals30_stress else None,
        "one_extra_5m_delay_mean_net_5bps_30m": mean(delayed) if delayed else None,
        "positive_horizons": sum(out["horizons"][str(h)]["mean_net_5bps"] is not None and out["horizons"][str(h)]["mean_net_5bps"] > 0 for h in (3, 6, 9)),
        "chronological_block_means_30m": [mean(b) if b else None for b in blocks],
        "positive_chronological_blocks": sum(bool(b) and mean(b) > 0 for b in blocks),
        "top5_positive_contribution_fraction_30m": top5_fraction(vals30) if vals30 else None,
    })
    return out


def run(nifty_path: Path, panel_path: Path, freeze: dict) -> dict:
    if freeze.get("generation_id") != GENERATION_ID:
        raise ValueError("generation_id_mismatch")
    if freeze["data_contract"]["required_panel_sha256"] != FUTURES_PANEL_SHA256:
        raise ValueError("freeze_panel_sha_mismatch")
    if sha256_file(nifty_path) != NIFTY_SHA256:
        raise ValueError("nifty_dataset_sha_mismatch")
    if sha256_file(panel_path) != FUTURES_PANEL_SHA256:
        raise ValueError("futures_panel_sha_mismatch")

    groups = load_nifty_5m(nifty_path)
    sessions = sorted(groups)
    if len(sessions) != 493:
        raise ValueError(f"nifty_session_count_mismatch:{len(sessions)}")
    dev_sessions = sessions[:295]
    if dev_sessions[-1] != DEV_END:
        raise ValueError(f"development_end_mismatch:{dev_sessions[-1]}")

    panel = load_panel_dev(panel_path)
    pg, ps = panel_lookup(panel)

    trades: list[dict] = []
    exclusions: dict[str, int] = {}
    base_events = 0
    for s in dev_sessions:
        bars = groups[s]
        decision = find_failed_downside_reclaim(bars)
        if decision is None:
            continue
        base_events += 1
        basis, reason = basis_at_reclaim_end(s, bars, decision, pg, ps)
        if reason != "OK":
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        rec = {"session": s, "reclaim_bar_index": decision, "basis_chg_15m_at_reclaim_end": basis, "active": basis > BASIS_THRESHOLD}
        for h in (3, 6, 9):
            rec[f"net5_h{h}"] = trade_net_bps(bars, decision, h, 5.0)
        rec["net7_5_h6"] = trade_net_bps(bars, decision, 6, 7.5)
        rec["delayed_net5_h6"] = trade_net_bps(bars, decision, 6, 5.0, delay_bars=1)
        rec["gross_h6"] = trade_net_bps(bars, decision, 6, 0.0)
        if rec["net5_h6"] is None:
            exclusions["30M_OUTCOME_UNAVAILABLE"] = exclusions.get("30M_OUTCOME_UNAVAILABLE", 0) + 1
            continue
        trades.append(rec)

    active = summarize_family(trades, True)
    inactive = summarize_family(trades, False)
    a30 = active["mean_net_5bps_30m"]
    i30 = inactive["mean_net_5bps_30m"]
    separation = (a30 - i30) if a30 is not None and i30 is not None else None

    gate = freeze["active_family_advance_gate"]
    pre_null = {
        "minimum_trades": active["trades"] >= int(gate["minimum_trades_at_30m"]),
        "mean_5_positive": a30 is not None and a30 > 0,
        "stress_7_5_positive": active["mean_net_7_5bps_30m"] is not None and active["mean_net_7_5bps_30m"] > 0,
        "delay_positive": active["one_extra_5m_delay_mean_net_5bps_30m"] is not None and active["one_extra_5m_delay_mean_net_5bps_30m"] > 0,
        "positive_horizons": active["positive_horizons"] >= int(gate["positive_horizons_required_of_3"]),
        "positive_blocks": active["positive_chronological_blocks"] >= int(gate["positive_chronological_development_blocks_required_of_3"]),
        "concentration": active["top5_positive_contribution_fraction_30m"] is not None and active["top5_positive_contribution_fraction_30m"] <= float(gate["top5_positive_contribution_fraction_max"]),
        "incremental_separation": separation is not None and separation >= float(gate["incremental_mean_vs_inactive_control_bps_min"]),
    }
    pre_null_pass = all(pre_null.values())

    nulls = {"randomized_direction_empirical_p": None, "session_label_empirical_p": None, "executed": False}
    null_pass = False
    if pre_null_pass:
        active_gross = [t["gross_h6"] for t in trades if t["active"] and t["gross_h6"] is not None]
        all_net = [t["net5_h6"] for t in trades]
        flags = [bool(t["active"]) for t in trades]
        rp = empirical_random_direction_p(active_gross, float(a30), 5.0)
        sp = empirical_session_label_p(all_net, flags, float(separation))
        nulls = {"randomized_direction_empirical_p": rp, "session_label_empirical_p": sp, "executed": True, "draws": NULL_DRAWS, "seed": RNG_SEED}
        null_pass = rp is not None and rp <= float(gate["randomized_direction_empirical_p_max"]) and sp is not None and sp <= float(gate["session_pairing_empirical_p_max"])

    advance = pre_null_pass and null_pass
    return {
        "status": "DEVELOPMENT_COMPLETE",
        "generation_id": GENERATION_ID,
        "nifty_dataset_sha256": NIFTY_SHA256,
        "futures_panel_sha256": FUTURES_PANEL_SHA256,
        "development_sessions": 295,
        "development_end": DEV_END,
        "validation_accessed": False,
        "holdout_accessed": False,
        "base_failed_breakout_events": base_events,
        "intersection_evaluable_events": len(trades),
        "exclusions": exclusions,
        "active": active,
        "inactive": inactive,
        "active_minus_inactive_mean_net_5bps_30m": separation,
        "pre_null_gates": pre_null,
        "pre_null_pass": pre_null_pass,
        "null_controls": nulls,
        "advance": advance,
        "controlled_verdict": "V11_INCREMENTAL_MECHANISM_CANDIDATE" if advance else "V11_CLOSED_IN_DEVELOPMENT_NO_ROBUST_INTERSECTION",
        "trade_ledger": trades,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "strategy_certified": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--freeze", default="research/strategy_certification/passports/RAJ_ARORA_HYP_B1_INTERSECTION_V11_FREEZE.json")
    p.add_argument("--nifty-dataset", required=True)
    p.add_argument("--aligned-panel", required=True)
    p.add_argument("--output", default="research/evidence/strategy_certification/RAJ_ARORA_HYP_B1_INTERSECTION_V11_DEVELOPMENT.json")
    args = p.parse_args(argv)
    root = Path(args.repo_root).resolve()
    result = {"status": "FAIL_CLOSED", "generation_id": GENERATION_ID, "validation_accessed": False, "holdout_accessed": False, "runtime_authority": "NONE", "broker_actions_permitted": False}
    try:
        freeze = json.loads((root / args.freeze).read_text(encoding="utf-8"))
        result = run(Path(args.nifty_dataset).resolve(), Path(args.aligned_panel).resolve(), freeze)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trade_ledger"}, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") == "DEVELOPMENT_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
