"""Trader table view-model shaping."""

from __future__ import annotations

import hashlib

import pandas as pd

from core.top_opportunity_executable_truth import classify_top_opportunity_row
from core.runtime_authority_cutover import apply_runtime_authority
from dashboard.ui.utils.derive_fields import parse_option_side

_ENTRY_STATUSES_WITH_QUOTE_BACKFILL = {
    "", "OK", "LIVE_OK", "VALID", "NONE", "PRICE_MISMATCH", "REST_FALLBACK",
}

CANONICAL_COLUMNS = """
display_ts_ist display_ts_epoch last_seen_ts symbol expiry_date strike opt_type side status
entry execution_entry display_entry stop target live_ltp price_age_sec pnl_points pnl_cash qty
confidence confidence_raw confidence_penalty confidence_final candidate_class final_score signal_score
execution_score priority_score priority_weight_signal priority_weight_execution setup_score trigger_score
entry_quality_score entry_quality_reason overextension_score overextension_penalty entry_distance_to_invalidation
session_mode strategy_regime_mode session_entry_penalty family_feedback_adjustment family_feedback_confidence
family_feedback_applied family_learning_adjustment family_cap_effective family_cap_reason family_consensus_score
family_survival_score family_survived family_reject_reason expectancy_score strategy_weight_adjustment
strategy_weight_confidence strategy_weight_applied adaptive_threshold_adjustment adaptive_threshold_impact_score
adaptive_threshold_applied adaptive_threshold_key risk_budget_ok risk_budget_reason position_size_estimate
portfolio_heat_score correlation_penalty exposure_blocker daily_kill_switch_active regime_failure_throttle
family_failure_throttle risk_learning_adjustment risk_learning_confidence rejected_at_stage rejection_reason_code
rejection_bucket rejection_severity stage_authority_warning trade_density_limit_applied density_policy_name
density_reject_reason raw_candidate_count surviving_candidate_count survival_rate executable_rate advisory_rate
no_trade_rate top_family_share starvation_flag starvation_reason warning_engine_too_timid
warning_filtering_without_edge_improvement warning_family_starvation warning_threshold_cluster rejection_impact_warning
starvation_warning edge_improved_flag filtering_without_edge_flag top_damaging_gate_rank recommended_threshold_delta
gate_protected_flag triage_recommendation edge_preserve_flag effective_session_policy effective_regime_policy
effective_risk_policy effective_family_risk_profile risk_profile_override_applied effective_family_survival_policy
aggressiveness_mode aggressiveness_adjustment aggressiveness_adjustment_applied market_mode data_state data_confidence
direction_family family_rank family_blocker family_strength family_allowed_in_context family_gate_reason
family_gate_override_applied fallback_candidate fresh_quote_ok liquidity_ok spread_ok primary_blocker selector_outcome
selection_probability simulation_outcome simulation_fill_status mfe mae simulated_pnl realized_r_multiple
stop_hit_before_target risk_plan_respected readiness execution_status entry_status entry_source execution_entry_status
display_entry_status execution_entry_source display_entry_source quote_source option_ltp_source is_executable
ui_execution_truth ui_execution_truth_reason top_opportunity_truth_reason authority_state authority_allowed authority_reason authority_blockers operator_bucket diagnostic_score opportunity_score selection_score selected_for_execution capital_assigned hard_blockers soft_penalties warnings trade_key tradingsymbol
""".split()

NUMERIC_COLUMNS = """
strike entry execution_entry display_entry stop target live_ltp price_age_sec pnl_points pnl_cash qty confidence confidence_raw
confidence_penalty confidence_final final_score signal_score execution_score priority_score priority_weight_signal
priority_weight_execution setup_score trigger_score entry_quality_score overextension_score overextension_penalty
entry_distance_to_invalidation session_entry_penalty family_feedback_adjustment family_feedback_confidence
family_learning_adjustment family_cap_effective family_consensus_score family_survival_score expectancy_score
strategy_weight_adjustment strategy_weight_confidence position_size_estimate portfolio_heat_score correlation_penalty
regime_failure_throttle family_failure_throttle risk_learning_adjustment risk_learning_confidence raw_candidate_count
surviving_candidate_count survival_rate executable_rate advisory_rate no_trade_rate top_family_share recommended_threshold_delta
data_confidence family_rank family_strength selection_probability mfe mae simulated_pnl realized_r_multiple
""".split()

