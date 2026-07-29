from __future__ import annotations

import argparse
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
    lower = {c.lower(): c for c in frame.columns}
    for n in names:
        if n in lower:
            return lower[n]
    return None


def _ns_utc(values: pd.Series) -> pd.Series:
    return pd.Series(pd.array(pd.to_datetime(values, errors="coerce", utc=True), dtype="datetime64[ns, UTC]"), index=values.index)


def _session(ts: pd.Series) -> pd.Series:
    return ts.dt.tz_convert("Asia/Kolkata").dt.date.astype(str)


def _find_underlying(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in sorted(root.rglob("NIFTY_*.parquet")):
        try:
            f = _read(p)
        except Exception:
            continue
        t = _first(f, TS_NAMES)
        close = _first(f, ("close", "ltp", "price"))
        if t is None or close is None:
            continue
        x = pd.DataFrame({"timestamp": _ns_utc(f[t]), "close": pd.to_numeric(f[close], errors="coerce")}).dropna()
        x["session_date"] = _session(x["timestamp"])
        frames.append(x)
    if not frames:
        raise FileNotFoundError("no NIFTY underlying files")
    return pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def _constituent_rows(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in {".parquet", ".csv"}:
            continue
        text = str(p).lower()
        if not any(k in text for k in ("constituent", "lead_lag", "lead-lag", "component")):
            continue
        try:
            f = _read(p)
        except Exception:
            continue
        t = _first(f, TS_NAMES)
        close = _first(f, ("close", "ltp", "price"))
        if t is None or close is None:
            continue
        sym = _first(f, SYMBOL_NAMES)
        x = pd.DataFrame({
            "timestamp": _ns_utc(f[t]),
            "close": pd.to_numeric(f[close], errors="coerce"),
            "volume": pd.to_numeric(f[_first(f, ("volume", "vol"))], errors="coerce") if _first(f, ("volume", "vol")) else np.nan,
            "oi": pd.to_numeric(f[_first(f, ("oi", "open_interest"))], errors="coerce") if _first(f, ("oi", "open_interest")) else np.nan,
        })
        x["symbol"] = f[sym].astype(str).values if sym else p.stem
        x = x.dropna(subset=["timestamp", "close"])
        frames.append(x)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _build_breadth(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    x = rows.sort_values(["symbol", "timestamp"]).copy()
    x["ret1"] = x.groupby("symbol")["close"].pct_change()
    x["ret3"] = x.groupby("symbol")["close"].pct_change(3)
    x["vol_ratio"] = x["volume"] / x.groupby("symbol")["volume"].transform(lambda s: s.rolling(20, min_periods=5).median())
    g = x.groupby("timestamp", sort=True)
    out = g.agg(
        breadth_up_1=("ret1", lambda s: float((s > 0).mean())),
        breadth_down_1=("ret1", lambda s: float((s < 0).mean())),
        breadth_up_3=("ret3", lambda s: float((s > 0).mean())),
        breadth_median_ret1=("ret1", "median"),
        breadth_mean_ret1=("ret1", "mean"),
        breadth_dispersion=("ret1", "std"),
        participation_count=("symbol", "nunique"),
        volume_shock_share=("vol_ratio", lambda s: float((s >= 1.5).mean())),
    ).reset_index()
    # Concentration proxy: largest absolute constituent move share.
    concentration = g["ret1"].apply(lambda s: float(s.abs().max() / s.abs().sum()) if s.abs().sum() > 0 else np.nan)
    out = out.merge(concentration.rename("move_concentration").reset_index(), on="timestamp", how="left")
    return out.sort_values("timestamp")


def _option_events(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in {".parquet", ".csv"} or not any(k in str(p).lower() for k in ("option", "chain", "premium")):
            continue
        try:
            f = _read(p)
        except Exception:
            continue
        t = _first(f, TS_NAMES)
        typ = _first(f, ("option_type", "right", "cp_type", "type"))
        px = _first(f, ("premium", "ltp", "close", "price"))
        if t is None or typ is None or px is None:
            continue
        x = pd.DataFrame({"timestamp": _ns_utc(f[t]), "option_type": f[typ].astype(str).str.upper(), "premium": pd.to_numeric(f[px], errors="coerce")})
        for logical, names in {"iv": ("iv", "implied_volatility"), "oi": ("oi", "open_interest"), "volume": ("volume", "vol"), "spread": ("spread", "bid_ask_spread")}.items():
            c = _first(f, names)
            x[logical] = pd.to_numeric(f[c], errors="coerce") if c else np.nan
        frames.append(x.dropna(subset=["timestamp", "premium"]))
    if not frames:
        return pd.DataFrame()
    x = pd.concat(frames, ignore_index=True)
    x["side"] = np.where(x["option_type"].str.contains("PE|PUT"), "PE", np.where(x["option_type"].str.contains("CE|CALL"), "CE", "OTHER"))
    x = x[x.side != "OTHER"]
    agg = x.groupby(["timestamp", "side"]).agg(premium=("premium", "median"), iv=("iv", "median"), oi=("oi", "sum"), volume=("volume", "sum"), spread=("spread", "median")).reset_index()
    wide = agg.pivot(index="timestamp", columns="side")
    wide.columns = [f"{a.lower()}_{b.lower()}" for a, b in wide.columns]
    wide = wide.reset_index().sort_values("timestamp")
    for side in ("ce", "pe"):
        if f"premium_{side}" in wide:
            wide[f"premium_ret_{side}"] = wide[f"premium_{side}"].pct_change()
    if {"premium_ret_pe", "premium_ret_ce"}.issubset(wide.columns):
        wide["premium_response_skew"] = wide["premium_ret_pe"] - wide["premium_ret_ce"]
    return wide


def _merge_asof(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if right.empty:
        return left
    left = left.copy(); right = right.copy()
    left["timestamp"] = _ns_utc(left["timestamp"]); right["timestamp"] = _ns_utc(right["timestamp"])
    return pd.merge_asof(left.sort_values("timestamp"), right.sort_values("timestamp"), on="timestamp", direction="backward", tolerance=pd.Timedelta("5min"))


def _metrics(r: pd.Series) -> dict[str, float]:
    r = r.dropna()
    if r.empty:
        return {"trades": 0, "mean": 0.0, "win_rate": 0.0, "profit_factor": 0.0}
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": int(len(r)), "mean": float(r.mean()), "win_rate": float((r > 0).mean()), "profit_factor": float(gains / losses) if losses > 0 else float("inf")}


def _cooldown(frame: pd.DataFrame, minutes: int = 15) -> pd.DataFrame:
    keep: list[int] = []
    last: dict[str, pd.Timestamp] = {}
    for i, r in frame.sort_values("timestamp").iterrows():
        prev = last.get(r.session_date)
        if prev is None or r.timestamp - prev >= pd.Timedelta(minutes=minutes):
            keep.append(i); last[r.session_date] = r.timestamp
    return frame.loc[keep]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-root", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)

    underlying = _find_underlying(args.evidence_root)
    breadth = _build_breadth(_constituent_rows(args.evidence_root))
    options = _option_events(args.evidence_root)
    data = _merge_asof(_merge_asof(underlying, breadth), options)
    data["index_ret1"] = data.groupby("session_date")["close"].pct_change()
    data["future_return_15"] = data.groupby("session_date")["close"].shift(-15) / data["close"] - 1.0
    if "breadth_mean_ret1" in data:
        data["index_breadth_divergence"] = data["index_ret1"] - data["breadth_mean_ret1"]
    if "move_concentration" in data and "breadth_down_1" in data:
        data["narrow_decline_event"] = data["move_concentration"] * (1.0 - data["breadth_down_1"])
    if "premium_response_skew" in data:
        data["pe_response_without_breadth"] = data["premium_response_skew"] - data.get("breadth_down_1", 0.0)

    sessions = sorted(data.session_date.unique()); c1, c2 = int(len(sessions) * .6), int(len(sessions) * .8)
    train_s, val_s, hold_s = set(sessions[:c1]), set(sessions[c1:c2]), set(sessions[c2:])
    feature_names = [c for c in (
        "breadth_up_1", "breadth_down_1", "breadth_up_3", "breadth_median_ret1", "breadth_mean_ret1", "breadth_dispersion",
        "volume_shock_share", "move_concentration", "index_breadth_divergence", "narrow_decline_event",
        "premium_response_skew", "premium_ret_pe", "premium_ret_ce", "pe_response_without_breadth",
    ) if c in data.columns and data[c].notna().mean() >= .15]

    candidates: list[dict[str, object]] = []
    train = data[data.session_date.isin(train_s)]
    for feature in feature_names:
        s = train[feature].replace([np.inf, -np.inf], np.nan).dropna()
        if len(s) < 500:
            continue
        for q in (.1, .2, .8, .9):
            threshold = float(s.quantile(q)); high = q > .5
            base = data[feature] >= threshold if high else data[feature] <= threshold
            # Sequence requirement: event persists or strengthens on two consecutive observations.
            seq = base & base.groupby(data["session_date"]).shift(1, fill_value=False)
            for direction, sign in (("CE", 1.0), ("PE", -1.0)):
                row: dict[str, object] = {"feature": feature, "quantile": q, "threshold": threshold, "side": "high" if high else "low", "sequence": "two-step persistence", "direction": direction}
                for name, split in (("validation", val_s), ("holdout", hold_s)):
                    sub = _cooldown(data[seq & data.session_date.isin(split)].copy())
                    row[name] = _metrics(sign * sub["future_return_15"] - .0002)
                candidates.append(row)

    viable = [c for c in candidates if c["validation"]["trades"] >= 30 and c["validation"]["profit_factor"] >= 1.10 and c["validation"]["mean"] > 0 and c["holdout"]["trades"] >= 30 and c["holdout"]["profit_factor"] >= 1.05 and c["holdout"]["mean"] > 0]
    viable.sort(key=lambda c: (c["holdout"]["mean"], c["holdout"]["profit_factor"]), reverse=True)
    report = {
        "scope": "explicit breadth, concentration, option-response and persistent event-sequence discovery",
        "rows": len(data), "sessions": len(sessions), "breadth_rows": len(breadth), "option_rows": len(options),
        "features": feature_names, "tested_candidates": len(candidates), "viable_candidates": viable[:25],
        "verdict": "EXPLICIT_EVENT_SEQUENCE_CANDIDATES_FOUND" if viable else "NO_EXPLICIT_EVENT_SEQUENCE_EDGE_FOUND",
    }
    data.to_parquet(args.output_dir / "explicit_event_sequence_dataset.parquet", index=False)
    pd.DataFrame(candidates).to_json(args.output_dir / "candidate_ledger.json", orient="records", indent=2)
    (args.output_dir / "explicit_event_sequence_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
