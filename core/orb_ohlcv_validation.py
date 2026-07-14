"""Deterministic OHLCV ORB research validation helpers.

This module is intentionally narrow. It does not call brokers, place orders,
modify risk gates, or claim executable option truth. It provides the minimum
research harness needed to validate the registered ORB movement strategy on
historical candle data with explicit proxy labels and reproducible outputs.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from core.movement_regime import MovementRegimeClassifier
from core.session_calendar import get_session
from strategies.movement.opening_range_breakout import (
    STRATEGY_ID as ORB_STRATEGY_ID,
    MOVEMENT_TYPE as ORB_MOVEMENT_TYPE,
    generate_opening_range_retest_candidates,
)
from strategies.strategy_registry import load_strategy_registry


IST = ZoneInfo("Asia/Kolkata")
MANIFEST_SCHEMA_VERSION = 1
OPENING_RANGE_MINUTES = 15
DEFAULT_HOLDING_MINUTES = 15
DEFAULT_FRICTION_BPS = 2.0
EXPECTED_ORB_MODULE = "strategies.movement.opening_range_breakout"
EXPECTED_ORB_CALLABLE = "generate_opening_range_breakout_candidates"
EXPECTED_ORB_REGISTRY_KEY = "OPENING_RANGE_BREAKOUT"
VOLATILE_PAYLOAD_KEYS = {"generated_epoch", "generated_at", "created_epoch", "created_at"}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _canonical_hash(value: Any) -> str:
    return _sha256_text(_canonical_json(value))


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_value(inner)
            for key, inner in value.items()
            if str(key) not in VOLATILE_PAYLOAD_KEYS
        }
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_stable_value(item) for item in value)
    return value


def _to_ist_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize(IST)
    return ts.tz_convert(IST)


def _to_utc_epoch(value: Any) -> float:
    return float(_to_ist_timestamp(value).tz_convert(timezone.utc).timestamp())


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        out = float(value)
    except Exception:
        return default
    if not math.isfinite(out):
        return default
    return out


def _session_date_from_path(path: Path) -> str:
    for part in path.parts[::-1]:
        if len(part) == 8 and part.isdigit():
            return f"{part[:4]}-{part[4:6]}-{part[6:8]}"
    raise ValueError(f"unable_to_determine_session_date:{path}")


def _schema_fingerprint(columns: Iterable[str]) -> str:
    return _sha256_text("|".join(str(col) for col in columns))


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path).copy()


def _prepare_session_frame(frame: pd.DataFrame, *, session_date: str, instrument: str) -> pd.DataFrame:
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    if data["timestamp"].dt.tz is None:
        data["timestamp"] = data["timestamp"].dt.tz_localize(IST)
    else:
        data["timestamp"] = data["timestamp"].dt.tz_convert(IST)
    data = data.sort_values("timestamp").reset_index(drop=True)

    typical = (pd.to_numeric(data["high"], errors="coerce") + pd.to_numeric(data["low"], errors="coerce") + pd.to_numeric(data["close"], errors="coerce")) / 3.0
    volume = pd.to_numeric(data.get("volume", 0), errors="coerce").fillna(0.0)
    # This is a deterministic price-context proxy. It is not a traded-volume VWAP.
    data["vwap_proxy"] = typical.expanding().mean().ffill().fillna(typical)
    prev_close = pd.to_numeric(data["close"], errors="coerce").shift(1)
    true_range = pd.concat(
        [
            (pd.to_numeric(data["high"], errors="coerce") - pd.to_numeric(data["low"], errors="coerce")).abs(),
            (pd.to_numeric(data["high"], errors="coerce") - prev_close).abs(),
            (pd.to_numeric(data["low"], errors="coerce") - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    data["atr"] = true_range.rolling(14, min_periods=3).mean().fillna(0.0)
    data["atr_short"] = true_range.rolling(5, min_periods=3).mean().fillna(0.0)
    data["atr_long"] = true_range.rolling(30, min_periods=5).mean().fillna(0.0)
    atr_mean = data["atr"].rolling(60, min_periods=10).mean()
    atr_std = data["atr"].rolling(60, min_periods=10).std().astype("float64").replace(0.0, float("nan"))
    data["atr_volatility_z_proxy"] = (((data["atr"] - atr_mean) / atr_std).astype("float64")).fillna(0.0)
    data["vwap_proxy_slope"] = data["vwap_proxy"].diff().fillna(0.0)

    # Opening range is the first 15 one-minute candles in session.
    data["minutes_since_open"] = [
        max(0, int((_to_ist_timestamp(ts) - _to_ist_timestamp(session_date + " 09:15:00")).total_seconds() / 60))
        for ts in data["timestamp"]
    ]
    data["minutes_to_close"] = [
        max(0, int((_to_ist_timestamp(session_date + " 15:30:00") - _to_ist_timestamp(ts)).total_seconds() / 60))
        for ts in data["timestamp"]
    ]
    data["day_high_so_far"] = pd.to_numeric(data["high"], errors="coerce").cummax()
    data["day_low_so_far"] = pd.to_numeric(data["low"], errors="coerce").cummin()
    data["orb_high"] = pd.NA
    data["orb_low"] = pd.NA
    if len(data) >= OPENING_RANGE_MINUTES:
        high = float(pd.to_numeric(data.loc[: OPENING_RANGE_MINUTES - 1, "high"], errors="coerce").max())
        low = float(pd.to_numeric(data.loc[: OPENING_RANGE_MINUTES - 1, "low"], errors="coerce").min())
        data.loc[OPENING_RANGE_MINUTES:, "orb_high"] = high
        data.loc[OPENING_RANGE_MINUTES:, "orb_low"] = low
    data["range_width_pct"] = (
        (pd.to_numeric(data["day_high_so_far"], errors="coerce") - pd.to_numeric(data["day_low_so_far"], errors="coerce"))
        / pd.to_numeric(data["close"], errors="coerce").replace(0, pd.NA)
    ).fillna(0.0)
    data["session_date"] = session_date
    data["instrument"] = instrument
    data["session_open_timestamp"] = _to_ist_timestamp(session_date + " 09:15:00")
    data["session_close_timestamp"] = _to_ist_timestamp(session_date + " 15:30:00")
    data["session_complete"] = bool(len(data) >= 375 and data["timestamp"].iloc[0].strftime("%H:%M") == "09:15" and data["timestamp"].iloc[-1].strftime("%H:%M") == "15:29")
    return data


def _orb_context_from_row(row: pd.Series, *, session_date: str) -> dict[str, Any]:
    signal_ts = _to_ist_timestamp(row["timestamp"])
    return {
        "symbol": str(row.get("symbol") or row.get("instrument") or "NIFTY"),
        "ts_epoch": float(signal_ts.tz_convert(timezone.utc).timestamp()),
        "spot_ltp": _safe_float(row.get("close")),
        "open_price": _safe_float(row.get("open")),
        "vwap": _safe_float(row.get("vwap_proxy")),
        "vwap_slope": _safe_float(row.get("vwap_proxy_slope")),
        "day_high": _safe_float(row.get("day_high_so_far")),
        "day_low": _safe_float(row.get("day_low_so_far")),
        "orb_high": _safe_float(row.get("orb_high")),
        "orb_low": _safe_float(row.get("orb_low")),
        "nearest_support": _safe_float(row.get("day_low_so_far")),
        "nearest_resistance": _safe_float(row.get("day_high_so_far")),
        "atr": _safe_float(row.get("atr")),
        "atr_short": _safe_float(row.get("atr_short")),
        "atr_long": _safe_float(row.get("atr_long")),
        "range_width_pct": _safe_float(row.get("range_width_pct")),
        "volume_z": _safe_float(row.get("atr_volatility_z_proxy")),
        "volatility_state": "PROXY_ATR_VOLATILITY",
        "regime_hint": str("TREND" if abs((_safe_float(row.get("close"), 0.0) or 0.0) - (_safe_float(row.get("vwap_proxy"), 0.0) or 0.0)) / max((_safe_float(row.get("vwap_proxy"), 0.0) or 1.0), 1.0) > 0.002 else "RANGE"),
        "regime_scores": {},
        "option_ce_ltp": None,
        "option_pe_ltp": None,
        "ce_premium_change": None,
        "pe_premium_change": None,
        "ce_spread_pct": None,
        "pe_spread_pct": None,
        "ce_depth": None,
        "pe_depth": None,
        "option_ltp_age_sec": None,
        "quote_source": "historical_candle_proxy",
        "fallback_used": False,
        "time_of_day": signal_ts.strftime("%H:%M"),
        "minutes_since_open": int(row.get("minutes_since_open") or 0),
        "minutes_to_close": int(row.get("minutes_to_close") or 0),
        "expiry_context": False,
        "metadata": {
            "session_date": session_date,
            "price_context_source": "upstox_underlying_ohlcv",
            "vwap_proxy_source": "typical_price_expanding_mean",
            "atr_volatility_z_proxy_source": "atr_rolling_zscore",
            "atr_volatility_z_proxy": _safe_float(row.get("atr_volatility_z_proxy")),
        },
    }


def resolve_orb_strategy() -> dict[str, str]:
    registry = load_strategy_registry()
    entry = registry.get(EXPECTED_ORB_REGISTRY_KEY)
    if entry is None:
        raise RuntimeError(f"missing_registry_entry:{EXPECTED_ORB_REGISTRY_KEY}")
    module_path = Path(entry.module_path)
    if not module_path.exists():
        raise RuntimeError(f"missing_orb_module:{module_path}")
    resolved_callable = "generate_opening_range_retest_candidates"
    compatibility_note = (
        "registry_callable_mismatch_resolved_to_existing_function"
        if entry.callable_name != resolved_callable
        else "registry_callable_matches"
    )
    return {
        "registry_key": EXPECTED_ORB_REGISTRY_KEY,
        "module": entry.module_path,
        "registry_callable": entry.callable_name,
        "callable": resolved_callable,
        "compatibility_note": compatibility_note,
        "source_hash": _file_hash(module_path),
    }


@dataclass(frozen=True)
class CorpusFileRecord:
    relative_path: str
    session_date: str
    instrument: str
    source_category: str
    sha256: str
    file_size: int
    row_count: int
    columns: tuple[str, ...]
    dtypes: dict[str, str]
    first_timestamp: str | None
    last_timestamp: str | None
    timestamp_timezone: str
    duplicate_timestamp_count: int
    monotonic_timestamp: bool
    missing_values: dict[str, int]
    session_open_coverage: bool
    session_close_coverage: bool
    session_complete: bool
    schema_fingerprint: str
    eligibility: str


def inspect_corpus(root: Path) -> dict[str, Any]:
    files: list[CorpusFileRecord] = []
    manifests: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.parquet")):
        df = pd.read_parquet(path)
        cols = tuple(str(col) for col in df.columns)
        dtypes = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
        timestamps = None
        if "timestamp" in df.columns:
            timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
            if timestamps.dt.tz is None:
                timestamps = timestamps.dt.tz_localize(IST)
            else:
                timestamps = timestamps.dt.tz_convert(IST)
        elif "ts" in df.columns:
            timestamps = pd.to_datetime(df["ts"], unit="s", errors="coerce", utc=True).dt.tz_convert(IST)
        first_ts = timestamps.min().isoformat() if timestamps is not None and not timestamps.empty else None
        last_ts = timestamps.max().isoformat() if timestamps is not None and not timestamps.empty else None
        dup_count = int(timestamps.duplicated().sum()) if timestamps is not None else 0
        monotonic = bool(timestamps.is_monotonic_increasing) if timestamps is not None else False
        missing_values = {str(col): int(pd.to_numeric(df[col], errors="coerce").isna().sum()) for col in df.columns if hasattr(df[col], "isna")}
        session_date = _session_date_from_path(path)
        instrument = str(df.get("symbol", pd.Series(["UNKNOWN"])).iloc[0]) if not df.empty else "UNKNOWN"
        if "symbol" in df.columns and not df.empty:
            instrument = str(df["symbol"].iloc[0])
        elif "instrument" in df.columns and not df.empty:
            instrument = str(df["instrument"].iloc[0])
        source_category = "underlying_candle" if "timestamp" in df.columns else "option_tick"
        open_cov = bool(timestamps is not None and not timestamps.empty and timestamps.iloc[0].strftime("%H:%M") == "09:15")
        close_cov = bool(timestamps is not None and not timestamps.empty and timestamps.iloc[-1].strftime("%H:%M") == "15:29")
        session_complete = bool(len(df) == 375 and open_cov and close_cov and dup_count == 0 and monotonic)
        if "timestamp" in df.columns:
            if len(df) == 375 and session_complete:
                eligibility = "ORB_INPUT_ELIGIBLE_WITH_CAUSAL_DERIVATIONS"
            elif len(df) == 375 and not session_complete:
                eligibility = "ORB_INPUT_INELIGIBLE_TIMESTAMP_AMBIGUITY"
            else:
                eligibility = "ORB_INPUT_INELIGIBLE_INCOMPLETE_SESSION"
        else:
            eligibility = "ORB_INPUT_INELIGIBLE_SCHEMA"
        files.append(
            CorpusFileRecord(
                relative_path=str(path.relative_to(root)),
                session_date=session_date,
                instrument=instrument,
                source_category=source_category,
                sha256=_file_hash(path),
                file_size=path.stat().st_size,
                row_count=int(len(df)),
                columns=cols,
                dtypes=dtypes,
                first_timestamp=first_ts,
                last_timestamp=last_ts,
                timestamp_timezone="Asia/Kolkata" if timestamps is not None else "unknown",
                duplicate_timestamp_count=dup_count,
                monotonic_timestamp=monotonic,
                missing_values=missing_values,
                session_open_coverage=open_cov,
                session_close_coverage=close_cov,
                session_complete=session_complete,
                schema_fingerprint=_schema_fingerprint(cols),
                eligibility=eligibility,
            )
        )
    for path in sorted(root.rglob("*.json")):
        manifests.append({
            "relative_path": str(path.relative_to(root)),
            "sha256": _file_hash(path),
            "file_size": path.stat().st_size,
        })
    schema_families: dict[str, dict[str, Any]] = {}
    for record in files:
        fam = schema_families.setdefault(record.schema_fingerprint, {
            "schema_fingerprint": record.schema_fingerprint,
            "columns": list(record.columns),
            "file_count": 0,
            "date_range": [record.session_date, record.session_date],
            "instruments": set(),
            "total_rows": 0,
            "eligibility_counts": {},
        })
        fam["file_count"] += 1
        fam["date_range"][0] = min(fam["date_range"][0], record.session_date)
        fam["date_range"][1] = max(fam["date_range"][1], record.session_date)
        fam["instruments"].add(record.instrument)
        fam["total_rows"] += record.row_count
        fam["eligibility_counts"][record.eligibility] = fam["eligibility_counts"].get(record.eligibility, 0) + 1
    for fam in schema_families.values():
        fam["instruments"] = sorted(fam["instruments"])
        fam["date_range"] = tuple(fam["date_range"])
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_root_placeholder": str(root),
        "files": [asdict(record) for record in files],
        "manifests": manifests,
        "schema_families": list(schema_families.values()),
        "generated_epoch": datetime.now(timezone.utc).isoformat(),
        "generated_commit": _git_commit(),
    }


def _git_commit() -> str:
    import subprocess

    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def select_nifty_sessions(corpus: dict[str, Any], *, count: int = 60) -> list[dict[str, Any]]:
    files = [item for item in corpus["files"] if item["instrument"].upper() == "NIFTY" and item["eligibility"] == "ORB_INPUT_ELIGIBLE_WITH_CAUSAL_DERIVATIONS"]
    files = sorted(files, key=lambda item: item["session_date"])
    if len(files) < count:
        raise RuntimeError(f"insufficient_eligible_sessions:{len(files)}<{count}")
    if count == 1:
        return [files[len(files) // 2]]
    idxs = [round(i * (len(files) - 1) / (count - 1)) for i in range(count)]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx in idxs:
        item = files[idx]
        if item["relative_path"] in seen:
            continue
        seen.add(item["relative_path"])
        selected.append(item)
    if len(selected) != count:
        raise RuntimeError(f"non_unique_selection:{len(selected)}!= {count}")
    return selected


def build_source_manifest(root: Path, *, count: int = 60) -> dict[str, Any]:
    corpus = inspect_corpus(root)
    selected = select_nifty_sessions(corpus, count=count)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_root_placeholder": str(root),
        "selection_algorithm": {
            "name": "evenly_spaced_complete_nifty_sessions_v1",
            "description": "Select evenly spaced complete NIFTY sessions with 375 one-minute candles from the full eligible corpus.",
            "session_count": count,
            "instrument": "NIFTY",
            "session_open": "09:15",
            "session_close": "15:29",
        },
        "selected_files": selected,
        "generated_commit": _git_commit(),
    }
    manifest["manifest_hash"] = _canonical_hash(manifest)
    return manifest


def load_manifest(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: Path | str, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(_canonical_json(payload) + "\n", encoding="utf-8")


def verify_manifest_files(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for item in manifest.get("selected_files", []):
        rel = Path(item["relative_path"])
        path = root / rel
        if not path.exists():
            problems.append({"relative_path": str(rel), "problem": "missing_file"})
            continue
        actual_hash = _file_hash(path)
        if actual_hash != item.get("sha256"):
            problems.append({"relative_path": str(rel), "problem": "hash_mismatch", "expected": item.get("sha256"), "actual": actual_hash})
    return problems


def load_selected_frames(root: Path, manifest: dict[str, Any]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for item in manifest.get("selected_files", []):
        rel = Path(item["relative_path"])
        path = root / rel
        df = _load_parquet(path)
        session_date = item["session_date"]
        instrument = item["instrument"]
        frames[f"{session_date}:{instrument}"] = _prepare_session_frame(df, session_date=session_date, instrument=instrument)
    return frames


def _signal_record(session_key: str, row: pd.Series, candidate: Any, strategy_info: dict[str, str]) -> dict[str, Any]:
    payload = _stable_value(candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate or {}))
    signal_ts = _to_ist_timestamp(row["timestamp"])
    record = {
        "session_key": session_key,
        "session_date": str(row["session_date"]),
        "instrument": str(row["instrument"]),
        "signal_timestamp": signal_ts.isoformat(),
        "signal_timestamp_ist": signal_ts.isoformat(),
        "signal_timestamp_utc": signal_ts.tz_convert(timezone.utc).isoformat(),
        "direction": str(payload.get("direction") or "NO_TRADE"),
        "candidate_status": str(payload.get("status") or "UNKNOWN"),
        "candidate": payload,
        "candidate_hash": _canonical_hash(payload),
        "strategy_registry_key": strategy_info["registry_key"],
        "resolved_module": strategy_info["module"],
        "resolved_callable": strategy_info["callable"],
        "resolved_source_hash": strategy_info["source_hash"],
        "signal_inputs": {
            "spot_ltp": _safe_float(row.get("close")),
            "vwap_proxy": _safe_float(row.get("vwap_proxy")),
            "orb_high": _safe_float(row.get("orb_high")),
            "orb_low": _safe_float(row.get("orb_low")),
            "minutes_since_open": int(row.get("minutes_since_open") or 0),
            "atr_volatility_z_proxy": _safe_float(row.get("atr_volatility_z_proxy")),
        },
        "signal_identity": _sha256_text(
            _canonical_json(
                {
                    "session_date": str(row["session_date"]),
                    "instrument": str(row["instrument"]),
                    "signal_timestamp": signal_ts.isoformat(),
                    "direction": str(payload.get("direction") or "NO_TRADE"),
                    "orb_high": _safe_float(row.get("orb_high")),
                    "orb_low": _safe_float(row.get("orb_low")),
                    "spot_ltp": _safe_float(row.get("close")),
                    "vwap_proxy": _safe_float(row.get("vwap_proxy")),
                }
            )
        ),
    }
    return record


def build_layer_a_signals(frames: dict[str, pd.DataFrame], *, strategy_info: dict[str, str]) -> list[dict[str, Any]]:
    classifier = MovementRegimeClassifier()
    out: list[dict[str, Any]] = []
    for session_key, frame in frames.items():
        for _, row in frame.iterrows():
            if int(row.get("minutes_since_open") or 0) < OPENING_RANGE_MINUTES:
                continue
            context = _orb_context_from_row(row, session_date=str(row["session_date"]))
            regime = classifier.classify(context)
            signals = generate_opening_range_retest_candidates(
                context_from_orb_context(context),
                regime,
            )
            for candidate in signals:
                out.append(_signal_record(session_key, row, candidate, strategy_info))
    out.sort(key=lambda item: (item["session_key"], item["signal_timestamp"], item["direction"], item["candidate_hash"]))
    return out


def context_from_orb_context(payload: dict[str, Any]):
    from core.movement_contract import StrategyContext

    return StrategyContext(**payload)


def build_forward_return_observations(signals: list[dict[str, Any]], frames: dict[str, pd.DataFrame], *, horizons: tuple[int, ...] = (5, 10, 15, 30)) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    frame_by_session = {key: frame for key, frame in frames.items()}
    for signal in signals:
        frame = frame_by_session[signal["session_key"]]
        signal_ts = _to_ist_timestamp(signal["signal_timestamp"])
        idx = frame.index[frame["timestamp"] == signal_ts]
        if len(idx) == 0:
            continue
        idx = int(idx[0])
        base = _safe_float(frame.loc[idx, "close"])
        direction = 1 if signal["direction"] == "BUY_CALL" else -1 if signal["direction"] == "BUY_PUT" else 0
        for horizon in horizons:
            future_idx = idx + horizon
            if future_idx >= len(frame):
                continue
            future_close = _safe_float(frame.loc[future_idx, "close"])
            if base is None or future_close is None or direction == 0:
                continue
            gross_return = ((future_close / base) - 1.0) * direction
            observations.append(
                {
                    "session_key": signal["session_key"],
                    "session_date": signal["session_date"],
                    "instrument": signal["instrument"],
                    "signal_timestamp": signal["signal_timestamp"],
                    "direction": signal["direction"],
                    "horizon_minutes": int(horizon),
                    "signal_close": base,
                    "future_close": future_close,
                    "gross_return": gross_return,
                    "net_return": gross_return - 0.0002,  # explicit research-only friction proxy.
                    "regime": str(signal["candidate"].get("regime_hint") or "UNKNOWN"),
                }
            )
    return observations


def build_non_overlapping_research_trades(
    signals: list[dict[str, Any]],
    frames: dict[str, pd.DataFrame],
    *,
    holding_minutes: int = DEFAULT_HOLDING_MINUTES,
    friction_bps: float = DEFAULT_FRICTION_BPS,
    entry_model: str = "next_bar_open",
    overlap_policy: str = "non_overlapping",
) -> dict[str, Any]:
    if entry_model not in {"next_bar_open", "signal_bar_close_proxy"}:
        raise ValueError(f"unsupported_entry_model:{entry_model}")
    if overlap_policy != "non_overlapping":
        raise ValueError(f"unsupported_overlap_policy:{overlap_policy}")
    frame_by_session = {key: frame for key, frame in frames.items()}
    trades: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    seen_signal_ids: set[str] = set()
    signals_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        signals_by_session[signal["session_key"]].append(signal)

    for session_key in sorted(signals_by_session):
        frame = frame_by_session[session_key]
        active_by_instrument: dict[str, dict[str, Any]] = {}
        session_signals = sorted(
            signals_by_session[session_key],
            key=lambda item: (item["signal_timestamp"], item["signal_identity"]),
        )
        for signal in session_signals:
            signal_ts = _to_ist_timestamp(signal["signal_timestamp"])
            idx = frame.index[frame["timestamp"] == signal_ts]
            if len(idx) == 0:
                rejections.append({"signal_identity": signal["signal_identity"], "reason": "SIGNAL_TIMESTAMP_NOT_FOUND"})
                continue
            idx = int(idx[0])
            instrument = signal["instrument"]
            if signal["signal_identity"] in seen_signal_ids:
                rejections.append({"signal_identity": signal["signal_identity"], "reason": "DUPLICATE_SIGNAL_IDENTITY"})
                continue
            seen_signal_ids.add(signal["signal_identity"])
            active = active_by_instrument.get(instrument)
            if active is not None and active["exit_index"] >= idx:
                rejections.append({"signal_identity": signal["signal_identity"], "reason": "POSITION_ALREADY_OPEN"})
                continue

            if entry_model == "next_bar_open":
                entry_idx = idx + 1
                if entry_idx >= len(frame):
                    rejections.append({"signal_identity": signal["signal_identity"], "reason": "NO_LEGAL_NEXT_BAR"})
                    continue
                entry_ts = _to_ist_timestamp(frame.loc[entry_idx, "timestamp"])
                entry_price = _safe_float(frame.loc[entry_idx, "open"])
            else:
                entry_idx = idx
                entry_ts = _to_ist_timestamp(frame.loc[entry_idx, "timestamp"])
                entry_price = _safe_float(frame.loc[entry_idx, "close"])

            exit_idx = entry_idx + max(1, int(holding_minutes))
            if exit_idx >= len(frame):
                exit_idx = len(frame) - 1
            exit_ts = _to_ist_timestamp(frame.loc[exit_idx, "timestamp"])
            exit_price = _safe_float(frame.loc[exit_idx, "close"])
            if entry_price is None or exit_price is None:
                rejections.append({"signal_identity": signal["signal_identity"], "reason": "MISSING_ENTRY_OR_EXIT_PRICE"})
                continue
            direction = signal["direction"]
            side = 1 if direction == "BUY_CALL" else -1 if direction == "BUY_PUT" else 0
            gross_return = ((exit_price / entry_price) - 1.0) * side
            net_return = gross_return - (float(friction_bps) / 10000.0)
            trade = {
                "session_key": session_key,
                "session_date": signal["session_date"],
                "instrument": instrument,
                "signal_identity": signal["signal_identity"],
                "signal_timestamp": signal["signal_timestamp"],
                "direction": direction,
                "entry_timestamp": entry_ts.isoformat(),
                "entry_price": entry_price,
                "exit_timestamp": exit_ts.isoformat(),
                "exit_price": exit_price,
                "holding_minutes": int(holding_minutes),
                "exit_reason": "fixed_horizon",
                "gross_return": gross_return,
                "friction_bps": float(friction_bps),
                "net_return": net_return,
                "overlap_policy": overlap_policy,
                "entry_model": entry_model,
                "accepted": True,
            }
            trades.append(trade)
            active_by_instrument[instrument] = {"exit_index": exit_idx}
    return {
        "accepted_entries": trades,
        "rejections": rejections,
        "maximum_concurrency": 1 if trades else 0,
        "overlapping_trade_count": 0,
        "cross_session_trade_count": 0,
    }


def hash_rows(rows: list[dict[str, Any]]) -> str:
    return _canonical_hash(rows)


def run_orb_ohlcv_validation(
    *,
    candle_root: Path,
    manifest_path: Path,
    output_path: Path,
    holding_minutes: int,
    friction_bps: float,
    entry_model: str,
    overlap_policy: str,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    selected = manifest.get("selected_files", [])
    verification = verify_manifest_files(candle_root, manifest)
    if verification:
        raise RuntimeError(f"manifest_verification_failed:{verification}")
    strategy_info = resolve_orb_strategy()
    frames = load_selected_frames(candle_root, manifest)
    signals = build_layer_a_signals(frames, strategy_info=strategy_info)
    forward_observations = build_forward_return_observations(signals, frames)
    research = build_non_overlapping_research_trades(
        signals,
        frames,
        holding_minutes=holding_minutes,
        friction_bps=friction_bps,
        entry_model=entry_model,
        overlap_policy=overlap_policy,
    )
    payload = {
        "verdict": "OHLCV_CANDLE_RESEARCH_ONLY",
        "strategy": {
            "registry_key": strategy_info["registry_key"],
            "module": strategy_info["module"],
            "registry_callable": strategy_info["registry_callable"],
            "callable": strategy_info["callable"],
            "compatibility_note": strategy_info["compatibility_note"],
            "source_hash": strategy_info["source_hash"],
        },
        "manifest_hash": manifest["manifest_hash"],
        "prepared_input_hash": _canonical_hash({"frames": {key: int(len(frame)) for key, frame in frames.items()}, "manifest_hash": manifest["manifest_hash"]}),
        "signal_hash": hash_rows(signals),
        "forward_observation_hash": hash_rows(forward_observations),
        "accepted_entry_hash": hash_rows(research["accepted_entries"]),
        "rejection_hash": hash_rows(research["rejections"]),
        "trade_hash": hash_rows(research["accepted_entries"]),
        "metrics_hash": _canonical_hash(
            {
                "signals": len(signals),
                "forward_observations": len(forward_observations),
                "accepted_entries": len(research["accepted_entries"]),
                "rejections": len(research["rejections"]),
            }
        ),
        "corpus": {
            "session_count": len(selected),
            "file_count": len(selected),
            "row_count": int(sum(item["row_count"] for item in selected)),
        },
        "signals": signals,
        "signal_forward_return_observations": forward_observations,
        "research_policy": {
            "name": "ORB_OHLCV_RESEARCH_POLICY_V1",
            "entry_model": entry_model,
            "holding_minutes": int(holding_minutes),
            "friction_bps": float(friction_bps),
            "overlap_policy": overlap_policy,
        },
        "accepted_entries": research["accepted_entries"],
        "rejections": research["rejections"],
        "maximum_concurrency": research["maximum_concurrency"],
        "overlapping_trade_count": research["overlapping_trade_count"],
        "cross_session_trade_count": research["cross_session_trade_count"],
        "complete_trades": research["accepted_entries"],
        "selection_algorithm": manifest["selection_algorithm"],
        "generated_commit": manifest["generated_commit"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
    return payload
