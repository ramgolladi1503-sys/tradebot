from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(path)


def _timestamp_column(frame: pd.DataFrame) -> str | None:
    for name in ("timestamp", "datetime", "date_time", "time", "ts"):
        if name in frame.columns:
            return name
    return None


def _normalise(frame: pd.DataFrame, source: Path) -> pd.DataFrame | None:
    ts_col = _timestamp_column(frame)
    if ts_col is None:
        return None
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out[ts_col], errors="coerce", utc=True)
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp")
    out["source_file"] = str(source)
    return out


def _candidate_files(root: Path) -> list[Path]:
    keys = (
        "constituent", "breadth", "lead_lag", "lead-lag", "option", "chain",
        "premium", "depth", "orderbook", "basis", "futures", "sector",
    )
    files: list[Path] = []
    for suffix in ("*.parquet", "*.csv"):
        for path in root.rglob(suffix):
            text = str(path).lower()
            if any(key in text for key in keys):
                files.append(path)
    return sorted(set(files))


def _pick_numeric_columns(frame: pd.DataFrame) -> list[str]:
    names = []
    for col in frame.select_dtypes(include=[np.number]).columns:
        low = col.lower()
        if any(k in low for k in (
            "breadth", "advance", "decline", "weight", "sector", "lead", "lag",
            "ce", "pe", "premium", "iv", "volume", "oi", "spread", "depth",
            "imbalance", "basis", "future", "elastic", "response",
        )):
            names.append(col)
    return names[:80]


def _merge_sources(files: list[Path]) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    merged: pd.DataFrame | None = None
    inventory: list[dict[str, object]] = []
    for path in files:
        try:
            raw = _read(path)
            norm = _normalise(raw, path)
        except Exception as exc:  # evidence inventory must remain truthful
            inventory.append({"path": str(path), "status": "read_error", "error": repr(exc)})
            continue
        if norm is None:
            inventory.append({"path": str(path), "status": "no_timestamp"})
            continue
        cols = _pick_numeric_columns(norm)
        inventory.append({"path": str(path), "status": "usable" if cols else "no_event_columns", "rows": len(norm), "columns": cols})
        if not cols:
            continue
        slim = norm[["timestamp", *cols]].drop_duplicates("timestamp")
        prefix = path.stem[:24].replace("-", "_")
        slim = slim.rename(columns={c: f"{prefix}__{c}" for c in cols})
        merged = slim if merged is None else pd.merge_asof(
            merged.sort_values("timestamp"), slim.sort_values("timestamp"), on="timestamp",
            direction="backward", tolerance=pd.Timedelta("5min")
        )
    return (merged if merged is not None else pd.DataFrame()), inventory


def _find_underlying(root: Path) -> pd.DataFrame:
    files = sorted(root.rglob("NIFTY_*.parquet"))
    frames = []
    for path in files:
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        ts = _timestamp_column(frame)
        if ts is None or "close" not in frame.columns:
            continue
        frame = frame.copy()
        frame["timestamp"] = pd.to_datetime(frame[ts], errors="coerce", utc=True)
        frame = frame.dropna(subset=["timestamp"])
        if "session_date" not in frame.columns:
            frame["session_date"] = frame["timestamp"].dt.tz_convert("Asia/Kolkata").dt.date.astype(str)
        frames.append(frame[["timestamp", "session_date", "close"]])
    if not frames:
        raise FileNotFoundError("no NIFTY underlying parquet files found")
    out = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    return out


