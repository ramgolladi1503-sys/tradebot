from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

IST = "Asia/Kolkata"
CAMPAIGN = "sensex_late_session_convexity_data_v1"
RESEARCH_VERDICT_INVALID = "INVALID_DATA_ACQUISITION"


@dataclass(frozen=True)
class KiteCapabilityFinding:
    finding: str
    implication: str
    status: str = "DOCUMENTED"


KITE_LIMITATION_FINDINGS = (
    KiteCapabilityFinding(
        "Kite historical candles are fetched by instrument_token.",
        "Symbol-only recovery is insufficient for historical candles.",
    ),
    KiteCapabilityFinding(
        "The current Kite instrument master describes currently tradable instruments.",
        "Current dumps are not a complete registry of expired derivatives.",
    ),
    KiteCapabilityFinding(
        "Expired futures and options receive contract-specific instrument tokens.",
        "A token cannot be inferred from the underlying symbol alone.",
    ),
    KiteCapabilityFinding(
        "Expired option tokens generally cannot be rediscovered from the current instruments dump.",
        "Historical option acquisition needs cached old dumps, sidecars, old files, or still-live contracts.",
    ),
    KiteCapabilityFinding(
        "Kite continuous history does not solve intraday expired-option retrieval.",
        "Continuous mode is not a substitute for expired option token authority.",
    ),
    KiteCapabilityFinding(
        "Current contracts must not be substituted for expired contracts.",
        "Any option lane without recovered contract tokens remains blocked.",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_ist_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError("invalid timestamp")
    if ts.tzinfo is None:
        raise ValueError(f"timezone-naive timestamp rejected: {value!r}")
    return ts.tz_convert(IST)


def normalize_candles(rows: Iterable[dict[str, Any]]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return pd.DataFrame(), []
    if "date" in frame.columns and "timestamp" not in frame.columns:
        frame = frame.rename(columns={"date": "timestamp"})
    if "timestamp" not in frame.columns:
        raise ValueError("missing timestamp column")
    frame["timestamp"] = frame["timestamp"].map(normalize_ist_timestamp)
    for col in ("open", "high", "low", "close", "volume", "oi"):
        if col not in frame.columns:
            frame[col] = 0 if col in {"volume", "oi"} else pd.NA
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    subset = ["timestamp", "exchange", "tradingsymbol", "instrument_token"]
    subset = [col for col in subset if col in frame.columns]
    conflicting: list[dict[str, Any]] = []
    keep_rows = []
    for _, group in frame.sort_values("timestamp").groupby(subset or ["timestamp"], dropna=False):
        comparable = group.drop(columns=[c for c in ("retrieved_at", "source") if c in group.columns])
        if len(comparable.drop_duplicates()) > 1:
            conflicting.append({"key": {col: str(group.iloc[0][col]) for col in subset}, "rows": int(len(group))})
            keep_rows.extend(group.index.tolist())
        else:
            keep_rows.append(group.index[0])
    deduped = frame.loc[sorted(set(keep_rows))].sort_values("timestamp").reset_index(drop=True)
    return deduped, conflicting


def derive_five_minute(minute: pd.DataFrame) -> pd.DataFrame:
    if minute.empty:
        return minute.copy()
    frame = minute.copy()
    frame["timestamp"] = frame["timestamp"].map(normalize_ist_timestamp)
    frame = frame.sort_values("timestamp")
    session_open = frame["timestamp"].dt.normalize() + pd.Timedelta(hours=9, minutes=15)
    offset_minutes = ((frame["timestamp"] - session_open).dt.total_seconds() // 60).astype("int64")
    frame["_bar_open"] = session_open + pd.to_timedelta((offset_minutes // 5) * 5, unit="m")
    group_cols = [c for c in ("exchange", "tradingsymbol", "instrument_token") if c in frame.columns] + ["_bar_open"]
    rows = []
    for key, group in frame.groupby(group_cols, sort=True, dropna=False):
        key_values = key if isinstance(key, tuple) else (key,)
        row = dict(zip(group_cols, key_values))
        row.update(
            {
                "timestamp": row.pop("_bar_open"),
                "open": group["open"].iloc[0],
                "high": group["high"].max(),
                "low": group["low"].min(),
                "close": group["close"].iloc[-1],
                "volume": group["volume"].sum(),
                "oi": group["oi"].iloc[-1] if "oi" in group.columns else 0,
                "bar_label": "bar_open",
                "source_minutes": int(len(group)),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


OPTION_RE = re.compile(
    r"(?P<underlying>SENSEX|SENSEX50|NIFTY|BANKNIFTY)[A-Z0-9]*?(?P<strike>\d{4,6})(?P<option_type>CE|PE)$",
    re.IGNORECASE,
)


def parse_option_symbol(symbol: str) -> dict[str, Any]:
    text = str(symbol or "").upper().strip()
    match = OPTION_RE.search(text)
    if not match:
        raise ValueError(f"not an option symbol: {symbol}")
    return {
        "underlying": match.group("underlying").upper(),
        "strike": int(match.group("strike")),
        "option_type": match.group("option_type").upper(),
    }


def classify_expiry_regime(expiry: date) -> str:
    weekday = expiry.weekday()
    if weekday == 4:
        return "FRIDAY_EXPIRY_REGIME"
    if weekday == 1:
        return "TUESDAY_EXPIRY_REGIME"
    if weekday == 3:
        return "THURSDAY_EXPIRY_REGIME"
    return "HOLIDAY_SHIFTED_OR_EXCEPTIONAL"


def constituent_coverage(expected: pd.DataFrame, available: pd.DataFrame) -> dict[str, Any]:
    expected_symbols = set(expected["trading_symbol"].astype(str))
    available_symbols = set(available["tradingsymbol"].astype(str))
    present = expected_symbols & available_symbols
    weight_col = "weight" if "weight" in expected.columns else None
    weight = 0.0
    if weight_col:
        weight = float(expected[expected["trading_symbol"].astype(str).isin(present)][weight_col].fillna(0).sum())
    return {
        "expected_constituents": int(len(expected_symbols)),
        "available_constituents": int(len(present)),
        "missing_constituents": sorted(expected_symbols - present),
        "weight_coverage": weight,
        "equal_weight_coverage": (len(present) / len(expected_symbols)) if expected_symbols else 0.0,
    }


def future_dependent_strike_selection(selection_ts: Any, underlying_ts: Any) -> bool:
    return normalize_ist_timestamp(underlying_ts) > normalize_ist_timestamp(selection_ts)


def _read_tabular_preview(path: Path) -> dict[str, Any]:
    suffixes = "".join(path.suffixes[-2:]).lower()
    try:
        if path.stat().st_size > 50_000_000:
            return {"preview_skipped": "file_over_50mb"}
    except OSError:
        return {"preview_skipped": "stat_failed"}
    try:
        if path.suffix.lower() == ".parquet":
            try:
                import pyarrow.parquet as pq

                meta = pq.ParquetFile(path)
                result = {
                    "row_count": int(meta.metadata.num_rows),
                    "columns": [str(name) for name in meta.schema.names[:80]],
                    "preview_skipped": "parquet_metadata_only",
                }
                return result
            except Exception as exc:
                return {"read_error": f"{type(exc).__name__}:{exc}"}
        elif path.suffix.lower() == ".csv":
            df = pd.read_csv(path, nrows=5000)
        elif suffixes.endswith(".csv.gz"):
            df = pd.read_csv(path, compression="gzip", nrows=5000)
        else:
            return {}
    except Exception as exc:
        return {"read_error": f"{type(exc).__name__}:{exc}"}
    ts_col = next((c for c in ("timestamp", "date", "datetime", "ts") if c in df.columns), None)
    result: dict[str, Any] = {"row_count": int(len(df)), "columns": list(map(str, df.columns[:80]))}
    if ts_col:
        parsed = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
        if parsed.notna().any():
            result["minimum_timestamp"] = parsed.min().isoformat()
            result["maximum_timestamp"] = parsed.max().isoformat()
    for token_col in ("instrument_token", "token", "instrument_key"):
        if token_col in df.columns:
            result["instrument_count"] = int(df[token_col].dropna().astype(str).nunique())
            break
    return result


def classify_source(path: Path) -> str:
    lower = str(path).lower()
    if "instrument" in lower or "contract" in lower:
        return "instrument_master_or_contract_registry"
    if "candidate_replay" in lower:
        return "candidate_replay_archive_or_manifest"
    if "sensex" in lower and path.suffix.lower() in {".parquet", ".csv"}:
        return "sensex_market_data_candidate"
    return "research_or_evidence_file"


def inventory_sources(search_roots: Iterable[Path]) -> list[dict[str, Any]]:
    needles = ("sensex", "sensex50", "bfo", "candidate_replay", "instruments", "contract")
    records: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path in seen or not path.is_file():
                continue
            text = str(path).lower()
            if not any(n in text for n in needles):
                continue
            seen.add(path)
            stat = path.stat()
            rec = {
                "absolute_path": str(path.resolve()),
                "type": classify_source(path),
                "size": int(stat.st_size),
                "sha256": sha256_file(path) if stat.st_size <= 250_000_000 else "SKIPPED_LARGE_FILE",
                "immutable": str(path).startswith("/Users/madhuram/tradebot-ml-evidence"),
                "trusted": "UNKNOWN",
                "suitable_for_research": False,
                "rejection_reason": "not yet proven complete for SENSEX convexity acquisition",
            }
            rec.update(_read_tabular_preview(path))
            records.append(rec)
    return sorted(records, key=lambda r: (r["type"], r["absolute_path"]))


def recover_option_registry(source_records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for rec in source_records:
        path = Path(rec["absolute_path"])
        if "instrument" not in str(path).lower() and "contract" not in str(path).lower():
            continue
        try:
            if path.stat().st_size > 10_000_000:
                continue
        except OSError:
            continue
        candidates: list[dict[str, Any]] = []
        try:
            if path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(payload, dict):
                    for value in payload.values():
                        if isinstance(value, list):
                            candidates.extend(x for x in value if isinstance(x, dict))
                elif isinstance(payload, list):
                    candidates.extend(x for x in payload if isinstance(x, dict))
            elif path.suffix.lower() == ".csv":
                with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
                    candidates.extend(csv.DictReader(handle))
            elif "".join(path.suffixes[-2:]).lower().endswith(".json.gz"):
                with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
                    payload = json.load(handle)
                if isinstance(payload, list):
                    candidates.extend(x for x in payload if isinstance(x, dict))
                elif isinstance(payload, dict):
                    for value in payload.values():
                        if isinstance(value, list):
                            candidates.extend(x for x in value if isinstance(x, dict))
        except Exception:
            continue
        for item in candidates:
            symbol = str(item.get("tradingsymbol") or item.get("trading_symbol") or item.get("instrument_key") or "")
            if "SENSEX" not in symbol.upper() or not symbol.upper().endswith(("CE", "PE")):
                continue
            try:
                parsed = parse_option_symbol(symbol)
            except ValueError:
                parsed = {"underlying": "SENSEX", "strike": item.get("strike"), "option_type": symbol[-2:].upper()}
            rows.append(
                {
                    "instrument_token": item.get("instrument_token") or item.get("token"),
                    "exchange": item.get("exchange") or item.get("segment"),
                    "tradingsymbol": symbol,
                    "underlying": parsed["underlying"],
                    "expiry_date": str(item.get("expiry") or item.get("expiry_date") or ""),
                    "strike": parsed["strike"] or item.get("strike"),
                    "option_type": parsed["option_type"],
                    "lot_size": item.get("lot_size"),
                    "tick_size": item.get("tick_size"),
                    "source_registry_file": str(path.resolve()),
                    "registry_file_sha256": rec.get("sha256"),
                    "confidence": "HIGH" if item.get("instrument_token") else "LOW_NO_TOKEN",
                    "kite_historical_retrieval": "NOT_ATTEMPTED",
                }
            )
    columns = [
        "instrument_token",
        "exchange",
        "tradingsymbol",
        "underlying",
        "expiry_date",
        "strike",
        "option_type",
        "lot_size",
        "tick_size",
        "source_registry_file",
        "registry_file_sha256",
        "confidence",
        "kite_historical_retrieval",
    ]
    return pd.DataFrame(rows, columns=columns).drop_duplicates().reset_index(drop=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def build_frozen_spec(latest_completed_trade_date: str) -> dict[str, Any]:
    return {
        "research_name": "SENSEX Late-Session Convexity Ignition V1",
        "scope": "DATA_ACQUISITION_ONLY",
        "date_range": {"start": "2024-07-01", "end": latest_completed_trade_date, "exclude_current_incomplete_session": True},
        "source_interval": "minute",
        "derived_intervals": ["3minute_optional", "5minute"],
        "session": {"timezone": IST, "start": "09:15:00", "end": "15:30:00", "bar_label": "bar_open"},
        "instrument_groups": [
            "SENSEX underlying",
            "available SENSEX constituents",
            "SENSEX futures where token history permits",
            "SENSEX options where token history permits",
            "NIFTY 50 underlying control",
            "BANKNIFTY underlying control",
        ],
        "constituent_mapping_authority_order": [
            "official BSE/SP BSE historical constituent or weight records already available",
            "repository-cached official files",
            "reproducible archived reference data",
            "current membership fallback labelled non-historical",
        ],
        "quality_gates": {
            "minimum_constituents": 27,
            "minimum_weight_coverage": 0.90,
            "no_future_constituent_candles": True,
            "same_completed_bar_boundary_as_sensex": True,
        },
        "forbidden_claims": [
            "option certification",
            "executable bid/ask reconstruction",
            "profitability",
            "production readiness",
        ],
    }


def credential_status() -> dict[str, Any]:
    return {
        "KITE_API_KEY_present": bool(os.getenv("KITE_API_KEY")),
        "KITE_API_SECRET_present": bool(os.getenv("KITE_API_SECRET")),
        "KITE_ACCESS_TOKEN_present": bool(os.getenv("KITE_ACCESS_TOKEN")),
        "secrets_printed": False,
    }


def build_readiness_report(payload: dict[str, Any]) -> str:
    registry = payload["option_registry_report"]
    inv = payload["inventory_summary"]
    verdict = payload["final_readiness_verdict"]
    return "\n".join(
        [
            "# SENSEX Late-Session Convexity V1 Data Readiness",
            "",
            f"Final verdict: `{verdict}`",
            "",
            "## Answers",
            f"1. Complete SENSEX underlying candles: {payload['sensex_underlying_coverage']}.",
            "2. Historically valid SENSEX constituent panel: NO.",
            "3. Historical weights: not proven; approximate/equal-weight panels only if later sourced and labelled.",
            "4. Expiry regimes covered: " + ", ".join(payload["expiry_regimes_covered"]),
            f"5. Historical SENSEX option tokens recovered: {registry['contracts_found']}.",
            f"6. Expiries with usable option OHLCV: {registry['successful_kite_lookups']}.",
            "7. Normal-day versus expiry-day underlying discovery: BLOCKED until complete underlying plus calendar audit passes.",
            "8. Constituent-event-graph discovery: BLOCKED until historical constituent membership/weights and >=27/30 coverage pass.",
            "9. Option-premium discovery: BLOCKED unless recovered tokens also produce complete OHLCV.",
            "10. Without historical bid/ask: no executable entry/exit, spread, profitability, or production-readiness claims.",
            "",
            "## Kite Limitation",
            *[f"- {item['finding']} Implication: {item['implication']}" for item in payload["kite_limitation_findings"]],
            "",
            "## Inventory Summary",
            f"- Sources indexed: {inv['sources_indexed']}",
            f"- SENSEX-like sources: {inv['sensex_like_sources']}",
            f"- Instrument/contract registries: {inv['instrument_registry_sources']}",
            "",
            "## Blockers",
            *[f"- {blocker}" for blocker in payload["blockers"]],
        ]
    ) + "\n"