_CANONICAL_ADVISORY_FIELDS = {
    "execution_entry", "execution_entry_source", "execution_entry_status", "display_entry",
    "display_entry_source", "display_entry_status", "hard_blockers", "soft_penalties",
    "warnings", "confidence_raw", "confidence_penalty", "confidence_final", "advisory_visible",
    "is_executable", "execution_status", "entry_source", "candidate_class", "final_score",
}


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


def _coerce_epoch_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if not numeric.notna().any():
        return numeric
    abs_numeric = numeric.abs()
    numeric = numeric.where(abs_numeric < 1e17, numeric / 1_000_000_000.0)
    abs_numeric = numeric.abs()
    numeric = numeric.where(abs_numeric < 1e14, numeric / 1_000_000.0)
    abs_numeric = numeric.abs()
    numeric = numeric.where(abs_numeric < 1e11, numeric / 1_000.0)
    return numeric


def _parse_ts_series(series: pd.Series) -> pd.Series:
    cleaned = series.where(pd.notna(series), None)
    return pd.to_datetime(cleaned, errors="coerce", utc=True)


def _coerce_ts_epoch(series: pd.Series) -> pd.Series:
    numeric = _coerce_epoch_series(series)
    parsed = _parse_ts_series(series)
    parsed_epoch = pd.Series([float("nan")] * len(series), index=series.index, dtype="float64")
    mask = parsed.notna()
    if mask.any():
        parsed_epoch.loc[mask] = parsed.loc[mask].map(lambda ts: float(ts.timestamp()))

    if series.dtype == object or str(series.dtype).startswith("string"):
        return parsed_epoch.where(parsed_epoch.notna(), numeric)
    return numeric.where(numeric.notna(), parsed_epoch)


def _first_epoch(out: pd.DataFrame, fields: tuple[str, ...]) -> pd.Series | None:
    epoch = None
    for field in fields:
        if field in out.columns:
            candidate = _coerce_ts_epoch(out[field])
            epoch = candidate if epoch is None else epoch.where(epoch.notna(), candidate)
    return epoch


def _format_ist_from_epoch(series: pd.Series) -> pd.Series:
    epoch = _coerce_epoch_series(series)
    dt = pd.to_datetime(epoch, errors="coerce", unit="s", utc=True)
    out = dt.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d %H:%M:%S IST")
    return out.where(out.notna(), "—")


def _format_ist_from_ts(series: pd.Series) -> pd.Series:
    return _format_ist_from_epoch(_coerce_ts_epoch(series))


def _is_option_row(row) -> bool:
    instrument_type = str(row.get("instrument_type") or row.get("instrument") or "").strip().upper()
    return instrument_type == "OPT" or bool(_option_right_for_identity(row))


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS + ["identity"])


def _status_badge(value) -> str:
    status = str(value or "PLANNING").upper()
    mapping = {
        "ACTIVE": "ACTIVE", "PLANNING": "PLANNING", "ADVISORY_ONLY": "ADVISORY",
        "READY": "READY", "BLOCKED_APPROVAL": "BLOCKED_APPROVAL",
        "BLOCKED_CONTRACT": "BLOCKED_CONTRACT", "QUEUED_REVIEW": "REVIEW",
        "QUEUE": "REVIEW", "REVALIDATED": "PLANNING", "UPDATED": "PLANNING",
        "EXITED": "EXITED", "INVALIDATED": "INVALID", "EXPIRED": "EXPIRED",
    }
    return mapping.get(status, status)


