from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_all_strategies_available_data import (  # noqa: E402
    COST_BPS,
    EXIT_HORIZONS,
    TRADEABLE_INSTRUMENTS,
    _extract_signals,
    _market_row,
    _max_drawdown,
    _prepare_frames,
    _profit_factor,
    _run_movement_strategy,
    _run_pairs_strategy,
    _strategy_context,
    discover_strategy_specs,
    inspect_dataset,
    load_dataset,
)


FINAL_VERDICT = "DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST"
BASELINE_HORIZON = 15
BASELINE_COST = 2.0
FULL_PROXY_VERDICT = "FULL_PROXY_ANALYSIS"
PARTIAL_PROXY_VERDICT = "PARTIAL_PROXY_ANALYSIS"
STATE_FILE = "analysis_state.json"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _read_market_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported raw market dataset for proxy analysis: {path}")


def _normalize_ohlc(frame: pd.DataFrame, fallback_symbol: str = "") -> pd.DataFrame:
    data = frame.copy()
    lower = {str(col).lower(): str(col) for col in data.columns}
    rename = {}
    for canonical in ("date", "timestamp", "datetime", "time"):
        if canonical in lower:
            rename[lower[canonical]] = "date"
            break
    for canonical in ("open", "high", "low", "close", "volume", "instrument", "symbol"):
        if canonical in lower:
            target = "instrument" if canonical == "symbol" else canonical
            rename[lower[canonical]] = target
    data = data.rename(columns=rename)
    if "date" not in data.columns:
        raise ValueError("missing date/timestamp column")
    for col in ("open", "high", "low", "close"):
        if col not in data.columns:
            raise ValueError(f"missing OHLC column: {col}")
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if "volume" not in data.columns:
        data["volume"] = 0
    if "instrument" not in data.columns:
        data["instrument"] = fallback_symbol or "UNKNOWN"
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", "open", "high", "low", "close"]).copy()
    return data[["date", "open", "high", "low", "close", "volume", "instrument"]]


def _path_date(path: str, date_min: str) -> str:
    if date_min:
        try:
            return pd.Timestamp(date_min).date().isoformat()
        except Exception:
            pass
    return ""


def _signal_spam_flag(group: pd.DataFrame, candle_count: int) -> str:
    if group.empty:
        return ""
    if candle_count and len(group) / candle_count > 0.5:
        return "SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES"
    if len(group) > 100:
        return "SIGNAL_SPAM_RISK:MORE_THAN_100_SIGNALS_PER_DATASET"
    ordered = group.sort_values("timestamp")
    run = 0
    previous = None
    for side in ordered["side"]:
        if side == previous:
            run += 1
            if run >= 5:
                return "SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION"
        else:
            run = 1
            previous = side
    return ""


def _proxy_rows(signals: list[Any], frames: Mapping[str, pd.DataFrame], dataset_path: str, dataset_date: str) -> list[dict[str, Any]]:
    idx_by = {
        instrument: {pd.Timestamp(row.date).isoformat(): int(idx) for idx, row in frame.iterrows()}
        for instrument, frame in frames.items()
    }
    rows: list[dict[str, Any]] = []
    for signal in signals:
        if signal.instrument not in frames:
            continue
        frame = frames[signal.instrument]
        idx = idx_by[signal.instrument].get(signal.timestamp)
        if idx is None:
            continue
        entry_idx = idx + 1
        if entry_idx >= len(frame):
            continue
        entry = float(frame.loc[entry_idx, "open"])
        for horizon in EXIT_HORIZONS:
            exit_idx = entry_idx + int(horizon)
            if exit_idx >= len(frame) or entry_idx >= exit_idx:
                continue
            exit_price = float(frame.loc[exit_idx, "close"])
            gross_bps = ((exit_price / entry) - 1.0) * 10000.0 * int(signal.side)
            for cost in COST_BPS:
                net_bps = gross_bps - float(cost)
                rows.append(
                    {
                        "strategy": signal.strategy,
                        "dataset_path": dataset_path,
                        "date": dataset_date,
                        "instrument": signal.instrument,
                        "timestamp": signal.timestamp,
                        "entry_timestamp": pd.Timestamp(frame.loc[entry_idx, "date"]).isoformat(),
                        "exit_timestamp": pd.Timestamp(frame.loc[exit_idx, "date"]).isoformat(),
                        "direction": signal.direction,
                        "side": "LONG" if signal.side > 0 else "SHORT",
                        "exit_horizon_min": int(horizon),
                        "cost_bps": float(cost),
                        "entry_underlying": entry,
                        "exit_underlying": exit_price,
                        "gross_bps": gross_bps,
                        "net_bps": net_bps,
                        "net_points": entry * net_bps / 10000.0,
                        "win": bool(net_bps > 0),
                        "executable": False,
                    }
                )
    return rows


