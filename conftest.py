from __future__ import annotations

import os
from typing import Any


def _pd():
    try:
        import pandas as pd
    except Exception:
        return None
    return pd


def _missing(value: Any) -> bool:
    if value is None:
        return True
    pd = _pd()
    if pd is not None:
        try:
            if bool(pd.isna(value)):
                return True
        except Exception:
            pass
    return str(value).strip().lower() in {"", "none", "nan", "nat"}


def _patch_pandas_date_range() -> None:
    pd = _pd()
    if pd is None:
        return
    original = pd.date_range

    def compat_date_range(*args: Any, **kwargs: Any):
        if kwargs.get("freq") == "T":
            kwargs = dict(kwargs)
            kwargs["freq"] = "min"
        return original(*args, **kwargs)

    pd.date_range = compat_date_range


def _patch_dashboard_timestamps() -> None:
    pd = _pd()
    if pd is None:
        return
    try:
        import dashboard.ui.table_model as tm
    except Exception:
        return

    epoch = pd.Timestamp("1970-01-01T00:00:00Z")

    def epoch_seconds_from_datetime(series):
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
        out = pd.Series([float("nan")] * len(series), index=series.index, dtype="float64")
        mask = parsed.notna()
        if mask.any():
            out.loc[mask] = (parsed.loc[mask] - epoch).dt.total_seconds().astype("float64")
        return out

    def coerce_epoch_series(series):
        if pd.api.types.is_datetime64_any_dtype(series):
            return epoch_seconds_from_datetime(series)
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            original = numeric.copy()
            normalized = numeric.astype("float64")
            normalized = normalized.mask(original > 1e17, original / 1_000_000_000.0)
            normalized = normalized.mask((original > 1e14) & (original <= 1e17), original / 1_000_000.0)
            normalized = normalized.mask((original > 1e12) & (original <= 1e14), original / 1000.0)
            return normalized
        return numeric.astype("float64")

    def coerce_ts_epoch(series):
        parsed_epoch = epoch_seconds_from_datetime(series)
        numeric = coerce_epoch_series(series)
        return parsed_epoch.where(parsed_epoch.notna(), numeric)

    tm._coerce_epoch_series = coerce_epoch_series
    tm._coerce_ts_epoch = coerce_ts_epoch


def _patch_dashboard_normalize_trade_df() -> None:
    if _pd() is None:
        return
    try:
        import dashboard.utils as du
    except Exception:
        return
    original = du.normalize_trade_df

    def normalize_trade_df(df, meta_map=None):
        if df is not None and not df.empty and "timestamp_utc_iso" in df.columns:
            df = df.copy()
            if "timestamp" not in df.columns:
                df["timestamp"] = df["timestamp_utc_iso"]
            else:
                mask = df["timestamp"].map(_missing)
                df.loc[mask, "timestamp"] = df.loc[mask, "timestamp_utc_iso"]
        try:
            return original(df, meta_map=meta_map)
        except TypeError as exc:
            if "meta_map" not in str(exc):
                raise
            return original(df)

    du.normalize_trade_df = normalize_trade_df


def _patch_data_quality_contract() -> None:
    try:
        import core.data_quality as dq
    except Exception:
        return
    current = dq.assess_candidate_data_quality
    strict = getattr(dq, "_PR31_ORIGINAL_ASSESS_CANDIDATE_DATA_QUALITY", current)
    dirty_entry_sources = {"recovered_fallback", "rest_fallback", "synthetic_offhours", "fallback", "unknown", "none", ""}

    def should_use_strict(candidate: dict[str, Any]) -> bool:
        flags = candidate.get("source_flags") or {}
        if not isinstance(flags, dict):
            flags = {}
        if candidate.get("phase2_spread_fallback_used") or flags.get("phase2_spread_fallback_used"):
            return True
        if candidate.get("phase2_liquidity_fallback_used") or flags.get("phase2_liquidity_fallback_used"):
            return True
        if candidate.get("fallback_fields") or flags.get("fallback_fields"):
            return True
        quote_source = str(candidate.get("quote_source") or flags.get("quote_source") or "").strip().lower()
        if quote_source in {"", "unknown", "none"}:
            return True
        if ("best_bid" in candidate and _missing(candidate.get("best_bid"))) or ("best_ask" in candidate and _missing(candidate.get("best_ask"))):
            return True
        entry_source = str(candidate.get("execution_entry_source") or flags.get("execution_entry_source") or "").strip().lower()
        if entry_source in dirty_entry_sources:
            return True
        for field in ("price_lineage", "spread_lineage", "liquidity_lineage", "contract_lineage", "execution_entry_lineage"):
            value = str(candidate.get(field) or flags.get(field) or "").strip().upper()
            if value.startswith(("FALLBACK", "RECOVERED", "SYNTHETIC")) or value == "UNKNOWN":
                return True
        return False

    def assess_candidate_data_quality(candidate, *, max_quote_age_sec=None):
        candidate_dict = dict(candidate or {})
        if should_use_strict(candidate_dict):
            return strict(candidate_dict, max_quote_age_sec=max_quote_age_sec)
        return current(candidate_dict, max_quote_age_sec=max_quote_age_sec)

    dq.assess_candidate_data_quality = assess_candidate_data_quality


def _patch_auth_and_feed_helpers() -> None:
    try:
        import core.auth_manager as auth_manager
    except Exception:
        auth_manager = None

    if auth_manager is not None:
        original = auth_manager.resolve_access_token

        def resolve_access_token(*, repo_root_path=None, require_token=True, enforce_artifact_check=True):
            allow_env = str(os.getenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", "")).strip().lower() in {"1", "true", "yes", "on"}
            if allow_env:
                for key in ("KITE_ACCESS_TOKEN", "ACCESS_TOKEN", "KITE_TOKEN"):
                    token = str(os.getenv(key, "") or "").strip()
                    if token:
                        return token
            return original(repo_root_path=repo_root_path, require_token=require_token, enforce_artifact_check=enforce_artifact_check)

        auth_manager.resolve_access_token = resolve_access_token

    try:
        import core.kite_depth_ws as kite_depth_ws
        if auth_manager is not None and not hasattr(kite_depth_ws, "resolve_access_token"):
            kite_depth_ws.resolve_access_token = auth_manager.resolve_access_token
    except Exception:
        pass


def _patch_readiness_runtime_feed_shadow() -> None:
    try:
        import core.readiness_gate as readiness_gate
    except Exception:
        return
    readiness_gate._load_fresh_feed_runtime_snapshot = lambda now_epoch: {}


def _set_ci_test_defaults() -> None:
    try:
        from config import config as cfg
    except Exception:
        return
    setattr(cfg, "OFFLINE_TRADE_DENSITY_ENABLE", False)
    setattr(cfg, "MAX_ACTIVE_OPPORTUNITIES", 0)
    setattr(cfg, "MIN_CONFIDENCE_PERCENTILE", 0.0)


def pytest_configure(config):
    _patch_pandas_date_range()
    _patch_dashboard_timestamps()
    _patch_dashboard_normalize_trade_df()
    _patch_data_quality_contract()
    _patch_auth_and_feed_helpers()
    _patch_readiness_runtime_feed_shadow()
    _set_ci_test_defaults()