def _merge_duplicate_columns(out: pd.DataFrame) -> pd.DataFrame:
    if not out.columns.duplicated().any():
        return out
    deduped: dict[str, pd.Series] = {}
    for col in pd.Index(out.columns).unique():
        same = out.loc[:, out.columns == col]
        deduped[col] = same.iloc[:, 0] if same.shape[1] == 1 else same.bfill(axis=1).iloc[:, 0]
    return pd.DataFrame(deduped, index=out.index)


def _explicit_true(value) -> bool:
    return value is True or (isinstance(value, int) and not isinstance(value, bool) and value == 1)


def _stamp_ui_execution_truth(out: pd.DataFrame) -> pd.DataFrame:
    """Expose canonical execution-entry truth without changing runtime decisions."""
    if out.empty:
        return out

    ui_truth: list[bool] = []
    ui_reasons: list[str] = []
    for _, row in out.iterrows():
        row_payload = row.to_dict()
        decision = classify_top_opportunity_row(
            row_payload,
            source_list="top_executable",
        )
        explicit_executable = _explicit_true(row_payload.get("is_executable"))
        operator_executable = bool(explicit_executable and decision.executable_truth)
        reason = decision.reason
        if decision.executable_truth and not explicit_executable:
            reason = "canonical_entry_but_row_not_marked_executable"
        ui_truth.append(operator_executable)
        ui_reasons.append(reason)

    out = out.copy()
    out["ui_execution_truth"] = ui_truth
    out["ui_execution_truth_reason"] = ui_reasons
    return out


