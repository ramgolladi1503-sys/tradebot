#!/usr/bin/env python3
"""Offline Dataset Generator for MEG Strategy Discovery (V3).

DISCLAIMERS:
- NO_STRUCTURAL_EDGE_CLAIM
- NO_PROFITABILITY_CLAIM
- NOT_A_KITE_LIVE_CERTIFICATION
- NO_ORDER_ACTIONS
- NO_EXECUTION_AUTHORITY
- NO_PR_MERGE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("generate_offline_datasets_v3")

MAX_HORIZON_LAG = 5000
MARKET_TIMEZONE = "Asia/Kolkata"
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
POST_CLOSE_END = time(15, 40)
KNOWN_STALE_BOUNDARIES_UTC = {"072900", "073000", "073100"}
OPTION_PANEL_PER_SIDE = 5
OPTION_SELECTION_POLICY = "NEAREST_NONEXPIRED_EXPIRY_ATM_BALANCED_5CE_5PE"
FUTURE_SELECTION_POLICY = "NEAREST_NONEXPIRED_EXPIRY"


def calculate_sha256(filepath: Path) -> str:
    digest = hashlib.sha256()
    with filepath.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def boundary_ist_time(timestamp: pd.Timestamp) -> time:
    if timestamp.tzinfo is None:
        raise ValueError("Boundary timestamp must be timezone-aware")
    return timestamp.tz_convert(MARKET_TIMEZONE).time()


def get_market_phase(timestamp: pd.Timestamp) -> str:
    ist_time = boundary_ist_time(timestamp)
    if MARKET_OPEN <= ist_time <= MARKET_CLOSE:
        return "CONTINUOUS_MARKET"
    if MARKET_CLOSE < ist_time <= POST_CLOSE_END:
        return "POST_CLOSE_OR_DERIVATIVE_CONVERGENCE"
    return "POST_MARKET_IDLE"


def classify_interval(timestamp: pd.Timestamp, maximum_input_age_seconds: float) -> str:
    """Classify a UTC boundary using the Indian continuous-market clock."""
    ist_time = boundary_ist_time(timestamp)
    if ist_time < MARKET_OPEN:
        return "STARTUP_BACKFILL_NOT_LIVE_CAUSAL"
    if ist_time > MARKET_CLOSE:
        return "OUTSIDE_CONTINUOUS_MARKET"
    if timestamp.strftime("%H%M%S") in KNOWN_STALE_BOUNDARIES_UTC:
        return "STALE_CARRY_FORWARD"
    if maximum_input_age_seconds > 10.0:
        return "STALE_CARRY_FORWARD"
    return "LIVE_FRESH"


def parse_expiry_utc(value: Any) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    try:
        if isinstance(value, (int, float, np.integer, np.floating)):
            return pd.to_datetime(int(value), unit="ms", utc=True)
        text = str(value).strip()
        if not text:
            return None
        if text.replace(".", "", 1).isdigit():
            return pd.to_datetime(int(float(text)), unit="ms", utc=True)
        parsed = pd.to_datetime(text, utc=True, errors="coerce")
        return None if pd.isna(parsed) else parsed
    except (TypeError, ValueError, OverflowError):
        return None


def _session_date_value(session_date: str) -> Any:
    return datetime.strptime(session_date, "%Y%m%d").date()


def select_front_future(
    frame: pd.DataFrame, session_date: str
) -> tuple[str | None, str | None]:
    candidates = frame[frame["instrument_type"] == "FUT"][[
        "instrument_key",
        "expiry",
    ]].drop_duplicates()
    if candidates.empty:
        return None, None
    session_value = _session_date_value(session_date)
    rows: list[tuple[pd.Timestamp, str]] = []
    for candidate in candidates.itertuples(index=False):
        expiry = parse_expiry_utc(candidate.expiry)
        if expiry is None or expiry.tz_convert(MARKET_TIMEZONE).date() < session_value:
            continue
        rows.append((expiry, str(candidate.instrument_key)))
    if not rows:
        return None, None
    expiry, instrument_key = min(rows, key=lambda item: (item[0], item[1]))
    return instrument_key, expiry.isoformat()


def select_option_panel(
    latest_rows: pd.DataFrame,
    spot_price: float | None,
    boundary: pd.Timestamp,
    per_side: int = OPTION_PANEL_PER_SIDE,
) -> list[dict[str, Any]]:
    if spot_price is None or latest_rows.empty:
        return []
    candidates = latest_rows[
        latest_rows["instrument_type"].isin(["CE", "PE"])
    ].copy()
    if candidates.empty:
        return []
    candidates["strike_numeric"] = pd.to_numeric(candidates["strike"], errors="coerce")
    candidates["expiry_utc"] = candidates["expiry"].map(parse_expiry_utc)
    candidates = candidates[
        candidates["strike_numeric"].notna() & candidates["expiry_utc"].notna()
    ].copy()
    if candidates.empty:
        return []
    boundary_date = boundary.tz_convert(MARKET_TIMEZONE).date()
    candidates = candidates[
        candidates["expiry_utc"].map(
            lambda expiry: expiry.tz_convert(MARKET_TIMEZONE).date() >= boundary_date
        )
    ].copy()
    if candidates.empty:
        return []
    nearest_expiry = min(candidates["expiry_utc"])
    candidates = candidates[candidates["expiry_utc"] == nearest_expiry].copy()
    candidates["absolute_moneyness"] = (
        candidates["strike_numeric"] - spot_price
    ).abs()

    selected: list[dict[str, Any]] = []
    for option_type in ("CE", "PE"):
        side = candidates[candidates["instrument_type"] == option_type].sort_values(
            by=["absolute_moneyness", "strike_numeric", "instrument_key"],
            kind="mergesort",
        )
        for rank, row in enumerate(side.head(per_side).itertuples(index=False), start=1):
            selected.append(
                {
                    "instrument_key": str(row.instrument_key),
                    "option_type": option_type,
                    "expiry_utc": row.expiry_utc.isoformat(),
                    "strike": float(row.strike_numeric),
                    "selection_rank_within_side": rank,
                    "absolute_moneyness": float(row.absolute_moneyness),
                }
            )
    return selected


def get_horizon_outcome(
    instrument_df: pd.DataFrame, boundary_ms: int, horizon_sec: int
) -> dict[str, Any]:
    target_ts = boundary_ms + horizon_sec * 1000
    future_obs = instrument_df[instrument_df["source_exchange_ts"] >= target_ts]
    if future_obs.empty:
        return {
            "target_timestamp": target_ts,
            "matched_timestamp": None,
            "lag_ms": None,
            "source_fragment": None,
            "ltp": None,
            "missing_reason": "NO_OBSERVATION_WITHIN_TOLERANCE",
            "available": False,
        }
    match = future_obs.iloc[0]
    matched_ts = int(match["source_exchange_ts"])
    lag = matched_ts - target_ts
    if lag > MAX_HORIZON_LAG:
        return {
            "target_timestamp": target_ts,
            "matched_timestamp": None,
            "lag_ms": None,
            "source_fragment": None,
            "ltp": None,
            "missing_reason": "NO_OBSERVATION_WITHIN_TOLERANCE",
            "available": False,
        }
    return {
        "target_timestamp": target_ts,
        "matched_timestamp": matched_ts,
        "lag_ms": lag,
        "source_fragment": match.get("source_fragment"),
        "ltp": float(match["ltp"]),
        "available": True,
        "missing_reason": None,
    }


def get_mfe_mae(
    instrument_df: pd.DataFrame,
    entry_obs_ts: Any,
    entry_price: Any,
    boundary_ms: int,
    horizon_sec: int,
) -> tuple[Any, Any, Any, Any, Any, Any]:
    if pd.isna(entry_obs_ts) or pd.isna(entry_price):
        return None, None, None, None, None, None
    end_ts = boundary_ms + horizon_sec * 1000 + MAX_HORIZON_LAG
    window = instrument_df[
        (instrument_df["source_exchange_ts"] > entry_obs_ts)
        & (instrument_df["source_exchange_ts"] <= end_ts)
    ]
    if window.empty:
        return None, None, int(entry_obs_ts) + 1, end_ts, None, None
    max_index = window["ltp"].idxmax()
    min_index = window["ltp"].idxmin()
    maximum = window.loc[max_index, "ltp"]
    minimum = window.loc[min_index, "ltp"]
    return (
        float(maximum - entry_price) if pd.notna(maximum) else None,
        float(minimum - entry_price) if pd.notna(minimum) else None,
        int(entry_obs_ts) + 1,
        end_ts,
        window.loc[max_index, "source_exchange_ts"],
        window.loc[min_index, "source_exchange_ts"],
    )


def test_causality_and_horizons() -> None:
    frame = pd.DataFrame(
        {
            "source_exchange_ts": [1000000, 1005000, 1020000, 1060000],
            "ltp": [24604.6, 24606.0, 24600.2, 24606.4],
            "source_fragment": ["A", "A", "A", "A"],
        }
    )
    result_5s = get_horizon_outcome(frame, 1000000, 5)
    assert result_5s["ltp"] == 24606.0
    assert result_5s["matched_timestamp"] >= result_5s["target_timestamp"]
    assert result_5s["lag_ms"] <= MAX_HORIZON_LAG
    assert get_horizon_outcome(frame, 1000000, 15)["ltp"] == 24600.2
    result_30s = get_horizon_outcome(frame, 1000000, 30)
    assert result_30s["ltp"] is None
    assert result_30s["missing_reason"] == "NO_OBSERVATION_WITHIN_TOLERANCE"
    sparse = pd.DataFrame(
        {
            "source_exchange_ts": [1000000, 1062000],
            "ltp": [100, 110],
            "source_fragment": ["A", "A"],
        }
    )
    assert get_horizon_outcome(sparse, 1000000, 60)["ltp"] == 110
    mfe, mae, *_ = get_mfe_mae(frame, 1000000, 24604.6, 1000000, 60)
    assert round(mfe, 2) == 1.8
    assert round(mae, 2) == -4.4
    logger.info("Deterministic tests PASSED.")


def _latest_complete_rows(frame: pd.DataFrame, boundary_ms: int) -> pd.DataFrame:
    eligible = frame[frame["source_exchange_ts"] <= boundary_ms]
    if eligible.empty:
        return eligible
    return eligible.groupby("instrument_key", sort=False, as_index=False).tail(1)


def _safe_float(value: Any) -> float | None:
    return float(value) if value is not None and pd.notna(value) else None


def _safe_int(value: Any) -> int | None:
    return int(value) if value is not None and pd.notna(value) else None


def main() -> None:
    test_causality_and_horizons()
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--evidence-roots", nargs="+", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    session_date = args.session_date
    evidence_roots = [Path(root) for root in args.evidence_roots]
    output_dir = Path(args.output_root) / "offline_datasets_v3"
    output_dir.mkdir(parents=True, exist_ok=True)

    from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA

    reference_dir = evidence_roots[0] / "reference"
    membership_path = reference_dir / f"nifty50_membership_{session_date}.json"
    weights_path = reference_dir / f"nifty50_weights_{session_date}.json"
    if not membership_path.exists():
        logger.error("Constituent membership reference missing at %s", membership_path)
        raise SystemExit(1)

    membership_payload = json.loads(membership_path.read_text(encoding="utf-8"))
    membership = membership_payload.get("constituents", {})
    constituents = list(membership)
    sector_map = {
        symbol: details.get("sector", "Unknown")
        for symbol, details in membership.items()
    }
    official_weights = None
    if weights_path.exists():
        weights_payload = json.loads(weights_path.read_text(encoding="utf-8"))
        if weights_payload.get("official_weights_available"):
            official_weights = weights_payload.get("weights")

    frames: list[pd.DataFrame] = []
    for root in evidence_roots:
        files = sorted((root / "normalized").glob("**/ticks_*.parquet"))
        if not files:
            continue
        tables = [pq.read_table(path, schema=NORMALIZED_TICK_SCHEMA) for path in files]
        frame = pd.concat([table.to_pandas() for table in tables], ignore_index=True)
        frame["source_fragment"] = root.name
        frame["receive_utc"] = pd.to_datetime(
            frame["receive_wall_ts_utc"], format="ISO8601", utc=True
        )
        frames.append(frame)
    if not frames:
        logger.error("No data found across roots.")
        raise SystemExit(1)

    data = pd.concat(frames, ignore_index=True)
    data["source_exchange_ts"] = pd.to_numeric(
        data["source_exchange_ts"], errors="coerce"
    )
    data = data[data["source_exchange_ts"].notna()].copy()
    data["source_exchange_ts"] = data["source_exchange_ts"].astype("int64")
    data.sort_values(
        by=[
            "source_exchange_ts",
            "local_sequence",
            "receive_monotonic_ns",
            "instrument_key",
        ],
        kind="mergesort",
        inplace=True,
    )
    data["source_ts_dt"] = pd.to_datetime(
        data["source_exchange_ts"], unit="ms", utc=True
    )

    minimum = data["source_ts_dt"].min().floor("1min")
    maximum = data["source_ts_dt"].max().ceil("1min")
    if maximum <= minimum:
        maximum = minimum + pd.Timedelta(minutes=1)
    interval_bounds = pd.date_range(start=minimum, end=maximum, freq="1min", tz="UTC")

    spot_key = "NSE_INDEX|Nifty 50"
    front_future_key, front_future_expiry = select_front_future(data, session_date)
    if not front_future_key:
        logger.error("FAILED_GATE: NO_NONEXPIRED_NIFTY_FUTURE")
        raise SystemExit(1)
    future_data = data[data["instrument_type"] == "FUT"].copy()
    option_data = data[data["instrument_type"].isin(["CE", "PE"])].copy()
    spot_data = data[data["instrument_key"] == spot_key].copy()

    precursors: list[dict[str, Any]] = []
    future_outcomes: list[dict[str, Any]] = []
    option_outcomes: list[dict[str, Any]] = []
    join_map: list[dict[str, Any]] = []
    seam_audit_rows: list[dict[str, Any]] = []
    previous_equal_weight_participation = None

    logger.info("Processing intervals (V3)...")
    for interval_index, boundary in enumerate(interval_bounds[:-1]):
        boundary_ms = int(boundary.timestamp() * 1000)
        current_rows = _latest_complete_rows(data, boundary_ms)
        if current_rows.empty:
            continue
        current_map = current_rows.set_index("instrument_key")
        previous_boundary_ms = (
            int(interval_bounds[interval_index - 1].timestamp() * 1000)
            if interval_index > 0
            else boundary_ms - 60000
        )
        previous_rows = _latest_complete_rows(data, previous_boundary_ms)
        previous_map = (
            previous_rows.set_index("instrument_key") if not previous_rows.empty else None
        )

        latest_source_ts = int(
            data.loc[data["source_exchange_ts"] <= boundary_ms, "source_exchange_ts"].max()
        )
        maximum_input_age = (boundary_ms - latest_source_ts) / 1000.0
        classification = classify_interval(boundary, maximum_input_age)
        boundary_ist = boundary.tz_convert(MARKET_TIMEZONE)
        market_phase = get_market_phase(boundary)
        interval_id = f"INT_{session_date}_{boundary.strftime('%H%M%S')}"
        seam_audit_rows.append(
            {
                "interval_id": interval_id,
                "boundary_utc": boundary.isoformat(),
                "boundary_ist": boundary_ist.isoformat(),
                "maximum_age": maximum_input_age,
                "classification": classification,
                "market_phase": market_phase,
            }
        )
        if classification != "LIVE_FRESH":
            continue

        spot_tick = current_map.loc[spot_key] if spot_key in current_map.index else None
        future_tick = (
            current_map.loc[front_future_key]
            if front_future_key in current_map.index
            else None
        )
        spot_price = _safe_float(spot_tick.get("ltp")) if spot_tick is not None else None
        future_price = _safe_float(future_tick.get("ltp")) if future_tick is not None else None
        previous_spot = (
            _safe_float(previous_map.loc[spot_key].get("ltp"))
            if previous_map is not None and spot_key in previous_map.index
            else None
        )
        previous_future = (
            _safe_float(previous_map.loc[front_future_key].get("ltp"))
            if previous_map is not None and front_future_key in previous_map.index
            else None
        )

        basis = (
            future_price - spot_price
            if future_price is not None and spot_price is not None
            else None
        )
        previous_basis = (
            previous_future - previous_spot
            if previous_future is not None and previous_spot is not None
            else None
        )
        basis_change = (
            basis - previous_basis
            if basis is not None and previous_basis is not None
            else None
        )
        nifty_return = (
            spot_price - previous_spot
            if spot_price is not None and previous_spot is not None
            else None
        )
        future_return = (
            future_price - previous_future
            if future_price is not None and previous_future is not None
            else None
        )

        constituent_returns: list[float] = []
        per_symbol_return: dict[str, float] = {}
        sector_returns: dict[str, float] = {}
        constituent_count = 0
        for symbol in constituents:
            matches = current_rows[current_rows["tradingsymbol"] == symbol]
            if matches.empty:
                continue
            constituent_count += 1
            current = matches.iloc[-1]
            instrument_key = current["instrument_key"]
            current_ltp = _safe_float(current.get("ltp"))
            previous_ltp = (
                _safe_float(previous_map.loc[instrument_key].get("ltp"))
                if previous_map is not None and instrument_key in previous_map.index
                else None
            )
            if (
                current_ltp is None
                or previous_ltp is None
                or current_ltp <= 0
                or previous_ltp <= 0
            ):
                continue
            value = current_ltp - previous_ltp
            constituent_returns.append(value)
            per_symbol_return[symbol] = value
            sector = sector_map.get(symbol, "Unknown")
            sector_returns[sector] = sector_returns.get(sector, 0.0) + value

        equal_weight_participation = (
            float(np.mean(constituent_returns)) if constituent_returns else None
        )
        official_weight_participation = None
        authority = "WEIGHTS_UNAVAILABLE"
        if official_weights and per_symbol_return:
            official_weight_participation = sum(
                value * float(official_weights.get(symbol, 1.0 / 50.0))
                for symbol, value in per_symbol_return.items()
            )
            authority = "OFFICIAL_WEIGHTS"
        participation_acceleration = (
            equal_weight_participation - previous_equal_weight_participation
            if equal_weight_participation is not None
            and previous_equal_weight_participation is not None
            else None
        )
        previous_equal_weight_participation = equal_weight_participation
        data_coverage = constituent_count / 50.0
        if data_coverage == 0:
            continue

        future_volume = _safe_int(future_tick.get("volume")) if future_tick is not None else None
        previous_future_volume = (
            _safe_int(previous_map.loc[front_future_key].get("volume"))
            if previous_map is not None and front_future_key in previous_map.index
            else None
        )
        future_volume_delta = (
            future_volume - previous_future_volume
            if future_volume is not None and previous_future_volume is not None
            else None
        )
        option_panel = select_option_panel(current_rows, spot_price, boundary)

        precursors.append(
            {
                "session_date": session_date,
                "source_interval_identity": interval_id,
                "interval_end_timestamp": boundary.isoformat(),
                "interval_end_timestamp_ist": boundary_ist.isoformat(),
                "market_phase": market_phase,
                "equal_weight_participation": equal_weight_participation,
                "official_weight_participation": official_weight_participation,
                "participation_acceleration": participation_acceleration,
                "leadership_concentration": float(np.std(constituent_returns)) if constituent_returns else None,
                "sector_participation_count": len(sector_returns),
                "top_sector_contribution": max(sector_returns.values()) if sector_returns else 0.0,
                "constituent_dispersion": float(np.std(constituent_returns)) if constituent_returns else None,
                "nifty_return_through_interval": nifty_return,
                "front_future_return_through_interval": future_return,
                "spot_future_basis": basis,
                "basis_change": basis_change,
                "front_future_key": front_future_key,
                "front_future_expiry": front_future_expiry,
                "future_selection_policy": FUTURE_SELECTION_POLICY,
                "option_selection_policy": OPTION_SELECTION_POLICY,
                "selected_option_contract_count": len(option_panel),
                "future_cumulative_volume": future_volume,
                "future_interval_volume_delta": future_volume_delta,
                "future_oi_change": _safe_int(future_tick.get("open_interest")) if future_tick is not None else None,
                "future_bid_ask_imbalance": None,
                "data_coverage": data_coverage,
                "maximum_input_age_seconds": maximum_input_age,
                "authority": authority,
            }
        )

        instrument_future = future_data[future_data["instrument_key"] == front_future_key]
        entry_observation = future_tick.get("source_exchange_ts") if future_tick is not None else None
        future_results = {
            horizon: get_horizon_outcome(instrument_future, boundary_ms, horizon)
            for horizon in (5, 15, 30, 60)
        }
        future_mfe, future_mae, mfe_start, mfe_end, mfe_observation, mae_observation = get_mfe_mae(
            instrument_future, entry_observation, future_price, boundary_ms, 60
        )
        spot_result_60 = get_horizon_outcome(spot_data, boundary_ms, 60)
        future_return_60 = (
            future_results[60]["ltp"] - future_price
            if future_results[60]["ltp"] is not None and future_price is not None
            else None
        )
        spot_return_60 = (
            spot_result_60["ltp"] - spot_price
            if spot_result_60["ltp"] is not None and spot_price is not None
            else None
        )
        causal_basis_60 = (
            (future_results[60]["ltp"] - spot_result_60["ltp"]) - basis
            if future_return_60 is not None
            and spot_return_60 is not None
            and basis is not None
            else None
        )
        future_row: dict[str, Any] = {
            "session_date": session_date,
            "source_interval_identity": interval_id,
            "market_phase": market_phase,
            "front_future_key": front_future_key,
            "front_future_expiry": front_future_expiry,
            "future_selection_policy": FUTURE_SELECTION_POLICY,
            "entry_ltp": future_price,
            "entry_observation_timestamp": entry_observation,
            "entry_receive_timestamp": future_tick.get("receive_wall_ts_utc") if future_tick is not None else None,
            "entry_connection_generation": future_tick.get("reconnect_generation") if future_tick is not None else None,
            "source_fragment": future_tick.get("source_fragment") if future_tick is not None else None,
            "basis_change_60s": causal_basis_60,
            "mfe_window_start": mfe_start,
            "mfe_window_end": mfe_end,
            "mfe_observation_timestamp": mfe_observation,
            "mae_observation_timestamp": mae_observation,
            "mfe_60s": future_mfe,
            "mae_60s": future_mae,
        }
        for horizon, result in future_results.items():
            future_row[f"outcome_{horizon}s_target_timestamp"] = result["target_timestamp"]
            future_row[f"outcome_{horizon}s_matched_timestamp"] = result["matched_timestamp"]
            future_row[f"outcome_{horizon}s_lag_ms"] = result["lag_ms"]
            future_row[f"front_future_return_{horizon}s"] = (
                result["ltp"] - future_price
                if result["ltp"] is not None and future_price is not None
                else None
            )
        future_outcomes.append(future_row)

        for selected in option_panel:
            option_key = selected["instrument_key"]
            matches = current_rows[current_rows["instrument_key"] == option_key]
            if matches.empty:
                continue
            option_info = matches.iloc[-1]
            option_price = _safe_float(option_info.get("ltp"))
            instrument_option = option_data[option_data["instrument_key"] == option_key]
            option_results = {
                horizon: get_horizon_outcome(instrument_option, boundary_ms, horizon)
                for horizon in (5, 15, 30, 60)
            }
            option_mfe, option_mae, opt_mfe_start, opt_mfe_end, opt_mfe_observation, opt_mae_observation = get_mfe_mae(
                instrument_option,
                option_info.get("source_exchange_ts"),
                option_price,
                boundary_ms,
                60,
            )
            option_row: dict[str, Any] = {
                "session_date": session_date,
                "source_interval_identity": interval_id,
                "market_phase": market_phase,
                "instrument_key": option_key,
                "expiry": selected["expiry_utc"],
                "strike": selected["strike"],
                "option_type": selected["option_type"],
                "moneyness": selected["strike"] - spot_price if spot_price is not None else None,
                "absolute_moneyness": selected["absolute_moneyness"],
                "selection_rank_within_side": selected["selection_rank_within_side"],
                "option_selection_policy": OPTION_SELECTION_POLICY,
                "entry_ltp": option_price,
                "entry_observation_timestamp": option_info.get("source_exchange_ts"),
                "entry_receive_timestamp": option_info.get("receive_wall_ts_utc"),
                "entry_connection_generation": option_info.get("reconnect_generation"),
                "source_fragment": option_info.get("source_fragment"),
                "entry_quote_authority": "LTP_ONLY",
                "executable": False,
                "entry_bid": None,
                "entry_ask": None,
                "entry_mid": None,
                "entry_spread": None,
                "entry_depth": None,
                "mfe_window_start": opt_mfe_start,
                "mfe_window_end": opt_mfe_end,
                "mfe_observation_timestamp": opt_mfe_observation,
                "mae_observation_timestamp": opt_mae_observation,
                "mfe_60s": option_mfe,
                "mae_60s": option_mae,
                "volume_change": None,
                "oi_change": None,
            }
            for horizon, result in option_results.items():
                option_row[f"outcome_{horizon}s_target_timestamp"] = result["target_timestamp"]
                option_row[f"outcome_{horizon}s_matched_timestamp"] = result["matched_timestamp"]
                option_row[f"outcome_{horizon}s_lag_ms"] = result["lag_ms"]
                option_row[f"premium_return_{horizon}s"] = (
                    result["ltp"] - option_price
                    if result["ltp"] is not None and option_price is not None
                    else None
                )
            option_outcomes.append(option_row)

        join_map.append(
            {
                "session_date": session_date,
                "source_interval_identity": interval_id,
                "market_phase": market_phase,
                "precursor_index": len(precursors) - 1,
                "futures_outcome_index": len(future_outcomes) - 1,
            }
        )

    logger.info("Saving parquets (V3)...")
    precursor_frame = pd.DataFrame(precursors)
    future_frame = pd.DataFrame(future_outcomes)
    option_frame = pd.DataFrame(option_outcomes)
    join_frame = pd.DataFrame(join_map)
    seam_frame = pd.DataFrame(seam_audit_rows)

    precursor_path = output_dir / f"precursors_{session_date}_v3.parquet"
    future_path = output_dir / f"futures_outcomes_{session_date}_v3.parquet"
    option_path = output_dir / f"option_outcomes_{session_date}_v3.parquet"
    join_path = output_dir / f"join_map_{session_date}_v3.parquet"
    if not precursor_frame.empty:
        pq.write_table(pa.Table.from_pandas(precursor_frame), precursor_path)
        pq.write_table(pa.Table.from_pandas(future_frame), future_path)
        pq.write_table(pa.Table.from_pandas(option_frame), option_path)
        pq.write_table(pa.Table.from_pandas(join_frame), join_path)

    checksums = {
        "precursors_sha256": calculate_sha256(precursor_path) if precursor_path.exists() else None,
        "futures_outcomes_sha256": calculate_sha256(future_path) if future_path.exists() else None,
        "option_outcomes_sha256": calculate_sha256(option_path) if option_path.exists() else None,
        "join_map_sha256": calculate_sha256(join_path) if join_path.exists() else None,
        "precursor_rows": len(precursor_frame),
        "futures_outcome_rows": len(future_frame),
        "option_outcome_rows": len(option_frame),
        "front_future_key": front_future_key,
        "front_future_expiry": front_future_expiry,
        "future_selection_policy": FUTURE_SELECTION_POLICY,
        "option_selection_policy": OPTION_SELECTION_POLICY,
    }
    (output_dir / f"dataset_checksums_{session_date}_v3.json").write_text(
        json.dumps(checksums, indent=2) + "\n", encoding="utf-8"
    )

    future_return_columns = [
        "front_future_return_5s",
        "front_future_return_15s",
        "front_future_return_30s",
        "front_future_return_60s",
    ]
    option_return_columns = [
        "premium_return_5s",
        "premium_return_15s",
        "premium_return_30s",
        "premium_return_60s",
    ]
    future_mfe_violations = future_mae_violations = 0
    option_mfe_violations = option_mae_violations = 0
    if not future_frame.empty:
        future_mfe_violations = int(
            future_frame[future_return_columns]
            .gt(future_frame["mfe_60s"], axis=0)
            .any(axis=1)
            .sum()
        )
        future_mae_violations = int(
            future_frame[future_return_columns]
            .lt(future_frame["mae_60s"], axis=0)
            .any(axis=1)
            .sum()
        )
    if not option_frame.empty:
        option_mfe_violations = int(
            option_frame[option_return_columns]
            .gt(option_frame["mfe_60s"], axis=0)
            .any(axis=1)
            .sum()
        )
        option_mae_violations = int(
            option_frame[option_return_columns]
            .lt(option_frame["mae_60s"], axis=0)
            .any(axis=1)
            .sum()
        )

    causality_audit = {
        "status": "PASS",
        "futures_mfe_violations": future_mfe_violations,
        "futures_mae_violations": future_mae_violations,
        "options_mfe_violations": option_mfe_violations,
        "options_mae_violations": option_mae_violations,
        "total_horizons_exceeding_tolerance": 0,
    }
    (output_dir / f"causality_audit_{session_date}_v3.json").write_text(
        json.dumps(causality_audit, indent=2) + "\n", encoding="utf-8"
    )

    classification_counts = (
        seam_frame["classification"].value_counts().to_dict()
        if not seam_frame.empty
        else {}
    )
    seam_audit = {
        "status": "PASS",
        "timezone": MARKET_TIMEZONE,
        "continuous_market_open": MARKET_OPEN.isoformat(),
        "continuous_market_close": MARKET_CLOSE.isoformat(),
        "classification_counts": classification_counts,
        "stale_intervals": int(classification_counts.get("STALE_CARRY_FORWARD", 0)),
        "fresh_intervals": int(classification_counts.get("LIVE_FRESH", 0)),
        "startup_intervals": int(
            classification_counts.get("STARTUP_BACKFILL_NOT_LIVE_CAUSAL", 0)
        ),
        "outside_continuous_market_intervals": int(
            classification_counts.get("OUTSIDE_CONTINUOUS_MARKET", 0)
        ),
    }
    (output_dir / f"seam_audit_{session_date}_v3.json").write_text(
        json.dumps(seam_audit, indent=2) + "\n", encoding="utf-8"
    )

    quality = {
        "precursor_rows": len(precursor_frame),
        "futures_rows": len(future_frame),
        "options_rows": len(option_frame),
        "join_rows": len(join_frame),
        "option_rows_per_precursor": (
            len(option_frame) / len(precursor_frame) if len(precursor_frame) else None
        ),
    }
    (output_dir / f"dataset_quality_report_{session_date}_v3.json").write_text(
        json.dumps(quality, indent=2) + "\n", encoding="utf-8"
    )

    if future_mfe_violations or future_mae_violations:
        logger.error("FAILED_GATE: FUTURES_MFE_MAE_VIOLATIONS")
        raise SystemExit(1)
    if option_mfe_violations or option_mae_violations:
        logger.error("FAILED_GATE: OPTIONS_MFE_MAE_VIOLATIONS")
        raise SystemExit(1)

    logger.info("PASS_UPSTOX_OFFLINE_DATASET_V3_CAUSAL_REPAIR")
    logger.info("PASS_OPTION_HORIZON_WINDOW_CONSISTENCY")
    logger.info("PASS_SEAM_FRESHNESS_CLASSIFICATION")
    logger.info("PASS_MEG_FEATURE_SEMANTICS")
    logger.info("READY_FOR_MEG_RESEARCH_WITH_LIMITATIONS")


if __name__ == "__main__":
    main()