def _run_strategy_signals(spec: Any, frames: Mapping[str, pd.DataFrame], errors: list[dict[str, Any]], dataset_path: str) -> list[Any]:
    signals: list[Any] = []
    for instrument in TRADEABLE_INSTRUMENTS:
        if instrument not in frames:
            continue
        frame = frames[instrument]
        warmup = 30 if len(frame) > 70 else 0
        for idx in range(warmup, max(warmup, len(frame) - max(EXIT_HORIZONS) - 1)):
            market = _market_row(frames, instrument, idx)
            try:
                if spec.strategy.startswith("movement."):
                    result = _run_movement_strategy(spec, market)
                elif spec.runner is not None:
                    result = spec.runner(market)
                else:
                    result = None
                signals.extend(_extract_signals(spec, market, result))
            except Exception as exc:
                errors.append(
                    {
                        "strategy": spec.strategy,
                        "dataset_path": dataset_path,
                        "error": repr(exc),
                        "traceback": traceback.format_exc(limit=4),
                    }
                )
    if spec.strategy == "pairs_arbitrage.generate_signal" and "NIFTY" in frames and "BANKNIFTY" in frames:
        n = min(len(frames["NIFTY"]), len(frames["BANKNIFTY"]))
        for idx in range(30, max(30, n - max(EXIT_HORIZONS) - 1)):
            try:
                signals.extend(_run_pairs_strategy(frames, idx))
            except Exception as exc:
                errors.append({"strategy": spec.strategy, "dataset_path": dataset_path, "error": repr(exc), "traceback": traceback.format_exc(limit=4)})
    return signals


def _summary_from_trades(trades: pd.DataFrame, signals: pd.DataFrame, candle_count: int) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in trades.groupby(["strategy", "dataset_path", "date", "exit_horizon_min", "cost_bps"], dropna=False):
        strategy, dataset_path, date, horizon, cost = keys
        net_points = group["net_points"].astype(float)
        net_bps = group["net_bps"].astype(float)
        signal_group = signals[(signals["strategy"] == strategy) & (signals["dataset_path"] == dataset_path)] if not signals.empty else pd.DataFrame()
        rows.append(
            {
                "strategy": strategy,
                "dataset_path": dataset_path,
                "dataset_type": "INDEX_OHLC",
                "date_range": date,
                "instruments": "|".join(sorted(group["instrument"].dropna().astype(str).unique())),
                "capability_bucket": "DIRECTIONAL_PROXY_ONLY",
                "analysis_mode": "NEXT_OPEN_UNDERLYING_DIRECTIONAL_PROXY",
                "trades_or_signals": int(len(group)),
                "win_rate": round(float(group["win"].mean()), 6),
                "avg_net_bps": round(float(net_bps.mean()), 6),
                "total_net_points": round(float(net_points.sum()), 6),
                "profit_factor_proxy": round(_profit_factor(net_points), 6),
                "max_drawdown_proxy": round(_max_drawdown(net_points), 6),
                "long_count": int((group["side"] == "LONG").sum()),
                "short_count": int((group["side"] == "SHORT").sum()),
                "signal_spam_flag": _signal_spam_flag(signal_group, candle_count),
                "volume_invalid_flag": False,
                "option_truth_missing_flag": True,
                "executable_replay_ready": False,
                "verdict": _verdict_for_proxy(group),
                "reason": "underlying index next-open directional proxy; not option PnL",
            }
        )
    return pd.DataFrame(rows)


