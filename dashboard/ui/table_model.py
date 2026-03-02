"""Trader table view-model shaping.

Migration note:
Introduces a canonical trade table schema and compact speed-trader views.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pandas as pd


CANONICAL_COLUMNS = [
    "last_seen_ts",
    "symbol",
    "expiry_date",
    "strike",
    "opt_type",
    "side",
    "status",
    "entry",
    "stop",
    "target",
    "live_ltp",
    "price_age_sec",
    "pnl_points",
    "pnl_cash",
    "qty",
    "confidence",
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
]


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS + ["identity"])


def _status_badge(value) -> str:
    status = str(value or "PLANNING").upper()
    mapping = {
        "ACTIVE": "ACTIVE",
        "PLANNING": "PLANNING",
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
        "pnl_1qty": "pnl_points",
        "pnl_1lot": "pnl_cash",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
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
    for col in CANONICAL_COLUMNS:
        if col not in out.columns:
            out[col] = None
    if "last_seen_ts" in out.columns:
        out["last_seen_ts"] = out["last_seen_ts"].where(out["last_seen_ts"].notna(), datetime.now(timezone.utc))
        out["last_seen_ts"] = pd.to_datetime(out["last_seen_ts"], errors="coerce")
        out["last_seen_ts"] = out["last_seen_ts"].fillna(pd.Timestamp.utcnow())
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["opt_type"] = out["opt_type"].astype(str).str.upper().replace({"CALL": "CE", "PUT": "PE"})
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
        parts = [
            str(row.get("symbol") or "").upper(),
            str(row.get("expiry_date") or ""),
            str(row.get("strike") if pd.notna(row.get("strike")) else ""),
            str(row.get("opt_type") or "").upper(),
            str(row.get("side") or "").upper(),
            str(row.get("entry") if pd.notna(row.get("entry")) else ""),
            str(row.get("stop") if pd.notna(row.get("stop")) else ""),
            str(row.get("target") if pd.notna(row.get("target")) else ""),
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
    out["identity"] = out.apply(
        lambda r: "\n".join(
            [
                str(r.get("symbol") or "--"),
                str(r.get("expiry_date") or "--"),
                f"{str(r.get('strike') if pd.notna(r.get('strike')) else '--')} {str(r.get('opt_type') or '--')}",
            ]
        ),
        axis=1,
    )
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
            "side",
            "entry",
            "stop",
            "target",
            "confidence",
            "trade_key",
            "tradingsymbol",
        ]
    cols = [c for c in cols if c in out.columns]
    out = out[cols].copy()
    if "status" in out.columns:
        out["status"] = out["status"].apply(_status_badge)
    for c in ("entry", "stop", "target", "live_ltp", "pnl_points", "pnl_cash", "confidence"):
        if c in out.columns:
            out[c] = out[c].round(2)
    return out


def filter_non_active(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "status" not in df.columns:
        return df
    status = df["status"].astype(str).str.upper()
    return df[status != "ACTIVE"].copy()
