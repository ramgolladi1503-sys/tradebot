#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
SEED = 20260804
FAMILIES = (
    "SOURCE_TREND_SLOPE",
    "SOURCE_TREND_ACCEL_STRICT",
    "SOURCE_MIDLINE",
    "SOURCE_BANDS_RECLAIM",
)
CENTRE_MODES = ("TRUE_VWMA", "UNIFORM_VOLUME_SMA", "EMA_SENSITIVITY")


@dataclass(frozen=True)
class SourceModeSpec:
    centre_length: int = 20
    atr_length: int = 14
    escape_distance_atr: float = 1.5
    band_width_atr: float = 1.5
    max_hold_bars: int = 6
    bar_minutes: int = 5
    primary_cost_bps: float = 2.0
    severe_cost_bps: float = 5.0
    centre_mode: str = "TRUE_VWMA"


def _true_range(frame: pd.DataFrame) -> pd.Series:
    previous = frame["close"].shift(1)
    return pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous).abs(),
            (frame["low"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)


def _vwma(close: pd.Series, volume: pd.Series, length: int) -> pd.Series:
    numeric_volume = pd.to_numeric(volume, errors="coerce").fillna(0.0)
    if not (numeric_volume > 0).any():
        raise ValueError("true_vwma_requires_positive_volume")
    denominator = numeric_volume.rolling(length, min_periods=length).sum()
    numerator = (close * numeric_volume).rolling(length, min_periods=length).sum()
    return numerator / denominator.replace(0.0, np.nan)


def add_source_indicators(df: pd.DataFrame, spec: SourceModeSpec) -> pd.DataFrame:
    """Build causal indicators for the published-description signal modes.

    TRUE_VWMA is the authoritative lane. The SMA and EMA lanes are explicitly
    diagnostic proxies and must never be represented as exact source-code replicas.
    """
    required = {"timestamp", "session", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing_columns={sorted(missing)}")
    if spec.centre_mode not in CENTRE_MODES:
        raise ValueError(f"unsupported_centre_mode={spec.centre_mode}")

    frame = df.copy().sort_values("timestamp").reset_index(drop=True)
    frame["atr"] = _true_range(frame).ewm(
        alpha=1.0 / spec.atr_length,
        adjust=False,
        min_periods=spec.atr_length,
    ).mean()

    if spec.centre_mode == "TRUE_VWMA":
        if "volume" not in frame.columns:
            raise ValueError("true_vwma_requires_volume_column")
        frame["centre"] = _vwma(frame["close"], frame["volume"], spec.centre_length)
    elif spec.centre_mode == "UNIFORM_VOLUME_SMA":
        frame["centre"] = frame["close"].rolling(
            spec.centre_length,
            min_periods=spec.centre_length,
        ).mean()
    else:
        frame["centre"] = frame["close"].ewm(
            span=spec.centre_length,
            adjust=False,
            min_periods=spec.centre_length,
        ).mean()

    frame["centre_slope"] = frame["centre"].diff()
    frame["centre_accel"] = frame["centre_slope"].diff()
    frame["escape_upper"] = frame["centre"] + spec.escape_distance_atr * frame["atr"]
    frame["escape_lower"] = frame["centre"] - spec.escape_distance_atr * frame["atr"]
    frame["outer_upper"] = frame["centre"] + spec.band_width_atr * frame["atr"]
    frame["outer_lower"] = frame["centre"] - spec.band_width_atr * frame["atr"]
    frame["inner_upper"] = frame["centre"] + 0.5 * spec.band_width_atr * frame["atr"]
    frame["inner_lower"] = frame["centre"] - 0.5 * spec.band_width_atr * frame["atr"]
    frame["displacement_atr"] = (
        (frame["close"] - frame["centre"]) / frame["atr"].replace(0.0, np.nan)
    )
    return frame


def signals_for_frame(frame: pd.DataFrame, family: str) -> list[tuple[int, str]]:
    """Return completed-bar state flips with state preserved across sessions."""
    if family not in FAMILIES:
        raise ValueError(f"unsupported_family={family}")

    close = frame["close"].to_numpy(float)
    centre = frame["centre"].to_numpy(float)
    slope = frame["centre_slope"].to_numpy(float)
    accel = frame["centre_accel"].to_numpy(float)
    escape_upper = frame["escape_upper"].to_numpy(float)
    escape_lower = frame["escape_lower"].to_numpy(float)
    outer_upper = frame["outer_upper"].to_numpy(float)
    outer_lower = frame["outer_lower"].to_numpy(float)

    signals: list[tuple[int, str]] = []
    state = 0
    initialized = False
    for index in range(1, len(frame)):
        values = (
            close[index], centre[index], slope[index], accel[index],
            escape_upper[index], escape_lower[index], outer_upper[index], outer_lower[index],
            close[index - 1], centre[index - 1], outer_upper[index - 1], outer_lower[index - 1],
        )
        if not all(math.isfinite(value) for value in values):
            continue

        candidate = state
        if family == "SOURCE_TREND_SLOPE":
            if close[index] > escape_upper[index] and slope[index] > 0:
                candidate = 1
            elif close[index] < escape_lower[index] and slope[index] < 0:
                candidate = -1
        elif family == "SOURCE_TREND_ACCEL_STRICT":
            if close[index] > escape_upper[index] and slope[index] > 0 and accel[index] >= 0:
                candidate = 1
            elif close[index] < escape_lower[index] and slope[index] < 0 and accel[index] <= 0:
                candidate = -1
        elif family == "SOURCE_MIDLINE":
            if close[index] > centre[index]:
                candidate = 1
            elif close[index] < centre[index]:
                candidate = -1
        else:
            crossed_above_lowest = (
                close[index - 1] <= outer_lower[index - 1]
                and close[index] > outer_lower[index]
            )
            crossed_below_highest = (
                close[index - 1] >= outer_upper[index - 1]
                and close[index] < outer_upper[index]
            )
            if crossed_above_lowest:
                candidate = 1
            elif crossed_below_highest:
                candidate = -1

        if not initialized:
            state = candidate
            initialized = True
            continue
        if candidate != state and candidate in (-1, 1):
            signals.append((index, "LONG" if candidate == 1 else "SHORT"))
            state = candidate
    return signals


def _event_record(
    frame: pd.DataFrame,
    family: str,
    side: str,
    signal_index: int,
    entry_index: int,
    exit_index: int,
    exit_price: float,
    exit_timestamp: pd.Timestamp,
    exit_kind: str,
    spec: SourceModeSpec,
) -> dict:
    signal = frame.iloc[signal_index]
    entry = frame.iloc[entry_index]
    sign = 1.0 if side == "LONG" else -1.0
    gross_bps = sign * (exit_price - float(entry.open)) / float(entry.open) * 10000.0
    true_volume = spec.centre_mode == "TRUE_VWMA"
    return {
        "event_id": hashlib.sha256(
            f"{family}|{side}|{signal.session}|{signal.timestamp.isoformat()}|{spec.centre_mode}".encode()
        ).hexdigest()[:20],
        "family": family,
        "side": side,
        "session": str(signal.session),
        "signal_timestamp": pd.Timestamp(signal.timestamp).isoformat(),
        "entry_timestamp": pd.Timestamp(entry.timestamp).isoformat(),
        "exit_timestamp": pd.Timestamp(exit_timestamp).isoformat(),
        "entry": float(entry.open),
        "exit": float(exit_price),
        "exit_kind": exit_kind,
        "hold_bars": int(exit_index - entry_index + 1),
        "gross_bps": float(gross_bps),
        "net2_bps": float(gross_bps - spec.primary_cost_bps),
        "net5_bps": float(gross_bps - spec.severe_cost_bps),
        "signal_close": float(signal.close),
        "centre": float(signal.centre),
        "atr": float(signal.atr),
        "centre_slope": float(signal.centre_slope),
        "centre_accel": float(signal.centre_accel),
        "displacement_atr": float(signal.displacement_atr),
        "centre_mode": spec.centre_mode,
        "volume_weighting_available": true_volume,
        "published_description_semantics_reproduced": True,
        "exact_source_code_replication": False,
        "authority": "TRUE_VWMA_SOURCE_MODE" if true_volume else "PRICE_ONLY_PROXY_DIAGNOSTIC",
    }


def generate_source_mode_events(df: pd.DataFrame, spec: SourceModeSpec) -> pd.DataFrame:
    """Generate source-description flips and enforce next-bar, same-session outcomes."""
    frame = df.sort_values("timestamp").reset_index(drop=True)
    session_last_index = {
        session: int(indices[-1])
        for session, indices in frame.groupby("session", sort=False).indices.items()
    }
    rows: list[dict] = []

    for family in FAMILIES:
        signals = signals_for_frame(frame, family)
        for position, (signal_index, side) in enumerate(signals):
            entry_index = signal_index + 1
            if entry_index >= len(frame):
                continue
            signal_session = str(frame.iloc[signal_index].session)
            if str(frame.iloc[entry_index].session) != signal_session:
                continue

            last_index = session_last_index[frame.iloc[entry_index].session]
            fixed_exit_index = min(entry_index + spec.max_hold_bars - 1, last_index)
            next_flip_entry_index = (
                signals[position + 1][0] + 1 if position + 1 < len(signals) else len(frame)
            )
            next_flip_same_session = (
                next_flip_entry_index < len(frame)
                and str(frame.iloc[next_flip_entry_index].session) == signal_session
            )
            if next_flip_same_session and next_flip_entry_index <= fixed_exit_index:
                exit_index = next_flip_entry_index
                exit_price = float(frame.iloc[exit_index].open)
                exit_timestamp = pd.Timestamp(frame.iloc[exit_index].timestamp)
                exit_kind = "NEXT_OPPOSITE_ENTRY_OPEN"
            else:
                exit_index = fixed_exit_index
                exit_price = float(frame.iloc[exit_index].close)
                exit_timestamp = pd.Timestamp(frame.iloc[exit_index].timestamp) + pd.Timedelta(
                    minutes=spec.bar_minutes
                )
                exit_kind = "MAX_HOLD_OR_EOD_CLOSE"

            rows.append(
                _event_record(
                    frame, family, side, signal_index, entry_index, exit_index,
                    exit_price, exit_timestamp, exit_kind, spec,
                )
            )
    return pd.DataFrame(rows)


def _profit_factor(values: np.ndarray) -> float | None:
    gains = values[values > 0].sum()
    losses = values[values <= 0].sum()
    return float(gains / abs(losses)) if gains > 0 and losses < 0 else None


def _session_ci(df: pd.DataFrame, column: str, replications: int = 2000) -> list[float]:
    values = df.groupby("session")[column].mean().dropna().to_numpy(float)
    if len(values) == 0:
        return [math.nan, math.nan]
    if len(values) == 1:
        return [float(values[0]), float(values[0])]
    rng = np.random.default_rng(SEED)
    means = rng.choice(values, size=(replications, len(values)), replace=True).mean(axis=1)
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def metrics(df: pd.DataFrame, column: str = "net2_bps") -> dict:
    sample = df.dropna(subset=[column]).copy()
    if sample.empty:
        return {"trade_count": 0, "session_count": 0}
    values = sample[column].to_numpy(float)
    sorted_values = np.sort(values)
    without_top5 = sorted_values[:-5] if len(values) > 5 else np.array([])
    session_pnl = sample.groupby("session")[column].sum().sort_values(ascending=False)
    without_top_sessions = sample.loc[
        ~sample.session.isin(set(session_pnl.head(2).index)), column
    ].to_numpy(float)
    return {
        "trade_count": int(len(sample)),
        "session_count": int(sample.session.nunique()),
        "long_count": int((sample.side == "LONG").sum()),
        "short_count": int((sample.side == "SHORT").sum()),
        "expectancy_bps": float(values.mean()),
        "median_bps": float(np.median(values)),
        "win_rate": float((values > 0).mean()),
        "profit_factor": _profit_factor(values),
        "bootstrap_95pct": _session_ci(sample, column),
        "expectancy_after_remove_top5": float(without_top5.mean()) if len(without_top5) else None,
        "expectancy_after_remove_top2_sessions": (
            float(without_top_sessions.mean()) if len(without_top_sessions) else None
        ),
    }


def _read_input(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    elif path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        raise ValueError(f"unsupported_input={path}")
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], utc=True, errors="raise"
    ).dt.tz_convert(IST)
    if "session" not in frame:
        frame["session"] = frame["timestamp"].dt.date.astype(str)
    return frame


def _available_modes(source: pd.DataFrame) -> tuple[str, ...]:
    volume = pd.to_numeric(
        source.get("volume", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0.0)
    if len(volume) == len(source) and (volume > 0).any():
        return ("TRUE_VWMA", "UNIFORM_VOLUME_SMA", "EMA_SENSITIVITY")
    return ("UNIFORM_VOLUME_SMA", "EMA_SENSITIVITY")


def run_study(source: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    sessions = sorted(source.session.astype(str).unique())
    development_end = int(len(sessions) * 0.6)
    validation_end = int(len(sessions) * 0.8)
    development = sessions[:development_end]
    validation = sessions[development_end:validation_end]
    holdout = sessions[validation_end:]
    split = {session: "development" for session in development}
    split.update({session: "validation" for session in validation})
    split.update({session: "holdout_sealed" for session in holdout})
    research = source[source.session.astype(str).isin(development + validation)].copy()

    ledgers: list[pd.DataFrame] = []
    results: dict[str, dict] = {}
    for mode in _available_modes(source):
        spec = SourceModeSpec(centre_mode=mode)
        events = generate_source_mode_events(add_source_indicators(research, spec), spec)
        events["split"] = events.session.map(split)
        ledgers.append(events)
        results[mode] = {}
        for family in FAMILIES:
            results[mode][family] = {
                "development_net2": metrics(
                    events[(events.family == family) & (events.split == "development")]
                ),
                "validation_net2": metrics(
                    events[(events.family == family) & (events.split == "validation")]
                ),
                "validation_net5": metrics(
                    events[(events.family == family) & (events.split == "validation")],
                    "net5_bps",
                ),
            }

    ledger = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()
    report = {
        "study_id": "gravity_well_published_description_modes_v2",
        "source_page": "https://www.tradingview.com/script/H80GVoRt-Gravity-Well-Trend-Lyro-RS/",
        "spec": asdict(SourceModeSpec()),
        "centre_modes_executed": list(_available_modes(source)),
        "session_counts": {
            "total": len(sessions),
            "development": len(development),
            "validation": len(validation),
            "holdout_sealed": len(holdout),
        },
        "claim_boundary": {
            "published_description_semantics_reproduced": True,
            "exact_source_code_replication": False,
            "true_vwma_executed": "TRUE_VWMA" in _available_modes(source),
            "real_option_evidence_available": False,
            "holdout_opened": False,
            "state_preserved_across_sessions": True,
            "outcomes_forced_same_session": True,
        },
        "results": results,
        "verdict": "NO_VALIDATION_SURVIVOR_IN_EXECUTED_CENTRE_MODES",
    }
    return ledger, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source = _read_input(args.input)
    ledger, report = run_study(source)
    ledger.to_csv(args.output_dir / "source_mode_event_ledger.csv", index=False)
    (args.output_dir / "source_mode_audit.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
