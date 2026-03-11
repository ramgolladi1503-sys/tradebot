import json
import time
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from core.orders.order_intent import OrderIntent
from core.learning_paths import canonical_suggestions_log_path, rejected_candidates_paths, suggestion_log_paths
from core.paths import logs_dir, data_root
from core.upstox_resolver import resolve_upstox_key
from core.market_calendar import choose_nearest_available_expiry
from core.trade_schema import build_instrument_id
from core.trade_permission import (
    build_permission_payload,
    classify_confidence_vs_threshold,
    resolve_confidence_thresholds,
)
from core.trade_identity import compute_trade_key, derive_strategy_id
from core.option_token_resolver import TokenCoverageError, resolve_option_token
from core.option_liquidity_cache import hydrate_option_liquidity_fields
from core.option_entry import get_option_ltp_sla_sec, validate_live_entry
from core.gating import gate_decision
from core.tick_store import get_ltp
from core.kite_depth_ws import ensure_subscribed_tokens
from core.entry_semantics import ENTRY_SOURCE_ENUM, EntryContractViolation, build_entry_state, enforce_entry_contract
from core.advisory_schema import AdvisorySchemaError, deserialize_advisory_row, log_advisory_schema_error, serialize_advisory_row
from core.blocker_lifecycle import TARGET_BLOCKER_CODES, evaluate_advisory_contract_blockers, get_blocker_registry
from core.events import write_json_atomic
from core.issue_policy import ISSUE_CATEGORY_HARD, ISSUE_CATEGORY_SOFT, ISSUE_CATEGORY_WARNING, classify_issue
from core.time_utils import is_market_open_ist

try:
    from config import config as cfg
except Exception:
    cfg = None

logger = logging.getLogger(__name__)


