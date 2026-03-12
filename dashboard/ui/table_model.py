"""Trader table view-model shaping.

Migration note:
Introduces a canonical trade table schema and compact speed-trader views.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pandas as pd
from dashboard.ui.utils.derive_fields import parse_option_side

_ENTRY_STATUSES_WITH_QUOTE_BACKFILL = {
    "",
    "OK",
    "LIVE_OK",
    "VALID",
    "NONE",
    "PRICE_MISMATCH",
    "REST_FALLBACK",
}

_CANONICAL_ADVISORY_FIELDS = {
    "execution_entry",
    "execution_entry_source",
    "execution_entry_status",
    "display_entry",
    "display_entry_source",
    "display_entry_status",
    "entry_reason",
    "entry_clear_reason",
    "hard_blockers",
    "soft_penalties",
    "warnings",
    "confidence_raw",
    "confidence_penalty",
    "confidence_final",
    "advisory_visible",
    "is_executable",
    "execution_status",
    "entry_source",
}


CANONICAL_COLUMNS = [
    "last_seen_ts",
    "symbol",
    "expiry_date",
    "strike",
    "opt_type",
    "side",
    "status",
    "entry",
    "execution_entry",
    "display_entry",
    "stop",
    "target",
    "live_ltp",
    "price_age_sec",
    "pnl_points",
    "pnl_cash",
    "qty",
    "confidence",
    "confidence_raw",
    "confidence_penalty",
    "confidence_final",
    "readiness",
    "execution_status",
    "entry_status",
    "entry_source",
    "execution_entry_status",
    "display_entry_status",
    "execution_entry_source",
    "display_entry_source",
    "hard_blockers",
    "soft_penalties",
    "warnings",
    "trade_key",
    "tradingsymbol",
]


NUMERIC_COLUMNS = [
    "strike",
    "entry",
    "stop",
    "target",
    "live_ltp",
    "price_age_sec",
    "pnl_points",
    "pnl_cash",
    "qty",
    "confidence",
    "confidence_raw",
    "confidence_penalty",
    "confidence_final",
]


def _normalize_option_right(value) -> str:
    text = str(value or "").strip().upper()
    if text in {"CE", "CALL", "C"}:
        return "CE"
    if text in {"PE", "PUT", "P"}:
        return "PE"
    return ""


def _option_right_for_identity(row) -> str:
    for field in ("opt_type", "option_type", "type", "right", "option_side", "contract_side"):
        right = _normalize_option_right(row.get(field))
        if right:
            return right
    for field in ("tradingsymbol", "instrument_id", "symbol"):
        right = parse_option_side(row.get(field))
        if right in {"CE", "PE"}:
            return right
    return ""


def _is_option_row(row) -> bool:
    instrument_type = str(row.get("instrument_type") or row.get("instrument") or "").strip().upper()
    if instrument_type == "OPT":
        return True
    if _option_right_for_identity(row):
        return True
    return False


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS + ["identity"])


def _status_badge(value) -> str:
    status = str(value or "PLANNING").upper()
    mapping = {
        "ACTIVE": "ACTIVE",
        "PLANNING": "PLANNING",
        "ADVISORY_ONLY": "ADVISORY",
        "READY": "READY",
        "BLOCKED_APPROVAL": "BLOCKED_APPROVAL",
        "BLOCKED_CONTRACT": "BLOCKED_CONTRACT",
        "QUEUED_REVIEW": "REVIEW",
        "QUEUE": "REVIEW",
        "REVALIDATED": "PLANNING",
        "UPDATED": "PLANNING",
        "EXITED": "EXITED",
        "INVALIDATED": "INVALID",
        "EXPIRED": "EXPIRED",
    }
    label = mapping.get(status, status)
    icon_map = {
        "ACTIVE": "ACTIVE",
        "PLANNING": "PLANNING",
        "ADVISORY": "ADVISORY",
        "READY": "READY",
        "BLOCKED_APPROVAL": "BLOCKED_APPROVAL",
        "BLOCKED_CONTRACT": "BLOCKED_CONTRACT",
        "REVIEW": "REVIEW",
        "EXITED": "EXITED",
        "INVALID": "INVALID",
        "EXPIRED": "EXPIRED",
    }
    return f"{icon_map.get(label, label)}"


def normalize_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    out = df.copy()
    rename_map = {
        "timestamp": "last_seen_ts",
        "created_at": "last_seen_ts",
        "ts": "last_seen_ts",
        "last_seen": "last_seen_ts",
        "type": "opt_type",
        "option_type": "opt_type",
        "right": "opt_type",
        "option_side": "opt_type",
        "contract_side": "opt_type",
        "pnl_1qty": "pnl_points",
        "pnl_1lot": "pnl_cash",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    canonical_advisory = any(col in out.columns for col in _CANONICAL_ADVISORY_FIELDS)
    if out.columns.duplicated().any():
        # Merge duplicate columns by taking the first non-null value left-to-right.
        deduped: dict[str, pd.Series] = {}
        for col in pd.Index(out.columns).unique():
            same = out.loc[:, out.columns == col]
            if same.shape[1] == 1:
                deduped[col] = same.iloc[:, 0]
            else:
                deduped[col] = same.bfill(axis=1).iloc[:, 0]
        out = pd.DataFrame(deduped, index=out.index)
    if "target" not in out.columns and "target_points" in out.columns:
        out["target"] = out["target_points"]
    if "suggested_entry" in out.columns and not canonical_advisory:
        if "entry" not in out.columns:
            out["entry"] = None
        suggested = pd.to_numeric(out["suggested_entry"], errors="coerce")
        current_ltp = pd.to_numeric(out["current_ltp"], errors="coerce") if "current_ltp" in out.columns else None
        entry_price = pd.to_numeric(out["entry_price"], errors="coerce") if "entry_price" in out.columns else None
        if "entry_status" in out.columns:
            status = out["entry_status"].astype(str).str.upper()
            ok_mask = status.isin(_ENTRY_STATUSES_WITH_QUOTE_BACKFILL)
            suggested = suggested.where(ok_mask)
            if current_ltp is not None:
                current_ltp = current_ltp.where(ok_mask)
            if entry_price is not None:
                entry_price = entry_price.where(ok_mask)
        if current_ltp is not None:
            suggested = suggested.where(suggested.notna(), current_ltp)
        if entry_price is not None:
            suggested = suggested.where(suggested.notna(), entry_price)
        # Fail-closed: do not fill entry from signal/reference price fields.
        out["entry"] = out.get("entry").where(out.get("entry").notna(), suggested)
    if "confidence_final" in out.columns:
        out["confidence_final"] = pd.to_numeric(out["confidence_final"], errors="coerce")
        if "confidence" not in out.columns:
            out["confidence"] = out["confidence_final"]
        else:
            out["confidence"] = pd.to_numeric(out["confidence"], errors="coerce")
            out["confidence"] = out["confidence_final"].where(out["confidence_final"].notna(), out["confidence"])
    for col in CANONICAL_COLUMNS:
        if col not in out.columns:
            out[col] = None
    if "last_seen_ts" in out.columns:
        out["last_seen_ts"] = out["last_seen_ts"].where(out["last_seen_ts"].notna(), datetime.now(timezone.utc))
        out["last_seen_ts"] = pd.to_datetime(out["last_seen_ts"], errors="coerce")
        out["last_seen_ts"] = out["last_seen_ts"].fillna(pd.Timestamp.utcnow())
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["opt_type"] = out["opt_type"].apply(_normalize_option_right)
    if "tradingsymbol" in out.columns:
        inferred = out["tradingsymbol"].map(parse_option_side)
        out["opt_type"] = out["opt_type"].where(out["opt_type"].isin(["CE", "PE"]), inferred)
    if "instrument_id" in out.columns:
        inferred = out["instrument_id"].map(parse_option_side)
        out["opt_type"] = out["opt_type"].where(out["opt_type"].isin(["CE", "PE"]), inferred)
    out["opt_type"] = out["opt_type"].where(out["opt_type"].isin(["CE", "PE"]), "")
    out["status"] = out["status"].astype(str).str.upper()
    return out


def compute_trade_key(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    out = df.copy()
    if "trade_key" not in out.columns:
        out["trade_key"] = None

    def _build(row) -> str:
        existing = row.get("trade_key")
        if existing not in (None, "", "None"):
            return str(existing)
        # Stable identity key: do not include mutable price levels.
        # This prevents duplicate rows on every re-evaluation tick.
        parts = [
            str(row.get("symbol") or "").upper(),
            str(row.get("expiry_date") or ""),
            str(row.get("strike") if pd.notna(row.get("strike")) else ""),
            str(row.get("opt_type") or "").upper(),
            str(row.get("side") or "").upper(),
        ]
        raw = "|".join(parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    out["trade_key"] = out.apply(_build, axis=1)
    return out


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    out = compute_trade_key(normalize_df(df))
    out = out.sort_values("last_seen_ts", ascending=False)
    if "trade_key" in out.columns:
        out = out.drop_duplicates(subset=["trade_key"], keep="first")
    return out


def build_identity_col(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    out = df.copy()

    def _build_identity(row) -> str:
        symbol = str(row.get("symbol") or row.get("underlying") or "--")
        expiry = str(row.get("expiry_date") or row.get("expiry") or "--")
        strike = str(row.get("strike") if pd.notna(row.get("strike")) else "--")
        right = _option_right_for_identity(row)
        if _is_option_row(row):
            return "\n".join([symbol, expiry, f"{strike} {right or '--'}"])
        return "\n".join([symbol, expiry, strike])

    out["identity"] = out.apply(_build_identity, axis=1)
    return out


def select_display_df(df: pd.DataFrame, view: str) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    out = build_identity_col(df)
    view = str(view or "advisory").lower()
    if view == "active":
        cols = [
            "last_seen_ts",
            "identity",
            "status",
            "side",
            "entry",
            "stop",
            "target",
            "live_ltp",
            "pnl_points",
            "pnl_cash",
            "qty",
            "confidence",
            "trade_key",
            "tradingsymbol",
        ]
    elif view == "review":
        cols = [
            "last_seen_ts",
            "identity",
            "status",
            "side",
            "entry",
            "stop",
            "target",
            "confidence",
            "trade_key",
            "tradingsymbol",
        ]
    else:
        cols = [
            "last_seen_ts",
            "identity",
            "status",
            "readiness",
            "execution_status",
            "side",
            "entry",
            "entry_status",
            "entry_source",
            "stop",
            "target",
            "confidence_raw",
            "confidence_penalty",
            "confidence_final",
            "hard_blockers",
            "soft_penalties",
            "warnings",
            "trade_key",
            "tradingsymbol",
        ]
    cols = [c for c in cols if c in out.columns]
    out = out[cols].copy()
    if "status" in out.columns:
        out["status"] = out["status"].apply(_status_badge)
    for c in (
        "entry",
        "stop",
        "target",
        "live_ltp",
        "pnl_points",
        "pnl_cash",
        "confidence",
        "confidence_raw",
        "confidence_penalty",
        "confidence_final",
    ):
        if c in out.columns:
            out[c] = out[c].round(2)
    if "last_seen_ts" in out.columns:
        ts = pd.to_datetime(out["last_seen_ts"], errors="coerce", utc=True)
        out["last_seen_ts"] = ts.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d %H:%M:%S IST")
        out["last_seen_ts"] = out["last_seen_ts"].where(out["last_seen_ts"].notna(), "—")
    return out


def filter_non_active(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "status" not in df.columns:
        return df
    status = df["status"].astype(str).str.upper()
    return df[status != "ACTIVE"].copy()
