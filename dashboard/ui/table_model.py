"""Shared table formatting helpers for dashboard views."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _status_badge(value: Any) -> str:
    text = str(value or "").strip().upper()
    badges = {
        "READY": "🟢 READY",
        "PLANNING": "🟡 PLANNING",
        "WAIT": "🟡 WAIT",
        "BLOCKED": "🔴 BLOCKED",
        "REJECTED": "🔴 REJECTED",
        "CLOSED": "⚪ CLOSED",
    }
    return badges.get(text, text or "—")


def _format_ist_from_ts(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    formatted = parsed.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d %H:%M:%S IST")
    return formatted.where(parsed.notna(), "—")


def _coalesce_columns(out: pd.DataFrame, target: str, sources: tuple[str, ...]) -> None:
    if target not in out.columns:
        out[target] = None
    for source in sources:
        if source in out.columns:
            out[target] = out[target].where(out[target].notna(), out[source])


def _normalise_option_type(out: pd.DataFrame) -> None:
    _coalesce_columns(out, "opt_type", ("option_type", "type", "right"))
    if "tradingsymbol" in out.columns:
        symbol_text = out["tradingsymbol"].fillna("").astype(str).str.upper()
        inferred = symbol_text.str.extract(r"(CE|PE)$", expand=False)
        out["opt_type"] = out["opt_type"].where(out["opt_type"].notna(), inferred)
    if "opt_type" in out.columns:
        out["opt_type"] = out["opt_type"].fillna("").astype(str).str.upper()


def _normalise_side(out: pd.DataFrame) -> None:
    if "side" not in out.columns:
        out["side"] = None
    side = out["side"].fillna("").astype(str).str.upper()
    side = side.replace({"BUY_CALL": "BUY", "BUY_PUT": "BUY", "SELL_CALL": "SELL", "SELL_PUT": "SELL"})
    out["side"] = side


def _normalise_identity(out: pd.DataFrame) -> None:
    for column in ("symbol", "expiry_date", "strike", "tradingsymbol"):
        if column not in out.columns:
            out[column] = None
    _normalise_option_type(out)
    _normalise_side(out)
    strike = out["strike"].apply(lambda value: "" if pd.isna(value) else f"{value:g}" if isinstance(value, (int, float)) else str(value))
    identity = (
        out["symbol"].fillna("").astype(str)
        + " "
        + out["expiry_date"].fillna("").astype(str)
        + " "
        + strike
        + " "
        + out["opt_type"].fillna("").astype(str)
        + " "
        + out["side"].fillna("").astype(str)
    ).str.strip().str.replace(r"\s+", " ", regex=True)
    fallback = out["tradingsymbol"].fillna("").astype(str)
    out["identity"] = identity.where(identity.ne(""), fallback)


def _normalise_execution_truth(out: pd.DataFrame) -> None:
    if "fallback_candidate" not in out.columns:
        out["fallback_candidate"] = False
    out["fallback_candidate"] = out["fallback_candidate"].fillna(False).astype(bool)

    for column in (
        "execution_entry_source",
        "display_entry_source",
        "entry_source",
        "quote_source",
        "option_ltp_source",
        "execution_status",
        "execution_entry_status",
        "readiness",
        "status",
    ):
        if column not in out.columns:
            out[column] = None

    fallback_source = pd.Series(False, index=out.index)
    for column in ("execution_entry_source", "display_entry_source", "entry_source", "quote_source", "option_ltp_source"):
        fallback_source |= out[column].fillna("").astype(str).str.lower().str.contains("fallback", regex=False)
    out["fallback_candidate"] = out["fallback_candidate"] | fallback_source

    if "is_executable" not in out.columns:
        out["is_executable"] = False
    explicit_exec = out["is_executable"].fillna(False).astype(bool)
    status_exec = out["execution_status"].fillna("").astype(str).str.lower().eq("executable")
    entry_exec = out["execution_entry_status"].fillna("").astype(str).str.lower().eq("executable")
    readiness_exec = out["readiness"].fillna("").astype(str).str.upper().eq("READY")
    out["is_executable"] = (explicit_exec | (status_exec & entry_exec & readiness_exec)) & ~out["fallback_candidate"]

    out["ui_execution_truth"] = out["is_executable"].map({True: "EXECUTABLE", False: "ADVISORY_ONLY"})
    if "ui_execution_truth_reason" not in out.columns:
        out["ui_execution_truth_reason"] = None
    fallback_reason = out["fallback_candidate"].map({True: "fallback_source_non_executable", False: None})
    out["ui_execution_truth_reason"] = out["ui_execution_truth_reason"].where(out["ui_execution_truth_reason"].notna(), fallback_reason)


def normalize_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    if out.empty:
        return out

    aliases: dict[str, tuple[str, ...]] = {
        "entry": ("display_entry", "execution_entry", "price"),
        "stop": ("stop_loss", "sl"),
        "target": ("target_price", "tp"),
        "confidence_raw": ("confidence", "confidence_score"),
        "confidence_final": ("final_score", "rank_score", "confidence_raw", "confidence"),
        "display_entry": ("entry", "execution_entry", "price"),
        "execution_entry": ("entry", "display_entry", "price"),
        "display_ts_epoch": ("ts_epoch", "timestamp_epoch"),
        "display_ts_utc": ("timestamp", "ts_utc"),
        "display_ts_ist": ("ts_ist",),
    }
    for target, sources in aliases.items():
        _coalesce_columns(out, target, sources)

    if "display_ts_epoch" in out.columns:
        numeric_epoch = pd.to_numeric(out["display_ts_epoch"], errors="coerce")
        out["display_ts_epoch"] = numeric_epoch
        generated_utc = pd.to_datetime(numeric_epoch, errors="coerce", unit="s", utc=True)
        if "display_ts_utc" not in out.columns:
            out["display_ts_utc"] = generated_utc
        else:
            existing_utc = pd.to_datetime(out["display_ts_utc"], errors="coerce", utc=True)
            out["display_ts_utc"] = existing_utc.where(existing_utc.notna(), generated_utc)
        generated_ist = generated_utc.dt.tz_convert("Asia/Kolkata")
        if "display_ts_ist" not in out.columns:
            out["display_ts_ist"] = generated_ist
        else:
            existing_ist = pd.to_datetime(out["display_ts_ist"], errors="coerce", utc=True)
            existing_ist = existing_ist.dt.tz_convert("Asia/Kolkata")
            out["display_ts_ist"] = existing_ist.where(existing_ist.notna(), generated_ist)

    _normalise_identity(out)
    _normalise_execution_truth(out)

    defaults = (
        "status", "readiness", "execution_status", "execution_entry_status", "execution_entry_source",
        "display_entry_status", "display_entry_source", "entry_status", "entry_source", "quote_source",
        "option_ltp_source", "primary_blocker", "hard_blockers", "soft_penalties", "warnings",
        "trade_key", "candidate_class", "market_mode", "top_opportunity_truth_reason", "final_score",
        "confidence_penalty", "fresh_quote_ok", "liquidity_ok", "spread_ok", "last_seen_ts",
    )
    for col in defaults:
        if col not in out.columns:
            out[col] = None
    return out


def _format_display_ts_ist(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    formatted = parsed.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d %H:%M:%S IST")
    return formatted.where(parsed.notna(), "—")


def select_display_df(df: pd.DataFrame | None, view: str = "advisory", include_last_seen: bool = True) -> pd.DataFrame:
    out = normalize_df(df)
    if out.empty:
        return out

    if "display_ts_ist" in out.columns:
        out["display_ts_ist"] = _format_display_ts_ist(out["display_ts_ist"])

    if view == "review":
        cols = ["display_ts_ist"]
        if include_last_seen:
            cols.append("last_seen_ts")
        cols += [
            "identity", "status", "candidate_class", "final_score", "side", "entry", "stop", "target",
            "confidence_raw", "confidence_final", "primary_blocker", "hard_blockers", "soft_penalties",
            "warnings", "trade_key", "tradingsymbol",
        ]
    else:
        cols = ["display_ts_ist"]
        if include_last_seen:
            cols.append("last_seen_ts")
        cols += [
            "identity", "status", "ui_execution_truth", "ui_execution_truth_reason",
            "is_executable", "top_opportunity_truth_reason", "candidate_class", "final_score",
            "market_mode", "fallback_candidate", "quote_source", "option_ltp_source",
            "readiness", "execution_status", "side", "execution_entry",
            "execution_entry_status", "execution_entry_source", "display_entry",
            "display_entry_status", "display_entry_source", "entry", "entry_status",
            "entry_source", "stop", "target", "confidence_raw", "confidence_penalty",
            "confidence_final", "fresh_quote_ok", "liquidity_ok", "spread_ok",
            "primary_blocker", "hard_blockers", "soft_penalties", "warnings",
            "trade_key", "tradingsymbol",
        ]
    out = out[[c for c in cols if c in out.columns]].copy()
    if "status" in out.columns:
        out["status"] = out["status"].apply(_status_badge)
    for c in (
        "entry", "execution_entry", "display_entry", "stop", "target", "live_ltp",
        "pnl_points", "pnl_cash", "confidence", "confidence_raw", "confidence_penalty",
        "confidence_final",
    ):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(2)
    if "display_ts_ist" in out.columns:
        out["display_ts_ist"] = out["display_ts_ist"].where(out["display_ts_ist"].notna(), "—")
    if "last_seen_ts" in out.columns:
        out["last_seen_ts"] = _format_ist_from_ts(out["last_seen_ts"])
    return out


def filter_non_active(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "status" not in df.columns:
        return df
    active = {"READY", "PLANNING", "WAIT"}
    raw = df["status"].fillna("").astype(str).str.upper()
    return df.loc[raw.isin(active)].copy()