def _verdict_for_proxy(group: pd.DataFrame) -> str:
    if group.empty:
        return "NO_EDGE_FOUND"
    avg = float(group["net_bps"].mean())
    wins = float(group["win"].mean())
    if avg <= 0:
        return "NO_EDGE_FOUND"
    if float(group["cost_bps"].iloc[0]) >= 10.0 and avg <= 0:
        return "COST_FRAGILE"
    return "ROBUST_DIRECTIONAL_PROXY" if wins >= 0.55 and len(group) >= 30 else "WEAK_DIRECTIONAL_PROXY"


def _fallback_non_executable(row: Mapping[str, Any]) -> bool:
    text = " ".join(str(row.get(col, "")) for col in ("reason", "schema_columns", "path")).lower()
    return any(token in text for token in ("fallback", "advisory", "recovered"))


def _capability_for_catalog_row(row: Mapping[str, Any], strategy: Any) -> tuple[str, str, str, str]:
    dtype = str(row.get("detected_dataset_type", "UNKNOWN"))
    volume_invalid = str(row.get("volume_quality", "")) in {"ZERO_VOLUME", "MISSING_VOLUME"} and bool(getattr(strategy, "vwap_dependent", False) or getattr(strategy, "volume_dependent", False))
    option_missing = not _bool(row.get("has_option_ltp")) and bool(getattr(strategy, "option_specific", False) or getattr(strategy, "uses_option_ltp", False))
    if dtype == "BACKTEST_REPORT":
        return "UNSUPPORTED_DATA", "DERIVED_REPORT_IGNORED", "UNSUPPORTED_DATA", "generated reports are not raw market evidence"
    if dtype == "CANDIDATE_DECISIONS":
        return "SIGNAL_ONLY_ANALYSIS", "SIGNAL_ONLY_ANALYSIS", "SIGNAL_ONLY_ANALYSIS", "candidate decisions without future quote trace"
    if dtype == "RANKING_SNAPSHOTS":
        return "RANKING_BEHAVIOR_ANALYSIS_ONLY", "RANKING_BEHAVIOR_ANALYSIS_ONLY", "RANKING_BEHAVIOR_ANALYSIS_ONLY", "ranking snapshots without quote truth"
    if dtype == "OPTION_OHLC_OR_LTP":
        return "OPTION_LTP_REPLAY_ONLY", "OPTION_LTP_REPLAY_ONLY", "OPTION_LTP_REPLAY_ONLY", "option LTP without bid/ask/depth executable truth"
    if dtype == "OPTION_QUOTE_TRUTH" and _bool(row.get("usable_for_executable_option_replay")) and not _fallback_non_executable(row):
        return "EXECUTABLE_REPLAY_CANDIDATE", "EXECUTABLE_REPLAY_CANDIDATE", "EXECUTABLE_REPLAY_CANDIDATE", "candidate-linked bid/ask/depth truth available"
    if dtype == "INDEX_OHLC":
        if volume_invalid:
            return "INVALID_VOLUME_OR_VWAP_PROXY", "DIRECTIONAL_PROXY_ONLY", "INVALID_VOLUME_OR_VWAP_PROXY", "volume or VWAP input is zero/missing"
        if option_missing:
            return "NOT_EXECUTABLE_OPTION_BACKTEST", "DIRECTIONAL_PROXY_ONLY", "NOT_EXECUTABLE_OPTION_BACKTEST", "option truth missing; directional proxy only"
        return "DIRECTIONAL_PROXY_ONLY", "DIRECTIONAL_PROXY_ONLY", "WEAK_DIRECTIONAL_PROXY", "index OHLC supports only underlying directional proxy"
    if dtype in {"STRATEGY_SIGNAL_TRACE", "LIVE_LOG"}:
        return "SIGNAL_ONLY_ANALYSIS", "SIGNAL_ONLY_ANALYSIS", "SIGNAL_ONLY_ANALYSIS", "signals/logs without future quote trace"
    return "UNSUPPORTED_DATA", "UNSUPPORTED_DATA", "UNSUPPORTED_DATA", str(row.get("reason", "unsupported data"))


