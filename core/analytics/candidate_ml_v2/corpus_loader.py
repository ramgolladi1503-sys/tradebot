from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION
from .market_corpus import MARKET_CORPUS_LANE, normalize_tick_frame, validate_materialized_parquet


_TIMESTAMP_ALIASES = (
    "ts",
    "timestamp",
    "timestamp_epoch_ms",
    "ts_epoch_ms",
    "timestamp_epoch",
    "ts_epoch",
    "event_timestamp",
    "exchange_timestamp",
    "received_at",
    "created_at",
    "last_trade_time",
)
_INSTRUMENT_ALIASES = ("instrument_key", "instrument", "symbol", "tradingsymbol", "trading_symbol")
_PRICE_ALIASES = ("ltp", "last_price", "close", "price")


def _stream_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    by_lower = {str(column).strip().lower(): str(column) for column in frame.columns}
    for alias in aliases:
        if alias in by_lower:
            return by_lower[alias]
    return None


def _canonicalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    timestamp = _find_column(frame, _TIMESTAMP_ALIASES)
    instrument = _find_column(frame, _INSTRUMENT_ALIASES)
    price = _find_column(frame, _PRICE_ALIASES)
    if timestamp is None:
        raise ValueError("market_corpus_timestamp_column_missing")
    if instrument is None:
        raise ValueError("market_corpus_instrument_column_missing")
    if price is None:
        raise ValueError("market_corpus_price_column_missing")
    if timestamp != "timestamp":
        rename[timestamp] = "timestamp"
    if instrument != "instrument_key":
        rename[instrument] = "instrument_key"
    if price != "ltp":
        rename[price] = "ltp"
    return frame.rename(columns=rename)


def load_market_tick_corpus_resilient(
    paths: Iterable[str | Path],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw_path in sorted({str(Path(item)) for item in paths}):
        path = Path(raw_path)
        try:
            validate_materialized_parquet(path)
            raw = pd.read_parquet(path)
            canonical = _canonicalize_columns(raw)
            normalized = normalize_tick_frame(canonical, source_file=str(path))
            if normalized.empty:
                raise ValueError("market_corpus_no_normalized_rows")
            accepted.append(
                {
                    "path": str(path),
                    "sha256": _stream_sha256(path),
                    "bytes": int(path.stat().st_size),
                    "raw_rows": int(raw.shape[0]),
                    "normalized_rows": int(normalized.shape[0]),
                    "columns": sorted(str(column) for column in raw.columns),
                }
            )
            frames.append(normalized)
        except Exception as exc:
            columns: list[str] = []
            try:
                columns = sorted(str(column) for column in pd.read_parquet(path).columns)
            except Exception:
                pass
            rejected.append(
                {
                    "path": str(path),
                    "reason": f"{type(exc).__name__}:{exc}",
                    "columns": columns,
                    "bytes": int(path.stat().st_size) if path.exists() else 0,
                }
            )
    if not frames:
        rejection_summary = {
            "rejected_file_count": len(rejected),
            "sample": rejected[:10],
        }
        raise ValueError(
            "market_corpus_no_readable_rows:" + json.dumps(rejection_summary, sort_keys=True)
        )
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["timestamp", "instrument_key", "ltp"], keep="last"
    )
    combined = combined.sort_values(
        ["timestamp", "instrument_key"], kind="stable"
    ).reset_index(drop=True)
    contract_payload = json.dumps(
        {"accepted": accepted, "rejected": rejected},
        sort_keys=True,
        separators=(",", ":"),
    )
    manifest = {
        "lane": MARKET_CORPUS_LANE,
        "schema_version": SCHEMA_VERSION,
        "source_files": accepted,
        "rejected_files": rejected,
        "source_file_count": int(len(accepted)),
        "rejected_file_count": int(len(rejected)),
        "normalized_rows": int(combined.shape[0]),
        "source_contract_sha256": sha256(contract_payload.encode("utf-8")).hexdigest(),
        **SAFETY_CONTRACT,
    }
    return combined, manifest


__all__ = ["load_market_tick_corpus_resilient"]
