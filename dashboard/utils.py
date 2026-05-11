"""Dashboard utilities for trade table normalization.

Migration note:
Normalize trade tables to a consistent speed-trader schema and
surface data issues via ui_warning instead of silent failures.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from core.trade_identity import compute_trade_key, derive_strategy_id
from core.time_utils import format_ts_ist
from dashboard.ui.utils.derive_fields import parse_option_side

logger = logging.getLogger(__name__)

_ENTRY_STATUSES_WITH_QUOTE_BACKFILL = {
    "",
    "OK",
    "LIVE_OK",
    "VALID",
    "NONE",
    "PRICE_MISMATCH",
    "REST_FALLBACK",
}


REQUIRED_COLUMNS = [
    "timestamp",
    "timestamp_ist",
    "trade_key",
    "trade_status",
    "first_seen",
    "last_seen",
    "update_count",
    "symbol",
    "instrument_id",
    "expiry_date",
    "tradingsymbol",
    "strike",
    "option_type",
    "side",
    "entry",
    "expected_entry",
    "fill_entry",
    "signal_price",
    "current_ltp",
    "suggested_entry",
    "price_age_sec",
    "entry_status",
    "target",
    "stop",
    "status",
    "activation_price",
    "activated_ts",
    "current_ltp_ts",
    "pnl_points",
    "pnl_cash",
    "activation_reason",
    "invalidation_reason",
    "confidence",
    "direction",
    "global_confidence",
    "permission",
    "permission_reason",
    "countertrend",
    "raw_signal_confidence",
    "regime",
    "regime_confidence",
    "day_confidence",
    "orb_bias",
]


def _coerce_opt_type(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ("CE", "CALL"):
        return "CE"
    if text in ("PE", "PUT"):
        return "PE"
    return None


def _coerce_expiry(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NONE", "NA", "N/A", "NAN"}:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return text


def _coerce_strike(value) -> str | float | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text == "ATM":
        return "ATM"
    try:
        return float(text)
    except Exception:
        return None


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _ensure_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df


def normalize_trade_df(df: pd.DataFrame | None, meta_map: dict | None = None) -> pd.DataFrame:
    """
    Normalize heterogeneous trade rows into a consistent schema.
    """
    if df is None:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))
    if df.empty:
        return _ensure_columns(df.copy(), REQUIRED_COLUMNS + ["ui_warning"])

    norm = df.copy()
    norm = _ensure_columns(norm, REQUIRED_COLUMNS + ["ui_warning"])
    canonical_entry_fields = {
        "execution_entry",
        "execution_entry_source",
        "execution_entry_status",
        "display_entry",
        "display_entry_source",
        "display_entry_status",
        "entry_reason",
        "entry_clear_reason",
    }
    canonical_entry = any(col in norm.columns for col in canonical_entry_fields)

    # Map synonyms
    synonym_map = {
        "expiry": "expiry_date",
        "type": "option_type",
        "right": "option_type",
        "stop_loss": "stop",
        "tp": "target",
        "take_profit": "target",
        "target_premium": "target",
        "target_points": "target",
        "stop_premium": "stop",
        "activation_ts": "activated_ts",
        "symbol": "symbol",
        "underlying": "symbol",
        "instrument_token": "instrument_id",
    }
    for src, dst in synonym_map.items():
        if src in norm.columns and dst in norm.columns:
            norm[dst] = norm[dst].where(norm[dst].notna(), norm[src])

    warnings = []
    for idx, row in norm.iterrows():
        try:
            row_warn = []
            expiry_val = _coerce_expiry(row.get("expiry_date"))
            if expiry_val:
                norm.at[idx, "expiry_date"] = expiry_val

            opt_type = _coerce_opt_type(row.get("option_type"))
            if not opt_type:
                opt_type = _coerce_opt_type(parse_option_side(row.get("tradingsymbol")))
            if not opt_type:
                opt_type = _coerce_opt_type(parse_option_side(row.get("instrument_id")))
            if opt_type:
                norm.at[idx, "option_type"] = opt_type

            strike_val = _coerce_strike(row.get("strike"))
            if strike_val is not None:
                norm.at[idx, "strike"] = strike_val
            elif row.get("strike") not in (None, "", "None"):
                row_warn.append("strike_invalid")

            ts = row.get("timestamp")
            if not ts:
                for alt in ("created_at", "queue_ts", "ts"):
                    if row.get(alt):
                        ts = row.get(alt)
                        break
            last_seen = row.get("last_seen")
            if last_seen not in (None, "", "None"):
                ts = last_seen
            if not ts:
                ts = datetime.now(timezone.utc).isoformat()
                row_warn.append("timestamp_fallback")
            norm.at[idx, "timestamp"] = str(ts)
            norm.at[idx, "timestamp_ist"] = format_ts_ist(ts) or format_ts_ist(datetime.now(timezone.utc))

            conf = _to_float(row.get("confidence"))
            norm.at[idx, "confidence"] = conf if conf is not None else None

            # Preserve engine-provided entry semantics; do not backfill entry here.

            status = str(row.get("status") or "PLANNING").upper()
            norm.at[idx, "status"] = status

            instrument_id = row.get("instrument_id")
            if instrument_id not in (None, "", "None"):
                instr_text = str(instrument_id)
                if norm.at[idx, "tradingsymbol"] in (None, "", "None") and not instr_text.isdigit():
                    norm.at[idx, "tradingsymbol"] = instr_text
            tradingsymbol = row.get("tradingsymbol")
            if tradingsymbol not in (None, "", "None") and norm.at[idx, "instrument_id"] in (None, "", "None"):
                norm.at[idx, "instrument_id"] = str(tradingsymbol)

            trade_key = row.get("trade_key")
            if not trade_key:
                strategy_id = derive_strategy_id(row.get("strategy_id"), row.get("strategy") or row.get("generator"))
                trade_key = compute_trade_key(
                    row.get("symbol"),
                    row.get("expiry_date"),
                    row.get("strike"),
                    row.get("option_type"),
                    row.get("side"),
                    strategy_id,
                )
                norm.at[idx, "trade_key"] = trade_key
            if norm.at[idx, "trade_status"] in (None, "", "None"):
                norm.at[idx, "trade_status"] = row.get("trade_status") or "NEW"
            if norm.at[idx, "first_seen"] in (None, "", "None"):
                norm.at[idx, "first_seen"] = norm.at[idx, "timestamp"]
            if norm.at[idx, "last_seen"] in (None, "", "None"):
                norm.at[idx, "last_seen"] = norm.at[idx, "timestamp"]
            if norm.at[idx, "update_count"] in (None, "", "None"):
                norm.at[idx, "update_count"] = 0

            if row_warn:
                norm.at[idx, "ui_warning"] = ",".join(sorted(set(row_warn)))
        except Exception as exc:
            logger.warning("normalize_trade_df row_failed: %s", exc)
            norm.at[idx, "ui_warning"] = "normalize_failed"
            warnings.append(str(exc))
            continue

    if warnings:
        logger.warning("normalize_trade_df warnings=%s", warnings[:5])
    return dedupe_by_trade_key(norm)


def dedupe_by_trade_key(df: pd.DataFrame, sort_by: str | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "trade_key" not in df.columns:
        return df
    sort_col = sort_by
    if not sort_col:
        for candidate in ("last_seen", "timestamp"):
            if candidate in df.columns:
                sort_col = candidate
                break
    if sort_col and sort_col in df.columns:
        df = df.sort_values(sort_col, ascending=False)
    return df.drop_duplicates(subset=["trade_key"], keep="first").copy()


def filter_by_permission(df: pd.DataFrame, permission: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    perm = str(permission or "").strip().upper()
    if "permission" not in df.columns:
        return df
    series = df["permission"].fillna("").astype(str).str.upper()
    return df[series == perm].copy()

# _PR31_NORMALIZE_TRADE_DF_TIMESTAMP_PRESERVE
_PR31_PREV_NORMALIZE_TRADE_DF = normalize_trade_df

def normalize_trade_df(df):
    original_timestamp = None
    try:
        if df is not None and "timestamp" in df.columns:
            original_timestamp = df["timestamp"].copy()
    except Exception:
        original_timestamp = None

    out = _PR31_PREV_NORMALIZE_TRADE_DF(df)

    try:
        if original_timestamp is not None and "timestamp" in out.columns:
            bad = out["timestamp"].astype(str).isin({"nan", "NaN", "None", "NaT", ""})
            out.loc[bad, "timestamp"] = original_timestamp.loc[bad].astype(str)
    except Exception:
        pass

    return out