def analyze_catalog(
    *,
    catalog_path: Path,
    out_dir: Path,
    max_proxy_datasets: int | None = None,
    batch_size: int | None = None,
    resume: int = 0,
    only_dataset_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    instrument: str | None = None,
    selection_strategy: str = "all",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = pd.read_csv(catalog_path)
    specs = discover_strategy_specs()
    by_dataset_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    proxy_executed = 0
    proxy_available = 0
    selected_paths: list[str] = []
    skipped_paths: list[str] = []
    state = _load_state(out_dir)
    processed_fingerprints: set[str] = set(state.get("processed_fingerprints", [])) if resume else set()

    eligible = catalog.copy()
    if "eligible_as_raw_market_input" in eligible.columns:
        eligible = eligible[eligible["eligible_as_raw_market_input"].astype(str).str.lower().isin({"true", "1"})]
    if "is_duplicate" in eligible.columns:
        eligible = eligible[eligible["is_duplicate"].astype(str).str.lower().isin({"false", "0", ""})]
    if only_dataset_type:
        eligible = eligible[eligible["detected_dataset_type"] == only_dataset_type]
    if from_date and "date_max" in eligible.columns:
        eligible = eligible[pd.to_datetime(eligible["date_max"], errors="coerce") >= pd.Timestamp(from_date)]
    if to_date and "date_min" in eligible.columns:
        eligible = eligible[pd.to_datetime(eligible["date_min"], errors="coerce") <= pd.Timestamp(to_date)]
    if instrument:
        eligible = eligible[eligible["instruments_symbols"].astype(str).str.contains(instrument, na=False)]
    eligible = eligible[eligible["detected_dataset_type"] == "INDEX_OHLC"].copy()
    eligible = eligible.sort_values(["date_min", "path"], ascending=[True, True]).reset_index(drop=True)
    proxy_available = int(len(eligible))

    if processed_fingerprints:
        eligible = eligible[~eligible["dataset_fingerprint"].astype(str).isin(processed_fingerprints)].copy()

    if selection_strategy == "all":
        selected = eligible
    elif selection_strategy == "newest":
        selected = eligible.sort_values(["date_min", "path"], ascending=[False, False])
    elif selection_strategy == "oldest":
        selected = eligible.sort_values(["date_min", "path"], ascending=[True, True])
    elif selection_strategy == "stratified_by_date":
        selected = eligible.drop_duplicates(subset=["date_min"], keep="first")
    elif selection_strategy == "explicit_paths":
        selected = eligible
    else:
        selected = eligible

    if batch_size is not None and batch_size >= 0:
        selected = selected.iloc[: int(batch_size)].copy()
    if max_proxy_datasets is not None and max_proxy_datasets >= 0:
        selected = selected.iloc[: int(max_proxy_datasets)].copy()

    selected_paths = selected["path"].astype(str).tolist()
    skipped_paths = [str(p) for p in eligible["path"].astype(str).tolist() if str(p) not in set(selected_paths)]

    selected_set = set(selected_paths)
    for _, catalog_row in catalog.iterrows():
        row = catalog_row.to_dict()
        dataset_path = str(row.get("path", ""))
        dtype = str(row.get("detected_dataset_type", "UNKNOWN"))
        if dataset_path in selected_set and dtype == "INDEX_OHLC" and _bool(row.get("usable_for_directional_proxy")):
            proxy_executed += 1
            try:
                raw = _read_market_dataset(Path(dataset_path))
                data = _normalize_ohlc(raw, fallback_symbol=Path(dataset_path).stem.split("_")[0])
                inspection = inspect_dataset(data)
                frames = _prepare_frames(data)
                candle_count = int(sum(len(frame) for frame in frames.values()))
                dataset_date = _path_date(dataset_path, str(row.get("date_min", "")))
                signal_records: list[dict[str, Any]] = []
                trade_records: list[dict[str, Any]] = []
                directional_specs: set[str] = set()
                for spec in specs:
                    cap, mode, preliminary_verdict, reason = _capability_for_catalog_row(row, spec)
                    if cap != "DIRECTIONAL_PROXY_ONLY":
                        by_dataset_rows.append(_empty_result(row, spec, cap, mode, preliminary_verdict, reason))
                        continue
                    directional_specs.add(spec.strategy)
                    signals = _run_strategy_signals(spec, frames, errors, dataset_path)
                    signal_records.extend(
                        {
                            "strategy": signal.strategy,
                            "dataset_path": dataset_path,
                            "timestamp": signal.timestamp,
                            "instrument": signal.instrument,
                            "side": signal.side,
                        }
                        for signal in signals
                    )
                    trade_records.extend(_proxy_rows(signals, frames, dataset_path, dataset_date))
                trades = pd.DataFrame(trade_records)
                signal_frame = pd.DataFrame(signal_records)
                summary = _summary_from_trades(trades, signal_frame, candle_count)
                if not summary.empty and {"exit_horizon_min", "cost_bps", "strategy"}.issubset(summary.columns):
                    baseline = summary[(summary["exit_horizon_min"] == BASELINE_HORIZON) & (summary["cost_bps"] == BASELINE_COST)]
                    by_dataset_rows.extend(baseline.to_dict("records"))
                produced = set(summary["strategy"].unique()) if not summary.empty and "strategy" in summary.columns else set()
                for spec in specs:
                    if spec.strategy in directional_specs and spec.strategy not in produced:
                        cap, mode, verdict, reason = _capability_for_catalog_row(row, spec)
                        by_dataset_rows.append(_empty_result(row, spec, cap, mode, verdict if cap != "DIRECTIONAL_PROXY_ONLY" else "NO_EDGE_FOUND", reason))
                state.setdefault("processed_fingerprints", []).append(str(row.get("dataset_fingerprint", "")))
            except Exception as exc:
                errors.append({"dataset_path": dataset_path, "strategy": "*", "error": repr(exc), "traceback": traceback.format_exc(limit=5)})
                for spec in specs:
                    by_dataset_rows.append(_empty_result(row, spec, "ERROR", "ERROR", "ERROR", repr(exc)))
            continue
        for spec in specs:
            cap, mode, verdict, reason = _capability_for_catalog_row(row, spec)
            if cap == "DIRECTIONAL_PROXY_ONLY":
                if dataset_path in selected_set:
                    by_dataset_rows.append(_empty_result(row, spec, cap, mode, verdict, reason))
                else:
                    by_dataset_rows.append(_empty_result(row, spec, "DIRECTIONAL_PROXY_CATALOG_ONLY", "CATALOG_ONLY_NO_EDGE_ANALYSIS", "CATALOG_ONLY_NO_EDGE_ANALYSIS", "eligible raw dataset excluded from selection"))
            else:
                by_dataset_rows.append(_empty_result(row, spec, cap, mode, verdict, reason))

    by_dataset = pd.DataFrame(by_dataset_rows)
    by_dataset = _merge_with_existing(by_dataset, out_dir / "full_strategy_proxy_by_dataset.csv", key_cols=["dataset_fingerprint", "strategy", "dataset_path", "exit_horizon_min", "cost_bps", "analysis_mode", "capability_bucket", "verdict"])
    by_strategy = _aggregate_by_strategy(by_dataset)
    summary = _overall_summary(by_dataset)
    errors_df = pd.DataFrame(errors, columns=["dataset_path", "strategy", "error", "traceback"])
    _write_outputs(by_dataset, by_strategy, summary, errors_df, out_dir)
    proxy_skipped = max(proxy_available - len(selected_paths), 0)
    payload = write_report(
        out_dir=out_dir,
        by_dataset=by_dataset,
        by_strategy=by_strategy,
        errors=errors_df,
        max_proxy_datasets=max_proxy_datasets,
        proxy_executed=proxy_executed,
        proxy_available=proxy_available,
        proxy_skipped=proxy_skipped,
        selected_paths=selected_paths,
        skipped_paths=skipped_paths,
        selection_strategy=selection_strategy,
    )
    _save_state(out_dir, state)
    return payload


def _empty_result(row: Mapping[str, Any], spec: Any, capability: str, mode: str, verdict: str, reason: str) -> dict[str, Any]:
    return {
        "dataset_fingerprint": row.get("dataset_fingerprint", ""),
        "duplicate_group_id": row.get("duplicate_group_id", ""),
        "canonical_dataset_path": row.get("canonical_dataset_path", row.get("path", "")),
        "is_duplicate": bool(row.get("is_duplicate", False)),
        "strategy": spec.strategy,
        "dataset_path": row.get("path", ""),
        "dataset_type": row.get("detected_dataset_type", "UNKNOWN"),
        "date_range": f"{row.get('date_min', '')}..{row.get('date_max', '')}",
        "instruments": row.get("instruments_symbols", ""),
        "capability_bucket": capability,
        "analysis_mode": mode,
        "analysis_confidence": "FULL_MULTI_DATASET_PROXY" if capability in {"DIRECTIONAL_PROXY_ONLY", "EXECUTABLE_REPLAY_CANDIDATE"} else "CATALOG_ONLY_NO_EDGE_ANALYSIS" if capability == "DIRECTIONAL_PROXY_CATALOG_ONLY" else "UNSUPPORTED_DATA",
        "trades_or_signals": 0,
        "win_rate": "",
        "avg_net_bps": "",
        "total_net_points": "",
        "profit_factor_proxy": "",
        "max_drawdown_proxy": "",
        "long_count": 0,
        "short_count": 0,
        "signal_spam_flag": "",
        "volume_invalid_flag": verdict == "INVALID_VOLUME_OR_VWAP_PROXY",
        "option_truth_missing_flag": verdict in {"NOT_EXECUTABLE_OPTION_BACKTEST", "OPTION_LTP_REPLAY_ONLY"},
        "executable_replay_ready": capability == "EXECUTABLE_REPLAY_CANDIDATE" and not _fallback_non_executable(row),
        "verdict": "SIGNAL_ONLY_ANALYSIS" if _fallback_non_executable(row) and capability == "EXECUTABLE_REPLAY_CANDIDATE" else verdict,
        "reason": "fallback/advisory/recovered evidence cannot be executable" if _fallback_non_executable(row) and capability == "EXECUTABLE_REPLAY_CANDIDATE" else reason,
    }


def _merge_with_existing(new: pd.DataFrame, existing_path: Path, key_cols: list[str]) -> pd.DataFrame:
    if existing_path.exists():
        try:
            old = pd.read_csv(existing_path)
        except Exception:
            old = pd.DataFrame()
        if not old.empty:
            combined = pd.concat([old, new], ignore_index=True, sort=False)
            present = [col for col in key_cols if col in combined.columns]
            if present:
                combined = combined.drop_duplicates(subset=present, keep="last")
            return combined
    return new


def _write_outputs(by_dataset: pd.DataFrame, by_strategy: pd.DataFrame, summary: pd.DataFrame, errors_df: pd.DataFrame, out_dir: Path) -> None:
    by_dataset.to_csv(out_dir / "full_strategy_proxy_by_dataset.csv", index=False)
    by_dataset.to_csv(out_dir / "all_available_strategy_edge_by_dataset.csv", index=False)
    by_strategy.to_csv(out_dir / "full_strategy_proxy_by_strategy.csv", index=False)
    by_strategy.to_csv(out_dir / "all_available_strategy_edge_by_strategy.csv", index=False)
    summary.to_csv(out_dir / "full_strategy_proxy_by_date.csv", index=False)
    summary.to_csv(out_dir / "all_available_strategy_edge_summary.csv", index=False)
    errors_df.to_csv(out_dir / "full_strategy_proxy_errors.csv", index=False)
    errors_df.to_csv(out_dir / "all_available_strategy_edge_errors.csv", index=False)
    by_instrument = _aggregate_by_dimension(by_dataset, "instruments")
    by_instrument.to_csv(out_dir / "full_strategy_proxy_by_instrument.csv", index=False)
    by_date = _aggregate_by_dimension(by_dataset, "date_range")
    by_date.to_csv(out_dir / "full_strategy_proxy_by_date.csv", index=False)


def _load_state(out_dir: Path) -> dict[str, Any]:
    path = out_dir / STATE_FILE
    if not path.exists():
        return {"processed_fingerprints": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"processed_fingerprints": []}


def _save_state(out_dir: Path, state: Mapping[str, Any]) -> None:
    path = out_dir / STATE_FILE
    path.write_text(json.dumps(dict(state), indent=2, default=str), encoding="utf-8")


def _aggregate_by_strategy(by_dataset: pd.DataFrame) -> pd.DataFrame:
    if by_dataset.empty:
        return pd.DataFrame()
    rows = []
    for strategy, group in by_dataset.groupby("strategy", dropna=False):
        numeric = pd.to_numeric(group["avg_net_bps"], errors="coerce")
        confidences = set(group["analysis_confidence"].dropna().astype(str).tolist())
        if "UNSUPPORTED_DATA" in confidences:
            strategy_confidence = "UNSUPPORTED_DATA"
        elif "CATALOG_ONLY_NO_EDGE_ANALYSIS" in confidences and len(confidences) == 1:
            strategy_confidence = "CATALOG_ONLY_NO_EDGE_ANALYSIS"
        elif "FULL_MULTI_DATASET_PROXY" in confidences and len(group["dataset_path"].unique()) > 1:
            strategy_confidence = "FULL_MULTI_DATASET_PROXY"
        elif "FULL_MULTI_DATASET_PROXY" in confidences and len(group["dataset_path"].unique()) == 1:
            strategy_confidence = "SINGLE_DAY_PROXY_ONLY"
        else:
            strategy_confidence = "PARTIAL_MULTI_DATASET_PROXY"
        rows.append(
            {
                "strategy": strategy,
                "dataset_count": int(group["dataset_path"].nunique()),
                "analysis_modes": "|".join(sorted(group["analysis_mode"].dropna().astype(str).unique())),
                "analysis_confidence": "|".join(sorted(group["analysis_confidence"].dropna().astype(str).unique())),
                "strategy_result_confidence": strategy_confidence,
                "total_trades_or_signals": int(pd.to_numeric(group["trades_or_signals"], errors="coerce").fillna(0).sum()),
                "mean_avg_net_bps": round(float(numeric.dropna().mean()), 6) if numeric.notna().any() else "",
                "verdicts": "|".join(sorted(group["verdict"].dropna().astype(str).unique())),
                "executable_replay_ready_any": bool(group["executable_replay_ready"].astype(bool).any()),
            }
        )
    return pd.DataFrame(rows)


def _aggregate_by_dimension(by_dataset: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if by_dataset.empty or dimension not in by_dataset.columns:
        return pd.DataFrame()
    rows = []
    for keys, group in by_dataset.groupby(["strategy", dimension], dropna=False):
        strategy, value = keys
        numeric = pd.to_numeric(group["avg_net_bps"], errors="coerce")
        rows.append(
            {
                "strategy": strategy,
                dimension: value,
                "dataset_count": int(group["dataset_path"].nunique()),
                "trades_or_signals": int(pd.to_numeric(group["trades_or_signals"], errors="coerce").fillna(0).sum()),
                "mean_avg_net_bps": round(float(numeric.dropna().mean()), 6) if numeric.notna().any() else "",
                "verdicts": "|".join(sorted(group["verdict"].dropna().astype(str).unique())),
            }
        )
    return pd.DataFrame(rows)


def _overall_summary(by_dataset: pd.DataFrame) -> pd.DataFrame:
    if by_dataset.empty:
        return pd.DataFrame()
    return (
        by_dataset.groupby(["capability_bucket", "analysis_mode", "verdict"], dropna=False)
        .size()
        .reset_index(name="row_count")
        .sort_values(["capability_bucket", "analysis_mode", "verdict"])
    )


def write_report(
    *,
    out_dir: Path,
    by_dataset: pd.DataFrame,
    by_strategy: pd.DataFrame,
    errors: pd.DataFrame,
    max_proxy_datasets: int | None,
    proxy_executed: int,
    proxy_available: int,
    proxy_skipped: int,
    selected_paths: list[str],
    skipped_paths: list[str],
    selection_strategy: str,
) -> dict[str, Any]:
    proxy_verdict = FULL_PROXY_VERDICT if proxy_skipped == 0 else PARTIAL_PROXY_VERDICT
    data_availability_verdict = "HAS_INDEX_OHLC_ONLY"
    payload = {
        "final_verdict": FINAL_VERDICT,
        "data_availability_verdict": data_availability_verdict,
        "proxy_analysis_verdict": proxy_verdict,
        "executable_option_replay_verdict": "NOT_EXECUTABLE_OPTION_BACKTEST",
        "safety": {
            "read_only": True,
            "broker_api_called": False,
            "is_order_action": False,
            "allowed_for_live_execution": False,
            "executable_option_pnl_claim": False,
        },
        "dataset_strategy_rows": int(len(by_dataset)),
        "strategy_count": int(by_strategy["strategy"].nunique()) if not by_strategy.empty else 0,
        "error_count": int(len(errors)),
        "max_proxy_datasets": int(max_proxy_datasets) if max_proxy_datasets is not None else None,
        "selection_strategy": selection_strategy,
        "proxy_datasets_available": int(proxy_available),
        "proxy_datasets_executed": int(proxy_executed),
        "proxy_datasets_analyzed": int(proxy_executed),
        "proxy_datasets_skipped_due_to_cap": int(proxy_skipped),
        "selected_dataset_paths": selected_paths,
        "skipped_dataset_paths": skipped_paths,
        "capability_counts": by_dataset["capability_bucket"].value_counts().to_dict() if not by_dataset.empty else {},
        "verdict_counts": by_dataset["verdict"].value_counts().to_dict() if not by_dataset.empty else {},
    }
    (out_dir / "all_available_strategy_edge_report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    lines = [
        "# All Available Strategy Edge Audit",
        "",
        f"Final verdict: **{FINAL_VERDICT}**",
        "",
        "This is offline evidence analysis only. It does not call broker APIs, place orders, change gates, or claim executable option PnL from index-only data.",
        "",
            "## Capability Counts",
            "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in payload["capability_counts"].items())
    lines.extend(["", "## Verdict Counts", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in payload["verdict_counts"].items())
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- selection_strategy={selection_strategy}",
            f"- max_proxy_datasets={max_proxy_datasets}",
            f"- proxy_datasets_available={proxy_available}",
            f"- proxy_datasets_analyzed={proxy_executed}",
            f"- proxy_datasets_skipped_due_to_cap={proxy_skipped}",
            f"- proxy_datasets_executed={proxy_executed}",
            "- broker_api_called=false",
            "- is_order_action=false",
            "- allowed_for_live_execution=false",
            "- executable_option_pnl_claim=false",
            "",
            "## Non-Negotiable Interpretation",
            "",
            "- Generated reports are treated as derived evidence, not raw market data.",
            "- Index OHLC can only produce directional proxy evidence.",
            "- Option LTP without bid/ask/depth is replay-only, not executable proof.",
            "- Fallback/advisory/recovered evidence remains non-executable.",
        ]
    )
    (out_dir / "all_available_strategy_edge_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze all cataloged offline strategy evidence.")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-proxy-datasets", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--resume", type=int, default=0)
    parser.add_argument("--only-dataset-type", type=str, default=None)
    parser.add_argument("--from-date", type=str, default=None)
    parser.add_argument("--to-date", type=str, default=None)
    parser.add_argument("--instrument", type=str, default=None)
    parser.add_argument("--selection-strategy", type=str, default="all", choices=["all", "newest", "oldest", "stratified_by_date", "explicit_paths"])
    args = parser.parse_args()
    result = analyze_catalog(
        catalog_path=args.catalog,
        out_dir=args.out,
        max_proxy_datasets=args.max_proxy_datasets,
        batch_size=args.batch_size,
        resume=args.resume,
        only_dataset_type=args.only_dataset_type,
        from_date=args.from_date,
        to_date=args.to_date,
        instrument=args.instrument,
        selection_strategy=args.selection_strategy,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
