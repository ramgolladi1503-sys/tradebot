from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

IST = "Asia/Kolkata"


@dataclass(frozen=True)
class FeatureEngineResult:
    rows: pd.DataFrame
    rejected: list[dict[str, Any]]


def _normalize_bars(path: Path, instrument: str, trading_date: str) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
    ts_col = next((col for col in ("timestamp", "datetime", "date", "time") if col in df.columns), None)
    if ts_col is None:
        raise ValueError(f"{path}: missing timestamp column")
    timestamps = pd.to_datetime(df[ts_col], errors="coerce")
    if timestamps.isna().any():
        raise ValueError(f"{path}: invalid timestamps")
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(IST)
    else:
        timestamps = timestamps.dt.tz_convert(IST)
    out = df.copy()
    out["timestamp"] = timestamps
    out["instrument"] = instrument
    out["session_date"] = trading_date
    out["source_path"] = str(path)
    return out.sort_values("timestamp")


def build_five_minute_features(manifest: list[dict[str, Any]], *, decision_offset: int = 3) -> FeatureEngineResult:
    frames: list[pd.DataFrame] = []
    rejected: list[dict[str, Any]] = []
    for row in manifest:
        path = Path(row["absolute_path"]) if "absolute_path" in row else Path(row["relative_path"])
        try:
            bars = _normalize_bars(path, row["instrument"], row["trading_date"])
        except Exception as exc:
            rejected.append({"path": str(path), "reason": str(exc)})
            continue
        diffs = bars["timestamp"].diff().dropna()
        if not diffs.empty and not (diffs == pd.Timedelta(minutes=5)).all():
            rejected.append({"path": str(path), "reason": "non-five-minute interval"})
            continue
        frames.append(bars)
    if not frames:
        return FeatureEngineResult(pd.DataFrame(), rejected)
    bars = pd.concat(frames, ignore_index=True)
    rows = []
    for date, session in bars.groupby("session_date"):
        by_inst = {inst: part.reset_index(drop=True) for inst, part in session.groupby("instrument")}
        missing = {"NIFTY", "BANKNIFTY", "SENSEX"} - set(by_inst)
        if missing:
            rejected.append({"session_date": date, "reason": f"missing index components: {sorted(missing)}"})
            continue
        common_times = set(by_inst["NIFTY"]["timestamp"])
        for inst in ("BANKNIFTY", "SENSEX"):
            common_times &= set(by_inst[inst]["timestamp"])
        if not common_times:
            rejected.append({"session_date": date, "reason": "no common completed timestamps"})
            continue
        decision_ts = sorted(common_times)[min(decision_offset, len(common_times) - 1)]
        inputs = {}
        for inst in ("NIFTY", "BANKNIFTY", "SENSEX"):
            usable = by_inst[inst][by_inst[inst]["timestamp"] <= decision_ts]
            if usable.empty:
                rejected.append({"session_date": date, "reason": f"{inst} unavailable at decision"})
                break
            first = usable.iloc[0]
            last = usable.iloc[-1]
            inputs[inst] = {
                "open": float(first["open"]),
                "close": float(last["close"]),
                "timestamp": last["timestamp"].isoformat(),
                "source_path": last["source_path"],
            }
        if set(inputs) != {"NIFTY", "BANKNIFTY", "SENSEX"}:
            continue
        nifty_move = (inputs["NIFTY"]["close"] / inputs["NIFTY"]["open"]) - 1.0
        bank_move = (inputs["BANKNIFTY"]["close"] / inputs["BANKNIFTY"]["open"]) - 1.0
        sensex_move = (inputs["SENSEX"]["close"] / inputs["SENSEX"]["open"]) - 1.0
        rows.append(
            {
                "session_date": date,
                "decision_timestamp": decision_ts.isoformat(),
                "nifty_move": nifty_move,
                "banknifty_move": bank_move,
                "sensex_move": sensex_move,
                "cross_index_dislocation": nifty_move - ((bank_move + sensex_move) / 2.0),
                "lineage": inputs,
            }
        )
    return FeatureEngineResult(pd.DataFrame(rows), rejected)


def truncation_oracle(manifest: list[dict[str, Any]], decision_timestamp: str) -> bool:
    full = build_five_minute_features(manifest).rows
    if full.empty:
        return True
    cutoff = pd.Timestamp(decision_timestamp)
    truncated_manifest = []
    temp_files: list[Path] = []
    for row in manifest:
        path = Path(row["absolute_path"]) if "absolute_path" in row else Path(row["relative_path"])
        df = _normalize_bars(path, row["instrument"], row["trading_date"])
        df = df[df["timestamp"] <= cutoff]
        tmp = path.with_name(path.stem + ".truncated_for_oracle.csv")
        df.to_csv(tmp, index=False)
        temp_files.append(tmp)
        truncated_manifest.append({**row, "absolute_path": str(tmp)})
    try:
        truncated = build_five_minute_features(truncated_manifest).rows
    finally:
        for path in temp_files:
            path.unlink(missing_ok=True)
    cols = ["session_date", "decision_timestamp", "nifty_move", "banknifty_move", "sensex_move", "cross_index_dislocation"]
    return full[cols].head(len(truncated)).equals(truncated[cols])