def _metrics(ret: pd.Series) -> dict[str, float]:
    ret = ret.dropna()
    if ret.empty:
        return {"trades": 0, "mean": 0.0, "win_rate": 0.0, "profit_factor": 0.0}
    gains = ret[ret > 0].sum()
    losses = -ret[ret < 0].sum()
    return {
        "trades": int(len(ret)),
        "mean": float(ret.mean()),
        "win_rate": float((ret > 0).mean()),
        "profit_factor": float(gains / losses) if losses > 0 else float("inf"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    underlying = _find_underlying(args.evidence_root)
    event_files = _candidate_files(args.evidence_root)
    events, inventory = _merge_sources(event_files)

    report: dict[str, object] = {
        "event_file_count": len(event_files),
        "usable_event_sources": sum(1 for x in inventory if x.get("status") == "usable"),
        "inventory": inventory,
        "scope": "non-candle multi-event directional discovery using breadth/lead-lag/options/liquidity/basis sources",
    }
    if events.empty:
        report["verdict"] = "MULTIEVENT_INPUTS_NOT_AVAILABLE"
        (args.output_dir / "multievent_report.json").write_text(json.dumps(report, indent=2, default=str))
        print(json.dumps(report, indent=2, default=str))
        return 0

    data = pd.merge_asof(underlying, events.sort_values("timestamp"), on="timestamp", direction="backward", tolerance=pd.Timedelta("5min"))
    data["future_return_5"] = data.groupby("session_date")["close"].shift(-5) / data["close"] - 1.0
    data["future_return_15"] = data.groupby("session_date")["close"].shift(-15) / data["close"] - 1.0

    sessions = sorted(data["session_date"].unique())
    c1, c2 = int(len(sessions) * 0.60), int(len(sessions) * 0.80)
    train_s, val_s, hold_s = set(sessions[:c1]), set(sessions[c1:c2]), set(sessions[c2:])
    numeric = [c for c in data.select_dtypes(include=[np.number]).columns if "__" in c and data[c].notna().mean() >= 0.20]

    candidates: list[dict[str, object]] = []
    train = data[data.session_date.isin(train_s)]
    for col in numeric:
        s = train[col].replace([np.inf, -np.inf], np.nan).dropna()
        if len(s) < 500:
            continue
        for q in (0.10, 0.20, 0.80, 0.90):
            threshold = float(s.quantile(q))
            side = "low" if q < 0.5 else "high"
            for direction, sign in (("PE", -1.0), ("CE", 1.0)):
                row = {"feature": col, "quantile": q, "threshold": threshold, "side": side, "direction": direction}
                ok = data[col] <= threshold if side == "low" else data[col] >= threshold
                for split_name, split_sessions in (("validation", val_s), ("holdout", hold_s)):
                    subset = data[ok & data.session_date.isin(split_sessions)].copy()
                    # 15-minute cooldown to avoid duplicate overlapping events
                    subset = subset.sort_values("timestamp")
                    keep = []
                    last_by_session: dict[str, pd.Timestamp] = {}
                    for idx, r in subset.iterrows():
                        last = last_by_session.get(r.session_date)
                        if last is None or r.timestamp - last >= pd.Timedelta("15min"):
                            keep.append(idx)
                            last_by_session[r.session_date] = r.timestamp
                    ret = sign * subset.loc[keep, "future_return_15"] - 0.0002
                    row[split_name] = _metrics(ret)
                candidates.append(row)

    viable = [c for c in candidates if c["validation"]["trades"] >= 40 and c["validation"]["profit_factor"] >= 1.10 and c["validation"]["mean"] > 0 and c["holdout"]["trades"] >= 40 and c["holdout"]["profit_factor"] >= 1.05 and c["holdout"]["mean"] > 0]
    viable.sort(key=lambda x: (x["holdout"]["mean"], x["holdout"]["profit_factor"]), reverse=True)

    report.update({
        "rows": len(data), "sessions": len(sessions), "event_features": len(numeric),
        "tested_candidates": len(candidates), "viable_candidates": viable[:25],
        "verdict": "MULTIEVENT_DIRECTIONAL_CANDIDATES_FOUND" if viable else "NO_MULTIEVENT_DIRECTIONAL_EDGE_FOUND",
    })
    data.to_parquet(args.output_dir / "multievent_joined_dataset.parquet", index=False)
    (args.output_dir / "multievent_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
