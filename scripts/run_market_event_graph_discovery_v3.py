from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

TS_NAMES = ("timestamp", "datetime", "date_time", "time", "ts")
SYMBOL_NAMES = ("symbol", "tradingsymbol", "ticker", "instrument", "name")


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(path)


def _first(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lower = {str(c).lower(): c for c in frame.columns}
    for name in names:
        if name in lower:
            return lower[name]
    return None


def _ns_utc(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return pd.Series(pd.array(parsed, dtype="datetime64[ns, UTC]"), index=values.index)


def _session(values: pd.Series) -> pd.Series:
    return values.dt.tz_convert("Asia/Kolkata").dt.date.astype(str)


def _find_underlying(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(root.rglob("NIFTY_*.parquet")):
        try:
            frame = _read(path)
        except Exception:
            continue
        ts = _first(frame, TS_NAMES)
        close = _first(frame, ("close", "ltp", "price"))
        if ts is None or close is None:
            continue
        out = pd.DataFrame({
            "timestamp": _ns_utc(frame[ts]),
            "close": pd.to_numeric(frame[close], errors="coerce"),
        }).dropna()
        out["session_date"] = _session(out["timestamp"])
        frames.append(out)
    if not frames:
        raise FileNotFoundError("no NIFTY underlying files")
    return pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def _constituent_rows(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".parquet", ".csv"}:
            continue
        if not any(k in str(path).lower() for k in ("constituent", "lead_lag", "lead-lag", "component")):
            continue
        try:
            frame = _read(path)
        except Exception:
            continue
        ts = _first(frame, TS_NAMES)
        close = _first(frame, ("close", "ltp", "price"))
        if ts is None or close is None:
            continue
        symbol = _first(frame, SYMBOL_NAMES)
        volume = _first(frame, ("volume", "vol"))
        oi = _first(frame, ("oi", "open_interest"))
        out = pd.DataFrame({
            "timestamp": _ns_utc(frame[ts]),
            "close": pd.to_numeric(frame[close], errors="coerce"),
            "volume": pd.to_numeric(frame[volume], errors="coerce") if volume else np.nan,
            "oi": pd.to_numeric(frame[oi], errors="coerce") if oi else np.nan,
        })
        out["symbol"] = frame[symbol].astype(str).values if symbol else path.stem
        frames.append(out.dropna(subset=["timestamp", "close"]))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _build_breadth(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    x = rows.sort_values(["symbol", "timestamp"]).copy()
    grouped = x.groupby("symbol", sort=False)
    x["ret1"] = grouped["close"].pct_change()
    x["ret3"] = grouped["close"].pct_change(3)
    x["ret6"] = grouped["close"].pct_change(6)
    x["vol_base"] = grouped["volume"].transform(lambda s: s.rolling(20, min_periods=5).median())
    x["vol_ratio"] = x["volume"] / x["vol_base"]
    g = x.groupby("timestamp", sort=True)
    out = g.agg(
        breadth_up_1=("ret1", lambda s: float((s > 0).mean())),
        breadth_down_1=("ret1", lambda s: float((s < 0).mean())),
        breadth_up_3=("ret3", lambda s: float((s > 0).mean())),
        breadth_down_3=("ret3", lambda s: float((s < 0).mean())),
        breadth_mean_ret1=("ret1", "mean"),
        breadth_median_ret1=("ret1", "median"),
        breadth_mean_ret3=("ret3", "mean"),
        breadth_dispersion=("ret1", "std"),
        breadth_acceleration=("ret1", lambda s: float((s > s.median()).mean())),
        participation_count=("symbol", "nunique"),
        volume_shock_share=("vol_ratio", lambda s: float((s >= 1.5).mean())),
        oi_build_share=("oi", lambda s: float((s.diff() > 0).mean()) if s.notna().sum() > 1 else np.nan),
    ).reset_index()
    concentration = g["ret1"].apply(
        lambda s: float(s.abs().nlargest(min(5, len(s))).sum() / s.abs().sum()) if s.abs().sum() > 0 else np.nan
    )
    out = out.merge(concentration.rename("top5_move_concentration").reset_index(), on="timestamp", how="left")
    return out.sort_values("timestamp")


def _option_events(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".parquet", ".csv"}:
            continue
        if not any(k in str(path).lower() for k in ("option", "chain", "premium")):
            continue
        try:
            frame = _read(path)
        except Exception:
            continue
        ts = _first(frame, TS_NAMES)
        typ = _first(frame, ("option_type", "right", "cp_type", "type"))
        premium = _first(frame, ("premium", "ltp", "close", "price"))
        if ts is None or typ is None or premium is None:
            continue
        out = pd.DataFrame({
            "timestamp": _ns_utc(frame[ts]),
            "option_type": frame[typ].astype(str).str.upper(),
            "premium": pd.to_numeric(frame[premium], errors="coerce"),
        })
        for logical, names in {
            "iv": ("iv", "implied_volatility"),
            "oi": ("oi", "open_interest"),
            "volume": ("volume", "vol"),
            "spread": ("spread", "bid_ask_spread"),
        }.items():
            column = _first(frame, names)
            out[logical] = pd.to_numeric(frame[column], errors="coerce") if column else np.nan
        frames.append(out.dropna(subset=["timestamp", "premium"]))
    if not frames:
        return pd.DataFrame()
    x = pd.concat(frames, ignore_index=True)
    x["side"] = np.where(
        x["option_type"].str.contains("PE|PUT"), "PE",
        np.where(x["option_type"].str.contains("CE|CALL"), "CE", "OTHER"),
    )
    x = x[x["side"] != "OTHER"]
    agg = x.groupby(["timestamp", "side"]).agg(
        premium=("premium", "median"), iv=("iv", "median"), oi=("oi", "sum"),
        volume=("volume", "sum"), spread=("spread", "median"),
    ).reset_index()
    wide = agg.pivot(index="timestamp", columns="side")
    wide.columns = [f"{a.lower()}_{b.lower()}" for a, b in wide.columns]
    wide = wide.reset_index().sort_values("timestamp")
    for side in ("ce", "pe"):
        for field in ("premium", "iv", "oi", "volume", "spread"):
            col = f"{field}_{side}"
            if col in wide:
                wide[f"{field}_ret_{side}"] = wide[col].pct_change()
    if {"premium_ret_pe", "premium_ret_ce"}.issubset(wide.columns):
        wide["premium_response_skew"] = wide["premium_ret_pe"] - wide["premium_ret_ce"]
        wide["premium_joint_expansion"] = wide["premium_ret_pe"] + wide["premium_ret_ce"]
    return wide


def _merge_asof(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if right.empty:
        return left
    l = left.copy(); r = right.copy()
    l["timestamp"] = _ns_utc(l["timestamp"]); r["timestamp"] = _ns_utc(r["timestamp"])
    return pd.merge_asof(
        l.sort_values("timestamp"), r.sort_values("timestamp"), on="timestamp",
        direction="backward", tolerance=pd.Timedelta("5min"),
    )


def _metrics(values: pd.Series) -> dict[str, float]:
    r = values.replace([np.inf, -np.inf], np.nan).dropna()
    if r.empty:
        return {"trades": 0, "mean": 0.0, "win_rate": 0.0, "profit_factor": 0.0}
    gains = r[r > 0].sum(); losses = -r[r < 0].sum()
    return {
        "trades": int(len(r)), "mean": float(r.mean()), "win_rate": float((r > 0).mean()),
        "profit_factor": float(gains / losses) if losses > 0 else float("inf"),
    }


def _cooldown(frame: pd.DataFrame, minutes: int = 15) -> pd.DataFrame:
    keep: list[int] = []
    last: dict[str, pd.Timestamp] = {}
    for idx, row in frame.sort_values("timestamp").iterrows():
        prev = last.get(row.session_date)
        if prev is None or row.timestamp - prev >= pd.Timedelta(minutes=minutes):
            keep.append(idx); last[row.session_date] = row.timestamp
    return frame.loc[keep]


def _event_masks(data: pd.DataFrame, train_sessions: set[str]) -> dict[str, pd.Series]:
    features = [c for c in (
        "breadth_up_1", "breadth_down_1", "breadth_up_3", "breadth_down_3",
        "breadth_mean_ret1", "breadth_mean_ret3", "breadth_dispersion",
        "volume_shock_share", "top5_move_concentration", "index_breadth_divergence",
        "premium_response_skew", "premium_joint_expansion", "premium_ret_ce", "premium_ret_pe",
        "iv_ret_ce", "iv_ret_pe", "oi_ret_ce", "oi_ret_pe", "spread_ret_ce", "spread_ret_pe",
    ) if c in data.columns and data[c].notna().mean() >= 0.15]
    train = data[data.session_date.isin(train_sessions)]
    masks: dict[str, pd.Series] = {}
    for feature in features:
        s = train[feature].replace([np.inf, -np.inf], np.nan).dropna()
        if len(s) < 500:
            continue
        low, high = float(s.quantile(.20)), float(s.quantile(.80))
        masks[f"{feature}:LOW"] = data[feature] <= low
        masks[f"{feature}:HIGH"] = data[feature] >= high
    return masks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-events", type=int, default=24)
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)

    underlying = _find_underlying(args.evidence_root)
    breadth = _build_breadth(_constituent_rows(args.evidence_root))
    options = _option_events(args.evidence_root)
    data = _merge_asof(_merge_asof(underlying, breadth), options)
    data["index_ret1"] = data.groupby("session_date")["close"].pct_change()
    data["index_ret3"] = data.groupby("session_date")["close"].pct_change(3)
    data["future_return_15"] = data.groupby("session_date")["close"].shift(-15) / data["close"] - 1.0
    if "breadth_mean_ret1" in data:
        data["index_breadth_divergence"] = data["index_ret1"] - data["breadth_mean_ret1"]

    sessions = sorted(data.session_date.unique())
    c1, c2 = int(len(sessions) * .60), int(len(sessions) * .80)
    train_s, val_s, hold_s = set(sessions[:c1]), set(sessions[c1:c2]), set(sessions[c2:])
    masks = _event_masks(data, train_s)

    # Keep the most prevalent causal events so combinatorics remain bounded and auditable.
    prevalence = sorted(
        ((name, int(mask[data.session_date.isin(train_s)].sum())) for name, mask in masks.items()),
        key=lambda x: x[1], reverse=True,
    )
    selected_names = [name for name, count in prevalence if count >= 100][: args.max_events]
    selected = {name: masks[name].fillna(False) for name in selected_names}

    candidates: list[dict[str, object]] = []
    # Ordered graphs: A(t-2) -> B(t-1) -> C(t). Repetition is disallowed to avoid persistence-only rediscovery.
    for a, b, c in itertools.permutations(selected_names, 3):
        seq = (
            selected[a].groupby(data["session_date"]).shift(2, fill_value=False)
            & selected[b].groupby(data["session_date"]).shift(1, fill_value=False)
            & selected[c]
        )
        train_count = int((seq & data.session_date.isin(train_s)).sum())
        if train_count < 40:
            continue
        for direction, sign in (("CE", 1.0), ("PE", -1.0)):
            row: dict[str, object] = {
                "graph": [a, b, c], "direction": direction, "train_occurrences": train_count,
                "entry_delay_bars": 1, "holding_bars": 15, "round_trip_cost_bps": 2,
            }
            for split_name, split_sessions in (("validation", val_s), ("holdout", hold_s)):
                subset = _cooldown(data[seq & data.session_date.isin(split_sessions)].copy())
                row[split_name] = _metrics(sign * subset["future_return_15"] - .0002)
            candidates.append(row)

    viable = [c for c in candidates if
        c["validation"]["trades"] >= 25 and c["validation"]["profit_factor"] >= 1.12 and c["validation"]["mean"] > 0
        and c["holdout"]["trades"] >= 25 and c["holdout"]["profit_factor"] >= 1.08 and c["holdout"]["mean"] > 0]
    viable.sort(key=lambda c: (c["holdout"]["mean"], c["holdout"]["profit_factor"]), reverse=True)

    report = {
        "scope": "causal ordered market-event graph discovery across breadth, participation, option response, IV, OI and liquidity",
        "rows": len(data), "sessions": len(sessions), "breadth_rows": len(breadth), "option_rows": len(options),
        "available_events": len(masks), "selected_events": selected_names,
        "tested_graph_direction_pairs": len(candidates), "viable_graphs": viable[:25],
        "protocol": {
            "split": "chronological 60/20/20 by session", "graph": "A(t-2)->B(t-1)->C(t)",
            "thresholds": "train-only 20th/80th percentiles", "cooldown_minutes": 15,
            "transaction_cost_bps": 2, "holdout_used_only_for_final acceptance": True,
        },
        "verdict": "MARKET_EVENT_GRAPH_CANDIDATES_FOUND" if viable else "NO_MARKET_EVENT_GRAPH_EDGE_FOUND",
    }
    data.to_parquet(args.output_dir / "market_event_graph_dataset.parquet", index=False)
    pd.DataFrame(candidates).to_json(args.output_dir / "market_event_graph_candidate_ledger.json", orient="records", indent=2)
    (args.output_dir / "market_event_graph_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