def _runtime_path(cfg_key: str, filename: str) -> Path:
    try:
        raw = str(getattr(cfg, cfg_key, "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        return Path(raw)
    return logs_dir() / filename


QUEUE_PATH = _runtime_path("REVIEW_QUEUE_PATH", "review_queue.json")
QUICK_QUEUE_PATH = _runtime_path("QUICK_REVIEW_QUEUE_PATH", "quick_review_queue.json")
ZERO_HERO_QUEUE_PATH = _runtime_path("ZERO_HERO_QUEUE_PATH", "zero_hero_queue.json")
SCALP_QUEUE_PATH = _runtime_path("SCALP_QUEUE_PATH", "scalp_queue.json")
TARGET_POINTS_QUEUE_PATH = _runtime_path("TARGET_POINTS_QUEUE_PATH", "target_points_queue.json")
APPROVED_PATH = _runtime_path("APPROVED_TRADES_PATH", "approved_trades.json")

_META_CACHE = {"ts": 0.0, "data": {}}
_CHAIN_CACHE = {"ts": 0.0, "data": {"by_token": {}, "by_contract": {}, "by_symbol_strike_type": {}}}
_ADVISORY_REST_LTP_CACHE: dict[str, dict] = {}
_ADVISORY_REST_LTP_LAST_ATTEMPT: dict[str, float] = {}
_NON_BLOCKING_ENTRY_STATUSES = {"OK", "PRICE_MISMATCH", "REST_FALLBACK", "OFFHOURS_SYNTHETIC", "DISPLAYABLE", "NON_EXECUTABLE"}
_LOW_GLOBAL_CONF_LOGGED_MINUTE_BY_SYMBOL: dict[str, int] = {}
_ENTRY_REQUIRED_STATUSES = {"ACTIVE", "PLANNING", "PROPOSED", "READY", "QUEUE_ONLY"}
_ENTRY_INTEGRITY_REASON = "MISSING_ENTRY"
_EXPLICIT_REVIEW_STATUSES = {"PLANNING", "BLOCKED_CONTRACT", "BLOCKED_APPROVAL", "ADVISORY_ONLY", "QUEUE_ONLY", "READY"}
_DISPLAY_ENTRY_STATUSES = {"displayable", "non_executable", "missing"}
_EXECUTION_ENTRY_STATUSES = {"executable", "non_executable", "missing"}


def _entry_lifecycle_payload(
    *,
    execution_entry=None,
    execution_entry_source=None,
    execution_entry_status=None,
    display_entry=None,
    display_entry_source=None,
    display_entry_status=None,
    clear_reason=None,
    entry_reason=None,
) -> dict:
    return {
        "execution_entry": _safe_float(execution_entry),
        "execution_entry_source": str(execution_entry_source or "").strip().lower() or "none",
        "execution_entry_status": str(execution_entry_status or "").strip().lower(),
        "display_entry": _safe_float(display_entry),
        "display_entry_source": str(display_entry_source or "").strip().lower() or "none",
        "display_entry_status": str(display_entry_status or "").strip().lower(),
        "clear_reason": str(clear_reason or "").strip().lower() or None,
        "entry_reason": None if not str(entry_reason or "").strip() else str(entry_reason),
    }


def _entry_lifecycle_from_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return _entry_lifecycle_payload()
    return _entry_lifecycle_payload(
        execution_entry=entry.get("execution_entry"),
        execution_entry_source=entry.get("execution_entry_source"),
        execution_entry_status=entry.get("execution_entry_status"),
        display_entry=entry.get("display_entry"),
        display_entry_source=entry.get("display_entry_source"),
        display_entry_status=entry.get("display_entry_status"),
        clear_reason=entry.get("entry_clear_reason"),
        entry_reason=entry.get("entry_reason"),
    )


def _entry_lifecycle_is_valid(lifecycle: dict) -> bool:
    if not isinstance(lifecycle, dict):
        return False
    display_entry = _safe_float(lifecycle.get("display_entry"))
    execution_entry = _safe_float(lifecycle.get("execution_entry"))
    display_entry_status = str(lifecycle.get("display_entry_status") or "").strip().lower()
    execution_entry_status = str(lifecycle.get("execution_entry_status") or "").strip().lower()
    clear_reason = str(lifecycle.get("clear_reason") or "").strip()
    return bool(
        display_entry_status in _DISPLAY_ENTRY_STATUSES
        and execution_entry_status in _EXECUTION_ENTRY_STATUSES
        and (
            (display_entry is not None and display_entry_status in {"displayable", "non_executable"})
            or (display_entry is None and display_entry_status == "missing" and bool(clear_reason))
        )
        and (
            (execution_entry is not None and execution_entry_status == "executable")
            or (execution_entry is None and execution_entry_status in {"non_executable", "missing"})
        )
    )


def _normalize_entry_lifecycle(
    lifecycle: dict,
    *,
    fallback_clear_reason: str | None = None,
) -> dict:
    normalized = _entry_lifecycle_payload(**(lifecycle or {}))
    display_entry = normalized["display_entry"]
    execution_entry = normalized["execution_entry"]

    if execution_entry is None:
        normalized["execution_entry_source"] = normalized.get("execution_entry_source") or "none"
        if normalized.get("execution_entry_status") not in _EXECUTION_ENTRY_STATUSES or normalized.get("execution_entry_status") == "executable":
            normalized["execution_entry_status"] = "non_executable" if display_entry is not None else "missing"
    else:
        normalized["execution_entry_status"] = "executable"

    if display_entry is None:
        normalized["display_entry_source"] = "none"
        normalized["display_entry_status"] = "missing"
        normalized["clear_reason"] = str(
            normalized.get("clear_reason")
            or fallback_clear_reason
            or "missing_display_entry"
        ).strip().lower()
        normalized["entry_reason"] = None if not str(normalized.get("entry_reason") or "").strip() else normalized.get("entry_reason")
    else:
        if normalized.get("display_entry_status") not in {"displayable", "non_executable"}:
            normalized["display_entry_status"] = "displayable" if execution_entry is not None else "non_executable"
        normalized["clear_reason"] = None

    return normalized


def _apply_entry_lifecycle(
    entry: dict,
    lifecycle: dict,
    *,
    align_for_schema: bool,
    entry_status_override: str | None = None,
    entry_value_override=None,
    entry_source_override=None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    normalized = _normalize_entry_lifecycle(lifecycle)
    out = dict(entry)
    out["execution_entry"] = normalized["execution_entry"]
    out["execution_entry_source"] = normalized["execution_entry_source"]
    out["execution_entry_status"] = normalized["execution_entry_status"]
    out["display_entry"] = normalized["display_entry"]
    out["display_entry_source"] = normalized["display_entry_source"]
    out["display_entry_status"] = normalized["display_entry_status"]
    out["entry_reason"] = normalized["entry_reason"]
    out["entry_clear_reason"] = normalized["clear_reason"]

    if normalized["display_entry"] is None:
        if align_for_schema:
            out["entry"] = None
            out["entry_source"] = "none"
            out["entry_status"] = "missing"
        else:
            out["entry"] = _safe_float(entry_value_override)
            if out["entry"] is None:
                out["entry_source"] = "none"
            else:
                out["entry_source"] = str(entry_source_override or out.get("entry_source") or "none")
            out["entry_status"] = str(entry_status_override or "missing")
    else:
        out["entry"] = normalized["display_entry"]
        out["entry_source"] = normalized["display_entry_source"]
        out["entry_status"] = normalized["display_entry_status"] if align_for_schema else str(
            entry_status_override or normalized["display_entry_status"]
        )
    return out


def _display_entry_source_for_row(entry: dict) -> str:
    quote_source = str(entry.get("quote_source") or entry.get("option_ltp_source") or "").strip().lower()
    display_source = str(entry.get("display_entry_source") or entry.get("entry_source") or "").strip().lower()
    if display_source in ENTRY_SOURCE_ENUM:
        return display_source
    if quote_source in {"tick_store", "rest_fallback", "synthetic_offhours", "unknown"}:
        return "last"
    if quote_source in {"mark", "mid", "last"}:
        return quote_source
    return "last"


def _display_entry_reason_for_source(source: str) -> str:
    source_key = str(source or "").strip().lower()
    if source_key == "mark":
        return "display_from_mark"
    if source_key == "mid":
        return "display_from_mid"
    return "display_from_last"


def _is_entry_status_blocking(status: str | None) -> bool:
    status_key = str(status or "").strip().upper()
    if not status_key:
        return False
    return status_key not in _NON_BLOCKING_ENTRY_STATUSES


def _log_entry_lifecycle_resolution(entry: dict) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    try:
        logger.debug(
            "entry_lifecycle_resolved trade_id=%s symbol=%s execution_entry=%s execution_entry_source=%s execution_entry_status=%s display_entry=%s display_entry_source=%s display_entry_status=%s entry_status=%s",
            entry.get("trade_id"),
            entry.get("symbol"),
            entry.get("execution_entry"),
            entry.get("execution_entry_source"),
            entry.get("execution_entry_status"),
            entry.get("display_entry"),
            entry.get("display_entry_source"),
            entry.get("display_entry_status"),
            entry.get("entry_status"),
        )
    except Exception:
        logger.debug("entry_lifecycle_resolved trade_id=%s", entry.get("trade_id"))


def _canonicalize_entry_lifecycle(
    entry: dict,
    *,
    mode_for_entry: str | None = None,
    allow_stale_quotes_for_entry: bool | None = None,
    market_open_for_entry: bool | None = None,
    align_for_schema: bool = False,
) -> dict:
    if not isinstance(entry, dict):
        return entry

    out = dict(entry)
    legacy_entry_status = str(out.get("entry_status") or "").strip()
    legacy_entry = _safe_float(out.get("entry"))
    legacy_entry_source = out.get("entry_source")
    if legacy_entry_status and legacy_entry_status.lower() not in _DISPLAY_ENTRY_STATUSES:
        out.setdefault("quote_validation_status", legacy_entry_status)

    lifecycle = _entry_lifecycle_from_entry(out)
    has_valid_canonical_lifecycle = _entry_lifecycle_is_valid(lifecycle)

    if not has_valid_canonical_lifecycle:
        if mode_for_entry is None:
            mode_for_entry = _entry_execution_mode(out)
        if allow_stale_quotes_for_entry is None:
            allow_stale_quotes_for_entry = _allow_rest_fallback_for_mode(mode_for_entry)
        if market_open_for_entry is None:
            market_open_for_entry, _ = _resolve_entry_market_open(
                out,
                mode_for_entry,
                bool(allow_stale_quotes_for_entry),
            )
        token_missing_identified = out.get("instrument_token") in (None, "", "None") and bool(out.get("tradingsymbol"))
        synthetic_offhours = _is_synthetic_offhours_row(out)
        if synthetic_offhours:
            lifecycle_last_keys = (
                "expected_entry",
                "suggested_entry",
                "entry_price",
                "entry",
                "signal_price",
                "current_ltp",
                "opt_ltp",
                "ltp",
            )
        elif token_missing_identified:
            lifecycle_last_keys = (
                "suggested_entry",
                "entry",
                "entry_price",
                "expected_entry",
                "signal_price",
                "current_ltp",
                "opt_ltp",
                "ltp",
            )
        else:
            lifecycle_last_keys = (
                "current_ltp",
                "suggested_entry",
                "expected_entry",
                "entry",
                "entry_price",
                "signal_price",
                "opt_ltp",
                "ltp",
            )
        lifecycle_last = _first_present_float(out, lifecycle_last_keys)
        try:
            built_state = build_entry_state(
                symbol=out.get("symbol"),
                expiry=out.get("expiry_date") or out.get("expiry"),
                strike=out.get("strike"),
                right=out.get("option_type") or out.get("type") or out.get("right"),
                side=out.get("side"),
                direction=out.get("direction"),
                bid=out.get("best_bid") or out.get("bid") or out.get("opt_bid"),
                ask=out.get("best_ask") or out.get("ask") or out.get("opt_ask"),
                mark=out.get("mark_price"),
                mid=out.get("mid_price"),
                last=lifecycle_last,
                quote_age_sec=out.get("quote_age_sec") if out.get("quote_age_sec") not in (None, "", "None") else out.get("price_age_sec"),
                mode=mode_for_entry,
                allow_stale_quotes=bool(allow_stale_quotes_for_entry),
                market_open=market_open_for_entry,
                instrument_matches=not bool(out.get("unresolved_contract")),
                quote_source=out.get("quote_source") or out.get("option_ltp_source") or out.get("entry_source"),
            )
        except EntryContractViolation:
            built_state = {}
        lifecycle = _entry_lifecycle_payload(
            execution_entry=built_state.get("execution_entry"),
            execution_entry_source=built_state.get("execution_entry_source"),
            execution_entry_status=built_state.get("execution_entry_status"),
            display_entry=built_state.get("display_entry"),
            display_entry_source=built_state.get("display_entry_source"),
            display_entry_status=built_state.get("display_entry_status"),
            clear_reason=built_state.get("entry_clear_reason"),
            entry_reason=built_state.get("entry_reason"),
        )
        display_entry_after_build = _safe_float(lifecycle.get("display_entry"))
        can_retain_legacy_display = bool(
            legacy_entry is not None
            and (
                token_missing_identified
                or synthetic_offhours
                or str(out.get("quote_validation_status") or "").strip().upper() in {"NON_EXECUTABLE", "REST_FALLBACK", "OFFHOURS_SYNTHETIC"}
                or legacy_entry_status.upper() in {"NON_EXECUTABLE", "REST_FALLBACK", "OFFHOURS_SYNTHETIC", "PRICE_MISMATCH"}
            )
        )
        if display_entry_after_build is None and can_retain_legacy_display:
            display_source = _display_entry_source_for_row(out)
            lifecycle = _entry_lifecycle_payload(
                execution_entry=lifecycle.get("execution_entry"),
                execution_entry_source=lifecycle.get("execution_entry_source"),
                execution_entry_status=lifecycle.get("execution_entry_status") if lifecycle.get("execution_entry") is not None else "non_executable",
                display_entry=legacy_entry,
                display_entry_source=display_source,
                display_entry_status="non_executable",
                clear_reason=None,
                entry_reason=_display_entry_reason_for_source(display_source),
            )

    clear_reason_source = (
        out.get("quote_validation_status")
        or (legacy_entry_status if legacy_entry_status.lower() not in _DISPLAY_ENTRY_STATUSES else "")
        or out.get("validation_issue_code")
        or out.get("permission_reason")
        or out.get("hard_reason")
        or out.get("final_blocker")
        or "missing_display_entry"
    )
    lifecycle = _normalize_entry_lifecycle(lifecycle, fallback_clear_reason=clear_reason_source)
    out = _apply_entry_lifecycle(
        out,
        lifecycle,
        align_for_schema=align_for_schema,
        entry_status_override=(legacy_entry_status if not align_for_schema and legacy_entry_status else None),
        entry_value_override=(legacy_entry if not align_for_schema and lifecycle.get("display_entry") is None else None),
        entry_source_override=(legacy_entry_source if not align_for_schema and legacy_entry_source not in (None, "", "None") else None),
    )

    return out


def _coerce_instrument_token(value) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        token_value = int(value)
        return token_value if token_value > 0 else None
    except Exception:
        return None


def _has_valid_broker_contract(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    token_value = _coerce_instrument_token(entry.get("instrument_token"))
    tradingsymbol = str(entry.get("tradingsymbol") or "").strip()
    expiry_date = _coerce_expiry(entry.get("expiry_date") or entry.get("expiry"))
    return bool(token_value is not None and tradingsymbol and expiry_date)


def _missing_broker_contract_fields(entry: dict) -> list[str]:
    if not isinstance(entry, dict):
        return []
    missing: list[str] = []
    if _coerce_instrument_token(entry.get("instrument_token")) is None:
        missing.append("instrument_token")
    if not str(entry.get("tradingsymbol") or "").strip():
        missing.append("tradingsymbol")
    if not _coerce_expiry(entry.get("expiry_date") or entry.get("expiry")):
        missing.append("expiry_date")
    return missing


def _is_blocked_contract_row(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    status = str(entry.get("status") or "").strip().upper()
    permission = str(entry.get("permission") or "").strip().upper()
    hard_reason = str(entry.get("hard_reason") or "").strip().lower()
    permission_reason = str(entry.get("permission_reason") or "").strip().lower()
    if bool(entry.get("unresolved_contract")):
        return True
    if status == "BLOCKED_CONTRACT":
        return True
    if hard_reason == "unresolved_contract":
        return True
    if permission == "BLOCK" and permission_reason == "unresolved_contract":
        return True
    return False


def _derive_review_status(entry: dict, fallback_status: str | None = None) -> str:
    raw_status = str(fallback_status or entry.get("status_raw") or entry.get("status") or "PLANNING").strip().upper() or "PLANNING"
    if _is_blocked_contract_row(entry):
        return "BLOCKED_CONTRACT"
    if bool(entry.get("approval_blocked")):
        return "BLOCKED_APPROVAL"
    permission = str(entry.get("permission") or "").strip().upper()
    final_action = str(entry.get("final_action") or "").strip().upper()
    if permission == "BLOCK" or final_action == "BLOCK":
        return "INVALID"
    if permission == "EXECUTE" and final_action == "EXECUTE":
        return "READY"
    if permission == "QUEUE_ONLY" and final_action == "QUEUE_ONLY":
        return "QUEUE_ONLY"
    if permission == "ADVISORY_ONLY" or final_action == "ADVISORY_ONLY":
        return "ADVISORY_ONLY"
    if raw_status in _EXPLICIT_REVIEW_STATUSES:
        return raw_status
    return "PLANNING"


def _enrich_contract_identity(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if str(entry.get("instrument") or entry.get("instrument_type") or "").upper() != "OPT":
        return entry
    if not entry.get("expiry_date") and entry.get("expiry"):
        entry["expiry_date"] = _coerce_expiry(entry.get("expiry")) or entry.get("expiry")
    if entry.get("expiry_date"):
        entry["expiry_date"] = _coerce_expiry(entry.get("expiry_date")) or entry.get("expiry_date")
        entry["expiry"] = entry.get("expiry_date")
    opt_type = _coerce_option_type(entry.get("option_type") or entry.get("type") or entry.get("right"))
    if opt_type:
        entry["option_type"] = opt_type
        entry["type"] = opt_type
    strike_val = _coerce_strike(entry.get("strike"))
    if strike_val is not None:
        entry["strike"] = strike_val
    token_value = _coerce_instrument_token(entry.get("instrument_token"))
    if token_value is not None:
        entry["instrument_token"] = token_value
    tradingsymbol_text = str(entry.get("tradingsymbol") or "").strip()
    if token_value is None and tradingsymbol_text:
        direct_meta = _lookup_instrument_meta_by_tradingsymbol(tradingsymbol_text)
        direct_token = _coerce_instrument_token(direct_meta.get("instrument_token"))
        if direct_token is not None:
            entry["instrument_token"] = direct_token
            token_value = direct_token
        direct_expiry = _coerce_expiry(direct_meta.get("expiry"))
        if direct_expiry and not entry.get("expiry_date"):
            entry["expiry_date"] = direct_expiry
            entry["expiry"] = direct_expiry
    chain_meta = _option_chain_meta_map()
    if token_value is not None and not _has_valid_broker_contract(entry):
        meta = _instrument_meta_map().get(token_value, {})
        if not meta and chain_meta:
            meta = (chain_meta.get("by_token") or {}).get(token_value, {})
        if meta:
            expiry = _coerce_expiry(meta.get("expiry"))
            if expiry and not entry.get("expiry_date"):
                entry["expiry_date"] = expiry
                entry["expiry"] = expiry
            tradingsymbol = str(meta.get("tradingsymbol") or "").strip()
            if tradingsymbol and not entry.get("tradingsymbol"):
                entry["tradingsymbol"] = tradingsymbol
            meta_type = _coerce_option_type(meta.get("type"))
            if meta_type:
                entry.setdefault("option_type", meta_type)
                entry.setdefault("type", meta_type)
            meta_strike = _coerce_strike(meta.get("strike"))
            if meta_strike is not None and entry.get("strike") in (None, "", "None"):
                entry["strike"] = meta_strike
    if token_value is None and entry.get("symbol") and strike_val is not None and opt_type:
        meta = None
        expiry_date = entry.get("expiry_date")
        if expiry_date:
            meta = (chain_meta.get("by_contract") or {}).get((entry.get("symbol"), expiry_date, float(strike_val), opt_type))
        if meta is None:
            candidates = (chain_meta.get("by_symbol_strike_type") or {}).get(
                (entry.get("symbol"), float(strike_val), opt_type),
                [],
            )
            if candidates:
                exp_dates = []
                meta_by_exp = {}
                for cand in candidates:
                    exp = _coerce_expiry(cand.get("expiry"))
                    if not exp:
                        continue
                    try:
                        exp_dt = datetime.fromisoformat(exp).date()
                    except Exception:
                        continue
                    exp_dates.append(exp_dt)
                    meta_by_exp[exp_dt.isoformat()] = cand
                if exp_dates:
                    chosen = choose_nearest_available_expiry(exp_dates, today=datetime.now().date())
                    if chosen is not None:
                        meta = meta_by_exp.get(chosen.isoformat())
        if meta:
            expiry = _coerce_expiry(meta.get("expiry"))
            if expiry and not entry.get("expiry_date"):
                entry["expiry_date"] = expiry
                entry["expiry"] = expiry
            tradingsymbol = str(meta.get("tradingsymbol") or "").strip()
            if tradingsymbol and not entry.get("tradingsymbol"):
                entry["tradingsymbol"] = tradingsymbol
            meta_token = _coerce_instrument_token(meta.get("instrument_token"))
            if meta_token is not None and entry.get("instrument_token") in (None, "", "None"):
                entry["instrument_token"] = meta_token
                token_value = meta_token
            meta_type = _coerce_option_type(meta.get("type"))
            if meta_type:
                entry.setdefault("option_type", meta_type)
                entry.setdefault("type", meta_type)
    if _coerce_instrument_token(entry.get("instrument_token")) is None and entry.get("symbol") and entry.get("expiry_date") and strike_val is not None and opt_type:
        try:
            resolved = resolve_option_token(
                entry.get("symbol"),
                entry.get("expiry_date"),
                strike_val,
                opt_type,
            )
        except TokenCoverageError as exc:
            resolved = None
            entry.setdefault("token_coverage_error_code", exc.code)
            entry.setdefault("token_coverage_evidence", exc.evidence)
        if resolved:
            resolved_token = _coerce_instrument_token(resolved.get("instrument_token"))
            if resolved_token is not None:
                entry["instrument_token"] = resolved_token
            tradingsymbol = str(resolved.get("tradingsymbol") or "").strip()
            if tradingsymbol and not entry.get("tradingsymbol"):
                entry["tradingsymbol"] = tradingsymbol
    liquidity_meta = {}
    token_value = _coerce_instrument_token(entry.get("instrument_token"))
    if chain_meta:
        if token_value is not None:
            liquidity_meta = (chain_meta.get("by_token") or {}).get(token_value, {}) or {}
        if (
            not liquidity_meta
            and entry.get("symbol")
            and entry.get("expiry_date")
            and strike_val is not None
            and opt_type
        ):
            liquidity_meta = (
                (chain_meta.get("by_contract") or {}).get(
                    (entry.get("symbol"), entry.get("expiry_date"), float(strike_val), opt_type)
                )
                or {}
            )
    entry = _apply_option_chain_liquidity(entry, liquidity_meta)
    entry = hydrate_option_liquidity_fields(
        entry,
        symbol=entry.get("symbol"),
        expiry=entry.get("expiry_date"),
        strike=entry.get("strike"),
        option_type=opt_type,
        now_epoch=time.time(),
    )
    if not entry.get("liquidity_source"):
        if any(_safe_float(entry.get(field_name)) is not None for field_name in ("volume", "current_volume", "oi", "oi_change")):
            entry["liquidity_source"] = "trade_payload"
    if entry.get("liquidity_age_sec") is None:
        entry["liquidity_age_sec"] = _safe_float(entry.get("quote_age_sec"))
    if entry.get("liquidity_cache_hit") is None:
        entry["liquidity_cache_hit"] = False
    if entry.get("liquidity_missing_fields") is None:
        entry["liquidity_missing_fields"] = [
            field_name
            for field_name in ("volume", "current_volume", "oi", "oi_change")
            if _safe_float(entry.get(field_name)) is None
        ]
    if not entry.get("instrument_id"):
        if entry.get("tradingsymbol"):
            entry["instrument_id"] = entry.get("tradingsymbol")
        elif _coerce_instrument_token(entry.get("instrument_token")) is not None:
            entry["instrument_id"] = str(entry.get("instrument_token"))
        else:
            entry["instrument_id"] = build_instrument_id(
                entry.get("underlying") or entry.get("symbol"),
                "OPT",
                entry.get("expiry_date"),
                entry.get("strike"),
                entry.get("option_type") or entry.get("type"),
            )
    return entry


def _is_unresolved_option_contract(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    option_right = _coerce_option_type(entry.get("option_type") or entry.get("type") or entry.get("right"))
    if str(entry.get("instrument_type") or entry.get("instrument") or "").upper() != "OPT":
        return True
    if option_right not in {"CE", "PE"}:
        return True
    if not str(entry.get("tradingsymbol") or "").strip():
        return True
    if not _coerce_expiry(entry.get("expiry_date") or entry.get("expiry")):
        return True
    return False


def _apply_unresolved_contract_state(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    missing_identity_fields = _missing_broker_contract_fields(entry)
    current_status = str(entry.get("status_raw") or entry.get("status") or "PLANNING").strip().upper() or "PLANNING"
    if current_status == "BLOCKED_CONTRACT":
        current_status = "PLANNING"
    entry["status_raw"] = current_status
    entry["unresolved_contract"] = True
    entry["tradable"] = False
    entry["tradable_reasons_blocking"] = list(
        dict.fromkeys(list(entry.get("tradable_reasons_blocking") or []) + ["unresolved_contract"])
    )
    entry["status"] = "BLOCKED_CONTRACT"
    entry["permission"] = "BLOCK"
    entry["execution_allowed"] = False
    entry["final_action"] = "BLOCK"
    entry["hard_reason"] = "unresolved_contract"
    entry["approval_blocked"] = False
    entry["permission_reason"] = "unresolved_contract"
    entry["entry_status"] = str(entry.get("entry_status") or "MISSING_OPTION_TOKEN")
    entry["missing_identity_fields"] = missing_identity_fields
    entry["entry"] = None
    entry["suggested_entry"] = None
    entry["expected_entry"] = None
    return entry


def _clear_unresolved_contract_state(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    status_raw = str(entry.get("status_raw") or "").strip().upper() or "PLANNING"
    entry["unresolved_contract"] = False
    entry["missing_identity_fields"] = []
    reasons = [reason for reason in list(entry.get("tradable_reasons_blocking") or []) if str(reason) != "unresolved_contract"]
    entry["tradable_reasons_blocking"] = reasons
    entry["status"] = status_raw if status_raw != "BLOCKED_CONTRACT" else "PLANNING"
    entry["hard_reason"] = None
    entry["permission"] = None
    entry["permission_reason"] = None
    entry["entry_status"] = None if str(entry.get("entry_status") or "").strip() == "MISSING_OPTION_TOKEN" else entry.get("entry_status")
    entry["final_action"] = None
    entry["final_blocker"] = None
    entry["token_coverage_error_code"] = None
    entry["token_coverage_evidence"] = None
    return entry


def _build_advisory_emit_failure_payload(
    entry: dict,
    advisory_payload: dict,
    exc: Exception,
    *,
    emission_target: str,
) -> dict:
    lifecycle_source = advisory_payload if isinstance(advisory_payload, dict) else entry
    return {
        "ts_epoch": float(time.time()),
        "ts_local": datetime.now().astimezone().isoformat(),
        "source": "review_queue.emit",
        "emission_target": emission_target,
        "failure_reason": str(exc),
        "trade_id": entry.get("trade_id"),
        "advisory_id": entry.get("advisory_id") or entry.get("trade_id"),
        "symbol": entry.get("symbol"),
        "strike": entry.get("strike"),
        "option_type": entry.get("option_type") or entry.get("type") or entry.get("right"),
        "permission": entry.get("permission"),
        "permission_reason": entry.get("permission_reason"),
        "readiness": entry.get("readiness"),
        "execution_status": entry.get("execution_status"),
        "final_action": entry.get("final_action"),
        "entry": lifecycle_source.get("entry"),
        "entry_source": lifecycle_source.get("entry_source"),
        "entry_status": lifecycle_source.get("entry_status"),
        "execution_entry": lifecycle_source.get("execution_entry"),
        "execution_entry_source": lifecycle_source.get("execution_entry_source"),
        "execution_entry_status": lifecycle_source.get("execution_entry_status"),
        "display_entry": lifecycle_source.get("display_entry"),
        "display_entry_source": lifecycle_source.get("display_entry_source"),
        "display_entry_status": lifecycle_source.get("display_entry_status"),
        "entry_reason": lifecycle_source.get("entry_reason"),
        "entry_clear_reason": lifecycle_source.get("entry_clear_reason"),
    }


def _emit_review_queue_logs(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {"ok": False, "target": "unknown", "diagnostic": None}
    emission_target = "rejected_candidates" if _is_blocked_contract_row(entry) else "suggestions"
    advisory_payload = _canonicalize_entry_lifecycle(
        entry,
        mode_for_entry=_entry_execution_mode(entry),
        allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(entry)),
        align_for_schema=True,
    )
    try:
        advisory_entry = serialize_advisory_row(advisory_payload, allow_legacy=True)
    except AdvisorySchemaError as exc:
        diagnostic = _build_advisory_emit_failure_payload(
            entry,
            advisory_payload,
            exc,
            emission_target=emission_target,
        )
        log_advisory_schema_error("review_queue.emit", advisory_payload, exc)
        logger.error("advisory_emit_schema_error payload=%s", json.dumps(diagnostic, sort_keys=True))
        _append_jsonl([logs_dir() / "advisory_emit_failures.jsonl"], diagnostic)
        return {"ok": False, "target": emission_target, "diagnostic": diagnostic}
    suggestion_paths: list[Path] = []
    seen_paths: set[str] = set()

    def _add_suggestion_path(path) -> None:
        try:
            normalized = Path(path).expanduser()
        except Exception:
            return
        key = str(normalized)
        if not key or key in seen_paths:
            return
        seen_paths.add(key)
        suggestion_paths.append(normalized)

    explicit_suggestions_path = None
    try:
        raw = str(getattr(cfg, "SUGGESTIONS_LOG_PATH", "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        explicit_suggestions_path = canonical_suggestions_log_path()
    if explicit_suggestions_path is not None:
        _add_suggestion_path(explicit_suggestions_path)
    for path in suggestion_log_paths():
        _add_suggestion_path(path)
    if _is_blocked_contract_row(entry):
        if explicit_suggestions_path is not None:
            _append_jsonl([Path(explicit_suggestions_path).expanduser()], advisory_entry)
        blocked_payload = dict(advisory_entry)
        blocked_payload.setdefault("reject_reason", "unresolved_contract")
        blocked_payload.setdefault("reason_code", "unresolved_contract")
        _append_jsonl(rejected_candidates_paths(), blocked_payload)
        return {"ok": True, "target": emission_target, "diagnostic": None}
    _append_jsonl(suggestion_paths, advisory_entry)
    return {"ok": True, "target": emission_target, "diagnostic": None}


def _apply_manual_approval_state(entry: dict, now_epoch: float | None = None) -> dict:
    if not isinstance(entry, dict):
        return entry
    if bool(entry.get("unresolved_contract")):
        entry["approval_blocked"] = False
        return entry
    if not _manual_approval_required_for_entry(entry):
        entry.setdefault("approval_blocked", False)
        return entry
    approval_payload_hash = str(entry.get("approval_payload_hash") or "").strip() or None
    approval_context_present = bool(
        approval_payload_hash
        or str(entry.get("approval_reason") or "").strip()
    )
    if not approval_context_present:
        entry.setdefault("approval_blocked", False)
        return entry
    trade_id = str(entry.get("trade_id") or "").strip()
    if not trade_id:
        entry.setdefault("approval_blocked", False)
        return entry
    approved, approval_reason = approval_status(
        trade_id,
        payload_hash=approval_payload_hash,
        now_epoch=now_epoch,
    )
    if approved:
        entry["approval_blocked"] = False
        return entry
    entry["approval_blocked"] = True
    entry["approval_reason"] = str(approval_reason or entry.get("approval_reason") or "approval_missing")
    entry["execution_allowed"] = False
    if str(entry.get("permission") or "").upper() == "EXECUTE":
        entry = _apply_permission_state(
            entry,
            "ADVISORY_ONLY",
            entry["approval_reason"],
            downgrade_reason=entry["approval_reason"],
        )
    elif not str(entry.get("permission_reason") or "").strip():
        entry["permission_reason"] = entry["approval_reason"]
    if str(entry.get("final_action") or "").upper() == "EXECUTE":
        entry["final_action"] = "ADVISORY_ONLY"
    return entry


def _enforce_executable_entry_integrity(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    token_missing_identified = entry.get("instrument_token") in (None, "", "None") and bool(entry.get("tradingsymbol"))
    if token_missing_identified:
        return entry
    status = str(entry.get("status") or "").strip().upper()
    if status not in _ENTRY_REQUIRED_STATUSES:
        return entry
    entry_val = _safe_float(entry.get("entry"))
    if entry_val is not None:
        return entry
    entry["status"] = "INVALID"
    entry["permission"] = "ADVISORY_ONLY"
    entry["permission_reason"] = str(entry.get("permission_reason") or _ENTRY_INTEGRITY_REASON)
    entry["entry_status"] = str(entry.get("entry_status") or _ENTRY_INTEGRITY_REASON)
    entry["final_action"] = "ADVISORY_ONLY"
    entry["activation_gate_reason"] = str(entry.get("activation_gate_reason") or "missing_entry")
    blockers = list(entry.get("tradable_reasons_blocking") or [])
    if _ENTRY_INTEGRITY_REASON not in blockers:
        blockers.append(_ENTRY_INTEGRITY_REASON)
    entry["tradable_reasons_blocking"] = blockers
    return entry


def _log_low_global_conf_once_per_symbol_minute(
    *,
    symbol: str | None,
    raw_conf: float | None,
    regime_conf: float | None,
    orb_bias: str | None,
    orb_factor: float | None,
    reg_penalty: float | None,
    global_conf: float | None,
) -> None:
    try:
        sym = str(symbol or "").strip().upper()
        if not sym:
            return
        global_val = _safe_float(global_conf)
        advisory_threshold = float(getattr(cfg, "CONFIDENCE_THRESHOLD_ADVISORY", 0.15))
        if global_val is None or global_val >= advisory_threshold:
            return
        minute_bucket = int(time.time() // 60)
        if _LOW_GLOBAL_CONF_LOGGED_MINUTE_BY_SYMBOL.get(sym) == minute_bucket:
            return
        _LOW_GLOBAL_CONF_LOGGED_MINUTE_BY_SYMBOL[sym] = minute_bucket
        logger.info(
            "low_global_conf symbol=%s raw_conf=%.3f regime_conf=%s orb_bias=%s orb_factor=%s reg_pen=%s global_conf=%.3f",
            sym,
            float(_safe_float(raw_conf) or 0.0),
            f"{_safe_float(regime_conf):.3f}" if _safe_float(regime_conf) is not None else "None",
            str(orb_bias or "UNKNOWN").upper(),
            f"{_safe_float(orb_factor):.3f}" if _safe_float(orb_factor) is not None else "None",
            f"{_safe_float(reg_penalty):.3f}" if _safe_float(reg_penalty) is not None else "None",
            float(global_val),
        )
    except Exception:
        return


def _rest_ltp_cache_key(token_value, tradingsymbol: str | None) -> str | None:
    if token_value not in (None, "", "None"):
        return f"token:{token_value}"
    text = str(tradingsymbol or "").strip().upper()
    if text:
        return f"symbol:{text}"
    return None


def _extract_ltp_from_payload(payload, symbols: list[str]) -> float | None:
    if not isinstance(payload, dict):
        return None
    keys = []
    for candidate in list(symbols) + list(payload.keys()):
        if candidate not in keys:
            keys.append(candidate)
    for key in keys:
        row = payload.get(key)
        if isinstance(row, dict):
            for field in ("last_price", "ltp", "price"):
                try:
                    value = row.get(field)
                    if value is None:
                        continue
                    ltp_val = float(value)
                    if ltp_val > 0:
                        return ltp_val
                except Exception:
                    continue
            continue
        try:
            if row is None:
                continue
            ltp_val = float(row)
            if ltp_val > 0:
                return ltp_val
        except Exception:
            continue
    return None


def _fetch_option_ltp_rest(tradingsymbol: str | None) -> tuple[float | None, float | None]:
    symbol = str(tradingsymbol or "").strip()
    if not symbol:
        return None, None
    symbol_upper = symbol.upper()
    # Advisory fallback must fetch option contracts only; never resolve/index-fallback
    # into underlying quotes for option candidates.
    if not re.search(r"(CE|PE)$", symbol_upper):
        return None, None
    try:
        from core.kite_client import kite_client
    except Exception:
        return None, None
    symbols = [symbol]
    if ":" not in symbol:
        symbols.extend([f"NFO:{symbol}", f"BFO:{symbol}"])
    try:
        payload = kite_client.ltp(symbols)
    except Exception:
        return None, None
    ltp_val = _extract_ltp_from_payload(payload, symbols)
    if ltp_val is None:
        return None, None
    return float(ltp_val), float(time.time())


def _resolve_rest_fallback_ltp(
    *,
    token_value,
    tradingsymbol: str | None,
    now_epoch: float | None = None,
) -> tuple[float | None, float | None, bool]:
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    cache_key = _rest_ltp_cache_key(token_value, tradingsymbol)
    if not cache_key:
        return None, None, False
    cooldown_sec = float(getattr(cfg, "ADVISORY_REST_LTP_COOLDOWN_SEC", 10.0))
    cache = _ADVISORY_REST_LTP_CACHE.get(cache_key)
    if isinstance(cache, dict):
        fetched_epoch = float(cache.get("fetched_epoch") or 0.0)
        if fetched_epoch > 0 and (now_epoch - fetched_epoch) < cooldown_sec:
            return cache.get("ltp"), cache.get("ltp_ts_epoch"), True
    last_attempt = float(_ADVISORY_REST_LTP_LAST_ATTEMPT.get(cache_key) or 0.0)
    if last_attempt > 0 and (now_epoch - last_attempt) < cooldown_sec:
        if isinstance(cache, dict):
            return cache.get("ltp"), cache.get("ltp_ts_epoch"), True
        return None, None, False
    _ADVISORY_REST_LTP_LAST_ATTEMPT[cache_key] = now_epoch
    ltp_val, ltp_ts_epoch = _fetch_option_ltp_rest(tradingsymbol)
    if ltp_val is None or ltp_ts_epoch is None:
        if isinstance(cache, dict):
            return cache.get("ltp"), cache.get("ltp_ts_epoch"), True
        return None, None, False
    _ADVISORY_REST_LTP_CACHE[cache_key] = {
        "ltp": float(ltp_val),
        "ltp_ts_epoch": float(ltp_ts_epoch),
        "fetched_epoch": now_epoch,
    }
    return float(ltp_val), float(ltp_ts_epoch), True


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
        return None


def _coerce_option_type(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ("CE", "CALL"):
        return "CE"
    if text in ("PE", "PUT"):
        return "PE"
    return None


def _coerce_strike(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _option_chain_meta_map(ttl_sec: int = 300) -> dict:
    now = time.time()
    cache = _CHAIN_CACHE.get("data") or {}
    ts = float(_CHAIN_CACHE.get("ts") or 0.0)
    if cache and (now - ts) < ttl_sec:
        return cache
    path = data_root() / "option_chain_latest.json"
    if not path.exists():
        return cache if isinstance(cache, dict) else {}
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return cache if isinstance(cache, dict) else {}
    by_token = {}
    by_contract = {}
    by_symbol_strike_type: dict[tuple, list] = {}
    if isinstance(raw, dict):
        for symbol, rows in raw.items():
            if not isinstance(rows, (list, tuple)):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                token = row.get("instrument_token")
                expiry = _coerce_expiry(row.get("expiry") or row.get("expiry_date"))
                strike = _coerce_strike(row.get("strike"))
                opt_type = _coerce_option_type(row.get("type") or row.get("option_type") or row.get("right"))
                tradingsymbol = row.get("tradingsymbol")
                meta = {
                    "symbol": symbol,
                    "expiry": expiry,
                    "strike": strike,
                    "type": opt_type,
                    "tradingsymbol": tradingsymbol,
                    "instrument_token": token,
                    "volume": _safe_float(row.get("volume")),
                    "current_volume": _safe_float(
                        row.get("current_volume")
                        if "current_volume" in row
                        else row.get("volume")
                    ),
                    "oi": _safe_float(row.get("oi")),
                    "oi_change": _safe_float(row.get("oi_change")),
                    "quote_age_sec": _safe_float(row.get("quote_age_sec")),
                }
                if token:
                    by_token[token] = meta
                if symbol and expiry and strike is not None and opt_type:
                    by_contract[(symbol, expiry, float(strike), opt_type)] = meta
                if symbol and strike is not None and opt_type:
                    key = (symbol, float(strike), opt_type)
                    by_symbol_strike_type.setdefault(key, []).append(meta)
    _CHAIN_CACHE["ts"] = now
    _CHAIN_CACHE["data"] = {
        "by_token": by_token,
        "by_contract": by_contract,
        "by_symbol_strike_type": by_symbol_strike_type,
    }
    return _CHAIN_CACHE["data"]


def _apply_option_chain_liquidity(entry: dict, meta: dict | None) -> dict:
    if not isinstance(entry, dict) or not isinstance(meta, dict) or not meta:
        return entry
    updated = False
    for field_name, source_fields in (
        ("volume", ("volume", "current_volume")),
        ("current_volume", ("current_volume", "volume")),
        ("oi", ("oi",)),
        ("oi_change", ("oi_change",)),
        ("quote_age_sec", ("quote_age_sec",)),
    ):
        if _safe_float(entry.get(field_name)) is not None:
            continue
        for source_field in source_fields:
            if source_field not in meta:
                continue
            value = _safe_float(meta.get(source_field))
            if value is None:
                continue
            entry[field_name] = value
            updated = True
            break
    if updated:
        if not entry.get("liquidity_source"):
            entry["liquidity_source"] = "option_chain_meta"
    return entry


def _instrument_meta_map(ttl_sec: int = 3600) -> dict:
    now = time.time()
    cache = _META_CACHE.get("data") or {}
    ts = float(_META_CACHE.get("ts") or 0.0)
    if cache and (now - ts) < ttl_sec:
        return cache
    try:
        from core.kite_client import kite_client
        meta = {}
        for exchange in ("NFO", "BFO"):
            for inst in kite_client.instruments_cached(exchange, ttl_sec=ttl_sec) or []:
                tok = inst.get("instrument_token")
                if not tok:
                    continue
                meta[tok] = {
                    "tradingsymbol": inst.get("tradingsymbol"),
                    "symbol": inst.get("name"),
                    "strike": inst.get("strike"),
                    "type": inst.get("instrument_type"),
                    "expiry": str(inst.get("expiry")) if inst.get("expiry") else None,
                    "segment": inst.get("segment"),
                }
        _META_CACHE["ts"] = now
        _META_CACHE["data"] = meta
        return meta
    except Exception:
        return cache if isinstance(cache, dict) else {}


def _lookup_instrument_meta_by_tradingsymbol(tradingsymbol: str | None) -> dict:
    tradingsymbol_text = str(tradingsymbol or "").strip().upper()
    meta_map = _instrument_meta_map()
    instrument_map_size = len(meta_map or {})
    if not tradingsymbol_text:
        logger.info(
            "[TOKEN_RESOLUTION] tradingsymbol=%s lookup_result=missing instrument_map_size=%d",
            tradingsymbol_text,
            instrument_map_size,
        )
        return {}
    for token_value, meta in (meta_map or {}).items():
        if str((meta or {}).get("tradingsymbol") or "").strip().upper() != tradingsymbol_text:
            continue
        logger.info(
            "[TOKEN_RESOLUTION] tradingsymbol=%s lookup_result=resolved instrument_map_size=%d instrument_token=%s",
            tradingsymbol_text,
            instrument_map_size,
            token_value,
        )
        out = dict(meta or {})
        out.setdefault("instrument_token", token_value)
        return out
    logger.warning(
        "[TOKEN_RESOLUTION] tradingsymbol=%s lookup_result=missing instrument_map_size=%d",
        tradingsymbol_text,
        instrument_map_size,
    )
    return {}


def _parse_timestamp(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _dedupe_queue_entries(entries: list[dict], new_entry: dict, window_min: int) -> list[dict]:
    symbol = new_entry.get("symbol")
    strike = new_entry.get("strike")
    expiry = new_entry.get("expiry_date") or new_entry.get("expiry")
    if not symbol or strike in (None, ""):
        return entries + [new_entry]
    new_ts = _parse_timestamp(new_entry.get("timestamp")) or datetime.now()
    window_sec = max(int(window_min), 1) * 60

    def _key(entry):
        return (
            entry.get("symbol"),
            entry.get("expiry_date") or entry.get("expiry"),
            entry.get("strike"),
        )

    def _score(entry):
        score = entry.get("trade_score")
        conf = entry.get("confidence")
        try:
            score_val = float(score) if score is not None else None
        except Exception:
            score_val = None
        try:
            conf_val = float(conf) if conf is not None else None
        except Exception:
            conf_val = None
        ts_val = _parse_timestamp(entry.get("timestamp")) or datetime.min
        return (
            score_val if score_val is not None else -1e9,
            conf_val if conf_val is not None else -1e9,
            ts_val.timestamp(),
        )

    dupes = []
    survivors = []
    for entry in entries:
        if _key(entry) == (symbol, expiry, strike):
            ts = _parse_timestamp(entry.get("timestamp")) or new_ts
            if abs((new_ts - ts).total_seconds()) <= window_sec:
                dupes.append(entry)
                continue
        survivors.append(entry)
    if not dupes:
        return survivors + [new_entry]
    candidates = dupes + [new_entry]
    best = sorted(candidates, key=_score, reverse=True)[0]
    survivors.append(best)
    return survivors


def _append_jsonl(paths, payload):
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            continue


def _cfg_bool(name, default=False):
    try:
        from config import config as cfg
        return bool(getattr(cfg, name, default))
    except Exception:
        return bool(default)


def _cfg_int(name, default=0):
    try:
        from config import config as cfg
        return int(getattr(cfg, name, default))
    except Exception:
        return int(default)

def _cfg_csv_set(name: str, default: str = "") -> set[str]:
    try:
        raw = str(getattr(cfg, name, default) or default)
    except Exception:
        raw = str(default or "")
    return {part.strip().upper() for part in raw.split(",") if part.strip()}

def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _first_present_float(mapping: dict, keys: tuple[str, ...]) -> float | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key not in mapping:
            continue
        value = _safe_float(mapping.get(key))
        if value is not None:
            return value
    return None


def _validation_reference_price(
    entry: dict,
    current_ltp: float | None = None,
    *,
    allow_live_ltp: bool = True,
) -> tuple[float | None, str | None]:
    for field_name in ("expected_entry", "suggested_entry", "entry_price"):
        value = _safe_float(entry.get(field_name))
        if value is not None:
            return value, field_name
    entry_val = _safe_float(entry.get("entry"))
    if entry_val is not None:
        return entry_val, "entry"
    signal_price = _safe_float(entry.get("signal_price"))
    if signal_price is not None:
        return signal_price, "signal_price"
    if allow_live_ltp:
        live_ltp = _safe_float(current_ltp)
        if live_ltp is None:
            live_ltp = _safe_float(entry.get("current_ltp"))
        if live_ltp is not None:
            return live_ltp, "current_ltp"
    return None, None


def _is_stale_pre_validation_entry(
    current_entry: float | None,
    executable_reference: float | None,
) -> bool:
    if current_entry is None or executable_reference is None or executable_reference <= 0:
        return current_entry is None and executable_reference is not None
    mismatch_pct = _safe_float(getattr(cfg, "OPTION_ENTRY_MISMATCH_PCT", 0.03))
    threshold = float(mismatch_pct if mismatch_pct is not None and mismatch_pct > 0 else 0.03)
    diff = abs(float(current_entry) - float(executable_reference)) / float(executable_reference)
    return bool(diff > threshold)


def _quote_spread_pct(entry: dict) -> float | None:
    spread = _safe_float(entry.get("spread_pct"))
    if spread is not None:
        return spread
    bid = _safe_float(entry.get("best_bid") or entry.get("opt_bid") or entry.get("bid"))
    ask = _safe_float(entry.get("best_ask") or entry.get("opt_ask") or entry.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    return (ask - bid) / mid


def _entry_execution_mode(entry: dict) -> str:
    if isinstance(entry, dict):
        for key in ("execution_mode", "mode"):
            value = str(entry.get(key) or "").strip().upper()
            if value:
                return value
        market_context = entry.get("market_context")
        if isinstance(market_context, dict):
            value = str(market_context.get("execution_mode") or "").strip().upper()
            if value:
                return value
    try:
        return str(getattr(cfg, "EXECUTION_MODE", "") or "").strip().upper()
    except Exception:
        return ""


def _entry_execution_mode_explicit(entry: dict) -> str:
    if isinstance(entry, dict):
        for key in ("execution_mode", "mode"):
            value = str(entry.get(key) or "").strip().upper()
            if value:
                return value
        market_context = entry.get("market_context")
        if isinstance(market_context, dict):
            value = str(market_context.get("execution_mode") or "").strip().upper()
            if value:
                return value
    return ""


def _entry_market_open(mode_for_entry: str, allow_stale_quotes_for_entry: bool) -> bool:
    mode_key = str(mode_for_entry or "").strip().upper()
    if mode_key in {"OFFHOURS", "PAPER", "BACKTEST"}:
        return False
    return not bool(allow_stale_quotes_for_entry)


def _coerce_optional_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _resolve_entry_market_open(
    entry: dict,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
) -> tuple[bool, str]:
    symbol = None
    explicit_entry_market_open = None
    explicit_market_context_open = None
    explicit_freshness_market_open = None
    exchange_clock_result = None
    if isinstance(entry, dict):
        symbol = str(entry.get("symbol") or "").strip().upper() or None
        explicit_entry_market_open = _coerce_optional_bool(entry.get("market_open"))
        if explicit_entry_market_open is not None:
            logger.debug(
                "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
                symbol,
                str(mode_for_entry or "").strip().upper(),
                explicit_entry_market_open,
                explicit_market_context_open,
                explicit_freshness_market_open,
                exchange_clock_result,
                explicit_entry_market_open,
                "entry.market_open",
            )
            return explicit_entry_market_open, "entry.market_open"
        market_context = entry.get("market_context")
        if isinstance(market_context, dict):
            explicit_market_context_open = _coerce_optional_bool(market_context.get("market_open"))
            if explicit_market_context_open is not None:
                logger.debug(
                    "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
                    symbol,
                    str(mode_for_entry or "").strip().upper(),
                    explicit_entry_market_open,
                    explicit_market_context_open,
                    explicit_freshness_market_open,
                    exchange_clock_result,
                    explicit_market_context_open,
                    "market_context.market_open",
                )
                return explicit_market_context_open, "market_context.market_open"
        explicit_freshness_market_open = _coerce_optional_bool(entry.get("freshness_market_open"))
        if explicit_freshness_market_open is not None:
            logger.debug(
                "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
                symbol,
                str(mode_for_entry or "").strip().upper(),
                explicit_entry_market_open,
                explicit_market_context_open,
                explicit_freshness_market_open,
                exchange_clock_result,
                explicit_freshness_market_open,
                "entry.freshness_market_open",
            )
            return explicit_freshness_market_open, "entry.freshness_market_open"
    try:
        exchange_clock_result = bool(is_market_open_ist())
        logger.debug(
            "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
            symbol,
            str(mode_for_entry or "").strip().upper(),
            explicit_entry_market_open,
            explicit_market_context_open,
            explicit_freshness_market_open,
            exchange_clock_result,
            exchange_clock_result,
            "exchange_clock",
        )
        return exchange_clock_result, "exchange_clock"
    except Exception:
        pass
    final_market_open = _entry_market_open(mode_for_entry, allow_stale_quotes_for_entry)
    logger.debug(
        "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
        symbol,
        str(mode_for_entry or "").strip().upper(),
        explicit_entry_market_open,
        explicit_market_context_open,
        explicit_freshness_market_open,
        exchange_clock_result,
        final_market_open,
        "mode_fallback",
    )
    return final_market_open, "mode_fallback"


def _manual_approval_required_for_entry(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if bool(entry.get("unresolved_contract")):
        return False
    if not _has_valid_broker_contract(entry):
        return False
    if not _cfg_bool("MANUAL_APPROVAL", False):
        return False
    required_modes = _cfg_csv_set("APPROVAL_REQUIRED_MODES", "PAPER,LIVE")
    mode = _entry_execution_mode(entry)
    if mode and mode not in required_modes:
        return False
    return True


def _allow_rest_fallback_for_mode(mode: str | None) -> bool:
    mode_key = str(mode or "").strip().upper()
    return mode_key in {"PAPER", "SIM", "OFFHOURS", "ADVISORY", "PLANNING"}


def _is_synthetic_offhours_row(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    option_ltp_source = str(entry.get("option_ltp_source") or "").strip().lower()
    quote_source = str(entry.get("quote_source") or "").strip().lower()
    return option_ltp_source == "synthetic_offhours" or quote_source == "synthetic_offhours"


def _clear_synthetic_offhours_state_for_live_takeover(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    for field in ("blockers", "hard_blockers", "soft_penalties", "warnings", "tradable_reasons_blocking"):
        values = [
            str(value or "").strip()
            for value in list(entry.get(field) or [])
            if str(value or "").strip() not in {"NO_LIVE_OPTION_FEED", "OFFHOURS_SYNTHETIC"}
        ]
        if values:
            entry[field] = values
        else:
            entry.pop(field, None)
    for field in ("hard_reason", "final_blocker", "permission_reason"):
        text = str(entry.get(field) or "").strip()
        if text in {"NO_LIVE_OPTION_FEED", "OFFHOURS_SYNTHETIC"}:
            entry.pop(field, None)
    entry.pop("subscription_failed", None)
    if str(entry.get("validation_reference_source") or "").strip().lower() == "synthetic_offhours":
        entry.pop("validation_reference_source", None)
    if str(entry.get("entry_status") or "").strip().upper() == "OFFHOURS_SYNTHETIC":
        entry.pop("entry_status", None)
    return entry


def _clear_synthetic_pricing_state_for_live_takeover(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    for field in (
        "expected_entry",
        "expected_entry_source",
        "entry_ref_price",
        "validation_reference_price",
        "validation_reference_source",
        "pre_validation_entry",
    ):
        entry.pop(field, None)
    return entry


def _should_force_live_reference_for_takeover(
    entry: dict,
    *,
    current_ltp: float | None,
    ltp_ts_epoch: float | None,
) -> bool:
    if not isinstance(entry, dict):
        return False
    if current_ltp is None or ltp_ts_epoch is None:
        return False
    if _is_synthetic_offhours_row(entry):
        return True
    return str(entry.get("strategy") or "").strip().upper() == "QUICK_SYNTH"


def _current_non_lifecycle_blockers(entry: dict) -> list[str]:
    blockers: list[str] = []
    for source in (
        list(entry.get("tradable_reasons_blocking") or []),
    ):
        for reason in source:
            text = str(reason or "").strip()
            if not text or text in blockers or text in TARGET_BLOCKER_CODES:
                continue
            blockers.append(text)
    for field in ("hard_reason", "final_blocker"):
        text = str(entry.get(field) or "").strip()
        if text.upper().startswith("HARD_"):
            continue
        if not text or text in blockers or text in TARGET_BLOCKER_CODES:
            continue
        blockers.append(text)
    return blockers


def _derive_advisory_readiness(entry: dict, blockers: list[str]) -> str:
    permission = str(entry.get("permission") or "").strip().upper()
    if bool(entry.get("unresolved_contract")) or permission == "BLOCK" or any(
        code in {"NO_TOKEN", "NO_LIVE_OPTION_FEED", "unresolved_contract"} for code in blockers
    ):
        return "BLOCKED"
    if permission == "EXECUTE" and not blockers:
        return "READY"
    if permission == "QUEUE_ONLY" and not blockers:
        return "QUEUE_ONLY"
    return "ADVISORY_ONLY"


def _dedupe_issue_codes(values) -> list[str]:
    out: list[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _derive_confidence_rejection_stage(entry: dict) -> str | None:
    if not isinstance(entry, dict):
        return None
    hard_blockers = list(entry.get("hard_blockers") or [])
    if hard_blockers:
        return "hard_gate"
    raw_threshold = _safe_float(entry.get("confidence_raw_gate_threshold"))
    final_threshold = _safe_float(entry.get("confidence_final_gate_threshold"))
    stages = [
        ("model_raw", _safe_float(entry.get("confidence_model_raw"))),
        ("micro", _safe_float(entry.get("confidence_after_micro"))),
        ("alpha", _safe_float(entry.get("confidence_after_alpha"))),
        ("latency", _safe_float(entry.get("confidence_after_latency"))),
        ("soft_veto", _safe_float(entry.get("confidence_after_soft_veto"))),
    ]
    if raw_threshold is not None:
        previous_value = None
        for stage_name, stage_value in stages:
            if stage_value is None:
                continue
            if stage_value < raw_threshold and (previous_value is None or previous_value >= raw_threshold):
                return stage_name
            previous_value = stage_value
    final_conf = _safe_float(entry.get("confidence_final"))
    after_soft_veto = _safe_float(entry.get("confidence_after_soft_veto"))
    if final_threshold is not None and final_conf is not None and final_conf < final_threshold:
        if after_soft_veto is not None and after_soft_veto < final_threshold:
            return "soft_veto"
        return "final_gate"
    if str(entry.get("permission_reason") or "").strip().upper() == "SOFT_CONFIDENCE_BELOW_THRESHOLD":
        return "final_gate"
    return None


def _log_confidence_rejection(entry: dict) -> None:
    if not isinstance(entry, dict):
        return
    stage = str(entry.get("confidence_rejection_stage") or "").strip()
    if not stage:
        return
    logger.info(
        "confidence_rejection symbol=%s strike=%s type=%s stage=%s raw_conf=%s final_conf=%s raw_threshold=%s final_threshold=%s",
        entry.get("symbol"),
        entry.get("strike"),
        entry.get("option_type") or entry.get("type") or entry.get("right"),
        stage,
        _safe_float(entry.get("confidence_raw")),
        _safe_float(entry.get("confidence_final")),
        _safe_float(entry.get("confidence_raw_gate_threshold")),
        _safe_float(entry.get("confidence_final_gate_threshold")),
    )


def _current_issue_codes(entry: dict) -> list[str]:
    issue_codes = _dedupe_issue_codes(list(entry.get("blockers") or []) + _current_non_lifecycle_blockers(entry))
    for field in ("validation_issue_code", "quote_validation_status", "hard_reason", "final_blocker", "entry_status"):
        text = str(entry.get(field) or "").strip()
        if not text:
            continue
        if field in {"entry_status", "quote_validation_status"} and text.upper() in {"DISPLAYABLE", "NON_EXECUTABLE", "MISSING"}:
            continue
        if field in {"validation_issue_code", "entry_status", "quote_validation_status"} and text.upper() in {"OK", "LIVE_OK", "VALID", "REST_FALLBACK", "OFFHOURS_SYNTHETIC"}:
            continue
        if field in {"hard_reason", "final_blocker"} and text.upper().startswith("HARD_"):
            continue
        if text not in issue_codes:
            issue_codes.append(text)
    return _dedupe_issue_codes(issue_codes)


def _apply_issue_classification(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    issue_codes = _current_issue_codes(entry)
    current_ltp = _safe_float(entry.get("current_ltp"))
    validation_reference_price = _safe_float(entry.get("validation_reference_price"))
    confidence_raw = _safe_float(entry.get("confidence_base"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("global_confidence"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("confidence"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("raw_signal_confidence"))
    existing_confidence_penalty = _safe_float(entry.get("confidence_penalty_total"))
    if existing_confidence_penalty is None:
        existing_confidence_penalty = _safe_float(entry.get("confidence_penalty"))
    if existing_confidence_penalty is None and confidence_raw is not None:
        softened_confidence = _safe_float(entry.get("confidence"))
        if softened_confidence is not None:
            existing_confidence_penalty = max(0.0, float(confidence_raw) - float(softened_confidence))
    if existing_confidence_penalty is None:
        existing_confidence_penalty = 0.0
    confidence_before_soft_veto = _safe_float(entry.get("confidence_before_soft_veto"))
    if confidence_before_soft_veto is None:
        confidence_before_soft_veto = confidence_raw
    confidence_after_soft_veto = _safe_float(entry.get("confidence_after_soft_veto"))
    if confidence_after_soft_veto is None and confidence_before_soft_veto is not None:
        confidence_after_soft_veto = max(
            0.0,
            min(1.0, float(confidence_before_soft_veto) - float(existing_confidence_penalty)),
        )
    confidence_penalty_soft_veto_total = _safe_float(entry.get("confidence_penalty_soft_veto_total"))
    if confidence_penalty_soft_veto_total is None:
        confidence_penalty_soft_veto_total = 0.0
    confidence_penalty_soft_veto_reasons = _dedupe_issue_codes(
        list(entry.get("confidence_penalty_soft_veto_reasons") or [])
    )
    quote_age_sec = _safe_float(
        entry.get("quote_age_sec")
        or entry.get("price_age_sec")
        or entry.get("option_ltp_age_sec")
    )
    market_open_for_entry, _market_open_source = _resolve_entry_market_open(
        entry,
        mode_for_entry,
        allow_stale_quotes_for_entry,
    )
    ctx = {
        "mode": mode_for_entry,
        "market_open": market_open_for_entry,
        "allow_stale_quotes": allow_stale_quotes_for_entry,
        "permission": entry.get("permission"),
        "entry_status": entry.get("entry_status"),
        "subscription_failed": bool(entry.get("subscription_failed")),
        "quote_source": entry.get("option_ltp_source") or entry.get("quote_source"),
        "quote_age_sec": quote_age_sec,
        "current_ltp": current_ltp,
        "reference_price": validation_reference_price,
        "advisory_id": entry.get("advisory_id") or entry.get("trade_id") or entry.get("trade_key"),
        "symbol": entry.get("symbol"),
    }
    gating_payload = entry.get("gating") if isinstance(entry.get("gating"), dict) else {}
    permission = str(entry.get("permission") or "").strip().upper()
    permission_base = str(entry.get("permission_base") or "").strip().upper()
    permission_downgraded_from = str(entry.get("permission_downgraded_from") or "").strip().upper()
    apply_execution_hard_gates = bool(
        permission == "EXECUTE"
        or permission_base == "EXECUTE"
        or permission_downgraded_from == "EXECUTE"
    )
    hard_blockers: list[str] = _dedupe_issue_codes(
        gating_payload.get("hard_reasons") if apply_execution_hard_gates else []
    )
    soft_penalties: list[str] = []
    warnings: list[str] = []
    issue_penalty = 0.0
    issue_classifications: list[dict] = []
    for code in issue_codes:
        classification = classify_issue(code, ctx)
        issue_classifications.append(
            {
                "code": classification.code,
                "category": classification.category,
                "penalty": classification.penalty,
                "reason": classification.reason,
                "evidence": dict(classification.evidence or {}),
            }
        )
        if classification.category == ISSUE_CATEGORY_HARD:
            if classification.code not in hard_blockers:
                hard_blockers.append(classification.code)
        elif classification.category == ISSUE_CATEGORY_SOFT:
            if classification.code not in soft_penalties:
                soft_penalties.append(classification.code)
            issue_penalty += float(classification.penalty or 0.0)
        elif classification.category == ISSUE_CATEGORY_WARNING:
            if classification.code not in warnings:
                warnings.append(classification.code)
    subscription_failed_without_live_quote = bool(
        str(entry.get("instrument") or entry.get("instrument_type") or "").strip().upper() == "OPT"
        and permission == "BLOCK"
        and current_ltp is None
        and str(entry.get("entry_status") or "").strip().upper() in {"NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN"}
        and hard_blockers
        and set(hard_blockers).issubset({"NO_TOKEN", "unresolved_contract", "MISSING_OPTION_TOKEN"})
    )
    if subscription_failed_without_live_quote:
        hard_blockers = ["NO_LIVE_OPTION_FEED"]
        if str(entry.get("permission_reason") or "").strip() in {"", "unresolved_contract"}:
            entry["permission_reason"] = "NO_LIVE_OPTION_FEED"
        if str(entry.get("hard_reason") or "").strip() in {"", "unresolved_contract"}:
            entry["hard_reason"] = "NO_LIVE_OPTION_FEED"
        if str(entry.get("final_blocker") or "").strip() in {"", "unresolved_contract"}:
            entry["final_blocker"] = "NO_LIVE_OPTION_FEED"
    if (permission == "BLOCK" or bool(entry.get("unresolved_contract"))) and not hard_blockers:
        fallback_code = str(entry.get("hard_reason") or entry.get("permission_reason") or "execution_blocked").strip()
        if fallback_code and fallback_code not in hard_blockers:
            hard_blockers.append(fallback_code)
    confidence_penalty_reasons = _dedupe_issue_codes(
        list(entry.get("confidence_penalty_reasons") or []) + soft_penalties
    )
    confidence_penalty_total = max(0.0, float(existing_confidence_penalty) + float(issue_penalty))
    confidence_final = confidence_raw
    if confidence_final is not None:
        confidence_final = max(0.0, min(1.0, float(confidence_raw) - float(confidence_penalty_total)))
    blockers = _dedupe_issue_codes(hard_blockers + soft_penalties + warnings)
    entry["hard_blockers"] = hard_blockers
    entry["soft_penalties"] = soft_penalties
    entry["warnings"] = warnings
    entry["blockers"] = blockers
    entry["confidence_base"] = confidence_raw
    entry["confidence_raw"] = confidence_raw
    entry["confidence_penalty"] = round(float(confidence_penalty_total), 6)
    entry["confidence_penalty_total"] = round(float(confidence_penalty_total), 6)
    entry["confidence_penalty_reasons"] = confidence_penalty_reasons
    entry["confidence_final"] = confidence_final
    if confidence_final is not None:
        entry["confidence"] = confidence_final
        entry["global_confidence"] = confidence_final
    entry["entry_source"] = (
        entry.get("expected_entry_source")
        or entry.get("entry_price_source")
        or entry.get("validation_reference_source")
        or entry.get("option_ltp_source")
        or entry.get("quote_source")
    )
    entry["issue_classifications"] = issue_classifications
    entry["confidence_before_soft_veto"] = confidence_before_soft_veto
    entry["confidence_after_soft_veto"] = confidence_after_soft_veto
    entry["confidence_penalty_soft_veto_total"] = round(float(confidence_penalty_soft_veto_total), 6)
    entry["confidence_penalty_soft_veto_reasons"] = confidence_penalty_soft_veto_reasons
    return finalize_trade_decision(entry)


def _refresh_lifecycle_blockers(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    current_ltp: float | None,
    validation_reference_price: float | None,
) -> dict:
    if not isinstance(entry, dict) or str(entry.get("instrument") or entry.get("instrument_type") or "").upper() != "OPT":
        return entry
    option_sla = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    canonical_live_sla = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
    stale_threshold = float(
        get_option_ltp_sla_sec(
            mode_for_entry,
            min(option_sla, canonical_live_sla),
            allow_stale_quotes=allow_stale_quotes_for_entry,
            market_open=_entry_market_open(mode_for_entry, allow_stale_quotes_for_entry),
            expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
        )
    )
    advisory_generation = (
        str(entry.get("advisory_id") or "").strip()
        or str(entry.get("trade_id") or "").strip()
        or str(entry.get("trade_key") or "").strip()
        or str(entry.get("timestamp") or "").strip()
    )
    active_records = evaluate_advisory_contract_blockers(
        get_blocker_registry("advisory"),
        now_ts=float(time.time()),
        symbol=entry.get("symbol"),
        expiry=entry.get("expiry_date") or entry.get("expiry"),
        strike=entry.get("strike"),
        right=entry.get("option_type") or entry.get("type") or entry.get("right"),
        advisory_generation=advisory_generation,
        instrument_token=entry.get("instrument_token"),
        tradingsymbol=entry.get("tradingsymbol"),
        live_price=current_ltp,
        reference_price=validation_reference_price,
        quote_age_sec=entry.get("price_age_sec"),
        stale_threshold_sec=stale_threshold,
        abs_tol=float(getattr(cfg, "OPTION_ENTRY_MISMATCH_ABS", 1.0)),
        pct_tol=float(getattr(cfg, "OPTION_ENTRY_MISMATCH_PCT", 0.03)),
        subscription_failed=bool(entry.get("subscription_failed")),
    )
    lifecycle_codes = [str(record.code) for record in active_records]
    blockers = list(dict.fromkeys(lifecycle_codes + _current_non_lifecycle_blockers(entry)))
    entry["blockers"] = blockers
    return entry


def _perm_rank(value: str | None) -> int:
    mapping = {
        "BLOCK": 0,
        "ADVISORY_ONLY": 1,
        "QUEUE_ONLY": 2,
        "EXECUTE": 3,
    }
    if value is None:
        return -1
    return mapping.get(str(value).strip().upper(), -1)


def _apply_permission_state(
    entry: dict,
    permission: str | None,
    reason: str | None,
    *,
    downgrade_reason: str | None = None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    prev_permission = str(entry.get("permission") or "").strip().upper()
    new_permission = str(permission or "").strip().upper()
    reason_text = str(reason or "").strip()
    if prev_permission and new_permission and _perm_rank(new_permission) < _perm_rank(prev_permission):
        entry["permission_downgraded_from"] = prev_permission
        entry["permission_downgrade_reason"] = str(downgrade_reason or reason_text or "")
    if new_permission:
        entry["permission"] = new_permission
    if reason_text:
        entry["permission_reason"] = reason_text
    return entry


def finalize_trade_decision(
    entry: dict,
    *,
    gate_decision_payload: dict | None = None,
    permission_payload: dict | None = None,
    entry_block_reason: str | None = None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    permission_payload = permission_payload if isinstance(permission_payload, dict) else {}
    gate_decision_payload = gate_decision_payload if isinstance(gate_decision_payload, dict) else {}
    base_permission = str(
        permission_payload.get("permission")
        or entry.get("permission_base")
        or entry.get("permission")
        or "ADVISORY_ONLY"
    ).strip().upper() or "ADVISORY_ONLY"
    base_reason = str(
        permission_payload.get("permission_reason")
        or entry.get("permission_reason_base")
        or entry.get("permission_reason")
        or ""
    ).strip()
    current_permission = str(entry.get("permission") or base_permission or "ADVISORY_ONLY").strip().upper() or "ADVISORY_ONLY"
    current_reason = str(entry.get("permission_reason") or base_reason or "").strip()
    hard_blockers = _dedupe_issue_codes(list(entry.get("hard_blockers") or []))
    blockers = _dedupe_issue_codes(list(entry.get("blockers") or []))
    gate_hard_reasons = _dedupe_issue_codes(list(gate_decision_payload.get("hard_reasons") or []))
    gate_hard_reason = gate_hard_reasons[0] if gate_hard_reasons else ""
    effective_entry_block_reason = str(
        entry_block_reason
        or entry.get("entry_block_reason")
        or ""
    ).strip()

    final_permission = current_permission
    final_reason = current_reason or base_reason
    if bool(entry.get("unresolved_contract")):
        final_permission = "BLOCK"
        final_reason = final_reason or "unresolved_contract"
    elif bool(entry.get("subscription_failed")) and str(entry.get("entry_status") or "").strip().upper() == "NO_LIVE_OPTION_FEED":
        final_permission = "BLOCK"
        final_reason = "NO_LIVE_OPTION_FEED"
    elif gate_hard_reason:
        if final_permission != "BLOCK":
            final_permission = "ADVISORY_ONLY"
        final_reason = gate_hard_reason
    elif effective_entry_block_reason and _is_entry_status_blocking(effective_entry_block_reason):
        if final_permission != "BLOCK":
            final_permission = "ADVISORY_ONLY"
        final_reason = effective_entry_block_reason
    elif str(final_reason).upper() == "SOFT_CONFIDENCE_BELOW_THRESHOLD":
        final_permission = "ADVISORY_ONLY"
    elif final_permission not in {"BLOCK", "ADVISORY_ONLY", "QUEUE_ONLY", "EXECUTE"}:
        final_permission = base_permission
        final_reason = base_reason

    entry = _apply_permission_state(
        entry,
        final_permission,
        final_reason,
        downgrade_reason=final_reason,
    )

    final_blocker = None
    if hard_blockers:
        final_blocker = hard_blockers[0]
    elif bool(entry.get("unresolved_contract")):
        final_blocker = "unresolved_contract"
    elif final_permission == "BLOCK":
        final_blocker = final_reason or effective_entry_block_reason or None
    entry["final_blocker"] = final_blocker

    if hard_blockers or final_permission == "BLOCK" or bool(entry.get("unresolved_contract")):
        readiness = "BLOCKED"
        execution_status = "blocked"
        is_executable = False
    elif final_permission == "EXECUTE":
        readiness = "READY"
        execution_status = "executable"
        is_executable = True
    elif final_permission == "QUEUE_ONLY":
        readiness = "QUEUE_ONLY"
        execution_status = "queue_only"
        is_executable = False
    else:
        readiness = "ADVISORY_ONLY"
        execution_status = "advisory_only"
        is_executable = False

    final_action = "BLOCK" if final_permission == "BLOCK" else (
        "EXECUTE"
        if final_permission == "EXECUTE" and not hard_blockers and not effective_entry_block_reason
        else ("QUEUE_ONLY" if final_permission == "QUEUE_ONLY" and not hard_blockers and not effective_entry_block_reason else "ADVISORY_ONLY")
    )

    entry["permission"] = final_permission
    entry["permission_reason"] = final_reason
    entry["readiness"] = readiness
    entry["execution_status"] = execution_status
    entry["final_action"] = final_action
    entry["advisory_visible"] = not _is_blocked_contract_row(entry)
    entry["is_executable"] = is_executable
    entry["entry_block_reason"] = effective_entry_block_reason or None
    return entry


def _apply_confidence_threshold_fields(
    entry: dict,
    *,
    confidence_value: float | None,
    execution_mode: str,
    hard_blockers: list[str] | None = None,
    entry_block_reason: str | None = None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    thresholds = resolve_confidence_thresholds(execution_mode)
    entry["threshold_display"] = float(thresholds["display"])
    entry["threshold_advisory"] = float(thresholds["advisory"])
    entry["threshold_execution"] = float(thresholds["execution"])
    entry["confidence_vs_threshold_reason"] = classify_confidence_vs_threshold(
        confidence_value,
        execution_mode=thresholds["mode"],
        hard_blocker=bool(hard_blockers),
        entry_blocked=bool(entry_block_reason) and not bool(hard_blockers),
    )
    return entry


def _material_change(old_entry: dict, new_entry: dict, tol: float) -> bool:
    for key in ("entry", "target", "stop"):
        old_val = _safe_float(old_entry.get(key))
        new_val = _safe_float(new_entry.get(key))
        if old_val is None and new_val is None:
            continue
        if old_val is None or new_val is None:
            return True
        if abs(old_val - new_val) > float(tol):
            return True
    return False


def _find_existing_by_key(data: list[dict], trade_key: str) -> tuple[int | None, dict | None]:
    if not trade_key:
        return None, None
    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            continue
        key = row.get("trade_key")
        if not key:
            key = compute_trade_key(
                row.get("symbol"),
                row.get("expiry_date") or row.get("expiry"),
                row.get("strike"),
                row.get("option_type") or row.get("type"),
                row.get("side"),
                row.get("strategy_id") or row.get("strategy") or row.get("generator"),
            )
            row["trade_key"] = key
        if key == trade_key:
            return idx, row
    return None, None


def _merge_trade_entry(data: list[dict], entry: dict) -> list[dict]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    trade_key = entry.get("trade_key")
    if not trade_key:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    idx, existing = _find_existing_by_key(data, trade_key)
    if existing is None:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    existing_status = str(existing.get("trade_status") or "").upper()
    if existing_status in {"INVALIDATED", "EXPIRED"}:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    tol = float(getattr(cfg, "TRADE_DEDUP_PRICE_TOL", 0.05)) if cfg else 0.05
    old_perm = existing.get("permission")
    new_perm = entry.get("permission")
    perm_escalated = _perm_rank(new_perm) > _perm_rank(old_perm)
    changed = _material_change(existing, entry, tol)
    if perm_escalated:
        trade_status = "UPDATED_PERMISSION"
    elif changed:
        trade_status = "UPDATED"
    else:
        trade_status = "REVALIDATED"

    existing_lifecycle = str(existing.get("status") or "").upper()
    incoming_lifecycle = str(entry.get("status") or "").upper()
    if existing_lifecycle in {"ACTIVE", "RESOLVED"} and incoming_lifecycle in {"PLANNING", "NEW", ""}:
        entry["status"] = existing_lifecycle

    # Keep entry deterministic for planning rows to avoid entry drift on each revalidation tick.
    # New entry may still populate when it was previously missing.
    freeze_planning_entry = bool(getattr(cfg, "FREEZE_PLANNING_ENTRY_ON_REVALIDATE", True)) if cfg else True
    if freeze_planning_entry and existing_lifecycle in {"PLANNING", "NEW", ""}:
        old_entry = _safe_float(existing.get("entry"))
        if old_entry is not None:
            entry["entry"] = existing.get("entry")
            if existing.get("suggested_entry") not in (None, "", "None"):
                entry["suggested_entry"] = existing.get("suggested_entry")

    update_count = int(existing.get("update_count") or 0) + 1
    first_seen = existing.get("first_seen") or entry.get("first_seen") or now_iso

    existing.update(entry)
    existing["first_seen"] = first_seen
    existing["last_seen"] = now_iso
    existing["update_count"] = update_count
    existing["trade_status"] = trade_status
    data[idx] = existing
    return data


def _derive_target(entry_val, stop_val, side, rr_default: float):
    try:
        entry_f = float(entry_val)
        stop_f = float(stop_val)
        rr_f = float(rr_default)
    except Exception:
        return None
    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return None
    side_val = str(side or "").upper()
    if side_val == "SELL":
        target = entry_f - (risk * rr_f)
    else:
        target = entry_f + (risk * rr_f)
    if target <= 0:
        return None
    return round(float(target), 2)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)


def _update_suggestions_status_latest(entry: dict, emission_result: dict | None = None) -> None:
    try:
        if not isinstance(entry, dict):
            return
        path = logs_dir() / "suggestions_status.json"
        suggestions_path = canonical_suggestions_log_path()
        current = _read_json(path, {})
        if not isinstance(current, dict):
            current = {}
        suggestion_count = int(current.get("suggestion_count") or 0)
        try:
            if suggestions_path.exists():
                with suggestions_path.open("r", encoding="utf-8") as fh:
                    suggestion_count = sum(1 for line in fh if str(line).strip())
        except Exception:
            pass
        primary_blocker = (
            str(entry.get("final_blocker") or "").strip()
            or str(entry.get("hard_reason") or "").strip()
            or str(entry.get("entry_status") or "").strip()
            or str(entry.get("permission_reason") or "").strip()
            or None
        )
        status = "blocked" if _is_entry_status_blocking(entry.get("entry_status")) or str(entry.get("permission") or "").upper() == "BLOCK" else "ok"
        emission_ok = not isinstance(emission_result, dict) or bool(emission_result.get("ok"))
        emission_target = (
            str(emission_result.get("target") or "").strip()
            if isinstance(emission_result, dict)
            else ""
        )
        emission_diagnostic = (
            dict(emission_result.get("diagnostic") or {})
            if isinstance(emission_result, dict) and isinstance(emission_result.get("diagnostic"), dict)
            else {}
        )
        if not emission_ok:
            status = "error"
        payload = dict(current)
        payload.update(
            {
                "ts_epoch": float(time.time()),
                "ts_local": datetime.now().astimezone().isoformat(),
                "status": status,
                "suggestion_count": int(suggestion_count),
                "latest_trade_id": entry.get("trade_id"),
                "latest_entry_status": entry.get("entry_status"),
                "latest_permission": entry.get("permission"),
                "latest_permission_reason": entry.get("permission_reason"),
                "primary_blocker": primary_blocker or current.get("primary_blocker"),
                "latest_emit_status": "ok" if emission_ok else "schema_failed",
                "latest_emit_target": emission_target or None,
                "latest_emit_reason": emission_diagnostic.get("failure_reason"),
            }
        )
        write_json_atomic(path, payload)
        rejected_status_path = logs_dir() / "rejected_candidates_status.json"
        if emission_target == "rejected_candidates" or _is_blocked_contract_row(entry):
            rejected_current = _read_json(rejected_status_path, {})
            if not isinstance(rejected_current, dict):
                rejected_current = {}
            rejected_payload = dict(rejected_current)
            rejected_payload.update(
                {
                    "ts_epoch": float(time.time()),
                    "ts_local": datetime.now().astimezone().isoformat(),
                    "status": "ok" if emission_ok else "error",
                    "latest_trade_id": entry.get("trade_id"),
                    "latest_entry_status": entry.get("entry_status"),
                    "latest_permission": entry.get("permission"),
                    "latest_permission_reason": entry.get("permission_reason"),
                    "latest_emit_status": "ok" if emission_ok else "schema_failed",
                    "latest_emit_target": emission_target or "rejected_candidates",
                    "latest_emit_reason": emission_diagnostic.get("failure_reason"),
                    "primary_blocker": primary_blocker or rejected_current.get("primary_blocker"),
                }
            )
            write_json_atomic(rejected_status_path, rejected_payload)
        engine_path = logs_dir() / "engine_cycle_status.json"
        engine_current = _read_json(engine_path, {})
        if isinstance(engine_current, dict):
            engine_payload = dict(engine_current)
            engine_payload.update(
                {
                    "ts_epoch": float(time.time()),
                    "cycle_ok": bool(emission_ok),
                    "cycle_stage": "emit_failed" if not emission_ok else ("blocked" if status == "blocked" else "ok"),
                    "reason": "advisory_emit_schema_error" if not emission_ok else (primary_blocker if status == "blocked" else "ok"),
                    "subreason": emission_diagnostic.get("failure_reason") if not emission_ok else "",
                    "candidates_seen": max(int(engine_current.get("candidates_seen") or 0), int(suggestion_count)),
                    "candidates_enqueued": max(int(engine_current.get("candidates_enqueued") or 0), int(suggestion_count)),
                    "primary_blocker": primary_blocker or engine_current.get("primary_blocker"),
                    "latest_emit_status": "ok" if emission_ok else "schema_failed",
                    "latest_emit_target": emission_target or None,
                }
            )
            write_json_atomic(engine_path, engine_payload)
    except Exception:
        logger.warning("suggestions_status_update_failed trade_id=%s", entry.get("trade_id") if isinstance(entry, dict) else None)


def _looks_like_trade(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("symbol") or payload.get("trade_id"):
        return True
    if payload.get("strike") is not None:
        return True
    if payload.get("type") or payload.get("option_type"):
        return True
    return False


def _normalize_queue_row(row: dict) -> dict:
    had_explicit_quote_validation_status = isinstance(row, dict) and "quote_validation_status" in row
    out = dict(row or {})
    canonical_entry = any(
        key in out
        for key in (
            "execution_entry",
            "execution_entry_source",
            "execution_entry_status",
            "display_entry",
            "display_entry_source",
            "display_entry_status",
            "entry_reason",
            "entry_clear_reason",
        )
    )
    original_status = str(out.get("status_raw") or out.get("status") or "PLANNING").strip().upper() or "PLANNING"
    out["status_raw"] = original_status
    out = _canonicalize_entry_lifecycle(
        out,
        mode_for_entry=_entry_execution_mode(out),
        allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(out)),
        align_for_schema=False,
    )
    out.setdefault("symbol", out.get("underlying"))
    if out.get("expiry_date") in (None, "", "None"):
        out["expiry_date"] = _coerce_expiry(out.get("expiry")) or out.get("expiry")
    if out.get("expiry") in (None, "", "None"):
        out["expiry"] = out.get("expiry_date")
    opt_type = _coerce_option_type(out.get("option_type") or out.get("type") or out.get("right"))
    if opt_type:
        out["option_type"] = opt_type
        out["type"] = opt_type
    strike = out.get("strike")
    strike_val = _coerce_strike(strike)
    if strike_val is not None:
        out["strike"] = strike_val
    out.setdefault("status", original_status)
    if _is_blocked_contract_row(out):
        out = _apply_unresolved_contract_state(out)
    quote_validation_status = str(out.get("quote_validation_status") or out.get("entry_status") or "").strip()
    if quote_validation_status:
        out["quote_validation_status"] = quote_validation_status
    if _safe_float(out.get("display_entry")) is not None and _safe_float(out.get("entry")) is None:
        out["entry"] = _safe_float(out.get("display_entry"))
    if (
        (
            ("entry_status" not in out or out.get("entry_status") in (None, "", "None"))
            or (
                canonical_entry
                and not had_explicit_quote_validation_status
                and str(out.get("entry_status") or "").strip().upper() in {"OK", "LIVE_OK", "VALID"}
            )
        )
        and "display_entry_status" in out
        and out.get("display_entry_status") not in (None, "", "None")
    ):
        out["entry_status"] = str(out.get("display_entry_status")).lower()
    if (
        ("entry_source" not in out or out.get("entry_source") in (None, "", "None"))
        and "display_entry_source" in out
        and out.get("display_entry_source") not in (None, "", "None")
    ):
        out["entry_source"] = out.get("display_entry_source")
    out.setdefault("entry", out.get("entry_price"))
    entry_status = str(out.get("entry_status") or "").strip().upper()
    token_missing_advisory = out.get("instrument_token") in (None, "", "None") and bool(out.get("tradingsymbol"))
    if out.get("entry") in ("", "None"):
        out["entry"] = None
    # Fail-closed normalization: executable entry must come from validated quote fields.
    # Do not carry stale/model reference prices as actionable entry.
    if canonical_entry:
        pass
    elif entry_status and entry_status != "OK":
        suggested = _safe_float(out.get("suggested_entry"))
        current_ltp = _safe_float(out.get("current_ltp"))
        if token_missing_advisory:
            planned_entry = suggested
            if planned_entry is None:
                planned_entry = _safe_float(out.get("entry_price"))
            out["entry"] = planned_entry
        else:
            out["entry"] = suggested if suggested is not None else current_ltp
    elif out.get("entry") is None:
        suggested = _safe_float(out.get("suggested_entry"))
        if suggested is not None:
            out["entry"] = suggested
        else:
            fallback_entry = _safe_float(out.get("entry_price"))
            if fallback_entry is not None:
                out["entry"] = fallback_entry
    if _safe_float(out.get("expected_entry")) is None:
        expected_entry = _safe_float(out.get("suggested_entry"))
        if expected_entry is None:
            expected_entry = _safe_float(out.get("mark_price"))
        if expected_entry is None:
            expected_entry = _safe_float(out.get("entry"))
        if expected_entry is not None:
            out["expected_entry"] = expected_entry
    if _safe_float(out.get("fill_entry")) is None:
        fill_entry = _safe_float(out.get("fill_price"))
        if fill_entry is None:
            fill_entry = _safe_float(out.get("avg_fill_price"))
        if fill_entry is not None:
            out["fill_entry"] = fill_entry
    for key in ("symbol", "expiry_date", "strike", "type", "status"):
        out.setdefault(key, None)
    ts_ms = _coerce_timestamp_epoch_ms(out)
    out["timestamp_epoch_ms"] = int(ts_ms)
    out["timestamp_utc_iso"] = _epoch_ms_to_utc_iso(ts_ms)
    # Backward-compatible timestamp field
    if out.get("timestamp") in (None, "", "None"):
        out["timestamp"] = out["timestamp_utc_iso"]
    else:
        out["timestamp"] = str(out.get("timestamp"))
    if _is_blocked_contract_row(out):
        out = _apply_unresolved_contract_state(out)
    if original_status in {"APPROVED", "ACTIVE"}:
        out["status"] = original_status
    elif bool(out.get("unresolved_contract")):
        out["status"] = "BLOCKED_CONTRACT"
    else:
        out["status"] = _derive_review_status(out, fallback_status=original_status)
    out = _enforce_executable_entry_integrity(out)
    out = enforce_entry_contract(out, stage="review_queue.normalize")
    return out


def _epoch_ms_to_utc_iso(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).isoformat()


def _coerce_epoch_ms(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        val = float(value)
        if val <= 0:
            return None
        # If already in ms, keep as-is; otherwise treat as seconds.
        if val >= 10_000_000_000:
            return int(val)
        return int(val * 1000.0)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _coerce_epoch_ms(float(text))
    except Exception:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000.0)


def _coerce_timestamp_epoch_ms(row: dict) -> int:
    for key in ("timestamp_epoch_ms", "timestamp_utc_iso", "timestamp"):
        ts_ms = _coerce_epoch_ms(row.get(key))
        if ts_ms is not None:
            return int(ts_ms)
    return int(time.time() * 1000.0)


def load_queue_rows(path: Path, rewrite_healed: bool = True) -> list[dict]:
    if not path.exists():
        return []
    raw = _read_json(path, [])
    if not isinstance(raw, list):
        logger.warning("queue_load_invalid_shape path=%s type=%s", path, type(raw).__name__)
        return []
    rows: list[dict] = []
    modified = False
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("queue_load_skip_non_dict path=%s item_type=%s", path, type(item).__name__)
            modified = True
            continue
        try:
            normalized = _normalize_queue_row(item)
        except EntryContractViolation:
            raise
        except Exception:
            logger.warning("queue_load_row_normalize_failed path=%s", path)
            modified = True
            continue
        if normalized != item:
            modified = True
        rows.append(normalized)
    if rewrite_healed and modified:
        try:
            write_queue_rows(path, rows)
        except Exception:
            logger.warning("queue_heal_write_failed path=%s", path)
    return rows


def write_queue_rows(path: Path, rows: list[dict]) -> None:
    safe_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        safe_rows.append(_normalize_queue_row(row))
    _write_json(path, safe_rows)


def _load_approvals():
    raw = _read_json(APPROVED_PATH, {"version": 2, "approvals": {}})
    if isinstance(raw, dict) and isinstance(raw.get("approvals"), dict):
        return raw
    # Backward-compat: old format was list[trade_id]. Keep detectable but fail-closed by default.
    if isinstance(raw, list):
        legacy = {}
        for trade_id in raw:
            legacy[str(trade_id)] = {"legacy": True, "status": "APPROVED"}
        return {"version": 2, "approvals": legacy}
    return {"version": 2, "approvals": {}}


def canonical_order_payload(trade):
    try:
        intent = OrderIntent.from_trade(trade, mode="PAPER")
        return intent.to_canonical_dict()
    except Exception:
        return {}


def order_payload_hash(trade):
    payload = canonical_order_payload(trade)
    if not payload:
        return ""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def approval_status(trade_id, payload_hash=None, now_epoch=None):
    trade_id = str(trade_id or "")
    if not trade_id:
        return False, "approval_missing_trade_id"
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    strict = True
    if not _cfg_bool("APPROVAL_STRICT_PAYLOAD_HASH", True):
        return False, "approval_strict_mode_required"
    store = _load_approvals()
    record = (store.get("approvals") or {}).get(trade_id)
    if not record:
        return False, "approval_missing"
    if not isinstance(record, dict):
        return False, "approval_record_invalid"
    if record.get("status") and str(record.get("status")).upper() != "APPROVED":
        return False, "approval_not_approved"
    if record.get("legacy") is True and strict:
        return False, "approval_legacy_record"
    expires_epoch = record.get("expires_epoch")
    try:
        if expires_epoch is not None and now_epoch > float(expires_epoch):
            return False, "approval_expired"
    except Exception:
        return False, "approval_expiry_invalid"
    approved_hash = record.get("payload_hash")
    if strict and not approved_hash:
        return False, "approval_missing_payload_hash"
    if payload_hash and approved_hash and payload_hash != approved_hash:
        return False, "approval_payload_mismatch"
    if payload_hash and strict and not approved_hash:
        return False, "approval_missing_payload_hash"
    return True, "approved"

def _trade_attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _build_review_queue_entry(trade, *, extra=None, default_mode: str = "ADVISORY") -> tuple[dict, str, bool, bool]:
    mode_for_entry = default_mode
    allow_stale_quotes_for_entry = True
    strike_val = _trade_attr(trade, "strike")
    trade_id = _trade_attr(trade, "trade_id")
    if strike_val in (None, 0) and trade_id and "ATM" in str(trade_id):
        strike_val = "ATM"
    strategy_id = _trade_attr(trade, "strategy_id") or _trade_attr(trade, "strategy") or _trade_attr(trade, "generator")
    entry = {
        "trade_id": trade_id,
        "symbol": _trade_attr(trade, "symbol"),
        "underlying": _trade_attr(trade, "underlying") or _trade_attr(trade, "symbol"),
        "instrument_id": _trade_attr(trade, "instrument_id"),
        "tradingsymbol": _trade_attr(trade, "tradingsymbol"),
        "strike": strike_val,
        "instrument": _trade_attr(trade, "instrument"),
        "instrument_token": _trade_attr(trade, "instrument_token"),
        "expiry": _trade_attr(trade, "expiry"),
        "expiry_date": _trade_attr(trade, "expiry_date"),
        "type": _trade_attr(trade, "right") or _trade_attr(trade, "option_type"),
        "option_type": _trade_attr(trade, "option_type") or _trade_attr(trade, "right"),
        "side": _trade_attr(trade, "side"),
        # Preserve raw trade.entry when present, but keep entry_price as the
        # backward-compatible fallback so pre-validation state is not lost.
        "entry": _trade_attr(trade, "entry", None) if _trade_attr(trade, "entry", None) not in (None, "", "None") else _trade_attr(trade, "entry_price"),
        "entry_source": _trade_attr(trade, "entry_source", None),
        "entry_price": _trade_attr(trade, "entry_price"),
        "entry_price_source": _trade_attr(trade, "entry_price_source", None),
        "entry_condition": _trade_attr(trade, "entry_condition") or "BREAKOUT",
        "entry_ref_price": _trade_attr(trade, "entry_ref_price"),
        "signal_price": _trade_attr(trade, "signal_price", None),
        "stop": _trade_attr(trade, "stop_loss"),
        "stop_price": _trade_attr(trade, "stop_price") or _trade_attr(trade, "stop_loss"),
        "target": _trade_attr(trade, "target"),
        "target_price": _trade_attr(trade, "target_price") or _trade_attr(trade, "target"),
        "original_stop": _trade_attr(trade, "original_stop") or _trade_attr(trade, "stop_loss"),
        "current_stop": _trade_attr(trade, "current_stop") or _trade_attr(trade, "stop_loss"),
        "trail_enabled": _trade_attr(trade, "trail_enabled"),
        "trail_rule": _trade_attr(trade, "trail_rule") or getattr(cfg, "TRAIL_RULE_DEFAULT", "MFE_MINUS_OFFSET"),
        "trail_offset": _trade_attr(trade, "trail_offset"),
        "trail_start": _trade_attr(trade, "trail_start") or getattr(cfg, "TRAIL_START_DEFAULT", "AFTER_1R"),
        "mfe_price": _trade_attr(trade, "mfe_price"),
        "trail_stop": _trade_attr(trade, "trail_stop"),
        "last_update_ts": _trade_attr(trade, "last_update_ts"),
        "exit_signal": _trade_attr(trade, "exit_signal"),
        "exit_reason": _trade_attr(trade, "exit_reason"),
        "status": _trade_attr(trade, "status") or "PLANNING",
        "activated_ts": _trade_attr(trade, "activated_ts"),
        "activation_price": _trade_attr(trade, "activation_price"),
        "fill_price": _trade_attr(trade, "fill_price"),
        "ltp_at_activation": _trade_attr(trade, "ltp_at_activation"),
        "qty": _trade_attr(trade, "qty"),
        "confidence": _trade_attr(trade, "confidence"),
        "strategy": _trade_attr(trade, "strategy"),
        "strategy_id": strategy_id,
        "regime": _trade_attr(trade, "regime"),
        "regime_confidence": _trade_attr(trade, "regime_confidence"),
        "day_confidence": _trade_attr(trade, "day_confidence"),
        "orb_bias": _trade_attr(trade, "orb_bias"),
        "tier": _trade_attr(trade, "tier", None),
        "legs": _trade_attr(trade, "legs", None),
        "max_profit": _trade_attr(trade, "max_profit", None),
        "max_loss": _trade_attr(trade, "max_loss", None),
        "max_profit_label": _trade_attr(trade, "max_profit_label", None),
        "max_loss_label": _trade_attr(trade, "max_loss_label", None),
        "breakeven_low": _trade_attr(trade, "breakeven_low", None),
        "breakeven_high": _trade_attr(trade, "breakeven_high", None),
        "est_pnl_at_ltp": _trade_attr(trade, "est_pnl_at_ltp", None),
        "opt_ltp": _trade_attr(trade, "opt_ltp", None),
        "opt_bid": _trade_attr(trade, "opt_bid", None),
        "opt_ask": _trade_attr(trade, "opt_ask", None),
        "volume": _trade_attr(trade, "volume", None),
        "current_volume": _trade_attr(trade, "current_volume", None),
        "oi": _trade_attr(trade, "oi", None),
        "oi_change": _trade_attr(trade, "oi_change", None),
        "liquidity_source": _trade_attr(trade, "liquidity_source", None),
        "liquidity_age_sec": _trade_attr(trade, "liquidity_age_sec", None),
        "liquidity_cache_hit": _trade_attr(trade, "liquidity_cache_hit", None),
        "liquidity_missing_fields": _trade_attr(trade, "liquidity_missing_fields", None),
        "tick_volume": _trade_attr(trade, "tick_volume", None),
        "spread_pct": _trade_attr(trade, "spread_pct", None),
        "quote_ok": _trade_attr(trade, "quote_ok", None),
        "underlying_spot": _trade_attr(trade, "underlying_spot", None),
        "spot_source": _trade_attr(trade, "spot_source", None),
        "option_ltp_source": _trade_attr(trade, "option_ltp_source", None),
        "option_ltp_timestamp": _trade_attr(trade, "option_ltp_timestamp", None),
        "current_ltp": _trade_attr(trade, "current_ltp", None),
        "suggested_entry": _trade_attr(trade, "suggested_entry", None),
        "expected_entry": _trade_attr(trade, "expected_entry", None),
        "expected_entry_source": _trade_attr(trade, "expected_entry_source", None),
        "fill_entry": _trade_attr(trade, "fill_entry", None),
        "execution_entry": _trade_attr(trade, "execution_entry", None),
        "execution_entry_source": _trade_attr(trade, "execution_entry_source", None),
        "execution_entry_status": _trade_attr(trade, "execution_entry_status", None),
        "display_entry": _trade_attr(trade, "display_entry", None),
        "display_entry_source": _trade_attr(trade, "display_entry_source", None),
        "display_entry_status": _trade_attr(trade, "display_entry_status", None),
        "entry_reason": _trade_attr(trade, "entry_reason", None),
        "entry_clear_reason": _trade_attr(trade, "entry_clear_reason", None),
        "price_age_sec": _trade_attr(trade, "price_age_sec", None),
        "quote_age_sec": _trade_attr(trade, "quote_age_sec", None),
        "entry_status": _trade_attr(trade, "entry_status", None),
        "price_source": _trade_attr(trade, "price_source", None),
        "quote_source": _trade_attr(trade, "quote_source", None),
        "mark_price": _trade_attr(trade, "mark_price", None),
        "mid_price": _trade_attr(trade, "mid_price", None),
        "best_bid": _trade_attr(trade, "best_bid", None),
        "best_ask": _trade_attr(trade, "best_ask", None),
        "entry_price_proxy": _trade_attr(trade, "entry_price_proxy", None),
        "entry_price_proxy_buy": _trade_attr(trade, "entry_price_proxy_buy", None),
        "entry_price_proxy_sell": _trade_attr(trade, "entry_price_proxy_sell", None),
        "chain_source": _trade_attr(trade, "chain_source", None),
        "trade_score": _trade_attr(trade, "trade_score", None),
        "trade_alignment": _trade_attr(trade, "trade_alignment", None),
        "trade_score_detail": _trade_attr(trade, "trade_score_detail", None),
        "direction": _trade_attr(trade, "direction", None),
        "execution_mode": _trade_attr(trade, "execution_mode", None),
        "mode": _trade_attr(trade, "mode", None),
        "market_open": _trade_attr(trade, "market_open", None),
        "market_context": _trade_attr(trade, "market_context", None),
        "global_confidence": _trade_attr(trade, "global_confidence", None),
        "permission": _trade_attr(trade, "permission", None),
        "permission_reason": _trade_attr(trade, "permission_reason", None),
        "countertrend": _trade_attr(trade, "countertrend", None),
        "raw_signal_confidence": _trade_attr(trade, "raw_signal_confidence", None),
        "confidence_model_raw": _trade_attr(trade, "confidence_model_raw", None),
        "confidence_model_component": _trade_attr(trade, "confidence_model_component", None),
        "confidence_micro_component": _trade_attr(trade, "confidence_micro_component", None),
        "confidence_micro_blend_method": _trade_attr(trade, "confidence_micro_blend_method", None),
        "confidence_after_micro": _trade_attr(trade, "confidence_after_micro", None),
        "confidence_after_alpha": _trade_attr(trade, "confidence_after_alpha", None),
        "confidence_after_latency": _trade_attr(trade, "confidence_after_latency", None),
        "confidence_before_soft_veto": _trade_attr(trade, "confidence_before_soft_veto", None),
        "confidence_after_soft_veto": _trade_attr(trade, "confidence_after_soft_veto", None),
        "confidence_penalty_soft_veto_total": _trade_attr(trade, "confidence_penalty_soft_veto_total", None),
        "confidence_penalty_soft_veto_reasons": _trade_attr(trade, "confidence_penalty_soft_veto_reasons", None),
        "confidence_gate_threshold": _trade_attr(trade, "confidence_gate_threshold", None),
        "confidence_raw_gate_threshold": _trade_attr(trade, "confidence_raw_gate_threshold", None),
        "confidence_final_gate_threshold": _trade_attr(trade, "confidence_final_gate_threshold", None),
        "confidence_rejection_stage": _trade_attr(trade, "confidence_rejection_stage", None),
        "confidence_base": _trade_attr(trade, "confidence_base", None),
        "confidence_penalty_total": _trade_attr(trade, "confidence_penalty_total", None),
        "confidence_penalty_reasons": _trade_attr(trade, "confidence_penalty_reasons", None),
        "snapshot_id": _trade_attr(trade, "snapshot_id", None),
        "timestamp": str(_trade_attr(trade, "timestamp")),
        "upstox_instrument_key": _trade_attr(trade, "upstox_instrument_key"),
    }
    if extra:
        entry.update(extra)
    mode_for_entry = _entry_execution_mode(entry) or mode_for_entry
    allow_stale_quotes_for_entry = _allow_rest_fallback_for_mode(mode_for_entry)
    market_open_for_entry, market_open_source = _resolve_entry_market_open(
        entry,
        mode_for_entry,
        allow_stale_quotes_for_entry,
    )
    entry["market_open"] = market_open_for_entry
    entry["market_open_source"] = market_open_source
    return entry, mode_for_entry, allow_stale_quotes_for_entry, market_open_for_entry


def _apply_quote_and_entry_logic(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> dict:
    if entry.get("instrument") == "OPT":
        input_token_missing = entry.get("instrument_token") in (None, "", "None") and bool(entry.get("tradingsymbol"))
        entry = _enrich_contract_identity(entry)
        if entry.get("target") in (None, "", "None"):
            rr_default = float(getattr(cfg, "TARGET_RR_DEFAULT", 1.5)) if cfg else 1.5
            derived_target = _derive_target(entry.get("entry"), entry.get("stop"), entry.get("side"), rr_default)
            if derived_target is not None:
                entry["target"] = derived_target
                entry["target_derived"] = True
                entry["target_rr"] = rr_default
        unresolved_contract = _is_unresolved_option_contract(entry)
        if unresolved_contract:
            entry = _apply_unresolved_contract_state(entry)
        else:
            entry = _clear_unresolved_contract_state(entry)
            token_val = entry.get("instrument_token")
            subscription_ok = True
            if token_val is not None:
                try:
                    subscription_ok = bool(
                        ensure_subscribed_tokens([int(token_val)], reason="trade_created", symbol=entry.get("symbol"))
                    )
                except Exception:
                    subscription_ok = False
            token_value = entry.get("instrument_token")
            current_ltp = None
            ltp_ts_epoch = None
            rest_fallback_used = False
            if token_value not in (None, "", "None"):
                try:
                    current_ltp, ltp_ts_epoch = get_ltp(token_value, decision_path=True)
                except TypeError:
                    current_ltp, ltp_ts_epoch = get_ltp(token_value)
                except Exception:
                    current_ltp, ltp_ts_epoch = None, None
            token_present = token_value not in (None, "", "None")
            explicit_mode_for_fallback = _entry_execution_mode_explicit(entry)
            allow_rest_fallback = bool(
                token_present
                and entry.get("tradingsymbol")
                and (subscription_ok or _allow_rest_fallback_for_mode(explicit_mode_for_fallback))
            )
            if current_ltp is None and allow_rest_fallback:
                fallback_ltp, fallback_ts_epoch, fallback_used = _resolve_rest_fallback_ltp(
                    token_value=token_value,
                    tradingsymbol=entry.get("tradingsymbol"),
                    now_epoch=time.time(),
                )
                if fallback_ltp is not None and fallback_ts_epoch is not None:
                    current_ltp, ltp_ts_epoch = float(fallback_ltp), float(fallback_ts_epoch)
                    rest_fallback_used = bool(fallback_used)
            synthetic_offhours = _is_synthetic_offhours_row(entry)
            live_quote_available = current_ltp is not None and ltp_ts_epoch is not None
            live_quote_source = "rest_fallback" if rest_fallback_used else "tick_store"
            token_missing_identified = bool(input_token_missing)
            live_took_over_synthetic = _should_force_live_reference_for_takeover(
                entry,
                current_ltp=current_ltp,
                ltp_ts_epoch=ltp_ts_epoch,
            )
            if live_took_over_synthetic:
                entry = _clear_synthetic_offhours_state_for_live_takeover(entry)
                entry = _clear_synthetic_pricing_state_for_live_takeover(entry)
                synthetic_offhours = False
            validation_signal_price = _safe_float(entry.get("signal_price"))
            pre_validation_entry = None if live_took_over_synthetic else _safe_float(entry.get("entry"))
            if live_took_over_synthetic:
                validation_reference_entry = dict(entry)
                for field in (
                    "expected_entry",
                    "expected_entry_source",
                    "entry_ref_price",
                    "validation_reference_price",
                    "validation_reference_source",
                    "pre_validation_entry",
                    "suggested_entry",
                    "entry",
                    "entry_price",
                    "signal_price",
                ):
                    validation_reference_entry.pop(field, None)
                validation_reference_price, validation_reference_source = _validation_reference_price(
                    validation_reference_entry,
                    current_ltp=current_ltp,
                )
                validation_reference_source = live_quote_source
            else:
                validation_reference_price, validation_reference_source = _validation_reference_price(
                    entry,
                    current_ltp=current_ltp,
                    allow_live_ltp=not token_missing_identified,
                )
            if (not token_missing_identified) and _safe_float(entry.get("expected_entry")) is None and validation_reference_price is not None:
                entry["expected_entry"] = validation_reference_price
            if (not token_missing_identified) and _is_stale_pre_validation_entry(pre_validation_entry, validation_reference_price):
                entry["entry"] = validation_reference_price
            if synthetic_offhours:
                synthetic_entry = _safe_float(entry.get("expected_entry"))
                if synthetic_entry is None:
                    synthetic_entry = _safe_float(entry.get("entry_price"))
                if synthetic_entry is None:
                    synthetic_entry = validation_reference_price
                entry["current_ltp"] = current_ltp
                entry["option_ltp_timestamp"] = ltp_ts_epoch
                entry["validation_signal_price"] = validation_signal_price
                entry["validation_reference_price"] = synthetic_entry
                entry["validation_reference_source"] = "synthetic_offhours"
                entry["pre_validation_entry"] = pre_validation_entry
                entry["entry_status"] = "OFFHOURS_SYNTHETIC"
                entry["suggested_entry"] = synthetic_entry
                if _safe_float(entry.get("expected_entry")) is None and synthetic_entry is not None:
                    entry["expected_entry"] = synthetic_entry
                if _is_stale_pre_validation_entry(pre_validation_entry, synthetic_entry):
                    entry["entry"] = synthetic_entry
                if not entry.get("option_ltp_source"):
                    entry["option_ltp_source"] = "synthetic_offhours"
            else:
                if token_missing_identified:
                    advisory_entry = _safe_float(entry.get("suggested_entry"))
                    if advisory_entry is None:
                        advisory_entry = pre_validation_entry
                    if advisory_entry is None:
                        advisory_entry = _safe_float(entry.get("entry_price"))
                    if advisory_entry is None:
                        advisory_entry = _safe_float(entry.get("signal_price"))
                    if advisory_entry is None:
                        advisory_entry = _safe_float(entry.get("expected_entry"))
                    entry["current_ltp"] = current_ltp
                    entry["option_ltp_timestamp"] = ltp_ts_epoch
                    entry["price_age_sec"] = None
                    entry["freshness_reason"] = None
                    entry["freshness_market_open"] = market_open_for_entry
                    entry["freshness_now_epoch"] = None
                    entry["freshness_quote_epoch"] = None
                    entry["freshness_candle_epoch"] = None
                    entry["freshness_threshold_sec"] = None
                    entry["freshness_selected_source"] = None
                    entry["freshness_selected_age_sec"] = None
                    entry["candle_age_sec"] = None
                    entry["quote_validation_status"] = "non_executable"
                    entry["validation_signal_price"] = validation_signal_price
                    entry["validation_reference_price"] = advisory_entry
                    entry["validation_reference_source"] = "tradingsymbol_without_token"
                    entry["pre_validation_entry"] = pre_validation_entry
                    entry["entry_status"] = "non_executable"
                    entry["suggested_entry"] = advisory_entry
                    if _safe_float(entry.get("expected_entry")) is None and advisory_entry is not None:
                        entry["expected_entry"] = advisory_entry
                    entry["entry"] = advisory_entry
                    entry.setdefault("execution_allowed", False)
                    entry["permission"] = "ADVISORY_ONLY"
                    entry["permission_reason"] = entry.get("permission_reason") or "instrument_token_missing"
                    entry["option_ltp_source"] = entry.get("option_ltp_source") or "unknown"
                    entry["quote_source"] = entry.get("quote_source") or entry["option_ltp_source"]
                else:
                    validation = validate_live_entry(
                        signal_price=validation_reference_price,
                        current_ltp=current_ltp,
                        ltp_ts_epoch=ltp_ts_epoch,
                        candle_ts_epoch=_safe_float(
                            entry.get("candle_ts_epoch")
                            or entry.get("last_candle_ts_epoch")
                            or entry.get("signal_candle_epoch")
                        ),
                        mode=mode_for_entry,
                        allow_stale_quotes=allow_stale_quotes_for_entry,
                        market_open=market_open_for_entry,
                        now_epoch=float(time.time()),
                        segment="NSE_FNO",
                        token=token_value,
                        symbol=entry.get("symbol"),
                        trade_id=str(entry.get("advisory_id") or entry.get("trade_id") or entry.get("trade_key") or ""),
                        require_token=True,
                        require_strict_match=False,
                        allow_candle_fallback=True,
                    )
                    entry["current_ltp"] = validation.get("current_ltp")
                    entry["option_ltp_timestamp"] = ltp_ts_epoch
                    entry["price_age_sec"] = validation.get("price_age_sec")
                    entry["freshness_reason"] = validation.get("freshness_reason")
                    entry["freshness_market_open"] = validation.get("freshness_market_open")
                    entry["freshness_now_epoch"] = validation.get("freshness_now_epoch")
                    entry["freshness_quote_epoch"] = validation.get("freshness_quote_epoch")
                    entry["freshness_candle_epoch"] = validation.get("freshness_candle_epoch")
                    entry["freshness_threshold_sec"] = validation.get("freshness_threshold_sec")
                    entry["freshness_selected_source"] = validation.get("freshness_selected_source")
                    entry["freshness_selected_age_sec"] = validation.get("freshness_selected_age_sec")
                    entry["candle_age_sec"] = validation.get("candle_age_sec")
                    entry["quote_validation_status"] = validation.get("entry_status")
                    entry["validation_signal_price"] = validation_signal_price
                    entry["validation_reference_price"] = (
                        _safe_float(validation.get("suggested_entry"))
                        if live_took_over_synthetic
                        else validation_reference_price
                    )
                    entry["validation_reference_source"] = (
                        live_quote_source if live_took_over_synthetic else validation_reference_source
                    )
                    entry["pre_validation_entry"] = pre_validation_entry
                    entry_status_value = validation.get("entry_status")
                    if rest_fallback_used and validation.get("valid"):
                        entry_status_value = "REST_FALLBACK"
                    entry["entry_status"] = entry_status_value
                    entry["suggested_entry"] = validation.get("suggested_entry")
                    if _safe_float(entry.get("expected_entry")) is None:
                        expected_entry = _safe_float(validation.get("suggested_entry"))
                        if expected_entry is None:
                            expected_entry = _safe_float(validation.get("current_ltp"))
                        if expected_entry is not None:
                            entry["expected_entry"] = expected_entry
                    if live_took_over_synthetic and _safe_float(entry.get("expected_entry")) is not None:
                        entry["expected_entry_source"] = live_quote_source
                    if validation.get("valid"):
                        entry["entry"] = validation.get("suggested_entry")
                        entry["option_ltp_source"] = "rest_fallback" if rest_fallback_used else "tick_store"
                        entry["quote_source"] = entry["option_ltp_source"]
                    else:
                        fallback_entry = _safe_float(validation.get("suggested_entry"))
                        if fallback_entry is None:
                            fallback_entry = _safe_float(current_ltp)
                        entry["entry"] = fallback_entry
                        if fallback_entry is None:
                            fallback_entry = _safe_float(current_ltp)
                        entry.setdefault("execution_allowed", False)
                        entry["permission"] = "ADVISORY_ONLY"
                        entry["permission_reason"] = entry.get("permission_reason") or entry_status_value
                        if rest_fallback_used:
                            entry["option_ltp_source"] = "rest_fallback"
                            entry["quote_source"] = "rest_fallback"
            if (
                current_ltp is None
                and token_present
                and not subscription_ok
                and not _allow_rest_fallback_for_mode(explicit_mode_for_fallback)
            ):
                entry["entry"] = None
                entry["entry_status"] = "NO_LIVE_OPTION_FEED"
                entry["option_ltp_source"] = "subscription_failed"
                entry["quote_source"] = "subscription_failed"
                entry["subscription_failed"] = True
                entry = _apply_permission_state(
                    entry,
                    "BLOCK",
                    "NO_LIVE_OPTION_FEED",
                    downgrade_reason="NO_LIVE_OPTION_FEED",
                )
                entry["execution_allowed"] = False
                entry["final_action"] = "BLOCK"
            if not entry.get("option_ltp_source"):
                entry["option_ltp_source"] = "rest_fallback" if rest_fallback_used else "tick_store"
            if not entry.get("quote_source"):
                entry["quote_source"] = entry.get("option_ltp_source")
            entry["post_validation_entry"] = _safe_float(entry.get("entry"))
            if not entry.get("upstox_instrument_key"):
                try:
                    entry["upstox_instrument_key"] = resolve_upstox_key(entry)
                except Exception:
                    entry["upstox_instrument_key"] = None
            try:
                entry_val = float(entry.get("entry") or 0.0)
                target_val = float(entry.get("target") or 0.0)
                stop_val = float(entry.get("stop") or 0.0)
                if entry_val > 0 and target_val > 0:
                    entry["target_premium"] = round(abs(target_val - entry_val), 2)
                if entry_val > 0 and stop_val > 0:
                    entry["stop_premium"] = round(abs(entry_val - stop_val), 2)
            except Exception:
                pass
    return _canonicalize_entry_lifecycle(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
        align_for_schema=False,
    )


def _finalize_review_queue_entry(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> dict:
    perm = {}
    try:
        entry.pop("permission_downgraded_from", None)
        entry.pop("permission_downgrade_reason", None)
        raw_conf = entry.get("raw_signal_confidence")
        if raw_conf is None:
            raw_conf = entry.get("confidence")
        regime = entry.get("regime") or "UNKNOWN"
        regime_conf = entry.get("regime_confidence")
        if regime_conf is None:
            regime_conf = entry.get("day_confidence")
        orb_bias = entry.get("orb_bias")
        if not orb_bias and isinstance(entry.get("source_flags"), dict):
            orb_bias = entry.get("source_flags", {}).get("orb_bias")
        option_type = entry.get("option_type") or entry.get("type")
        side = entry.get("side")
        last_candle = entry.get("last_candle")
        atr_ratio = entry.get("atr_ratio") or entry.get("atr_pct")
        perm = build_permission_payload(
            signal_score=raw_conf,
            regime=regime,
            regime_conf=regime_conf,
            orb_bias=orb_bias,
            option_type=option_type,
            side=side,
            execution_mode=mode_for_entry,
            last_candle=last_candle if isinstance(last_candle, dict) else None,
            atr_ratio=atr_ratio,
        )
        entry["direction"] = perm.get("direction")
        entry["global_confidence"] = perm.get("global_confidence")
        entry["permission"] = perm.get("permission")
        entry["permission_reason"] = perm.get("permission_reason")
        entry["permission_base"] = str(entry.get("permission") or "").strip().upper()
        entry["permission_reason_base"] = str(entry.get("permission_reason") or "")
        entry["countertrend"] = perm.get("countertrend")
        entry["raw_signal_confidence"] = raw_conf
        entry["threshold_display"] = _safe_float(perm.get("threshold_display"))
        entry["threshold_advisory"] = _safe_float(perm.get("threshold_advisory"))
        entry["threshold_execution"] = _safe_float(perm.get("threshold_execution"))
        entry["confidence_vs_threshold_reason"] = str(
            perm.get("confidence_vs_threshold_reason") or ""
        )
        if perm.get("global_confidence") is not None:
            entry["confidence"] = perm.get("global_confidence")
        if perm.get("regime_confidence") is not None:
            entry["regime_confidence"] = perm.get("regime_confidence")
        _log_low_global_conf_once_per_symbol_minute(
            symbol=entry.get("symbol"),
            raw_conf=raw_conf,
            regime_conf=entry.get("regime_confidence"),
            orb_bias=(perm.get("orb_bias") if isinstance(perm, dict) else entry.get("orb_bias")),
            orb_factor=(perm.get("orb_factor") if isinstance(perm, dict) else None),
            reg_penalty=(perm.get("regime_penalty") if isinstance(perm, dict) else None),
            global_conf=entry.get("global_confidence"),
        )
        entry_status = str(entry.get("entry_status") or "")
        if _is_entry_status_blocking(entry_status):
            entry = _apply_permission_state(
                entry,
                "ADVISORY_ONLY",
                entry_status,
                downgrade_reason=entry_status,
            )
        if bool(entry.get("subscription_failed")) and entry_status == "NO_LIVE_OPTION_FEED":
            entry = _apply_permission_state(
                entry,
                "BLOCK",
                "NO_LIVE_OPTION_FEED",
                downgrade_reason="NO_LIVE_OPTION_FEED",
            )
            entry["execution_allowed"] = False
    except Exception as exc:
        logger.warning("permission_compute_failed: %s", exc)
        entry["permission_reason"] = f"permission_compute_failed:{type(exc).__name__}"
    entry_status = str(entry.get("entry_status") or "")
    entry_block_reason = entry_status if _is_entry_status_blocking(entry_status) else None
    permission = str(entry.get("permission") or "ADVISORY_ONLY").upper()
    permission_reason = str(entry.get("permission_reason") or "")
    global_conf = _safe_float(entry.get("global_confidence"))
    gate_snapshot = {
        "freshness": {
            "max_tick_age_sec": _safe_float(entry.get("price_age_sec")),
            "sla_threshold_sec": _safe_float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0)),
        },
        "feed_state": (
            entry.get("feed_state")
            or (entry.get("feed_health_snapshot") or {}).get("state")
            or "UNKNOWN"
        ),
    }
    gate_candidate = {
        "current_ltp": _safe_float(entry.get("current_ltp") or entry.get("live_ltp") or entry.get("entry")),
        "option_age_sec": _safe_float(
            entry.get("option_age_sec")
            or entry.get("price_age_sec")
            or entry.get("option_ltp_age_sec")
        ),
        "spread_pct": _quote_spread_pct(entry),
        "volume": _first_present_float(entry, ("volume", "current_volume", "tick_volume")),
        "best_bid": _safe_float(entry.get("best_bid") or entry.get("bid") or entry.get("opt_bid")),
        "best_ask": _safe_float(entry.get("best_ask") or entry.get("ask") or entry.get("opt_ask")),
        "feed_state": gate_snapshot["feed_state"],
        "global_confidence": _safe_float(entry.get("global_confidence")),
        "confidence": _safe_float(entry.get("confidence")),
        "raw_signal_confidence": _safe_float(entry.get("raw_signal_confidence")),
    }
    gate_eval = gate_decision(gate_candidate, gate_snapshot)
    entry["gating"] = gate_eval
    if not bool(gate_eval.get("hard_pass")):
        hard_reason = (
            (gate_eval.get("hard_reasons") or [None])[0]
            or "HARD_GATE_FAILED"
        )
        entry_block_reason = entry_block_reason or hard_reason
        permission = (
            "BLOCK"
            if bool(entry.get("subscription_failed")) and entry_status == "NO_LIVE_OPTION_FEED"
            else "ADVISORY_ONLY"
        )
        permission_reason = hard_reason
        entry = _apply_permission_state(
            entry,
            permission,
            permission_reason,
            downgrade_reason=hard_reason,
        )
        entry.setdefault("execution_allowed", False)
        entry["entry_status"] = entry_status or hard_reason
        entry_status = str(entry.get("entry_status") or "")

    threshold_execution = _safe_float(entry.get("threshold_execution"))
    if threshold_execution is None:
        threshold_execution = float(resolve_confidence_thresholds(mode_for_entry)["execution"])
    final_conf_threshold = float(
        getattr(cfg, "GATING_FINAL_CONFIDENCE_MIN", threshold_execution)
    )
    entry["confidence_raw_gate_threshold"] = _safe_float(entry.get("confidence_raw_gate_threshold"))
    entry["confidence_final_gate_threshold"] = final_conf_threshold
    gate_final_conf = _safe_float(gate_eval.get("final_confidence"))
    if gate_final_conf is not None:
        entry["global_confidence"] = gate_final_conf
        entry["confidence"] = gate_final_conf
        global_conf = gate_final_conf
    soft_conf_reject = bool(
        bool(gate_eval.get("hard_pass"))
        and permission == "EXECUTE"
        and entry_block_reason is None
        and gate_final_conf is not None
        and gate_final_conf < final_conf_threshold
    )
    if soft_conf_reject:
        permission = "ADVISORY_ONLY"
        permission_reason = "SOFT_CONFIDENCE_BELOW_THRESHOLD"
        entry = _apply_permission_state(
            entry,
            permission,
            permission_reason,
            downgrade_reason=permission_reason,
        )
        entry.setdefault("execution_allowed", False)
    if bool(entry.get("unresolved_contract")):
        entry = _apply_unresolved_contract_state(entry)
    else:
        entry = _apply_manual_approval_state(entry, now_epoch=time.time())
    entry = _refresh_lifecycle_blockers(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        current_ltp=_safe_float(entry.get("current_ltp")),
        validation_reference_price=_safe_float(entry.get("validation_reference_price")),
    )
    entry = _apply_issue_classification(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
    )
    entry = _apply_confidence_threshold_fields(
        entry,
        confidence_value=_safe_float(entry.get("confidence_final")),
        execution_mode=mode_for_entry,
        hard_blockers=list(entry.get("hard_blockers") or []),
        entry_block_reason=entry_block_reason,
    )
    entry = finalize_trade_decision(
        entry,
        gate_decision_payload=gate_eval,
        permission_payload=perm,
        entry_block_reason=entry_block_reason,
    )
    entry["confidence_final_gate_threshold"] = final_conf_threshold
    entry["confidence_rejection_stage"] = _derive_confidence_rejection_stage(entry)
    global_conf = _safe_float(entry.get("confidence_final"))
    permission = str(entry.get("permission") or permission or "ADVISORY_ONLY").upper()
    permission_reason = str(entry.get("permission_reason") or permission_reason or "")
    entry["status_raw"] = str(entry.get("status_raw") or entry.get("status") or "PLANNING").strip().upper() or "PLANNING"
    entry["status"] = _derive_review_status(entry, fallback_status=entry["status_raw"])
    high_execute_threshold = float(
        getattr(
            cfg,
            "HIGH_EXECUTE_MIN_CONF",
            _safe_float(entry.get("threshold_execution")) or 0.30,
        )
    )
    high_execute_eligible = bool(
        permission == "EXECUTE"
        and entry_block_reason is None
        and global_conf is not None
        and global_conf >= high_execute_threshold
    )
    high_execute_blockers: list[str] = []
    if global_conf is None or global_conf < high_execute_threshold:
        high_execute_blockers.append("global_conf_below_high_execute")
    if permission != "EXECUTE":
        high_execute_blockers.append(f"permission_{permission}")
    if entry_block_reason:
        high_execute_blockers.append(f"entry_{entry_block_reason}")
    if soft_conf_reject:
        high_execute_blockers.append("soft_confidence_below_threshold")
    decision_trace = {
        "signal_score": _safe_float(perm.get("signal_score") if isinstance(perm, dict) else entry.get("raw_signal_confidence")),
        "regime_conf": _safe_float(entry.get("regime_confidence")),
        "orb_bias": (perm.get("orb_bias") if isinstance(perm, dict) else None) or entry.get("orb_bias"),
        "orb_factor": _safe_float(perm.get("orb_factor") if isinstance(perm, dict) else None),
        "reg_penalty": _safe_float(perm.get("regime_penalty") if isinstance(perm, dict) else None),
        "global_conf": global_conf,
        "permission": permission,
        "permission_reason": permission_reason,
        "permission_base": entry.get("permission_base"),
        "permission_reason_base": entry.get("permission_reason_base"),
        "permission_downgraded_from": entry.get("permission_downgraded_from"),
        "permission_downgrade_reason": entry.get("permission_downgrade_reason"),
        "entry_status": entry_status or None,
        "entry_block_reason": entry_block_reason,
        "hard_pass": bool(gate_eval.get("hard_pass")),
        "hard_gate_reasons": list(gate_eval.get("hard_reasons") or []),
        "soft_gate_reasons": list(gate_eval.get("soft_reasons") or []),
        "soft_score_adjustment": _safe_float(gate_eval.get("soft_score_adjustment")),
        "final_confidence_after_soft_gates": gate_final_conf,
        "final_confidence_min_threshold": final_conf_threshold,
        "threshold_display": _safe_float(entry.get("threshold_display")),
        "threshold_advisory": _safe_float(entry.get("threshold_advisory")),
        "threshold_execution": _safe_float(entry.get("threshold_execution")),
        "confidence_model_raw": _safe_float(entry.get("confidence_model_raw")),
        "confidence_model_component": _safe_float(entry.get("confidence_model_component")),
        "confidence_micro_component": _safe_float(entry.get("confidence_micro_component")),
        "confidence_micro_blend_method": entry.get("confidence_micro_blend_method"),
        "confidence_after_micro": _safe_float(entry.get("confidence_after_micro")),
        "confidence_after_alpha": _safe_float(entry.get("confidence_after_alpha")),
        "confidence_after_latency": _safe_float(entry.get("confidence_after_latency")),
        "confidence_before_soft_veto": _safe_float(entry.get("confidence_before_soft_veto")),
        "confidence_after_soft_veto": _safe_float(entry.get("confidence_after_soft_veto")),
        "confidence_penalty_soft_veto_total": _safe_float(entry.get("confidence_penalty_soft_veto_total")),
        "confidence_penalty_soft_veto_reasons": list(entry.get("confidence_penalty_soft_veto_reasons") or []),
        "confidence_gate_threshold": _safe_float(entry.get("confidence_gate_threshold")),
        "confidence_raw_gate_threshold": _safe_float(entry.get("confidence_raw_gate_threshold")),
        "confidence_final_gate_threshold": _safe_float(entry.get("confidence_final_gate_threshold")),
        "confidence_rejection_stage": entry.get("confidence_rejection_stage"),
        "confidence_vs_threshold_reason": entry.get("confidence_vs_threshold_reason"),
        "high_execute_threshold": high_execute_threshold,
        "high_execute_eligible": high_execute_eligible,
        "high_execute_blockers": high_execute_blockers,
        "strategy_qualified": bool(permission in {"EXECUTE", "QUEUE", "HIGH_EXECUTE"}),
        "gating_reason": entry_block_reason or permission_reason or None,
        "final_blocker": (
            entry.get("final_blocker")
            or entry_block_reason
            or permission_reason
            or None
        ),
        "feed_state": (
            entry.get("feed_state")
            or (entry.get("feed_health_snapshot") or {}).get("state")
            or None
        ),
        "quote_age_sec": _safe_float(entry.get("quote_age_sec")),
        "option_age_sec": _safe_float(
            entry.get("option_age_sec")
            or entry.get("price_age_sec")
            or entry.get("option_ltp_age_sec")
        ),
        "final_action": entry.get("final_action"),
    }
    entry["decision_trace"] = decision_trace
    _log_confidence_rejection(entry)
    if (
        str(entry.get("instrument") or entry.get("instrument_type") or "").strip().upper() == "OPT"
        and str(entry.get("permission") or "").strip().upper() == "BLOCK"
        and str(entry.get("entry_status") or "").strip().upper() in {"NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN"}
        and _safe_float(entry.get("current_ltp")) is None
        and not str(entry.get("option_ltp_source") or "").strip()
    ):
        entry["option_ltp_source"] = "subscription_failed"
        if not str(entry.get("quote_source") or "").strip():
            entry["quote_source"] = "subscription_failed"
    entry = enforce_entry_contract(entry, stage="review_queue.add_to_queue")
    entry = _enforce_executable_entry_integrity(entry)
    _log_entry_lifecycle_resolution(entry)
    source_flags = entry.get("source_flags")
    if isinstance(source_flags, dict):
        merged_flags = dict(source_flags)
        merged_flags["decision_trace"] = decision_trace
        entry["source_flags"] = merged_flags
    return entry


def _validate_review_queue_advisory_row(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> None:
    try:
        serialize_advisory_row(
            _canonicalize_entry_lifecycle(
                entry,
                mode_for_entry=mode_for_entry,
                allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
                market_open_for_entry=market_open_for_entry,
                align_for_schema=True,
            ),
            allow_legacy=True,
        )
    except AdvisorySchemaError as exc:
        log_advisory_schema_error("review_queue.add_to_queue", entry, exc)
        logger.warning("advisory_queue_schema_error trade_id=%s error=%s", entry.get("trade_id"), exc)


def _write_review_queue_artifacts(path: Path, data: list[dict], entry: dict) -> None:
    entry["trade_key"] = compute_trade_key(
        entry.get("symbol"),
        entry.get("expiry_date") or entry.get("expiry"),
        entry.get("strike"),
        entry.get("option_type") or entry.get("type"),
        entry.get("side"),
        entry.get("strategy_id") or entry.get("strategy"),
    )
    data = _merge_trade_entry(data, entry)
    write_queue_rows(path, data)
    emission_result = _emit_review_queue_logs(entry)
    _update_suggestions_status_latest(entry, emission_result=emission_result)


def add_to_queue(trade, queue_path=None, extra=None):
    try:
        from config import config as cfg
        instr = getattr(trade, "instrument", None)
        if instr is None and isinstance(trade, dict):
            instr = trade.get("instrument")
        if instr == "EQ" and not getattr(cfg, "ENABLE_EQUITIES", True):
            return
    except Exception:
        pass
    path = queue_path or QUEUE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_queue_rows(path)
    entry, mode_for_entry, allow_stale_quotes_for_entry, market_open_for_entry = _build_review_queue_entry(
        trade,
        extra=extra,
        default_mode="ADVISORY",
    )
    entry = _apply_quote_and_entry_logic(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    entry = _finalize_review_queue_entry(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    _validate_review_queue_advisory_row(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    _write_review_queue_artifacts(path, data, entry)

def is_approved(trade_id, payload_hash=None):
    ok, _reason = approval_status(trade_id, payload_hash=payload_hash)
    return ok


def approve(trade_id, payload_hash=None, ttl_sec=None, approver=None):
    trade_id = str(trade_id)
    store = _load_approvals()
    approvals = store.setdefault("approvals", {})
    now_epoch = time.time()
    if ttl_sec is None:
        ttl_sec = _cfg_int("APPROVAL_TTL_SEC", 600)
    expires_epoch = now_epoch + max(int(ttl_sec), 0)
    approvals[trade_id] = {
        "status": "APPROVED",
        "payload_hash": payload_hash,
        "approved_epoch": now_epoch,
        "expires_epoch": expires_epoch,
        "approved_by": approver,
    }
    _write_json(APPROVED_PATH, store)


def get_queue_entry(trade_id, queue_paths=None):
    queue_paths = queue_paths or [QUEUE_PATH, QUICK_QUEUE_PATH, ZERO_HERO_QUEUE_PATH, SCALP_QUEUE_PATH, TARGET_POINTS_QUEUE_PATH]
    for path in queue_paths:
        rows = load_queue_rows(path)
        for row in rows:
            if isinstance(row, dict) and str(row.get("trade_id")) == str(trade_id):
                return row
    return None

def remove_from_queue(trade_id):
    if not QUEUE_PATH.exists():
        return
    data = load_queue_rows(QUEUE_PATH)
    data = [d for d in data if d.get("trade_id") != trade_id]
    write_queue_rows(QUEUE_PATH, data)