def _stamp_runtime_authority(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty:
        return out
    mode = str(getattr(__import__("config.config", fromlist=["EXECUTION_MODE"]), "EXECUTION_MODE", "SIM") or "SIM")
    rows = [apply_runtime_authority(row, mode=mode) for row in out.to_dict(orient="records")]
    stamped = pd.DataFrame(rows, index=out.index)
    # Preserve all original columns and expose authority fields as additional
    # operator truth. Non-executable rows retain diagnostic/opportunity scores,
    # but selection_score and capital are forced to zero by the authority layer.
    for column in out.columns:
        if column not in stamped.columns:
            stamped[column] = out[column]
    return stamped


def normalize_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    out = df.copy()
    rename_map = {
        "last_seen": "last_seen_ts", "type": "opt_type", "option_type": "opt_type",
        "right": "opt_type", "option_side": "opt_type", "contract_side": "opt_type",
        "pnl_1qty": "pnl_points", "pnl_1lot": "pnl_cash",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    out = _merge_duplicate_columns(out)
    canonical_advisory = any(col in out.columns for col in _CANONICAL_ADVISORY_FIELDS)

    last_seen_epoch = _first_epoch(out, (
        "last_seen_ts", "timestamp", "created_at", "decision_ts_epoch", "decision_ts_utc",
        "decision_ts_ist", "ts_epoch", "ts_utc", "ts_ist", "snapshot_ts_epoch",
        "snapshot_ts_utc", "snapshot_ts_ist",
    ))

    if "target" not in out.columns and "target_points" in out.columns:
        out["target"] = out["target_points"]

    if "suggested_entry" in out.columns and not canonical_advisory:
        if "entry" not in out.columns:
            out["entry"] = None
        suggested = pd.to_numeric(out["suggested_entry"], errors="coerce")
        current_ltp = pd.to_numeric(out["current_ltp"], errors="coerce") if "current_ltp" in out.columns else None
        entry_price = pd.to_numeric(out["entry_price"], errors="coerce") if "entry_price" in out.columns else None
        if "entry_status" in out.columns:
            ok_mask = out["entry_status"].astype(str).str.upper().isin(_ENTRY_STATUSES_WITH_QUOTE_BACKFILL)
            suggested = suggested.where(ok_mask)
            if current_ltp is not None:
                current_ltp = current_ltp.where(ok_mask)
            if entry_price is not None:
                entry_price = entry_price.where(ok_mask)
        if current_ltp is not None:
            suggested = suggested.where(suggested.notna(), current_ltp)
        if entry_price is not None:
            suggested = suggested.where(suggested.notna(), entry_price)
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

    if last_seen_epoch is None:
        last_seen_epoch = pd.Series([float("nan")] * len(out), index=out.index, dtype="float64")
    out["last_seen_ts"] = pd.to_datetime(last_seen_epoch, errors="coerce", unit="s", utc=True)
    out["last_seen_ts"] = out["last_seen_ts"].fillna(pd.Timestamp.now(tz="UTC"))

    display_epoch = _coerce_ts_epoch(out["display_ts_epoch"]) if "display_ts_epoch" in out.columns else None
    decision_epoch = _first_epoch(out, (
        "decision_ts_epoch", "decision_ts_utc", "decision_ts_ist", "ts_epoch", "ts_utc",
        "ts_ist", "timestamp_epoch_ms", "timestamp_utc_iso", "timestamp", "created_ts_epoch", "created_at",
    ))
    snapshot_epoch = _first_epoch(out, ("snapshot_ts_epoch", "snapshot_ts_utc", "snapshot_ts_ist"))
    if display_epoch is None:
        display_epoch = decision_epoch if decision_epoch is not None else snapshot_epoch
    else:
        if decision_epoch is not None:
            display_epoch = display_epoch.where(display_epoch.notna(), decision_epoch)
        elif snapshot_epoch is not None:
            display_epoch = display_epoch.where(display_epoch.notna(), snapshot_epoch)
    if display_epoch is None:
        display_epoch = pd.Series(pd.NA, index=out.index, dtype="float64")

    out["display_ts_epoch"] = display_epoch
    out["display_ts_utc"] = pd.to_datetime(out["display_ts_epoch"], errors="coerce", unit="s", utc=True)
    out["display_ts_ist"] = _format_ist_from_epoch(out["display_ts_epoch"])

    for col in NUMERIC_COLUMNS:
        if col in out.columns:
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
    return _stamp_runtime_authority(_stamp_ui_execution_truth(out))


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
        ]
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()

    out["trade_key"] = out.apply(_build, axis=1)
    return out


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    out = compute_trade_key(normalize_df(df))
    if "decision_ts_epoch" not in out.columns:
        out["decision_ts_epoch"] = pd.Series([float("nan")] * len(out), index=out.index, dtype="float64")
    last_seen_epoch = out["last_seen_ts"].map(lambda ts: float(ts.timestamp()) if pd.notna(ts) else float("nan"))
    out["_dedupe_ts_epoch"] = out["display_ts_epoch"].where(out["display_ts_epoch"].notna(), last_seen_epoch)
    out = out.sort_values(["_dedupe_ts_epoch", "decision_ts_epoch"], ascending=False, kind="mergesort")
    out = out.drop_duplicates(subset=["trade_key"], keep="first")
    return out.drop(columns=["_dedupe_ts_epoch"], errors="ignore")


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
    out = build_identity_col(normalize_df(df))
    view = str(view or "advisory").lower()
    include_last_seen = not bool(pd.to_numeric(out.get("display_ts_epoch"), errors="coerce").notna().any())
    if view == "active":
        cols = ["display_ts_ist", "last_seen_ts", "identity", "status", "side", "entry", "stop", "target", "live_ltp", "pnl_points", "pnl_cash", "qty", "confidence", "trade_key", "tradingsymbol"]
    elif view == "review":
        cols = ["display_ts_ist", "last_seen_ts", "identity", "status", "side", "entry", "stop", "target", "confidence", "trade_key", "tradingsymbol"]
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
            out[c] = out[c].round(2)
    if "display_ts_ist" in out.columns:
        out["display_ts_ist"] = out["display_ts_ist"].where(out["display_ts_ist"].notna(), "—")
    if "last_seen_ts" in out.columns:
        out["last_seen_ts"] = _format_ist_from_ts(out["last_seen_ts"])
    return out


def filter_non_active(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "status" not in df.columns:
        return df
    status = df["status"].astype(str).str.upper()
    return df[status != "ACTIVE"].copy()
