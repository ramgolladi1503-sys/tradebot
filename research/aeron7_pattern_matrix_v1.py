#!/usr/bin/env python3
"""Pull Aeron7 NIFTY/BANKNIFTY data and test frozen market-pattern rules.

Research-only. Does not touch TradeBot production code or live broker paths.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

AERON_REPO = "https://github.com/aeron7/nifty-banknifty-intraday-data.git"
YEARS = set(range(2012, 2024))
SYMBOLS = {"NIFTY", "BANKNIFTY"}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    print("+", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)
    if completed.stderr.strip():
        print(completed.stderr.strip(), flush=True)
    return completed.stdout


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clone_index_files(work_root: Path) -> tuple[Path, list[str]]:
    repo = work_root / "aeron7"
    run([
        "git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1",
        AERON_REPO, str(repo),
    ])
    paths = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo).splitlines()
    selected: list[str] = []
    for path in paths:
        parts = path.split("/")
        if not parts or not parts[0].isdigit() or int(parts[0]) not in YEARS:
            continue
        if Path(path).name.upper() not in {"NIFTY.TXT", "BANKNIFTY.TXT"}:
            continue
        selected.append(path)
    if not selected:
        raise RuntimeError("No Aeron7 NIFTY/BANKNIFTY files found")

    run(["git", "config", "core.sparseCheckout", "true"], cwd=repo)
    sparse = repo / ".git" / "info" / "sparse-checkout"
    sparse.parent.mkdir(parents=True, exist_ok=True)
    sparse.write_text("".join(f"/{p}\n" for p in selected), encoding="utf-8")
    run(["git", "read-tree", "-mu", "HEAD"], cwd=repo)
    return repo, selected


def normalize_symbol(value: str) -> str | None:
    token = re.sub(r"[^A-Z0-9]", "", value.upper())
    if token in {"NIFTY", "NIFTY50", "NIFTYI"}:
        return "NIFTY"
    if token in {"BANKNIFTY", "NIFTYBANK", "BANKNIFTYI"}:
        return "BANKNIFTY"
    return None


def load_raw(repo: Path, selected: list[str]) -> tuple[pd.DataFrame, dict]:
    rows: list[tuple] = []
    failed: list[dict] = []
    parsed_files = 0
    for index, rel in enumerate(selected, 1):
        path = repo / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            accepted = 0
            for line in text.splitlines():
                parts = [item.strip() for item in line.split(",")]
                if len(parts) < 7:
                    continue
                symbol = normalize_symbol(parts[0])
                if symbol is None:
                    continue
                if not re.fullmatch(r"\d{8}", parts[1]):
                    continue
                if not re.fullmatch(r"\d{1,2}:\d{2}", parts[2]):
                    continue
                try:
                    values = tuple(float(x) for x in parts[3:7])
                except ValueError:
                    continue
                rows.append((symbol, parts[1], parts[2], *values, rel))
                accepted += 1
            if accepted:
                parsed_files += 1
        except Exception as exc:  # evidence capture, not silent ignore
            failed.append({"path": rel, "error": repr(exc)})
        if index % 250 == 0:
            print(f"parsed {index}/{len(selected)} selected files", flush=True)

    raw = pd.DataFrame(rows, columns=[
        "symbol", "date_text", "time_text", "open", "high", "low", "close", "source_file"
    ])
    if raw.empty:
        raise RuntimeError("Aeron7 files produced no usable index rows")
    raw["dt"] = pd.to_datetime(
        raw["date_text"] + " " + raw["time_text"], format="%Y%m%d %H:%M", errors="coerce"
    )
    raw = raw.dropna(subset=["dt"])
    raw = raw[raw["dt"].dt.year.isin(YEARS)]
    raw = raw[(raw["dt"].dt.time >= pd.Timestamp("09:15").time()) &
              (raw["dt"].dt.time < pd.Timestamp("15:30").time())]
    valid = (
        (raw[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (raw["low"] <= raw[["open", "close"]].min(axis=1))
        & (raw["high"] >= raw[["open", "close"]].max(axis=1))
        & (raw["low"] <= raw["high"])
    )
    invalid_ohlc = int((~valid).sum())
    raw = raw[valid].copy()
    before = len(raw)
    raw = raw.sort_values(["symbol", "dt", "source_file"]).drop_duplicates(
        ["symbol", "dt"], keep="last"
    )
    duplicate_rows = before - len(raw)
    inventory = {
        "repository": AERON_REPO,
        "selected_paths": len(selected),
        "parsed_files": parsed_files,
        "failed_files": failed,
        "raw_rows_after_dedup": int(len(raw)),
        "duplicate_rows_removed": int(duplicate_rows),
        "invalid_ohlc_removed": invalid_ohlc,
        "raw_min_timestamp": str(raw["dt"].min()),
        "raw_max_timestamp": str(raw["dt"].max()),
    }
    return raw, inventory


def resample_5m(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    frames: list[pd.DataFrame] = []
    rejected: list[dict] = []
    raw = raw.copy()
    raw["session"] = raw["dt"].dt.strftime("%Y-%m-%d")
    for (symbol, session), group in raw.groupby(["symbol", "session"], sort=True):
        group = group.sort_values("dt").set_index("dt")
        bars = group[["open", "high", "low", "close"]].resample(
            "5min", origin="start_day", offset="9h15min", label="left", closed="left"
        ).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        bars = bars[(bars.index.time >= pd.Timestamp("09:15").time()) &
                    (bars.index.time < pd.Timestamp("15:30").time())]
        required = {"09:15", "09:25", "09:40", "09:45", "10:10", "10:45", "12:55", "13:00", "13:55", "14:00", "15:25"}
        present = set(bars.index.strftime("%H:%M"))
        if len(bars) < 70 or not required.issubset(present):
            rejected.append({
                "symbol": symbol, "session": session, "bars": int(len(bars)),
                "missing_required": sorted(required - present),
            })
            continue
        bars = bars.reset_index()
        bars["symbol"] = symbol
        bars["session"] = session
        frames.append(bars)
    if not frames:
        raise RuntimeError("No complete Aeron7 sessions after 5-minute normalization")
    data = pd.concat(frames, ignore_index=True)
    info = {
        "accepted_symbol_sessions": int(data.groupby(["symbol", "session"]).ngroups),
        "accepted_dates": int(data["session"].nunique()),
        "rejected_symbol_sessions": len(rejected),
        "rejected_examples": rejected[:50],
        "min_session": str(data["session"].min()),
        "max_session": str(data["session"].max()),
    }
    return data, info


def value_at(group: pd.DataFrame, time_text: str, column: str) -> float:
    row = group[group["time"] == time_text]
    return float(row.iloc[0][column]) if len(row) else np.nan


def close_before(group: pd.DataFrame, decision: str) -> float:
    rows = group[group["time"] < decision]
    return float(rows.iloc[-1]["close"]) if len(rows) else np.nan


def range_window(group: pd.DataFrame, start: str, end: str) -> tuple[float, float, float]:
    rows = group[(group["time"] >= start) & (group["time"] < end)]
    if rows.empty:
        return np.nan, np.nan, np.nan
    return float(rows["high"].max() - rows["low"].min()), float(rows["high"].max()), float(rows["low"].min())


def build_features(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy().sort_values(["symbol", "session", "dt"])
    data["time"] = data["dt"].dt.strftime("%H:%M")
    records: list[dict] = []
    for symbol, symbol_data in data.groupby("symbol"):
        previous = None
        for session, group in symbol_data.groupby("session", sort=True):
            group = group.sort_values("dt")
            open_price = value_at(group, "09:15", "open")
            close15 = close_before(group, "09:30")
            close30 = close_before(group, "09:45")
            close60 = close_before(group, "10:15")
            close1300 = close_before(group, "13:00")
            close1400 = close_before(group, "14:00")
            entry0945 = value_at(group, "09:45", "open")
            exit1045 = value_at(group, "10:45", "open")
            entry1300 = value_at(group, "13:00", "open")
            entry1400 = value_at(group, "14:00", "open")
            close_day = value_at(group, "15:25", "close")
            high_day = float(group["high"].max())
            low_day = float(group["low"].min())
            range15, high15, low15 = range_window(group, "09:15", "09:30")
            range30, high30, low30 = range_window(group, "09:15", "09:45")
            range60, high60, low60 = range_window(group, "09:15", "10:15")
            range13, high13, low13 = range_window(group, "09:15", "13:00")
            range14, high14, low14 = range_window(group, "09:15", "14:00")
            midday_range, _, _ = range_window(group, "11:30", "13:00")
            if previous and previous["range"] > 0:
                pr = previous["range"]
                record = {
                    "symbol": symbol, "session": session, "date": pd.Timestamp(session),
                    "open": open_price, "close15": close15, "close30": close30,
                    "close60": close60, "close1300": close1300, "close1400": close1400,
                    "entry0945": entry0945, "exit1045": exit1045,
                    "entry1300": entry1300, "entry1400": entry1400, "close_day": close_day,
                    "prev_close": previous["close"], "prev_high": previous["high"],
                    "prev_low": previous["low"], "prev_range": pr,
                    "gap_norm": abs(open_price - previous["close"]) / pr,
                    "gap_dir": int(np.sign(open_price - previous["close"])),
                    "disp15_norm": (close15 - open_price) / pr,
                    "disp30_norm": (close30 - open_price) / pr,
                    "disp60_norm": (close60 - open_price) / pr,
                    "disp1400_norm": (close1400 - open_price) / pr,
                    "r15_ret": close15 / open_price - 1,
                    "r30_ret": close30 / open_price - 1,
                    "r30_norm": range30 / pr,
                    "r60": range60, "r_mid": midday_range,
                    "efficiency30": abs(close30 - open_price) / range30 if range30 else np.nan,
                    "efficiency60": abs(close60 - open_price) / range60 if range60 else np.nan,
                    "clv30": (close30 - low30) / range30 if range30 else np.nan,
                    "clv13": (close1300 - low13) / range13 if range13 else np.nan,
                    "clv14": (close1400 - low14) / range14 if range14 else np.nan,
                    "ret_0945_1045": exit1045 / entry0945 - 1,
                    "ret_0945_close": close_day / entry0945 - 1,
                    "ret_1300_close": close_day / entry1300 - 1,
                    "ret_1400_close": close_day / entry1400 - 1,
                }
                records.append(record)
            previous = {"close": close_day, "high": high_day, "low": low_day, "range": high_day - low_day}
    features = pd.DataFrame(records)
    for name in ["disp15_norm", "disp30_norm", "disp60_norm", "disp1400_norm"]:
        features["dir" + name[4:name.index("_") if "_" in name[4:] else None]] = np.sign(features[name]).astype(int)
    features["dir15"] = np.sign(features["disp15_norm"]).astype(int)
    features["dir30"] = np.sign(features["disp30_norm"]).astype(int)
    features["dir60"] = np.sign(features["disp60_norm"]).astype(int)
    features["dir1400"] = np.sign(features["disp1400_norm"]).astype(int)

    context: list[dict] = []
    for session, group in features.groupby("session"):
        if set(group["symbol"]) != SYMBOLS:
            continue
        r15 = group.set_index("symbol")["r15_ret"]
        r30 = group.set_index("symbol")["r30_ret"]
        dir15 = group.set_index("symbol")["dir15"]
        dir30 = group.set_index("symbol")["dir30"]
        abs30 = group.set_index("symbol")["disp30_norm"].abs()
        context.append({
            "session": session,
            "disp15_bps": float((r15.max() - r15.min()) * 1e4),
            "disp30_bps": float((r30.max() - r30.min()) * 1e4),
            "both_dir15": bool(len(set(dir15)) == 1 and int(dir15.iloc[0]) != 0),
            "both_dir30": bool(len(set(dir30)) == 1 and int(dir30.iloc[0]) != 0),
            "leader_symbol": str(abs30.idxmax()),
        })
    return features.merge(pd.DataFrame(context), on="session", how="inner")


def add_patterns(features: pd.DataFrame) -> dict[str, dict]:
    f = features
    abs15 = f["disp15_norm"].abs()
    abs30 = f["disp30_norm"].abs()
    abs60 = f["disp60_norm"].abs()
    abs1400 = f["disp1400_norm"].abs()
    edge_dir = np.where(f["clv30"] >= 0.8, 1, np.where(f["clv30"] <= 0.2, -1, 0))
    outside_dir = np.where(
        f["close30"] >= f["prev_high"] + 0.05 * f["prev_range"], 1,
        np.where(f["close30"] <= f["prev_low"] - 0.05 * f["prev_range"], -1, 0),
    )
    mid_same = ((f["dir60"] > 0) & (f["clv13"] >= 0.65)) | ((f["dir60"] < 0) & (f["clv13"] <= 0.35))
    late_same = ((f["dir1400"] > 0) & (f["clv14"] >= 0.8)) | ((f["dir1400"] < 0) & (f["clv14"] <= 0.2))

    return {
        "GAP_GO": {"stage": "OPEN", "active": (f["gap_norm"] >= 0.33) & (f["gap_dir"] != 0) & (f["dir30"] == f["gap_dir"]) & (abs30 >= 0.15), "direction": f["gap_dir"]},
        "GAP_REJECT_RESUME": {"stage": "OPEN", "active": (f["gap_norm"] >= 0.33) & (f["gap_dir"] != 0) & (f["dir15"] == -f["gap_dir"]) & (abs15 >= 0.10) & (f["dir30"] == f["gap_dir"]) & (abs30 >= 0.10), "direction": f["gap_dir"]},
        "WIDE_OPEN_OVERSHOOT_FADE": {"stage": "OPEN", "active": (f["gap_norm"] >= 0.33) & (f["r30_norm"] >= 0.55) & (abs15 >= 0.20) & (f["dir15"] != 0), "direction": -f["dir15"]},
        "NARROW_OR_EDGE_CONFIRM": {"stage": "OPEN", "active": (f["r30_norm"] <= 0.35) & (edge_dir != 0) & f["both_dir30"] & (f["dir30"] == edge_dir), "direction": pd.Series(edge_dir, index=f.index)},
        "LOW_DISPERSION_15_RESUME": {"stage": "OPEN", "active": (f["disp15_bps"] <= 12) & f["both_dir15"] & (abs15 >= 0.10), "direction": f["dir15"]},
        "EFFICIENT_SYNC_DRIVE": {"stage": "OPEN", "active": f["both_dir30"] & (f["disp30_bps"] <= 20) & (abs30 >= 0.25) & (f["efficiency30"] >= 0.65), "direction": f["dir30"]},
        "PRIOR_RANGE_ACCEPTANCE": {"stage": "OPEN", "active": (outside_dir != 0) & f["both_dir30"] & (f["dir30"] == outside_dir), "direction": pd.Series(outside_dir, index=f.index)},
        "LEADER_PERSISTENCE": {"stage": "OPEN", "active": (f["leader_symbol"] == f["symbol"]) & (f["disp30_bps"] >= 20) & (abs30 >= 0.20) & (f["dir30"] != 0), "direction": f["dir30"]},
        "MORNING_TREND_MIDDAY_COMP": {"stage": "MIDDAY", "active": (abs60 >= 0.35) & (f["efficiency60"] >= 0.65) & (f["r_mid"] <= 0.35 * f["r60"]) & mid_same & (f["dir60"] != 0), "direction": f["dir60"]},
        "LATE_DAY_PERSISTENCE": {"stage": "LATE", "active": (abs1400 >= 0.50) & late_same & (f["dir1400"] != 0), "direction": f["dir1400"]},
    }


def signal_rows(features: pd.DataFrame, rule: dict) -> pd.DataFrame:
    mask = rule["active"].fillna(False).astype(bool) & (rule["direction"].fillna(0) != 0)
    rows = features.loc[mask, [
        "symbol", "session", "date", "ret_0945_1045", "ret_0945_close", "ret_1300_close", "ret_1400_close"
    ]].copy()
    rows["direction"] = rule["direction"].loc[mask].astype(int).values
    if rule["stage"] == "OPEN":
        rows["signed_short"] = rows["direction"] * rows["ret_0945_1045"]
        rows["signed_primary"] = rows["direction"] * rows["ret_0945_close"]
    elif rule["stage"] == "MIDDAY":
        rows["signed_short"] = np.nan
        rows["signed_primary"] = rows["direction"] * rows["ret_1300_close"]
    else:
        rows["signed_short"] = np.nan
        rows["signed_primary"] = rows["direction"] * rows["ret_1400_close"]
    return rows


def metrics(rows: pd.DataFrame, dates: pd.Series) -> dict:
    total_dates = int(dates.nunique())
    if rows.empty or total_dates == 0:
        return {"dates": 0, "occurrence_pct": 0.0, "symbol_trades": 0}
    equal = rows.groupby("date").agg(value=("signed_primary", "mean"), symbol_trades=("symbol", "nunique")).reset_index()
    values = equal["value"].dropna()
    gains = values[values > 0].sum()
    top5 = values.nlargest(min(5, len(values))).sum()
    return {
        "dates": int(len(equal)),
        "occurrence_pct": float(100 * len(equal) / total_dates),
        "symbol_trades": int(len(rows)),
        "win_pct": float(100 * (values > 0).mean()),
        "net5_win_pct": float(100 * (values * 1e4 > 5).mean()),
        "mean_bps": float(values.mean() * 1e4),
        "median_bps": float(values.median() * 1e4),
        "net5_mean_bps": float(values.mean() * 1e4 - 5),
        "top5_positive_share_pct": float(100 * top5 / gains) if gains > 0 else None,
    }


def evaluate(features: pd.DataFrame, rules: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    periods = {
        "2012-2015": (2012, 2015),
        "2016-2019": (2016, 2019),
        "2020-2023": (2020, 2023),
    }
    signals = {name: signal_rows(features, rule) for name, rule in rules.items()}
    single_records: list[dict] = []
    for name, rows in signals.items():
        for period, (start, end) in periods.items():
            allowed_dates = features.loc[features["date"].dt.year.between(start, end), "date"].drop_duplicates()
            subset = rows[rows["date"].dt.year.between(start, end)]
            single_records.append({"pattern": name, "period": period, **metrics(subset, allowed_dates)})

    comparable_open = [
        "GAP_GO", "GAP_REJECT_RESUME", "NARROW_OR_EDGE_CONFIRM", "LOW_DISPERSION_15_RESUME",
        "EFFICIENT_SYNC_DRIVE", "PRIOR_RANGE_ACCEPTANCE", "LEADER_PERSISTENCE",
    ]
    combos: dict[str, pd.DataFrame] = {}
    for left, right in [
        ("PRIOR_RANGE_ACCEPTANCE", "LEADER_PERSISTENCE"),
        ("GAP_GO", "LEADER_PERSISTENCE"),
        ("LOW_DISPERSION_15_RESUME", "PRIOR_RANGE_ACCEPTANCE"),
        ("GAP_GO", "LOW_DISPERSION_15_RESUME"),
        ("GAP_GO", "PRIOR_RANGE_ACCEPTANCE"),
        ("GAP_GO", "EFFICIENT_SYNC_DRIVE"),
    ]:
        a, b = rules[left], rules[right]
        mask = a["active"] & b["active"] & (a["direction"] == b["direction"]) & (a["direction"] != 0)
        rows = features.loc[mask, ["symbol", "session", "date", "ret_0945_1045", "ret_0945_close"]].copy()
        rows["direction"] = a["direction"].loc[mask].astype(int).values
        rows["signed_short"] = rows["direction"] * rows["ret_0945_1045"]
        rows["signed_primary"] = rows["direction"] * rows["ret_0945_close"]
        combos[f"{left} + {right}"] = rows

    votes = features[["symbol", "session", "date", "ret_0945_1045", "ret_0945_close"]].copy()
    vote_columns = []
    for name in comparable_open:
        column = f"{name}_vote"
        vote_columns.append(column)
        votes[column] = np.where(rules[name]["active"], rules[name]["direction"], 0)
    votes["positive"] = (votes[vote_columns] > 0).sum(axis=1)
    votes["negative"] = (votes[vote_columns] < 0).sum(axis=1)
    for required in (2, 3):
        direction = np.where(
            (votes["positive"] >= required) & (votes["negative"] == 0), 1,
            np.where((votes["negative"] >= required) & (votes["positive"] == 0), -1, 0),
        )
        mask = direction != 0
        rows = votes.loc[mask, ["symbol", "session", "date", "ret_0945_1045", "ret_0945_close"]].copy()
        rows["direction"] = direction[mask]
        rows["signed_short"] = rows["direction"] * rows["ret_0945_1045"]
        rows["signed_primary"] = rows["direction"] * rows["ret_0945_close"]
        combos[f"{required}-OF-7 UNANIMOUS-SIDE VOTE"] = rows

    priority = [
        "GAP_REJECT_RESUME", "GAP_GO", "EFFICIENT_SYNC_DRIVE", "LOW_DISPERSION_15_RESUME",
        "PRIOR_RANGE_ACCEPTANCE", "NARROW_OR_EDGE_CONFIRM", "LEADER_PERSISTENCE",
    ]
    chosen = np.zeros(len(features), dtype=int)
    component = np.array([""] * len(features), dtype=object)
    for name in priority:
        rule = rules[name]
        take = (chosen == 0) & rule["active"].values & (rule["direction"].values != 0)
        chosen[take] = rule["direction"].values[take]
        component[take] = name
    mask = chosen != 0
    rows = features.loc[mask, ["symbol", "session", "date", "ret_0945_1045", "ret_0945_close"]].copy()
    rows["direction"] = chosen[mask]
    rows["component"] = component[mask]
    rows["signed_short"] = rows["direction"] * rows["ret_0945_1045"]
    rows["signed_primary"] = rows["direction"] * rows["ret_0945_close"]
    combos["REGIME_ROUTER"] = rows

    combo_records: list[dict] = []
    for name, rows in combos.items():
        for period, (start, end) in periods.items():
            allowed_dates = features.loc[features["date"].dt.year.between(start, end), "date"].drop_duplicates()
            subset = rows[rows["date"].dt.year.between(start, end)]
            combo_records.append({"combo": name, "period": period, **metrics(subset, allowed_dates)})

    annual: dict[str, dict] = {}
    for name in ["GAP_GO", "LOW_DISPERSION_15_RESUME", "EFFICIENT_SYNC_DRIVE", "PRIOR_RANGE_ACCEPTANCE", "LEADER_PERSISTENCE", "LATE_DAY_PERSISTENCE"]:
        annual[name] = {}
        for year in range(2012, 2024):
            dates = features.loc[features["date"].dt.year == year, "date"].drop_duplicates()
            annual[name][str(year)] = metrics(signals[name][signals[name]["date"].dt.year == year], dates)
    return pd.DataFrame(single_records), pd.DataFrame(combo_records), annual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="aeron7_pattern_output")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix="aeron7-pattern-"))
    try:
        repo, selected = clone_index_files(work_root)
        raw, source_inventory = load_raw(repo, selected)
        five_minute, session_inventory = resample_5m(raw)
        features = build_features(five_minute)
        rules = add_patterns(features)
        single, combos, annual = evaluate(features, rules)

        five_path = output / "aeron7_nifty_banknifty_5minute_2012_2023.csv.gz"
        five_minute.to_csv(five_path, index=False, compression="gzip")
        feature_path = output / "aeron7_session_features_2012_2023.csv.gz"
        features.to_csv(feature_path, index=False, compression="gzip")
        single_path = output / "aeron7_single_pattern_matrix.csv"
        combo_path = output / "aeron7_combination_matrix.csv"
        single.to_csv(single_path, index=False)
        combos.to_csv(combo_path, index=False)

        manifest = {
            "source": source_inventory,
            "sessions": session_inventory,
            "features": {
                "rows": int(len(features)),
                "dates": int(features["session"].nunique()),
                "symbols": sorted(features["symbol"].unique().tolist()),
                "min_date": str(features["session"].min()),
                "max_date": str(features["session"].max()),
            },
            "comparability": {
                "exactly_comparable": [
                    "GAP_GO", "GAP_REJECT_RESUME", "WIDE_OPEN_OVERSHOOT_FADE",
                    "MORNING_TREND_MIDDAY_COMP", "LATE_DAY_PERSISTENCE",
                ],
                "two_index_analogue_only": [
                    "NARROW_OR_EDGE_CONFIRM", "LOW_DISPERSION_15_RESUME",
                    "EFFICIENT_SYNC_DRIVE", "PRIOR_RANGE_ACCEPTANCE", "LEADER_PERSISTENCE",
                ],
                "not_computable_exactly": ["UNCONFIRMED_COUNTER_GAP", "three-index SENSEX confirmation"],
                "volume_vwap": "not evaluated; Aeron7 index volume fields are not treated as reliable traded volume",
            },
            "single_metrics": single.to_dict(orient="records"),
            "combination_metrics": combos.to_dict(orient="records"),
            "annual": annual,
            "artifacts": {},
        }
        for path in [five_path, feature_path, single_path, combo_path]:
            manifest["artifacts"][path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        manifest_path = output / "aeron7_pattern_matrix.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        (output / "aeron7_pattern_matrix.json.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="utf-8")

        summary = {
            "source": manifest["source"],
            "sessions": manifest["sessions"],
            "features": manifest["features"],
            "comparability": manifest["comparability"],
            "single_metrics": manifest["single_metrics"],
            "combination_metrics": manifest["combination_metrics"],
        }
        print("AERON7_RESULT_JSON_BEGIN", flush=True)
        print(json.dumps(summary, separators=(",", ":")), flush=True)
        print("AERON7_RESULT_JSON_END", flush=True)
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


if __name__ == "__main__":
    main()
