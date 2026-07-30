from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("research/local_evidence_consolidation_v1")
STAGE1 = Path("information-migration-sequence-v1-stage1")
OUT = Path("information-migration-sequence-v1-stage2")
HORIZONS_MINUTES = (5, 10, 15)
MIN_DEVELOPMENT_TRADES = 100
MIN_VALIDATION_TRADES = 40
FIXED_ROUND_TRIP_FRICTION_PCT = 0.01


def _first_path(name: str) -> Path:
    paths = sorted(ROOT.rglob(name))
    if not paths:
        raise SystemExit(f"missing {name}")
    return paths[0]


def _summary(frame: pd.DataFrame, column: str) -> dict[str, float | int]:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return {"trades": 0, "mean": float("nan"), "median": float("nan"), "win_rate": float("nan")}
    return {
        "trades": int(values.size),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "win_rate": float((values > 0).mean()),
    }


def main() -> None:
    signals_path = STAGE1 / "frozen_signals.parquet"
    report_path = STAGE1 / "stage1_report.json"
    if not signals_path.exists() or not report_path.exists():
        raise SystemExit("Stage 1 evidence missing; run Stage 1 first")

    stage1_report = json.loads(report_path.read_text())
    if stage1_report.get("principal_verdict") != "STAGE1_SIGNAL_DEFINITION_FROZEN_OUTCOME_BLIND":
        raise SystemExit("Stage 1 verdict is not eligible for option attachment")
    if stage1_report.get("holdout_evaluated"):
        raise SystemExit("holdout contamination detected")

    signals = pd.read_parquet(signals_path)
    signals["timestamp"] = pd.to_datetime(signals["timestamp"], utc=True, errors="coerce")
    signals = signals.loc[signals["split"].isin(["development", "validation"])].copy()
    signals["option_type"] = np.where(signals["direction"].eq(1), "CE", "PE")

    joint_path = _first_path("repaired_joint_underlying_option_warehouse.parquet")
    cols = [
        "session_date", "event_timestamp", "option_type", "trading_symbol", "strike", "close",
        "premium_mean", "spread_mean", "certified_for_replay", "stale_price_flag",
        "underlying_completed_bar", "underlying_stale_flag",
    ]
    options = pd.read_parquet(joint_path, columns=cols)
    options["event_timestamp"] = pd.to_datetime(options["event_timestamp"], utc=True, errors="coerce")
    options["session"] = pd.to_datetime(options["session_date"], errors="coerce").dt.date.astype(str)
    for col in ["strike", "close", "premium_mean", "spread_mean"]:
        options[col] = pd.to_numeric(options[col], errors="coerce")
    options = options.loc[
        options["certified_for_replay"].fillna(False)
        & ~options["stale_price_flag"].fillna(False)
        & options["underlying_completed_bar"].fillna(False)
        & ~options["underlying_stale_flag"].fillna(False)
        & options["premium_mean"].gt(0)
        & options["event_timestamp"].notna()
        & options["option_type"].isin(["CE", "PE"])
    ].copy()
    options = options.sort_values(["session", "option_type", "event_timestamp", "trading_symbol"])

    grouped = {(s, o): g.reset_index(drop=True) for (s, o), g in options.groupby(["session", "option_type"], sort=False)}
    trades: list[dict] = []

    for signal in signals.itertuples(index=False):
        key = (str(signal.session), str(signal.option_type))
        day = grouped.get(key)
        if day is None or day.empty:
            continue
        later = day.loc[day["event_timestamp"] > signal.timestamp]
        if later.empty:
            continue
        entry_time = later["event_timestamp"].min()
        entry_slice = later.loc[later["event_timestamp"].eq(entry_time)].copy()
        entry_slice["moneyness"] = (entry_slice["strike"] - entry_slice["close"]).abs()
        entry_slice = entry_slice.sort_values(["moneyness", "spread_mean", "trading_symbol"], na_position="last")
        entry = entry_slice.iloc[0]
        symbol_rows = day.loc[
            day["trading_symbol"].eq(entry["trading_symbol"])
            & day["event_timestamp"].ge(entry_time)
        ].sort_values("event_timestamp")
        if symbol_rows.empty:
            continue

        entry_premium = float(entry["premium_mean"])
        entry_spread = float(entry["spread_mean"]) if pd.notna(entry["spread_mean"]) else 0.0
        friction_pct = FIXED_ROUND_TRIP_FRICTION_PCT + max(entry_spread, 0.0) / entry_premium
        record = {
            "session": str(signal.session),
            "signal_timestamp": signal.timestamp,
            "entry_timestamp": entry_time,
            "split": str(signal.split),
            "group": int(signal.group),
            "direction": int(signal.direction),
            "option_type": str(signal.option_type),
            "trading_symbol": str(entry["trading_symbol"]),
            "strike": float(entry["strike"]),
            "underlying_close": float(entry["close"]),
            "entry_premium": entry_premium,
            "entry_spread": entry_spread,
            "friction_pct": friction_pct,
        }
        for horizon in HORIZONS_MINUTES:
            target = entry_time + pd.Timedelta(minutes=horizon)
            exits = symbol_rows.loc[symbol_rows["event_timestamp"] >= target]
            if exits.empty:
                record[f"net_return_{horizon}m"] = np.nan
                record[f"exit_timestamp_{horizon}m"] = pd.NaT
                continue
            exit_row = exits.iloc[0]
            gross = float(exit_row["premium_mean"]) / entry_premium - 1.0
            record[f"net_return_{horizon}m"] = gross - friction_pct
            record[f"exit_timestamp_{horizon}m"] = exit_row["event_timestamp"]
        trades.append(record)

    trade_frame = pd.DataFrame(trades)
    if trade_frame.empty:
        raise SystemExit("no certified option outcomes attached")

    development_metrics = {}
    for horizon in HORIZONS_MINUTES:
        col = f"net_return_{horizon}m"
        development_metrics[str(horizon)] = _summary(trade_frame.loc[trade_frame["split"].eq("development")], col)

    eligible = [
        (h, development_metrics[str(h)])
        for h in HORIZONS_MINUTES
        if development_metrics[str(h)]["trades"] >= MIN_DEVELOPMENT_TRADES
    ]
    if not eligible:
        selected_horizon = None
        validation_metrics = {"trades": 0, "mean": float("nan"), "median": float("nan"), "win_rate": float("nan")}
        verdict = "INSUFFICIENT_DEVELOPMENT_OPTION_TRADES"
    else:
        selected_horizon = max(eligible, key=lambda item: (item[1]["mean"], item[1]["median"]))[0]
        selected_col = f"net_return_{selected_horizon}m"
        validation_metrics = _summary(trade_frame.loc[trade_frame["split"].eq("validation")], selected_col)
        development_selected = development_metrics[str(selected_horizon)]
        passes = (
            development_selected["mean"] > 0
            and validation_metrics["trades"] >= MIN_VALIDATION_TRADES
            and validation_metrics["mean"] > 0
            and validation_metrics["median"] > -0.005
        )
        verdict = "VALIDATION_EDGE_CANDIDATE" if passes else "NO_VALIDATED_EDGE"

    OUT.mkdir(parents=True, exist_ok=True)
    trade_frame.to_parquet(OUT / "attached_option_trades.parquet", index=False)
    report = {
        "schema_version": 1,
        "research_only": True,
        "allowed_for_live_execution": False,
        "stage1_verdict": stage1_report["principal_verdict"],
        "holdout_evaluated": False,
        "holdout_sessions_sealed": stage1_report["holdout_sessions_sealed"],
        "signals_input": int(len(signals)),
        "option_trades_attached": int(len(trade_frame)),
        "entry_rule": "first certified option timestamp strictly after signal; nearest strike by absolute moneyness",
        "fixed_round_trip_friction_pct": FIXED_ROUND_TRIP_FRICTION_PCT,
        "additional_spread_cost": "entry spread divided by entry premium",
        "development_metrics_by_horizon": development_metrics,
        "selected_horizon_minutes": selected_horizon,
        "validation_metrics": validation_metrics,
        "principal_verdict": verdict,
        "next_stage": "negative controls and sealed holdout only if validation edge candidate" if verdict == "VALIDATION_EDGE_CANDIDATE" else "reject information migration candidate in tested form",
    }
    (OUT / "stage2_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
