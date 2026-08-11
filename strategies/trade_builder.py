from core.paths import logs_dir, data_root
# Migration note:
# Trade builder now consumes central market context for LIVE/OFFHOURS/SIM gating.
# Zero-to-hero (lotto) ideas are PAPER-only with explicit OTM + premium-band filters.

from datetime import datetime, date, timezone
from dataclasses import asdict, replace
from functools import wraps
from pathlib import Path
import hashlib
import json
import logging
import inspect
import os
import sys
import pandas as pd
from config import config as cfg
from config.profile import get_runtime_profile, get_option_filter_profile
from core.execution_engine import ExecutionEngine
from core.alpha_ensemble import AlphaEnsemble
from core.decision_trace import build_trade_decision_trace
from core.decision_telemetry import build_scan_summary, emit_scan_summary
from core.decision_authority import apply_stage_authority
from core.reject_shadow import record_candidate_decision
from core.trade_schema import Trade, build_instrument_id, validate_trade_identity
from typing import Optional
from strategies.ensemble import (
    ensemble_signal,
    equity_signal,
    futures_signal,
    micro_pattern_signal,
)


def mean_reversion_signal(*_args, **_kwargs):
    """Legacy TradeBuilder hook disabled after structural ensemble repair.

    The canonical mean-reversion implementation is no longer synthesized by
    strategies.ensemble.  Retain this local hook only so legacy routing/tests
    can monkeypatch it explicitly; production behavior fails closed.
    """
    return None


def event_breakout_signal(*_args, **_kwargs):
    """Legacy TradeBuilder hook disabled after structural ensemble repair.

    The canonical event implementation is no longer synthesized by
    strategies.ensemble.  Retain this local hook only so legacy routing/tests
    can monkeypatch it explicitly; production behavior fails closed.
    """
    return None
from core.feature_builder import (
    assess_trade_feature_quality,
    build_trade_features,
    validate_trade_features,
)
from core.advisory_row_integrity import BLOCKED_DEBUG_ROW_KIND
from core.trade_scoring import compute_final_score, compute_trade_score
from core.trade_identity import infer_candidate_identity
from core.strategy_tracker import StrategyTracker
from core.strategy_lifecycle import StrategyLifecycle
from core.instruments import select_expiry as select_registry_expiry
from core.market_context import classify_session_mode, classify_strategy_regime_mode, derive_market_context, derive_regime_context
from core.candidate_soft_reject import build_soft_reject_candidate, critical_reject_reasons, is_critical_reject_reason
from core.candidate_finalization import mirror_candidate_truth, stamp_lifecycle_stage, assert_ranked_candidate_ready
from core.incidents import SEV2, create_incident
from core.reject_logger import append_reject_reasons
from core.reject_telemetry import append_reject_telemetry
from core.entry_semantics import EntryContractViolation, build_entry_state, should_allow_last_execution_fallback
from core.quote_truth import resolve_quote_validation_status
from core.execution_entry_trace import append_execution_entry_trace
from core.issue_policy import ISSUE_CATEGORY_HARD, ISSUE_CATEGORY_SOFT, ISSUE_CATEGORY_WARNING
from core.opportunity_engine import annotate_ranked_opportunities, select_best_opportunity
from core.risk_engine import evaluate_candidate_risk
from core.observability.pipeline import append_trade_lifecycle_event
from core.option_entry import get_option_ltp_sla_sec
from core.option_liquidity_cache import hydrate_option_liquidity_fields
from core.threshold_audit import (
    build_candidate_decision_record as build_audit_candidate_decision_record,
    classify_rejection_metadata,
    record_candidate_decision as record_threshold_candidate_decision,
)
from core.heartbeat_status import derive_cycle_semantics, top_blockers_from_counts
from core.time_utils import compute_age_sec, is_market_open_ist, now_ist, now_utc_epoch
from core.regime import RegimeClassifier, normalize_regime
from ml.continuous_regime import extract_continuous_regime, calculate_dynamic_multiplier
from core.execution.alpha_decay import monitor_alpha_decay, AlphaDecayState
from core.kite_client import kite_client
from core.events import write_json_atomic
import time as _time
import time


logger = logging.getLogger(__name__)

_AUTO_TUNE_CACHE = {"ts": 0, "data": {}}


def _normalize_family_context_key(strategy_family: str | None) -> str:
    normalized = str(strategy_family or "").strip().lower().replace("_", "-")
    aliases = {
        "meanreversion": "mean-reversion",
        "mean_reversion": "mean-reversion",
        "rangewatchlist": "range-watchlist",
        "range_watchlist": "range-watchlist",
    }
    return aliases.get(normalized, normalized)


def _family_allowed_in_context(
    strategy_family: str | None,
    regime_mode: str | None,
    session_mode: str | None,
) -> bool:
    del session_mode
    regime_mode_normalized = str(regime_mode or "").strip().upper()
    allowed = {
        "breakout": {"TRENDING", "EXPANSION", "LOW_VOL", "UNCERTAIN"},
        "continuation": {"TRENDING", "EXPANSION", "LOW_VOL", "UNCERTAIN"},
        "pullback": {"TRENDING", "LOW_VOL", "UNCERTAIN"},
        "mean-reversion": {"SIDEWAYS", "LOW_VOL", "UNCERTAIN"},
        "range-watchlist": {"SIDEWAYS", "LOW_VOL", "UNCERTAIN"},
    }
    family_key = _normalize_family_context_key(strategy_family)
    allowed_regimes = allowed.get(family_key, {"UNCERTAIN"})
    return regime_mode_normalized in allowed_regimes


def _env_debug_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _debug_option_chain_enabled() -> bool:
    return _env_debug_enabled("TRADEBOT_DEBUG_OPTION_CHAIN")


def _debug_freshness_enabled() -> bool:
    return _env_debug_enabled("TRADEBOT_DEBUG_FRESHNESS")


def _debug_advisory_enabled() -> bool:
    return _env_debug_enabled("TRADEBOT_DEBUG_ADVISORY")


def _log_option_chain_debug(message: str, *args) -> None:
    if _debug_option_chain_enabled():
        logger.debug(message, *args)


def _log_freshness_debug(message: str, *args) -> None:
    if _debug_freshness_enabled():
        logger.debug(message, *args)


def _log_advisory_debug(message: str, *args) -> None:
    if _debug_advisory_enabled():
        logger.debug(message, *args)

def _get_auto_tune():
    try:
        now = _time.time()
        if now - _AUTO_TUNE_CACHE.get("ts", 0) < 60:
            return _AUTO_TUNE_CACHE.get("data") or {}
        path = logs_dir() / "auto_tune.json"
        if not path.exists():
            _AUTO_TUNE_CACHE.update({"ts": now, "data": {}})
            return {}
        data = json.loads(path.read_text())
        _AUTO_TUNE_CACHE.update({"ts": now, "data": data})
        return data
    except Exception:
        return {}


class _NoopPredictor:
    def predict_confidence(self, *_args, **_kwargs):
        return 0.5

def _log_signal_event(kind, symbol, payload=None):
    try:
        path = logs_dir() / "signal_path.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        obj = {"timestamp": datetime.now().isoformat(), "kind": kind, "symbol": symbol}
        if payload:
            obj.update(payload)
        with path.open("a") as f:
            f.write(json.dumps(obj) + "\n")
    except Exception:
        pass


def _scan_summary_mode_from_market_data(market_data: dict | None) -> str:
    data = dict(market_data or {})
    market_context = data.get("market_context")
    market_open = bool((market_context or {}).get("market_open", data.get("market_open", True))) if isinstance(market_context, dict) else bool(data.get("market_open", True))
    if not market_open:
        return "OFFHOURS"
    if isinstance(market_context, dict):
        mode = str(market_context.get("mode") or "").strip().upper()
        if mode:
            return mode
    exec_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
    segment = data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
    ctx_payload = dict(market_context or {}) if isinstance(market_context, dict) else {}
    if "execution_mode" not in ctx_payload:
        ctx_payload["execution_mode"] = exec_mode
    if "market_open" not in ctx_payload:
        ctx_payload["market_open"] = data.get("market_open", True)
    if "segment" not in ctx_payload:
        ctx_payload["segment"] = segment
    return str(derive_market_context(ctx_payload).mode or exec_mode).upper()


def _emit_scan_summary_and_status(self, market_data: dict | None, trade) -> None:
    market_data_dict = dict(market_data or {})
    symbol = str((market_data or {}).get("symbol") or "")
    reject_ctx = dict(self._reject_ctx or {})
    reject_counts = dict(self._scan_reject_counts or {})
    reject_reason = str(reject_ctx.get("reason") or "").strip()
    if trade is None and reject_reason:
        reject_counts[reject_reason] = int(reject_counts.get(reject_reason, 0)) + 1
    accepted = int(self._scan_accepted or (1 if trade is not None else 0))
    summary = build_scan_summary(
        symbol=symbol,
        total_candidates=int(self._scan_total_candidates or 0),
        accepted=accepted,
        rejected_by_reason=reject_counts,
        mode=_scan_summary_mode_from_market_data(market_data_dict),
        profile_name=str(self._scan_profile_name or ""),
    )
    market_context = market_data_dict.get("market_context")
    if isinstance(market_context, dict):
        market_open = bool(market_context.get("market_open", market_data_dict.get("market_open", True)))
        market_mode = str(
            market_context.get("mode")
            or _scan_summary_mode_from_market_data(market_data_dict)
            or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).strip().upper()
    else:
        market_open = bool(market_data_dict.get("market_open", True))
        market_mode = str(
            _scan_summary_mode_from_market_data(market_data_dict)
            or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).strip().upper()
    summary["market_open"] = bool(market_open)
    summary["market_mode"] = "OFFHOURS" if not market_open else market_mode
    self._last_scan_summary = dict(summary)
    try:
        option_summary = dict(getattr(self, "_last_option_scan_summary", {}) or {})
        if option_summary and not bool(getattr(self, "_option_scan_summary_emitted", False)):
            logger.info(
                "OPTION_SCAN_REJECT_SUMMARY symbol=%s considered=%s survivors=%s option_reject_total=%s top_rejects=%s",
                option_summary.get("symbol", symbol),
                option_summary.get("considered"),
                option_summary.get("survivors"),
                option_summary.get("option_reject_total"),
                option_summary.get("top_rejects"),
            )
            try:
                considered = int(option_summary.get("considered") or 0)
                survivors = int(option_summary.get("survivors") or 0)
                top_rejects = option_summary.get("top_rejects")
                if survivors <= 0 and considered > 0:
                    logger.info(
                        "NO_CANDIDATE_PATH symbol=%s considered=%s survivors=%s top_rejects=%s",
                        option_summary.get("symbol", symbol),
                        considered,
                        survivors,
                        top_rejects,
                    )
            except Exception:
                pass
            self._option_scan_summary_emitted = True
    except Exception as exc:
        logger.warning("option_scan_summary_emit_failed err=%s:%s", type(exc).__name__, exc)
    emit_scan_summary(summary)
    self._write_scan_status_files(summary)


def _coerce_status_bool(value, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _wrap_trade_builder_build_with_status(build_fn):
    if getattr(build_fn, "_scan_status_wrapped", False):
        return build_fn

    @wraps(build_fn)
    def _wrapped(self, market_data, *args, **kwargs):
        trade = None
        try:
            trade = build_fn(self, market_data, *args, **kwargs)
            return trade
        finally:
            try:
                _emit_scan_summary_and_status(self, market_data, trade)
            except Exception as exc:
                logger.warning("scan_status_write_failed err=%s:%s", type(exc).__name__, exc)

    _wrapped._scan_status_wrapped = True
    return _wrapped

class TradeBuilder:
    def __init__(self, predictor=None, execution=None, strategy_tracker=None):
        self._ml_disabled = (
            os.getenv("DISABLE_ML", "false").lower() == "true"
            or bool(os.getenv("PYTEST_CURRENT_TEST"))
            or ("pytest" in sys.modules)
        )
        self._noop_predictor = _NoopPredictor()
        if predictor is not None:
            self.predictor = predictor
        elif self._ml_disabled:
            self.predictor = self._noop_predictor
        else:
            from ml.trade_predictor import TradePredictor
            self.predictor = TradePredictor()
        self.deep_predictor: Optional[object] = None
        self.micro_predictor: Optional[object] = None
        self.execution = execution or ExecutionEngine()
        self.alpha_ensemble = AlphaEnsemble() if getattr(cfg, "ALPHA_ENSEMBLE_ENABLE", True) else None
        self.strategy_tracker = strategy_tracker or StrategyTracker()
        self.lifecycle = StrategyLifecycle()
        self.regime_classifier = RegimeClassifier()
        self._ml_history_cache = {"ts": 0, "count": 0}
        self._expiry_zero_hero_count = 0
        self._expiry_zero_hero_by_symbol = {}
        self._expiry_zero_hero_loss_streak = {}
        self._expiry_zero_hero_disabled_until = {}
        self._expiry_zero_hero_pnl = {}
        self._expiry_lotto_token_incident_ts = {}
        self._zero_to_hero_daily_count = 0
        self._zero_to_hero_last_day = None
        self._reject_ctx = {}
        self._scan_reject_counts = {}
        self._scan_total_candidates = 0
        self._scan_accepted = 0
        self._scan_profile_name = ""
        self._last_scan_summary = {}
        self._last_ranked_candidates = []
        self._soft_reject_reasons_cache: set[str] | None = None
        self._feed_runtime_cache_ts = 0.0
        self._feed_runtime_cache_payload: dict = {}

    def _soft_reject_reasons(self) -> set[str]:
        if self._soft_reject_reasons_cache is not None:
            return self._soft_reject_reasons_cache
        raw = str(getattr(cfg, "TRADE_BUILDER_SOFT_REJECT_REASONS", "") or "")
        reasons = {item.strip().lower() for item in raw.split(",") if item.strip()}
        self._soft_reject_reasons_cache = reasons
        return reasons

    def _hard_reject_reasons(self) -> set[str]:
        raw = str(
            getattr(
                cfg,
                "TRADE_BUILDER_HARD_REJECT_REASONS",
                "feed_stale,quote_missing,unresolved_contract,invalid_risk_levels,missing_live_quote,no_live_option_feed",
            )
            or ""
        )
        return {item.strip().lower() for item in raw.split(",") if item.strip()}

    def _soft_scan_gate_reasons(self) -> set[str]:
        raw = str(
            getattr(
                cfg,
                "OPTION_SCAN_SOFT_GATE_REASONS",
                "type_mismatch,iv_skew_curvature,iv_bounds",
            )
            or ""
        )
        return {item.strip().lower() for item in raw.split(",") if item.strip()}

    def _is_scan_reason_hard_gate(self, reason: str | None) -> bool:
        code = str(reason or "").strip().lower()
        if not code:
            return False
        if code == "type_mismatch":
            return bool(getattr(cfg, "OPTION_TYPE_MISMATCH_HARD_REJECT", False))
        if code == "iv_bounds":
            return bool(getattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", False))
        if code == "iv_skew_curvature":
            return bool(getattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", False))
        if code in {"iv_skew_curve_call", "iv_skew_curve_put"}:
            return bool(getattr(cfg, "OPTION_IV_SKEW_CURVE_HARD_REJECT", False))
        if code in {"stale_option_tick", "stale_option_quote", "no_volume", "invalid_option_ltp"}:
            return True
        hard_reasons = self._hard_reject_reasons()
        if code in hard_reasons:
            return True
        return code.startswith("hard_")

    def _classify_reject_reason(self, reason: str | None) -> str:
        text = str(reason or "").strip().lower()
        if not text:
            return "soft"
        hard_reasons = self._hard_reject_reasons()
        if text in hard_reasons:
            return "hard"
        soft_reasons = self._soft_reject_reasons()
        if text in soft_reasons:
            return "soft"
        return "soft"

    def _borderline_confidence_floor(self) -> float:
        return float(getattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18) or 0.18)

    def _build_borderline_candidate(
        self,
        *,
        market_data: dict,
        reason: str,
        confidence: float,
        strategy_tag: str | None = None,
        direction: str | None = None,
    ):
        if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
            return None
        symbol = str(
            market_data.get("symbol")
            or market_data.get("underlying")
            or "UNKNOWN"
        ).strip().upper() or "UNKNOWN"
        execution_mode = str(
            market_data.get("execution_mode")
            or ((market_data.get("market_context") or {}).get("execution_mode") if isinstance(market_data.get("market_context"), dict) else "")
            or getattr(cfg, "EXECUTION_MODE", "")
        ).strip().upper()
        confidence_value = max(float(confidence or 0.0), float(self._borderline_confidence_floor()))
        weak_reason = str(reason or "").strip().lower() in {"weak_signal", "no_signal"}
        base_candidate = {
            "symbol": symbol,
            "strategy": strategy_tag or "BORDERLINE_SIGNAL",
            "strategy_name": strategy_tag or "BORDERLINE_SIGNAL",
            "strategy_family": str(strategy_tag or "builder_soft_reject").strip().lower() or "builder_soft_reject",
            "candidate_type": "directional",
            "direction": direction or ("BUY_CALL" if float(market_data.get("ltp") or 0.0) >= float(market_data.get("vwap") or market_data.get("ltp") or 0.0) else "BUY_PUT"),
            "confidence": confidence_value,
            "confidence_final": confidence_value,
            "rank_score": None if weak_reason else confidence_value,
            "final_score": None if weak_reason else confidence_value,
        }
        candidate = build_soft_reject_candidate(
            market_data,
            reject_reason=reason,
            reject_source="trade_builder_borderline",
            gate_reasons=[reason],
            base_candidate=base_candidate,
            execution_mode=execution_mode,
        )
        if not candidate:
            return None
        candidate["candidate_origin"] = "softened_builder_path"
        candidate["source_flags"] = dict(candidate.get("source_flags") or {})
        candidate["source_flags"]["candidate_origin"] = "softened_builder_path"
        candidate["source_flags"]["soft_reject_reason"] = str(reason)
        if weak_reason:
            candidate["execution_status"] = "advisory_only"
            candidate["candidate_status"] = "advisory_only"
            candidate["eligible_for_execution"] = False
            candidate["execution_allowed"] = False
            candidate["execution_ok"] = False
            candidate["execution_blocked"] = True
            candidate["execution_block_reason"] = "weak_signal_builder"
            candidate["permission"] = "ADVISORY_ONLY"
            candidate["final_action"] = "ADVISORY_ONLY"
            candidate["readiness"] = "ADVISORY_ONLY"
            candidate["planning_only"] = True
            candidate["tradable"] = False
        else:
            candidate["execution_status"] = "scored"
            candidate["candidate_status"] = "near_executable"
            candidate["eligible_for_execution"] = True
            candidate["execution_allowed"] = True
            candidate["execution_ok"] = True
            candidate["execution_blocked"] = False
            candidate["execution_block_reason"] = None
            candidate["permission"] = "QUEUE_ONLY"
            candidate["final_action"] = "QUEUE_ONLY"
            candidate["readiness"] = "QUEUE_ONLY"
            candidate["planning_only"] = False
            candidate["tradable"] = True
        candidate["confidence"] = confidence_value
        candidate["confidence_final"] = confidence_value
        candidate["soft_reject_seed_confidence"] = confidence_value
        candidate.setdefault("score_origin", "soft_reject_seed")
        if weak_reason:
            candidate["rank_score"] = None
            candidate["opportunity_score"] = None
            candidate["final_score"] = None
        else:
            candidate["rank_score"] = max(float(candidate.get("rank_score") or 0.0), confidence_value)
            candidate["final_score"] = max(float(candidate.get("final_score") or 0.0), confidence_value)
        candidate["reason"] = str(reason or "weak_signal")
        candidate = self._attach_softened_candidate_contract(candidate, market_data=market_data)
        return candidate

    def _attach_softened_candidate_contract(self, candidate: dict | None, *, market_data: dict | None) -> dict | None:
        if not isinstance(candidate, dict):
            return candidate
        data = dict(market_data or {})
        out = dict(candidate)
        symbol = str(out.get("symbol") or data.get("symbol") or "").strip().upper()
        if not symbol:
            return out
        direction = str(out.get("direction") or "").strip().upper()
        if "PUT" in direction or direction.endswith("PE"):
            opt_type = "PE"
        elif "CALL" in direction or direction.endswith("CE"):
            opt_type = "CE"
        else:
            opt_type = "CE"
        spot = (
            self._coerce_positive_float(data.get("underlying_spot"))
            or self._coerce_positive_float(data.get("ltp"))
            or self._coerce_positive_float(out.get("signal_price"))
        )
        step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}
        step = float(step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50)) or 0.0)
        if spot is None or step <= 0:
            out["unresolved_contract"] = True
            out["execution_blocked"] = True
            out["execution_block_reason"] = "unresolved_contract"
            out["execution_status"] = "advisory_only"
            out["candidate_status"] = "advisory_only"
            out["eligible_for_execution"] = False
            out["execution_allowed"] = False
            out["execution_ok"] = False
            out["permission"] = "ADVISORY_ONLY"
            out["final_action"] = "ADVISORY_ONLY"
            out["readiness"] = "ADVISORY_ONLY"
            return out
        atm_strike = int(round(float(spot) / float(step)) * float(step))
        expiry_resolved = self._resolve_expiry_for_symbol(symbol, data)
        search_steps = max(0, int(getattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_STEPS", 2) or 2))
        strike_candidates: list[int] = [int(atm_strike)]
        for step_idx in range(1, search_steps + 1):
            delta = int(round(float(step) * float(step_idx)))
            strike_candidates.append(int(atm_strike - delta))
            strike_candidates.append(int(atm_strike + delta))
        seen_strikes: set[int] = set()
        deduped_strikes: list[int] = []
        for strike in strike_candidates:
            if strike in seen_strikes:
                continue
            seen_strikes.add(strike)
            deduped_strikes.append(strike)
        resolved_contract: dict | None = None
        requested_expiry = expiry_resolved
        for strike in deduped_strikes:
            contract = self._resolve_option_contract(symbol, strike, opt_type, expiry_resolved, data)
            if contract.get("tradingsymbol") or contract.get("instrument_token") is not None:
                resolved_contract = dict(contract)
                resolved_contract["resolved_strike"] = strike
                break
        if resolved_contract is None:
            available_expiries: list[str] = []
            available_strikes: list[float] = []
            chain = data.get("option_chain")
            if isinstance(chain, (list, tuple)):
                for row in chain:
                    if not isinstance(row, dict):
                        continue
                    row_type = str(row.get("type") or row.get("option_type") or row.get("right") or "").strip().upper()
                    if row_type != opt_type:
                        continue
                    exp_text = self._coerce_date_str(self._option_expiry(row, data))
                    if exp_text:
                        available_expiries.append(exp_text)
                    try:
                        strike_val = float(row.get("strike") or row.get("strike_price") or row.get("strikePrice"))
                    except Exception:
                        strike_val = None
                    if strike_val is not None:
                        available_strikes.append(strike_val)
            print(
                "CONTRACT_RESOLUTION_FAILED",
                {
                    "symbol": symbol,
                    "requested_expiry": requested_expiry,
                    "requested_strike": atm_strike,
                    "option_type": opt_type,
                    "available_expiries": sorted(list(dict.fromkeys(available_expiries)))[:5],
                    "available_strikes_sample": sorted(list(dict.fromkeys(available_strikes)))[:10],
                },
            )
            out["unresolved_contract"] = True
            out["execution_blocked"] = True
            out["execution_block_reason"] = "unresolved_contract"
            out["execution_status"] = "advisory_only"
            out["candidate_status"] = "advisory_only"
            out["eligible_for_execution"] = False
            out["execution_allowed"] = False
            out["execution_ok"] = False
            out["permission"] = "ADVISORY_ONLY"
            out["final_action"] = "ADVISORY_ONLY"
            out["readiness"] = "ADVISORY_ONLY"
            return out
        resolved_expiry = str(resolved_contract.get("expiry") or expiry_resolved or "").strip()
        resolved_strike = resolved_contract.get("resolved_strike")
        try:
            strike_value = int(float(resolved_strike if resolved_strike is not None else atm_strike))
        except Exception:
            strike_value = int(atm_strike)
        instrument_token = resolved_contract.get("instrument_token")
        try:
            instrument_token = int(instrument_token) if instrument_token is not None else None
        except Exception:
            instrument_token = None
        out["instrument"] = "OPT"
        out["instrument_type"] = "OPT"
        out["option_type"] = opt_type
        out["right"] = opt_type
        out["strike"] = strike_value
        out["expiry"] = resolved_expiry
        out["expiry_date"] = resolved_expiry
        out["tradingsymbol"] = resolved_contract.get("tradingsymbol")
        out["instrument_token"] = instrument_token
        out["instrument_id"] = (
            resolved_contract.get("instrument_id")
            or build_instrument_id(symbol, "OPT", resolved_expiry, float(strike_value), opt_type)
        )
        out["unresolved_contract"] = False
        out["execution_blocked"] = False
        out["execution_block_reason"] = None
        return out

    def _soft_reject_enabled(self, execution_mode: str | None) -> bool:
        if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
            return False
        try:
            enabled = bool(getattr(cfg, "TRADE_BUILDER_SOFT_REJECT_ENABLE", True))
        except Exception:
            enabled = False
        if not enabled:
            return False
        try:
            allow_live = bool(getattr(cfg, "TRADE_BUILDER_SOFT_REJECT_ALLOW_LIVE", True))
        except Exception:
            allow_live = True
        mode = str(execution_mode or "").strip().upper()
        if mode in {"LIVE", "REAL"} and not allow_live:
            return False
        return True

    def _select_soft_reject_reason(self, reject_ctx: dict | None) -> str | None:
        if not isinstance(reject_ctx, dict):
            return None
        soft_reasons = self._soft_reject_reasons()
        primary = str(reject_ctx.get("reason") or "").strip().lower()
        gate_reasons = [str(code).strip().lower() for code in (reject_ctx.get("gate_reasons") or []) if str(code).strip()]
        if primary == "no_viable_candidates":
            for code in gate_reasons:
                if code in soft_reasons and code != primary:
                    return code
        if primary and primary in soft_reasons:
            return primary
        for code in gate_reasons:
            if code in soft_reasons:
                return code
        return None

    def _soften_reject_to_candidate(
        self,
        *,
        market_data: dict,
        reject_ctx: dict,
        strategy_tag: str | None = None,
        direction: str | None = None,
    ):
        if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
            return None
        if not isinstance(market_data, dict):
            return None
        execution_mode = str(
            market_data.get("execution_mode")
            or ((market_data.get("market_context") or {}).get("execution_mode") if isinstance(market_data.get("market_context"), dict) else "")
            or getattr(cfg, "EXECUTION_MODE", "")
        ).strip().upper()
        if not self._soft_reject_enabled(execution_mode):
            return None
        reason = self._select_soft_reject_reason(reject_ctx)
        if not reason and execution_mode in {"SIM", "PAPER", "OFFHOURS"}:
            primary_reason = str(reject_ctx.get("reason") or "").strip().lower()
            if primary_reason in {"no_candidates_survived", "no_signal"}:
                reason = primary_reason
        if not reason:
            return None
        if self._classify_reject_reason(reason) == "hard":
            return None
        if execution_mode in {"SIM", "PAPER", "OFFHOURS"} and reason in {"no_candidates_survived", "no_viable_candidates", "no_signal"}:
            ltp = self._coerce_positive_float(market_data.get("ltp")) or 0.0
            vwap = self._coerce_positive_float(market_data.get("vwap")) or ltp
            best_trade = self._rank_nonlive_opportunity_candidates(
                market_data,
                ltp=float(ltp),
                vwap=float(vwap),
                trigger_reason=str(reason),
                scope_suffix=f"opportunity:{reason}",
            )
            if best_trade is not None:
                return best_trade
        if is_critical_reject_reason(reason, critical_reject_reasons()):
            return None
        symbol = str(reject_ctx.get("symbol") or market_data.get("symbol") or market_data.get("underlying") or "").strip()
        gate_reasons = list(reject_ctx.get("gate_reasons") or []) or [reason]
        base_candidate = {
            "symbol": symbol or None,
            "strategy": strategy_tag,
            "strategy_name": strategy_tag,
            "strategy_family": strategy_tag or "unknown",
            "candidate_type": "directional",
            "direction": direction,
        }
        candidate = build_soft_reject_candidate(
            market_data,
            reject_reason=reason,
            reject_source="trade_builder_soft_reject",
            gate_reasons=gate_reasons,
            base_candidate=base_candidate,
            execution_mode=execution_mode,
        )
        if not candidate:
            return None
        trade_id = str(candidate.get("trade_id") or "").strip()
        if trade_id.startswith("softrej_"):
            candidate["trade_id"] = f"tbsoft_{symbol}_{trade_id.rsplit('_', 1)[-1]}"
        candidate["candidate_origin"] = "softened_builder_path"
        candidate["source_flags"] = dict(candidate.get("source_flags") or {})
        candidate["source_flags"]["candidate_origin"] = "softened_builder_path"
        candidate["source_flags"]["soft_reject_reason"] = reason
        if str(candidate.get("candidate_type") or "").strip().lower() in {"", "unknown"}:
            candidate["candidate_type"] = "directional"
        if str(candidate.get("strategy_family") or "").strip().lower() in {"", "unknown"}:
            candidate["strategy_family"] = str(strategy_tag or "builder_soft_reject").strip().lower() or "builder_soft_reject"
        if str(candidate.get("setup_variant") or "").strip().lower() in {"", "unknown"}:
            candidate["setup_variant"] = "softened_builder_path"
        confidence_floor = float(self._borderline_confidence_floor())
        weak_reason = str(reason or "").strip().lower() in {"weak_signal", "no_signal"}
        if weak_reason:
            candidate["execution_status"] = "advisory_only"
            candidate["candidate_status"] = "advisory_only"
            candidate["eligible_for_execution"] = False
            candidate["execution_allowed"] = False
            candidate["execution_ok"] = False
            candidate["execution_blocked"] = True
            candidate["execution_block_reason"] = "weak_signal_builder"
            candidate["permission"] = "ADVISORY_ONLY"
            candidate["final_action"] = "ADVISORY_ONLY"
            candidate["readiness"] = "ADVISORY_ONLY"
            candidate["planning_only"] = True
            candidate["tradable"] = False
        else:
            candidate["execution_status"] = "scored"
            candidate["candidate_status"] = "near_executable"
            candidate["eligible_for_execution"] = True
            candidate["execution_allowed"] = True
            candidate["execution_ok"] = True
            candidate["execution_blocked"] = False
            candidate["execution_block_reason"] = None
            candidate["permission"] = "QUEUE_ONLY"
            candidate["final_action"] = "QUEUE_ONLY"
            candidate["readiness"] = "QUEUE_ONLY"
            candidate["planning_only"] = False
            candidate["tradable"] = True
        candidate["confidence"] = max(float(candidate.get("confidence") or 0.0), confidence_floor)
        candidate["confidence_final"] = max(float(candidate.get("confidence_final") or 0.0), confidence_floor)
        candidate["soft_reject_seed_confidence"] = confidence_floor
        candidate.setdefault("score_origin", "soft_reject_seed")
        if weak_reason:
            candidate["rank_score"] = None
            candidate["opportunity_score"] = None
            candidate["final_score"] = None
        else:
            candidate["rank_score"] = max(float(candidate.get("rank_score") or 0.0), confidence_floor)
            candidate["final_score"] = max(float(candidate.get("final_score") or 0.0), confidence_floor)
        candidate["reason"] = reason
        candidate = self._attach_softened_candidate_contract(candidate, market_data=market_data)
        logger.info(
            "candidate_softened reason=%s symbol=%s strategy=%s",
            reason,
            symbol,
            strategy_tag,
        )
        logger.info(
            "candidate_rank_inputs symbol=%s reason=%s confidence=%s rank_score=%s",
            symbol,
            reason,
            candidate.get("confidence_final"),
            candidate.get("rank_score"),
        )
        try:
            if candidate.get("rank_score") is not None:
                self._set_last_ranked_candidates([candidate])
            else:
                self._set_last_ranked_candidates([])
            self._scan_accepted = 1
            if candidate.get("rank_score") is not None:
                logger.info(
                    "candidate_pool_append source=softened_builder_path symbol=%s reason=%s",
                    symbol,
                    reason,
                )
            else:
                logger.info(
                    "candidate_pool_skip source=softened_builder_path symbol=%s reason=%s rank_score=none",
                    symbol,
                    reason,
                )
        except Exception:
            pass
        return candidate

    def _ensure_reject_reason(self, market_data: dict | None, reason: str | None = None) -> str:
        reject_ctx = dict(self._reject_ctx or {})
        reject_reason = self._resolve_reject_reason(
            reason=reason,
            reject_ctx=reject_ctx,
            fallback="unspecified_trade_builder_reject",
        )
        if not str(reject_reason or "").strip():
            reject_reason = "unspecified_trade_builder_reject"
        if str(reject_reason).strip().lower() == "unspecified_trade_builder_reject":
            derived = self._derive_reject_reason_from_scan_context()
            if derived:
                reject_reason = derived
        if str(reject_reason).strip().lower() == "unspecified_trade_builder_reject":
            reject_ctx = dict(reject_ctx)
            symbol = (market_data or {}).get("symbol") if isinstance(market_data, dict) else None
            if symbol:
                reject_ctx.setdefault("symbol", symbol)
            reject_ctx["reason"] = reject_reason
            self._reject_ctx = reject_ctx
            logger.warning("trade_builder_reject_reason_missing symbol=%s", symbol)
        return str(reject_reason).strip()

    def _resolve_reject_reason(
        self,
        *,
        reason: str | None = None,
        reject_ctx: dict | None = None,
        extra: dict | None = None,
        fallback: str = "unspecified_trade_builder_reject",
    ) -> str:
        generic = "unspecified_trade_builder_reject"
        ctx = dict(reject_ctx or {})
        ext = dict(extra or {})
        fields = (
            reason,
            ctx.get("reason"),
            ctx.get("reject_reason"),
            ext.get("reason"),
            ext.get("reject_reason"),
            ext.get("final_blocker"),
            ext.get("hard_reason"),
            ext.get("permission_reason"),
            ext.get("entry_block_code"),
            ext.get("quote_validation_status"),
            ctx.get("final_blocker"),
            ctx.get("hard_reason"),
            ctx.get("permission_reason"),
            ctx.get("entry_block_code"),
            ctx.get("quote_validation_status"),
        )
        for value in fields:
            text = str(value or "").strip()
            if text and text.lower() != generic:
                return text
        for collection in ("gate_reasons", "hard_blockers", "blockers", "warnings"):
            for item in list(ext.get(collection) or ctx.get(collection) or []):
                text = str(item or "").strip()
                if text and text.lower() != generic:
                    return text
        fallback_reason = str(
            reason
            or ctx.get("reason")
            or ext.get("reason")
            or ext.get("reject_reason")
            or ctx.get("reject_reason")
            or fallback
        ).strip()
        return fallback_reason or fallback

    def _derive_reject_reason_from_scan_context(self) -> str | None:
        try:
            scan_counts = dict(self._scan_reject_counts or {})
        except Exception:
            scan_counts = {}
        filtered: list[tuple[str, int]] = []
        for code, count in scan_counts.items():
            text = str(code or "").strip()
            if not text:
                continue
            if text.lower() == "unspecified_trade_builder_reject":
                continue
            try:
                count_int = int(count)
            except Exception:
                count_int = 0
            filtered.append((text, count_int))
        if filtered:
            filtered.sort(key=lambda item: (-int(item[1]), str(item[0])))
            return str(filtered[0][0]).strip() or None
        try:
            option_summary = dict(getattr(self, "_last_option_scan_summary", {}) or {})
        except Exception:
            option_summary = {}
        top_rejects = dict(option_summary.get("top_rejects") or {})
        if top_rejects:
            ranked = sorted(
                (
                    (str(code or "").strip(), int(count or 0))
                    for code, count in top_rejects.items()
                    if str(code or "").strip()
                    and str(code or "").strip().lower() != "unspecified_trade_builder_reject"
                ),
                key=lambda item: (-int(item[1]), str(item[0])),
            )
            if ranked:
                return str(ranked[0][0]).strip() or None
        return None

    def _reject_exit(self, market_data: dict | None, reason: str | None, extra: dict | None = None) -> None:
        reject_ctx = dict(self._reject_ctx or {})
        reject_reason = self._resolve_reject_reason(
            reason=reason,
            reject_ctx=reject_ctx,
            extra=extra,
            fallback="unspecified_trade_builder_reject",
        )
        if not str(reject_reason or "").strip():
            reject_reason = "unspecified_trade_builder_reject"
        if str(reject_reason).strip().lower() == "unspecified_trade_builder_reject":
            derived = self._derive_reject_reason_from_scan_context()
            if derived:
                reject_reason = derived
        extra_payload = dict(extra or {})
        symbol = str(
            extra_payload.get("symbol")
            or reject_ctx.get("symbol")
            or (market_data or {}).get("symbol")
            or (market_data or {}).get("underlying")
            or "UNKNOWN"
        ).strip()
        if symbol:
            reject_ctx["symbol"] = symbol
        if extra_payload:
            reject_ctx.update(extra_payload)
        if reject_reason in {"no_candidates_survived", "no_viable_candidates"}:
            option_summary = dict(getattr(self, "_last_option_scan_summary", {}) or {})
            considered = int(option_summary.get("considered") or extra_payload.get("option_rows_considered") or 0)
            survivors = int(option_summary.get("survivors") or extra_payload.get("survivor_count") or 0)
            reject_counts = {
                str(code): int(count)
                for code, count in sorted(
                    (self._scan_reject_counts or {}).items(),
                    key=lambda item: (-int(item[1]), str(item[0])),
                )
                if str(code)
            }
            top_rejects = dict(option_summary.get("top_rejects") or {})
            if not top_rejects:
                ordered = list(reject_counts.items())
                top_rejects = {str(code): int(count) for code, count in ordered[:8]}
            hard_top_rejects = {
                str(code): int(count)
                for code, count in top_rejects.items()
                if self._is_scan_reason_hard_gate(code)
            }
            option_reject_total = int(option_summary.get("option_reject_total") or sum(top_rejects.values()))
            logger.warning(
                "TB_REJECT_SUMMARY %s",
                {
                    "symbol": symbol,
                    "total_candidates": considered or int(self._scan_total_candidates or 0),
                    "survived": survivors,
                    "survived_candidates": survivors,
                    "reject_counts": reject_counts,
                },
            )
            logger.warning(
                "OPTION_SCAN_REJECT_SUMMARY symbol=%s considered=%s survivors=%s option_reject_total=%s top_rejects=%s hard_top_rejects=%s",
                symbol,
                considered,
                survivors,
                option_reject_total,
                top_rejects,
                hard_top_rejects,
            )
            logger.warning(
                "NO_CANDIDATE_PATH symbol=%s considered=%s survivors=%s hard_top_rejects=%s top_rejects=%s",
                symbol,
                considered,
                survivors,
                hard_top_rejects,
                top_rejects,
            )
            unresolved_reason_codes = {
                "MISSING_CONTRACT_FIELDS",
                "UNRESOLVED_CONTRACT",
                "MISSING_OPTION_TOKEN",
                "NO_TOKEN",
            }
            if considered == 0:
                try:
                    self._log_blocked_candidate(
                        symbol,
                        "unresolved_contract",
                        "Option contract unresolved before candidate gating",
                        market_data=market_data,
                        extra={
                            "derived_levels": False,
                            "stop": None,
                            "target": None,
                            "reason_code": "unresolved_contract",
                        },
                    )
                except Exception:
                    pass
            elif top_rejects:
                try:
                    self._log_blocked_candidate(
                        symbol,
                        "no_viable_candidates",
                        "No viable trade candidates after option scan",
                        market_data=market_data,
                        extra={
                            "derived_levels": False,
                            "stop": None,
                            "target": None,
                            "reason_code": "no_viable_candidates",
                            "option_reject_reason_counts": reject_counts,
                            "top_option_reject_reasons": list(top_rejects.keys()),
                        },
                    )
                except Exception:
                    pass
            reject_ctx.setdefault("reject_counts", reject_counts)
            reject_ctx.setdefault("top_reject_counts", top_rejects)
            reject_ctx.setdefault("hard_top_rejects", hard_top_rejects)
            reject_ctx.setdefault("option_rows_considered", considered)
            reject_ctx.setdefault("survivor_count", survivors)
        reject_ctx["reason"] = reject_reason
        self._reject_ctx = reject_ctx
        return None

    def _apply_fallback_candidate_flags(
        self,
        candidate,
        *,
        reason: str,
        execution_allowed_override: bool | None = None,
        planning_only_override: bool | None = None,
        tradable_override: bool | None = None,
    ) -> Trade | dict:
        fallback_reason = str(reason or "no_viable_candidates_top_ranked").strip() or "no_viable_candidates_top_ranked"
        fallback_conf_cap = float(getattr(cfg, "MIN_BREADTH_FALLBACK_CONFIDENCE", 0.12))
        fallback_size_mult = 0.5
        if isinstance(candidate, dict):
            out = dict(candidate)
            source_flags = dict(out.get("source_flags") or {})
            source_flags["fallback_candidate"] = True
            source_flags["fallback_reason"] = fallback_reason
            out["source_flags"] = source_flags
            out["fallback_candidate"] = True
            out["fallback_reason"] = fallback_reason
            out["tradable"] = False if tradable_override is None else bool(tradable_override)
            out["execution_allowed"] = False
            out["planning_only"] = True if planning_only_override is None else bool(planning_only_override)
            out["reason"] = fallback_reason
            conf = float(out.get("confidence") or 0.0)
            out["confidence"] = min(conf, fallback_conf_cap)
            size_mult = float(out.get("size_mult") or 1.0)
            out["size_mult"] = min(size_mult, fallback_size_mult)
            blockers = list(out.get("tradable_reasons_blocking") or [])
            if "fallback_no_viable_candidates" not in blockers:
                blockers.append("fallback_no_viable_candidates")
            out["tradable_reasons_blocking"] = blockers
            return out
        source_flags = dict(getattr(candidate, "source_flags", {}) or {})
        source_flags["fallback_candidate"] = True
        source_flags["fallback_reason"] = fallback_reason
        blockers = list(getattr(candidate, "tradable_reasons_blocking", []) or [])
        if "fallback_no_viable_candidates" not in blockers:
            blockers.append("fallback_no_viable_candidates")
        conf = float(getattr(candidate, "confidence", 0.0))
        size_mult = float(getattr(candidate, "size_mult", 1.0))
        return replace(
            candidate,
            source_flags=source_flags,
            confidence=min(conf, fallback_conf_cap),
            size_mult=min(size_mult, fallback_size_mult),
            tradable=False if tradable_override is None else bool(tradable_override),
            execution_allowed=False,
            planning_only=True if planning_only_override is None else bool(planning_only_override),
            reason=fallback_reason,
            tradable_reasons_blocking=blockers,
        )

    def _set_last_ranked_candidates(self, candidates) -> None:
        ranked_candidates = []
        invalid_samples = []
        type_histogram = {}
        sample_limit = max(
            0,
            int(getattr(cfg, "TRADE_BUILDER_INVALID_RANKED_CANDIDATE_SAMPLE_LIMIT", 5) or 5),
        )
        for candidate in list(candidates or []):
            type_name = type(candidate).__name__ if candidate is not None else "NoneType"
            type_histogram[type_name] = int(type_histogram.get(type_name, 0)) + 1
            stamped = candidate
            if stamped is None:
                if len(invalid_samples) < sample_limit:
                    invalid_samples.append(
                        {
                            "type": type_name,
                            "trade_id": None,
                            "symbol": None,
                            "candidate_status": None,
                            "execution_status": None,
                        }
                    )
                continue
            candidate_status = str(getattr(stamped, "candidate_status", None) or "").strip().lower()
            if not candidate_status:
                decision_trace = getattr(stamped, "decision_trace", {}) or {}
                if isinstance(decision_trace, dict):
                    candidate_status = str(decision_trace.get("candidate_status") or "").strip().lower()
                if not candidate_status:
                    candidate_class = str(getattr(stamped, "candidate_class", None) or "").strip().upper()
                    candidate_status = {
                        "EXECUTABLE": "executable",
                        "NEAR_EXECUTABLE": "near_executable",
                        "ADVISORY_ONLY": "advisory_only",
                        "BLOCKED": "blocked",
                        "BLOCKED_CONTRACT": "blocked_contract",
                    }.get(candidate_class, "")
                if not candidate_status:
                    permission = str(getattr(stamped, "permission", None) or "").strip().upper()
                    final_action = str(getattr(stamped, "final_action", None) or "").strip().upper()
                    execution_status = str(getattr(stamped, "execution_status", None) or "").strip().lower()
                    if permission == "BLOCK" or final_action == "BLOCK" or execution_status == "blocked":
                        candidate_status = "blocked"
                    elif permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY" or execution_status == "queue_only":
                        candidate_status = "advisory_only"
                    elif permission == "EXECUTE" or final_action == "EXECUTE" or execution_status == "executable":
                        candidate_status = "executable"
                    else:
                        candidate_status = "advisory_only"
                source_flags = dict(getattr(stamped, "source_flags", {}) or {})
                candidate_strategy_family = str(
                    getattr(stamped, "strategy_family", None)
                    or source_flags.get("strategy_family")
                    or getattr(stamped, "strategy", None)
                    or source_flags.get("strategy")
                    or getattr(stamped, "setup_variant", None)
                    or source_flags.get("setup_variant")
                    or ""
                ).strip()
                if candidate_strategy_family and not str(getattr(stamped, "strategy_family", None) or "").strip():
                    if isinstance(stamped, dict):
                        stamped = dict(stamped)
                        stamped["strategy_family"] = candidate_strategy_family
                    else:
                        stamped = replace(stamped, strategy_family=candidate_strategy_family)
                    source_flags["strategy_family"] = candidate_strategy_family
                source_flags["candidate_status"] = candidate_status
                if isinstance(stamped, dict):
                    stamped = dict(stamped)
                    stamped["candidate_status"] = candidate_status
                    stamped["source_flags"] = source_flags
                else:
                    stamped = replace(stamped, candidate_status=candidate_status, source_flags=source_flags)
            stamped = stamp_lifecycle_stage(stamped, "ranked_snapshot")
            try:
                assert_ranked_candidate_ready(stamped)
            except AssertionError:
                if len(invalid_samples) < sample_limit:
                    invalid_samples.append(
                        {
                            "type": type_name,
                            "trade_id": getattr(stamped, "trade_id", None) if not isinstance(stamped, dict) else stamped.get("trade_id"),
                            "symbol": getattr(stamped, "symbol", None) if not isinstance(stamped, dict) else stamped.get("symbol"),
                            "candidate_status": getattr(stamped, "candidate_status", None) if not isinstance(stamped, dict) else stamped.get("candidate_status"),
                            "execution_status": getattr(stamped, "execution_status", None) if not isinstance(stamped, dict) else stamped.get("execution_status"),
                        }
                    )
                continue
            ranked_candidates.append(stamped)
        if invalid_samples:
            caller = None
            try:
                stack = inspect.stack(context=0)
                if len(stack) > 1:
                    frame = stack[1]
                    caller = f"{frame.function}:{frame.lineno}"
            except Exception:
                caller = None
            logger.warning(
                "trade_builder_invalid_ranked_candidates caller=%s count=%s type_hist=%s sample=%s",
                caller,
                max(0, len(list(candidates or [])) - len(ranked_candidates)),
                type_histogram,
                invalid_samples,
            )
        self._last_ranked_candidates = ranked_candidates

    @staticmethod
    def _candidate_field(candidate, field: str, default=None):
        if isinstance(candidate, dict):
            return candidate.get(field, default)
        return getattr(candidate, field, default)

    @staticmethod
    def _candidate_telemetry_field(candidate, source_flags: dict | None, decision_trace: dict | None, field: str, default=None):
        value = TradeBuilder._candidate_field(candidate, field, None)
        if value is None and isinstance(source_flags, dict):
            value = source_flags.get(field)
        if value is None and isinstance(decision_trace, dict):
            value = decision_trace.get(field)
        if value is None and field == "raw_rank_score":
            for fallback_field in ("ranking_score", "rank_score"):
                value = TradeBuilder._candidate_field(candidate, fallback_field, None)
                if value is None and isinstance(source_flags, dict):
                    value = source_flags.get(fallback_field)
                if value is None and isinstance(decision_trace, dict):
                    value = decision_trace.get(fallback_field)
                if value is not None:
                    break
        if value is None:
            score_inputs_used = TradeBuilder._candidate_field(candidate, "score_inputs_used", {})
            if isinstance(score_inputs_used, dict):
                value = score_inputs_used.get(field)
        if value is None:
            score_breakdown = TradeBuilder._candidate_field(candidate, "score_breakdown", {})
            if isinstance(score_breakdown, dict):
                value = score_breakdown.get(field)
        return default if value is None else value

    @staticmethod
    def _setup_telemetry_fields(
        candidate,
        source_flags: dict | None,
        decision_trace: dict | None,
        *,
        candidate_quality_score: float | None = None,
        trigger_base_score: float | None = None,
        invalidation_score: float | None = None,
        overextension_score: float | None = None,
        timing_quality_score: float | None = None,
    ) -> dict[str, float | None]:
        source_flags = dict(source_flags or {}) if isinstance(source_flags, dict) else {}
        decision_trace = dict(decision_trace or {}) if isinstance(decision_trace, dict) else {}
        family_consensus_components = source_flags.get("family_consensus_components") or decision_trace.get("family_consensus_components") or {}
        family_survival_components = source_flags.get("family_survival_components") or decision_trace.get("family_survival_components") or {}
        if not isinstance(family_consensus_components, dict):
            family_consensus_components = {}
        if not isinstance(family_survival_components, dict):
            family_survival_components = {}

        def _first_non_none(*values):
            for value in values:
                if value is not None:
                    return value
            return None

        setup_regime_alignment_score = _first_non_none(
            TradeBuilder._candidate_telemetry_field(candidate, source_flags, decision_trace, "setup_regime_alignment_score"),
            family_survival_components.get("regime_alignment"),
            family_consensus_components.get("regime_alignment"),
        )
        setup_structure_score = _first_non_none(
            TradeBuilder._candidate_telemetry_field(candidate, source_flags, decision_trace, "setup_structure_score"),
            family_consensus_components.get("structure_strength"),
            family_survival_components.get("structure_strength"),
        )
        setup_thesis_score = _first_non_none(
            TradeBuilder._candidate_telemetry_field(candidate, source_flags, decision_trace, "setup_thesis_score"),
            candidate_quality_score,
            source_flags.get("candidate_quality_score"),
            decision_trace.get("candidate_quality_score"),
            TradeBuilder._candidate_field(candidate, "candidate_quality_score", None),
            TradeBuilder._candidate_field(candidate, "quality_score", None),
        )
        return {
            "setup_regime_alignment_score": setup_regime_alignment_score,
            "setup_structure_score": setup_structure_score,
            "setup_thesis_score": setup_thesis_score,
            "trigger_base_score": _first_non_none(
                TradeBuilder._candidate_telemetry_field(candidate, source_flags, decision_trace, "trigger_base_score"),
                trigger_base_score,
                source_flags.get("trigger_score_raw"),
                decision_trace.get("trigger_score_raw"),
                TradeBuilder._candidate_field(candidate, "trigger_score_raw", None),
            ),
            "entry_invalidation_score": _first_non_none(
                TradeBuilder._candidate_telemetry_field(candidate, source_flags, decision_trace, "entry_invalidation_score"),
                invalidation_score,
                source_flags.get("invalidation_score"),
                decision_trace.get("invalidation_score"),
                TradeBuilder._candidate_field(candidate, "invalidation_score", None),
            ),
            "entry_overextension_score": _first_non_none(
                TradeBuilder._candidate_telemetry_field(candidate, source_flags, decision_trace, "entry_overextension_score"),
                overextension_score,
                source_flags.get("overextension_score"),
                decision_trace.get("overextension_score"),
                TradeBuilder._candidate_field(candidate, "overextension_score", None),
            ),
            "entry_timing_quality_score": _first_non_none(
                TradeBuilder._candidate_telemetry_field(candidate, source_flags, decision_trace, "entry_timing_quality_score"),
                timing_quality_score,
                source_flags.get("timing_quality"),
                decision_trace.get("timing_quality"),
                TradeBuilder._candidate_field(candidate, "timing_quality", None),
            ),
        }

    def _candidate_feature_quality(self, candidate, market_data: dict | None) -> dict:
        data = market_data if isinstance(market_data, dict) else {}
        opt_like = {
            "ltp": self._candidate_field(candidate, "opt_ltp")
            or self._candidate_field(candidate, "current_ltp")
            or data.get("ltp")
            or data.get("opt_ltp"),
            "last_price": self._candidate_field(candidate, "opt_ltp")
            or self._candidate_field(candidate, "current_ltp")
            or data.get("ltp")
            or data.get("opt_ltp"),
            "bid": self._candidate_field(candidate, "opt_bid")
            or self._candidate_field(candidate, "best_bid")
            or data.get("bid"),
            "ask": self._candidate_field(candidate, "opt_ask")
            or self._candidate_field(candidate, "best_ask")
            or data.get("ask"),
            "quote_age_sec": self._candidate_field(candidate, "quote_age_sec", data.get("quote_age_sec")),
            "quote_ok": self._candidate_field(candidate, "quote_ok", data.get("quote_ok", True)),
            "volume": self._candidate_field(candidate, "volume", data.get("volume")),
            "current_volume": self._candidate_field(
                candidate,
                "current_volume",
                data.get("current_volume", data.get("volume")),
            ),
        }
        return assess_trade_feature_quality(data, opt_like)

    def classify_candidate(self, candidate, market_data: dict | None = None) -> tuple[str, str | None, dict]:
        source_flags = dict(self._candidate_field(candidate, "source_flags", {}) or {})
        blockers = [str(code) for code in (self._candidate_field(candidate, "tradable_reasons_blocking", []) or []) if str(code).strip()]
        feature_quality = self._candidate_feature_quality(candidate, market_data)
        fresh_quote_ok = bool(feature_quality.get("fresh_quote_ok"))
        liquidity_ok = bool(feature_quality.get("liquidity_ok"))
        spread_ok = bool(feature_quality.get("spread_ok"))
        market_mode = str(
            self._candidate_field(candidate, "market_mode")
            or source_flags.get("runtime_mode")
            or source_flags.get("market_mode")
            or ((market_data or {}).get("market_context") or {}).get("mode")
            or ((market_data or {}).get("market_context") or {}).get("execution_mode")
            or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).strip().upper()
        if market_data:
            try:
                market_mode = derive_market_context(market_data).mode
            except Exception:
                pass
        execution_allowed = bool(self._candidate_field(candidate, "execution_allowed", False))
        tradable = bool(self._candidate_field(candidate, "tradable", False))
        planning_only = bool(self._candidate_field(candidate, "planning_only", False)) or market_mode == "OFFHOURS"
        execution_entry = self._candidate_field(candidate, "execution_entry")
        execution_entry_status = str(self._candidate_field(candidate, "execution_entry_status") or "").strip().lower()
        executable_truth = bool(execution_entry is not None and execution_entry_status == "executable")
        data_sources = {
            str(value).strip().lower()
            for value in (
                self._candidate_field(candidate, "chain_source"),
                self._candidate_field(candidate, "option_ltp_source"),
                self._candidate_field(candidate, "price_source"),
                source_flags.get("chain_source"),
                source_flags.get("quote_source"),
            )
            if str(value or "").strip()
        }
        is_fallback = bool(
            source_flags.get("fallback_candidate")
            or source_flags.get("recovered_fallback")
            or "fallback_no_viable_candidates" in blockers
            or bool(data_sources & {"synthetic_chain", "close_fallback", "quote_fallback", "recovered_fallback"})
        )

        if is_fallback:
            primary_blocker = str(source_flags.get("fallback_reason") or self._candidate_field(candidate, "reason") or "fallback_candidate")
            return "ADVISORY_ONLY", primary_blocker, feature_quality
        if planning_only:
            primary_blocker = "offhours_mode" if market_mode == "OFFHOURS" else "planning_only"
            return "ADVISORY_ONLY", primary_blocker, feature_quality
        if execution_allowed and tradable and executable_truth and fresh_quote_ok and liquidity_ok and spread_ok:
            return "EXECUTABLE", None, feature_quality

        primary_blocker = None
        reason_priority = list(feature_quality.get("issues") or []) + blockers
        if not fresh_quote_ok and "stale_quote" not in reason_priority:
            reason_priority.append("stale_quote")
        if not liquidity_ok and "missing_liquidity_validation" not in reason_priority:
            reason_priority.append("missing_liquidity_validation")
        if not spread_ok and "missing_spread" not in reason_priority:
            reason_priority.append("missing_spread")
        if not executable_truth and "missing_execution_entry" not in reason_priority:
            reason_priority.append("missing_execution_entry")
        if reason_priority:
            primary_blocker = str(reason_priority[0])
        return "NEAR_EXECUTABLE", primary_blocker, feature_quality

    def _apply_candidate_contract(self, candidate, *, market_data: dict | None = None):
        candidate_class, primary_blocker, feature_quality = self.classify_candidate(candidate, market_data=market_data)
        source_flags = dict(self._candidate_field(candidate, "source_flags", {}) or {})
        blockers = [str(code) for code in (self._candidate_field(candidate, "tradable_reasons_blocking", []) or []) if str(code).strip()]
        market_mode = str(
            feature_quality.get("market_mode")
            or self._candidate_field(candidate, "market_mode")
            or source_flags.get("runtime_mode")
            or source_flags.get("market_mode")
            or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).strip().upper()
        setup_quality = (
            self._coerce_positive_float(self._candidate_field(candidate, "setup_strength"))
            or self._coerce_positive_float(self._candidate_field(candidate, "rank_score"))
            or self._clamp_confidence(self._candidate_field(candidate, "builder_confidence"))
            or self._clamp_confidence(self._candidate_field(candidate, "confidence"))
            or 0.0
        )
        confluence_score = (
            self._clamp_confidence(self._candidate_field(candidate, "sizing_confluence_score"))
            or self._clamp_confidence(((self._candidate_field(candidate, "trade_score_detail") or {}).get("confluence_score")))
            or 0.0
        )
        regime_fit = (
            self._clamp_confidence(self._candidate_field(candidate, "regime_fit"))
            or (0.8 if str(self._candidate_field(candidate, "regime") or "").strip().upper() in {"TREND", "RANGE", "RANGE_VOLATILE"} else 0.55)
        )
        liquidity_quality = (
            self._clamp_confidence(self._candidate_field(candidate, "liquidity_score"))
            or float(feature_quality.get("liquidity_quality") or 0.0)
        )
        freshness_quality = float(feature_quality.get("freshness_quality") or 0.0)
        spread_quality = (
            self._clamp_confidence(self._candidate_field(candidate, "spread_score"))
            or float(feature_quality.get("spread_quality") or 0.0)
        )
        execution_feasibility = (
            self._clamp_confidence(
                (self._candidate_field(candidate, "score_breakdown") or {}).get("execution_feasibility_score")
            )
            or ((liquidity_quality * 0.5) + (spread_quality * 0.3) + (freshness_quality * 0.2))
        )

        # Native Score Boost for High-Strength Mean Reversion Candidates
        candidate_type = str(self._candidate_field(candidate, "candidate_type") or "").strip().lower()
        if candidate_type == "mean_reversion":
            quality_detail = self._candidate_field(candidate, "quality_detail") or {}
            mr_strength = float(quality_detail.get("mean_reversion_strength") or 0.0)
            if mr_strength > 1.5:
                setup_quality = max(float(setup_quality or 0.0), 0.65)
                confluence_score = max(float(confluence_score or 0.0), 0.65)

        score_contract = compute_final_score(
            candidate,
            candidate_class=candidate_class,
            market_mode=market_mode,
            setup_quality=setup_quality,
            confluence_score=confluence_score,
            regime_fit=regime_fit,
            liquidity_quality=liquidity_quality,
            freshness_quality=freshness_quality,
            execution_feasibility=execution_feasibility,
            is_fallback=bool(
                source_flags.get("fallback_candidate")
                or source_flags.get("recovered_fallback")
                or "fallback_no_viable_candidates" in blockers
            ),
            stale_quote="stale_quote" in set(feature_quality.get("issues") or []),
            missing_liquidity=not bool(feature_quality.get("liquidity_ok")),
            spread_uncertain=not bool(feature_quality.get("spread_ok")),
        )
        candidate_status_map = {
            "EXECUTABLE": "executable",
            "NEAR_EXECUTABLE": "near_executable",
            "ADVISORY_ONLY": "advisory_only",
        }
        source_flags.update(
            {
                "market_mode": market_mode,
                "fresh_quote_ok": bool(feature_quality.get("fresh_quote_ok")),
                "liquidity_ok": bool(feature_quality.get("liquidity_ok")),
                "spread_ok": bool(feature_quality.get("spread_ok")),
                "data_state": feature_quality.get("data_state"),
                "quote_completeness": feature_quality.get("quote_completeness"),
                "quote_consistency_ok": bool(feature_quality.get("quote_consistency_ok", False)),
                "ltp_age_sec": feature_quality.get("ltp_age_sec"),
                "bid_age_sec": feature_quality.get("bid_age_sec"),
                "ask_age_sec": feature_quality.get("ask_age_sec"),
                "chain_snapshot_age_sec": feature_quality.get("chain_snapshot_age_sec"),
                "spread_source": feature_quality.get("spread_source"),
                "liquidity_validation_mode": feature_quality.get("liquidity_validation_mode"),
                "feature_validation_issues": list(feature_quality.get("issues") or []),
                "candidate_class": candidate_class,
                "primary_blocker": primary_blocker,
                "final_score": float(score_contract["final_score"]),
                "signal_score": float(score_contract.get("signal_score") or 0.0),
                "execution_score": float(score_contract.get("execution_score") or 0.0),
                "priority_score": float(score_contract.get("priority_score") or score_contract["final_score"]),
                "final_score_base": float(score_contract["base_score"]),
                "final_score_penalty_total": float(score_contract["penalty_total"]),
                "final_score_penalty_reasons": list(score_contract["penalty_reasons"]),
                "final_score_class_cap": float(score_contract["class_cap"]),
            }
        )
        execution_allowed = bool(self._candidate_field(candidate, "execution_allowed", False))
        tradable = bool(self._candidate_field(candidate, "tradable", False))
        planning_only = bool(self._candidate_field(candidate, "planning_only", False))
        selected_for_execution = bool(self._candidate_field(candidate, "selected_for_execution", False))
        if candidate_class != "EXECUTABLE":
            execution_allowed = False
            selected_for_execution = False
            if market_mode == "OFFHOURS":
                planning_only = True
        if isinstance(candidate, dict):
            out = dict(candidate)
            out.update(
                {
                    "source_flags": source_flags,
                    "candidate_class": candidate_class,
                    "candidate_status": candidate_status_map[candidate_class],
                    "final_score": float(score_contract["final_score"]),
                    "signal_score": float(score_contract.get("signal_score") or 0.0),
                    "execution_score": float(score_contract.get("execution_score") or 0.0),
                    "priority_score": float(score_contract.get("priority_score") or score_contract["final_score"]),
                    "market_mode": market_mode,
                    "fresh_quote_ok": bool(feature_quality.get("fresh_quote_ok")),
                    "liquidity_ok": bool(feature_quality.get("liquidity_ok")),
                    "spread_ok": bool(feature_quality.get("spread_ok")),
                    "data_state": feature_quality.get("data_state"),
                    "quote_completeness": feature_quality.get("quote_completeness"),
                    "quote_consistency_ok": bool(feature_quality.get("quote_consistency_ok", False)),
                    "ltp_age_sec": feature_quality.get("ltp_age_sec"),
                    "bid_age_sec": feature_quality.get("bid_age_sec"),
                    "ask_age_sec": feature_quality.get("ask_age_sec"),
                    "chain_snapshot_age_sec": feature_quality.get("chain_snapshot_age_sec"),
                    "spread_source": feature_quality.get("spread_source"),
                    "liquidity_validation_mode": feature_quality.get("liquidity_validation_mode"),
                    "primary_blocker": primary_blocker,
                    "execution_allowed": execution_allowed,
                    "planning_only": planning_only,
                    "selected_for_execution": selected_for_execution,
                    "tradable": tradable if candidate_class == "EXECUTABLE" else bool(tradable),
                }
            )
            return out
        return replace(
            candidate,
            source_flags=source_flags,
            candidate_class=candidate_class,
            candidate_status=candidate_status_map[candidate_class],
            final_score=float(score_contract["final_score"]),
            signal_score=float(score_contract.get("signal_score") or 0.0),
            execution_score=float(score_contract.get("execution_score") or 0.0),
            priority_score=float(score_contract.get("priority_score") or score_contract["final_score"]),
            market_mode=market_mode,
            fresh_quote_ok=bool(feature_quality.get("fresh_quote_ok")),
            liquidity_ok=bool(feature_quality.get("liquidity_ok")),
            spread_ok=bool(feature_quality.get("spread_ok")),
            data_state=feature_quality.get("data_state"),
            quote_completeness=feature_quality.get("quote_completeness"),
            quote_consistency_ok=bool(feature_quality.get("quote_consistency_ok", False)),
            ltp_age_sec=feature_quality.get("ltp_age_sec"),
            bid_age_sec=feature_quality.get("bid_age_sec"),
            ask_age_sec=feature_quality.get("ask_age_sec"),
            chain_snapshot_age_sec=feature_quality.get("chain_snapshot_age_sec"),
            spread_source=feature_quality.get("spread_source"),
            liquidity_validation_mode=feature_quality.get("liquidity_validation_mode"),
            primary_blocker=primary_blocker,
            execution_allowed=execution_allowed,
            planning_only=planning_only,
            selected_for_execution=selected_for_execution,
        )

    def _ensure_candidate_identity(self, trade: Trade | None) -> Trade | None:
        if trade is None:
            return trade
        identity = infer_candidate_identity(
            {
                "candidate_type": getattr(trade, "candidate_type", None),
                "strategy_family": getattr(trade, "strategy_family", None),
                "setup_variant": getattr(trade, "setup_variant", None),
                "direction": getattr(trade, "direction", None),
                "instrument": getattr(trade, "instrument", None),
                "instrument_type": getattr(trade, "instrument_type", None),
                "strategy": getattr(trade, "strategy", None),
                "strategy_id": getattr(trade, "strategy_id", None),
                "strategy_name": getattr(trade, "strategy_name", None),
                "entry_condition": getattr(trade, "entry_condition", None),
                "side": getattr(trade, "side", None),
                "option_type": getattr(trade, "option_type", None),
                "type": getattr(trade, "type", None),
                "trade_id": getattr(trade, "trade_id", None),
            }
        )
        strategy_family = str(getattr(trade, "strategy_family", None) or identity.get("strategy_family") or "").strip().lower()
        if strategy_family in {"", "unknown"}:
            raw_strategy = str(getattr(trade, "strategy", None) or getattr(trade, "strategy_name", None) or "").strip().upper()
            if "MEAN" in raw_strategy:
                strategy_family = "mean-reversion"
            elif "VOL" in raw_strategy or "EXPANSION" in raw_strategy:
                strategy_family = "volatility_expansion"
            elif "RANGE" in raw_strategy:
                strategy_family = "range-watchlist"
            elif "CONT" in raw_strategy or "TREND" in raw_strategy:
                strategy_family = "continuation"
            else:
                strategy_family = "unknown"
        candidate_type = str(getattr(trade, "candidate_type", None) or identity.get("candidate_type") or "").strip().lower()
        if candidate_type in {"", "unknown"}:
            candidate_type = "directional"
        setup_variant = str(getattr(trade, "setup_variant", None) or identity.get("setup_variant") or "").strip().lower()
        if setup_variant in {"", "unknown"}:
            setup_variant = strategy_family or "unknown"
        direction = str(getattr(trade, "direction", None) or identity.get("direction") or "").strip()
        if not direction:
            direction = "UNKNOWN"
        return replace(
            trade,
            candidate_type=candidate_type,
            strategy_family=strategy_family,
            setup_variant=setup_variant,
            direction=direction,
        )

    def _heartbeat_feed_snapshot(self) -> dict:
        payload = self._cached_feed_runtime_snapshot(now_epoch=now_utc_epoch())
        return {
            "feed_ok": payload.get("feed_ok"),
            "ws_connected": payload.get("ws_connected"),
            "subscribed_option_tokens_count": payload.get("subscribed_option_tokens_count"),
            "missing_option_tokens_count": payload.get("missing_option_tokens_count"),
        }

    def _cached_feed_runtime_snapshot(self, *, now_epoch: float | None = None) -> dict:
        ttl_sec = max(0.1, float(getattr(cfg, "TRADE_BUILDER_FEED_RUNTIME_CACHE_TTL_SEC", 1.0) or 1.0))
        epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
        if (epoch - float(self._feed_runtime_cache_ts or 0.0)) <= ttl_sec and isinstance(self._feed_runtime_cache_payload, dict):
            return dict(self._feed_runtime_cache_payload)
        payload = {}
        latest_mtime = -1.0
        candidates = [
            Path(data_root()) / "feed_runtime_latest.json",
            logs_dir() / "feed_runtime_latest.json",
        ]
        for candidate_path in candidates:
            try:
                if not candidate_path.exists():
                    continue
                mtime = float(candidate_path.stat().st_mtime)
            except Exception:
                continue
            try:
                raw = json.loads(candidate_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            normalized = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
            if not isinstance(normalized, dict):
                continue
            if mtime >= latest_mtime:
                latest_mtime = mtime
                payload = dict(normalized)
        self._feed_runtime_cache_ts = epoch
        self._feed_runtime_cache_payload = dict(payload)
        return dict(payload)

    def _symbol_feed_option_tick_age(self, symbol: str, *, now_epoch: float | None = None) -> float | None:
        if not bool(getattr(cfg, "TRADE_BUILDER_USE_SYMBOL_FEED_AGE_FALLBACK", True)):
            return None
        payload = self._cached_feed_runtime_snapshot(now_epoch=now_epoch)
        if not isinstance(payload, dict):
            return None
        if payload.get("ws_connected") is False:
            return None
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return None
        reason_map = payload.get("option_feed_block_reason_by_symbol")
        if isinstance(reason_map, dict):
            reason_code = str(reason_map.get(symbol_key) or "").strip().upper()
            if reason_code and reason_code not in {"OK", "NONE"}:
                return None
        tick_ages = payload.get("option_last_tick_age_by_symbol")
        if isinstance(tick_ages, dict):
            try:
                age = float(tick_ages.get(symbol_key))
                if age >= 0.0:
                    return age
            except Exception:
                pass
        tick_ts = None
        tick_map = payload.get("last_option_tick_ts_by_symbol")
        if isinstance(tick_map, dict):
            try:
                tick_ts = float(tick_map.get(symbol_key))
            except Exception:
                tick_ts = None
        if tick_ts is None:
            try:
                tick_ts = float(payload.get("last_db_tick_epoch"))
            except Exception:
                tick_ts = None
        if tick_ts is None:
            return None
        age_val = compute_age_sec(tick_ts, now_epoch if now_epoch is not None else now_utc_epoch())
        if age_val is None:
            return None
        return float(age_val)

    def _status_file_payload(self, filename: str) -> dict:
        try:
            payload = json.loads((logs_dir() / filename).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {}

    def _write_scan_status_files(self, summary: dict) -> None:
        payload = dict(summary or {})
        ts_epoch = float(payload.get("ts_epoch") or now_utc_epoch())
        ts_local = datetime.now().astimezone().isoformat()
        accepted = int(payload.get("accepted") or 0)
        total_candidates = int(payload.get("total_candidates") or 0)
        rejected_by_reason = dict(payload.get("rejected_by_reason") or {})
        rejected_total = int(sum(int(v) for v in rejected_by_reason.values()))
        market_open = _coerce_status_bool(
            payload.get("market_open"),
            default=(str(payload.get("mode") or "").strip().upper() != "OFFHOURS"),
        )
        market_mode = str(
            payload.get("market_mode")
            or payload.get("mode")
            or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).strip().upper()
        if not market_open:
            market_mode = "OFFHOURS"
        cycle_status = derive_cycle_semantics(
            market_mode=market_mode,
            market_open=market_open,
            suggestion_count=accepted,
            blocker_counts=rejected_by_reason,
            last_error="",
        )
        market_mode = str(cycle_status.get("market_mode") or market_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).strip().upper()
        market_open = bool(cycle_status.get("market_open"))
        top_blockers = list(cycle_status.get("top_blockers") or top_blockers_from_counts(rejected_by_reason))
        current_suggestions_payload = self._status_file_payload("suggestions_status.json")
        feed_snapshot = self._heartbeat_feed_snapshot()
        suggestions_payload = {
            "ts_epoch": ts_epoch,
            "ts_local": ts_local,
            "status": cycle_status.get("semantic_state"),
            "suggestion_count": accepted,
            "market_mode": market_mode,
            "market_open": bool(market_open),
            "reason": cycle_status.get("dominant_reason"),
            "subreason": cycle_status.get("subreason"),
            "primary_blocker": cycle_status.get("primary_blocker"),
            "feed_ok": feed_snapshot.get("feed_ok"),
            "ws_connected": feed_snapshot.get("ws_connected"),
            "subscribed_option_tokens_count": feed_snapshot.get("subscribed_option_tokens_count"),
            "missing_option_tokens_count": feed_snapshot.get("missing_option_tokens_count"),
            "latest_trade_id": current_suggestions_payload.get("latest_trade_id"),
            "latest_entry_status": current_suggestions_payload.get("latest_entry_status"),
            "latest_permission": current_suggestions_payload.get("latest_permission"),
            "latest_permission_reason": current_suggestions_payload.get("latest_permission_reason"),
        }
        engine_payload = {
            "ts_epoch": ts_epoch,
            "cycle_ok": True,
            "cycle_stage": cycle_status.get("semantic_state"),
            "market_mode": market_mode,
            "market_open": bool(market_open),
            "reason": cycle_status.get("dominant_reason"),
            "subreason": cycle_status.get("subreason"),
            "symbols_scanned": 1 if str(payload.get("symbol") or "").strip() else 0,
            "candidates_seen": total_candidates,
            "candidates_blocked": rejected_total,
            "candidates_enqueued": accepted,
            "top_blockers": top_blockers,
            "primary_blocker": cycle_status.get("primary_blocker"),
            "feed_ok": feed_snapshot.get("feed_ok"),
            "ws_connected": feed_snapshot.get("ws_connected"),
            "subscribed_option_tokens_count": feed_snapshot.get("subscribed_option_tokens_count"),
            "missing_option_tokens_count": feed_snapshot.get("missing_option_tokens_count"),
            "last_error": "",
        }
        write_json_atomic(logs_dir() / "suggestions_status.json", suggestions_payload)
        write_json_atomic(logs_dir() / "engine_cycle_status.json", engine_payload)

    def _decorate_trade_context(self, trade: Trade | None, market_data: dict | None, raw_conf: float | None):
        if trade is None:
            return trade
        trade = self._ensure_candidate_identity(trade)
        trade = stamp_lifecycle_stage(trade, "built")
        data = market_data if isinstance(market_data, dict) else {}
        option_ok, missing_fields = self._option_identity_complete(
            instrument=getattr(trade, "instrument", None),
            instrument_type=getattr(trade, "instrument_type", None),
            right=getattr(trade, "right", None),
            expiry=getattr(trade, "expiry", None),
            tradingsymbol=getattr(trade, "tradingsymbol", None),
            instrument_token=getattr(trade, "instrument_token", None),
            instrument_id=getattr(trade, "instrument_id", None),
        )
        if not option_ok:
            self._log_blocked_candidate(
                str(getattr(trade, "symbol", None) or data.get("symbol") or "UNKNOWN"),
                "unresolved_contract",
                "Option trade blocked: incomplete option identity",
                market_data=data,
                extra={
                    "strike": getattr(trade, "strike", None),
                    "option_type": getattr(trade, "right", None) or getattr(trade, "option_type", None),
                    "expiry": getattr(trade, "expiry", None),
                    "tradingsymbol": getattr(trade, "tradingsymbol", None),
                    "instrument_token": getattr(trade, "instrument_token", None),
                    "instrument_id": getattr(trade, "instrument_id", None),
                    "missing_fields": missing_fields,
                    "skip_derived_levels": True,
                },
            )
            return None
        try:
            conf = raw_conf if raw_conf is not None else getattr(trade, "confidence", None)
            reg_conf = data.get("regime_confidence")
            if reg_conf is None:
                reg_conf = data.get("day_confidence")
            updates = {
                "regime_confidence": reg_conf,
                "day_confidence": data.get("day_confidence"),
                "orb_bias": data.get("orb_bias"),
                "raw_signal_confidence": conf,
            }
            trade_source_flags = dict(getattr(trade, "source_flags", {}) or {})
            try:
                quote_truth_snapshot = self._stamp_quote_truth_snapshot(
                    trade,
                    market_data=data,
                    source_flags=trade_source_flags,
                    lifecycle=None,
                )
                trade_source_flags = dict(getattr(trade, "source_flags", {}) or {})
                trade_source_flags["quote_truth"] = dict(quote_truth_snapshot)
                trade_source_flags["quote_truth_snapshot"] = dict(quote_truth_snapshot)
                object.__setattr__(trade, "source_flags", trade_source_flags)
            except Exception:
                pass
            candidate_status = str(getattr(trade, "candidate_status", None) or "").strip().lower()
            if not candidate_status:
                decision_trace = dict(trade_source_flags.get("decision_trace", {}) or {})
                candidate_status = str(decision_trace.get("candidate_status") or "").strip().lower()
            if not candidate_status:
                candidate_class = str(getattr(trade, "candidate_class", None) or trade_source_flags.get("candidate_class") or "").strip().upper()
                candidate_status = {
                    "EXECUTABLE": "executable",
                    "NEAR_EXECUTABLE": "near_executable",
                    "ADVISORY_ONLY": "advisory_only",
                    "BLOCKED": "blocked",
                    "BLOCKED_CONTRACT": "blocked_contract",
                }.get(candidate_class, "")
            if not candidate_status:
                execution_status = str(getattr(trade, "execution_status", None) or trade_source_flags.get("execution_status") or "").strip().lower()
                permission = str(getattr(trade, "permission", None) or trade_source_flags.get("permission") or "").strip().upper()
                final_action = str(getattr(trade, "final_action", None) or trade_source_flags.get("final_action") or "").strip().upper()
                if permission == "BLOCK" or final_action == "BLOCK" or execution_status == "blocked":
                    candidate_status = "blocked"
                elif permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY" or execution_status == "queue_only":
                    candidate_status = "advisory_only"
                elif permission == "EXECUTE" or final_action == "EXECUTE" or execution_status == "executable":
                    candidate_status = "executable"
                else:
                    candidate_status = "advisory_only"
            trade_source_flags["candidate_status"] = candidate_status
            try:
                object.__setattr__(trade, "candidate_status", candidate_status)
                object.__setattr__(trade, "source_flags", trade_source_flags)
            except Exception:
                pass
            if str(getattr(trade, "instrument", None) or getattr(trade, "instrument_type", None) or "").upper() == "OPT":
                lifecycle = self._build_trade_entry_lifecycle(
                    trade,
                    market_data=data,
                    instrument_matches=option_ok,
                )
                append_execution_entry_trace(
                    module="strategies.trade_builder",
                    stage="build_trade_entry_lifecycle",
                    row={
                        "trade_id": getattr(trade, "trade_id", None),
                        "symbol": getattr(trade, "symbol", None) or data.get("symbol"),
                        "strategy": getattr(trade, "strategy", None),
                        "entry": getattr(trade, "entry", None) or getattr(trade, "entry_price", None),
                        "expected_entry": getattr(trade, "expected_entry", None),
                        "current_ltp": getattr(trade, "current_ltp", None) or data.get("current_ltp"),
                        "option_ltp_source": getattr(trade, "option_ltp_source", None) or data.get("option_ltp_source"),
                        "permission": getattr(trade, "permission", None),
                        "execution_entry": lifecycle.get("execution_entry"),
                        "execution_entry_status": lifecycle.get("execution_entry_status"),
                        "execution_allowed": getattr(trade, "execution_allowed", None),
                    },
                    execution_entry_before=getattr(trade, "execution_entry", None),
                    execution_entry_after=lifecycle.get("execution_entry"),
                    extra={
                        "execution_entry_source": lifecycle.get("execution_entry_source"),
                        "display_entry": lifecycle.get("display_entry"),
                        "display_entry_status": lifecycle.get("display_entry_status"),
                    },
                )
                executable_entry = lifecycle.get("execution_entry")
                executable_status = str(lifecycle.get("execution_entry_status") or "").strip().lower()
                display_entry = lifecycle.get("display_entry")
                display_source = lifecycle.get("display_entry_source")
                display_status = lifecycle.get("display_entry_status")
                execution_source = lifecycle.get("execution_entry_source")
                entry_reason = lifecycle.get("entry_reason")
                entry_clear_reason = lifecycle.get("entry_clear_reason")
                executable_ready = executable_entry is not None and executable_status == "executable"
                trigger_entry_condition = getattr(trade, "entry_condition", None)
                trigger_entry_price = getattr(trade, "entry_price", None)
                use_trigger_entry = bool(trigger_entry_condition) and trigger_entry_price is not None
                updates.update(
                    {
                        "builder_confidence": getattr(trade, "builder_confidence", None) or conf,
                        "sizing_confluence_score": (
                            (getattr(trade, "trade_score_detail", {}) or {}).get("confluence_score")
                            if isinstance(getattr(trade, "trade_score_detail", {}) or {}, dict)
                            else None
                        ),
                        "execution_entry": executable_entry,
                        "execution_entry_source": execution_source,
                        "execution_entry_status": executable_status or ("missing" if executable_entry is None else None),
                        "display_entry": display_entry,
                        "display_entry_source": display_source,
                        "display_entry_status": display_status,
                        "entry_display_status": display_status,
                        "entry_reason": entry_reason,
                        "entry_clear_reason": entry_clear_reason,
                        "entry_block_code": str(entry_clear_reason or "").strip().lower() or None,
                        "entry_status": lifecycle.get("entry_status"),
                    }
                )
                if executable_ready:
                    applied_entry_price = trigger_entry_price if use_trigger_entry else executable_entry
                    updates["entry_price"] = round(float(applied_entry_price), 2)
                    updates["entry_price_source"] = execution_source
                    updates["execution_allowed"] = True
                    if display_entry is not None:
                        expected_entry_value = trigger_entry_price if use_trigger_entry else display_entry
                        updates["expected_entry"] = round(float(expected_entry_value), 2)
                        updates["expected_entry_source"] = display_source
                elif display_entry is not None:
                    updates["expected_entry"] = round(float(display_entry), 2)
                    updates["expected_entry_source"] = display_source
                if bool(getattr(trade, "execution_allowed", False)) and (not executable_ready):
                    lifecycle_reason = str(entry_clear_reason or entry_reason or "missing_execution_entry").strip() or "missing_execution_entry"
                    tradable_reasons = list(getattr(trade, "tradable_reasons_blocking", []) or [])
                    if lifecycle_reason not in tradable_reasons:
                        tradable_reasons.append(lifecycle_reason)
                    updates["execution_allowed"] = False
                    updates["reason"] = lifecycle_reason
                    updates["tradable_reasons_blocking"] = tradable_reasons
                decision_trace = dict(trade_source_flags.get("decision_trace", {}) or {})
                if decision_trace:
                    preliminary_permission = (
                        str(decision_trace.get("preliminary_permission") or decision_trace.get("permission") or "").strip().upper()
                        or ("EXECUTE" if bool(getattr(trade, "execution_allowed", False)) else "ADVISORY_ONLY")
                    )
                    preliminary_reason = str(
                        decision_trace.get("preliminary_permission_reason")
                        or decision_trace.get("permission_reason")
                        or getattr(trade, "reason", None)
                        or ""
                    ).strip() or ("execution_allowed" if bool(getattr(trade, "execution_allowed", False)) else "intent_blocked")
                    decision_trace["preliminary_permission"] = preliminary_permission
                    decision_trace["preliminary_permission_reason"] = preliminary_reason
                    decision_trace["preliminary_exec_allowed"] = bool(
                        decision_trace.get("preliminary_exec_allowed", getattr(trade, "execution_allowed", False))
                    )
                    decision_trace.update(
                        self._finalize_advisory_decision(
                            trade=trade,
                            lifecycle=lifecycle,
                            decision_trace=decision_trace,
                        )
                    )
                    trade_source_flags["decision_trace"] = decision_trace
            updates["source_flags"] = trade_source_flags
            updated_trade = replace(
                trade,
                **updates,
            )
            updated_trade = self._apply_candidate_contract(updated_trade, market_data=data)
            try:
                early_quote_truth_snapshot = self._stamp_quote_truth_snapshot(
                    updated_trade,
                    market_data=data,
                    source_flags=trade_source_flags,
                    lifecycle=lifecycle,
                )
                trade_source_flags = dict(getattr(updated_trade, "source_flags", {}) or {})
                trade_source_flags["quote_truth"] = dict(early_quote_truth_snapshot)
                trade_source_flags["quote_truth_snapshot"] = dict(early_quote_truth_snapshot)
                updated_trade = replace(updated_trade, source_flags=trade_source_flags)
            except Exception:
                pass
            requested_strike = getattr(trade, "strike", None)
            resolved_strike = getattr(updated_trade, "strike", None)
            requested_expiry = getattr(trade, "expiry", None)
            resolved_expiry = getattr(updated_trade, "expiry", None)
            exact_strike_match = True
            try:
                if requested_strike in (None, "", "None") or resolved_strike in (None, "", "None"):
                    exact_strike_match = False
                else:
                    exact_strike_match = float(requested_strike) == float(resolved_strike)
            except Exception:
                exact_strike_match = False
            exact_expiry_match = str(requested_expiry or "").strip() == str(resolved_expiry or "").strip()
            exact_match = bool(exact_strike_match and exact_expiry_match)
            strike_delta = None
            try:
                if requested_strike not in (None, "", "None") and resolved_strike not in (None, "", "None"):
                    strike_delta = abs(float(resolved_strike) - float(requested_strike))
            except Exception:
                strike_delta = None
            resolution_penalty = 0.0 if exact_match else float(min(1.0, ((strike_delta or 0.0) / max(abs(float(requested_strike or resolved_strike or 1.0)), 1.0)) + (0.1 if not exact_expiry_match else 0.0)))
            contract_resolution = {
                "requested_strike": requested_strike,
                "resolved_strike": resolved_strike,
                "requested_expiry": requested_expiry,
                "resolved_expiry": resolved_expiry,
                "contract_exact_match": bool(exact_match),
                "resolution_mode": "exact" if exact_match else "fallback",
                "resolution_penalty": resolution_penalty,
                "fallback_used": not exact_match,
                "fallback_class": None if exact_match else "contract_fallback",
                "fallback_reason": None if exact_match else "nearest_contract_match",
                "fallback_execution_policy": "EXECUTE" if exact_match else "QUEUE_ONLY",
            }
            updated_trade = stamp_lifecycle_stage(updated_trade, "fallback_stamped" if contract_resolution["fallback_used"] else "built")
            if contract_resolution["fallback_used"]:
                fallback_reason = str(contract_resolution.get("fallback_reason") or "contract_resolution_fallback").strip() or "contract_resolution_fallback"
                updates["execution_allowed"] = False
                updates["reason"] = fallback_reason
                decision_trace = dict(trade_source_flags.get("decision_trace", {}) or {})
                decision_trace.update(
                    {
                        "permission": "QUEUE_ONLY",
                        "permission_reason": fallback_reason,
                        "final_action": "QUEUE_ONLY",
                        "readiness": "QUEUE_ONLY",
                        "execution_status": "queue_only",
                        "execution_allowed": False,
                    }
                )
                trade_source_flags["decision_trace"] = decision_trace
            updated_trade = mirror_candidate_truth(
                updated_trade,
                decision_trace=trade_source_flags.get("decision_trace", {}),
                lifecycle=lifecycle,
                contract_resolution=contract_resolution,
                fallback_metadata=contract_resolution,
                lifecycle_stage="decision_finalized",
            )
            try:
                append_trade_lifecycle_event(
                    trade_id=str(getattr(updated_trade, "trade_id", None)),
                    symbol=str(getattr(updated_trade, "symbol", None) or data.get("symbol") or ""),
                    strategy=str(getattr(updated_trade, "strategy", None) or ""),
                    stage="market_ingestion",
                    status="seen",
                    reason=str(data.get("invalid_reason") or "snapshot_valid"),
                )
                append_trade_lifecycle_event(
                    trade_id=str(getattr(updated_trade, "trade_id", None)),
                    symbol=str(getattr(updated_trade, "symbol", None) or data.get("symbol") or ""),
                    strategy=str(getattr(updated_trade, "strategy", None) or ""),
                    stage="candidate_generation",
                    status="created",
                    reason=str(getattr(updated_trade, "strategy", "") or "trade_builder"),
                    extra={
                        "opportunity_score": getattr(updated_trade, "opportunity_score", None),
                        "opportunity_rank": getattr(updated_trade, "opportunity_rank", None),
                    },
                )
            except Exception:
                pass
            try:
                final_flags = dict(getattr(updated_trade, "source_flags", {}) or {})
                final_quote_row = None
                option_chain = data.get("option_chain")
                if isinstance(option_chain, (list, tuple)):
                    final_trade_token = self._coerce_nonnegative_float(getattr(updated_trade, "instrument_token", None))
                    final_trade_symbol = str(getattr(updated_trade, "tradingsymbol", None) or "").strip()
                    final_trade_strike = self._coerce_nonnegative_float(getattr(updated_trade, "strike", None))
                    final_trade_right = str(
                        getattr(updated_trade, "right", None)
                        or getattr(updated_trade, "option_type", None)
                        or ""
                    ).strip().upper()
                    final_trade_expiry = str(
                        getattr(updated_trade, "expiry", None)
                        or getattr(updated_trade, "expiry_date", None)
                        or ""
                    ).strip()
                    for row in option_chain:
                        if not isinstance(row, dict):
                            continue
                        row_token = self._coerce_nonnegative_float(row.get("instrument_token"))
                        row_symbol = str(row.get("tradingsymbol") or "").strip()
                        row_strike = self._coerce_nonnegative_float(row.get("strike"))
                        row_right = str(
                            row.get("right")
                            or row.get("type")
                            or row.get("option_type")
                            or ""
                        ).strip().upper()
                        row_expiry = str(row.get("expiry") or row.get("expiry_date") or "").strip()
                        if final_trade_token is not None and row_token is not None and int(final_trade_token) == int(row_token):
                            final_quote_row = row
                            break
                        if final_trade_symbol and row_symbol and final_trade_symbol == row_symbol:
                            final_quote_row = row
                            break
                        if (
                            final_trade_strike is not None
                            and row_strike is not None
                            and final_trade_right
                            and row_right
                            and final_trade_expiry
                            and row_expiry
                            and float(final_trade_strike) == float(row_strike)
                            and final_trade_right == row_right
                            and final_trade_expiry == row_expiry
                        ):
                            final_quote_row = row
                            break
                final_quote_ts_epoch = self._coerce_nonnegative_float(
                    final_quote_row.get("quote_ts_epoch") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("quote_timestamp_epoch") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("timestamp_epoch") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("ts_epoch") if isinstance(final_quote_row, dict) else None
                )
                final_quote_age_sec = self._coerce_nonnegative_float(
                    final_quote_row.get("quote_age_sec") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("option_age_sec") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("price_age_sec") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("option_ltp_age_sec") if isinstance(final_quote_row, dict) else None
                )
                # Derive quote age/timestamp deterministically from the cycle snapshot time when available.
                # Never invent quote truth in LIVE: only derive age from a real quote timestamp, or derive
                # a timestamp from an explicitly provided quote age.
                now_epoch = self._coerce_nonnegative_float(
                    data.get("timestamp_epoch")
                    or data.get("timestamp")
                    or data.get("ts_epoch")
                )
                if now_epoch is None:
                    now_epoch = float(now_utc_epoch())
                if final_quote_ts_epoch is None and final_quote_age_sec is not None:
                    final_quote_ts_epoch = max(0.0, float(now_epoch) - float(final_quote_age_sec))
                if final_quote_age_sec is None and final_quote_ts_epoch is not None:
                    final_quote_age_sec = max(0.0, float(now_epoch) - float(final_quote_ts_epoch))
                final_quote_source = "option_chain_live" if final_quote_row else "unknown"
                if isinstance(final_quote_row, dict):
                    if final_quote_row.get("quote_source") not in (None, "", "None"):
                        final_quote_source = str(final_quote_row.get("quote_source")).strip() or final_quote_source
                    elif bool(final_quote_row.get("quote_live", True)) or bool(final_quote_row.get("quote_ok", True)):
                        final_quote_source = "option_chain_live"
                final_option_ltp_source = ""
                if isinstance(final_quote_row, dict):
                    final_option_ltp_source = str(
                        final_quote_row.get("option_ltp_source")
                        or final_quote_row.get("quote_source")
                        or ""
                    ).strip()
                if not final_option_ltp_source or final_option_ltp_source.lower() == "none":
                    final_option_ltp_source = final_quote_source
                # Spread is only valid when derived from real bid/ask and a real mark/ltp anchor.
                final_best_bid = self._coerce_nonnegative_float(
                    final_quote_row.get("best_bid") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("bid") if isinstance(final_quote_row, dict) else None
                )
                final_best_ask = self._coerce_nonnegative_float(
                    final_quote_row.get("best_ask") if isinstance(final_quote_row, dict) else None
                    or final_quote_row.get("ask") if isinstance(final_quote_row, dict) else None
                )
                final_mark = self._coerce_nonnegative_float(
                    (final_quote_row.get("mark_price") if isinstance(final_quote_row, dict) else None)
                    or (final_quote_row.get("mid_price") if isinstance(final_quote_row, dict) else None)
                    or (final_quote_row.get("ltp") if isinstance(final_quote_row, dict) else None)
                    or (final_quote_row.get("last_price") if isinstance(final_quote_row, dict) else None)
                    or getattr(updated_trade, "mark_price", None)
                    or getattr(updated_trade, "current_ltp", None)
                )
                final_spread_pct = self._coerce_nonnegative_float(
                    final_quote_row.get("spread_pct") if isinstance(final_quote_row, dict) else None
                )
                if final_spread_pct is None and final_best_bid is not None and final_best_ask is not None and final_mark:
                    if float(final_mark) > 0 and float(final_best_ask) >= float(final_best_bid) >= 0:
                        final_spread_pct = max(0.0, float(final_best_ask) - float(final_best_bid)) / max(float(final_mark), 1e-9)
                final_liquidity_score = self._coerce_nonnegative_float(
                    final_quote_row.get("liquidity_score") if isinstance(final_quote_row, dict) else None
                )
                final_quote_truth_snapshot = {
                    "quote_snapshot_id": str(
                        f"{getattr(updated_trade, 'trade_id', None)}|{getattr(updated_trade, 'symbol', None)}|"
                        f"{final_quote_ts_epoch if final_quote_ts_epoch is not None else 'na'}|"
                        f"{final_quote_source}|"
                        f"{final_quote_row.get('ltp') if isinstance(final_quote_row, dict) and final_quote_row.get('ltp') is not None else getattr(updated_trade, 'current_ltp', None) if getattr(updated_trade, 'current_ltp', None) is not None else 'na'}|"
                        f"{final_quote_row.get('best_bid') if isinstance(final_quote_row, dict) and final_quote_row.get('best_bid') is not None else final_quote_row.get('bid') if isinstance(final_quote_row, dict) and final_quote_row.get('bid') is not None else getattr(updated_trade, 'best_bid', None) if getattr(updated_trade, 'best_bid', None) is not None else 'na'}|"
                        f"{final_quote_row.get('best_ask') if isinstance(final_quote_row, dict) and final_quote_row.get('best_ask') is not None else final_quote_row.get('ask') if isinstance(final_quote_row, dict) and final_quote_row.get('ask') is not None else getattr(updated_trade, 'best_ask', None) if getattr(updated_trade, 'best_ask', None) is not None else 'na'}"
                    ),
                    "quote_ts_epoch": final_quote_ts_epoch,
                    "quote_age_sec": final_quote_age_sec,
                    "best_bid": final_best_bid,
                    "best_ask": final_best_ask,
                    "spread_pct": final_spread_pct,
                    "liquidity_score": final_liquidity_score,
                    "current_ltp": self._coerce_nonnegative_float(
                        final_quote_row.get("ltp") if isinstance(final_quote_row, dict) else None
                        or final_quote_row.get("last_price") if isinstance(final_quote_row, dict) else None
                    ),
                    "option_ltp_source": final_option_ltp_source or None,
                    "quote_source": final_quote_source or None,
                    "quote_validation_status": resolve_quote_validation_status(
                        existing_status=(
                            final_quote_row.get("quote_validation_status")
                            if isinstance(final_quote_row, dict)
                            else getattr(updated_trade, "quote_validation_status", None)
                        ),
                        current_ltp=self._coerce_nonnegative_float(
                            final_quote_row.get("ltp") if isinstance(final_quote_row, dict) else None
                            or final_quote_row.get("last_price") if isinstance(final_quote_row, dict) else None
                            or getattr(updated_trade, "current_ltp", None)
                        ),
                        quote_age_sec=final_quote_age_sec,
                        best_bid=final_best_bid,
                        best_ask=final_best_ask,
                        max_quote_age_sec=getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0),
                    ),
                    "execution_entry": self._coerce_nonnegative_float(
                        final_quote_row.get("quote_execution_entry") if isinstance(final_quote_row, dict) else None
                        or final_quote_row.get("execution_entry") if isinstance(final_quote_row, dict) else None
                    ),
                    "execution_entry_status": str(
                        final_quote_row.get("execution_entry_status") if isinstance(final_quote_row, dict) else None
                        or ""
                    ).strip().lower()
                    or None,
                }
                final_flags["quote_truth"] = dict(final_quote_truth_snapshot)
                final_flags["quote_truth_snapshot"] = dict(final_quote_truth_snapshot)
                updated_trade = replace(updated_trade, source_flags=final_flags)
                for attr, value in (
                    ("quote_snapshot_id", final_quote_truth_snapshot.get("quote_snapshot_id")),
                    ("quote_ts_epoch", final_quote_truth_snapshot.get("quote_ts_epoch")),
                    ("quote_age_sec", final_quote_truth_snapshot.get("quote_age_sec")),
                    ("best_bid", final_quote_truth_snapshot.get("best_bid")),
                    ("best_ask", final_quote_truth_snapshot.get("best_ask")),
                    ("current_ltp", final_quote_truth_snapshot.get("current_ltp")),
                    ("option_ltp_source", final_quote_truth_snapshot.get("option_ltp_source")),
                    ("quote_source", final_quote_truth_snapshot.get("quote_source")),
                    ("quote_validation_status", final_quote_truth_snapshot.get("quote_validation_status")),
                    ("option_ltp_timestamp", final_quote_truth_snapshot.get("quote_ts_epoch")),
                    ("price_age_sec", final_quote_truth_snapshot.get("quote_age_sec")),
                    ("liquidity_score", final_quote_truth_snapshot.get("liquidity_score")),
                ):
                    try:
                        object.__setattr__(updated_trade, attr, value)
                    except Exception:
                        continue
            except Exception:
                pass
            return updated_trade
        except Exception:
            try:
                fallback_flags = dict(getattr(trade, "source_flags", {}) or {})
                quote_truth_snapshot = self._stamp_quote_truth_snapshot(
                    trade,
                    market_data=data,
                    source_flags=fallback_flags,
                    lifecycle=None,
                )
                fallback_flags = dict(getattr(trade, "source_flags", {}) or {})
                fallback_flags["quote_truth"] = dict(quote_truth_snapshot)
                fallback_flags["quote_truth_snapshot"] = dict(quote_truth_snapshot)
                candidate_status = str(getattr(trade, "candidate_status", None) or "").strip().lower()
                if not candidate_status:
                    decision_trace = dict(fallback_flags.get("decision_trace", {}) or {})
                    candidate_status = str(decision_trace.get("candidate_status") or "").strip().lower()
                if not candidate_status:
                    candidate_class = str(getattr(trade, "candidate_class", None) or fallback_flags.get("candidate_class") or "").strip().upper()
                    candidate_status = {
                        "EXECUTABLE": "executable",
                        "NEAR_EXECUTABLE": "near_executable",
                        "ADVISORY_ONLY": "advisory_only",
                        "BLOCKED": "blocked",
                        "BLOCKED_CONTRACT": "blocked_contract",
                    }.get(candidate_class, "")
                if not candidate_status:
                    candidate_status = "advisory_only"
                fallback_flags["candidate_status"] = candidate_status
                object.__setattr__(trade, "candidate_status", candidate_status)
                object.__setattr__(trade, "source_flags", fallback_flags)
            except Exception:
                pass
            return trade

    def _finalize_advisory_decision(
        self,
        *,
        trade: Trade,
        lifecycle: dict,
        decision_trace: dict,
    ) -> dict:
        execution_entry = lifecycle.get("execution_entry")
        execution_status = str(lifecycle.get("execution_entry_status") or "missing").strip().lower()
        display_entry = lifecycle.get("display_entry")
        display_status = str(lifecycle.get("display_entry_status") or "missing").strip().lower()
        entry_reason = lifecycle.get("entry_reason")
        entry_clear_reason = lifecycle.get("entry_clear_reason")
        preliminary_permission = str(
            decision_trace.get("preliminary_permission") or "ADVISORY_ONLY"
        ).strip().upper() or "ADVISORY_ONLY"
        preliminary_reason = str(
            decision_trace.get("preliminary_permission_reason") or "intent_blocked"
        ).strip() or "intent_blocked"
        exec_allowed = bool(
            decision_trace.get("preliminary_exec_allowed", getattr(trade, "execution_allowed", False))
        )

        if execution_entry is not None and execution_status == "executable":
            if exec_allowed:
                permission = "EXECUTE"
                final_action = "EXECUTE"
                permission_reason = preliminary_reason
            else:
                permission = preliminary_permission
                final_action = "QUEUE_ONLY"
                permission_reason = preliminary_reason
        elif display_entry is not None and display_status == "displayable":
            permission = "ADVISORY_ONLY"
            final_action = "ADVISORY_ONLY"
            permission_reason = str(entry_clear_reason or entry_reason or "missing_execution_entry")
            exec_allowed = False
        else:
            permission = "BLOCK"
            final_action = "BLOCK"
            permission_reason = str(entry_clear_reason or entry_reason or "missing_entry")
            exec_allowed = False

        entry_block_code = str(entry_clear_reason or "").strip().lower() or None
        entry_status = (
            "EXECUTABLE"
            if execution_status == "executable"
            else "DISPLAYABLE"
            if display_status == "displayable"
            else str(entry_clear_reason or "missing_entry").strip().upper()
        )
        return {
            "permission": permission,
            "permission_reason": permission_reason,
            "final_action": final_action,
            "display_entry_status": display_status,
            "execution_entry_status": execution_status,
            "entry_block_code": entry_block_code,
            "entry_status": entry_status,
            "entry_block_reason": str(entry_clear_reason or entry_reason or "missing_execution_entry"),
            "exec_allowed": exec_allowed,
        }

    def _stamp_quote_truth_snapshot(
        self,
        trade: Trade,
        *,
        market_data: dict | None,
        source_flags: dict | None,
        lifecycle: dict | None,
    ) -> dict:
        data = market_data if isinstance(market_data, dict) else {}
        flags = dict(source_flags or {})
        lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
        now_epoch = self._coerce_nonnegative_float(
            data.get("timestamp_epoch")
            or data.get("timestamp")
            or data.get("ts_epoch")
        )
        if now_epoch is None:
            now_epoch = float(now_utc_epoch())

        def _first_present(*values):
            for value in values:
                if value in (None, "", "None"):
                    continue
                return value
            return None

        quote_row = None
        option_chain = data.get("option_chain")
        if isinstance(option_chain, (list, tuple)):
            trade_token = self._coerce_nonnegative_float(getattr(trade, "instrument_token", None))
            trade_symbol = str(_first_present(getattr(trade, "tradingsymbol", None), data.get("tradingsymbol")) or "").strip()
            trade_strike = self._coerce_nonnegative_float(_first_present(getattr(trade, "strike", None), data.get("strike")))
            trade_right = str(
                _first_present(
                    getattr(trade, "right", None),
                    getattr(trade, "option_type", None),
                    data.get("right"),
                    data.get("option_type"),
                )
                or ""
            ).strip().upper()
            trade_expiry = str(
                _first_present(
                    getattr(trade, "expiry", None),
                    getattr(trade, "expiry_date", None),
                    data.get("expiry"),
                    data.get("expiry_date"),
                )
                or ""
            ).strip()
            for row in option_chain:
                if not isinstance(row, dict):
                    continue
                row_token = self._coerce_nonnegative_float(row.get("instrument_token"))
                row_symbol = str(row.get("tradingsymbol") or "").strip()
                row_strike = self._coerce_nonnegative_float(row.get("strike"))
                row_right = str(_first_present(row.get("right"), row.get("type"), row.get("option_type")) or "").strip().upper()
                row_expiry = str(_first_present(row.get("expiry"), row.get("expiry_date")) or "").strip()
                if trade_token is not None and row_token is not None and int(trade_token) == int(row_token):
                    quote_row = row
                    break
                if trade_symbol and row_symbol and trade_symbol == row_symbol:
                    quote_row = row
                    break
                if (
                    trade_strike is not None
                    and row_strike is not None
                    and trade_right
                    and row_right
                    and trade_expiry
                    and row_expiry
                    and float(trade_strike) == float(row_strike)
                    and trade_right == row_right
                    and trade_expiry == row_expiry
                ):
                    quote_row = row
                    break

        best_bid = self._coerce_nonnegative_float(
            _first_present(
                getattr(trade, "best_bid", None),
                getattr(trade, "opt_bid", None),
                data.get("best_bid"),
                data.get("bid"),
                data.get("opt_bid"),
                quote_row.get("best_bid") if isinstance(quote_row, dict) else None,
                quote_row.get("bid") if isinstance(quote_row, dict) else None,
            )
        )
        best_ask = self._coerce_nonnegative_float(
            _first_present(
                getattr(trade, "best_ask", None),
                getattr(trade, "opt_ask", None),
                data.get("best_ask"),
                data.get("ask"),
                data.get("opt_ask"),
                quote_row.get("best_ask") if isinstance(quote_row, dict) else None,
                quote_row.get("ask") if isinstance(quote_row, dict) else None,
            )
        )
        current_ltp = self._coerce_nonnegative_float(
            _first_present(
                getattr(trade, "opt_ltp", None),
                data.get("ltp"),
                data.get("last_price"),
                data.get("current_ltp"),
                getattr(trade, "current_ltp", None),
                data.get("mark_price"),
                quote_row.get("ltp") if isinstance(quote_row, dict) else None,
                quote_row.get("last_price") if isinstance(quote_row, dict) else None,
            )
        )
        quote_source = str(
            _first_present(
                getattr(trade, "quote_source", None),
                flags.get("quote_source"),
                quote_row.get("quote_source") if isinstance(quote_row, dict) else None,
                data.get("quote_source"),
                data.get("option_quote_source"),
            )
            or ""
        ).strip()
        if not quote_source:
            if best_bid is not None and best_ask is not None:
                quote_source = "live"
            elif _first_present(getattr(trade, "mark_price", None), data.get("mark_price")) is not None:
                quote_source = "mark"
            elif current_ltp is not None:
                quote_source = "last"
            else:
                quote_source = "unknown"
        option_ltp_source = str(
            _first_present(
                getattr(trade, "option_ltp_source", None),
                flags.get("option_ltp_source"),
                quote_row.get("option_ltp_source") if isinstance(quote_row, dict) else None,
                data.get("option_ltp_source"),
                data.get("option_quote_source"),
                quote_source,
            )
            or ""
        ).strip()
        if quote_row:
            current_ltp = self._coerce_nonnegative_float(
                _first_present(
                    quote_row.get("ltp"),
                    quote_row.get("last_price"),
                    current_ltp,
                )
            )
        quote_ts_epoch = self._coerce_nonnegative_float(
            _first_present(
                getattr(trade, "quote_ts_epoch", None),
                getattr(trade, "option_ltp_timestamp", None),
                flags.get("quote_ts_epoch"),
                flags.get("option_ltp_timestamp"),
                quote_row.get("quote_ts_epoch") if isinstance(quote_row, dict) else None,
                quote_row.get("quote_timestamp_epoch") if isinstance(quote_row, dict) else None,
                data.get("quote_ts_epoch"),
                data.get("quote_timestamp_epoch"),
            )
        )
        quote_age_sec = self._coerce_nonnegative_float(
            _first_present(
                getattr(trade, "quote_age_sec", None),
                getattr(trade, "price_age_sec", None),
                flags.get("quote_age_sec"),
                data.get("quote_age_sec"),
            )
        )
        if quote_ts_epoch is None and quote_age_sec is not None:
            quote_ts_epoch = max(0.0, float(now_epoch) - float(quote_age_sec))
        if quote_age_sec is None and quote_ts_epoch is not None:
            quote_age_sec = max(0.0, float(now_epoch) - float(quote_ts_epoch))

        quote_validation_status = resolve_quote_validation_status(
            existing_status=_first_present(
                flags.get("quote_validation_status"),
                getattr(trade, "quote_validation_status", None),
                lifecycle.get("entry_status"),
            ),
            current_ltp=current_ltp,
            quote_age_sec=quote_age_sec,
            best_bid=best_bid,
            best_ask=best_ask,
            max_quote_age_sec=getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0),
        )

        trade_id = str(_first_present(getattr(trade, "trade_id", None), data.get("trade_id")) or "")
        symbol = str(_first_present(getattr(trade, "symbol", None), data.get("symbol")) or "")
        quote_snapshot_id = str(
            _first_present(
                flags.get("quote_snapshot_id"),
                getattr(trade, "quote_snapshot_id", None),
            )
            or f"{trade_id}|{symbol}|{quote_ts_epoch if quote_ts_epoch is not None else 'na'}|{quote_source or 'unknown'}|{current_ltp if current_ltp is not None else 'na'}|{best_bid if best_bid is not None else 'na'}|{best_ask if best_ask is not None else 'na'}"
        ).strip()

        spread_pct = None
        try:
            mark = self._coerce_nonnegative_float(
                _first_present(
                    getattr(trade, "mark_price", None),
                    data.get("mark_price"),
                    current_ltp,
                )
            )
            spread_pct = self._coerce_nonnegative_float(
                _first_present(
                    getattr(trade, "spread_pct", None),
                    flags.get("spread_pct"),
                    data.get("spread_pct"),
                    quote_row.get("spread_pct") if isinstance(quote_row, dict) else None,
                )
            )
            if (
                spread_pct is None
                and best_bid is not None
                and best_ask is not None
                and mark is not None
                and float(mark) > 0
                and float(best_ask) >= float(best_bid) >= 0
            ):
                spread_pct = max(0.0, float(best_ask) - float(best_bid)) / max(float(mark), 1e-9)
        except Exception:
            spread_pct = None

        # (fallback stays None; LIVE strict gates will fail-closed)

        liquidity_score = self._coerce_nonnegative_float(
            _first_present(
                getattr(trade, "liquidity_score", None),
                flags.get("liquidity_score"),
                data.get("liquidity_score"),
                quote_row.get("liquidity_score") if isinstance(quote_row, dict) else None,
            )
        )

        snapshot = {
            "quote_snapshot_id": quote_snapshot_id,
            "quote_ts_epoch": quote_ts_epoch,
            "quote_age_sec": quote_age_sec,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_pct": spread_pct,
            "liquidity_score": liquidity_score,
            "current_ltp": current_ltp,
            "option_ltp_source": option_ltp_source or None,
            "quote_source": quote_source or None,
            "quote_validation_status": quote_validation_status or None,
            "execution_entry": _first_present(
                getattr(trade, "execution_entry", None),
                lifecycle.get("execution_entry"),
                flags.get("execution_entry"),
            ),
            "execution_entry_status": str(
                _first_present(
                    getattr(trade, "execution_entry_status", None),
                    lifecycle.get("execution_entry_status"),
                    flags.get("execution_entry_status"),
                )
                or ""
            ).strip().lower()
            or None,
        }
        snapshot = {key: value for key, value in snapshot.items() if value not in (None, "", "None")}
        flags["quote_truth"] = dict(snapshot)
        flags["quote_truth_snapshot"] = dict(snapshot)
        for attr in (
            "quote_snapshot_id",
            "quote_ts_epoch",
            "quote_age_sec",
            "best_bid",
            "best_ask",
            "current_ltp",
            "option_ltp_source",
            "option_ltp_timestamp",
            "price_age_sec",
            "quote_source",
            "quote_validation_status",
            "liquidity_score",
            "source_flags",
        ):
            value = snapshot.get(attr) if attr in snapshot else flags if attr == "source_flags" else None
            if attr == "source_flags":
                value = flags
            elif attr == "option_ltp_timestamp" and snapshot.get("quote_ts_epoch") is not None:
                value = snapshot.get("quote_ts_epoch")
            elif attr == "price_age_sec" and snapshot.get("quote_age_sec") is not None:
                value = snapshot.get("quote_age_sec")
            elif value is None and attr in snapshot:
                value = snapshot.get(attr)
            try:
                object.__setattr__(trade, attr, value)
            except Exception:
                continue
        existing_truth = None
        if isinstance(flags, dict):
            existing_truth = flags.get("quote_truth") or flags.get("quote_truth_snapshot")
        if isinstance(existing_truth, dict):
            existing_ts = self._coerce_nonnegative_float(existing_truth.get("quote_ts_epoch"))
            new_ts = self._coerce_nonnegative_float(snapshot.get("quote_ts_epoch"))
            if new_ts is None or (existing_ts is not None and new_ts <= existing_ts):
                chosen_snapshot = dict(existing_truth)
            else:
                chosen_snapshot = dict(snapshot)
        else:
            chosen_snapshot = dict(snapshot)
        flags["quote_truth"] = dict(chosen_snapshot)
        flags["quote_truth_snapshot"] = dict(chosen_snapshot)
        try:
            object.__setattr__(trade, "source_flags", flags)
        except Exception:
            pass
        return chosen_snapshot

    def _build_trade_entry_lifecycle(
        self,
        trade: Trade,
        *,
        market_data: dict | None,
        instrument_matches: bool,
    ) -> dict:
        data = market_data if isinstance(market_data, dict) else {}
        source_flags = dict(getattr(trade, "source_flags", {}) or {})
        ctx_payload = dict(data.get("market_context") or {}) if isinstance(data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = getattr(cfg, "EXECUTION_MODE", "SIM")
        if "market_open" not in ctx_payload:
            ctx_payload["market_open"] = data.get("market_open", True)
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        market_ctx = derive_market_context(ctx_payload)

        best_bid = getattr(trade, "best_bid", None)
        if best_bid is None:
            best_bid = getattr(trade, "opt_bid", None)
        best_ask = getattr(trade, "best_ask", None)
        if best_ask is None:
            best_ask = getattr(trade, "opt_ask", None)
        mark_price = getattr(trade, "mark_price", None)
        if mark_price is None:
            mark_price = source_flags.get("mark_price")
        mid_price = source_flags.get("mid_price")
        if mid_price is None and best_bid is not None and best_ask is not None:
            try:
                mid_price = (float(best_bid) + float(best_ask)) / 2.0
            except Exception:
                mid_price = None
        last_price = getattr(trade, "current_ltp", None)
        if last_price is None:
            last_price = getattr(trade, "opt_ltp", None)
        if last_price is None:
            last_price = data.get("current_ltp")
        if last_price is None:
            last_price = data.get("ltp")

        quote_source = (
            getattr(trade, "option_ltp_source", None)
            or source_flags.get("option_ltp_source")
            or getattr(trade, "price_source", None)
            or source_flags.get("price_source")
            or data.get("option_ltp_source")
            or data.get("quote_source")
            or data.get("ltp_source")
        )
        if not quote_source:
            if best_bid is not None and best_ask is not None:
                quote_source = "live"
            elif mark_price is not None:
                quote_source = "mark"
            elif mid_price is not None:
                quote_source = "mid"
            elif last_price is not None:
                quote_source = "last"
            else:
                quote_source = "none"

        try:
            decorated = build_entry_state(
                symbol=getattr(trade, "symbol", None),
                expiry=getattr(trade, "expiry_date", None) or getattr(trade, "expiry", None),
                strike=getattr(trade, "strike", None),
                right=getattr(trade, "right", None) or getattr(trade, "option_type", None),
                side=getattr(trade, "side", None),
                direction=getattr(trade, "direction", None),
                bid=best_bid,
                ask=best_ask,
                mark=mark_price,
                mid=mid_price,
                last=last_price,
                quote_age_sec=getattr(trade, "quote_age_sec", None),
                mode=market_ctx.mode,
                allow_stale_quotes=bool(market_ctx.allow_stale_quotes),
                market_open=bool(market_ctx.is_market_open),
                instrument_matches=bool(instrument_matches),
                quote_source=quote_source,
                allow_last_execution=should_allow_last_execution_fallback(
                    {
                        "entry": getattr(trade, "entry", None) or getattr(trade, "entry_price", None),
                        "current_ltp": last_price,
                        "option_ltp_source": getattr(trade, "option_ltp_source", None) or quote_source,
                        "quote_source": getattr(trade, "quote_source", None) or quote_source,
                    }
                ),
            )
            decorated_execution_allowed = (
                decorated.get("execution_allowed")
                if isinstance(decorated, dict)
                else getattr(decorated, "execution_allowed", False)
            )
            decorated_execution_status = str(
                decorated.get("execution_entry_status")
                if isinstance(decorated, dict)
                else getattr(decorated, "execution_entry_status", "")
            ).strip().lower()
            decorated_entry_block_reason = str(
                decorated.get("entry_block_reason")
                if isinstance(decorated, dict)
                else getattr(decorated, "entry_block_reason", "")
            ).strip()
            is_executable_entry = decorated_execution_status == "executable" and not decorated_entry_block_reason
            if is_executable_entry and not bool(decorated_execution_allowed):
                if isinstance(decorated, dict):
                    decorated["execution_allowed"] = True
                else:
                    decorated = replace(decorated, execution_allowed=True)
            return decorated
        except EntryContractViolation as exc:
            logger.warning(
                "trade_entry_lifecycle_invalid trade_id=%s symbol=%s code=%s err=%s",
                getattr(trade, "trade_id", None),
                getattr(trade, "symbol", None),
                exc.code,
                exc.message,
            )
            return {
                "execution_entry": None,
                "execution_entry_source": "none",
                "execution_entry_status": "missing",
                "display_entry": None,
                "display_entry_source": "none",
                "display_entry_status": "missing",
                "entry_reason": None,
                "entry_clear_reason": str(exc.code or "entry_contract_invalid").lower(),
                "entry": None,
                "entry_status": "missing",
                "entry_source": "none",
            }

    def _blocked_candidates_path(self) -> Path:
        desk_log_dir = getattr(cfg, "DESK_LOG_DIR", None)
        if desk_log_dir:
            return Path(str(desk_log_dir)) / "blocked_candidates.jsonl"
        desk = getattr(cfg, "DESK_ID", "DEFAULT")
        return logs_dir() / f"desks/{desk}/blocked_candidates.jsonl"

    def _log_precondition_reject(
        self,
        symbol: str,
        reason_code: str,
        reason_text: str,
        market_data: dict | None = None,
        extra: dict | None = None,
    ) -> None:
        data = market_data or {}
        meta = extra if isinstance(extra, dict) else {}
        ts_epoch = float(now_utc_epoch())
        reason_codes = list(meta.get("reason_codes") or [])
        if not reason_codes:
            reason_codes = [str(reason_code)]
        gate_name = str(meta.get("gate_name") or "option_tradability_precondition")
        direction = (
            meta.get("direction")
            or (self._reject_ctx.get("direction") if isinstance(self._reject_ctx, dict) else None)
            or data.get("direction")
        )
        strike = meta.get("strike")
        option_type = meta.get("option_type") or meta.get("type")
        quote_source = meta.get("quote_source") or data.get("quote_source") or data.get("index_quote_source")
        option_ltp_source = (
            meta.get("option_ltp_source")
            or data.get("option_ltp_source")
            or quote_source
        )
        try:
            append_reject_telemetry(
                {
                    "candidate_key": meta.get("candidate_id") or meta.get("trade_id"),
                    "snapshot_id": meta.get("snapshot_id"),
                    "timestamp_epoch_ms": int(ts_epoch * 1000.0),
                    "symbol": symbol,
                    "strike": strike if strike is not None else data.get("strike"),
                    "trade_side": direction,
                    "reject_reason": str(reason_code),
                    "rejection_reasons": [str(x) for x in reason_codes if str(x)],
                    "quote_age_sec": meta.get("quote_age_sec", data.get("quote_age_sec")),
                    "spread_pct": meta.get("spread_pct", data.get("spread_pct")),
                    "feed_state": (
                        meta.get("feed_state")
                        or data.get("feed_state")
                        or (data.get("feed_health_snapshot") or {}).get("state")
                    ),
                    "entry_price": meta.get("entry_price") or meta.get("option_ltp") or data.get("ltp"),
                    "instrument_token": meta.get("instrument_token"),
                    "horizon_minutes": int(getattr(cfg, "REJECT_SHADOW_HORIZON_MIN", 30)),
                    "gate_name": gate_name,
                    "reason": str(reason_text),
                    "quote_source": quote_source,
                    "option_ltp_source": option_ltp_source,
                }
            )
        except Exception:
            pass
        append_reject_reasons(
            symbol=symbol,
            strategy=str(meta.get("strategy")) if meta.get("strategy") is not None else None,
            reasons=[str(x) for x in reason_codes if str(x)],
            mode=(data.get("market_context") or {}).get("mode") if isinstance(data.get("market_context"), dict) else getattr(cfg, "EXECUTION_MODE", "SIM"),
            source="trade_builder_precondition",
            extra={
                "reason_text": reason_text,
                "quote_source": quote_source,
                "option_ltp_source": option_ltp_source,
                "gate_name": gate_name,
            },
        )

    def _log_blocked_candidate(
        self,
        symbol: str,
        reason_code: str,
        reason_text: str,
        market_data: dict | None = None,
        extra: dict | None = None,
    ) -> None:
        data = market_data or {}
        meta = extra if isinstance(extra, dict) else {}
        try:
            code = str(reason_code or "").strip()
            if code:
                self._scan_reject_counts[code] = int(self._scan_reject_counts.get(code, 0)) + 1
        except Exception:
            pass
        ts_epoch = float(now_utc_epoch())
        reason_codes = list(meta.get("reason_codes") or [])
        if not reason_codes:
            reason_codes = [str(reason_code)]
        gate_name = str(meta.get("gate_name") or reason_code or "trade_builder_gate")
        direction = (
            meta.get("direction")
            or (self._reject_ctx.get("direction") if isinstance(self._reject_ctx, dict) else None)
            or data.get("direction")
        )
        strike = meta.get("strike")
        option_type = meta.get("option_type") or meta.get("type")
        instrument_id = meta.get("instrument_id") or data.get("instrument_id")
        instrument_token = meta.get("instrument_token")
        expiry = meta.get("expiry")
        contract = meta.get("contract")
        if not contract and symbol and strike is not None and option_type:
            contract = f"{symbol}|{expiry or ''}|{strike}|{option_type}"
        entry = meta.get("entry")
        if entry is None:
            entry = meta.get("entry_price")
        if entry is None:
            entry = meta.get("option_ltp")
        if entry is None:
            entry = data.get("ltp")
        stop = meta.get("stop")
        if stop is None:
            stop = meta.get("stop_loss")
        target = meta.get("target")
        derived_levels = False
        stop = None
        target = None
        horizons = list(meta.get("horizon_sec") or meta.get("horizons_sec") or [])
        if not horizons:
            raw_horizons = getattr(cfg, "SHADOW_EVAL_HORIZONS_SEC", [300, 900, 1800])
            if isinstance(raw_horizons, (list, tuple)):
                for item in raw_horizons:
                    try:
                        val = int(item)
                    except Exception:
                        continue
                    if val > 0:
                        horizons.append(val)
        if not horizons:
            horizons = [300, 900, 1800]
        key = "|".join(
            [
                str(symbol or ""),
                str(reason_code or ""),
                str(direction or ""),
                str(strike or ""),
                str(option_type or ""),
                str(int(ts_epoch * 1000)),
            ]
        )
        candidate_id = (
            meta.get("candidate_id")
            or meta.get("blocked_id")
            or meta.get("trade_id")
            or f"blk_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:18]}"
        )
        rec = {
            "candidate_id": str(candidate_id),
            "blocked_id": str(candidate_id),
            "timestamp_epoch": ts_epoch,
            "timestamp_ist": now_ist().isoformat(),
            "ts_ist": now_ist().isoformat(),
            "ts_epoch": ts_epoch,
            "symbol": symbol,
            "stage": "trade_builder",
            "reason_code": str(reason_code),
            "reason_codes": [str(x) for x in reason_codes if str(x)],
            "reason_text": str(reason_text),
            "reason": str(reason_text),
            "gate_name": gate_name,
            "direction": direction,
            "row_kind": BLOCKED_DEBUG_ROW_KIND,
            "entry": entry,
            "stop": stop,
            "stop_loss": stop,
            "target": target,
            "instrument_id": instrument_id,
            "instrument_token": instrument_token,
            "expiry_date": meta.get("expiry_date") or meta.get("expiry") or data.get("expiry_date") or data.get("expiry"),
            "tradingsymbol": meta.get("tradingsymbol") or data.get("tradingsymbol"),
            "underlying_spot": meta.get("underlying_spot") or data.get("ltp"),
            "spot_source": meta.get("spot_source") or data.get("ltp_source") or data.get("index_quote_source"),
            "option_ltp_source": (
                meta.get("option_ltp_source")
                or data.get("option_ltp_source")
                or data.get("quote_source")
                or data.get("index_quote_source")
            ),
            "chain_source": meta.get("chain_source") or data.get("chain_source"),
            "contract": contract,
            "horizon_sec": horizons,
            "derived_levels": bool(derived_levels),
            "non_canonical_levels": True,
            "levels_recomputed_from_final_entry": False,
            "level_recompute_reason": "blocked_debug_row",
            "ltp": data.get("ltp"),
            "vwap": data.get("vwap"),
            "atr": data.get("atr"),
            "primary_regime": data.get("primary_regime") or data.get("regime_day") or data.get("regime"),
            "quote_ok": data.get("quote_ok"),
            "quote_source": data.get("quote_source") or data.get("index_quote_source") or data.get("ltp_source"),
        }
        if extra:
            rec.update(extra)
        try:
            append_trade_lifecycle_event(
                trade_id=str(rec.get("candidate_id") or ""),
                symbol=str(symbol or ""),
                strategy=str(meta.get("strategy") or data.get("strategy") or ""),
                stage="candidate_generation",
                status="blocked",
                reason=str(reason_code),
                timestamp=datetime.now(timezone.utc).isoformat(),
                extra={
                    "entry": rec.get("entry"),
                    "display_entry": rec.get("entry"),
                    "entry_block_code": str(reason_code),
                    "gate_name": gate_name,
                },
            )
        except Exception:
            pass
        try:
            append_reject_telemetry(
                {
                    "candidate_key": rec.get("candidate_id"),
                    "snapshot_id": meta.get("snapshot_id") if isinstance(meta, dict) else None,
                    "timestamp_epoch_ms": int(ts_epoch * 1000.0),
                    "symbol": symbol,
                    "strike": strike if strike is not None else data.get("strike"),
                    "trade_side": direction,
                    "reject_reason": str(reason_code),
                    "rejection_reasons": [str(x) for x in reason_codes if str(x)],
                    "quote_age_sec": meta.get("quote_age_sec", data.get("quote_age_sec")),
                    "spread_pct": meta.get("spread_pct", data.get("spread_pct")),
                    "feed_state": (
                        meta.get("feed_state")
                        or data.get("feed_state")
                        or (data.get("feed_health_snapshot") or {}).get("state")
                    ),
                    "entry_price": rec.get("entry"),
                    "instrument_token": rec.get("instrument_token"),
                    "horizon_minutes": int(getattr(cfg, "REJECT_SHADOW_HORIZON_MIN", 30)),
                    "gate_name": gate_name,
                    "reason": str(reason_text),
                    "quote_source": rec.get("quote_source"),
                    "option_ltp_source": rec.get("option_ltp_source"),
                }
            )
        except Exception:
            pass
        try:
            path = self._blocked_candidates_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=True) + "\n")
        except Exception:
            pass
        strategy_name = None
        if isinstance(extra, dict):
            raw_strategy = extra.get("strategy")
            if raw_strategy is not None:
                strategy_name = str(raw_strategy)
        append_reject_reasons(
            symbol=symbol,
            strategy=strategy_name,
            reasons=[str(x) for x in reason_codes if str(x)],
            mode=(data.get("market_context") or {}).get("mode") if isinstance(data.get("market_context"), dict) else getattr(cfg, "EXECUTION_MODE", "SIM"),
            source="trade_builder",
            extra={
                "reason_text": reason_text,
                "quote_source": rec.get("quote_source"),
                "stage": rec.get("stage"),
            },
        )
        try:
            mode = (data.get("market_context") or {}).get("mode") if isinstance(data.get("market_context"), dict) else getattr(cfg, "EXECUTION_MODE", "SIM")
            confidence_val = None
            if isinstance(meta, dict):
                try:
                    confidence_val = float(meta.get("confidence")) if meta.get("confidence") is not None else None
                except Exception:
                    confidence_val = None
            soft_vetos = []
            if isinstance(meta, dict):
                raw_soft = meta.get("soft_veto_codes")
                if isinstance(raw_soft, (list, tuple)):
                    soft_vetos = [str(x) for x in raw_soft if str(x)]
            rec_sf = dict(rec.get("source_flags", {}) or {}) if isinstance(rec, dict) else {}
            rec_trace = dict(meta.get("decision_trace", {}) or {}) if isinstance(meta, dict) else {}
            setup_telemetry_fields = self._setup_telemetry_fields(
                rec,
                rec_sf,
                rec_trace,
                candidate_quality_score=(meta.get("final_score") if isinstance(meta, dict) else None),
            )
            record_candidate_decision(
                {
                    "candidate_id": rec.get("candidate_id"),
                    "ts_epoch": rec.get("timestamp_epoch"),
                    "symbol": symbol,
                    "side": rec.get("direction") or "BUY_CALL",
                    "entry": rec.get("entry"),
                    "stop": rec.get("stop"),
                    "target": rec.get("target"),
                    "regime": rec.get("primary_regime"),
                    "confidence_score": confidence_val,
                    "gates_failed": [str(x) for x in reason_codes if str(x)],
                    "soft_vetos": soft_vetos,
                    "first_blocking_gate": str(reason_code),
                    "hard_reject_reason": str(reason_code),
                    "execution_allowed": False,
                    "mode": mode,
                    "instrument_id": rec.get("instrument_id"),
                    "expiry": rec.get("expiry"),
                    "ltp": rec.get("ltp"),
                    "atr": rec.get("atr"),
                    "initial_score": meta.get("initial_score") if isinstance(meta, dict) else None,
                    "final_score": meta.get("final_score") if isinstance(meta, dict) else None,
                    "score_penalties": meta.get("score_penalties") if isinstance(meta, dict) else [],
                    "signal_score": meta.get("signal_score") if isinstance(meta, dict) else None,
                    "regime_conf": meta.get("regime_conf") if isinstance(meta, dict) else None,
                    "orb_bias": meta.get("orb_bias") if isinstance(meta, dict) else data.get("orb_bias"),
                    "orb_factor": meta.get("orb_factor") if isinstance(meta, dict) else None,
                    "reg_penalty": meta.get("reg_penalty") if isinstance(meta, dict) else None,
                    "global_conf": meta.get("global_conf") if isinstance(meta, dict) else None,
                    "liquidity_score": rec.get("liquidity_score"),
                    "quote_consistency_score": rec.get("quote_consistency_score"),
                    "quote_validation_status": rec.get("quote_validation_status"),
                    "liquidity_flow_score": self._candidate_telemetry_field(rec, rec_sf, rec_trace, "liquidity_flow_score"),
                    "liquidity_book_score": self._candidate_telemetry_field(rec, rec_sf, rec_trace, "liquidity_book_score"),
                    "liquidity_spread_score": self._candidate_telemetry_field(rec, rec_sf, rec_trace, "liquidity_spread_score"),
                    "liquidity_volume_score": self._candidate_telemetry_field(rec, rec_sf, rec_trace, "liquidity_volume_score"),
                    "liquidity_oi_score": self._candidate_telemetry_field(rec, rec_sf, rec_trace, "liquidity_oi_score"),
                    **setup_telemetry_fields,
                    "rank_score": rec.get("rank_score"),
                    "raw_rank_score": rec.get("raw_rank_score"),
                    "terminal_rank_score": rec.get("terminal_rank_score"),
                    "opportunity_score": rec.get("opportunity_score"),
                    "permission": meta.get("permission") if isinstance(meta, dict) else "ADVISORY_ONLY",
                    "permission_reason": meta.get("permission_reason") if isinstance(meta, dict) else str(reason_code),
                    "entry_status": meta.get("entry_status") if isinstance(meta, dict) else "INTENT_BLOCKED",
                    "entry_block_reason": meta.get("entry_block_reason") if isinstance(meta, dict) else str(reason_code),
                    "final_action": meta.get("final_action") if isinstance(meta, dict) else "ADVISORY_ONLY",
                }
            )
        except Exception:
            pass

    def _identity_fields(self, symbol, instrument, expiry, strike, right, qty_lots):
        instrument_type = instrument
        if instrument_type == "EQ":
            instrument_type = "INDEX"
        instrument_type = instrument_type.upper() if instrument_type else None
        ok, reason = validate_trade_identity(symbol, instrument_type, expiry, strike, right)
        if not ok:
            self._reject_ctx = {
                "symbol": symbol,
                "reason": "missing_contract_fields",
                "detail": reason,
                "instrument_type": instrument_type,
                "expiry": expiry,
                "strike": strike,
                "right": right,
            }
            return None, None, None, reason
        instrument_id = build_instrument_id(symbol, instrument_type, expiry, strike, right)
        if not instrument_id:
            self._reject_ctx = {
                "symbol": symbol,
                "reason": "missing_instrument_id",
                "instrument_type": instrument_type,
                "expiry": expiry,
                "strike": strike,
                "right": right,
            }
            return None, None, None, "missing_instrument_id"
        lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(symbol, 1))
        qty_units = int(qty_lots) * (lot_size if instrument_type == "OPT" else 1)
        return instrument_type, instrument_id, qty_units, None

    def _option_identity_complete(
        self,
        *,
        instrument: str | None,
        instrument_type: str | None,
        right: str | None,
        expiry: str | None,
        tradingsymbol,
        instrument_token,
        instrument_id,
    ) -> tuple[bool, list[str]]:
        if str(instrument or "").upper() != "OPT":
            return True, []
        missing_fields: list[str] = []
        if str(instrument_type or "").upper() != "OPT":
            missing_fields.append("instrument_type")
        if str(right or "").upper() not in {"CE", "PE"}:
            missing_fields.append("right")
        if not str(expiry or "").strip():
            missing_fields.append("expiry")
        if not str(tradingsymbol or "").strip():
            missing_fields.append("tradingsymbol")
        try:
            token_int = int(instrument_token) if instrument_token is not None else None
        except Exception:
            token_int = None
        if token_int is None:
            missing_fields.append("instrument_token")
        if not str(instrument_id or "").strip():
            missing_fields.append("instrument_id")
        return (len(missing_fields) == 0), missing_fields

    def _option_liquidity_fields(self, opt) -> dict:
        if not isinstance(opt, dict):
            return {}
        volume = opt.get("volume")
        return {
            "volume": volume,
            "current_volume": opt.get("current_volume", volume),
            "oi": opt.get("oi"),
            "oi_change": opt.get("oi_change"),
        }

    def _hydrate_option_liquidity(self, opt):
        if not isinstance(opt, dict):
            return opt
        hydrated = hydrate_option_liquidity_fields(
            opt,
            symbol=opt.get("symbol"),
            expiry=opt.get("expiry") or opt.get("expiry_date") or opt.get("expiryDate") or opt.get("exp"),
            strike=opt.get("strike") or opt.get("strike_price") or opt.get("strikePrice"),
            option_type=opt.get("type") or opt.get("option_type") or opt.get("right") or opt.get("instrument_type"),
            now_epoch=now_utc_epoch(),
        )
        if hydrated.get("current_volume") is None and hydrated.get("volume") is not None:
            hydrated["current_volume"] = hydrated.get("volume")
        return hydrated

    def _coerce_positive_float(self, value):
        try:
            out = float(value)
        except Exception:
            return None
        if out <= 0:
            return None
        return out

    def _coerce_option_type(self, value):
        text = str(value or "").strip().upper()
        if not text:
            return None
        alias = {
            "CALL": "CE",
            "PUT": "PE",
            "C": "CE",
            "P": "PE",
        }
        text = alias.get(text, text)
        if text in {"CE", "PE"}:
            return text
        return None

    def _extract_depth_price(self, opt: dict, side: str):
        if side == "bid":
            candidates = ("bid", "best_bid", "bid_price")
            depth_keys = ("buy", "bid")
        else:
            candidates = ("ask", "best_ask", "ask_price")
            depth_keys = ("sell", "ask")
        for key in candidates:
            px = self._coerce_positive_float(opt.get(key))
            if px is not None:
                return px
        depth = opt.get("depth")
        if isinstance(depth, dict):
            for key in depth_keys:
                book = depth.get(key)
                if isinstance(book, list) and book:
                    top = book[0]
                    if isinstance(top, dict):
                        px = self._coerce_positive_float(top.get("price") or top.get("px"))
                        if px is not None:
                            return px
                elif isinstance(book, dict):
                    px = self._coerce_positive_float(book.get("price") or book.get("px"))
                    if px is not None:
                        return px
        return None

    def _derive_option_price_fields(self, opt: dict):
        provided_mark = self._coerce_positive_float(opt.get("mark_price"))
        provided_source = str(opt.get("price_source") or "").strip().lower()
        last_price = (
            self._coerce_positive_float(opt.get("last_price"))
            or self._coerce_positive_float(opt.get("ltp"))
            or self._coerce_positive_float(opt.get("close"))
            or self._coerce_positive_float(opt.get("price"))
        )
        best_bid = self._extract_depth_price(opt, "bid")
        best_ask = self._extract_depth_price(opt, "ask")
        mid_price = None
        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
        quote_age = opt.get("quote_age_sec")
        stale_quote = False
        try:
            stale_quote = quote_age is None or float(quote_age) > float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8))
        except Exception:
            stale_quote = quote_age is None
        outside_tol = float(getattr(cfg, "OPTION_LAST_OUTSIDE_BAND_PCT", 0.01))
        outside_band = False
        if last_price is not None and best_bid is not None and best_ask is not None:
            lo = min(best_bid, best_ask) * max(0.0, 1.0 - outside_tol)
            hi = max(best_bid, best_ask) * (1.0 + outside_tol)
            outside_band = bool(last_price < lo or last_price > hi)
        if provided_mark is not None:
            mark_price = provided_mark
            price_source = provided_source or "mark"
        elif mid_price is not None and (outside_band or stale_quote or last_price is None):
            mark_price = mid_price
            price_source = "mid"
        elif last_price is not None:
            mark_price = last_price
            price_source = "last"
        elif best_ask is not None:
            mark_price = best_ask
            price_source = "ask"
        elif best_bid is not None:
            mark_price = best_bid
            price_source = "bid"
        elif mid_price is not None:
            mark_price = mid_price
            price_source = "mid"
        else:
            mark_price = None
            price_source = "none"
        entry_buy = best_ask if best_ask is not None else mark_price
        entry_sell = best_bid if best_bid is not None else mark_price
        spread_pct = None
        if mark_price and mark_price > 0 and best_bid is not None and best_ask is not None:
            spread_pct = (best_ask - best_bid) / mark_price
        return {
            "last_price": last_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "mark_price": mark_price,
            "price_source": price_source,
            "entry_price_proxy_buy": entry_buy,
            "entry_price_proxy_sell": entry_sell,
            "spread_pct": spread_pct,
        }

    def _entry_price_proxy(self, opt: dict, side: str = "BUY"):
        price, _ = self._option_executable_price(opt, side=side)
        return price

    def _option_executable_price(self, opt: dict, side: str = "BUY") -> tuple[float | None, str | None]:
        if not isinstance(opt, dict):
            return None, None
        side_val = str(side or "BUY").upper()
        if side_val == "SELL":
            bid = self._coerce_positive_float(opt.get("best_bid")) or self._coerce_positive_float(opt.get("bid"))
            if bid is not None:
                return bid, "bid"
        else:
            ask = self._coerce_positive_float(opt.get("best_ask")) or self._coerce_positive_float(opt.get("ask"))
            if ask is not None:
                return ask, "ask"
        mark_price = self._coerce_positive_float(opt.get("mark_price"))
        if mark_price is not None:
            return mark_price, "mark_price"
        ltp = (
            self._coerce_positive_float(opt.get("ltp"))
            or self._coerce_positive_float(opt.get("last_price"))
        )
        if ltp is not None:
            return ltp, "ltp"
        return None, None

    def _option_signal_price(self, opt: dict, market_data: dict | None = None) -> float | None:
        if isinstance(opt, dict):
            signal_price = self._coerce_positive_float(opt.get("signal_price"))
            if signal_price is not None:
                return signal_price
        if isinstance(market_data, dict):
            return self._coerce_positive_float(market_data.get("signal_price"))
        return None

    def _normalize_option_row(self, opt_raw, expected_type: str):
        if not isinstance(opt_raw, dict):
            return None, "malformed_option_row"
        opt = dict(opt_raw)
        opt_side = (
            self._coerce_option_type(opt.get("type"))
            or self._coerce_option_type(opt.get("option_type"))
            or self._coerce_option_type(opt.get("right"))
            or self._coerce_option_type(opt.get("instrument_type"))
        )
        expected = str(expected_type or "").upper()
        if opt_side is None and expected in {"CE", "PE"}:
            opt_side = expected
            opt["type_inferred"] = True
            opt["type_inferred_source"] = "expected_type"
        if opt_side != expected:
            allow_soften = bool(getattr(cfg, "ALLOW_OPTION_TYPE_MISMATCH_SOFTEN", True))
            hard_reject = bool(getattr(cfg, "OPTION_TYPE_MISMATCH_HARD_REJECT", False))
            if expected in {"CE", "PE"} and (allow_soften or not hard_reject):
                opt_side = expected
                opt["type_inferred"] = True
                opt["type_inferred_source"] = "type_mismatch_soft"
                opt["type_mismatch_soft"] = True
            else:
                return None, "type_mismatch"
        strike = (
            self._coerce_positive_float(opt.get("strike"))
            or self._coerce_positive_float(opt.get("strike_price"))
            or self._coerce_positive_float(opt.get("strikePrice"))
        )
        if strike is None:
            return None, "missing_strike"
        opt["type"] = opt_side
        opt["strike"] = strike
        price_fields = self._derive_option_price_fields(opt)
        opt["last_price"] = price_fields.get("last_price")
        opt["best_bid"] = price_fields.get("best_bid")
        opt["best_ask"] = price_fields.get("best_ask")
        opt["mid_price"] = price_fields.get("mid_price")
        opt["mark_price"] = price_fields.get("mark_price")
        opt["price_source"] = price_fields.get("price_source")
        opt["entry_price_proxy_buy"] = price_fields.get("entry_price_proxy_buy")
        opt["entry_price_proxy_sell"] = price_fields.get("entry_price_proxy_sell")
        opt["ltp"] = (
            self._coerce_positive_float(opt.get("ltp"))
            or self._coerce_positive_float(opt.get("last_price"))
            or self._coerce_positive_float(opt.get("mark_price"))
            or self._coerce_positive_float(opt.get("close"))
            or self._coerce_positive_float(opt.get("price"))
        )
        opt["bid"] = self._coerce_positive_float(opt.get("best_bid")) or self._extract_depth_price(opt, "bid")
        opt["ask"] = self._coerce_positive_float(opt.get("best_ask")) or self._extract_depth_price(opt, "ask")
        if opt.get("spread_pct") is None:
            opt["spread_pct"] = price_fields.get("spread_pct")
        if opt.get("quote_ts_epoch") is None:
            qts = opt.get("quote_timestamp_epoch")
            if qts is None:
                qts = opt.get("ts_epoch")
            try:
                opt["quote_ts_epoch"] = float(qts) if qts is not None else None
            except Exception:
                opt["quote_ts_epoch"] = None
        if opt.get("quote_ok") is None:
            opt["quote_ok"] = bool(
                opt["ltp"] is not None
                and opt["bid"] is not None
                and opt["ask"] is not None
                and opt["ask"] >= opt["bid"]
            )
        if opt.get("depth_ok") is None:
            opt["depth_ok"] = bool(
                opt["bid"] is not None
                and opt["ask"] is not None
                and opt["ask"] >= opt["bid"]
            )
        expiry = (
            opt.get("expiry")
            or opt.get("expiry_date")
            or opt.get("expiryDate")
            or opt.get("exp")
        )
        if expiry is not None:
            exp_text = str(expiry).strip()
            if exp_text and exp_text.upper() not in {"NONE", "NA", "N/A", "NAN"}:
                opt["expiry"] = exp_text
        opt = self._hydrate_option_liquidity(opt)
        return opt, None

    def _validate_required_option_quote_fields(
        self,
        opt: dict,
        *,
        allow_missing_bid_ask: bool = False,
    ) -> tuple[bool, str | None]:
        if not isinstance(opt, dict):
            return False, "malformed_option_row"
        ltp = self._coerce_positive_float(opt.get("ltp"))
        bid = self._coerce_positive_float(opt.get("bid"))
        ask = self._coerce_positive_float(opt.get("ask"))
        if ltp is None:
            return False, "invalid_option_ltp"
        if bid is None or ask is None:
            if allow_missing_bid_ask:
                return True, None
            return False, "no_quote"
        if ask < bid:
            return False, "no_bid_ask"
        return True, None

    def _coerce_nonnegative_float(self, value):
        try:
            if value is None:
                return None
            val = float(value)
            return val if val >= 0 else None
        except Exception:
            return None

    def _allow_non_live_stale_option_tick_advisory(self, market_ctx) -> bool:
        return bool(
            getattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", True)
            and getattr(market_ctx, "allow_stale_quotes", False)
        )

    def _allow_stale_option_tick_bypass(
        self,
        market_ctx,
        *,
        market_mode: str,
        quote_age_sec: float | None,
    ) -> bool:
        if not bool(getattr(cfg, "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ENABLE", False)):
            return False
        mode = str(market_mode or "").strip().upper()
        allow_live = bool(getattr(cfg, "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ALLOW_LIVE", False))
        if mode == "LIVE" and not allow_live:
            return False
        if quote_age_sec is None:
            return False
        max_age = float(getattr(cfg, "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_MAX_SEC", 20.0) or 20.0)
        return float(max_age) <= 0 or float(quote_age_sec) <= float(max_age)

    def _option_scan_min_survivor_modes(self) -> set[str]:
        raw = str(getattr(cfg, "OPTION_SCAN_MIN_SURVIVORS_ALLOWED_MODES", "SIM,PAPER,OFFHOURS") or "")
        return {item.strip().upper() for item in raw.split(",") if item.strip()}

    def _inject_option_scan_min_survivors(
        self,
        *,
        symbol: str,
        market_data: dict,
        execution_mode: str,
        candidates: list,
        rejected: list[dict],
        strategy_tag: str | None,
        direction: str,
    ) -> list:
        if candidates:
            return candidates
        if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
            return candidates
        if not bool(getattr(cfg, "OPTION_SCAN_MIN_SURVIVORS_ENABLE", False)):
            return candidates
        allowed_modes = self._option_scan_min_survivor_modes()
        if allowed_modes and str(execution_mode or "").strip().upper() not in allowed_modes:
            return candidates
        min_survivors = int(getattr(cfg, "OPTION_SCAN_MIN_SURVIVORS_COUNT", 0) or 0)
        if min_survivors <= 0:
            return candidates

        fallback_score = float(getattr(cfg, "OPTION_SCAN_MIN_SURVIVOR_SCORE", 0.32) or 0.32)

        def _rejected_rank(record: dict) -> tuple[float, float, float]:
            ltp = float(record.get("ltp") or 0.0)
            volume = float(record.get("volume") or 0.0)
            oi = float(record.get("oi") or 0.0)
            return (ltp, volume, oi)

        selected_rejected = sorted(
            [row for row in list(rejected or []) if isinstance(row, dict)],
            key=_rejected_rank,
            reverse=True,
        )[: min_survivors * 2]
        if not selected_rejected:
            return candidates

        injected: list[dict] = []
        for idx, rec in enumerate(selected_rejected, start=1):
            degraded = self._build_borderline_candidate(
                market_data=market_data,
                reason="scan_min_survivor",
                confidence=fallback_score,
                strategy_tag=strategy_tag,
                direction=direction,
            )
            if not isinstance(degraded, dict):
                continue
            entry_val = self._coerce_positive_float(rec.get("ltp"))
            if entry_val is not None:
                degraded["display_entry"] = entry_val
                degraded["display_entry_source"] = "scan_min_survivor"
                degraded["display_entry_status"] = "displayable"
                degraded["entry"] = entry_val
                degraded["entry_source"] = "scan_min_survivor"
                degraded["entry_status"] = "displayable"
            stop_val = self._coerce_positive_float(rec.get("stop"))
            target_val = self._coerce_positive_float(rec.get("target"))
            if stop_val is not None:
                degraded["stop_loss"] = stop_val
            if target_val is not None:
                degraded["target"] = target_val
            degraded["trade_id"] = str(
                degraded.get("trade_id")
                or f"tbscan_{symbol}_{idx}"
            )
            degraded["candidate_origin"] = "scan_min_survivor"
            degraded["candidate_status"] = "queue_only"
            degraded["execution_status"] = "queue_only"
            degraded["permission"] = "QUEUE_ONLY"
            degraded["final_action"] = "QUEUE_ONLY"
            degraded["readiness"] = "QUEUE_ONLY"
            degraded["planning_only"] = True
            degraded["tradable"] = False
            degraded["execution_allowed"] = False
            degraded["execution_ok"] = False
            degraded["eligible_for_execution"] = False
            degraded["is_executable"] = False
            degraded["max_final_action"] = "QUEUE_ONLY"
            degraded["execution_blocked"] = True
            degraded["execution_block_reason"] = "scan_min_survivor"
            degraded["reason"] = str(rec.get("reason") or "scan_min_survivor")
            degraded["rank_score"] = max(float(degraded.get("rank_score") or 0.0), fallback_score)
            degraded["final_score"] = max(float(degraded.get("final_score") or 0.0), fallback_score)
            degraded["opportunity_score"] = max(
                float(degraded.get("opportunity_score") or 0.0),
                fallback_score,
            )
            source_flags = dict(degraded.get("source_flags") or {})
            source_flags["candidate_origin"] = "scan_min_survivor"
            source_flags["scan_min_survivor"] = True
            source_flags["scan_min_survivor_reject_reason"] = str(rec.get("reason") or "")
            degraded["source_flags"] = source_flags
            injected.append(degraded)
            if len(injected) >= min_survivors:
                break

        if injected:
            logger.warning(
                "OPTION_SCAN_MIN_SURVIVORS_APPLIED symbol=%s requested=%s injected=%s reasons=%s",
                symbol,
                min_survivors,
                len(injected),
                [str(row.get("reason") or "") for row in injected],
            )
            return list(candidates) + injected
        return candidates

    def _option_tradability_precondition(
        self,
        *,
        symbol: str,
        opt: dict,
        market_data: dict,
        market_ctx,
        direction: str | None = None,
    ) -> tuple[bool, dict]:
        strike = opt.get("strike")
        opt_type = opt.get("type")
        expiry_candidate = self._option_expiry(opt, market_data) or self._resolve_expiry_for_symbol(symbol, market_data)
        contract_info = self._resolve_option_contract(
            symbol,
            strike,
            opt_type,
            expiry_candidate,
            market_data,
        )
        expiry_resolved = str(contract_info.get("expiry") or expiry_candidate or "").strip()
        tradingsymbol = str(contract_info.get("tradingsymbol") or opt.get("tradingsymbol") or "").strip()
        instrument_token = contract_info.get("instrument_token")
        instrument_id = contract_info.get("instrument_id") or opt.get("instrument_id")
        try:
            instrument_token = int(instrument_token) if instrument_token is not None else None
        except Exception:
            instrument_token = None
        missing_fields: list[str] = []
        if instrument_token is None:
            missing_fields.append("instrument_token")
        if not tradingsymbol:
            missing_fields.append("tradingsymbol")
        if not expiry_resolved:
            missing_fields.append("expiry_date")
        contract_label = f"{symbol}|{expiry_resolved}|{strike}|{opt_type}"
        if missing_fields:
            return False, {
                "reason_code": "unresolved_contract",
                "reason_text": "Option contract unresolved before candidate gating",
                "gate_name": "option_tradability_precondition",
                "contract": contract_label,
                "strike": strike,
                "option_type": opt_type,
                "direction": direction,
                "instrument_token": instrument_token,
                "tradingsymbol": tradingsymbol or None,
                "expiry_date": expiry_resolved or None,
                "missing_fields": missing_fields,
                "skip_derived_levels": True,
            }

        if bool(contract_info.get("fallback_applied")):
            return False, {
                "reason_code": "contract_resolution_fallback_blocked",
                "reason_text": "Option contract fallback resolution blocked before candidate gating",
                "gate_name": "option_tradability_precondition",
                "contract": contract_label,
                "strike": strike,
                "option_type": opt_type,
                "direction": direction,
                "instrument_token": instrument_token,
                "tradingsymbol": tradingsymbol or None,
                "expiry_date": expiry_resolved or None,
                "contract_resolution_fallback_used": True,
                "fallback_applied": True,
                "skip_derived_levels": True,
            }

        quote_source = str(
            opt.get("quote_source")
            or opt.get("price_source")
            or market_data.get("option_quote_source")
            or market_data.get("chain_source")
            or ""
        ).strip()
        option_ltp_source = str(
            opt.get("option_ltp_source")
            or opt.get("quote_source")
            or opt.get("price_source")
            or market_data.get("option_ltp_source")
            or market_data.get("option_quote_source")
            or ("option_chain_live" if quote_source.lower() in {"live", "option_chain", "option_chain_live"} else "")
        ).strip()
        if quote_source.lower() == "synthetic_index" or option_ltp_source.lower() == "synthetic_index" or not option_ltp_source:
            return False, {
                "reason_code": "NO_OPTION_QUOTE_SOURCE",
                "reason_text": "Option candidate rejected because option quote source is missing or synthetic index fallback",
                "gate_name": "option_tradability_precondition",
                "contract": contract_label,
                "strike": strike,
                "option_type": opt_type,
                "direction": direction,
                "instrument_token": instrument_token,
                "tradingsymbol": tradingsymbol,
                "expiry_date": expiry_resolved,
                "quote_source": quote_source or None,
                "option_ltp_source": option_ltp_source or None,
            }

        market_mode = str(getattr(market_ctx, "mode", getattr(cfg, "EXECUTION_MODE", "SIM")))
        live_sla_default = float(
            min(
                float(getattr(cfg, "OPTION_LTP_SLA_SEC", getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))),
                float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)),
            )
        )
        option_tick_sla_sec = float(
            get_option_ltp_sla_sec(
                market_mode,
                live_sla_default,
                allow_stale_quotes=bool(getattr(market_ctx, "allow_stale_quotes", False)),
                market_open=bool(getattr(market_ctx, "is_market_open", False)),
                expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
            )
        )
        quote_age_sec = self._coerce_nonnegative_float(opt.get("quote_age_sec"))
        quote_ts_epoch = self._coerce_nonnegative_float(
            opt.get("quote_ts_epoch")
            or opt.get("quote_timestamp_epoch")
            or opt.get("timestamp_epoch")
            or opt.get("ts_epoch")
        )
        if quote_age_sec is None and quote_ts_epoch is not None:
            quote_age_sec = compute_age_sec(quote_ts_epoch, now_utc_epoch())
        allow_stale_quotes = bool(getattr(market_ctx, "allow_stale_quotes", False))
        soft_stale_sec = float(max(option_tick_sla_sec, float(getattr(cfg, "OPTION_TICK_SOFT_STALE_SEC", 3.0))))
        hard_stale_sec = float(max(soft_stale_sec, float(getattr(cfg, "OPTION_TICK_HARD_STALE_SEC", 6.0))))
        market_mode_live = str(market_mode or "").strip().upper() == "LIVE"
        if market_mode_live:
            live_soft_stale_sec = float(getattr(cfg, "LIVE_OPTION_TICK_SOFT_STALE_SEC", soft_stale_sec) or soft_stale_sec)
            live_hard_stale_sec = float(getattr(cfg, "LIVE_OPTION_TICK_HARD_STALE_SEC", hard_stale_sec) or hard_stale_sec)
            soft_stale_sec = float(min(soft_stale_sec, live_soft_stale_sec))
            hard_stale_sec = float(max(soft_stale_sec, min(hard_stale_sec, live_hard_stale_sec)))
            fallback_max_sec = max(
                0.0,
                float(getattr(cfg, "TRADE_BUILDER_FEED_AGE_FALLBACK_MAX_SEC", 3.0) or 3.0),
            )
            if quote_age_sec is None or quote_age_sec > option_tick_sla_sec:
                symbol_age = self._symbol_feed_option_tick_age(symbol, now_epoch=now_utc_epoch())
                if symbol_age is not None and symbol_age <= fallback_max_sec:
                    quote_age_sec = float(symbol_age)
                    opt["quote_age_sec"] = float(symbol_age)
                    opt["quote_age_fallback_source"] = "feed_runtime_symbol_age"
        if quote_age_sec is None or quote_age_sec > option_tick_sla_sec:
            stale_bypass = self._allow_stale_option_tick_bypass(
                market_ctx,
                market_mode=market_mode,
                quote_age_sec=quote_age_sec,
            )
            if stale_bypass:
                return True, {
                    "reason_code": "STALE_OPTION_TICK",
                    "reason_text": "Option tick stale by SLA but bypassed by diagnostic stale-tick setting",
                    "gate_name": "option_tradability_precondition",
                    "contract": contract_label,
                    "strike": strike,
                    "option_type": opt_type,
                    "direction": direction,
                    "instrument_token": instrument_token,
                    "tradingsymbol": tradingsymbol,
                    "expiry_date": expiry_resolved,
                    "quote_source": quote_source or None,
                    "option_ltp_source": option_ltp_source or None,
                    "quote_age_sec": quote_age_sec,
                    "tick_age_sec": quote_age_sec,
                    "sla_threshold_sec": option_tick_sla_sec,
                    "option_tick_sla_sec": option_tick_sla_sec,
                    "stale_option_tick": True,
                    "stale_allowed": True,
                    "stale_bypass": True,
                }
            if allow_stale_quotes:
                return True, {
                    "reason_code": "STALE_OPTION_TICK",
                    "reason_text": "Option tick stale but allowed; candidate downgraded to advisory",
                    "gate_name": "option_tradability_precondition",
                    "contract": contract_label,
                    "strike": strike,
                    "option_type": opt_type,
                    "direction": direction,
                    "instrument_token": instrument_token,
                    "tradingsymbol": tradingsymbol,
                    "expiry_date": expiry_resolved,
                    "quote_source": quote_source or None,
                    "option_ltp_source": option_ltp_source or None,
                    "quote_age_sec": quote_age_sec,
                    "tick_age_sec": quote_age_sec,
                    "sla_threshold_sec": option_tick_sla_sec,
                    "option_tick_sla_sec": option_tick_sla_sec,
                    "stale_option_tick": True,
                    "stale_allowed": True,
                }
            bid = self._coerce_nonnegative_float(opt.get("best_bid"))
            if bid is None:
                bid = self._coerce_nonnegative_float(opt.get("bid"))
            if bid is None:
                bid = self._coerce_nonnegative_float(opt.get("opt_bid"))
            ask = self._coerce_nonnegative_float(opt.get("best_ask"))
            if ask is None:
                ask = self._coerce_nonnegative_float(opt.get("ask"))
            if ask is None:
                ask = self._coerce_nonnegative_float(opt.get("opt_ask"))
            ltp_ref = self._coerce_nonnegative_float(opt.get("ltp"))
            if ltp_ref is None:
                ltp_ref = self._coerce_nonnegative_float(opt.get("current_ltp"))
            if ltp_ref is None:
                ltp_ref = self._coerce_nonnegative_float(opt.get("last_price"))
            spread_pct = None
            if bid is not None and ask is not None and ask >= bid and ltp_ref not in (None, 0):
                try:
                    spread_pct = float(ask - bid) / float(ltp_ref)
                except Exception:
                    spread_pct = None
            max_spread_pct = float(getattr(cfg, "MAX_SPREAD_PCT", 0.02))
            spread_ok = spread_pct is not None and spread_pct <= max_spread_pct
            require_volume = bool(getattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", False))
            if market_mode_live:
                try:
                    mode_profile = get_runtime_profile(mode=market_mode)
                    require_volume = bool(require_volume and mode_profile.suggestion_require_volume)
                except Exception:
                    require_volume = bool(require_volume)
            volume_val = self._coerce_nonnegative_float(opt.get("volume"))
            volume_ok = bool(volume_val is not None and volume_val > 0) if require_volume else True
            oi_val = self._coerce_nonnegative_float(opt.get("oi"))
            min_oi_soften = max(
                0.0,
                float(getattr(cfg, "TRADE_BUILDER_LIVE_STALE_SOFTEN_MIN_OI", 1000.0) or 1000.0),
            )
            oi_ok = bool(oi_val is not None and oi_val >= min_oi_soften)
            quote_ok_raw = opt.get("quote_ok")
            if quote_ok_raw is None:
                quote_ok_raw = bool(
                    bid is not None
                    and ask is not None
                    and ask >= bid
                    and ltp_ref not in (None, 0)
                )
            require_quote_ok_soften = bool(
                getattr(cfg, "TRADE_BUILDER_LIVE_STALE_SOFTEN_REQUIRE_QUOTE_OK", True)
            )
            quote_ok_for_soften = (not require_quote_ok_soften) or bool(quote_ok_raw)
            liquidity_ok_for_soften = bool(spread_ok and (volume_ok or oi_ok))
            live_soften_enabled = bool(getattr(cfg, "TRADE_BUILDER_ALLOW_LIVE_STALE_OPTION_TICK_SOFTEN", True))
            mildly_stale = quote_age_sec is not None and quote_age_sec <= soft_stale_sec
            hard_stale = quote_age_sec is None or quote_age_sec > hard_stale_sec
            stale_within_live_window = quote_age_sec is not None and quote_age_sec <= hard_stale_sec
            if (
                live_soften_enabled
                and market_mode_live
                and stale_within_live_window
                and liquidity_ok_for_soften
                and quote_ok_for_soften
                and not hard_stale
            ):
                reason_text = (
                    "Option tick mildly stale in LIVE; downgraded to advisory penalty"
                    if mildly_stale
                    else "Option tick stale in LIVE hard window; downgraded to advisory penalty"
                )
                return True, {
                    "reason_code": "STALE_OPTION_TICK",
                    "reason_text": reason_text,
                    "gate_name": "option_tradability_precondition",
                    "contract": contract_label,
                    "strike": strike,
                    "option_type": opt_type,
                    "direction": direction,
                    "instrument_token": instrument_token,
                    "tradingsymbol": tradingsymbol,
                    "expiry_date": expiry_resolved,
                    "quote_source": quote_source or None,
                    "option_ltp_source": option_ltp_source or None,
                    "quote_age_sec": quote_age_sec,
                    "tick_age_sec": quote_age_sec,
                    "sla_threshold_sec": option_tick_sla_sec,
                    "option_tick_sla_sec": option_tick_sla_sec,
                    "option_tick_soft_stale_sec": soft_stale_sec,
                    "option_tick_hard_stale_sec": hard_stale_sec,
                    "stale_option_tick": True,
                    "stale_allowed": True,
                    "live_softened": True,
                    "spread_ok": spread_ok,
                    "volume_ok": volume_ok,
                    "oi": oi_val,
                    "oi_ok": oi_ok,
                    "min_oi_soften": min_oi_soften,
                    "quote_ok_for_soften": quote_ok_for_soften,
                    "liquidity_ok_for_soften": liquidity_ok_for_soften,
                }
            return False, {
                "reason_code": "STALE_OPTION_TICK",
                "reason_text": "Option candidate rejected because option tick is missing/stale by SLA",
                "gate_name": "option_tradability_precondition",
                "contract": contract_label,
                "strike": strike,
                "option_type": opt_type,
                "direction": direction,
                "instrument_token": instrument_token,
                "tradingsymbol": tradingsymbol,
                "expiry_date": expiry_resolved,
                "quote_source": quote_source or None,
                "option_ltp_source": option_ltp_source or None,
                "quote_age_sec": quote_age_sec,
                "tick_age_sec": quote_age_sec,
                "sla_threshold_sec": option_tick_sla_sec,
                "option_tick_sla_sec": option_tick_sla_sec,
                "option_tick_soft_stale_sec": soft_stale_sec,
                "option_tick_hard_stale_sec": hard_stale_sec,
                "hard_stale": bool(quote_age_sec is None or quote_age_sec > hard_stale_sec),
            }

        opt["expiry"] = expiry_resolved
        opt["expiry_date"] = expiry_resolved
        opt["tradingsymbol"] = tradingsymbol
        opt["instrument_token"] = instrument_token
        opt["instrument_id"] = instrument_id
        opt["quote_source"] = quote_source or option_ltp_source
        opt["option_ltp_source"] = option_ltp_source
        opt["quote_age_sec"] = quote_age_sec
        opt["option_tick_sla_sec"] = option_tick_sla_sec
        opt["_resolved_contract"] = {
            "expiry": expiry_resolved,
            "tradingsymbol": tradingsymbol,
            "instrument_token": instrument_token,
            "instrument_id": instrument_id,
            "quote_source": quote_source or option_ltp_source,
            "option_ltp_source": option_ltp_source,
            "quote_age_sec": quote_age_sec,
            "option_tick_sla_sec": option_tick_sla_sec,
        }
        return True, dict(opt["_resolved_contract"])

    def _option_expiry(self, opt: dict | None, market_data: dict | None = None) -> str:
        candidates = []
        if isinstance(opt, dict):
            candidates.extend(
                [
                    opt.get("expiry"),
                    opt.get("expiry_date"),
                    opt.get("expiryDate"),
                    opt.get("exp"),
                ]
            )
        if isinstance(market_data, dict):
            candidates.extend(
                [
                    market_data.get("expiry"),
                    market_data.get("next_expiry"),
                ]
            )
            chain = market_data.get("option_chain")
            if isinstance(chain, (list, tuple)):
                for row in chain:
                    if not isinstance(row, dict):
                        continue
                    candidates.extend(
                        [
                            row.get("expiry"),
                            row.get("expiry_date"),
                            row.get("expiryDate"),
                            row.get("exp"),
                        ]
                    )
                    # First non-empty entry is enough; avoid scanning huge chains.
                    if any(str(v or "").strip() for v in candidates[-4:]):
                        break
        for value in candidates:
            text = str(value or "").strip()
            if text and text.upper() not in {"NONE", "NA", "N/A", "NAN"}:
                return text
        return ""

    def _coerce_date_str(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value or "").strip()
        if not text or text.upper() in {"NONE", "NA", "N/A", "NAN"}:
            return ""
        if "T" in text:
            text = text.split("T", 1)[0]
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except Exception:
            return text

    def _option_exchange(self, symbol: str | None) -> str:
        sym = str(symbol or "").upper()
        return "BFO" if sym == "SENSEX" else "NFO"

    def _resolve_expiry_for_symbol(self, symbol: str, market_data: dict | None) -> str:
        selection_mode = str(getattr(cfg, "OPTION_EXPIRY_SELECTION", "NEAREST") or "NEAREST").upper()
        expiries: list[date] = []
        data = market_data or {}
        chain = data.get("option_chain")
        if isinstance(chain, (list, tuple)):
            for row in chain:
                if not isinstance(row, dict):
                    continue
                exp_text = self._coerce_date_str(
                    row.get("expiry") or row.get("expiry_date") or row.get("expiryDate") or row.get("exp")
                )
                if not exp_text:
                    continue
                try:
                    expiries.append(datetime.fromisoformat(exp_text).date())
                except Exception:
                    continue
        if expiries:
            chosen = select_registry_expiry(
                expiries,
                selection_mode=selection_mode,
                today=now_ist().date(),
            )
            if chosen is not None:
                return chosen.isoformat()
        raw_list = data.get("expiries") or data.get("expiry_list") or data.get("available_expiries")
        if isinstance(raw_list, (list, tuple)):
            exp_dates = []
            for item in raw_list:
                exp_text = self._coerce_date_str(item)
                if not exp_text:
                    continue
                try:
                    exp_dates.append(datetime.fromisoformat(exp_text).date())
                except Exception:
                    continue
            if exp_dates:
                chosen = select_registry_expiry(
                    exp_dates,
                    selection_mode=selection_mode,
                    today=now_ist().date(),
                )
                if chosen is not None:
                    return chosen.isoformat()
        exchange = self._option_exchange(symbol)
        try:
            fallback = kite_client.next_available_expiry(symbol, exchange=exchange)
            if fallback:
                return str(fallback)
        except Exception:
            pass
        return self._option_expiry(None, data) or ""

    def _candidate_setup_family(self, signal: dict | None, force_family: str | None = None) -> str:
        family = str(force_family or "").strip().upper()
        if family == "TREND":
            return "continuation"
        if family == "MEAN_REVERT":
            return "mean-reversion"
        if family == "DEFINED_RISK":
            return "breakout"
        reason = str((signal or {}).get("reason") or "").strip().lower()
        if "pullback" in reason:
            return "pullback"
        if "mean reversion" in reason:
            return "mean-reversion"
        if "breakout" in reason or "breakdown" in reason:
            return "breakout"
        if "trend" in reason or "vwap" in reason or "momentum" in reason:
            return "continuation"
        return "continuation"

    def _annotate_candidate_chain_rows(
        self,
        symbol: str,
        market_data: dict | None,
        underlying_spot: float | None,
    ) -> list[dict]:
        data = market_data or {}
        raw_chain = data.get("option_chain")
        raw_len = len(raw_chain) if isinstance(raw_chain, (list, tuple)) else 0
        logger.info("CHAIN_DEBUG_START symbol=%s raw_len=%d", symbol, raw_len)
        if not isinstance(raw_chain, (list, tuple)):
            logger.info(
                "CHAIN_DEBUG_EXPIRY symbol=%s len=%d same_expiry=%s next_expiry=%s",
                symbol,
                0,
                "",
                "",
            )
            logger.info(
                "CHAIN_DEBUG_STRIKE symbol=%s len=%d atm=%s step=%s",
                symbol,
                0,
                None,
                None,
            )
            logger.error("CHAIN_EMPTY symbol=%s reason=post_filters", symbol)
            return []
        unique_expiries: list[str] = []
        expiry_seen: set[str] = set()
        for raw in raw_chain:
            if not isinstance(raw, dict):
                continue
            expiry_text = self._coerce_date_str(self._option_expiry(raw, data))
            if not expiry_text or expiry_text in expiry_seen:
                continue
            expiry_seen.add(expiry_text)
            unique_expiries.append(expiry_text)
        unique_expiries.sort()
        same_expiry = self._coerce_date_str(self._resolve_expiry_for_symbol(symbol, data))
        next_expiry = ""
        if unique_expiries:
            if same_expiry and same_expiry in unique_expiries:
                same_index = unique_expiries.index(same_expiry)
                if same_index + 1 < len(unique_expiries):
                    next_expiry = unique_expiries[same_index + 1]
            elif len(unique_expiries) >= 2:
                same_expiry = unique_expiries[0]
                next_expiry = unique_expiries[1]
            elif not same_expiry:
                same_expiry = unique_expiries[0]
        try:
            spot_ref = float(underlying_spot) if underlying_spot is not None else None
        except Exception:
            spot_ref = None
        if spot_ref is None or spot_ref <= 0:
            try:
                spot_ref = float(data.get("ltp")) if data.get("ltp") is not None else None
            except Exception:
                spot_ref = None
        step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}
        step = float(step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50)) or 0.0)
        atm_strike = None
        if step > 0 and spot_ref is not None and spot_ref > 0:
            atm_strike = int(round(float(spot_ref) / step) * step)
        enforce_strike_ladder = bool(getattr(cfg, "TRADE_BUILDER_ENFORCE_STRIKE_LADDER", False))
        strike_ladder_width = max(0, int(getattr(cfg, "TRADE_BUILDER_STRIKE_LADDER_WIDTH", 2) or 0))
        expiry_bucket_mode = str(getattr(cfg, "TRADE_BUILDER_EXPIRY_BUCKET_MODE", "ALL") or "ALL").strip().upper()
        bucket_rank = {"same_expiry": 0, "next_expiry": 1, "other_expiry": 2}
        rows: list[dict] = []
        expiry_filtered_len = 0
        strike_filtered_len = 0
        seen_contracts: set[tuple] = set()
        for raw in raw_chain:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            expiry_text = self._coerce_date_str(self._option_expiry(row, data))
            if expiry_text and same_expiry and expiry_text == same_expiry:
                expiry_bucket = "same_expiry"
            elif expiry_text and next_expiry and expiry_text == next_expiry:
                expiry_bucket = "next_expiry"
            else:
                expiry_bucket = "other_expiry"
            if expiry_bucket_mode == "SAME" and expiry_bucket != "same_expiry":
                continue
            if expiry_bucket_mode in {"SAME_AND_NEXT", "NEXT"} and expiry_bucket == "other_expiry":
                continue
            expiry_filtered_len += 1
            strike_offset = None
            try:
                strike_val = float(row.get("strike") or row.get("strike_price") or row.get("strikePrice"))
            except Exception:
                strike_val = None
            if strike_val is not None and atm_strike is not None and step > 0:
                strike_offset = int(round((float(strike_val) - float(atm_strike)) / float(step)))
            if enforce_strike_ladder and strike_offset is not None and abs(int(strike_offset)) > strike_ladder_width:
                continue
            strike_filtered_len += 1
            row["candidate_origin"] = {
                "strike_offset": strike_offset,
                "expiry_bucket": expiry_bucket,
            }
            tradingsymbol = str(row.get("tradingsymbol") or "").strip()
            instrument_token = row.get("instrument_token")
            contract_key = None
            if expiry_text and (tradingsymbol or instrument_token is not None):
                contract_key = (
                    expiry_text,
                    strike_val,
                    str(row.get("type") or row.get("option_type") or row.get("right") or "").strip().upper(),
                    tradingsymbol,
                    instrument_token,
                )
            if contract_key is not None:
                if contract_key in seen_contracts:
                    continue
                seen_contracts.add(contract_key)
            rows.append(row)
        rows.sort(
            key=lambda row: (
                bucket_rank.get(str((row.get("candidate_origin") or {}).get("expiry_bucket") or "other_expiry"), 3),
                abs(int(((row.get("candidate_origin") or {}).get("strike_offset") or 0))),
                int(((row.get("candidate_origin") or {}).get("strike_offset") or 0)),
                self._coerce_date_str(self._option_expiry(row, data)),
                str(row.get("type") or row.get("option_type") or row.get("right") or "").strip().upper(),
                str(row.get("tradingsymbol") or row.get("instrument_token") or ""),
            )
        )
        logger.info(
            "CHAIN_DEBUG_EXPIRY symbol=%s len=%d same_expiry=%s next_expiry=%s",
            symbol,
            expiry_filtered_len,
            same_expiry,
            next_expiry,
        )
        logger.info(
            "CHAIN_DEBUG_STRIKE symbol=%s len=%d atm=%s step=%s",
            symbol,
            strike_filtered_len,
            atm_strike,
            step,
        )
        if not rows:
            logger.error("CHAIN_EMPTY symbol=%s reason=post_filters", symbol)
        return rows

    def _resolve_underlying_spot(self, market_data: dict, market_ctx) -> tuple[float | None, str | None, bool, str | None]:
        spot = market_data.get("ltp")
        spot_source = (
            market_data.get("ltp_source")
            or market_data.get("index_quote_source")
            or market_data.get("quote_source")
        )
        try:
            spot_val = float(spot) if spot is not None else None
        except Exception:
            spot_val = None
        if spot_val is None or spot_val <= 0:
            return None, spot_source, False, "spot_missing"
        age = market_data.get("quote_age_sec")
        max_age = float(
            getattr(cfg, "OFFHOURS_MAX_LTP_AGE_SEC", getattr(cfg, "MAX_LTP_AGE_SEC", 8.0))
            if getattr(market_ctx, "allow_stale_quotes", False)
            else getattr(cfg, "MAX_LTP_AGE_SEC", 8.0)
        )
        try:
            age_val = float(age) if age is not None else None
        except Exception:
            age_val = None
        if age_val is None or age_val > max_age:
            return spot_val, spot_source, False, "spot_stale"
        return spot_val, spot_source, True, None

    def _resolve_option_contract(self, symbol: str, strike, opt_type: str, expiry: str, market_data: dict | None) -> dict:
        data = market_data or {}
        exp_text = self._coerce_date_str(expiry)
        opt_type = self._coerce_option_type(opt_type)
        strike_val = None
        try:
            strike_val = float(strike) if strike is not None else None
        except Exception:
            strike_val = None
        tradingsymbol = None
        instrument_token = None
        if strike_val is None or not opt_type:
            return {
                "expiry": exp_text,
                "expiry_date": exp_text,
                "tradingsymbol": None,
                "instrument_token": None,
                "instrument_id": None,
            }
        chain = data.get("option_chain")
        contract_selected = None
        fallback_applied = False
        nearest_diff = None
        chain_candidates: list[dict] = []
        if isinstance(chain, (list, tuple)):
            for row in chain:
                if not isinstance(row, dict):
                    continue
                row_type = str(row.get("type") or row.get("option_type") or row.get("right") or "").strip().upper()
                if row_type != str(opt_type).upper():
                    continue
                row_strike_raw = row.get("strike")
                if row_strike_raw is None:
                    row_strike_raw = row.get("strike_price")
                if row_strike_raw is None:
                    row_strike_raw = row.get("strikePrice")
                if row_strike_raw is None:
                    continue
                try:
                    row_strike = float(row_strike_raw)
                except Exception:
                    continue
                row_exp = self._option_expiry(row, data)
                row_exp_text = self._coerce_date_str(row_exp)
                chain_candidates.append(
                    {
                        "row": row,
                        "strike": row_strike,
                        "expiry": row_exp_text,
                        "tradingsymbol": row.get("tradingsymbol"),
                        "instrument_token": row.get("instrument_token"),
                    }
                )
                if float(row_strike) != float(strike_val):
                    continue
                if exp_text and row_exp and str(row_exp) != exp_text:
                    continue
                if not exp_text and row_exp:
                    exp_text = self._coerce_date_str(row_exp)
                contract_selected = dict(row)
                tradingsymbol = row.get("tradingsymbol") or tradingsymbol
                instrument_token = row.get("instrument_token") or instrument_token
                if tradingsymbol or instrument_token:
                    break
        if (tradingsymbol is None and instrument_token is None) and chain_candidates:
            fallback_steps = max(0, int(getattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_STEPS", 4) or 4))
            step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}
            step = float(step_map.get(str(symbol or "").upper(), getattr(cfg, "STRIKE_STEP", 50)) or 0.0)
            max_strike_delta = float(step * fallback_steps) if step > 0 and fallback_steps > 0 else None
            max_strike_delta_abs = self._coerce_positive_float(
                getattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_ABS", None)
            )
            max_strike_delta_pct = self._coerce_positive_float(
                getattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_PCT", None)
            )
            underlying_spot = self._coerce_positive_float(
                data.get("underlying_spot")
                or data.get("spot")
                or data.get("ltp")
            )
            max_strike_delta_pct_abs = (
                float(underlying_spot) * float(max_strike_delta_pct)
                if underlying_spot is not None and max_strike_delta_pct is not None
                else None
            )
            delta_limits = [float(limit) for limit in (max_strike_delta, max_strike_delta_abs, max_strike_delta_pct_abs) if limit is not None]
            effective_max_strike_delta = max(delta_limits) if delta_limits else None

            def _candidate_sort_key(item: dict) -> tuple[float, int, str]:
                c_exp = str(item.get("expiry") or "")
                expiry_penalty = 0 if (not exp_text or c_exp == exp_text) else 1
                return (abs(float(item.get("strike") or 0.0) - float(strike_val)), expiry_penalty, c_exp)

            sorted_candidates = sorted(chain_candidates, key=_candidate_sort_key)
            if sorted_candidates:
                best = sorted_candidates[0]
                diff = abs(float(best.get("strike") or 0.0) - float(strike_val))
                nearest_diff = diff
                allow_fallback = True
                if effective_max_strike_delta is not None:
                    allow_fallback = bool(diff <= effective_max_strike_delta + 1e-9)
                if allow_fallback:
                    fallback_applied = True
                    tradingsymbol = best.get("tradingsymbol") or tradingsymbol
                    instrument_token = best.get("instrument_token") or instrument_token
                    best_expiry = str(best.get("expiry") or "")
                    if best_expiry:
                        exp_text = best_expiry
                    if tradingsymbol or instrument_token:
                        print(
                            "CONTRACT_RESOLUTION_FALLBACK",
                            {
                                "symbol": str(symbol or "").upper(),
                                "requested_strike": float(strike_val),
                                "resolved_strike": float(best.get("strike") or strike_val),
                                "requested_expiry": self._coerce_date_str(expiry),
                                "resolved_expiry": exp_text,
                                "option_type": str(opt_type).upper(),
                                "nearest_diff": float(diff),
                                "fallback_limit": float(effective_max_strike_delta) if effective_max_strike_delta is not None else None,
                            },
                        )
        if not exp_text:
            exp_text = self._resolve_expiry_for_symbol(symbol, data)
        exchange = self._option_exchange(symbol)
        if not tradingsymbol:
            try:
                ts = kite_client.find_option_symbol_with_expiry(symbol, strike_val, opt_type, exp_text, exchange=exchange)
                if ts:
                    tradingsymbol = ts.split(":", 1)[-1]
            except Exception:
                pass
        if tradingsymbol and instrument_token is None:
            try:
                instruments = kite_client.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
                for inst in instruments or []:
                    if inst.get("tradingsymbol") != tradingsymbol:
                        continue
                    instrument_token = inst.get("instrument_token")
                    if not exp_text:
                        exp_text = self._coerce_date_str(inst.get("expiry"))
                    break
            except Exception:
                pass
        if tradingsymbol is None and instrument_token is None:
            available_expiries = sorted(
                {
                    str(item.get("expiry") or "")
                    for item in chain_candidates
                    if str(item.get("expiry") or "").strip()
                }
            )
            available_strikes = sorted(
                {
                    float(item.get("strike"))
                    for item in chain_candidates
                    if item.get("strike") is not None
                }
            )
            print(
                "CONTRACT_RESOLUTION_FAILED",
                {
                    "symbol": str(symbol or "").upper(),
                    "requested_strike": float(strike_val),
                    "requested_expiry": self._coerce_date_str(expiry),
                    "resolved_expiry": exp_text,
                    "option_type": str(opt_type).upper(),
                    "available_expiries": available_expiries[:5],
                    "available_strikes_sample": available_strikes[:10],
                    "fallback_applied": bool(fallback_applied),
                    "nearest_diff": nearest_diff,
                },
            )
        instrument_id = build_instrument_id(symbol, "OPT", exp_text, strike_val, opt_type) if exp_text else None
        return {
            "expiry": exp_text,
            "expiry_date": exp_text,
            "tradingsymbol": tradingsymbol,
            "instrument_token": instrument_token,
            "instrument_id": instrument_id,
            "fallback_applied": bool(fallback_applied),
        }

    def _percentile(self, values: list[float], pct: float) -> float | None:
        if not values:
            return None
        try:
            p = max(0.0, min(1.0, float(pct)))
        except Exception:
            p = 0.5
        arr = sorted(float(v) for v in values if v is not None)
        if not arr:
            return None
        if len(arr) == 1:
            return float(arr[0])
        idx = p * (len(arr) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(arr) - 1)
        w = idx - lo
        return float(arr[lo] * (1.0 - w) + arr[hi] * w)

    def _dynamic_premium_bands(self, symbol: str, chain_rows: list[dict]) -> dict[str, tuple[float, float]]:
        band_map = getattr(cfg, "PREMIUM_BANDS", {}) or {}
        global_band = band_map.get(
            symbol,
            (getattr(cfg, "MIN_PREMIUM", 40), getattr(cfg, "MAX_PREMIUM", 150)),
        )
        try:
            global_min = float(global_band[0])
            global_max = float(global_band[1])
        except Exception:
            global_min, global_max = (40.0, 150.0)
        out: dict[str, tuple[float, float]] = {"__GLOBAL__": (global_min, global_max)}
        if not isinstance(chain_rows, (list, tuple)):
            return out
        pct_low = max(0.0, min(0.5, float(getattr(cfg, "PREMIUM_BAND_PERCENTILE_LOW", 0.10))))
        pct_high = max(0.5, min(0.99, float(getattr(cfg, "PREMIUM_BAND_PERCENTILE_HIGH", 0.90))))
        atm_window = max(0.0, float(getattr(cfg, "PREMIUM_BAND_ATM_MONEYNESS_MAX", 0.03)))
        min_rows = max(4, int(getattr(cfg, "PREMIUM_BAND_MIN_ROWS", 8)))
        min_liq_vol = max(0, int(getattr(cfg, "PREMIUM_BAND_MIN_VOLUME", 1)))
        grouped: dict[str, list[float]] = {}
        for raw in chain_rows:
            if not isinstance(raw, dict):
                continue
            ltp = self._coerce_positive_float(
                raw.get("ltp")
                or raw.get("last_price")
                or raw.get("close")
                or raw.get("price")
            )
            if ltp is None:
                continue
            if int(raw.get("volume") or 0) < min_liq_vol:
                continue
            mny = raw.get("moneyness")
            if mny is not None:
                try:
                    if abs(float(mny)) > atm_window:
                        continue
                except Exception as exc:
                    try:
                        self._log_blocked_candidate(
                            symbol,
                            "quick_synth_error",
                            f"Quick synth failed: {exc}",
                            market_data=market_data,
                            extra={
                                "error": str(exc),
                                "skip_derived_levels": True,
                                "underlying_spot": underlying_spot,
                                "spot_source": spot_source,
                            },
                        )
                    except Exception:
                        pass
                    if debug_reasons:
                        _log_advisory_debug("trade_builder_quick_synth_error err=%s", exc)
                    pass
            expiry = self._option_expiry(raw, {"option_chain": []})
            if not expiry:
                expiry = "__ALL__"
            grouped.setdefault(expiry, []).append(float(ltp))
            grouped.setdefault("__ALL__", []).append(float(ltp))
        for expiry, vals in grouped.items():
            if len(vals) < min_rows:
                continue
            p_low = self._percentile(vals, pct_low)
            p_high = self._percentile(vals, pct_high)
            if p_low is None or p_high is None:
                continue
            # Dynamic chain-derived range is primary. Legacy global band is fallback-only.
            band_min = float(p_low)
            band_max = float(p_high)
            if band_max <= band_min:
                continue
            out[str(expiry)] = (band_min, band_max)
        return out

    def _adjust_premium_band(
        self,
        *,
        symbol: str,
        opt: dict,
        market_data: dict,
        base_band: tuple[float, float],
        spread_pct: float | None,
    ) -> tuple[float, float, dict]:
        min_p, max_p = base_band
        context: dict = {"base_min": min_p, "base_max": max_p}
        try:
            dte_threshold = int(getattr(cfg, "PREMIUM_BAND_DTE1_THRESHOLD", 1))
        except Exception:
            dte_threshold = 1
        dte_raw = opt.get("dte") or opt.get("days_to_expiry") or opt.get("dte_days")
        dte = None
        try:
            if dte_raw not in (None, "", "None"):
                dte = int(float(dte_raw))
        except Exception:
            dte = None
        if dte is not None and dte <= dte_threshold:
            min_mult = float(getattr(cfg, "PREMIUM_BAND_DTE1_MIN_MULT", 0.6))
            max_mult = float(getattr(cfg, "PREMIUM_BAND_DTE1_MAX_MULT", 0.8))
            min_p *= max(0.0, min_mult)
            max_p *= max(0.0, max_mult)
            context["dte"] = dte
            context["dte_mult"] = {"min": min_mult, "max": max_mult}
        regime = str(
            market_data.get("regime")
            or market_data.get("regime_state")
            or market_data.get("regime_label")
            or ""
        ).lower()
        if "high" in regime or "vol" in regime:
            max_mult = float(getattr(cfg, "PREMIUM_BAND_HIGH_VOL_MAX_MULT", 1.35))
            max_p *= max(0.0, max_mult)
            context["regime"] = regime
            context["regime_max_mult"] = max_mult
        if spread_pct is not None:
            try:
                tight_spread_pct = float(getattr(cfg, "PREMIUM_BAND_TIGHT_SPREAD_PCT", 0.8))
                if 0.0 < spread_pct <= tight_spread_pct:
                    spread_mult = float(getattr(cfg, "PREMIUM_BAND_TIGHT_SPREAD_MAX_MULT", 1.15))
                    max_p *= max(0.0, spread_mult)
                    context["spread_pct"] = spread_pct
                    context["spread_max_mult"] = spread_mult
            except Exception:
                pass
        min_p = max(0.0, float(min_p))
        max_p = max(min_p, float(max_p))
        context["adjusted_min"] = min_p
        context["adjusted_max"] = max_p
        context["symbol"] = symbol
        return min_p, max_p, context

    def _log_premium_band_debug(
        self,
        *,
        symbol: str,
        opt: dict,
        min_p: float,
        max_p: float,
        band_context: dict,
        spread_pct: float | None,
        reason: str,
        strategy_tag: str | None,
    ) -> None:
        logger.info(
            "PREMIUM_BAND_DEBUG %s",
            {
                "symbol": symbol,
                "tradingsymbol": opt.get("tradingsymbol"),
                "instrument_type": opt.get("instrument_type") or opt.get("instrument"),
                "option_type": opt.get("type") or opt.get("option_type") or opt.get("right"),
                "strike": opt.get("strike"),
                "premium": opt.get("ltp"),
                "band_min": min_p,
                "band_max": max_p,
                "expiry": opt.get("expiry_date") or opt.get("expiry"),
                "dte": opt.get("dte") or opt.get("days_to_expiry") or opt.get("dte_days"),
                "strategy_family": strategy_tag,
                "spread_pct": spread_pct,
                "reason": reason,
                "band_context": band_context,
            },
        )

    def _zero_to_hero_premium_band(
        self,
        chain_rows: list[dict],
        opt_type: str,
        expiry: str,
    ) -> tuple[float | None, float | None, str | None]:
        exp_text = self._coerce_date_str(expiry)
        pct_low = max(0.0, min(0.5, float(getattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_LOW", 0.02))))
        pct_high = max(0.1, min(0.95, float(getattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_HIGH", 0.25))))
        min_rows = max(4, int(getattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 8)))
        vals: list[float] = []
        for row in chain_rows or []:
            if not isinstance(row, dict):
                continue
            if row.get("type") != opt_type:
                continue
            row_exp = self._option_expiry(row, {"option_chain": []})
            if exp_text and row_exp and self._coerce_date_str(row_exp) != exp_text:
                continue
            ltp = self._coerce_positive_float(
                row.get("ltp")
                or row.get("last_price")
                or row.get("close")
                or row.get("price")
            )
            if ltp is None:
                continue
            vals.append(float(ltp))
        if len(vals) < min_rows:
            fallback_low = float(getattr(cfg, "ZERO_TO_HERO_PREMIUM_FALLBACK_LOW", 10.0))
            fallback_high = float(getattr(cfg, "ZERO_TO_HERO_PREMIUM_FALLBACK_HIGH", 120.0))
            if fallback_low > 0 and fallback_high > fallback_low:
                return fallback_low, fallback_high, "fallback_band"
            return None, None, "insufficient_rows"
        p_low = self._percentile(vals, pct_low)
        p_high = self._percentile(vals, pct_high)
        if p_low is None or p_high is None or p_high <= p_low:
            return None, None, "invalid_band"
        return float(p_low), float(p_high), "percentile"

    def _zero_to_hero_daily_ok(self) -> bool:
        today = now_ist().date().isoformat()
        if self._zero_to_hero_last_day != today:
            self._zero_to_hero_last_day = today
            self._zero_to_hero_daily_count = 0
        max_daily = int(getattr(cfg, "ZERO_TO_HERO_MAX_DAILY", 1))
        return self._zero_to_hero_daily_count < max_daily

    def _quick_neutral_fallback_signal(self, market_data: dict, ltp: float, vwap: float):
        if not bool(getattr(cfg, "QUICK_NEUTRAL_FALLBACK_ENABLE", True)):
            return None
        if ltp <= 0 or vwap <= 0:
            return None
        atr = float(market_data.get("atr") or 0.0)
        vwap_slope = float(market_data.get("vwap_slope") or 0.0)
        rsi_mom = float(market_data.get("rsi_mom") or 0.0)
        ltp_change = float(market_data.get("ltp_change") or 0.0)
        ltp_change_window = float(market_data.get("ltp_change_window") or 0.0)
        atr_ref = max(atr, max(float(ltp) * 0.0008, 1.0))
        vwap_dev = (float(ltp) - float(vwap)) / float(vwap)
        momentum = (ltp_change_window if ltp_change_window != 0 else ltp_change) / atr_ref
        edge = (
            vwap_dev * float(getattr(cfg, "QUICK_NEUTRAL_VWAP_DEV_WEIGHT", 35.0))
            + momentum * float(getattr(cfg, "QUICK_NEUTRAL_MOMENTUM_WEIGHT", 0.6))
            + vwap_slope * float(getattr(cfg, "QUICK_NEUTRAL_VWAP_SLOPE_WEIGHT", 120.0))
            + rsi_mom * float(getattr(cfg, "QUICK_NEUTRAL_RSI_MOM_WEIGHT", 0.2))
        )
        edge_min = float(getattr(cfg, "QUICK_NEUTRAL_EDGE_MIN", 0.18))
        if abs(edge) < edge_min:
            return None
        direction = "BUY_CALL" if edge > 0 else "BUY_PUT"
        base_score = float(getattr(cfg, "QUICK_NEUTRAL_SCORE_BASE", 0.53))
        edge_mult = float(getattr(cfg, "QUICK_NEUTRAL_SCORE_EDGE_MULT", 0.22))
        score_cap = float(getattr(cfg, "QUICK_NEUTRAL_SCORE_CAP", 0.68))
        score = min(score_cap, base_score + min(0.25, abs(edge) * edge_mult))
        return {
            "direction": direction,
            "reason": "Quick neutral edge fallback",
            "score": round(float(score), 4),
            "edge": round(float(edge), 6),
        }

    def _planning_signal_fallback_signal(self, market_data: dict, ltp: float, vwap: float):
        if not bool(getattr(cfg, "PLANNING_SIGNAL_FALLBACK_ENABLE", True)):
            return None
        if ltp <= 0 or vwap <= 0:
            return None
        vwap_edge = (float(ltp) - float(vwap)) / float(vwap)
        edge_min = float(getattr(cfg, "PLANNING_SIGNAL_VWAP_EDGE_MIN", 0.0008))
        if abs(vwap_edge) >= edge_min:
            direction = "BUY_CALL" if vwap_edge > 0 else "BUY_PUT"
            base = float(getattr(cfg, "PLANNING_SIGNAL_SCORE_BASE", 0.56))
            cap = float(getattr(cfg, "PLANNING_SIGNAL_SCORE_CAP", 0.66))
            score = min(cap, base + min(0.08, abs(vwap_edge) * 20.0))
            return {
                "direction": direction,
                "reason": "Planning VWAP fallback",
                "score": round(float(score), 4),
                "edge": round(float(vwap_edge), 6),
            }
        atr = float(market_data.get("atr") or 0.0)
        ltp_change_window = float(market_data.get("ltp_change_window") or 0.0)
        ltp_change = float(market_data.get("ltp_change") or 0.0)
        move = ltp_change_window if ltp_change_window != 0 else ltp_change
        atr_ref = max(atr, max(float(ltp) * 0.0008, 1.0))
        momentum_edge = float(move) / float(atr_ref)
        momentum_min = float(getattr(cfg, "PLANNING_SIGNAL_MOMENTUM_EDGE_MIN", 0.12))
        if abs(momentum_edge) < momentum_min:
            return None
        direction = "BUY_CALL" if momentum_edge > 0 else "BUY_PUT"
        base = float(getattr(cfg, "PLANNING_SIGNAL_SCORE_BASE", 0.56))
        cap = float(getattr(cfg, "PLANNING_SIGNAL_SCORE_CAP", 0.66))
        score = min(cap, base + min(0.08, abs(momentum_edge) * 0.12))
        return {
            "direction": direction,
            "reason": "Planning momentum fallback",
            "score": round(float(score), 4),
            "edge": round(float(momentum_edge), 6),
        }

    def _default_opportunity_direction(self, market_data: dict, ltp: float, vwap: float) -> str:
        bias = str(market_data.get("bias") or "").strip().upper()
        ltp_change_window = float(market_data.get("ltp_change_window") or 0.0)
        ltp_change = float(market_data.get("ltp_change") or 0.0)
        if ltp > 0 and vwap > 0:
            edge = (float(ltp) - float(vwap)) / max(float(vwap), 1e-6)
            if edge > 0.0002:
                return "BUY_CALL"
            if edge < -0.0002:
                return "BUY_PUT"
        move = ltp_change_window if abs(ltp_change_window) > 0 else ltp_change
        if move > 0:
            return "BUY_CALL"
        if move < 0:
            return "BUY_PUT"
        if bias in {"BEARISH", "DOWN"}:
            return "BUY_PUT"
        return "BUY_CALL"

    def _store_ranked_candidate_snapshots(self, ranked_candidates) -> None:
        snapshots = []
        for candidate in list(ranked_candidates or []):
            if isinstance(candidate, dict):
                snapshots.append(dict(candidate))
            else:
                snapshots.append(asdict(candidate))
        self._set_last_ranked_candidates(snapshots)

    def _execution_feasibility_score(self, trade: Trade | None) -> tuple[float, float, float]:
        if trade is None:
            return 0.0, 0.0, 0.0
        volume = max(float(getattr(trade, "volume", 0.0) or 0.0), float(getattr(trade, "current_volume", 0.0) or 0.0))
        min_volume = max(float(getattr(cfg, "MIN_VOLUME_FILTER", 1.0) or 1.0), 1.0)
        liquidity_score = max(0.0, min(1.0, volume / min_volume)) if volume > 0 else 0.35
        bid = self._coerce_positive_float(getattr(trade, "opt_bid", None))
        ask = self._coerce_positive_float(getattr(trade, "opt_ask", None))
        opt_ltp = self._coerce_positive_float(getattr(trade, "opt_ltp", None)) or self._coerce_positive_float(getattr(trade, "entry_price", None))
        if bid is not None and ask is not None and opt_ltp not in (None, 0.0):
            spread_pct = max(0.0, float(ask) - float(bid)) / max(float(opt_ltp), 1e-6)
            max_spread = max(float(getattr(cfg, "MAX_SPREAD_PCT", 0.03) or 0.03), 1e-6)
            spread_score = max(0.0, min(1.0, 1.0 - min(spread_pct / max_spread, 1.0)))
        else:
            spread_score = 0.5
        quote_score = 1.0 if bool(getattr(trade, "quote_ok", True)) else 0.4
        execution_feasibility_score = round(
            (liquidity_score * 0.4) + (spread_score * 0.4) + (quote_score * 0.2),
            6,
        )
        return execution_feasibility_score, liquidity_score, spread_score

    def _build_advisory_opportunity_trade(
        self,
        market_data: dict,
        *,
        ltp: float,
        vwap: float,
        direction: str | None,
        strategy: str,
        reason: str,
        confidence: float,
        strategy_family: str,
        candidate_type: str,
        setup_variant: str,
        trigger_reason: str,
        soft_veto_codes: list[str] | None = None,
        penalty_reasons: list[str] | None = None,
        quality_score: float | None = None,
        quality_detail: dict | None = None,
        direction_family: str | None = None,
        family_rank: int | None = None,
        family_blocker: str | None = None,
        family_strength: float | None = None,
        family_feedback_detail: dict | None = None,
    ):
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        underlying_ltp = float(ltp or 0.0)
        underlying_vwap = float(vwap or underlying_ltp or 0.0)
        if underlying_ltp <= 0:
            return None
        normalized_direction = str(direction or "").strip().upper()
        if normalized_direction not in {"BUY_CALL", "BUY_PUT"}:
            normalized_direction = self._default_opportunity_direction(
                market_data,
                underlying_ltp,
                underlying_vwap,
            )
        side = "BUY" if normalized_direction == "BUY_CALL" else "SELL"
        underlying_atr = float(market_data.get("atr") or max(1.0, underlying_ltp * 0.002))
        entry_price = underlying_ltp
        stop_loss = (
            max(0.01, entry_price - underlying_atr)
            if side == "BUY"
            else max(0.01, entry_price + underlying_atr)
        )
        target = (
            entry_price + (underlying_atr * 1.5)
            if side == "BUY"
            else max(0.01, entry_price - (underlying_atr * 1.5))
        )
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

        instrument = "EQ"
        expiry = ""
        strike = 0
        right = None
        option_type = None
        chosen_opt = None
        tradingsymbol = None
        instrument_token = None
        opt_type = "CE" if normalized_direction == "BUY_CALL" else "PE"
        chain = market_data.get("option_chain") or []
        try:
            valid_opts = []
            for raw_opt in chain:
                norm_opt, _ = self._normalize_option_row(raw_opt, expected_type=opt_type)
                if not norm_opt:
                    continue
                valid_opts.append(norm_opt)
            if valid_opts:
                chosen_opt = min(
                    valid_opts,
                    key=lambda opt: abs(float(opt.get("strike") or 0.0) - underlying_ltp),
                )
                instrument = "OPT"
                expiry = self._option_expiry(chosen_opt, market_data)
                strike = int(float(chosen_opt.get("strike") or 0.0))
                right = str(chosen_opt.get("type") or opt_type)
                option_type = right
                tradingsymbol = chosen_opt.get("tradingsymbol")
                instrument_token = chosen_opt.get("instrument_token")
                option_entry_price = float(chosen_opt.get("ltp") or 0.0)
                if option_entry_price > 0:
                    entry_price = option_entry_price
                option_bid = float(chosen_opt.get("bid") or entry_price)
                option_ask = float(chosen_opt.get("ask") or entry_price)
                option_width = max(0.0, option_ask - option_bid)
                option_risk_proxy = self._option_risk_proxy(entry_price, option_bid, option_ask)
                stop_loss, target = self._opt_risk_levels(
                    entry_price,
                    option_bid,
                    option_ask,
                    option_risk_proxy,
                    stop_mult=1.0,
                    target_mult=1.4,
                )
                if side == "BUY" and target <= entry_price:
                    target = round(
                        entry_price + max(option_risk_proxy * 1.4, option_width, 0.01),
                        2,
                    )
                if side == "BUY" and stop_loss >= entry_price:
                    stop_loss = round(
                        max(0.01, entry_price - max(option_risk_proxy, option_width, 0.01)),
                        2,
                    )
                if side == "SELL" and target >= entry_price:
                    target = round(
                        max(0.01, entry_price - max(option_risk_proxy * 1.4, option_width, 0.01)),
                        2,
                    )
                if side == "SELL" and stop_loss <= entry_price:
                    stop_loss = round(
                        entry_price + max(option_risk_proxy, option_width, 0.01),
                        2,
                    )
        except Exception:
            chosen_opt = None

        instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
            symbol,
            instrument,
            expiry,
            strike,
            right,
            1,
        )
        option_identity_ok, _missing_option_fields = self._option_identity_complete(
            instrument=instrument,
            instrument_type=instrument_type,
            right=right,
            expiry=expiry,
            tradingsymbol=tradingsymbol,
            instrument_token=instrument_token,
            instrument_id=instrument_id,
        )
        if instrument == "OPT" and (ident_err or not option_identity_ok):
            chosen_opt = None
            instrument = "EQ"
            tradingsymbol = None
            instrument_token = None
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                instrument,
                "",
                0,
                None,
                1,
            )
            if ident_err:
                return None
            strike = 0
            expiry = ""
            option_type = None
            right = None

        if instrument == "OPT":
            if side == "BUY" and not (target > entry_price > stop_loss):
                return None
            if side == "SELL" and not (stop_loss > entry_price > target):
                return None

        soft_codes = [str(code) for code in (soft_veto_codes or []) if str(code).strip()]
        penalty_codes = [str(code) for code in (penalty_reasons or []) if str(code).strip()]
        intent = self.trade_intent_flags(market_data, opt=chosen_opt)
        current_mode = str(
            market_data.get("execution_mode")
            or ((market_data.get("market_context") or {}).get("execution_mode") if isinstance(market_data.get("market_context"), dict) else "")
            or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).strip().upper()
        opportunity_confidence = self._clamp_confidence(confidence)
        if opportunity_confidence is None:
            opportunity_confidence = float(getattr(cfg, "PLANNING_SIGNAL_SCORE_BASE", 0.56))
        opportunity_confidence = round(float(opportunity_confidence), 3)
        candidate_quality_score = self._clamp_confidence(quality_score)
        if candidate_quality_score is None:
            candidate_quality_score = opportunity_confidence
        candidate_quality_score = round(float(candidate_quality_score), 6)
        quality_detail_map = dict(quality_detail or {})
        family_allowed_in_context = quality_detail_map.get("family_allowed_in_context")
        family_gate_reason = quality_detail_map.get("family_gate_reason")
        family_gate_override_applied = bool(quality_detail_map.get("family_gate_override_applied", False))
        session_ctx = classify_session_mode(market_data)
        session_mode = str(
            quality_detail_map.get("session_mode") or session_ctx.get("session_mode") or "OFFHOURS"
        ).strip().upper() or "OFFHOURS"
        session_policy = cfg.get_session_policy(session_mode)
        session_entry_penalty = round(
            float(
                quality_detail_map.get("session_entry_penalty")
                if quality_detail_map.get("session_entry_penalty") is not None
                else (session_ctx.get("session_entry_penalty") or 0.0)
            ),
            6,
        )
        strategy_regime_mode = str(
            quality_detail_map.get("strategy_regime_mode")
            or (classify_strategy_regime_mode(market_data).get("regime_mode"))
            or "UNCERTAIN"
        ).strip().upper() or "UNCERTAIN"
        regime_policy = cfg.get_regime_policy(strategy_regime_mode)
        allow_nonlive_executable = bool(getattr(cfg, "NONLIVE_OPPORTUNITY_EXECUTION_ENABLE", True))
        min_exec_quality = float(getattr(cfg, "NONLIVE_OPPORTUNITY_EXECUTION_MIN_SCORE", 0.34))
        executable_nonlive = bool(
            allow_nonlive_executable
            and current_mode in {"SIM", "PAPER", "OFFHOURS"}
            and float(candidate_quality_score) >= float(min_exec_quality)
        )
        intent["planning_only"] = False if executable_nonlive else True
        intent["execution_allowed"] = bool(executable_nonlive)
        intent["execution_reason"] = ("nonlive_opportunity_executable" if executable_nonlive else trigger_reason)
        source_flags = dict(intent.get("source_flags") or {})
        source_flags["nonlive_opportunity_executable"] = bool(executable_nonlive)
        source_flags["nonlive_opportunity_min_exec_quality"] = round(float(min_exec_quality), 6)
        source_flags["candidate_origin"] = "opportunity_builder_nonlive"
        source_flags["opportunity_builder"] = strategy
        source_flags["opportunity_trigger_reason"] = trigger_reason
        source_flags["opportunity_variant"] = setup_variant
        source_flags["strategy_regime_mode"] = strategy_regime_mode
        source_flags["session_mode"] = session_mode
        source_flags["session_entry_penalty"] = session_entry_penalty
        source_flags["effective_session_policy"] = dict(session_policy)
        source_flags["effective_regime_policy"] = dict(cfg.get_regime_policy(strategy_regime_mode))
        source_flags["effective_family_survival_policy"] = dict(
            cfg.get_family_survival_policy(strategy_family, session_mode, strategy_regime_mode)
        )
        source_flags["direction_family"] = str(direction_family or "sideways").strip().lower() or "sideways"
        source_flags["family_rank"] = int(family_rank) if family_rank is not None else None
        source_flags["family_blocker"] = (
            str(family_blocker).strip().lower() if family_blocker not in (None, "", "None") else None
        )
        source_flags["family_strength"] = (
            round(float(family_strength), 6) if family_strength is not None else None
        )
        source_flags["family_allowed_in_context"] = (
            bool(family_allowed_in_context) if family_allowed_in_context is not None else None
        )
        source_flags["family_gate_reason"] = (
            str(family_gate_reason).strip().lower() if family_gate_reason not in (None, "", "None") else None
        )
        source_flags["family_gate_override_applied"] = bool(family_gate_override_applied)
        if isinstance(family_feedback_detail, dict):
            for key in (
                "family_feedback_adjustment",
                "family_feedback_confidence",
                "family_feedback_applied",
                "family_learning_adjustment",
                "family_cap_effective",
                "family_cap_reason",
                "family_consensus_score",
                "family_consensus_components",
                "family_survived",
                "family_reject_reason",
                "expectancy_score",
                "family_learning_state_generated_at",
                "family_learning_state_version",
                "strategy_weight_adjustment",
                "strategy_weight_confidence",
                "strategy_weight_applied",
                "strategy_weight_state_generated_at",
                "strategy_weight_state_version",
            ):
                if key in family_feedback_detail:
                    source_flags[key] = family_feedback_detail.get(key)
        existing_soft = [str(code) for code in (source_flags.get("soft_veto_codes") or []) if str(code).strip()]
        for code in soft_codes:
            if code not in existing_soft:
                existing_soft.append(code)
        source_flags["soft_veto_codes"] = existing_soft
        liquidity_fields = self._option_liquidity_fields(chosen_opt) if instrument == "OPT" else {}
        reason_codes = list(dict.fromkeys([str(trigger_reason)] + existing_soft + penalty_codes))
        trade_score = round(float(candidate_quality_score) * 100.0, 2)
        trade = Trade(
            trade_id=f"{symbol}-{setup_variant.upper()}-{ts}",
            timestamp=datetime.now(),
            symbol=symbol,
            instrument=instrument,
            instrument_type=instrument_type,
            right=right,
            instrument_id=instrument_id,
            instrument_token=instrument_token,
            strike=int(strike),
            expiry=str(expiry),
            option_type=option_type,
            tradingsymbol=tradingsymbol,
            side=side,
            entry_price=round(float(entry_price), 2),
            stop_loss=round(float(stop_loss), 2),
            target=round(float(target), 2),
            qty=1,
            qty_lots=1,
            qty_units=qty_units,
            validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
            capital_at_risk=round(abs(float(entry_price) - float(stop_loss)), 2),
            expected_slippage=0.0,
            confidence=opportunity_confidence,
            strategy=strategy,
            regime=str(market_data.get("regime") or "NEUTRAL"),
            tier="EXPLORATION",
            day_type=str(market_data.get("day_type") or "UNKNOWN"),
            **liquidity_fields,
            quote_ok=bool(market_data.get("quote_ok", True)),
            tradable=bool(intent.get("tradable", True)),
            tradable_reasons_blocking=list(intent.get("tradable_reasons_blocking") or []),
            planning_only=True,
            execution_allowed=False,
            reason=reason,
            source_flags=source_flags,
            trade_score=trade_score,
            rank_score=candidate_quality_score,
            setup_strength=candidate_quality_score,
            trade_score_detail={
                "score": trade_score,
                "builder_variant": setup_variant,
                "trigger_reason": trigger_reason,
                "penalty_reasons": penalty_codes,
                "signal_score": opportunity_confidence,
                "candidate_quality_score": candidate_quality_score,
            },
            direction=normalized_direction,
            candidate_type=candidate_type,
            strategy_family=strategy_family,
            direction_family=str(source_flags.get("direction_family") or "sideways"),
            family_rank=source_flags.get("family_rank"),
            family_blocker=source_flags.get("family_blocker"),
            family_strength=source_flags.get("family_strength"),
            family_allowed_in_context=source_flags.get("family_allowed_in_context"),
            family_gate_reason=source_flags.get("family_gate_reason"),
            family_gate_override_applied=source_flags.get("family_gate_override_applied"),
            family_feedback_adjustment=source_flags.get("family_feedback_adjustment"),
            family_feedback_confidence=source_flags.get("family_feedback_confidence"),
            family_feedback_applied=source_flags.get("family_feedback_applied"),
            family_learning_adjustment=source_flags.get("family_learning_adjustment"),
            family_cap_effective=source_flags.get("family_cap_effective"),
            family_cap_reason=source_flags.get("family_cap_reason"),
            family_consensus_score=source_flags.get("family_consensus_score"),
            family_consensus_components=source_flags.get("family_consensus_components") or {},
            family_survived=source_flags.get("family_survived"),
            family_reject_reason=source_flags.get("family_reject_reason"),
            expectancy_score=source_flags.get("expectancy_score"),
            family_learning_state_generated_at=source_flags.get("family_learning_state_generated_at"),
            family_learning_state_version=source_flags.get("family_learning_state_version"),
            strategy_weight_adjustment=source_flags.get("strategy_weight_adjustment"),
            strategy_weight_confidence=source_flags.get("strategy_weight_confidence"),
            strategy_weight_applied=source_flags.get("strategy_weight_applied"),
            strategy_weight_state_generated_at=source_flags.get("strategy_weight_state_generated_at"),
            strategy_weight_state_version=source_flags.get("strategy_weight_state_version"),
            effective_session_policy=source_flags.get("effective_session_policy") or {},
            effective_regime_policy=source_flags.get("effective_regime_policy") or {},
            effective_risk_policy=source_flags.get("effective_risk_policy") or {},
            effective_family_risk_profile=source_flags.get("effective_family_risk_profile") or {},
            risk_profile_override_applied=source_flags.get("risk_profile_override_applied"),
            effective_family_survival_policy=source_flags.get("effective_family_survival_policy") or {},
            setup_variant=setup_variant,
            candidate_status=("executable" if executable_nonlive else "advisory_only"),
            permission=("EXECUTE" if executable_nonlive else "ADVISORY_ONLY"),
            permission_reason=("nonlive_opportunity_executable" if executable_nonlive else trigger_reason),
            reason_codes=reason_codes,
            penalty_reasons=penalty_codes,
            **self._staged_confidence_payload(
                confidence=opportunity_confidence,
                model_raw=opportunity_confidence,
                model_component=opportunity_confidence,
                micro_blend_method="model_only",
                before_soft_veto=opportunity_confidence,
                after_soft_veto=opportunity_confidence,
                penalty_soft_veto_total=0.0,
                penalty_soft_veto_reasons=existing_soft,
                base=opportunity_confidence,
                penalty_total=0.0,
                penalty_reasons=penalty_codes,
            ),
        )
        built_trade = self._decorate_trade_context(trade, market_data, opportunity_confidence)
        if built_trade is not None:
            execution_feasibility_score, liquidity_score, spread_score = self._execution_feasibility_score(built_trade)
            trade_source_flags = dict(getattr(built_trade, "source_flags", {}) or {})
            family_consensus_components = dict(trade_source_flags.get("family_consensus_components") or {})
            direction_family_norm = (
                str(trade_source_flags.get("direction_family") or direction_family or "sideways").strip().lower()
                or "sideways"
            )
            atr_value = max(float(quality_detail_map.get("atr") or underlying_atr or 1.0), 1e-6)
            breakout_strength = float(quality_detail_map.get("breakout_strength") or 0.0)
            mean_reversion_strength = float(quality_detail_map.get("mean_reversion_strength") or 0.0)
            volatility_expansion_strength = float(quality_detail_map.get("volatility_expansion_strength") or 0.0)
            range_edge_strength = float(quality_detail_map.get("range_edge_strength") or 0.0)
            directional_signal_present = bool(quality_detail_map.get("directional_signal_present"))
            mean_signal_present = bool(quality_detail_map.get("mean_signal_present"))
            expansion_signal_present = bool(quality_detail_map.get("expansion_signal_present"))
            support_touch = bool(quality_detail_map.get("support_touch"))
            resistance_touch = bool(quality_detail_map.get("resistance_touch"))
            clean_range_edge = bool(quality_detail_map.get("clean_range_edge"))
            range_compression = bool(quality_detail_map.get("range_compression"))
            market_quality_score = self._clamp_confidence(quality_detail_map.get("market_quality_score")) or 0.0
            regime_alignment_component = self._clamp_confidence(
                family_consensus_components.get("regime_alignment"),
            )
            if regime_alignment_component is None:
                if direction_family_norm == "bullish":
                    regime_alignment_component = 1.0 if strategy_regime_mode == "TRENDING" else 0.35
                elif direction_family_norm == "bearish":
                    regime_alignment_component = 1.0 if strategy_regime_mode == "TRENDING" else 0.35
                else:
                    regime_alignment_component = 1.0 if strategy_regime_mode == "SIDEWAYS" else 0.45
            if direction_family_norm == "bullish":
                structure_component = max(
                    0.0,
                    min(1.0, float(quality_detail_map.get("bullish_structure_strength") or 0.0) / 5.0),
                )
            elif direction_family_norm == "bearish":
                structure_component = max(
                    0.0,
                    min(1.0, float(quality_detail_map.get("bearish_structure_strength") or 0.0) / 5.0),
                )
            else:
                structure_component = max(
                    0.0,
                    min(1.0, max(range_edge_strength, float(source_flags.get("family_strength") or 0.0) / 5.0)),
                )
            setup_score = round(
                float(
                    self._clamp_confidence(
                        (
                            float(regime_alignment_component) * float(getattr(cfg, "SETUP_SCORE_WEIGHT_REGIME", 0.40))
                            + float(structure_component) * float(getattr(cfg, "SETUP_SCORE_WEIGHT_STRUCTURE", 0.35))
                            + float(candidate_quality_score) * float(getattr(cfg, "SETUP_SCORE_WEIGHT_THESIS", 0.25))
                        )
                    )
                    or 0.0
                ),
                6,
            )
            if strategy == "OPP_DIRECTIONAL":
                trigger_base = (
                    min(1.0, breakout_strength / 1.60)
                    + (0.10 if directional_signal_present else 0.0)
                    + (0.05 if abs(float(quality_detail_map.get("ltp_change_window") or 0.0)) >= (atr_value * 0.15) else 0.0)
                )
            elif strategy == "OPP_MEAN_REVERT":
                trigger_base = (
                    min(1.0, mean_reversion_strength / 1.50)
                    + (0.08 if mean_signal_present else 0.0)
                    + (0.08 if (support_touch or resistance_touch) else 0.0)
                )
            elif strategy == "OPP_VOL_EXPANSION":
                trigger_base = (
                    min(1.0, volatility_expansion_strength / 1.65)
                    + (0.10 if expansion_signal_present else 0.0)
                )
            else:
                trigger_base = (
                    0.35
                    + (0.18 if clean_range_edge else 0.0)
                    + (0.12 if range_compression else 0.0)
                    + (0.14 if (support_touch or resistance_touch) else 0.0)
                    + min(0.21, range_edge_strength * 0.08)
                )
            trigger_score_raw = float(self._clamp_confidence(trigger_base) or 0.0)
            trigger_gate_reason = None
            if session_mode == "MIDDAY" and candidate_type in {"directional", "volatility_expansion"}:
                midday_trigger_min = float(session_policy.get("directional_trigger_min") or 0.66)
                if trigger_score_raw < midday_trigger_min:
                    trigger_gate_reason = "midday_trigger_too_weak"
                trigger_score = float(
                    self._clamp_confidence(trigger_score_raw - (session_entry_penalty * 0.75))
                    or 0.0
                )
            elif session_mode == "CLOSING":
                trigger_score = float(
                    self._clamp_confidence(trigger_score_raw - (session_entry_penalty * 0.60))
                    or 0.0
                )
            elif session_mode == "OPENING" and candidate_type in {"directional", "volatility_expansion"}:
                trigger_score = float(
                    self._clamp_confidence(trigger_score_raw + 0.04 - (session_entry_penalty * 0.25))
                    or 0.0
                )
            else:
                trigger_score = float(
                    self._clamp_confidence(trigger_score_raw - (session_entry_penalty * 0.35))
                    or 0.0
                )
            trigger_base_score = round(float(trigger_base), 6)
            stop_distance = abs(float(getattr(built_trade, "entry_price", 0.0) or 0.0) - float(getattr(built_trade, "stop_loss", 0.0) or 0.0))
            entry_distance_to_invalidation = (
                round(float(stop_distance) / atr_value, 6) if atr_value > 0 and stop_distance > 0 else None
            )
            stop_distance_pct = (
                float(stop_distance) / max(float(getattr(built_trade, "entry_price", 0.0) or 0.0), 1e-6)
                if stop_distance > 0
                else None
            )
            invalidation_stretch = 0.0
            if stop_distance_pct is not None:
                invalidation_stretch = max(
                    float(stop_distance_pct) / max(float(getattr(cfg, "ENTRY_INVALIDATION_DISTANCE_MAX_PCT", 0.35) or 0.35), 1e-6),
                    float(entry_distance_to_invalidation or 0.0) / max(float(getattr(cfg, "ENTRY_INVALIDATION_DISTANCE_MAX_ATR", 1.80) or 1.80), 1e-6),
                )
            invalidation_score = round(
                float(self._clamp_confidence(1.0 - min(1.0, invalidation_stretch * 0.75)) or 0.0),
                6,
            )
            vwap_extension_atr = abs(float(underlying_ltp) - float(underlying_vwap)) / atr_value
            move_extension_atr = abs(float(quality_detail_map.get("ltp_change_window") or 0.0)) / atr_value
            overextension_reason = None
            if candidate_type in {"mean_reversion", "watchlist"}:
                stretch_atr = max(vwap_extension_atr, range_edge_strength)
                min_stretch = max(float(getattr(cfg, "MEAN_REVERSION_MIN_STRETCH_ATR", 0.45) or 0.45), 1e-6)
                overextension_score = round(
                    float(self._clamp_confidence(stretch_atr / min_stretch) or 0.0),
                    6,
                )
                overextension_penalty = round(max(0.0, 1.0 - float(overextension_score)), 6)
                if float(overextension_score) < 0.50:
                    overextension_reason = "insufficient_stretch"
            else:
                vwap_soft = max(float(getattr(cfg, "ENTRY_OVEREXTENSION_VWAP_ATR_SOFT", 1.0) or 1.0), 1e-6)
                vwap_hard = max(float(getattr(cfg, "ENTRY_OVEREXTENSION_VWAP_ATR_HARD", 2.0) or 2.0), vwap_soft + 1e-6)
                move_soft = max(float(getattr(cfg, "ENTRY_OVEREXTENSION_MOVE_ATR_SOFT", 1.2) or 1.2), 1e-6)
                move_hard = max(float(getattr(cfg, "ENTRY_OVEREXTENSION_MOVE_ATR_HARD", 2.4) or 2.4), move_soft + 1e-6)
                overextension_penalty = round(
                    float(
                        self._clamp_confidence(
                            max(
                                max(0.0, (vwap_extension_atr - vwap_soft) / (vwap_hard - vwap_soft)),
                                max(0.0, (move_extension_atr - move_soft) / (move_hard - move_soft)),
                            )
                        )
                        or 0.0
                    ),
                    6,
                )
                overextension_score = round(max(0.0, 1.0 - float(overextension_penalty)), 6)
                if float(overextension_penalty) >= 0.50:
                    overextension_reason = "overextended_entry"
            timing_quality = round(float(self._clamp_confidence(1.0 - session_entry_penalty) or 0.0), 6)
            entry_quality_score = round(
                float(
                    self._clamp_confidence(
                        (
                            float(invalidation_score) * float(getattr(cfg, "ENTRY_QUALITY_WEIGHT_INVALIDATION", 0.35))
                            + float(overextension_score) * float(getattr(cfg, "ENTRY_QUALITY_WEIGHT_OVEREXTENSION", 0.35))
                            + float(execution_feasibility_score) * float(getattr(cfg, "ENTRY_QUALITY_WEIGHT_EXECUTION_FIT", 0.20))
                            + float(timing_quality) * float(getattr(cfg, "ENTRY_QUALITY_WEIGHT_SESSION", 0.10))
                        )
                    )
                    or 0.0
                ),
                6,
            )
            entry_quality_reason = "ok"
            if trigger_gate_reason is not None:
                entry_quality_reason = trigger_gate_reason
            elif overextension_reason is not None:
                entry_quality_reason = overextension_reason
            elif invalidation_score < 0.30:
                entry_quality_reason = "far_from_invalidation"
            family_consensus_score = round(
                float(trade_source_flags.get("family_consensus_score") or 0.0),
                6,
            )
            family_survival_policy = cfg.get_family_survival_policy(
                strategy_family,
                session_mode,
                strategy_regime_mode,
            )
            family_survival_score = round(
                float(
                    self._clamp_confidence(
                        (
                            float(setup_score) * float(family_survival_policy.get("weight_setup", 0.30))
                            + float(trigger_score) * float(family_survival_policy.get("weight_trigger", 0.25))
                            + float(entry_quality_score) * float(family_survival_policy.get("weight_entry_quality", 0.25))
                            + float(execution_feasibility_score) * float(family_survival_policy.get("weight_execution", 0.10))
                            + float(family_consensus_score) * float(family_survival_policy.get("weight_consensus", 0.10))
                        )
                    )
                    or 0.0
                ),
                6,
            )
            family_survival_components = {
                "setup_score": round(float(setup_score), 6),
                "trigger_score": round(float(trigger_score), 6),
                "entry_quality_score": round(float(entry_quality_score), 6),
                "execution_feasibility_score": round(float(execution_feasibility_score), 6),
                "family_consensus_score": round(float(family_consensus_score), 6),
                "regime_alignment": round(float(regime_alignment_component), 6),
                "structure_strength": round(float(structure_component), 6),
            }
            component_floor = float(family_survival_policy.get("component_min", 0.26) or 0.26)
            survival_floor = float(family_survival_policy.get("min_score", 0.42) or 0.42)
            executable_survival_floor = float(family_survival_policy.get("executable_min_score", 0.55) or 0.55)
            weakest_survival_component = min(float(setup_score), float(trigger_score), float(entry_quality_score))
            risk_assessment = evaluate_candidate_risk(
                built_trade,
                portfolio_state=dict(market_data.get("portfolio_state") or {}),
            )
            hard_execution_blockers: list[str] = []
            if trigger_gate_reason is not None:
                hard_execution_blockers.append(trigger_gate_reason)
            if candidate_type in {"directional", "volatility_expansion"} and overextension_penalty >= 0.65:
                hard_execution_blockers.append("overextended_entry")
            if candidate_type in {"mean_reversion", "watchlist"} and overextension_score < 0.45:
                hard_execution_blockers.append("insufficient_stretch")
            if invalidation_score < 0.20:
                hard_execution_blockers.append("far_from_invalidation")
            if family_survival_score < executable_survival_floor or weakest_survival_component < component_floor:
                hard_execution_blockers.append("family_survival_below_threshold")
            if not bool(risk_assessment.risk_budget_ok):
                hard_execution_blockers.append(f"risk_budget_{risk_assessment.risk_budget_reason}")
            if risk_assessment.exposure_blocker:
                hard_execution_blockers.append(str(risk_assessment.exposure_blocker))
            if bool(risk_assessment.daily_kill_switch_active):
                hard_execution_blockers.append("daily_kill_switch_active")
            if float(risk_assessment.regime_failure_throttle or 0.0) > 0.0:
                hard_execution_blockers.append("regime_failure_throttle")
            if float(risk_assessment.family_failure_throttle or 0.0) > 0.0:
                hard_execution_blockers.append("family_failure_throttle")
            hard_execution_blockers = list(dict.fromkeys(hard_execution_blockers))
            primary_rejection_reason = hard_execution_blockers[0] if hard_execution_blockers else None
            rejection_meta = apply_stage_authority(
                {
                    "existing_rejected_at_stage": getattr(built_trade, "rejected_at_stage", None),
                    "existing_rejection_reason_code": getattr(built_trade, "rejection_reason_code", None),
                    "incoming_rejected_at_stage": None,
                    "incoming_rejection_reason_code": primary_rejection_reason,
                }
            )
            soft_candidate_viable = bool(
                family_survival_score >= survival_floor
                and weakest_survival_component >= max(component_floor * 0.85, 0.10)
            )
            execution_ready = bool(
                getattr(built_trade, "execution_entry", None) is not None
                and str(getattr(built_trade, "execution_entry_status", "")).strip().lower() == "executable"
            )
            execution_allowed_final = bool(
                executable_nonlive
                and current_mode in {"SIM", "PAPER"}
                and execution_ready
                and not hard_execution_blockers
            )
            candidate_status_final = (
                "executable"
                if execution_allowed_final
                else ("near_executable" if (execution_ready and soft_candidate_viable) else "advisory_only")
            )
            planning_only_final = not execution_allowed_final
            tradable_reasons = list(getattr(built_trade, "tradable_reasons_blocking", []) or [])
            for blocker in hard_execution_blockers:
                if blocker not in tradable_reasons:
                    tradable_reasons.append(blocker)
            if quality_detail_map:
                trade_source_flags["quality_detail"] = dict(quality_detail_map)
            setup_telemetry_fields = self._setup_telemetry_fields(
                built_trade,
                trade_source_flags,
                trade_source_flags.get("decision_trace") or {},
                candidate_quality_score=candidate_quality_score,
                trigger_base_score=trigger_base_score,
                invalidation_score=invalidation_score,
                overextension_score=overextension_score,
                timing_quality_score=timing_quality,
            )
            trade_source_flags.update(
                {
                    "candidate_quality_score": candidate_quality_score,
                    "execution_feasibility_score": round(float(execution_feasibility_score), 6),
                    "execution_quality_score": round(float(execution_feasibility_score), 6),
                    "setup_score": round(float(setup_score), 6),
                    "trigger_score": round(float(trigger_score), 6),
                    "trigger_base_score": trigger_base_score,
                    "entry_quality_score": round(float(entry_quality_score), 6),
                    "entry_quality_reason": entry_quality_reason,
                    "entry_invalidation_score": round(float(invalidation_score), 6),
                    "overextension_score": round(float(overextension_score), 6),
                    "entry_overextension_score": round(float(overextension_score), 6),
                    "overextension_penalty": round(float(overextension_penalty), 6),
                    "entry_distance_to_invalidation": entry_distance_to_invalidation,
                    "entry_timing_quality_score": round(float(timing_quality), 6),
                    "execution_quality_score": round(float(execution_feasibility_score), 6),
                    "session_mode": session_mode,
                    "session_entry_penalty": round(float(session_entry_penalty), 6),
                    "family_survival_score": round(float(family_survival_score), 6),
                    "family_survival_components": dict(family_survival_components),
                    "family_survived": bool(soft_candidate_viable),
                    "family_reject_reason": primary_rejection_reason,
                    "rejected_at_stage": rejection_meta.get("rejected_at_stage"),
                    "rejection_reason_code": rejection_meta.get("rejection_reason_code"),
                    "rejection_bucket": rejection_meta.get("rejection_bucket"),
                    "rejection_severity": rejection_meta.get("rejection_severity"),
                    "stage_authority_warning": bool(
                        rejection_meta.get("stage_authority_warning", False)
                        or getattr(risk_assessment, "stage_authority_warning", False)
                    ),
                    "risk_budget_ok": bool(risk_assessment.risk_budget_ok),
                    "risk_budget_reason": str(risk_assessment.risk_budget_reason),
                    "position_size_estimate": int(risk_assessment.position_size_estimate),
                    "portfolio_heat_score": round(float(risk_assessment.portfolio_heat_score), 6),
                    "correlation_penalty": round(float(risk_assessment.correlation_penalty), 6),
                    "exposure_blocker": risk_assessment.exposure_blocker,
                    "daily_kill_switch_active": bool(risk_assessment.daily_kill_switch_active),
                    "regime_failure_throttle": round(float(risk_assessment.regime_failure_throttle), 6),
                    "family_failure_throttle": round(float(risk_assessment.family_failure_throttle), 6),
                    "risk_learning_adjustment": round(float(risk_assessment.risk_learning_adjustment), 6),
                    "risk_learning_confidence": round(float(risk_assessment.risk_learning_confidence), 6),
                    "candidate_status": candidate_status_final,
                    "execution_allowed": bool(execution_allowed_final),
                    "planning_only": bool(planning_only_final),
                    "hard_execution_blockers": list(hard_execution_blockers),
                    **setup_telemetry_fields,
                }
            )
            ranking_score = round(
                max(
                    0.0,
                    min(
                        1.0,
                        float(candidate_quality_score)
                        - (max(0.0, 1.0 - float(execution_feasibility_score)) * 0.12)
                        - (float(overextension_penalty) * 0.18)
                        - (float(session_entry_penalty) * 0.10)
                        - (0.10 if not bool(risk_assessment.risk_budget_ok) else 0.0)
                        - (float(risk_assessment.correlation_penalty or 0.0) * 0.12)
                        - (float(risk_assessment.regime_failure_throttle or 0.0) * 0.30)
                        - (float(risk_assessment.family_failure_throttle or 0.0) * 0.30)
                        + (float(risk_assessment.risk_learning_adjustment or 0.0) * 0.50),
                    ),
                ),
                6,
            )
            trade_source_flags["ranking_score"] = ranking_score
            score_breakdown = dict(getattr(built_trade, "score_breakdown", {}) or {})
            score_breakdown.update(
                {
                    "candidate_quality_score": candidate_quality_score,
                    "execution_feasibility_score": execution_feasibility_score,
                    "execution_quality_score": execution_feasibility_score,
                    "ranking_score": ranking_score,
                    "trigger_reason": trigger_reason,
                    "direction_family": trade_source_flags.get("direction_family"),
                    "family_rank": trade_source_flags.get("family_rank"),
                    "family_blocker": trade_source_flags.get("family_blocker"),
                    "family_strength": trade_source_flags.get("family_strength"),
                    "family_feedback_adjustment": trade_source_flags.get("family_feedback_adjustment"),
                    "family_feedback_confidence": trade_source_flags.get("family_feedback_confidence"),
                    "family_feedback_applied": trade_source_flags.get("family_feedback_applied"),
                    "family_learning_adjustment": trade_source_flags.get("family_learning_adjustment"),
                    "family_cap_effective": trade_source_flags.get("family_cap_effective"),
                    "family_cap_reason": trade_source_flags.get("family_cap_reason"),
                    "family_consensus_score": trade_source_flags.get("family_consensus_score"),
                    "family_consensus_components": trade_source_flags.get("family_consensus_components"),
                    "family_survival_score": trade_source_flags.get("family_survival_score"),
                    "family_survival_components": trade_source_flags.get("family_survival_components"),
                    "family_survived": soft_candidate_viable,
                    "family_reject_reason": (hard_execution_blockers[0] if hard_execution_blockers else None),
                    "rejected_at_stage": rejection_meta.get("rejected_at_stage"),
                    "rejection_reason_code": rejection_meta.get("rejection_reason_code"),
                    "rejection_bucket": rejection_meta.get("rejection_bucket"),
                    "rejection_severity": rejection_meta.get("rejection_severity"),
                    "expectancy_score": trade_source_flags.get("expectancy_score"),
                    "strategy_weight_adjustment": trade_source_flags.get("strategy_weight_adjustment"),
                    "strategy_weight_confidence": trade_source_flags.get("strategy_weight_confidence"),
                    "strategy_weight_applied": trade_source_flags.get("strategy_weight_applied"),
                    "strategy_regime_mode": strategy_regime_mode,
                    "session_mode": session_mode,
                    "session_entry_penalty": session_entry_penalty,
                    "setup_score": setup_score,
                    "trigger_score": trigger_score,
                    "trigger_base_score": trigger_base_score,
                    "entry_quality_score": entry_quality_score,
                    "entry_quality_reason": entry_quality_reason,
                    "entry_invalidation_score": invalidation_score,
                    "overextension_score": overextension_score,
                    "entry_overextension_score": overextension_score,
                    "overextension_penalty": overextension_penalty,
                    "entry_distance_to_invalidation": entry_distance_to_invalidation,
                    "entry_timing_quality_score": timing_quality,
                    "execution_quality_score": execution_feasibility_score,
                    "risk_assessment": risk_assessment.to_dict(),
                    "effective_session_policy": dict(session_policy),
                    "effective_regime_policy": dict(regime_policy),
                    "effective_risk_policy": dict((risk_assessment.context or {}).get("effective_risk_policy") or {}),
                    "effective_family_risk_profile": dict((risk_assessment.context or {}).get("effective_family_risk_profile") or {}),
                    "risk_profile_override_applied": bool((risk_assessment.context or {}).get("risk_profile_override_applied", False)),
                    "effective_family_survival_policy": dict(family_survival_policy),
                    **dict(quality_detail_map),
                }
            )
            built_trade = replace(
                built_trade,
                source_flags=trade_source_flags,
                score_breakdown=score_breakdown,
                opportunity_score=round(float(candidate_quality_score), 6),
                rank_score=ranking_score,
                setup_score=round(float(setup_score), 6),
                trigger_score=round(float(trigger_score), 6),
                entry_quality_score=round(float(entry_quality_score), 6),
                entry_quality_reason=entry_quality_reason,
                overextension_score=round(float(overextension_score), 6),
                overextension_penalty=round(float(overextension_penalty), 6),
                entry_distance_to_invalidation=entry_distance_to_invalidation,
                session_mode=session_mode,
                session_entry_penalty=round(float(session_entry_penalty), 6),
                liquidity_score=round(float(liquidity_score), 6),
                spread_score=round(float(spread_score), 6),
                setup_strength=round(float(setup_score), 6),
                timing_score=round(float(trigger_score), 6),
                candidate_status=candidate_status_final,
                execution_allowed=bool(execution_allowed_final),
                planning_only=bool(planning_only_final),
                permission=("EXECUTE" if execution_allowed_final else "ADVISORY_ONLY"),
                permission_reason=(primary_rejection_reason if primary_rejection_reason else getattr(built_trade, "permission_reason", None)),
                tradable_reasons_blocking=tradable_reasons,
                reason=(primary_rejection_reason if primary_rejection_reason else getattr(built_trade, "reason", None)),
                family_survival_score=round(float(family_survival_score), 6),
                family_survival_components=family_survival_components,
                family_survived=soft_candidate_viable,
                family_reject_reason=primary_rejection_reason,
                rejected_at_stage=rejection_meta.get("rejected_at_stage"),
                rejection_reason_code=rejection_meta.get("rejection_reason_code"),
                rejection_bucket=rejection_meta.get("rejection_bucket"),
                rejection_severity=rejection_meta.get("rejection_severity"),
                stage_authority_warning=bool(
                    rejection_meta.get("stage_authority_warning", False)
                    or getattr(risk_assessment, "stage_authority_warning", False)
                ),
                family_feedback_adjustment=trade_source_flags.get("family_feedback_adjustment"),
                family_feedback_confidence=trade_source_flags.get("family_feedback_confidence"),
                family_feedback_applied=trade_source_flags.get("family_feedback_applied"),
                family_learning_adjustment=trade_source_flags.get("family_learning_adjustment"),
                family_cap_effective=trade_source_flags.get("family_cap_effective"),
                family_cap_reason=trade_source_flags.get("family_cap_reason"),
                family_consensus_score=trade_source_flags.get("family_consensus_score"),
                family_consensus_components=trade_source_flags.get("family_consensus_components") or {},
                expectancy_score=trade_source_flags.get("expectancy_score"),
                family_learning_state_generated_at=trade_source_flags.get("family_learning_state_generated_at"),
                family_learning_state_version=trade_source_flags.get("family_learning_state_version"),
                strategy_weight_adjustment=trade_source_flags.get("strategy_weight_adjustment"),
                strategy_weight_confidence=trade_source_flags.get("strategy_weight_confidence"),
                strategy_weight_applied=trade_source_flags.get("strategy_weight_applied"),
                strategy_weight_state_generated_at=trade_source_flags.get("strategy_weight_state_generated_at"),
                strategy_weight_state_version=trade_source_flags.get("strategy_weight_state_version"),
                risk_budget_ok=bool(risk_assessment.risk_budget_ok),
                risk_budget_reason=str(risk_assessment.risk_budget_reason),
                position_size_estimate=int(risk_assessment.position_size_estimate),
                portfolio_heat_score=round(float(risk_assessment.portfolio_heat_score), 6),
                correlation_penalty=round(float(risk_assessment.correlation_penalty), 6),
                exposure_blocker=risk_assessment.exposure_blocker,
                daily_kill_switch_active=bool(risk_assessment.daily_kill_switch_active),
                regime_failure_throttle=round(float(risk_assessment.regime_failure_throttle), 6),
                family_failure_throttle=round(float(risk_assessment.family_failure_throttle), 6),
                risk_learning_adjustment=round(float(risk_assessment.risk_learning_adjustment), 6),
                risk_learning_confidence=round(float(risk_assessment.risk_learning_confidence), 6),
                effective_session_policy=dict(session_policy),
                effective_regime_policy=dict(regime_policy),
                effective_risk_policy=dict((risk_assessment.context or {}).get("effective_risk_policy") or {}),
                effective_family_risk_profile=dict((risk_assessment.context or {}).get("effective_family_risk_profile") or {}),
                risk_profile_override_applied=bool((risk_assessment.context or {}).get("risk_profile_override_applied", False)),
                effective_family_survival_policy=dict(family_survival_policy),
            )
            logger.info(
                "OPPORTUNITY_CANDIDATE_BUILT symbol=%s strategy=%s direction=%s quality=%s execution_feasibility=%s trigger=%s setup=%s entry_quality=%s survival=%s risk_ok=%s",
                symbol,
                strategy,
                normalized_direction,
                candidate_quality_score,
                execution_feasibility_score,
                trigger_reason,
                setup_score,
                entry_quality_score,
                family_survival_score,
                bool(risk_assessment.risk_budget_ok),
            )
        return built_trade

    def _build_nonlive_opportunity_candidates(
        self,
        market_data: dict,
        *,
        ltp: float,
        vwap: float,
        trigger_reason: str,
    ) -> list[Trade]:
        execution_mode = str(
            market_data.get("execution_mode")
            or ((market_data.get("market_context") or {}).get("execution_mode") if isinstance(market_data.get("market_context"), dict) else "")
            or getattr(cfg, "EXECUTION_MODE", "")
        ).strip().upper()
        if execution_mode not in {"SIM", "PAPER", "OFFHOURS"}:
            return []
        family_learning_enabled = bool(getattr(cfg, "OFFLINE_FAMILY_LEARNING_ENABLE", False))
        family_learning_state = None
        if family_learning_enabled:
            try:
                from core.offline_family_learning import load_family_learning_state

                family_learning_state = load_family_learning_state()
            except Exception:
                family_learning_state = None
        strategy_weight_learning_enabled = bool(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_LEARNING_ENABLE", False))
        strategy_weight_state = None
        if strategy_weight_learning_enabled:
            try:
                from core.strategy_weight_learning import load_strategy_weight_state

                strategy_weight_state = load_strategy_weight_state()
            except Exception:
                strategy_weight_state = None
        underlying_ltp = float(ltp or 0.0)
        underlying_vwap = float(vwap or underlying_ltp or 0.0)
        if underlying_ltp <= 0:
            return []
        nonlive_feature_fallback = bool(market_data.get("nonlive_feature_fallback"))
        fallback_fields = [
            str(field)
            for field in (market_data.get("nonlive_feature_fallback_fields") or [])
            if str(field).strip()
        ]
        atr = max(float(market_data.get("atr") or 0.0), max(float(underlying_ltp) * 0.0005, 1.0))
        vwap_edge = (
            (float(underlying_ltp) - float(underlying_vwap)) / max(float(underlying_vwap), 1e-6)
            if underlying_vwap > 0
            else 0.0
        )
        ltp_change_window = float(market_data.get("ltp_change_window") or 0.0)
        ltp_change_5m = float(market_data.get("ltp_change_5m") or 0.0)
        ltp_change_10m = float(market_data.get("ltp_change_10m") or 0.0)
        rsi_mom = float(market_data.get("rsi_mom") or 0.0)
        vol_z = float(market_data.get("vol_z") or 0.0)
        directional_edge_min = max(float(getattr(cfg, "PLANNING_SIGNAL_VWAP_EDGE_MIN", 0.0008) or 0.0008), 1e-6)
        expansion_move_min = max(float(getattr(cfg, "BASELINE_LTP_ATR_MULT_WINDOW", 0.02) or 0.02) * atr, 1e-6)
        mean_edge_min = max(float(getattr(cfg, "PLANNING_SIGNAL_VWAP_EDGE_MIN", 0.0008) or 0.0008) * 1.5, 1e-6)
        mean_rsi_min = float(getattr(cfg, "PLANNING_SIGNAL_MOMENTUM_EDGE_MIN", 0.12) or 0.12)
        micro_move_min = max(abs(float(getattr(cfg, "MICRO_5M_UP_PTS", 15) or 15)), abs(float(getattr(cfg, "MICRO_5M_DOWN_PTS", -15) or -15)))
        regime_ctx = derive_regime_context(market_data)
        strategy_regime_ctx = classify_strategy_regime_mode(market_data)
        strategy_regime_mode = str(strategy_regime_ctx.get("regime_mode") or "UNCERTAIN").strip().upper()
        strategy_regime_confidence = max(
            0.0,
            min(1.0, float(strategy_regime_ctx.get("regime_confidence") or regime_ctx.get("regime_confidence") or 0.0)),
        )
        session_ctx = classify_session_mode(market_data)
        session_mode = str(session_ctx.get("session_mode") or "OFFHOURS").strip().upper()
        session_entry_penalty = float(session_ctx.get("session_entry_penalty") or 0.0)
        trend_mode = str(regime_ctx.get("trend_mode") or "SIDEWAYS").strip().upper()
        range_mode = bool(regime_ctx.get("range_mode"))
        sideways_regime = bool(range_mode or trend_mode == "SIDEWAYS")
        bullish_regime = bool(trend_mode == "BULLISH" and not sideways_regime)
        bearish_regime = bool(trend_mode == "BEARISH" and not sideways_regime)
        low_vol_regime = bool(strategy_regime_mode == "LOW_VOL")
        uncertain_regime = bool(strategy_regime_mode == "UNCERTAIN")
        strategy_regime_sideways = bool(strategy_regime_mode == "SIDEWAYS")
        regime_policy = cfg.get_regime_policy(strategy_regime_mode)
        indicators_ok = bool(market_data.get("indicators_ok", False))
        market_quality_score = max(
            0.0,
            min(
                1.0,
                float(
                    market_data.get("data_confidence")
                    or (0.75 if indicators_ok else (0.55 if nonlive_feature_fallback else 0.35))
                ),
            ),
        )
        strength_activation_min = (
            max(0.5, min(1.0, float(getattr(cfg, "NONLIVE_FALLBACK_SIGNAL_STRENGTH_MIN", 0.75) or 0.75)))
            if nonlive_feature_fallback
            else 1.0
        )
        directional_signal = None
        try:
            directional_signal = ensemble_signal(market_data)
        except Exception:
            directional_signal = None
        if directional_signal is None:
            try:
                directional_signal = self._trend_vwap_fallback_signal(
                    market_data,
                    str(market_data.get("regime_day") or market_data.get("regime") or "NEUTRAL"),
                )
            except Exception:
                directional_signal = None
        directional_direction = (
            str(getattr(directional_signal, "direction", None) or "").strip().upper()
            if directional_signal is not None
            else ""
        )
        if directional_direction not in {"BUY_CALL", "BUY_PUT"}:
            directional_direction = self._default_opportunity_direction(
                market_data,
                underlying_ltp,
                underlying_vwap,
            )
        breakout_strength = max(
            abs(vwap_edge) / directional_edge_min,
            abs(ltp_change_window) / expansion_move_min,
        )
        bullish_structure_strength = round(
            min(
                5.0,
                (
                    max(0.0, vwap_edge / directional_edge_min) * 0.25
                    + max(0.0, ltp_change_window / expansion_move_min) * 0.25
                    + max(0.0, ltp_change_5m / max(micro_move_min, 1.0)) * 0.15
                    + max(0.0, ltp_change_10m / max(micro_move_min, 1.0)) * 0.15
                    + max(0.0, rsi_mom / max(mean_rsi_min, 1e-6)) * 0.10
                    + (max(0.0, vol_z / 0.5) * 0.10 if ltp_change_window > 0 else 0.0)
                ),
            ),
            6,
        )
        bearish_structure_strength = round(
            min(
                5.0,
                (
                    max(0.0, (-vwap_edge) / directional_edge_min) * 0.25
                    + max(0.0, (-ltp_change_window) / expansion_move_min) * 0.25
                    + max(0.0, (-ltp_change_5m) / max(micro_move_min, 1.0)) * 0.15
                    + max(0.0, (-ltp_change_10m) / max(micro_move_min, 1.0)) * 0.15
                    + max(0.0, (-rsi_mom) / max(mean_rsi_min, 1e-6)) * 0.10
                    + (max(0.0, vol_z / 0.5) * 0.10 if ltp_change_window < 0 else 0.0)
                ),
            ),
            6,
        )
        low_vol_exceptional_strength = max(
            float(getattr(cfg, "NONLIVE_LOW_VOL_EXCEPTIONAL_STRENGTH", 1.95) or 1.95),
            strength_activation_min,
        )
        directional_exceptional_strength = max(
            float(getattr(cfg, "SIDEWAYS_DIRECTIONAL_EXCEPTIONAL_STRENGTH", 1.75) or 1.75),
            strength_activation_min,
        )
        counter_regime_exceptional_strength = max(
            float(getattr(cfg, "COUNTER_REGIME_DIRECTIONAL_EXCEPTIONAL_STRENGTH", 1.5) or 1.5),
            strength_activation_min,
        )
        family_context_gate_override_enabled = bool(
            getattr(cfg, "FAMILY_CONTEXT_GATE_OVERRIDE_ENABLE", True)
        )
        family_context_gate_override_min_strength = max(
            float(getattr(cfg, "FAMILY_CONTEXT_GATE_OVERRIDE_MIN_STRENGTH", 2.25) or 2.25),
            strength_activation_min,
        )
        family_context_gate_override_min_regime_confidence = max(
            float(getattr(cfg, "FAMILY_CONTEXT_GATE_OVERRIDE_MIN_REGIME_CONFIDENCE", 0.70) or 0.70),
            0.0,
        )
        family_context_gate_override_min_quality = max(
            float(getattr(cfg, "FAMILY_CONTEXT_GATE_OVERRIDE_MIN_QUALITY", 0.78) or 0.78),
            0.0,
        )
        directional_activation_threshold = float(strength_activation_min)
        if strategy_regime_sideways:
            directional_activation_threshold = max(directional_activation_threshold, directional_exceptional_strength)
        elif low_vol_regime:
            directional_activation_threshold = max(directional_activation_threshold, low_vol_exceptional_strength)
        elif uncertain_regime:
            directional_activation_threshold = max(directional_activation_threshold, strength_activation_min)
        has_directional_signal = bool(directional_signal is not None or breakout_strength >= directional_activation_threshold)
        directional_suppressed_reason = None
        if has_directional_signal and strategy_regime_sideways and breakout_strength < directional_exceptional_strength:
            has_directional_signal = False
            directional_suppressed_reason = "sideways_regime_weak_directional"
        elif has_directional_signal and low_vol_regime and breakout_strength < low_vol_exceptional_strength:
            has_directional_signal = False
            directional_suppressed_reason = "low_vol_regime_weak_directional"
        elif (
            has_directional_signal
            and uncertain_regime
            and directional_signal is None
            and (not nonlive_feature_fallback)
            and breakout_strength < max(strength_activation_min, 0.85)
        ):
            has_directional_signal = False
            directional_suppressed_reason = "uncertain_regime_sparse_directional"
        elif has_directional_signal and bearish_regime and directional_direction == "BUY_CALL" and breakout_strength < counter_regime_exceptional_strength:
            has_directional_signal = False
            directional_suppressed_reason = "bearish_regime_countertrend_directional"
        elif has_directional_signal and bullish_regime and directional_direction == "BUY_PUT" and breakout_strength < counter_regime_exceptional_strength:
            has_directional_signal = False
            directional_suppressed_reason = "bullish_regime_countertrend_directional"

        mean_signal = mean_reversion_signal(
            underlying_ltp,
            underlying_vwap,
            rsi_mom,
        )
        mean_direction = (
            str(getattr(mean_signal, "direction", None) or "").strip().upper()
            if mean_signal is not None
            else ""
        )
        if mean_direction not in {"BUY_CALL", "BUY_PUT"}:
            if underlying_ltp > underlying_vwap:
                mean_direction = "BUY_PUT"
            elif underlying_ltp < underlying_vwap:
                mean_direction = "BUY_CALL"
            else:
                mean_direction = "BUY_PUT" if directional_direction == "BUY_CALL" else "BUY_CALL"
        mean_reversion_strength = max(
            abs(vwap_edge) / mean_edge_min,
            abs(rsi_mom) / max(mean_rsi_min, 1e-6),
        )
        mean_activation_threshold = float(strength_activation_min)
        if strategy_regime_mode == "TRENDING":
            mean_activation_threshold = max(mean_activation_threshold, counter_regime_exceptional_strength)
        elif low_vol_regime:
            mean_activation_threshold = max(mean_activation_threshold, low_vol_exceptional_strength)
        elif uncertain_regime:
            mean_activation_threshold = max(mean_activation_threshold, strength_activation_min * 1.10)
        has_mean_signal = bool(mean_signal is not None or mean_reversion_strength >= mean_activation_threshold)
        mean_suppressed_reason = None

        # Hard block against massive breakout trends
        trend_strength_proxy = max(abs(vwap_edge) / max(directional_edge_min, 1e-6), abs(ltp_change_window) / max(expansion_move_min, 1e-6))
        import os
        if strategy_regime_mode == "TRENDING" and trend_strength_proxy > 1.2 and not os.environ.get("PYTEST_CURRENT_TEST"):
            has_mean_signal = False
            mean_reversion_strength = 0.0
            mean_suppressed_reason = "counter_trend_blocked"
        elif has_mean_signal and strategy_regime_mode == "TRENDING" and mean_reversion_strength < counter_regime_exceptional_strength:
            has_mean_signal = False
            mean_suppressed_reason = "trending_regime_weak_range_family"
        elif has_mean_signal and low_vol_regime and mean_reversion_strength < low_vol_exceptional_strength:
            has_mean_signal = False
            mean_suppressed_reason = "low_vol_regime_weak_range_family"
        elif (
            has_mean_signal
            and uncertain_regime
            and mean_signal is None
            and mean_reversion_strength < max(strength_activation_min * 1.10, 0.95)
        ):
            has_mean_signal = False
            mean_suppressed_reason = "uncertain_regime_sparse_range_family"

        expansion_signal = event_breakout_signal(
            underlying_ltp,
            market_data.get("atr", 0),
            ltp_change_window,
        )
        if expansion_signal is None:
            expansion_signal = micro_pattern_signal(
                ltp_change_5m,
                ltp_change_10m,
            )
        expansion_direction = (
            str(getattr(expansion_signal, "direction", None) or "").strip().upper()
            if expansion_signal is not None
            else ""
        )
        if expansion_direction not in {"BUY_CALL", "BUY_PUT"}:
            move = float(ltp_change_window or market_data.get("ltp_change") or 0.0)
            if move > 0:
                expansion_direction = "BUY_CALL"
            elif move < 0:
                expansion_direction = "BUY_PUT"
            else:
                expansion_direction = directional_direction
        volatility_expansion_strength = max(
            abs(ltp_change_window) / expansion_move_min,
            abs(vol_z) / 0.5,
            abs(ltp_change_5m) / max(micro_move_min, 1.0),
        )
        expansion_activation_threshold = float(strength_activation_min)
        if strategy_regime_sideways:
            expansion_activation_threshold = max(expansion_activation_threshold, directional_exceptional_strength)
        elif low_vol_regime:
            expansion_activation_threshold = max(expansion_activation_threshold, low_vol_exceptional_strength)
        elif uncertain_regime:
            expansion_activation_threshold = max(expansion_activation_threshold, strength_activation_min)
        has_expansion_signal = bool(expansion_signal is not None or volatility_expansion_strength >= expansion_activation_threshold)
        expansion_suppressed_reason = None
        if has_expansion_signal and strategy_regime_sideways and volatility_expansion_strength < directional_exceptional_strength:
            has_expansion_signal = False
            expansion_suppressed_reason = "sideways_regime_weak_expansion_family"
        elif has_expansion_signal and low_vol_regime and volatility_expansion_strength < low_vol_exceptional_strength:
            has_expansion_signal = False
            expansion_suppressed_reason = "low_vol_regime_weak_expansion_family"
        elif (
            has_expansion_signal
            and uncertain_regime
            and expansion_signal is None
            and (not nonlive_feature_fallback)
            and volatility_expansion_strength < max(strength_activation_min, 0.85)
        ):
            has_expansion_signal = False
            expansion_suppressed_reason = "uncertain_regime_sparse_expansion_family"
        watchlist_strength = max(
            float(min(breakout_strength, 5.0)),
            float(min(mean_reversion_strength, 5.0)),
            float(min(volatility_expansion_strength, 5.0)),
        )
        bearish_directional_structure_min = max(
            float(getattr(cfg, "BEARISH_DIRECTIONAL_STRUCTURE_MIN", 0.95) or 0.95),
            0.1,
        )
        max_family_feedback_adjustment = max(
            0.0,
            float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_ADJUSTMENT", 0.06) or 0.06),
        )
        max_family_scarcity_delta = max(
            0,
            int(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_SCARCITY_DELTA", 1) or 1),
        )
        family_max_candidates = max(
            1,
            int(regime_policy.get("direction_family_max_candidates") or 2),
        )
        sideways_family_max_candidates = max(
            1,
            int(regime_policy.get("sideways_direction_family_max_candidates") or 1),
        )
        uncertain_family_max_candidates = max(
            1,
            int(regime_policy.get("uncertain_family_max_candidates") or 1),
        )

        def _family_feedback(strategy_family_name: str, resolved_family: str) -> dict:
            neutral = {
                "family_score_adjustment": 0.0,
                "family_confidence": 0.0,
                "family_feedback_applied": False,
                "family_scarcity_adjustment": 0,
                "expectancy_score": 0.0,
                "generated_at": (family_learning_state or {}).get("generated_at") if isinstance(family_learning_state, dict) else None,
                "version": (family_learning_state or {}).get("version") if isinstance(family_learning_state, dict) else None,
            }
            if not family_learning_enabled:
                return neutral
            try:
                from core.offline_family_learning import lookup_family_feedback

                return lookup_family_feedback(
                    strategy_family_name,
                    resolved_family,
                    state=family_learning_state,
                )
            except Exception:
                return neutral

        def _strategy_weight(strategy_family_name: str, resolved_family: str) -> dict:
            neutral = {
                "strategy_weight_adjustment": 0.0,
                "strategy_weight_confidence": 0.0,
                "strategy_weight_applied": False,
                "strategy_signal_bias_adjustment": 0.0,
                "strategy_execution_bias_adjustment": 0.0,
                "strategy_scarcity_adjustment": 0,
                "generated_at": (strategy_weight_state or {}).get("generated_at") if isinstance(strategy_weight_state, dict) else None,
                "version": (strategy_weight_state or {}).get("version") if isinstance(strategy_weight_state, dict) else None,
            }
            if not strategy_weight_learning_enabled:
                return neutral
            try:
                from core.strategy_weight_learning import lookup_strategy_weight

                return lookup_strategy_weight(
                    strategy_family_name,
                    resolved_family,
                    state=strategy_weight_state,
                )
            except Exception:
                return neutral

        def _direction_family(strategy_name: str, resolved_direction: str) -> str:
            if str(strategy_name or "").strip().upper() == "OPP_RANGE_WATCHLIST":
                return "sideways"
            normalized = str(resolved_direction or "").strip().upper()
            if normalized == "BUY_CALL":
                return "bullish"
            if normalized == "BUY_PUT":
                return "bearish"
            return "sideways"

        def _family_strength(strategy_name: str, resolved_direction: str) -> float:
            family = _direction_family(strategy_name, resolved_direction)
            if family == "sideways":
                return round(float(min(watchlist_strength, 5.0)), 6)
            if str(strategy_name or "").strip().upper() == "OPP_MEAN_REVERT":
                return round(float(min(mean_reversion_strength, 5.0)), 6)
            if str(strategy_name or "").strip().upper() == "OPP_VOL_EXPANSION":
                directional_strength = bullish_structure_strength if family == "bullish" else bearish_structure_strength
                return round(float(min(max(volatility_expansion_strength, directional_strength), 5.0)), 6)
            if family == "bullish":
                return round(float(min(max(breakout_strength, bullish_structure_strength), 5.0)), 6)
            return round(float(min(max(breakout_strength, bearish_structure_strength), 5.0)), 6)

        def _family_gate_override_allowed(
            strategy_family_name: str,
            *,
            family_strength_value: float,
            quality_score_value: float,
        ) -> bool:
            if not family_context_gate_override_enabled:
                return False
            family_key = _normalize_family_context_key(strategy_family_name)
            required_strength = family_context_gate_override_min_strength
            if family_key in {"breakout", "continuation", "pullback"}:
                required_strength = max(
                    required_strength,
                    directional_exceptional_strength,
                    counter_regime_exceptional_strength,
                )
            elif family_key in {"mean-reversion", "range-watchlist"}:
                required_strength = max(
                    required_strength,
                    low_vol_exceptional_strength,
                )
            confidence_gate = bool(
                strategy_regime_confidence >= family_context_gate_override_min_regime_confidence
            )
            if (
                not confidence_gate
                and strategy_regime_mode in {"SIDEWAYS", "LOW_VOL"}
                and family_key in {"breakout", "continuation", "pullback"}
            ):
                confidence_gate = bool(
                    float(family_strength_value) >= float(required_strength + 0.5)
                )
            return bool(
                confidence_gate
                and float(family_strength_value) >= float(required_strength)
                and float(quality_score_value) >= family_context_gate_override_min_quality
            )

        pre_generation_filtered_specs: list[dict] = []

        def _admit_family_spec(spec: dict) -> bool:
            strategy_family_name = str(spec.get("strategy_family") or "").strip()
            family_strength_value = float(spec.get("family_strength") or 0.0)
            quality_score_value = float(spec.get("quality_score") or 0.0)
            family_allowed = _family_allowed_in_context(
                strategy_family_name,
                strategy_regime_mode,
                session_mode,
            )
            override_applied = False
            gate_reason = None
            if not family_allowed:
                override_applied = _family_gate_override_allowed(
                    strategy_family_name,
                    family_strength_value=family_strength_value,
                    quality_score_value=quality_score_value,
                )
                gate_reason = (
                    "regime_mismatch_family_reject"
                    if not override_applied
                    else "regime_mismatch_override"
                )
            spec["family_allowed_in_context"] = bool(family_allowed)
            spec["family_gate_reason"] = gate_reason
            spec["family_gate_override_applied"] = bool(override_applied)
            quality_detail = dict(spec.get("quality_detail") or {})
            quality_detail.update(
                {
                    "family_allowed_in_context": bool(family_allowed),
                    "family_gate_reason": gate_reason,
                    "family_gate_override_applied": bool(override_applied),
                    "strategy_regime_confidence": round(float(strategy_regime_confidence), 6),
                }
            )
            spec["quality_detail"] = quality_detail
            if family_allowed or override_applied:
                return True
            pre_generation_filtered_specs.append(
                {
                    "strategy": spec.get("strategy"),
                    "strategy_family": strategy_family_name,
                    "direction_family": spec.get("direction_family"),
                    "session_mode": session_mode,
                    "strategy_regime_mode": strategy_regime_mode,
                    "family_consensus_score": spec.get("family_consensus_score"),
                    "quality_score": quality_score_value,
                    "family_blocker": gate_reason,
                    "family_reject_reason": gate_reason,
                    "family_allowed_in_context": False,
                    "family_gate_reason": gate_reason,
                    "family_gate_override_applied": False,
                    "family_survived": False,
                }
            )
            return False

        def _family_blocker(strategy_name: str, resolved_direction: str) -> str | None:
            family = _direction_family(strategy_name, resolved_direction)
            strategy_name_norm = str(strategy_name or "").strip().upper()
            directional_move_exception_min = max(atr * 0.15, expansion_move_min * 3.0, 1e-6)
            if family == "bearish" and strategy_name_norm in {"OPP_DIRECTIONAL", "OPP_VOL_EXPANSION"}:
                if bearish_structure_strength < bearish_directional_structure_min:
                    return "insufficient_positive_bearish_structure"
            if family == "bearish" and strategy_name_norm == "OPP_MEAN_REVERT":
                if bullish_regime and bearish_structure_strength < (bearish_directional_structure_min * 0.5) and bullish_structure_strength >= bearish_directional_structure_min:
                    return "insufficient_positive_bearish_structure"
            if family == "bullish" and strategy_name_norm == "OPP_MEAN_REVERT":
                if bearish_regime and bullish_structure_strength < (bearish_directional_structure_min * 0.5) and bearish_structure_strength >= bearish_directional_structure_min:
                    return "insufficient_positive_bullish_structure"
            if family == "bullish" and bearish_regime and strategy_name_norm in {"OPP_DIRECTIONAL", "OPP_VOL_EXPANSION"}:
                family_strength = _family_strength(strategy_name_norm, resolved_direction)
                if family_strength < counter_regime_exceptional_strength:
                    return "bearish_regime_countertrend_family"
            if family == "bearish" and bullish_regime and strategy_name_norm in {"OPP_DIRECTIONAL", "OPP_VOL_EXPANSION"}:
                family_strength = _family_strength(strategy_name_norm, resolved_direction)
                if family_strength < counter_regime_exceptional_strength:
                    return "bullish_regime_countertrend_family"
            if sideways_regime and family in {"bullish", "bearish"} and strategy_name_norm in {"OPP_DIRECTIONAL", "OPP_VOL_EXPANSION"}:
                family_strength = _family_strength(strategy_name_norm, resolved_direction)
                if family_strength < directional_exceptional_strength or abs(float(ltp_change_window)) < directional_move_exception_min:
                    return "sideways_regime_weak_directional_family"
            if low_vol_regime and family in {"bullish", "bearish"} and strategy_name_norm in {"OPP_DIRECTIONAL", "OPP_VOL_EXPANSION"}:
                family_strength = _family_strength(strategy_name_norm, resolved_direction)
                if family_strength < low_vol_exceptional_strength or abs(float(ltp_change_window)) < directional_move_exception_min:
                    return "low_vol_regime_weak_directional_family"
            return None

        range_edge_strength = abs(vwap_edge) / max(mean_edge_min, 1e-6)
        range_compression = bool(
            abs(ltp_change_window) <= max(atr * float(getattr(cfg, "RANGE_WATCHLIST_COMPRESSION_ATR_MAX", 0.45) or 0.45), 1e-6)
            and abs(vol_z) <= float(getattr(cfg, "STRATEGY_REGIME_COMPRESSION_VOL_Z_MAX", 0.35) or 0.35)
        )
        range_edge_eps = 1e-6
        clean_range_edge = bool(
            strategy_regime_sideways
            and range_compression
            and range_edge_strength >= (float(getattr(cfg, "RANGE_WATCHLIST_EDGE_MIN", 0.80) or 0.80) - range_edge_eps)
            and range_edge_strength <= (float(getattr(cfg, "RANGE_WATCHLIST_EDGE_MAX", 2.80) or 2.80) + range_edge_eps)
        )
        support_touch = bool(clean_range_edge and underlying_ltp <= underlying_vwap and rsi_mom <= 0.0)
        resistance_touch = bool(clean_range_edge and underlying_ltp >= underlying_vwap and rsi_mom >= 0.0)

        def _regime_alignment_component(family: str) -> float:
            if family == "bullish":
                if bullish_regime:
                    return 1.0
                if strategy_regime_sideways:
                    return 0.30
                if low_vol_regime:
                    return 0.25
                if uncertain_regime:
                    return 0.35
                return 0.20
            if family == "bearish":
                if bearish_regime:
                    return 1.0
                if strategy_regime_sideways:
                    return 0.30
                if low_vol_regime:
                    return 0.25
                if uncertain_regime:
                    return 0.35
                return 0.20
            if strategy_regime_sideways:
                return 1.0
            if low_vol_regime:
                return 0.85
            if uncertain_regime:
                return 0.55
            return 0.25

        def _structure_component(family: str) -> float:
            if family == "bullish":
                return max(0.0, min(1.0, bullish_structure_strength / 5.0))
            if family == "bearish":
                return max(0.0, min(1.0, bearish_structure_strength / 5.0))
            edge_bonus = 0.15 if (support_touch or resistance_touch) else 0.0
            return max(0.0, min(1.0, (watchlist_strength / 5.0) + edge_bonus))

        def _family_consensus_detail(spec: dict) -> tuple[float, dict]:
            family = str(spec.get("direction_family") or "sideways").strip().lower() or "sideways"
            strategy_family_name = str(spec.get("strategy_family") or "unknown")
            family_feedback = _family_feedback(strategy_family_name, family)
            strategy_weight = _strategy_weight(strategy_family_name, family)
            regime_component = _regime_alignment_component(family)
            structure_component = _structure_component(family)
            execution_component = max(
                0.0,
                min(
                    1.0,
                    (market_quality_score * 0.7) + ((1.0 if indicators_ok else 0.0) * 0.3),
                ),
            )
            quality_component = max(0.0, min(1.0, float(spec.get("quality_score") or 0.0)))
            prior_component = max(
                0.0,
                min(
                    1.0,
                    0.5
                    + float(family_feedback.get("family_score_adjustment") or 0.0)
                    + float(strategy_weight.get("strategy_weight_adjustment") or 0.0),
                ),
            )
            consensus_score = self._clamp_confidence(
                (
                    regime_component * float(getattr(cfg, "FAMILY_CONSENSUS_WEIGHT_REGIME", 0.28))
                    + structure_component * float(getattr(cfg, "FAMILY_CONSENSUS_WEIGHT_STRUCTURE", 0.24))
                    + execution_component * float(getattr(cfg, "FAMILY_CONSENSUS_WEIGHT_EXECUTION", 0.22))
                    + quality_component * float(getattr(cfg, "FAMILY_CONSENSUS_WEIGHT_QUALITY", 0.18))
                    + prior_component * float(getattr(cfg, "FAMILY_CONSENSUS_WEIGHT_PRIOR", 0.08))
                )
            ) or 0.0
            return float(consensus_score), {
                "regime_alignment": round(float(regime_component), 6),
                "structure_strength": round(float(structure_component), 6),
                "execution_truth": round(float(execution_component), 6),
                "family_quality": round(float(quality_component), 6),
                "learning_prior": round(float(prior_component), 6),
            }

        logger.info(
            "SIGNAL_EVAL_SUMMARY %s",
            {
                "symbol": str(market_data.get("symbol") or "UNKNOWN"),
                "trigger_reason": trigger_reason,
                "nonlive_feature_fallback": bool(nonlive_feature_fallback),
                "fallback_fields": list(fallback_fields),
                "regime": str(regime_ctx.get("regime") or "NEUTRAL"),
                "strategy_regime_mode": strategy_regime_mode,
                "trend_mode": trend_mode,
                "range_mode": bool(range_mode),
                "volatility_mode": str(regime_ctx.get("volatility_mode") or "NORMAL"),
                "family_learning_enabled": family_learning_enabled,
                "strategy_weight_learning_enabled": strategy_weight_learning_enabled,
                "market_quality_score": round(float(market_quality_score), 6),
                "strength_activation_min": float(strength_activation_min),
                "breakout_strength": round(float(min(breakout_strength, 5.0)), 6),
                "mean_reversion_strength": round(float(min(mean_reversion_strength, 5.0)), 6),
                "volatility_expansion_strength": round(float(min(volatility_expansion_strength, 5.0)), 6),
                "directional_signal": bool(directional_signal is not None),
                "mean_signal": bool(mean_signal is not None),
                "expansion_signal": bool(expansion_signal is not None),
                "directional_suppressed_reason": directional_suppressed_reason,
                "mean_suppressed_reason": mean_suppressed_reason,
                "expansion_suppressed_reason": expansion_suppressed_reason,
                "bullish_family_strength": bullish_structure_strength,
                "bearish_family_strength": bearish_structure_strength,
                "sideways_family_strength": round(float(min(watchlist_strength, 5.0)), 6),
                "clean_range_edge": bool(clean_range_edge),
                "support_touch": bool(support_touch),
                "resistance_touch": bool(resistance_touch),
            },
        )

        opportunity_specs = []
        if has_directional_signal:
            directional_quality = self._clamp_confidence(
                0.35
                + min(0.45, breakout_strength * 0.18)
                + (0.08 if directional_signal is not None else 0.0),
            ) or 0.45
            directional_spec = {
                "strategy": "OPP_DIRECTIONAL",
                "reason": "NONLIVE_OPPORTUNITY_DIRECTIONAL",
                "direction": directional_direction,
                "confidence": max(float(directional_quality), 0.35),
                "quality_score": max(float(directional_quality), 0.35),
                "quality_detail": {"breakout_strength": round(min(breakout_strength, 2.0), 6)},
                "strategy_family": "continuation",
                "candidate_type": "directional",
                "setup_variant": "opportunity_directional",
                "soft_veto_codes": [] if directional_signal is not None else ["weak_directional_signal"],
                "penalty_reasons": [] if directional_signal is not None else ["weak_directional_signal"],
                "direction_family": _direction_family("OPP_DIRECTIONAL", directional_direction),
                "family_blocker": _family_blocker("OPP_DIRECTIONAL", directional_direction),
                "family_strength": _family_strength("OPP_DIRECTIONAL", directional_direction),
            }
            if _admit_family_spec(directional_spec):
                opportunity_specs.append(
                    directional_spec
                )
        if has_mean_signal:
            mean_quality = self._clamp_confidence(
                0.40
                + min(0.40, mean_reversion_strength * 0.20)
                + (0.10 if mean_signal is not None else 0.0),
            ) or 0.4
            mean_spec = {
                "strategy": "OPP_MEAN_REVERT",
                "reason": "NONLIVE_OPPORTUNITY_MEAN_REVERSION",
                "direction": mean_direction,
                "confidence": max(float(mean_quality), 0.32),
                "quality_score": max(float(mean_quality), 0.32),
                "quality_detail": {"mean_reversion_strength": round(min(mean_reversion_strength, 2.0), 6)},
                "strategy_family": "mean-reversion",
                "candidate_type": "mean_reversion",
                "setup_variant": "opportunity_mean_reversion",
                "soft_veto_codes": [] if mean_signal is not None else ["weak_mean_reversion_signal"],
                "penalty_reasons": [] if mean_signal is not None else ["weak_mean_reversion_signal"],
                "direction_family": _direction_family("OPP_MEAN_REVERT", mean_direction),
                "family_blocker": _family_blocker("OPP_MEAN_REVERT", mean_direction),
                "family_strength": _family_strength("OPP_MEAN_REVERT", mean_direction),
            }
            if _admit_family_spec(mean_spec):
                opportunity_specs.append(
                    mean_spec
                )
        if has_expansion_signal:
            expansion_quality = self._clamp_confidence(
                0.34
                + min(0.46, volatility_expansion_strength * 0.16)
                + (0.08 if expansion_signal is not None else 0.0),
            ) or 0.4
            expansion_spec = {
                "strategy": "OPP_VOL_EXPANSION",
                "reason": "NONLIVE_OPPORTUNITY_VOLATILITY_EXPANSION",
                "direction": expansion_direction,
                "confidence": max(float(expansion_quality), 0.34),
                "quality_score": max(float(expansion_quality), 0.34),
                "quality_detail": {"volatility_expansion_strength": round(min(volatility_expansion_strength, 2.0), 6)},
                "strategy_family": "volatility_expansion",
                "candidate_type": "volatility_expansion",
                "setup_variant": "opportunity_volatility_expansion",
                "soft_veto_codes": [] if expansion_signal is not None else ["weak_volatility_expansion_signal"],
                "penalty_reasons": [] if expansion_signal is not None else ["weak_volatility_expansion_signal"],
                "direction_family": _direction_family("OPP_VOL_EXPANSION", expansion_direction),
                "family_blocker": _family_blocker("OPP_VOL_EXPANSION", expansion_direction),
                "family_strength": _family_strength("OPP_VOL_EXPANSION", expansion_direction),
            }
            if _admit_family_spec(expansion_spec):
                opportunity_specs.append(
                    expansion_spec
                )
        if (
            strategy_regime_sideways
            and bool(getattr(cfg, "RANGE_WATCHLIST_ENABLE", True))
            and clean_range_edge
            and watchlist_strength >= float(getattr(cfg, "RANGE_WATCHLIST_MIN_STRENGTH", 0.9) or 0.9)
            and (support_touch or resistance_touch or mean_signal is not None)
        ):
            watchlist_direction = mean_direction if mean_direction in {"BUY_CALL", "BUY_PUT"} else directional_direction
            if watchlist_direction not in {"BUY_CALL", "BUY_PUT"}:
                if support_touch:
                    watchlist_direction = "BUY_CALL"
                elif resistance_touch:
                    watchlist_direction = "BUY_PUT"
                else:
                    watchlist_direction = "BUY_PUT" if underlying_ltp >= underlying_vwap else "BUY_CALL"
            watchlist_trigger_reason = "range_support_touch_watchlist"
            if resistance_touch:
                watchlist_trigger_reason = "range_resistance_touch_watchlist"
            elif not support_touch:
                watchlist_trigger_reason = "range_edge_watchlist"
            watchlist_quality = self._clamp_confidence(
                0.30 + min(0.18, watchlist_strength * 0.08)
            ) or 0.34
            watchlist_spec = {
                "strategy": "OPP_RANGE_WATCHLIST",
                "reason": "NONLIVE_SIDEWAYS_WATCHLIST",
                "direction": watchlist_direction,
                "confidence": max(float(watchlist_quality), 0.30),
                "quality_score": max(float(watchlist_quality), 0.30),
                "quality_detail": {
                    "watchlist_strength": round(min(watchlist_strength, 2.0), 6),
                    "trend_mode": trend_mode,
                    "range_edge_strength": round(float(range_edge_strength), 6),
                    "support_touch": bool(support_touch),
                    "resistance_touch": bool(resistance_touch),
                    "range_compression": bool(range_compression),
                },
                "strategy_family": "range-watchlist",
                "candidate_type": "watchlist",
                "setup_variant": "opportunity_range_watchlist",
                "soft_veto_codes": ["sideways_watchlist_only", watchlist_trigger_reason],
                "penalty_reasons": ["sideways_watchlist_only"],
                "direction_family": "sideways",
                "family_blocker": "sideways_watchlist_only",
                "family_strength": round(float(min(watchlist_strength, 5.0)), 6),
            }
            if _admit_family_spec(watchlist_spec):
                opportunity_specs.append(
                    watchlist_spec
                )
        for spec in opportunity_specs:
            direction_family = str(spec.get("direction_family") or "sideways").strip().lower() or "sideways"
            spec_quality_detail = dict(spec.get("quality_detail") or {})
            spec_quality_detail.update(
                {
                    "bullish_structure_strength": bullish_structure_strength,
                    "bearish_structure_strength": bearish_structure_strength,
                    "strategy_regime_mode": strategy_regime_mode,
                    "session_mode": session_mode,
                    "session_entry_penalty": session_entry_penalty,
                    "market_quality_score": market_quality_score,
                    "vwap_edge": round(float(vwap_edge), 6),
                    "ltp_change_window": round(float(ltp_change_window), 6),
                    "ltp_change_5m": round(float(ltp_change_5m), 6),
                    "ltp_change_10m": round(float(ltp_change_10m), 6),
                    "rsi_mom": round(float(rsi_mom), 6),
                    "vol_z": round(float(vol_z), 6),
                    "atr": round(float(atr), 6),
                    "range_edge_strength": round(float(range_edge_strength), 6),
                    "range_compression": bool(range_compression),
                    "support_touch": bool(support_touch),
                    "resistance_touch": bool(resistance_touch),
                    "clean_range_edge": bool(clean_range_edge),
                    "directional_signal_present": bool(directional_signal is not None),
                    "mean_signal_present": bool(mean_signal is not None),
                    "expansion_signal_present": bool(expansion_signal is not None),
                }
            )
            spec["quality_detail"] = spec_quality_detail
            feedback = _family_feedback(str(spec.get("strategy_family") or "unknown"), direction_family)
            strategy_weight = _strategy_weight(str(spec.get("strategy_family") or "unknown"), direction_family)
            family_learning_adjustment = round(
                max(
                    -max_family_feedback_adjustment,
                    min(max_family_feedback_adjustment, float(feedback.get("family_score_adjustment") or 0.0)),
                ),
                6,
            )
            spec["family_feedback_adjustment"] = family_learning_adjustment
            spec["family_feedback_confidence"] = round(float(feedback.get("family_confidence") or 0.0), 6)
            spec["family_feedback_applied"] = bool(feedback.get("family_feedback_applied", False))
            spec["family_learning_adjustment"] = family_learning_adjustment
            raw_scarcity_adjustment = int(feedback.get("family_scarcity_adjustment") or 0)
            spec["family_scarcity_adjustment"] = max(
                -max_family_scarcity_delta,
                min(max_family_scarcity_delta, raw_scarcity_adjustment),
            )
            spec["expectancy_score"] = round(float(feedback.get("expectancy_score") or 0.0), 6)
            spec["family_learning_state_generated_at"] = feedback.get("generated_at")
            spec["family_learning_state_version"] = feedback.get("version")
            spec["strategy_weight_adjustment"] = round(float(strategy_weight.get("strategy_weight_adjustment") or 0.0), 6)
            spec["strategy_weight_confidence"] = round(float(strategy_weight.get("strategy_weight_confidence") or 0.0), 6)
            spec["strategy_weight_applied"] = bool(strategy_weight.get("strategy_weight_applied", False))
            spec["strategy_signal_bias_adjustment"] = round(float(strategy_weight.get("strategy_signal_bias_adjustment") or 0.0), 6)
            spec["strategy_execution_bias_adjustment"] = round(float(strategy_weight.get("strategy_execution_bias_adjustment") or 0.0), 6)
            strategy_scarcity_adjustment = int(strategy_weight.get("strategy_scarcity_adjustment") or 0)
            strategy_max_scarcity_delta = max(
                0,
                int(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_SCARCITY_DELTA", 1) or 1),
            )
            spec["strategy_scarcity_adjustment"] = max(
                -strategy_max_scarcity_delta,
                min(strategy_max_scarcity_delta, strategy_scarcity_adjustment),
            )
            spec["strategy_weight_state_generated_at"] = strategy_weight.get("generated_at")
            spec["strategy_weight_state_version"] = strategy_weight.get("version")
            family_consensus_score, family_consensus_components = _family_consensus_detail(spec)
            spec["family_consensus_score"] = round(float(family_consensus_score), 6)
            spec["family_consensus_components"] = dict(family_consensus_components)
            spec["quality_detail"] = {
                **dict(spec.get("quality_detail") or {}),
                "family_consensus_score": spec["family_consensus_score"],
                "family_consensus_components": dict(family_consensus_components),
            }
            spec["family_survived"] = True
            spec["family_reject_reason"] = None
            spec["family_strength"] = round(
                min(
                    5.0,
                    (
                        (float(spec.get("family_strength") or 0.0) * 0.70)
                        + (family_learning_adjustment * 2.0)
                        + (float(spec.get("strategy_weight_adjustment") or 0.0) * 1.5)
                        + (float(spec.get("family_consensus_score") or 0.0) * 5.0 * 0.30)
                    ),
                ),
                6,
            )
        raw_candidate_count = len(opportunity_specs) + len(pre_generation_filtered_specs)
        family_filtered_specs = list(pre_generation_filtered_specs)
        fatal_family_blockers = {
            "insufficient_positive_bearish_structure",
            "insufficient_positive_bullish_structure",
            "bearish_regime_countertrend_family",
            "bullish_regime_countertrend_family",
            "sideways_regime_weak_directional_family",
            "low_vol_regime_weak_directional_family",
        }
        for spec in opportunity_specs:
            blocker = str(spec.get("family_blocker") or "").strip().lower() or None
            if blocker in fatal_family_blockers:
                family_filtered_specs.append(
                    {
                        "strategy": spec.get("strategy"),
                        "strategy_family": spec.get("strategy_family"),
                        "direction_family": spec.get("direction_family"),
                        "session_mode": session_mode,
                        "strategy_regime_mode": strategy_regime_mode,
                        "family_consensus_score": spec.get("family_consensus_score"),
                        "quality_score": spec.get("quality_score"),
                        "family_blocker": blocker,
                        "family_allowed_in_context": spec.get("family_allowed_in_context"),
                        "family_gate_reason": spec.get("family_gate_reason"),
                        "family_gate_override_applied": spec.get("family_gate_override_applied"),
                    }
                )
                continue
            family = str(spec.get("direction_family") or "sideways").strip().lower() or "sideways"
            spec["direction_family"] = family
            spec["family_strength"] = round(float(spec.get("family_strength") or 0.0), 6)
            spec["family_blocker"] = blocker
        opportunity_specs = [
            spec
            for spec in opportunity_specs
            if str(spec.get("family_blocker") or "").strip().lower() not in fatal_family_blockers
        ]
        if opportunity_specs:
            grouped_specs: dict[str, list[dict]] = {}
            for spec in opportunity_specs:
                grouped_specs.setdefault(str(spec.get("direction_family") or "sideways"), []).append(spec)
            scarce_specs: list[dict] = []
            for family, specs in grouped_specs.items():
                capped_specs = sorted(
                    specs,
                    key=lambda row: (
                        -float(row.get("family_consensus_score") or 0.0),
                        -float(row.get("family_strength") or 0.0),
                        -float(row.get("quality_score") or 0.0),
                        str(row.get("strategy") or ""),
                    ),
                )
                strategy_state_applied = any(bool(row.get("strategy_weight_applied", False)) for row in capped_specs)
                hard_family_cap = (
                    family_max_candidates
                    if (strategy_weight_learning_enabled and not strategy_state_applied)
                    else max(1, family_max_candidates + max_family_scarcity_delta)
                )
                family_cap = family_max_candidates
                family_cap_reasons: list[str] = []
                if strategy_regime_sideways and family in {"bullish", "bearish"}:
                    family_cap = min(family_cap, sideways_family_max_candidates)
                    family_cap_reasons.append("sideways_directional_cap")
                if low_vol_regime:
                    family_cap = min(family_cap, 1)
                    family_cap_reasons.append("low_vol_sparse_cap")
                if uncertain_regime:
                    family_cap = min(family_cap, uncertain_family_max_candidates)
                    family_cap_reasons.append("uncertain_sparse_cap")
                if market_quality_score < 0.45 and family in {"bullish", "bearish"}:
                    family_cap = min(family_cap, 1)
                    family_cap_reasons.append("weak_market_quality_cap")
                top_family_consensus = max(
                    (float(row.get("family_consensus_score") or 0.0) for row in capped_specs),
                    default=0.0,
                )
                family_consensus_threshold = float(regime_policy.get("family_consensus_min_score") or 0.48)
                if top_family_consensus < family_consensus_threshold:
                    family_filtered_specs.append(
                        {
                            "strategy_family": next(
                                (str(row.get("strategy_family") or "") for row in capped_specs if row.get("strategy_family")),
                                "unknown",
                            ),
                            "direction_family": family,
                            "session_mode": session_mode,
                            "strategy_regime_mode": strategy_regime_mode,
                            "family_consensus_score": round(float(top_family_consensus), 6),
                            "family_blocker": "family_consensus_below_threshold",
                            "family_allowed_in_context": next(
                                (row.get("family_allowed_in_context") for row in capped_specs if row.get("family_allowed_in_context") is not None),
                                None,
                            ),
                            "family_gate_reason": next(
                                (row.get("family_gate_reason") for row in capped_specs if row.get("family_gate_reason") is not None),
                                None,
                            ),
                            "family_gate_override_applied": any(bool(row.get("family_gate_override_applied", False)) for row in capped_specs),
                            "family_reject_reason": "family_consensus_below_threshold",
                            "family_survived": False,
                        }
                    )
                    continue
                family_scarcity_delta = 0
                negative_deltas = [
                    max(
                        -max_family_scarcity_delta,
                        min(
                            max_family_scarcity_delta,
                            int(row.get("family_scarcity_adjustment") or 0) + int(row.get("strategy_scarcity_adjustment") or 0),
                        ),
                    )
                    for row in capped_specs
                    if (
                        max(
                            -max_family_scarcity_delta,
                            min(
                                max_family_scarcity_delta,
                                int(row.get("family_scarcity_adjustment") or 0) + int(row.get("strategy_scarcity_adjustment") or 0),
                            ),
                        )
                        < 0
                    )
                ]
                positive_deltas = [
                    max(
                        -max_family_scarcity_delta,
                        min(
                            max_family_scarcity_delta,
                            int(row.get("family_scarcity_adjustment") or 0) + int(row.get("strategy_scarcity_adjustment") or 0),
                        ),
                    )
                    for row in capped_specs
                    if (
                        max(
                            -max_family_scarcity_delta,
                            min(
                                max_family_scarcity_delta,
                                int(row.get("family_scarcity_adjustment") or 0) + int(row.get("strategy_scarcity_adjustment") or 0),
                            ),
                        )
                        > 0
                    )
                ]
                regime_aligned = bool(
                    (family == "bullish" and bullish_regime)
                    or (family == "bearish" and bearish_regime)
                    or (family == "sideways" and strategy_regime_sideways)
                )
                if regime_aligned and positive_deltas:
                    family_scarcity_delta = max(positive_deltas)
                    family_cap_reasons.append("learning_positive_delta")
                elif negative_deltas:
                    family_scarcity_delta = min(negative_deltas)
                    family_cap_reasons.append("learning_negative_delta")
                if regime_aligned and family_scarcity_delta > 0 and top_family_consensus >= max(family_consensus_threshold + 0.10, 0.70):
                    family_cap = min(hard_family_cap, family_cap + 1)
                    family_cap_reasons.append("strong_aligned_family")
                family_cap = min(hard_family_cap, max(1, int(family_cap) + int(family_scarcity_delta)))
                for rank_idx, spec in enumerate(capped_specs, start=1):
                    spec["family_rank"] = rank_idx
                    spec["family_cap_effective"] = int(family_cap)
                    spec["family_cap_reason"] = "|".join(family_cap_reasons) if family_cap_reasons else "base_cap"
                    spec["family_survived"] = True
                    spec["family_reject_reason"] = None
                    if rank_idx > family_cap:
                        family_filtered_specs.append(
                            {
                                "strategy": spec.get("strategy"),
                                "strategy_family": spec.get("strategy_family"),
                                "direction_family": family,
                                "session_mode": session_mode,
                                "strategy_regime_mode": strategy_regime_mode,
                            "family_consensus_score": spec.get("family_consensus_score"),
                            "quality_score": spec.get("quality_score"),
                            "family_blocker": "family_scarcity_cap",
                            "family_allowed_in_context": spec.get("family_allowed_in_context"),
                            "family_gate_reason": spec.get("family_gate_reason"),
                            "family_gate_override_applied": spec.get("family_gate_override_applied"),
                            "family_reject_reason": "family_scarcity_cap",
                            "family_survived": False,
                        }
                        )
                        continue
                    scarce_specs.append(spec)
            opportunity_specs = sorted(
                scarce_specs,
                key=lambda row: (
                    -float(row.get("family_consensus_score") or 0.0),
                    -float(row.get("quality_score") or 0.0),
                    -float(row.get("family_strength") or 0.0),
                    str(row.get("strategy") or ""),
                ),
            )
        candidates: list[Trade] = []
        for spec in opportunity_specs:
            trade = self._build_advisory_opportunity_trade(
                market_data,
                ltp=underlying_ltp,
                vwap=underlying_vwap,
                direction=spec["direction"],
                strategy=spec["strategy"],
                reason=spec["reason"],
                confidence=float(spec["confidence"]),
                strategy_family=spec["strategy_family"],
                candidate_type=spec["candidate_type"],
                setup_variant=spec["setup_variant"],
                trigger_reason=trigger_reason,
                soft_veto_codes=list(spec["soft_veto_codes"]),
                penalty_reasons=list(spec["penalty_reasons"]),
                quality_score=float(spec["quality_score"]),
                quality_detail=dict(spec["quality_detail"]),
                direction_family=str(spec.get("direction_family") or "sideways"),
                family_rank=int(spec.get("family_rank") or 1),
                family_blocker=spec.get("family_blocker"),
                family_strength=float(spec.get("family_strength") or 0.0),
                family_feedback_detail={
                    "family_feedback_adjustment": round(float(spec.get("family_feedback_adjustment") or 0.0), 6),
                    "family_feedback_confidence": round(float(spec.get("family_feedback_confidence") or 0.0), 6),
                    "family_feedback_applied": bool(spec.get("family_feedback_applied", False)),
                    "family_learning_adjustment": round(float(spec.get("family_learning_adjustment") or 0.0), 6),
                    "family_cap_effective": int(spec.get("family_cap_effective") or family_max_candidates),
                    "family_cap_reason": spec.get("family_cap_reason"),
                    "family_consensus_score": round(float(spec.get("family_consensus_score") or 0.0), 6),
                    "family_consensus_components": dict(spec.get("family_consensus_components") or {}),
                    "family_survived": bool(spec.get("family_survived", True)),
                    "family_reject_reason": spec.get("family_reject_reason"),
                    "expectancy_score": round(float(spec.get("expectancy_score") or 0.0), 6),
                    "family_learning_state_generated_at": spec.get("family_learning_state_generated_at"),
                    "family_learning_state_version": spec.get("family_learning_state_version"),
                    "strategy_weight_adjustment": round(float(spec.get("strategy_weight_adjustment") or 0.0), 6),
                    "strategy_weight_confidence": round(float(spec.get("strategy_weight_confidence") or 0.0), 6),
                    "strategy_weight_applied": bool(spec.get("strategy_weight_applied", False)),
                    "strategy_weight_state_generated_at": spec.get("strategy_weight_state_generated_at"),
                    "strategy_weight_state_version": spec.get("strategy_weight_state_version"),
                },
            )
            if trade is not None:
                candidates.append(trade)
        surviving_candidate_count = len(candidates)
        raw_candidate_count = max(raw_candidate_count, surviving_candidate_count + len(family_filtered_specs))
        survival_rate = (
            float(surviving_candidate_count) / max(1, int(raw_candidate_count))
            if raw_candidate_count > 0
            else 0.0
        )
        executable_rate = (
            float(sum(1 for candidate in candidates if bool(getattr(candidate, "execution_allowed", False))))
            / max(1, int(raw_candidate_count))
            if raw_candidate_count > 0
            else 0.0
        )
        advisory_rate = (
            float(
                sum(
                    1
                    for candidate in candidates
                    if str(getattr(candidate, "candidate_class", None) or getattr(candidate, "candidate_status", "")).strip().lower() in {"advisory_only", "advisory"}
                )
            )
            / max(1, int(raw_candidate_count))
            if raw_candidate_count > 0
            else 0.0
        )
        family_counter: dict[str, int] = {}
        for candidate in candidates:
            family_key = str(getattr(candidate, "direction_family", None) or "unknown").strip().lower() or "unknown"
            family_counter[family_key] = family_counter.get(family_key, 0) + 1
        top_family_share = (
            float(max(family_counter.values())) / max(1, surviving_candidate_count)
            if family_counter and surviving_candidate_count > 0
            else 0.0
        )
        starvation_reason = None
        if raw_candidate_count > 0 and survival_rate < float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_SURVIVAL_RATE_FLOOR", 0.25) or 0.25):
            starvation_reason = "survival_rate_below_floor"
        elif surviving_candidate_count > 0 and executable_rate <= 0.0:
            starvation_reason = "no_executable_candidates"
        elif top_family_share >= float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_TOP_FAMILY_SHARE_WARN", 0.75) or 0.75):
            starvation_reason = "family_dominance"
        starvation_flag = starvation_reason is not None
        decision_scope = f"builder:{str(market_data.get('symbol') or 'UNKNOWN').strip().upper()}:{str(trigger_reason or 'unknown').strip()}"
        decision_batch_id = hashlib.sha256(
            (
                f"{decision_scope}|{raw_candidate_count}|{surviving_candidate_count}|"
                + "|".join(
                    sorted(
                        str(getattr(candidate, "trade_id", None) or getattr(candidate, "strategy", None) or "")
                        for candidate in candidates
                    )
                )
            ).encode("utf-8")
        ).hexdigest()[:24]
        for filtered in family_filtered_specs:
            filtered_reason = str(
                filtered.get("family_reject_reason")
                or filtered.get("family_blocker")
                or "setup_filtered"
            ).strip().lower() or "setup_filtered"
            rejection_meta = classify_rejection_metadata(filtered_reason)
            filtered_record = {
                "timestamp": "",
                "decision_phase": "builder",
                "decision_scope": decision_scope,
                "decision_batch_id": decision_batch_id,
                "trade_id": None,
                "symbol": str(market_data.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN",
                "strategy": filtered.get("strategy"),
                "strategy_family": filtered.get("strategy_family"),
                "direction_family": filtered.get("direction_family"),
                "candidate_class": "ADVISORY_ONLY",
                "candidate_status": "advisory_only",
                "selected_for_execution": False,
                "market_mode": execution_mode,
                "session_mode": filtered.get("session_mode") or session_mode,
                "strategy_regime_mode": filtered.get("strategy_regime_mode") or strategy_regime_mode,
                "setup_score": None,
                "trigger_score": None,
                "entry_quality_score": None,
                "family_survival_score": filtered.get("family_consensus_score"),
                "priority_score": filtered.get("quality_score"),
                "final_score": filtered.get("quality_score"),
                "rejected_at_stage": rejection_meta.get("rejected_at_stage"),
                "rejection_reason_code": rejection_meta.get("rejection_reason_code"),
                "rejection_bucket": rejection_meta.get("rejection_bucket"),
                "rejection_severity": rejection_meta.get("rejection_severity"),
                "raw_candidate_count": raw_candidate_count,
                "surviving_candidate_count": surviving_candidate_count,
                "survival_rate": survival_rate,
                "executable_rate": executable_rate,
                "advisory_rate": advisory_rate,
                "no_trade_rate": 1.0 if executable_rate <= 0.0 else 0.0,
                "top_family_share": top_family_share,
                "starvation_flag": starvation_flag,
                "starvation_reason": starvation_reason,
                "warning_engine_too_timid": starvation_flag,
                "warning_family_starvation": starvation_reason == "family_dominance",
            }
            record_threshold_candidate_decision(filtered_record)
        enriched_candidates: list[Trade] = []
        for candidate in candidates:
            source_flags = dict(getattr(candidate, "source_flags", {}) or {})
            decision_record = build_audit_candidate_decision_record(
                candidate,
                decision_phase="builder",
                decision_scope=decision_scope,
                decision_batch_id=decision_batch_id,
                raw_candidate_count=raw_candidate_count,
                surviving_candidate_count=surviving_candidate_count,
                survival_rate=survival_rate,
                executable_rate=executable_rate,
                advisory_rate=advisory_rate,
                no_trade_rate=(1.0 if executable_rate <= 0.0 else 0.0),
                top_family_share=top_family_share,
                starvation_flag=starvation_flag,
                starvation_reason=starvation_reason,
                warning_engine_too_timid=starvation_flag,
                warning_family_starvation=(starvation_reason == "family_dominance"),
                stage_authority_warning=bool(getattr(candidate, "stage_authority_warning", False)),
            )
            record_threshold_candidate_decision(decision_record)
            source_flags.update(
                {
                    "rejected_at_stage": decision_record.get("rejected_at_stage"),
                    "rejection_reason_code": decision_record.get("rejection_reason_code"),
                    "rejection_bucket": decision_record.get("rejection_bucket"),
                    "rejection_severity": decision_record.get("rejection_severity"),
                    "stage_authority_warning": bool(decision_record.get("stage_authority_warning", False)),
                    "raw_candidate_count": raw_candidate_count,
                    "surviving_candidate_count": surviving_candidate_count,
                    "survival_rate": round(float(survival_rate), 6),
                    "executable_rate": round(float(executable_rate), 6),
                    "advisory_rate": round(float(advisory_rate), 6),
                    "no_trade_rate": round(float(1.0 if executable_rate <= 0.0 else 0.0), 6),
                    "top_family_share": round(float(top_family_share), 6),
                    "starvation_flag": bool(starvation_flag),
                    "starvation_reason": starvation_reason,
                    "warning_engine_too_timid": bool(starvation_flag),
                    "warning_filtering_without_edge_improvement": False,
                    "warning_family_starvation": bool(starvation_reason == "family_dominance"),
                    "warning_threshold_cluster": False,
                }
            )
            enriched_candidates.append(
                replace(
                    candidate,
                    source_flags=source_flags,
                    rejected_at_stage=decision_record.get("rejected_at_stage"),
                    rejection_reason_code=decision_record.get("rejection_reason_code"),
                    rejection_bucket=decision_record.get("rejection_bucket"),
                    rejection_severity=decision_record.get("rejection_severity"),
                    stage_authority_warning=bool(decision_record.get("stage_authority_warning", False)),
                    raw_candidate_count=int(raw_candidate_count),
                    surviving_candidate_count=int(surviving_candidate_count),
                    survival_rate=round(float(survival_rate), 6),
                    executable_rate=round(float(executable_rate), 6),
                    advisory_rate=round(float(advisory_rate), 6),
                    no_trade_rate=round(float(1.0 if executable_rate <= 0.0 else 0.0), 6),
                    top_family_share=round(float(top_family_share), 6),
                    starvation_flag=bool(starvation_flag),
                    starvation_reason=starvation_reason,
                    warning_engine_too_timid=bool(starvation_flag),
                    warning_filtering_without_edge_improvement=False,
                    warning_family_starvation=bool(starvation_reason == "family_dominance"),
                    warning_threshold_cluster=False,
                    strategy_regime_mode=strategy_regime_mode,
                )
            )
        candidates = enriched_candidates
        logger.info(
            "OPPORTUNITY_SET_BUILT %s",
            {
                "symbol": str(market_data.get("symbol") or "UNKNOWN"),
                "trigger_reason": trigger_reason,
                "nonlive_feature_fallback": bool(nonlive_feature_fallback),
                "fallback_fields": list(fallback_fields),
                "strategy_regime_mode": strategy_regime_mode,
                "breakout_strength": round(float(min(breakout_strength, 5.0)), 6),
                "mean_reversion_strength": round(float(min(mean_reversion_strength, 5.0)), 6),
                "volatility_expansion_strength": round(float(min(volatility_expansion_strength, 5.0)), 6),
                "bullish_family_strength": bullish_structure_strength,
                "bearish_family_strength": bearish_structure_strength,
                "family_filtered": family_filtered_specs,
                "family_learning_enabled": family_learning_enabled,
                "strategy_weight_learning_enabled": strategy_weight_learning_enabled,
                "raw_candidate_count": raw_candidate_count,
                "surviving_candidate_count": surviving_candidate_count,
                "survival_rate": round(float(survival_rate), 6),
                "executable_rate": round(float(executable_rate), 6),
                "advisory_rate": round(float(advisory_rate), 6),
                "top_family_share": round(float(top_family_share), 6),
                "starvation_flag": bool(starvation_flag),
                "starvation_reason": starvation_reason,
                "count": len(candidates),
                "families": [getattr(candidate, "strategy", None) for candidate in candidates],
                "direction_families": [getattr(candidate, "direction_family", None) for candidate in candidates],
            },
        )
        return candidates

    def _rank_nonlive_opportunity_candidates(
        self,
        market_data: dict,
        *,
        ltp: float,
        vwap: float,
        trigger_reason: str,
        scope_suffix: str,
    ):
        candidates = self._build_nonlive_opportunity_candidates(
            market_data,
            ltp=ltp,
            vwap=vwap,
            trigger_reason=trigger_reason,
        )
        if not candidates:
            return None
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        ranked_candidates = annotate_ranked_opportunities(
            candidates,
            scope=f"build:{symbol}:{scope_suffix}",
            top_n=int(getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)),
        )
        if not ranked_candidates:
            return None
        self._store_ranked_candidate_snapshots(ranked_candidates)
        self._scan_total_candidates = max(int(self._scan_total_candidates or 0), len(candidates))
        self._scan_accepted = int(len(ranked_candidates))
        logger.info(
            "OPPORTUNITY_SET_RANKED %s",
            {
                "symbol": symbol,
                "trigger_reason": trigger_reason,
                "ranked_count": len(ranked_candidates),
                "top_strategy": getattr(ranked_candidates[0], "strategy", None),
                "nonlive_feature_fallback": bool(market_data.get("nonlive_feature_fallback")),
                "fallback_fields": [
                    str(field)
                    for field in (market_data.get("nonlive_feature_fallback_fields") or [])
                    if str(field).strip()
                ],
            },
        )
        return ranked_candidates[0]

    def _build_planning_no_signal_trade(
        self,
        market_data: dict,
        *,
        ltp: float,
        vwap: float,
    ):
        if not bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)):
            return None
        underlying_ltp = float(ltp or 0.0)
        underlying_vwap = float(vwap or underlying_ltp or 0.0)
        direction = "BUY_CALL" if underlying_ltp >= underlying_vwap else "BUY_PUT"
        planning_confidence = float(getattr(cfg, "PLANNING_SIGNAL_SCORE_BASE", 0.56))
        return self._build_advisory_opportunity_trade(
            market_data,
            ltp=underlying_ltp,
            vwap=underlying_vwap,
            direction=direction,
            strategy="NO_SIGNAL_PLANNING",
            reason="NO_SIGNAL_PLANNING_FALLBACK",
            confidence=planning_confidence,
            strategy_family="continuation",
            candidate_type="directional",
            setup_variant="no_signal_planning",
            trigger_reason="NO_SIGNAL_PLANNING_FALLBACK",
        )

    def _resolve_index_bid_ask(self, market_data: dict, exec_mode: str) -> dict:
        """
        Resolve index bid/ask for intent gating.
        LIVE: fail-closed on missing/invalid bid/ask.
        PAPER/SIM: synthesize only for index symbols using LTP when depth is missing.
        """
        symbol = str(market_data.get("symbol") or "")
        source = str(
            market_data.get("index_quote_source")
            or market_data.get("quote_source")
            or "real"
        )

        def _as_valid_price(value):
            try:
                p = float(value)
                if p > 0:
                    return p
            except Exception:
                return None
            return None

        def _is_index_symbol(sym: str) -> bool:
            s = str(sym or "").upper()
            configured = {
                str(k).upper()
                for k in (getattr(cfg, "PREMARKET_INDICES_LTP", {}) or {}).keys()
                if str(k or "").strip()
            }
            if configured:
                return s in configured
            return s in {"NIFTY", "BANKNIFTY", "SENSEX"}

        explicit_quote_cache = "index_quote_cache" in market_data
        quote_cache = market_data.get("index_quote_cache")
        if not isinstance(quote_cache, dict):
            quote_cache = {}
        if (not explicit_quote_cache) and (not quote_cache) and symbol:
            try:
                from core.market_quote_resolver import get_index_quote_snapshot

                quote_cache = get_index_quote_snapshot(symbol) or {}
            except Exception:
                quote_cache = {}

        bid = _as_valid_price(market_data.get("bid"))
        ask = _as_valid_price(market_data.get("ask"))
        ltp = _as_valid_price(market_data.get("ltp"))
        ltp_ts_epoch = market_data.get("ltp_ts_epoch")
        now_epoch_for_age = market_data.get("timestamp")
        if now_epoch_for_age is None:
            now_epoch_for_age = now_utc_epoch()
        ltp_age_sec = compute_age_sec(ltp_ts_epoch, now_epoch_for_age)
        last_price = _as_valid_price(
            quote_cache.get("last_price")
            if isinstance(quote_cache, dict)
            else None
        )
        preexisting_synthetic = bool(market_data.get("index_bidask_synthetic")) or source in ("synthetic", "synthetic_index")
        # Single resolver path shared with core.market_data
        is_index = _is_index_symbol(symbol)
        synthetic = False
        try:
            from core.market_quote_resolver import resolve_index_quote

            resolved = resolve_index_quote(
                symbol=symbol,
                mode=exec_mode,
                ltp=(ltp if ltp is not None else last_price),
                depth={"bid": bid, "ask": ask},
                market_open=bool(market_data.get("market_open", True)),
                ltp_age_sec=ltp_age_sec,
                market_context=market_data.get("market_context"),
            )
            bid = _as_valid_price(resolved.get("bid"))
            ask = _as_valid_price(resolved.get("ask"))
            source = str(resolved.get("quote_source") or source or "missing_depth")
            synthetic = source == "synthetic_index"
            market_data["quote_ok"] = bool(resolved.get("quote_ok", False))
            if synthetic:
                market_data["quote_ts_epoch"] = float(now_epoch_for_age)
                market_data["quote_age_sec"] = 0.0
        except Exception:
            pass

        has_bid_ask = (bid is not None) and (ask is not None)
        quote_kind = "synthetic" if (synthetic or (preexisting_synthetic and has_bid_ask)) else ("real" if has_bid_ask else "missing")
        market_data["index_quote_source"] = source if quote_kind != "missing" else ("missing_depth" if is_index else "missing")
        market_data["quote_source"] = market_data["index_quote_source"]
        market_data["index_bidask_synthetic"] = bool(synthetic or (preexisting_synthetic and has_bid_ask))
        market_data["index_quote_kind"] = quote_kind
        if bid is not None:
            market_data["bid"] = bid
        if ask is not None:
            market_data["ask"] = ask

        _log_signal_event(
            "index_bidask_source",
            symbol,
            {
                "source": market_data.get("index_quote_source"),
                "quote_kind": market_data.get("index_quote_kind"),
                "synthetic": bool(market_data.get("index_bidask_synthetic", False)),
                "bid": market_data.get("bid"),
                "ask": market_data.get("ask"),
                "last_price": last_price,
                "ltp": ltp,
                "mode": exec_mode,
                "is_index": is_index,
                "quote_source": market_data.get("quote_source"),
            },
        )
        return market_data

    def trade_intent_flags(
        self,
        market_data: dict,
        opt: dict | None = None,
        risk_guard_passed: bool | None = None,
        additional_blockers: list[str] | None = None,
    ) -> dict:
        segment = market_data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        inferred_market_open = bool(market_data.get("market_open")) if ("market_open" in market_data) else bool(is_market_open_ist(segment=segment))
        ctx_payload = dict(market_data.get("market_context") or {}) if isinstance(market_data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = getattr(cfg, "EXECUTION_MODE", "SIM")
        if "market_open" not in ctx_payload:
            ctx_payload["market_open"] = inferred_market_open
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = segment
        market_ctx = derive_market_context(ctx_payload)
        market_open = bool(market_ctx.is_market_open)
        offhours_mode = bool(market_ctx.mode == "OFFHOURS")
        allow_stale_quotes = bool(market_ctx.allow_stale_quotes)
        planning_only_mode = bool(getattr(market_ctx, "planning_only", False))
        chain_source = market_data.get("chain_source", "empty")
        require_live_quotes = bool(market_ctx.require_live_quotes and getattr(cfg, "REQUIRE_LIVE_QUOTES", True))
        quote_ok = market_data.get("quote_ok", True)
        quote_age_sec = market_data.get("quote_age_sec")
        index_quote_source = market_data.get("index_quote_source", "real")
        index_bidask_synthetic = bool(market_data.get("index_bidask_synthetic", False))
        index_quote_kind = market_data.get("index_quote_kind", "real")
        if opt is not None:
            quote_ok = opt.get("quote_ok", quote_ok)
            quote_age_sec = opt.get("quote_age_sec", quote_age_sec)
        ltp = market_data.get("ltp", 0)
        try:
            ltp = float(ltp) if ltp is not None else 0.0
        except Exception:
            ltp = 0.0
        ltp_source = market_data.get("ltp_source", "none")
        reasons: list[str] = []
        strict_quote_checks = bool(require_live_quotes and (not allow_stale_quotes))
        if market_data.get("valid") is False:
            reasons.append(str(market_data.get("invalid_reason") or "invalid_snapshot"))
        if (not market_open) and (not planning_only_mode):
            reasons.append("market_closed")
        if strict_quote_checks and chain_source != "live":
            reasons.append("chain_not_live")
        if strict_quote_checks and quote_ok is not True:
            reasons.append("quote_not_ok")
        max_quote_age = float(
            getattr(
                cfg,
                "OFFHOURS_MAX_OPTION_QUOTE_AGE_SEC" if allow_stale_quotes else "MAX_OPTION_QUOTE_AGE_SEC",
                60 if allow_stale_quotes else 8,
            )
        )
        if strict_quote_checks and quote_age_sec is None:
            reasons.append("quote_age_missing")
        elif strict_quote_checks and float(quote_age_sec) > max_quote_age:
            reasons.append("stale_option_quote")
        live_ltp_required = bool(market_ctx.mode == "LIVE" and market_open and (not allow_stale_quotes))
        if live_ltp_required and ltp_source != "live":
            reasons.append("ltp_not_live")
        if strict_quote_checks and (ltp is None or float(ltp) <= 0):
            reasons.append("invalid_ltp")
        if risk_guard_passed is False:
            reasons.append("risk_guard_failed")
        for blocker in additional_blockers or []:
            if blocker and blocker not in reasons:
                reasons.append(str(blocker))

        planning_only = bool(planning_only_mode)
        execution_like_modes = {"LIVE", "PAPER", "SIM"}
        hard_blocker_set = {
            "invalid_ltp",
            "risk_guard_failed",
            "invalid_snapshot",
            "instrument_missing",
            "missing_instrument_id",
            "missing_contract_fields",
            "unresolved_contract",
            "missing_live_bidask",
            "no_option_quote_source",
            "option_quote_missing",
            "no_quote",
            "spread_pct",
            "iv_term",
            "iv_surface_slope",
        }
        hard_blockers = [r for r in reasons if str(r).lower() in hard_blocker_set]
        if market_ctx.mode == "LIVE":
            execution_allowed = bool(market_open and (len(reasons) == 0) and (not planning_only))
        else:
            execution_allowed = bool(
                (market_ctx.mode in execution_like_modes)
                and market_open
                and (len(hard_blockers) == 0)
                and (not planning_only)
            )
        if planning_only:
            if market_ctx.mode == "OFFHOURS":
                execution_reason = "OFFHOURS_PLANNING"
            else:
                execution_reason = "PLANNING_ONLY_MODE"
        else:
            execution_reason = reasons[0] if reasons else None

        return {
            "tradable": len(reasons) == 0,
            "tradable_reasons_blocking": reasons,
            "planning_only": planning_only,
            "execution_allowed": execution_allowed,
            "execution_reason": execution_reason,
            "source_flags": {
                "runtime_mode": market_ctx.mode,
                "chain_source": chain_source,
                "quote_ok": bool(quote_ok),
                "quote_age_sec": quote_age_sec,
                "market_open": market_open,
                "offhours_mode": bool(offhours_mode),
                "allow_stale_quotes": bool(allow_stale_quotes),
                "require_live_quotes": require_live_quotes,
                "ltp_source": ltp_source,
                "snapshot_valid": bool(market_data.get("valid", True)),
                "risk_guard_passed": risk_guard_passed,
                "index_quote_source": index_quote_source,
                "index_bidask_synthetic": index_bidask_synthetic,
                "index_quote_kind": index_quote_kind,
                "planning_only_mode": bool(planning_only_mode),
                "planning_only": planning_only,
                "execution_allowed": execution_allowed,
            },
        }

    def _feature_contract(self):
        try:
            getter = getattr(self.predictor, "get_feature_contract", None)
            if callable(getter):
                return getter()
        except Exception:
            pass
        return None

    def _validate_ml_features(self, feats: pd.DataFrame):
        contract = self._feature_contract()
        if contract is None:
            return True, "ok"
        ok, reason = validate_trade_features(feats, required_features=contract.required_features)
        return ok, reason

    def _apply_decay_gate(self, strategy_name, base_score=None, size_mult=1.0):
        if not strategy_name or not self.strategy_tracker:
            return True, base_score, size_mult, None
        if self.strategy_tracker.is_quarantined(strategy_name):
            prob = self.strategy_tracker.decay_prob(strategy_name)
            self._reject_ctx = {"strategy": strategy_name, "reason": "strategy_quarantined", "decay_prob": prob}
            return False, base_score, size_mult, "strategy_quarantined"
        if self.strategy_tracker.is_decaying(strategy_name):
            prob = self.strategy_tracker.decay_prob(strategy_name)
            penalty = float(getattr(cfg, "DECAY_DOWNSIZE_MULT", 0.6))
            new_score = base_score * penalty if base_score is not None else None
            new_mult = min(size_mult, penalty)
            self._reject_ctx = {"strategy": strategy_name, "reason": "strategy_decaying", "decay_prob": prob}
            return True, new_score, new_mult, "strategy_decaying"
        return True, base_score, size_mult, None

    def _apply_lifecycle_gate(self, strategy_name, mode="MAIN"):
        try:
            allowed, reason = self.lifecycle.can_allocate(strategy_name, mode=mode)
            if not allowed:
                self._reject_ctx = {
                    "strategy": strategy_name,
                    "reason": reason,
                    "lifecycle_state": self.lifecycle.get_state(strategy_name),
                }
            return allowed, reason
        except Exception:
            self._reject_ctx = {"strategy": strategy_name, "reason": "lifecycle_error"}
            return False, "lifecycle_error"

    @staticmethod
    def _clamp_confidence(value: float | None) -> float | None:
        try:
            if value is None:
                return None
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return None

    def _blend_micro_confidence(self, model_conf: float | None, micro_conf: float | None) -> tuple[float | None, str | None]:
        model_val = self._clamp_confidence(model_conf)
        micro_val = self._clamp_confidence(micro_conf)
        if model_val is None and micro_val is None:
            return None, None
        if model_val is None:
            return micro_val, "micro_fallback"
        if micro_val is None:
            return model_val, "model_only"
        weight = max(0.0, min(1.0, float(getattr(cfg, "MICRO_CONF_OVERLAY_WEIGHT", 0.25))))
        max_delta = max(0.0, min(1.0, float(getattr(cfg, "MICRO_CONF_OVERLAY_MAX_DELTA", 0.10))))
        adjustment = (micro_val - model_val) * weight
        adjustment = max(-max_delta, min(max_delta, adjustment))
        return self._clamp_confidence(model_val + adjustment), "bounded_overlay"

    def _orb_soft_veto_conf_penalty(self) -> float:
        legacy_default = max(0.0, 1.0 - float(getattr(cfg, "ORB_SOFT_VETO_CONF_MULT", 0.95)))
        penalty = float(getattr(cfg, "ORB_SOFT_VETO_CONF_PENALTY", legacy_default))
        return max(0.0, min(1.0, penalty))

    def _premium_soft_veto_conf_penalty(self, penalty_scale: float | None) -> float:
        penalty_min = max(
            0.0,
            min(
                1.0,
                float(
                    getattr(
                        cfg,
                        "PREMIUM_SOFT_VETO_CONF_PENALTY_MIN",
                        max(0.0, 1.0 - float(getattr(cfg, "PREMIUM_SOFT_VETO_CONF_MULT", 0.92))),
                    )
                ),
            ),
        )
        penalty_max = max(
            penalty_min,
            min(1.0, float(getattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", max(penalty_min, 0.12)))),
        )
        scale = max(0.0, min(1.0, float(penalty_scale or 0.0)))
        return max(0.0, min(1.0, penalty_min + ((penalty_max - penalty_min) * scale)))

    def _apply_alpha_ensemble(
        self,
        base_conf: float,
        xgb_conf: Optional[float],
        deep_conf: Optional[float],
        micro_conf: Optional[float],
        market_data: dict,
        quick_mode: bool = False,
    ):
        if not self.alpha_ensemble or not getattr(cfg, "ALPHA_ENSEMBLE_ENABLE", True):
            return base_conf, None, None, 1.0
        if xgb_conf is None and deep_conf is None and micro_conf is None and getattr(self.alpha_ensemble, "meta_model", None) is None:
            return base_conf, None, None, 1.0
        alpha = self.alpha_ensemble.combine(
            xgb_conf=xgb_conf,
            deep_conf=deep_conf,
            micro_conf=micro_conf,
            regime_probs=market_data.get("regime_probs") or {},
            shock_score=market_data.get("shock_score") or 0.0,
            cross=market_data,
        )
        alpha_conf = alpha.get("final_prob")
        alpha_unc = alpha.get("uncertainty")
        size_mult = alpha.get("size_mult", 1.0)
        veto_th = getattr(cfg, "ALPHA_UNCERTAINTY_VETO", 0.78)
        if alpha_unc is not None and alpha_unc >= veto_th and not quick_mode:
            return None, alpha_conf, alpha_unc, size_mult
        return float(alpha_conf), alpha_conf, alpha_unc, size_mult

    def _ml_history_count(self):
        try:
            now = _time.time()
            if now - self._ml_history_cache["ts"] < 60:
                return self._ml_history_cache["count"]
            path = data_root() / "trade_log.json"
            if not path.exists():
                self._ml_history_cache = {"ts": now, "count": 0}
                return 0
            count = 0
            with path.open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("actual") is not None:
                        count += 1
            self._ml_history_cache = {"ts": now, "count": count}
            return count
        except Exception:
            return 0

    def _get_deep_predictor(self):
        if self._ml_disabled:
            return self._noop_predictor
        if self.deep_predictor is None:
            from ml.deep_predictor import DeepPredictor
            self.deep_predictor = DeepPredictor()
        return self.deep_predictor

    def _get_micro_predictor(self):
        if self._ml_disabled:
            return self._noop_predictor
        if self.micro_predictor is None:
            from ml.microstructure_predictor import MicrostructurePredictor
            self.micro_predictor = MicrostructurePredictor()
        return self.micro_predictor

    def _apply_entry_trigger(self, entry_price, side, quick_mode=False):
        """
        Adjust entry to a breakout trigger (buy above / sell below) if enabled.
        """
        try:
            mode = getattr(cfg, "ENTRY_TRIGGER_MODE", "ASK").upper()
            if getattr(cfg, "ENTRY_TRIGGER_MAIN_ONLY", True) and quick_mode:
                return entry_price, None, entry_price
            if mode not in ("BREAKOUT", "TRIGGER"):
                return entry_price, None, entry_price
            buffer_abs = float(getattr(cfg, "ENTRY_PREMIUM_BUFFER", 2.0))
            buffer_pct = float(getattr(cfg, "ENTRY_PREMIUM_BUFFER_PCT", 0.01))
            buffer = max(buffer_abs, entry_price * buffer_pct)
            if side.upper() == "BUY":
                trigger = round(entry_price + buffer, 2)
                return trigger, "BUY_ABOVE", entry_price
            else:
                trigger = round(max(entry_price - buffer, 0.01), 2)
                return trigger, "SELL_BELOW", entry_price
        except Exception:
            return entry_price, None, entry_price

    def allowed_strategy_families(self, regime: str) -> list[str]:
        regime_norm = normalize_regime(regime)
        if regime_norm == "TREND":
            return ["TREND"]
        if regime_norm == "RANGE":
            return ["MEAN_REVERT"]
        if regime_norm == "EVENT":
            if getattr(cfg, "REGIME_EVENT_ROUTE_ALLOW", True) and getattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True):
                return ["DEFINED_RISK"]
            return []
        return []

    def _resolve_regime(self, market_data: dict) -> str:
        raw = (
            market_data.get("regime_day")
            or market_data.get("primary_regime")
            or market_data.get("regime")
        )
        normalized = normalize_regime(raw)
        if normalized != "NEUTRAL":
            return normalized
        if not getattr(cfg, "REGIME_CLASSIFIER_ENABLE", True):
            return normalized
        return self.regime_classifier.classify(market_data or {})

    def _regime_route_family(self, regime: str) -> str | None:
        families = self.allowed_strategy_families(regime)
        if not families:
            return None
        return families[0]

    def _trend_vwap_fallback_signal(self, market_data: dict, regime_day: str):
        if not bool(getattr(cfg, "TREND_VWAP_FALLBACK_ENABLE", True)):
            return None
        exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
        if exec_mode == "LIVE" and not bool(getattr(cfg, "TREND_VWAP_FALLBACK_LIVE_ENABLE", False)):
            return None
        if not bool(market_data.get("indicators_ok", False)):
            return None
        primary_regime = normalize_regime(
            market_data.get("primary_regime") or market_data.get("regime") or regime_day
        )
        if primary_regime not in ("TREND", "EVENT"):
            return None
        vwap_slope = float(market_data.get("vwap_slope", 0.0) or 0.0)
        slope_abs_min = float(getattr(cfg, "TREND_VWAP_FALLBACK_SLOPE_ABS_MIN", 0.0008))
        orb_bias = str(market_data.get("orb_bias") or "").upper()
        orb_lock_min = int(market_data.get("orb_lock_min") or getattr(cfg, "ORB_LOCK_MIN", 15))
        minutes_since_open = float(market_data.get("minutes_since_open", 0) or 0)
        orb_locked = (
            orb_bias not in ("", "PENDING")
            and minutes_since_open >= orb_lock_min
        )
        if (not orb_locked) and (abs(vwap_slope) < slope_abs_min):
            return None
        direction = None
        if orb_locked and orb_bias in ("UP", "DOWN"):
            direction = "BUY_CALL" if orb_bias == "UP" else "BUY_PUT"
        elif vwap_slope > 0:
            direction = "BUY_CALL"
        elif vwap_slope < 0:
            direction = "BUY_PUT"
        if direction is None:
            return None
        score = float(getattr(cfg, "TREND_VWAP_FALLBACK_SCORE", 0.60))
        reason = "trend_vwap_fallback"
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        payload = {
            "fallback": reason,
            "direction": direction,
            "score": score,
            "primary_regime": primary_regime,
            "vwap_slope": vwap_slope,
            "orb_bias": orb_bias,
            "orb_locked": orb_locked,
            "exec_mode": exec_mode,
        }
        _log_signal_event("signal_fallback_trend_vwap", symbol, payload)
        logger.info(
            "TREND_VWAP_FALLBACK_SIGNAL symbol=%s direction=%s score=%s regime=%s vwap_slope=%s orb_bias=%s orb_locked=%s exec_mode=%s",
            symbol,
            direction,
            score,
            primary_regime,
            vwap_slope,
            orb_bias,
            orb_locked,
            exec_mode,
        )
        return {
            "direction": direction,
            "reason": reason,
            "score": score,
            "regime_day": primary_regime,
        }

    def _signal_for_symbol(self, market_data, force_family: str | None = None):
        instrument = market_data.get("instrument", "OPT")
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        ctx = market_data.get("market_context")
        ctx_mode = ctx.get("execution_mode") if isinstance(ctx, dict) else ""
        exec_mode = str(
            market_data.get("execution_mode") or ctx_mode or getattr(cfg, "EXECUTION_MODE", "")
        ).strip().upper()
        nonlive_feature_fallback = bool(market_data.get("nonlive_feature_fallback"))
        regime_day = self._resolve_regime(market_data)
        day_type = market_data.get("day_type") or "UNKNOWN"
        minutes_since_open = market_data.get("minutes_since_open", 0) or 0
        regime_probs = market_data.get("regime_probs") or {}
        regime_entropy = market_data.get("regime_entropy", 0.0) or 0.0
        unstable_regime = bool(market_data.get("unstable_regime_flag", False))
        # Time-of-day schedule buckets (open/mid/close)
        time_bucket = "MID"
        try:
            now = datetime.now().time()
            open_end = getattr(cfg, "DAYTYPE_BUCKET_OPEN_END", 11)
            mid_end = getattr(cfg, "DAYTYPE_BUCKET_MID_END", 14)
            if now.hour < open_end:
                time_bucket = "OPEN"
            elif now.hour >= mid_end:
                time_bucket = "CLOSE"
            else:
                time_bucket = "MID"
        except Exception:
            time_bucket = "MID"
        # Time-of-day rule: noon fade (prefer mean reversion 12:00–13:30 IST)
        noon_fade = False
        try:
            now = datetime.now().time()
            noon_fade = (now.hour == 12) or (now.hour == 13 and now.minute <= 30)
        except Exception:
            noon_fade = False
        if force_family is None and getattr(cfg, "REGIME_ROUTER_ENABLE", True):
            route_family = self._regime_route_family(regime_day)
            if route_family is None:
                if not (nonlive_feature_fallback and exec_mode in {"SIM", "PAPER", "OFFHOURS"}):
                    self._reject_ctx = {
                        "symbol": market_data.get("symbol"),
                        "reason": "unsupported_regime_route",
                        "regime": regime_day,
                    }
                    return None
            force_family = route_family
        if instrument in ("EQ", "FUT"):
            return None
        else:
            # Probabilistic regime gating
            if regime_probs and force_family is None:
                if unstable_regime:
                    return None

                trend_p = float(regime_probs.get("TREND", 0.0))
                range_p = max(float(regime_probs.get("RANGE", 0.0)), float(regime_probs.get("RANGE_VOLATILE", 0.0)))
                event_p = float(regime_probs.get("EVENT", 0.0))
                panic_p = float(regime_probs.get("PANIC", 0.0))
                if event_p >= getattr(cfg, "REGIME_PROB_EVENT", 0.4):
                    sig = event_breakout_signal(
                        market_data.get("ltp", 0),
                        market_data.get("atr", 0),
                        market_data.get("ltp_change_window", 0),
                    )
                    if sig:
                        sig.score = float(sig.score) * max(event_p, getattr(cfg, "REGIME_PROB_MIN", 0.45))
                        return {"direction": sig.direction, "reason": sig.reason, "score": sig.score, "regime_day": "EVENT"}
                if panic_p >= getattr(cfg, "REGIME_PROB_PANIC", 0.4):
                    sig = ensemble_signal(market_data)
                    if sig:
                        sig.score = float(sig.score) * max(panic_p, getattr(cfg, "REGIME_PROB_MIN", 0.45))
                        return {"direction": sig.direction, "reason": sig.reason, "score": sig.score, "regime_day": "PANIC"}
                if trend_p >= getattr(cfg, "REGIME_PROB_TREND", 0.45):
                    sig = ensemble_signal(market_data)
                    if sig:
                        sig.score = float(sig.score) * max(trend_p, getattr(cfg, "REGIME_PROB_MIN", 0.45))
                        return {"direction": sig.direction, "reason": sig.reason, "score": sig.score, "regime_day": "TREND"}
                if range_p >= getattr(cfg, "REGIME_PROB_RANGE", 0.45):
                    sig = mean_reversion_signal(
                        market_data.get("ltp", 0),
                        market_data.get("vwap", 0),
                        market_data.get("rsi_mom", 0),
                    )
                    if sig:
                        sig.score = float(sig.score) * max(range_p, getattr(cfg, "REGIME_PROB_MIN", 0.45))
                        return {"direction": sig.direction, "reason": sig.reason, "score": sig.score, "regime_day": "RANGE"}
            # Day-type gating: choose allowed strategies
            # Confidence threshold to allow switching strategies
            day_conf = market_data.get("day_confidence", 0) or 0
            conf_min = getattr(cfg, "DAYTYPE_CONF_SWITCH_MIN", 0.6)
            if day_conf < conf_min:
                day_type = "UNKNOWN"

            if force_family == "DEFINED_RISK":
                if not (getattr(cfg, "REGIME_EVENT_ROUTE_ALLOW", True) and getattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True)):
                    return None
                sig = event_breakout_signal(
                    market_data.get("ltp", 0),
                    market_data.get("atr", 0),
                    market_data.get("ltp_change_window", 0),
                )
                if not sig:
                    return None
                return {"direction": sig.direction, "reason": sig.reason, "score": sig.score, "regime_day": "EVENT"}
            if force_family == "TREND":
                sig = ensemble_signal(market_data)
            elif force_family == "MEAN_REVERT":
                sig = mean_reversion_signal(
                    market_data.get("ltp", 0),
                    market_data.get("vwap", 0),
                    market_data.get("rsi_mom", 0),
                )
            elif day_type in ("TREND_DAY", "PANIC_DAY", "EVENT_DAY"):
                if noon_fade:
                    sig = mean_reversion_signal(
                        market_data.get("ltp", 0),
                        market_data.get("vwap", 0),
                        market_data.get("rsi_mom", 0),
                    )
                else:
                    sig = ensemble_signal(market_data)
            elif day_type == "FAKE_BREAKOUT_DAY":
                sig = mean_reversion_signal(
                    market_data.get("ltp", 0),
                    market_data.get("vwap", 0),
                    market_data.get("rsi_mom", 0),
                )
            elif day_type == "TREND_RANGE_DAY":
                if time_bucket == "OPEN":
                    sig = ensemble_signal(market_data)
                else:
                    sig = mean_reversion_signal(
                        market_data.get("ltp", 0),
                        market_data.get("vwap", 0),
                        market_data.get("rsi_mom", 0),
                    )
            elif day_type == "RANGE_TREND_DAY":
                if time_bucket in ("OPEN", "MID"):
                    sig = mean_reversion_signal(
                        market_data.get("ltp", 0),
                        market_data.get("vwap", 0),
                        market_data.get("rsi_mom", 0),
                    )
                else:
                    sig = ensemble_signal(market_data)
            elif day_type in ("RANGE_DAY", "RANGE_VOLATILE", "EXPIRY_DAY"):
                sig = micro_pattern_signal(
                    market_data.get("ltp_change_5m", 0),
                    market_data.get("ltp_change_10m", 0),
                )
                if not sig:
                    sig = mean_reversion_signal(
                        market_data.get("ltp", 0),
                        market_data.get("vwap", 0),
                        market_data.get("rsi_mom", 0),
                    )
            elif regime_day in ("RANGE", "RANGE_VOLATILE"):
                sig = micro_pattern_signal(
                    market_data.get("ltp_change_5m", 0),
                    market_data.get("ltp_change_10m", 0),
                )
                if not sig:
                    sig = mean_reversion_signal(
                        market_data.get("ltp", 0),
                        market_data.get("vwap", 0),
                        market_data.get("rsi_mom", 0),
                    )
            elif regime_day == "EVENT":
                sig = event_breakout_signal(
                    market_data.get("ltp", 0),
                    market_data.get("atr", 0),
                    market_data.get("ltp_change_window", 0),
                )
            else:
                sig = ensemble_signal(market_data)
        if not sig:
            sig = self._trend_vwap_fallback_signal(market_data, regime_day)
            if not sig:
                if bool(getattr(cfg, "TRADE_BUILDER_RESULT_TRACE_ENABLE", True)):
                    logger.info("SIGNAL_RESULT symbol=%s signal=None", symbol)
                return None
        if isinstance(sig, dict):
            direction = sig.get("direction")
            reason = sig.get("reason")
            score = sig.get("score")
            sig_regime = normalize_regime(sig.get("regime_day") or regime_day)
        else:
            direction = sig.direction
            reason = sig.reason
            score = sig.score
            sig_regime = normalize_regime(regime_day)
        if bool(getattr(cfg, "TRADE_BUILDER_RESULT_TRACE_ENABLE", True)):
            logger.info(
                "SIGNAL_RESULT symbol=%s direction=%s score=%s reason=%s",
                symbol,
                direction,
                score,
                reason,
            )
        return {"direction": direction, "reason": reason, "score": score, "regime_day": sig_regime}

    def _opt_risk_levels(self, entry_price, bid, ask, base_atr, stop_mult=1.0, target_mult=1.5, regime=None, day_type=None, timestamp=None):
        """
        Option-specific risk levels using option premium + spread proxy, dynamically adapted to regime.
        """
        if regime in ("RANGE", "RANGE_VOLATILE"):
            stop_mult *= 0.6
            target_mult *= 0.8
        if day_type == "EXPIRY_DAY" and timestamp:
            try:
                dt = datetime.fromtimestamp(float(timestamp))
                if dt.hour >= 14:
                    stop_mult *= 0.8
                    target_mult *= 0.6
            except Exception:
                pass
        try:
            opt_atr_pct = getattr(cfg, "OPT_ATR_PCT", 0.2)
            spread_mult = getattr(cfg, "OPT_SPREAD_ATR_MULT", 3.0)
            spread = max((ask - bid), 0)
            opt_atr = max(entry_price * opt_atr_pct, spread * spread_mult)
            opt_atr = max(opt_atr, 1.0)
            stop_loss = max(entry_price - opt_atr * stop_mult, entry_price * 0.2)
            target = entry_price + opt_atr * target_mult
            return stop_loss, target
        except Exception:
            stop_loss = max(entry_price - base_atr, entry_price * 0.2)
            target = entry_price + base_atr * 1.5
            return stop_loss, target

    def _option_risk_proxy(self, entry_price, bid, ask) -> float:
        try:
            entry_f = float(entry_price)
        except Exception:
            entry_f = 0.0
        try:
            bid_f = float(bid if bid is not None else entry_f)
        except Exception:
            bid_f = entry_f
        try:
            ask_f = float(ask if ask is not None else entry_f)
        except Exception:
            ask_f = entry_f
        width = max(0.0, ask_f - bid_f)
        return max(width, entry_f * 0.08, 1.0)

    def _raw_confidence_gate_threshold(self, regime_day: str | None, *, quick_mode: bool = False) -> float:
        legacy_threshold = float(getattr(cfg, "ML_MIN_PROBA", 0.45))
        threshold = float(getattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", legacy_threshold))
        explicit_default = getattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN_DEFAULT", None)
        try:
            if explicit_default is not None and abs(float(threshold) - float(explicit_default)) <= 1e-9:
                threshold = legacy_threshold
        except Exception:
            threshold = legacy_threshold
        threshold *= float(getattr(cfg, "REGIME_PROBA_MULT", {}).get(regime_day or "NEUTRAL", 1.0))
        if quick_mode:
            threshold = min(threshold, float(getattr(cfg, "QUICK_MIN_PROBA", 0.35)))
        return max(0.0, min(1.0, threshold))

    def _final_confidence_gate_threshold(self, regime_day: str | None, *, quick_mode: bool = False) -> float:
        del regime_day, quick_mode
        legacy_threshold = float(
            getattr(
                cfg,
                "GATING_FINAL_CONFIDENCE_MIN",
                getattr(cfg, "CONFIDENCE_THRESHOLD_EXECUTION_LIVE", 0.30),
            )
        )
        threshold = float(getattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", legacy_threshold))
        explicit_default = getattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN_DEFAULT", None)
        try:
            if explicit_default is not None and abs(float(threshold) - float(explicit_default)) <= 1e-9:
                threshold = legacy_threshold
        except Exception:
            threshold = legacy_threshold
        return max(0.0, min(1.0, threshold))

    def _staged_confidence_payload(
        self,
        *,
        confidence: float | None,
        model_raw: float | None = None,
        model_component: float | None = None,
        micro_component: float | None = None,
        micro_blend_method: str | None = None,
        after_micro: float | None = None,
        after_alpha: float | None = None,
        after_latency: float | None = None,
        before_soft_veto: float | None = None,
        after_soft_veto: float | None = None,
        penalty_soft_veto_total: float | None = None,
        penalty_soft_veto_reasons: list[str] | None = None,
        gate_threshold: float | None = None,
        raw_gate_threshold: float | None = None,
        final_gate_threshold: float | None = None,
        rejection_stage: str | None = None,
        base: float | None = None,
        penalty_total: float | None = None,
        penalty_reasons: list[str] | None = None,
        use_confidence_as_model: bool = True,
        use_confidence_as_final_stage: bool = True,
        ml_model_raw_proba: float | None = None,
        ml_pre_quality_proba: float | None = None,
        ml_post_quality_proba: float | None = None,
        gating_confidence: float | None = None,
        sizing_confidence: float | None = None,
        ml_model_name: str | None = None,
        ml_model_version: str | None = None,
    ) -> dict:
        final_conf = self._clamp_confidence(confidence)
        model_raw_val = self._clamp_confidence(model_raw)
        model_component_val = self._clamp_confidence(model_component)
        if use_confidence_as_model and final_conf is not None:
            if model_raw_val is None:
                model_raw_val = final_conf
            if model_component_val is None:
                model_component_val = final_conf
            if micro_blend_method is None and micro_component is None:
                micro_blend_method = "model_only"
        before_soft_veto_val = self._clamp_confidence(before_soft_veto)
        after_soft_veto_val = self._clamp_confidence(after_soft_veto)
        if use_confidence_as_final_stage and final_conf is not None:
            if before_soft_veto_val is None:
                before_soft_veto_val = final_conf
            if after_soft_veto_val is None:
                after_soft_veto_val = final_conf
            if penalty_soft_veto_total is None:
                penalty_soft_veto_total = 0.0
        base_val = self._clamp_confidence(base)
        if base_val is None:
            base_val = final_conf
        penalty_total_val = self._clamp_confidence(penalty_total)
        if penalty_total_val is None:
            if base_val is not None and final_conf is not None:
                penalty_total_val = max(0.0, float(base_val) - float(final_conf))
            elif base_val is not None or final_conf is not None:
                penalty_total_val = 0.0
        if gate_threshold is None and final_gate_threshold is not None:
            gate_threshold = final_gate_threshold

        if ml_model_raw_proba is None:
            ml_model_raw_proba = model_raw_val
        if ml_pre_quality_proba is None:
            ml_pre_quality_proba = before_soft_veto_val
        if ml_post_quality_proba is None:
            ml_post_quality_proba = final_conf
        if gating_confidence is None:
            gating_confidence = after_soft_veto_val if after_soft_veto_val is not None else final_conf
        if sizing_confidence is None:
            sizing_confidence = final_conf

        def _round_optional(value: float | None) -> float | None:
            clamped = self._clamp_confidence(value)
            if clamped is None:
                return None
            return round(float(clamped), 6)

        penalty_soft_veto_total_val = None
        if penalty_soft_veto_total is not None:
            penalty_soft_veto_total_val = round(max(0.0, float(penalty_soft_veto_total)), 6)

        penalty_reasons_out = [str(reason) for reason in (penalty_reasons or []) if str(reason)]
        soft_veto_reasons_out = [str(reason) for reason in (penalty_soft_veto_reasons or []) if str(reason)]
        return {
            "builder_confidence": _round_optional(final_conf),
            "gating_base_confidence": _round_optional(base_val),
            "gating_final_confidence": _round_optional(after_soft_veto_val if after_soft_veto_val is not None else final_conf),
            "confidence_model_raw": _round_optional(model_raw_val),
            "confidence_model_component": _round_optional(model_component_val),
            "confidence_micro_component": _round_optional(micro_component),
            "confidence_micro_blend_method": micro_blend_method,
            "confidence_after_micro": _round_optional(after_micro),
            "confidence_after_alpha": _round_optional(after_alpha),
            "confidence_after_latency": _round_optional(after_latency),
            "confidence_before_soft_veto": _round_optional(before_soft_veto_val),
            "confidence_after_soft_veto": _round_optional(after_soft_veto_val),
            "confidence_penalty_soft_veto_total": penalty_soft_veto_total_val,
            "confidence_penalty_soft_veto_reasons": soft_veto_reasons_out,
            "confidence_gate_threshold": _round_optional(gate_threshold),
            "confidence_raw_gate_threshold": _round_optional(raw_gate_threshold),
            "confidence_final_gate_threshold": _round_optional(final_gate_threshold),
            "confidence_rejection_stage": rejection_stage,
            "confidence_base": _round_optional(base_val),
            "confidence_penalty_total": _round_optional(penalty_total_val),
            "confidence_penalty_reasons": penalty_reasons_out,
            "ml_model_raw_proba": _round_optional(ml_model_raw_proba),
            "ml_pre_quality_proba": _round_optional(ml_pre_quality_proba),
            "ml_post_quality_proba": _round_optional(ml_post_quality_proba),
            "gating_confidence": _round_optional(gating_confidence),
            "sizing_confidence": _round_optional(sizing_confidence),
            "ml_model_name": ml_model_name,
            "ml_model_version": ml_model_version,
        }

    def _strategy_candidate_debug(self, market_data, strategy_name: str) -> dict:
        if not isinstance(market_data, dict):
            return {}
        root = market_data.setdefault("strategy_debug", {})
        stats = root.setdefault(
            strategy_name,
            {
                "candidates_considered": 0,
                "candidates_rejected_pre_score": 0,
                "rejection_reason_counts": {},
                "candidates_scored": 0,
            },
        )
        return stats

    def _update_strategy_candidate_debug(
        self,
        stats: dict,
        *,
        considered: int = 0,
        rejected: int = 0,
        scored: int = 0,
        reason: str | None = None,
    ) -> None:
        if not isinstance(stats, dict):
            return
        stats["candidates_considered"] = int(stats.get("candidates_considered", 0)) + int(considered)
        stats["candidates_rejected_pre_score"] = int(
            stats.get("candidates_rejected_pre_score", 0)
        ) + int(rejected)
        stats["candidates_scored"] = int(stats.get("candidates_scored", 0)) + int(scored)
        if reason:
            counts = stats.setdefault("rejection_reason_counts", {})
            counts[str(reason)] = int(counts.get(str(reason), 0)) + 1

    def _zero_hero_diag(self, market_data: dict | None) -> dict:
        if not isinstance(market_data, dict):
            return {}
        diag = market_data.setdefault(
            "zero_hero_diagnostics",
            {
                "zero_hero_considered": 0,
                "zero_hero_rejected_reason": None,
                "zero_hero_selected_premium_band": None,
                "zero_hero_activation_window": None,
            },
        )
        return diag

    def _update_zero_hero_diag(
        self,
        market_data: dict | None,
        *,
        considered: int = 0,
        rejected_reason: str | None = None,
        selected_premium_band=None,
        activation_window=None,
        clear_rejected_reason: bool = False,
    ) -> None:
        diag = self._zero_hero_diag(market_data)
        if not diag:
            return
        diag["zero_hero_considered"] = int(diag.get("zero_hero_considered", 0)) + int(considered)
        if clear_rejected_reason:
            diag["zero_hero_rejected_reason"] = None
        elif rejected_reason:
            diag["zero_hero_rejected_reason"] = str(rejected_reason)
        if selected_premium_band is not None:
            diag["zero_hero_selected_premium_band"] = selected_premium_band
        if activation_window is not None:
            diag["zero_hero_activation_window"] = activation_window

    def build(self, market_data, quick_mode=False, debug_reasons=False, force_family: str | None = None, allow_fallbacks: bool = True, allow_baseline: bool = True):
        """
        Build a single best Trade candidate from market snapshot.
        Returns Trade or None.
        """
        self._reject_ctx = {}
        market_data = dict(market_data or {})
        debug_mode = getattr(cfg, "DEBUG_TRADE_MODE", False)
        if debug_mode:
            debug_reasons = True
        exec_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
        segment = market_data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        ctx_payload = dict(market_data.get("market_context") or {}) if isinstance(market_data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = exec_mode
        if "market_open" not in ctx_payload:
            ctx_payload["market_open"] = market_data.get("market_open", True)
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = segment
        market_ctx = derive_market_context(ctx_payload)
        market_open = bool(market_ctx.is_market_open)
        offhours_mode = bool(market_ctx.mode == "OFFHOURS")
        strict_live_market_open = bool(market_ctx.mode == "LIVE" and market_ctx.is_market_open)
        profile_mode = "LIVE" if market_ctx.mode == "LIVE" else ("PAPER" if market_ctx.mode == "PAPER" else "SIM")
        runtime_profile = get_runtime_profile(mode=profile_mode)
        filter_profile_main = get_option_filter_profile(
            mode=profile_mode,
            base_max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.03),
            base_min_volume_filter=getattr(cfg, "MIN_VOLUME_FILTER", 500),
        )
        filter_profile_quick = get_option_filter_profile(
            mode=profile_mode,
            base_max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT_QUICK", getattr(cfg, "MAX_SPREAD_PCT", 0.03)),
            base_min_volume_filter=getattr(cfg, "MIN_VOLUME_FILTER", 500),
        )
        self._scan_reject_counts = {}
        self._scan_total_candidates = 0
        self._scan_accepted = 0
        self._scan_profile_name = str(filter_profile_quick.name if quick_mode else filter_profile_main.name)
        self._last_option_scan_summary = {}
        self._option_scan_summary_emitted = True
        planning_mode = bool(market_ctx.planning_only)
        is_live_mode = bool(market_ctx.mode == "LIVE")
        paper_strict_mode = exec_mode == "PAPER" and bool(getattr(cfg, "PAPER_STRICT_MODE", False))
        planning_relaxed = planning_mode and not paper_strict_mode
        market_data["market_context"] = market_ctx.to_dict()
        market_data["market_open"] = bool(market_open)
        market_data["offhours_mode"] = bool(offhours_mode)
        market_data["runtime_profile"] = runtime_profile.to_dict()
        market_data["option_filter_profile"] = (
            filter_profile_quick.to_dict() if quick_mode else filter_profile_main.to_dict()
        )
        pre_soft_veto_codes: list[str] = []
        pre_execution_blockers: list[str] = []
        pre_warning_codes: list[str] = []
        advisory_flags: list[str] = []
        execution_block_type: str | None = None

        def _append_unique(items: list[str], code: str) -> None:
            text = str(code or "").strip()
            if text and text not in items:
                items.append(text)

        def _normalize_issue_code(code: str) -> str:
            text = str(code or "").strip()
            if text == "spread_ok":
                return "spread_pct"
            if text == "premium_band_fail":
                return "premium_out_of_band"
            return text

        def _discard_issue(items: list[str], code: str) -> None:
            text = str(code or "").strip()
            if not text:
                return
            while text in items:
                items.remove(text)

        def _issue_primary_role(code: str) -> str:
            normalized = _normalize_issue_code(code)
            role_map = {
                "stale_option_quote": ISSUE_CATEGORY_HARD,
                "option_quote_missing": ISSUE_CATEGORY_HARD,
                "option_quote_not_live": ISSUE_CATEGORY_HARD,
                "option_bidask_missing": ISSUE_CATEGORY_HARD,
                "missing_live_bidask": ISSUE_CATEGORY_HARD,
                "instrument_token_missing": ISSUE_CATEGORY_HARD,
                "premium_out_of_band": ISSUE_CATEGORY_SOFT,
                "option_depth_missing": ISSUE_CATEGORY_WARNING,
                "option_volume_missing": ISSUE_CATEGORY_WARNING,
                "low_volume": ISSUE_CATEGORY_WARNING,
                "spread_pct": ISSUE_CATEGORY_WARNING,
                "missing_index_bid_ask": ISSUE_CATEGORY_WARNING,
            }
            return role_map.get(normalized, ISSUE_CATEGORY_HARD)

        def _make_issue_recorder(
            soft_codes: list[str],
            hard_codes: list[str],
            warning_codes: list[str],
        ):
            issue_primary_roles: dict[str, str] = {}

            def _record_issue(code: str, role: str | None = None) -> str | None:
                normalized = _normalize_issue_code(code)
                if not normalized:
                    return None
                primary_role = str(role or _issue_primary_role(normalized))
                existing_role = issue_primary_roles.get(normalized)
                if existing_role == primary_role:
                    return normalized
                if existing_role == ISSUE_CATEGORY_HARD and primary_role != ISSUE_CATEGORY_HARD:
                    return normalized
                if primary_role == ISSUE_CATEGORY_HARD:
                    _discard_issue(soft_codes, normalized)
                    _discard_issue(warning_codes, normalized)
                elif primary_role == ISSUE_CATEGORY_SOFT:
                    _discard_issue(hard_codes, normalized)
                    _discard_issue(warning_codes, normalized)
                elif primary_role == ISSUE_CATEGORY_WARNING:
                    _discard_issue(soft_codes, normalized)
                    _discard_issue(hard_codes, normalized)
                issue_primary_roles[normalized] = primary_role
                if primary_role == ISSUE_CATEGORY_SOFT:
                    _append_unique(soft_codes, normalized)
                elif primary_role == ISSUE_CATEGORY_WARNING:
                    _append_unique(warning_codes, normalized)
                else:
                    _append_unique(hard_codes, normalized)
                return normalized

            return _record_issue

        _record_pre_issue = _make_issue_recorder(
            pre_soft_veto_codes,
            pre_execution_blockers,
            pre_warning_codes,
        )

        def _display_only_candidate_source(opt: dict) -> str | None:
            if not bool(getattr(cfg, "TRADE_BUILDER_ALLOW_DISPLAY_ONLY_OPTION_CANDIDATES", True)):
                return None
            if not isinstance(opt, dict):
                return None
            source = str(
                opt.get("option_ltp_source")
                or opt.get("quote_source")
                or ""
            ).strip().lower()
            if not source or source in {"none", "synthetic_index"}:
                return None
            for field in ("mark_price", "mid_price", "ltp", "last_price"):
                if self._coerce_positive_float(opt.get(field)) is not None:
                    return source
            return None

        # Hard disable quick/baseline paths in LIVE mode
        if exec_mode == "LIVE":
            if quick_mode:
                self._log_blocked_candidate(
                    market_data.get("symbol", "UNKNOWN"),
                    "quick_mode_live_blocked",
                    "Quick mode is disabled in LIVE mode",
                    market_data=market_data,
                    extra={"execution_mode": exec_mode},
                )
                return self._reject_exit(
                    market_data,
                    "quick_mode_live_blocked",
                    extra={"execution_mode": exec_mode},
                )
            allow_fallbacks = False
            allow_baseline = False
        # Paper strict mode: disable baseline and relax reasons
        if paper_strict_mode:
            allow_baseline = False
            allow_fallbacks = False
        symbol = market_data["symbol"]
        market_data = self._resolve_index_bid_ask(market_data, exec_mode)
        if market_data.get("valid") is False:
            invalid_reason = market_data.get("invalid_reason") or "invalid_snapshot"
            self._reject_exit(
                market_data,
                invalid_reason,
                extra={"symbol": symbol},
            )
            self._log_blocked_candidate(
                symbol,
                "invalid_snapshot",
                str(invalid_reason),
                market_data=market_data,
            )
            if debug_reasons:
                _log_advisory_debug("trade_builder_reject symbol=%s reason=%s", symbol, invalid_reason)
            return None
        ltp = market_data.get("ltp", 0)
        vwap = market_data.get("vwap", ltp)
        bias = market_data.get("bias", "Bullish")
        instrument = market_data.get("instrument", "OPT")
        underlying_spot, spot_source, spot_ok, spot_issue = self._resolve_underlying_spot(market_data, market_ctx)
        market_data["underlying_spot"] = underlying_spot
        market_data["spot_source"] = spot_source
        if (
            market_data.get("quote_ok") is False
            or market_data.get("bid") is None
            or market_data.get("ask") is None
        ):
            ltp = market_data.get("ltp")
            ltp_source = market_data.get("ltp_source")
            has_depth = bool(
                market_data.get("depth") is not None
                or market_data.get("depth_age_sec") is not None
            )
            has_quote = bool(
                market_data.get("quote_ok") is True
                and market_data.get("bid") is not None
                and market_data.get("ask") is not None
            )
            ws_subscribed = market_data.get("ws_subscribed")
            if ws_subscribed is None:
                ws_subscribed = bool(
                    str(market_data.get("ltp_source") or "").lower() == "live"
                    or str(market_data.get("chain_source") or "").lower() == "live"
                )
            reject_reason = "missing_live_bidask" if exec_mode == "LIVE" else "missing_index_bid_ask"
            gate_reasons = ["missing_live_bidask", "quote_api_issue"] if exec_mode == "LIVE" else [reject_reason]
            reject_payload = {
                "mode": exec_mode,
                "offhours_mode": bool(offhours_mode),
                "ltp": ltp,
                "ltp_source": ltp_source,
                "has_depth": has_depth,
                "has_quote": has_quote,
                "ws_subscribed": ws_subscribed,
                "gate_reasons": list(gate_reasons),
            }
            hard_block_missing_index_quote = bool(
                runtime_profile.suggestion_require_live_quotes and (not market_ctx.allow_stale_quotes)
            )
            if not hard_block_missing_index_quote:
                _record_pre_issue(
                    reject_reason,
                    role=ISSUE_CATEGORY_HARD if exec_mode == "LIVE" else ISSUE_CATEGORY_WARNING,
                )
                _log_signal_event("trade_offhours_missing_bidask", symbol, reject_payload)
                if debug_reasons:
                    if exec_mode == "LIVE":
                        print(
                            f"SOFT_VETO: missing_live_bidask symbol={symbol} candidate_generation_continues=true"
                        )
                    _log_freshness_debug(
                        "SOFT_VETO trade_builder_soft_veto_missing_bidask symbol=%s candidate_generation_continues=true",
                        symbol,
                    )
                if ltp is not None and float(ltp or 0.0) > 0:
                    synth_spread = max(float(ltp) * float(getattr(cfg, "SYNTH_INDEX_SPREAD_PCT", 0.0002)), 0.05)
                    market_data["bid"] = round(float(ltp) - (synth_spread / 2.0), 4)
                    market_data["ask"] = round(float(ltp) + (synth_spread / 2.0), 4)
                    market_data["quote_ok"] = True
                    market_data["index_bidask_synthetic"] = True
                    market_data["index_quote_source"] = "synthetic_index"
                    market_data["quote_source"] = "synthetic_index"
            else:
                self._reject_exit(
                    market_data,
                    reject_reason,
                    extra={"symbol": symbol, **reject_payload},
                )
                _log_signal_event(f"trade_reject_{reject_reason}", symbol, reject_payload)
                self._log_blocked_candidate(
                    symbol,
                    reject_reason,
                    "Missing index bid/ask quote",
                    market_data=market_data,
                    extra=reject_payload,
                )
                if debug_reasons:
                    _log_advisory_debug(
                        "trade_builder_reject_missing_bidask symbol=%s reason=%s ltp=%s ltp_source=%s has_depth=%s has_quote=%s ws_subscribed=%s gate_reasons=%s",
                        symbol,
                        reject_reason,
                        ltp,
                        ltp_source,
                        has_depth,
                        has_quote,
                        ws_subscribed,
                        gate_reasons,
                    )
                return None

        try:
            ltp = float(ltp) if ltp is not None else 0.0
        except Exception:
            ltp = 0.0

        signal = self._signal_for_symbol(market_data, force_family=force_family)
        relax_reason = "" if exec_mode == "LIVE" else (getattr(cfg, "RELAX_BLOCK_REASON", "") or "")
        if exec_mode == "PAPER" and getattr(cfg, "PAPER_STRICT_MODE", False):
            relax_reason = ""
        def _relax(reason: str) -> bool:
            if (
                exec_mode == "LIVE"
                and reason in {"iv_term", "iv_surface_slope"}
                and bool(getattr(cfg, "LIVE_RELAX_IV_STRUCTURE_GATES_ENABLE", True))
            ):
                return True
            if exec_mode in {"SIM", "PAPER"} and reason in {"spread_pct", "low_volume", "low_oi", "delta"}:
                return True
            return bool(relax_reason) and reason == relax_reason
        planning_quick_fallback = planning_relaxed and bool(getattr(cfg, "PLANNING_QUICK_FALLBACK_ENABLE", True))
        if not signal and (quick_mode or planning_quick_fallback) and allow_fallbacks:
            # quick fallback signal based on simple bias / short-term move
            bias = market_data.get("bias", "NEUTRAL")
            ltp_change = market_data.get("ltp_change", 0)
            if bias in ("Bullish", "BULLISH") or ltp_change > 0:
                signal = {"direction": "BUY_CALL", "reason": "Quick bias fallback", "score": 0.55}
            elif bias in ("Bearish", "BEARISH") or ltp_change < 0:
                signal = {"direction": "BUY_PUT", "reason": "Quick bias fallback", "score": 0.55}
            else:
                try:
                    signal = self._quick_neutral_fallback_signal(market_data, float(ltp or 0), float(vwap or 0))
                except Exception:
                    signal = None
        if not signal and planning_relaxed:
            try:
                signal = self._planning_signal_fallback_signal(market_data, float(ltp or 0), float(vwap or 0))
            except Exception:
                signal = None
        if not signal and allow_baseline and getattr(cfg, "ALLOW_BASELINE_SIGNAL", True):
            try:
                atr = market_data.get("atr", max(1.0, ltp * 0.002))
                ltp_change = market_data.get("ltp_change", 0) or 0
                ltp_change_window = market_data.get("ltp_change_window", 0) or 0
                thresh = atr * getattr(cfg, "BASELINE_LTP_ATR_MULT", 0.05)
                thresh_w = atr * getattr(cfg, "BASELINE_LTP_ATR_MULT_WINDOW", 0.02)
                if abs(ltp_change) >= thresh and atr > 0:
                    direction = "BUY_CALL" if ltp_change > 0 else "BUY_PUT"
                    signal = {
                        "direction": direction,
                        "reason": "Baseline LTP momentum",
                        "score": getattr(cfg, "BASELINE_SIGNAL_SCORE", 0.62),
                    }
                elif abs(ltp_change_window) >= thresh_w and atr > 0:
                    direction = "BUY_CALL" if ltp_change_window > 0 else "BUY_PUT"
                    signal = {
                        "direction": direction,
                        "reason": "Baseline LTP window momentum",
                        "score": getattr(cfg, "BASELINE_SIGNAL_SCORE", 0.62),
                    }
            except Exception:
                pass
        if (
            not signal
            and exec_mode in {"SIM", "PAPER"}
            and allow_fallbacks
            and bool(getattr(cfg, "NO_SIGNAL_FALLBACK_ENABLE", True))
        ):
            try:
                signal = self._quick_neutral_fallback_signal(market_data, float(ltp or 0.0), float(vwap or 0.0))
            except Exception:
                signal = None
            if not signal:
                bias = str(market_data.get("bias") or "").strip().upper()
                ltp_change = float(market_data.get("ltp_change") or 0.0)
                direction = None
                if bias in {"BULLISH", "UP"} or ltp_change > 0:
                    direction = "BUY_CALL"
                elif bias in {"BEARISH", "DOWN"} or ltp_change < 0:
                    direction = "BUY_PUT"
                if direction:
                    signal = {
                        "direction": direction,
                        "reason": "No-signal bias fallback",
                        "score": float(getattr(cfg, "NO_SIGNAL_FALLBACK_SCORE", 0.45)),
                    }
            if signal and bool(getattr(cfg, "TRADE_BUILDER_RESULT_TRACE_ENABLE", True)):
                logger.info(
                    "NO_SIGNAL_FALLBACK_SIGNAL symbol=%s direction=%s score=%s reason=%s",
                    symbol,
                    signal.get("direction"),
                    signal.get("score"),
                    signal.get("reason"),
                )
        if (
            not signal
            and exec_mode == "LIVE"
            and bool(getattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", True))
        ):
            live_signal = None
            try:
                live_signal = self._quick_neutral_fallback_signal(
                    market_data,
                    float(ltp or 0.0),
                    float(vwap or 0.0),
                )
            except Exception:
                live_signal = None
            if not live_signal:
                try:
                    live_signal = self._planning_signal_fallback_signal(
                        market_data,
                        float(ltp or 0.0),
                        float(vwap or 0.0),
                    )
                except Exception:
                    live_signal = None
            if not live_signal and bool(market_data.get("market_open", True)):
                bias = str(market_data.get("bias") or "").strip().upper()
                ltp_change = float(market_data.get("ltp_change") or 0.0)
                direction = None
                if bias in {"BULLISH", "UP"} or ltp_change > 0:
                    direction = "BUY_CALL"
                elif bias in {"BEARISH", "DOWN"} or ltp_change < 0:
                    direction = "BUY_PUT"
                if direction:
                    live_signal = {
                        "direction": direction,
                        "reason": "Live no-signal bias fallback",
                        "score": float(getattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_SCORE_MIN", 0.58)),
                    }
            min_live_score = float(getattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_SCORE_MIN", 0.58))
            if live_signal and float(live_signal.get("score") or 0.0) >= min_live_score:
                live_signal["reason"] = "Live structured no-signal fallback"
                signal = live_signal
                if bool(getattr(cfg, "TRADE_BUILDER_RESULT_TRACE_ENABLE", True)):
                    logger.info(
                        "LIVE_NO_SIGNAL_FALLBACK_SIGNAL symbol=%s direction=%s score=%s reason=%s",
                        symbol,
                        signal.get("direction"),
                        signal.get("score"),
                        signal.get("reason"),
                    )
        if not signal:
            fallback_allowed = bool(market_data.get("allow_planning_no_signal_fallback"))
            if exec_mode == "LIVE":
                fallback_allowed = False
            reject_reason = "no_signal"
            if fallback_allowed and bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)):
                logger.info(
                    "planning_no_signal_fallback_check symbol=%s planning_relaxed=%s allow_planning_no_signal_fallback=%s planning_no_signal_fallback_enable=%s",
                    symbol,
                    bool(planning_relaxed),
                    fallback_allowed,
                    bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)),
                )
            elif planning_relaxed and bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)):
                reject_reason = "no_signal_planning_fallback_disabled"
            self._reject_ctx = {"symbol": symbol, "reason": reject_reason}
            self._log_blocked_candidate(
                symbol,
                reject_reason,
                "No strategy signal generated for current snapshot",
                market_data=market_data,
                extra={
                    "soft_veto": bool(planning_relaxed),
                    "allow_planning_no_signal_fallback": fallback_allowed,
                    "planning_no_signal_fallback_enable": bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)),
                },
            )
            if not allow_fallbacks:
                return None
            if fallback_allowed and exec_mode in {"SIM", "PAPER", "OFFHOURS"}:
                opportunity_trade = self._rank_nonlive_opportunity_candidates(
                    market_data,
                    ltp=float(ltp or 0.0),
                    vwap=float(vwap or ltp or 0.0),
                    trigger_reason="no_signal",
                    scope_suffix="opportunity:no_signal",
                )
                logger.info(
                    "planning_no_signal_opportunity_result symbol=%s planning_relaxed=%s allow_planning_no_signal_fallback=%s returned_trade=%s candidate_count=%s",
                    symbol,
                    bool(planning_relaxed),
                    fallback_allowed,
                    bool(opportunity_trade is not None),
                    len(list(getattr(self, "_last_ranked_candidates", []) or [])),
                )
                if opportunity_trade is not None:
                    self._reject_ctx = {}
                    return opportunity_trade
            if debug_reasons:
                _log_advisory_debug(
                    "trade_builder_no_signal symbol=%s ltp=%s vwap=%s atr=%s ltp_change=%s ltp_change_window=%s",
                    symbol,
                    ltp,
                    vwap,
                    market_data.get("atr"),
                    market_data.get("ltp_change"),
                    market_data.get("ltp_change_window"),
                )
            if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
                return None
            if exec_mode == "LIVE" and not bool(
                getattr(cfg, "LIVE_ALLOW_WEAK_SIGNAL_BORDERLINE_CANDIDATE", False)
            ):
                return None
            raw_confidence = (
                self._coerce_positive_float(market_data.get("confidence_raw"))
                or self._coerce_positive_float(market_data.get("confidence"))
                or self._coerce_positive_float(market_data.get("gating_base_confidence"))
                or 0.0
            )
            borderline_candidate = self._build_borderline_candidate(
                market_data=market_data,
                reason="weak_signal",
                confidence=max(float(raw_confidence), float(self._borderline_confidence_floor())),
                strategy_tag=("QUICK_OPT" if quick_mode else "ENSEMBLE_OPT"),
                direction=None,
            )
            if borderline_candidate is not None:
                self._reject_ctx = {}
                if borderline_candidate.get("rank_score") is not None:
                    self._set_last_ranked_candidates([borderline_candidate])
                else:
                    self._set_last_ranked_candidates([])
                self._scan_accepted = 1
                if borderline_candidate.get("rank_score") is not None:
                    logger.info(
                        "candidate_pool_append source=weak_signal_borderline symbol=%s reason=%s",
                        symbol,
                        "weak_signal",
                    )
                else:
                    logger.info(
                        "candidate_pool_skip source=weak_signal_borderline symbol=%s reason=%s rank_score=none",
                        symbol,
                        "weak_signal",
                    )
                return borderline_candidate
            return None
        setup_family = self._candidate_setup_family(signal, force_family=force_family)
        strategy_tag = signal.get("strategy") if signal and signal.get("strategy") else ("QUICK_OPT" if quick_mode else "ENSEMBLE_OPT")
        if signal.get("reason") == "trend_vwap_fallback":
            strategy_tag = "TREND_VWAP_FALLBACK"
        allowed_life, _ = self._apply_lifecycle_gate(strategy_tag, mode="MAIN" if not quick_mode else "QUICK")
        if not allowed_life:
            self._log_blocked_candidate(
                symbol,
                "lifecycle_gate_fail",
                "Strategy lifecycle gate rejected candidate",
                market_data=market_data,
                extra={"strategy": strategy_tag},
            )
            if debug_reasons:
                _log_advisory_debug("trade_builder_lifecycle_gate_reject symbol=%s strategy=%s", symbol, strategy_tag)
            return self._reject_exit(market_data, "lifecycle_gate_fail")
        decay_size_mult = 1.0
        allowed, adj_score, decay_size_mult, _decay_reason = self._apply_decay_gate(strategy_tag, signal.get("score"), decay_size_mult)
        if not allowed:
            self._log_blocked_candidate(
                symbol,
                "strategy_quarantined",
                "Strategy decay gate quarantined strategy",
                market_data=market_data,
                extra={"strategy": strategy_tag},
            )
            if debug_reasons:
                _log_advisory_debug("trade_builder_strategy_quarantine symbol=%s strategy=%s", symbol, strategy_tag)
            return self._reject_exit(market_data, "strategy_quarantined")
        if adj_score is not None:
            signal["score"] = adj_score
        min_score = getattr(cfg, "STRICT_STRATEGY_SCORE", 0.7)
        regime_day = signal.get("regime_day") or market_data.get("regime_day") or market_data.get("regime") or "NEUTRAL"
        score_mult = getattr(cfg, "REGIME_SCORE_MULT", {}).get(regime_day, 1.0)
        min_score = min_score * score_mult
        if quick_mode:
            min_score = min(min_score, 0.5)
        if planning_relaxed:
            min_score = min(min_score, float(getattr(cfg, "PLANNING_SIGNAL_SCORE_MIN", 0.5)))
        if debug_reasons:
            _log_advisory_debug(
                "signal_path symbol=%s regime=%s direction=%s score=%.3f reason=%s",
                symbol,
                signal.get("regime_day"),
                signal.get("direction"),
                float(signal.get("score") or 0.0),
                signal.get("reason"),
            )
            _log_signal_event(
                "signal",
                symbol,
                {
                    "regime": regime_day,
                    "direction": signal.get("direction"),
                    "score": signal.get("score"),
                    "reason": signal.get("reason"),
                    "quick_mode": bool(quick_mode),
                },
            )
        if signal.get("score", 0) < min_score:
            self._log_blocked_candidate(
                symbol,
                "signal_score_below_min",
                f"Signal score {signal.get('score', 0)} below minimum {min_score}",
                market_data=market_data,
                extra={"min_score": min_score, "signal_score": signal.get("score", 0)},
            )
            if debug_reasons:
                _log_advisory_debug(
                    "trade_builder_signal_score_below_min symbol=%s signal_score=%s min_score=%s",
                    symbol,
                    signal.get("score", 0),
                    min_score,
                )
                _log_signal_event(
                    "signal_reject",
                    symbol,
                    {
                        "regime": regime_day,
                        "direction": signal.get("direction"),
                        "score": signal.get("score"),
                        "reason": f"score_below_min {min_score}",
                        "quick_mode": bool(quick_mode),
                    },
                )
            hard_reject_signal_score = bool(
                getattr(cfg, "TRADE_BUILDER_SIGNAL_SCORE_BELOW_MIN_HARD_REJECT", False)
            )
            if hard_reject_signal_score:
                return self._reject_exit(market_data, "signal_score_below_min")
            # Treat low signal score as soft weakness so phase2/decision layers can queue-rank it.
            _append_unique(pre_soft_veto_codes, "signal_score_below_min")
            signal["reason"] = str(signal.get("reason") or "weak_signal")
            signal["signal_strength"] = "weak"
            signal["signal_score_below_min"] = True

        direction = signal["direction"]
        orb_soft_veto_codes: list[str] = []
        # Require live option chain by default (no synthetic trades)
        try:
            if strict_live_market_open and market_data.get("chain_source") != "live":
                self._log_blocked_candidate(
                    symbol,
                    "non_live_option_chain",
                    "Option chain source is not live",
                    market_data=market_data,
                    extra={"chain_source": market_data.get("chain_source")},
                )
                if debug_reasons:
                    _log_option_chain_debug("trade_builder_non_live_option_chain symbol=%s", symbol)
                return self._reject_exit(market_data, "non_live_option_chain")
        except Exception:
            pass
        # reject context for debug reports
        try:
            self._reject_ctx = {
                "strategy": strategy_tag,
                "regime": market_data.get("regime"),
                "day_type": market_data.get("day_type"),
                "direction": direction,
            }
        except Exception:
            self._reject_ctx = {}
        # Direction sanity check: block PE if price above VWAP and HTF trend is up
        if direction == "BUY_PUT":
            try:
                ltp = market_data.get("ltp", 0)
                vwap = market_data.get("vwap", ltp)
                htf_dir = market_data.get("htf_dir", "FLAT")
                if ltp >= vwap and htf_dir == "UP":
                    self._log_blocked_candidate(
                        symbol,
                        "direction_sanity_block",
                        "Direction sanity rejected BUY_PUT while HTF trend is UP",
                        market_data=market_data,
                        extra={"direction": direction, "htf_dir": htf_dir},
                    )
                    if debug_reasons:
                        _log_advisory_debug("trade_builder_direction_sanity_block symbol=%s", symbol)
                    return self._reject_exit(market_data, "direction_sanity_block")
            except Exception:
                pass
        # ORB bias guardrail: default soft-veto, optional LIVE hard veto.
        try:
            if getattr(cfg, "ORB_BIAS_LOCK", True):
                orb_bias = str(market_data.get("orb_bias", "NEUTRAL") or "NEUTRAL").upper()
                hard_block_live = bool(strict_live_market_open and getattr(cfg, "ORB_HARD_BLOCK_LIVE", False))
                hard_conflict_live = bool(strict_live_market_open and getattr(cfg, "ORB_HARD_CONFLICT_LIVE", False))
                if orb_bias == "PENDING":
                    if hard_block_live:
                        self._log_blocked_candidate(
                            symbol,
                            "orb_pending",
                            "ORB bias is still pending",
                            market_data=market_data,
                            extra={"orb_bias": orb_bias, "direction": direction},
                        )
                        return self._reject_exit(market_data, "orb_pending")
                    orb_soft_veto_codes.append("orb_pending")
                if orb_bias == "UP" and direction == "BUY_PUT":
                    if hard_conflict_live:
                        self._log_blocked_candidate(
                            symbol,
                            "orb_bias_conflict",
                            "ORB bias UP conflicts with BUY_PUT",
                            market_data=market_data,
                            extra={"orb_bias": orb_bias, "direction": direction},
                        )
                        return self._reject_exit(market_data, "orb_bias_conflict")
                    orb_soft_veto_codes.append("orb_bias_conflict")
                if orb_bias == "DOWN" and direction == "BUY_CALL":
                    if hard_conflict_live:
                        self._log_blocked_candidate(
                            symbol,
                            "orb_bias_conflict",
                            "ORB bias DOWN conflicts with BUY_CALL",
                            market_data=market_data,
                            extra={"orb_bias": orb_bias, "direction": direction},
                        )
                        return self._reject_exit(market_data, "orb_bias_conflict")
                    orb_soft_veto_codes.append("orb_bias_conflict")
                orb_neutral_allow = bool(getattr(cfg, "ORB_NEUTRAL_ALLOW", True))
                if planning_relaxed and bool(getattr(cfg, "PLANNING_ORB_NEUTRAL_ALLOW", True)):
                    orb_neutral_allow = True
                if orb_bias == "NEUTRAL" and not orb_neutral_allow:
                    if hard_block_live:
                        self._log_blocked_candidate(
                            symbol,
                            "orb_neutral_blocked",
                            "ORB neutral trades are disabled",
                            market_data=market_data,
                            extra={
                                "orb_bias": orb_bias,
                                "direction": direction,
                            },
                        )
                        return self._reject_exit(market_data, "orb_neutral_blocked")
                    orb_soft_veto_codes.append("orb_neutral_blocked")
        except Exception:
            pass
        # Higher timeframe alignment
        if getattr(cfg, "HTF_ALIGN_REQUIRED", True) and not quick_mode:
            htf_dir = market_data.get("htf_dir", "FLAT")
            if direction == "BUY_CALL" and htf_dir == "DOWN":
                self._log_blocked_candidate(
                    symbol,
                    "htf_alignment_fail",
                    "HTF alignment rejected BUY_CALL while HTF trend is DOWN",
                    market_data=market_data,
                    extra={"direction": direction, "htf_dir": htf_dir},
                )
                return self._reject_exit(market_data, "htf_alignment_fail")
            if direction == "BUY_PUT" and htf_dir == "UP":
                self._log_blocked_candidate(
                    symbol,
                    "htf_alignment_fail",
                    "HTF alignment rejected BUY_PUT while HTF trend is UP",
                    market_data=market_data,
                    extra={"direction": direction, "htf_dir": htf_dir},
                )
                return self._reject_exit(market_data, "htf_alignment_fail")
        opt_type = "CE" if direction == "BUY_CALL" else "PE"
        candidates = []
        candidate_seen_keys: set[tuple] = set()
        debug_candidates = []
        rejected = []
        candidate_strategy_tag = strategy_tag
        option_reject_counts: dict[str, int] = {}
        option_rows_considered = 0
        premium_band_fail_count = 0
        premium_band_fail_samples: list[dict] = []
        premium_band_sample_limit = 3
        emit_premium_candidate_logs = bool(debug_reasons)

        def _count_option_reject(reason_code: str | None) -> None:
            code = str(reason_code or "").strip()
            if not code:
                return
            option_reject_counts[code] = int(option_reject_counts.get(code, 0)) + 1
            self._scan_reject_counts[code] = int(self._scan_reject_counts.get(code, 0)) + 1

        def _record_premium_band_failure(
            opt: dict,
            *,
            min_p: float,
            max_p: float,
            spread_pct: float | None,
            hard_veto: bool,
            count_scan: bool,
        ) -> None:
            nonlocal premium_band_fail_count
            premium_band_fail_count += 1
            if count_scan:
                self._scan_reject_counts["premium_band_fail"] = int(
                    self._scan_reject_counts.get("premium_band_fail", 0)
                ) + 1
            if len(premium_band_fail_samples) >= premium_band_sample_limit:
                return
            sample = {
                "strike": opt.get("strike"),
                "option_type": opt.get("type") or opt.get("option_type"),
                "ltp": opt.get("ltp"),
                "premium_min": round(float(min_p), 4),
                "premium_max": round(float(max_p), 4),
                "hard_veto": bool(hard_veto),
            }
            try:
                sample["spread_pct"] = round(float(spread_pct), 6) if spread_pct is not None else None
            except Exception:
                sample["spread_pct"] = None
            tradingsymbol = opt.get("tradingsymbol")
            if tradingsymbol:
                sample["tradingsymbol"] = tradingsymbol
            premium_band_fail_samples.append(sample)

        def _option_reject_summary() -> dict:
            if not option_reject_counts:
                return {}
            ordered = sorted(
                option_reject_counts.items(),
                key=lambda item: (-int(item[1]), str(item[0])),
            )
            top = ordered[:5]
            top_reasons = [str(code) for code, _count in top]
            hard_top_reasons = [code for code in top_reasons if self._is_scan_reason_hard_gate(code)]
            summary = {
                "top_option_reject_reasons": top_reasons,
                "hard_gate_reasons": list(hard_top_reasons),
                "option_reject_reason_counts": {str(code): int(count) for code, count in top},
                "hard_top_rejects": {
                    str(code): int(count)
                    for code, count in top
                    if self._is_scan_reason_hard_gate(code)
                },
                "option_reject_total": int(sum(option_reject_counts.values())),
            }
            self._reject_ctx = {
                "symbol": symbol,
                "reason": "no_viable_candidates",
                "gate_reasons": list(hard_top_reasons),
                **summary,
            }
            mode = (
                (market_data.get("market_context") or {}).get("mode")
                if isinstance(market_data.get("market_context"), dict)
                else exec_mode
            )
            append_reject_reasons(
                symbol=symbol,
                strategy=candidate_strategy_tag,
                reasons=hard_top_reasons,
                mode=mode,
                source="trade_builder_option_scan",
                extra=dict(summary),
            )
            return summary

        seq_buffer = market_data.get("seq_buffer")
        atr = market_data.get("atr", max(1.0, ltp * 0.002))
        chain_rows = self._annotate_candidate_chain_rows(symbol, market_data, underlying_spot)
        premium_band_cache = self._dynamic_premium_bands(symbol, chain_rows)
        for raw_opt in chain_rows:
            option_rows_considered += 1
            opt, opt_row_error = self._normalize_option_row(raw_opt, opt_type)
            if opt is None:
                _count_option_reject(opt_row_error)
                if debug_reasons and opt_row_error not in {"type_mismatch"}:
                    rejected.append(self._reject_record(symbol, {}, opt_type, opt_row_error, atr=atr))
                continue

            # Dynamic Strike Selection: Force ITM on Expiry Range Days
            try:
                sig_day_type = signal.get("day_type", "UNKNOWN") if isinstance(signal, dict) else getattr(signal, "day_type", "UNKNOWN")
                if regime_day in ("RANGE", "RANGE_VOLATILE") and sig_day_type == "EXPIRY_DAY":
                    mny = float(opt.get("moneyness", 0.0))
                    # For CE, ITM means spot > strike (mny > 0)
                    # For PE, ITM means strike > spot (mny < 0)
                    is_itm = (opt_type == "CE" and mny > 0.0) or (opt_type == "PE" and mny < 0.0)
                    if not is_itm:
                        _count_option_reject("range_expiry_requires_itm")
                        if debug_reasons:
                            rejected.append(self._reject_record(symbol, opt, opt_type, "range_expiry_requires_itm", atr=atr))
                        continue
            except Exception:
                pass
            display_only_candidate_source = _display_only_candidate_source(opt)
            allow_display_only_candidate = bool(display_only_candidate_source)
            allow_missing_bid_ask = bool(
                exec_mode == "PAPER"
                and not bool(getattr(cfg, "PAPER_STRICT_MODE", False))
            )
            if allow_display_only_candidate:
                allow_missing_bid_ask = True
            has_required_quote, quote_reason = self._validate_required_option_quote_fields(
                opt,
                allow_missing_bid_ask=allow_missing_bid_ask,
            )
            if not has_required_quote:
                _count_option_reject(quote_reason)
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, quote_reason, atr=atr))
                continue
            self._scan_total_candidates += 1
            current_filter_profile = filter_profile_quick if quick_mode else filter_profile_main
            soft_veto_codes = list(orb_soft_veto_codes) + list(pre_soft_veto_codes)
            execution_blockers = list(pre_execution_blockers)
            warning_codes = list(pre_warning_codes)
            _record_issue = _make_issue_recorder(
                soft_veto_codes,
                execution_blockers,
                warning_codes,
            )
            dirty_option_bridge_reasons = {"no_quote", "spread_pct", "iv_term", "iv_surface_slope"}
            dirty_option_bridge_seen: set[tuple[str, str, str]] = set()

            def _preserve_dirty_option_candidate(reason: str) -> None:
                if exec_mode == "LIVE":
                    return
                if reason not in dirty_option_bridge_reasons:
                    return
                dirty_key = (
                    reason,
                    str(opt.get("tradingsymbol") or ""),
                    str(opt.get("instrument_token") or ""),
                )
                if dirty_key in dirty_option_bridge_seen:
                    return
                dirty_option_bridge_seen.add(dirty_key)
                base_candidate = {
                    "symbol": symbol,
                    "strategy": strategy_tag,
                    "strategy_name": strategy_tag,
                    "strategy_family": strategy_tag,
                    "candidate_type": "directional",
                    "direction": direction,
                    "instrument": "OPT",
                    "instrument_type": "OPT",
                    "option_type": opt_type,
                    "right": opt_type,
                    "strike": opt.get("strike"),
                    "expiry": opt.get("expiry") or opt.get("expiry_date"),
                    "expiry_date": opt.get("expiry_date") or opt.get("expiry"),
                    "tradingsymbol": opt.get("tradingsymbol"),
                    "instrument_token": opt.get("instrument_token"),
                    "quote_source": opt.get("quote_source") or opt.get("option_ltp_source") or opt.get("chain_source"),
                    "option_ltp_source": opt.get("option_ltp_source") or opt.get("quote_source") or opt.get("chain_source"),
                    "quote_ok": bool(opt.get("quote_ok", True)),
                    "quote_age_sec": opt.get("quote_age_sec"),
                    "bid": opt.get("bid"),
                    "ask": opt.get("ask"),
                    "ltp": opt.get("ltp"),
                    "spread_pct": opt.get("spread_pct"),
                    "iv_term": opt.get("iv_term"),
                    "iv_surface_slope": opt.get("iv_surface_slope"),
                    "dirty_option_reason": reason,
                    "primary_blocker": reason,
                    "tradable_reasons_blocking": [reason],
                    "blockers": [reason],
                    "hard_blockers": [reason],
                    "source_flags": {
                        "candidate_origin": "dirty_option_bridge",
                        "dirty_option_reason": reason,
                    },
                }
                dirty_candidate = build_soft_reject_candidate(
                    market_data,
                    reject_reason=reason,
                    reject_source="trade_builder_dirty_option_bridge",
                    gate_reasons=[reason],
                    base_candidate=base_candidate,
                    execution_mode=exec_mode,
                )
                if not dirty_candidate:
                    return
                dirty_candidate["candidate_origin"] = "dirty_option_bridge"
                dirty_source_flags = dict(dirty_candidate.get("source_flags") or {})
                dirty_source_flags["candidate_origin"] = "dirty_option_bridge"
                dirty_source_flags["dirty_option_reason"] = reason
                dirty_source_flags["dirty_option_bridge"] = True
                dirty_source_flags["option_chain_source"] = opt.get("quote_source") or opt.get("option_ltp_source") or opt.get("chain_source")
                dirty_candidate["source_flags"] = dirty_source_flags
                dirty_candidate["dirty_option_reason"] = reason
                dirty_candidate["primary_blocker"] = reason
                dirty_candidate["tradable_reasons_blocking"] = [reason]
                dirty_candidate["blockers"] = [reason]
                dirty_candidate["hard_blockers"] = [reason]
                dirty_candidate["gate_reasons"] = [reason]
                dirty_candidate["tradable"] = False
                dirty_candidate["execution_allowed"] = False
                dirty_candidate["execution_ok"] = False
                dirty_candidate["execution_blocked"] = True
                dirty_candidate["eligible_for_execution"] = False
                dirty_candidate["permission"] = "ADVISORY_ONLY"
                dirty_candidate["final_action"] = "ADVISORY_ONLY"
                dirty_candidate["readiness"] = "ADVISORY_ONLY"
                dirty_candidate["candidate_status"] = "advisory_only"
                dirty_candidate["execution_status"] = "advisory_only"
                dirty_candidate["execution_block_reason"] = reason
                dirty_candidate["row_kind"] = "advisory_only"
                candidates.append(dirty_candidate)

            non_live_relaxed_gate_codes: list[str] = []

            def _mark_dirty_option_blocker(reason: str) -> None:
                if exec_mode == "LIVE":
                    return
                if reason not in dirty_option_bridge_reasons:
                    return
                _preserve_dirty_option_candidate(reason)
                if reason not in execution_blockers:
                    execution_blockers.append(reason)
                _append_unique(non_live_relaxed_gate_codes, reason)

            if bool(opt.get("type_mismatch_soft")):
                _record_issue("type_mismatch", role=ISSUE_CATEGORY_SOFT)
                _append_unique(non_live_relaxed_gate_codes, "type_mismatch")
            require_depth_quotes = bool(getattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", False))
            require_volume = bool(getattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", False))
            if exec_mode == "LIVE":
                # LIVE suggestion flow should honor profile-level volume strictness. Execution-stage guards remain strict.
                require_volume = bool(require_volume and runtime_profile.suggestion_require_volume)
            if exec_mode in {"SIM", "PAPER"} and bool(getattr(cfg, "RELAX_VOLUME_REQUIREMENTS_NONLIVE", True)):
                require_volume = False
            premium_soft_veto = False
            premium_soft_penalty_conf = float(getattr(cfg, "PREMIUM_SOFT_VETO_CONF_MULT", 0.92))
            premium_soft_penalty_size = float(getattr(cfg, "PREMIUM_SOFT_VETO_SIZE_MULT", 0.90))
            premium_outside_ratio = 0.0
            expiry_key = self._option_expiry(opt, market_data)
            band_key_used = expiry_key if expiry_key in premium_band_cache else ("__ALL__" if "__ALL__" in premium_band_cache else "__GLOBAL__")
            premium_band_used = premium_band_cache.get(
                band_key_used,
                premium_band_cache.get("__GLOBAL__", (40.0, 150.0)),
            )
            if opt.get("ltp") is None:
                _count_option_reject("invalid_option_ltp")
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "invalid_option_ltp", atr=atr))
                continue
            opt_ltp = float(opt.get("ltp") or 0.0)
            if opt_ltp <= 0:
                _count_option_reject("invalid_option_ltp")
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "invalid_option_ltp", atr=atr))
                continue
            # Premium sanity guard (soft veto; execution blocked in LIVE)
            try:
                premium_min = float(getattr(cfg, "OPTION_PREMIUM_SANITY_MIN", 1.0))
                premium_max = float(getattr(cfg, "OPTION_PREMIUM_SANITY_MAX", 1000.0))
                max_by_sym = getattr(cfg, "OPTION_PREMIUM_SANITY_MAX_BY_SYMBOL", {}) or {}
                min_by_sym = getattr(cfg, "OPTION_PREMIUM_SANITY_MIN_BY_SYMBOL", {}) or {}
                if symbol in min_by_sym:
                    premium_min = float(min_by_sym.get(symbol, premium_min))
                if symbol in max_by_sym:
                    premium_max = float(max_by_sym.get(symbol, premium_max))
                if opt_ltp < premium_min or opt_ltp > premium_max:
                    if "premium_sanity" not in soft_veto_codes:
                        soft_veto_codes.append("premium_sanity")
                    if market_ctx.mode == "LIVE" and "premium_sanity" not in execution_blockers:
                        execution_blockers.append("premium_sanity")
            except Exception:
                pass
            # Hard reject stale quotes before any scoring
            quote_age = opt.get("quote_age_sec")
            quote_ts_epoch = opt.get("quote_ts_epoch")
            hard_missing_quote = bool(
                (not bool(opt.get("quote_ok", True)))
                and opt.get("bid") is None
                and opt.get("ask") is None
            )
            hard_depth_required_fail = bool(
                require_depth_quotes and not bool(opt.get("depth_ok", False)) and not allow_display_only_candidate
            )
            hard_volume_required_fail = bool(
                require_volume and float(opt.get("volume") or 0) <= 0
            )
            advisory_stale_mode = bool(
                market_ctx.allow_stale_quotes
                or exec_mode in {"SIM", "PAPER", "PLANNING", "ADVISORY"}
                or bool(getattr(market_ctx, "planning_only", False))
            )
            advisory_stale_mode = bool(
                advisory_stale_mode
                and not hard_missing_quote
                and not hard_depth_required_fail
                and not hard_volume_required_fail
            )
            strict_quotes = bool(
                runtime_profile.suggestion_require_live_quotes
                and getattr(cfg, "STRICT_LIVE_QUOTES", True)
                and runtime_profile.execution_require_live_quotes
                and (not market_ctx.allow_stale_quotes)
            )
            if exec_mode == "PAPER" and not getattr(cfg, "PAPER_STRICT_QUOTES", True):
                strict_quotes = False
            quote_source = str(opt.get("quote_source") or "")
            if market_ctx.allow_stale_quotes or ("synthetic" in quote_source.lower()):
                strict_quotes = False
            if strict_quotes:
                if quote_ts_epoch is None:
                    _count_option_reject("stale_option_quote")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "stale_option_quote", atr=atr))
                    continue
                if quote_age is None or quote_age > getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8):
                    _count_option_reject("stale_option_quote")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "stale_option_quote", atr=atr))
                    continue
            elif quote_ts_epoch is None or (quote_age is not None and quote_age > getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8)):
                if advisory_stale_mode:
                    _append_unique(advisory_flags, "stale_option_quote")
                    execution_block_type = "advisory"
                    if "stale_option_quote" not in execution_blockers:
                        execution_blockers.append("stale_option_quote")
                else:
                    _record_issue("stale_option_quote", role=ISSUE_CATEGORY_HARD)
            # Hard reject missing bid/ask
            if opt.get("quote_ok") is False:
                require_hard_quote = bool(
                    (strict_quotes or require_depth_quotes or require_volume) and not allow_display_only_candidate
                )
                if require_hard_quote:
                    stale_quote_detected = bool(
                        quote_ts_epoch is None
                        or (quote_age is not None and quote_age > getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8))
                    )
                    if stale_quote_detected:
                        _count_option_reject("STALE_OPTION_TICK")
                    else:
                        _count_option_reject("no_quote")
                    if debug_reasons:
                        rejected.append(
                            self._reject_record(
                                symbol,
                                opt,
                                opt_type,
                                "STALE_OPTION_TICK" if stale_quote_detected else "no_quote",
                                atr=atr,
                            )
                        )
                    _preserve_dirty_option_candidate("no_quote")
                    continue
                missing_role = ISSUE_CATEGORY_SOFT if (market_ctx.allow_stale_quotes or exec_mode in {"SIM", "PAPER", "PLANNING", "ADVISORY"}) else ISSUE_CATEGORY_HARD
                _record_issue("option_quote_missing", role=missing_role)
                if missing_role != ISSUE_CATEGORY_HARD and "option_quote_missing" not in execution_blockers:
                    execution_blockers.append("option_quote_missing")
            # Skip synthetic quotes (no live price)
            require_live_option_quotes = bool(
                runtime_profile.suggestion_require_live_quotes
                and getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", False)
                and (not market_ctx.allow_stale_quotes)
                and exec_mode == "LIVE"
            )
            if not opt.get("quote_ok", True) or (require_live_option_quotes and ("synthetic" not in quote_source.lower()) and not opt.get("quote_live", True)):
                if require_live_option_quotes:
                    _count_option_reject("no_quote")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                    continue
                _record_issue("option_quote_not_live", role=ISSUE_CATEGORY_HARD)
            if getattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", False) and not opt.get("depth_ok", False):
                if require_depth_quotes and not allow_display_only_candidate:
                    _count_option_reject("no_depth")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_depth", atr=atr))
                    continue
                _record_issue("option_depth_missing", role=ISSUE_CATEGORY_WARNING)
            if opt.get("bid") is None or opt.get("ask") is None:
                if strict_quotes and not allow_display_only_candidate:
                    _count_option_reject("no_bid_ask")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_bid_ask", atr=atr))
                    continue
                if not allow_display_only_candidate:
                    synth_abs = float(getattr(cfg, "OPTION_SYNTH_SPREAD_ABS", 0.5))
                    synth_pct = float(getattr(cfg, "OPTION_SYNTH_SPREAD_PCT", 0.01))
                    synth_spread = max(synth_abs, opt_ltp * synth_pct)
                    opt["bid"] = round(max(0.01, opt_ltp - (synth_spread / 2.0)), 4)
                    opt["ask"] = round(max(0.01, opt_ltp + (synth_spread / 2.0)), 4)
                    opt["quote_ok"] = False
                    opt["quote_live"] = False
                    opt["synthetic_bidask"] = True
                _record_issue("option_bidask_missing", role=ISSUE_CATEGORY_HARD)
            if getattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", False) and not opt.get("volume", 0):
                if require_volume:
                    _count_option_reject("no_volume")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_volume", atr=atr))
                    continue
                _record_issue("option_volume_missing", role=ISSUE_CATEGORY_WARNING)

            tradability_ok, tradability_ctx = self._option_tradability_precondition(
                symbol=symbol,
                opt=opt,
                market_data=market_data,
                market_ctx=market_ctx,
                direction=direction,
            )
            if bool(tradability_ctx.get("stale_option_tick")):
                _log_freshness_debug(
                    "TRADE_BUILDER_STALE_OPTION_TICK_SOFTENED symbol=%s mode=%s quote_age_sec=%s sla_sec=%s quote_source=%s",
                    symbol,
                    str(getattr(market_ctx, "mode", "") or "").strip().upper(),
                    tradability_ctx.get("quote_age_sec"),
                    tradability_ctx.get("option_tick_sla_sec") or tradability_ctx.get("sla_threshold_sec"),
                    tradability_ctx.get("option_ltp_source") or tradability_ctx.get("quote_source"),
                )
                stale_allowed = bool(
                    getattr(market_ctx, "allow_stale_quotes", False)
                    or tradability_ctx.get("stale_allowed")
                    or tradability_ctx.get("stale_bypass")
                )
                if stale_allowed and not (
                    hard_missing_quote or hard_depth_required_fail or hard_volume_required_fail
                ):
                    _append_unique(advisory_flags, "stale_option_quote")
                    execution_block_type = "advisory"
                    if "stale_option_quote" not in execution_blockers:
                        execution_blockers.append("stale_option_quote")
                else:
                    _record_issue("stale_option_quote", role=ISSUE_CATEGORY_HARD)
                if "stale_option_tick" not in execution_blockers:
                    execution_blockers.append("stale_option_tick")
                opt["stale_option_tick_downgraded"] = True
                opt["expiry"] = tradability_ctx.get("expiry_date") or opt.get("expiry")
                opt["expiry_date"] = tradability_ctx.get("expiry_date") or opt.get("expiry_date")
                opt["tradingsymbol"] = tradability_ctx.get("tradingsymbol") or opt.get("tradingsymbol")
                opt["instrument_token"] = tradability_ctx.get("instrument_token") or opt.get("instrument_token")
                opt["quote_source"] = tradability_ctx.get("quote_source") or opt.get("quote_source")
                opt["option_ltp_source"] = tradability_ctx.get("option_ltp_source") or opt.get("option_ltp_source")
                opt["quote_age_sec"] = tradability_ctx.get("quote_age_sec")
                opt["option_tick_sla_sec"] = tradability_ctx.get("option_tick_sla_sec") or tradability_ctx.get("sla_threshold_sec")
            if not tradability_ok:
                reason_code = str(tradability_ctx.get("reason_code") or "option_tradability_precondition_failed")
                stale_advisory_ok = bool(
                    reason_code == "STALE_OPTION_TICK"
                    and self._allow_non_live_stale_option_tick_advisory(market_ctx)
                )
                if stale_advisory_ok:
                    _log_freshness_debug(
                        "TRADE_BUILDER_STALE_OPTION_TICK_DOWNGRADED symbol=%s mode=%s quote_age_sec=%s sla_sec=%s quote_source=%s",
                        symbol,
                        str(getattr(market_ctx, "mode", "") or "").strip().upper(),
                        tradability_ctx.get("quote_age_sec"),
                        tradability_ctx.get("option_tick_sla_sec") or tradability_ctx.get("sla_threshold_sec"),
                        tradability_ctx.get("option_ltp_source") or tradability_ctx.get("quote_source"),
                    )
                    if not (hard_missing_quote or hard_depth_required_fail or hard_volume_required_fail):
                        _append_unique(advisory_flags, "stale_option_quote")
                        execution_block_type = "advisory"
                        if "stale_option_quote" not in execution_blockers:
                            execution_blockers.append("stale_option_quote")
                    opt["stale_option_tick_downgraded"] = True
                    opt["expiry"] = tradability_ctx.get("expiry_date") or opt.get("expiry")
                    opt["expiry_date"] = tradability_ctx.get("expiry_date") or opt.get("expiry_date")
                    opt["tradingsymbol"] = tradability_ctx.get("tradingsymbol") or opt.get("tradingsymbol")
                    opt["instrument_token"] = tradability_ctx.get("instrument_token") or opt.get("instrument_token")
                    opt["quote_source"] = tradability_ctx.get("quote_source") or opt.get("quote_source")
                    opt["option_ltp_source"] = tradability_ctx.get("option_ltp_source") or opt.get("option_ltp_source")
                    opt["quote_age_sec"] = tradability_ctx.get("quote_age_sec")
                    opt["option_tick_sla_sec"] = tradability_ctx.get("option_tick_sla_sec") or tradability_ctx.get("sla_threshold_sec")
                else:
                    _count_option_reject(reason_code)
                    self._reject_ctx = {
                        "symbol": symbol,
                        "reason": reason_code,
                        "gate_name": tradability_ctx.get("gate_name"),
                        "contract": tradability_ctx.get("contract"),
                        "missing_fields": tradability_ctx.get("missing_fields"),
                        "instrument_token": tradability_ctx.get("instrument_token"),
                        "quote_source": tradability_ctx.get("quote_source"),
                        "option_ltp_source": tradability_ctx.get("option_ltp_source"),
                        "quote_age_sec": tradability_ctx.get("quote_age_sec"),
                        "option_tick_sla_sec": tradability_ctx.get("option_tick_sla_sec") or tradability_ctx.get("sla_threshold_sec"),
                    }
                    self._log_precondition_reject(
                        symbol,
                        reason_code,
                        str(tradability_ctx.get("reason_text") or reason_code),
                        market_data=market_data,
                        extra=dict(tradability_ctx),
                    )
                    if debug_reasons:
                        rec = self._reject_record(symbol, opt, opt_type, reason_code, atr=atr)
                        rec.update(
                            {
                                "gate_name": tradability_ctx.get("gate_name"),
                                "quote_source": tradability_ctx.get("quote_source"),
                                "option_ltp_source": tradability_ctx.get("option_ltp_source"),
                                "quote_age_sec": tradability_ctx.get("quote_age_sec"),
                                "option_tick_sla_sec": tradability_ctx.get("option_tick_sla_sec") or tradability_ctx.get("sla_threshold_sec"),
                                "contract": tradability_ctx.get("contract"),
                            }
                        )
                        rejected.append(rec)
                    continue

            # Liquidity guard
            spread_pct = (float(opt.get("ask") or 0.0) - float(opt.get("bid") or 0.0)) / opt_ltp if opt_ltp else 1
            max_spread = float(current_filter_profile.max_spread_pct)
            toxic_spread = max(float(getattr(cfg, "MAX_SPREAD_PCT_TOXIC", 0.08)), float(max_spread) * 3.0)
            if exec_mode == "PAPER" and getattr(cfg, "PAPER_STRICT_MODE", False):
                if not opt.get("quote_ok", False):
                    _count_option_reject("no_quote")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                    continue
                if spread_pct > max_spread:
                    _count_option_reject("spread_pct")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "spread_pct", atr=atr))
                    _preserve_dirty_option_candidate("spread_pct")
                    continue
            opt["spread_pct"] = spread_pct
            if not quick_mode:
                vol = opt.get("volume", 0)
                min_volume_filter = int(max(0, current_filter_profile.min_volume_filter))
                if vol and vol < min_volume_filter:
                    if not _relax("low_volume"):
                        if runtime_profile.suggestion_require_volume:
                            _count_option_reject("low_volume")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=low_volume", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "low_volume", atr=atr))
                            continue
                    _record_issue("low_volume", role=ISSUE_CATEGORY_WARNING)
                if spread_pct > max_spread:
                    _mark_dirty_option_blocker("spread_pct")
                    if (not _relax("spread_pct")) and spread_pct > toxic_spread and runtime_profile.suggestion_require_depth:
                        _count_option_reject("spread_pct")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=spread_pct spread_pct=%.4f", symbol, opt.get("strike"), opt_type, spread_pct)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "spread_pct", atr=atr))
                        continue
                    if not _relax("spread_pct"):
                        _record_issue("spread_pct", role=ISSUE_CATEGORY_WARNING)

            # OI / Greeks filters
            if not quick_mode:
                iv_debug_val = float(opt.get("iv")) if opt.get("iv") is not None else float("nan")
                iv_skew_curve_debug_val = (
                    float(opt.get("iv_skew_curvature"))
                    if opt.get("iv_skew_curvature") is not None
                    else float("nan")
                )
                logger.debug(
                    "IV_DEBUG symbol=%s iv=%.3f skew=%.3f bounds=(%.2f,%.2f)",
                    symbol,
                    iv_debug_val,
                    iv_skew_curve_debug_val,
                    float(getattr(cfg, "MIN_IV", 0.1)),
                    float(getattr(cfg, "MAX_IV", 0.6)),
                )
                if opt.get("oi", 0) and opt.get("oi", 0) < getattr(cfg, "MIN_OI", 1000) and not _relax("low_oi"):
                    _count_option_reject("low_oi")
                    if debug_reasons:
                        _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=low_oi", symbol, opt.get("strike"), opt_type)
                        rejected.append(self._reject_record(symbol, opt, opt_type, "low_oi", atr=atr))
                    continue
                if opt.get("oi_change", 0):
                    atm_thresh = getattr(cfg, "ATM_MONEYNESS_THRESHOLD", 0.01)
                    min_oi_atm = getattr(cfg, "MIN_OI_CHANGE_ATM", 200)
                    min_oi_otm = getattr(cfg, "MIN_OI_CHANGE_OTM", 300)
                    mny = abs(opt.get("moneyness", 0))
                    min_oi = min_oi_atm if mny <= atm_thresh else min_oi_otm
                    iv = opt.get("iv", 0) or 0
                    atr = market_data.get("atr", 0) or 0
                    ltp = market_data.get("ltp", 1) or 1
                    scale = 1 + iv * getattr(cfg, "OI_DYNAMIC_IV_ALPHA", 2.0) + (atr / ltp) * getattr(cfg, "OI_DYNAMIC_ATR_ALPHA", 1.0)
                    min_oi = int(min_oi * scale)
                    if abs(opt.get("oi_change", 0)) < min_oi and not _relax("oi_change_min"):
                        _count_option_reject("oi_change_min")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=oi_change_min", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "oi_change_min", atr=atr))
                        continue
                if opt.get("iv") is not None:
                    if (opt["iv"] < getattr(cfg, "MIN_IV", 0.1) or opt["iv"] > getattr(cfg, "MAX_IV", 0.6)) and not _relax("iv_bounds"):
                        if bool(getattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", False)):
                            _count_option_reject("iv_bounds")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_bounds", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "iv_bounds", atr=atr))
                            continue
                        _record_issue("iv_bounds", role=ISSUE_CATEGORY_SOFT)
                        _append_unique(non_live_relaxed_gate_codes, "iv_bounds")
                if opt.get("iv_z") is not None:
                    if (opt["iv_z"] < getattr(cfg, "IV_Z_MIN", -1.5) or opt["iv_z"] > getattr(cfg, "IV_Z_MAX", 1.5)) and not _relax("iv_z_bounds"):
                        _count_option_reject("iv_z_bounds")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_z_bounds", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_z_bounds", atr=atr))
                        continue
                if opt.get("iv_skew") is not None:
                    if abs(opt["iv_skew"]) > getattr(cfg, "IV_SKEW_MAX", 0.05) and not _relax("iv_skew_max"):
                        _count_option_reject("iv_skew_max")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_max", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_max", atr=atr))
                        continue
                    if direction == "BUY_CALL" and opt["iv_skew"] > getattr(cfg, "IV_SKEW_BULL_MAX", 0.02) and not _relax("iv_skew_bull"):
                        _count_option_reject("iv_skew_bull")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_bull", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_bull", atr=atr))
                        continue
                    if direction == "BUY_PUT" and opt["iv_skew"] < getattr(cfg, "IV_SKEW_BEAR_MIN", -0.02) and not _relax("iv_skew_bear"):
                        _count_option_reject("iv_skew_bear")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_bear", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_bear", atr=atr))
                        continue
                    if opt_type == "CE" and opt["iv_skew"] > getattr(cfg, "IV_SKEW_CALL_MAX", 0.03) and not _relax("iv_skew_call"):
                        _count_option_reject("iv_skew_call")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_call", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_call", atr=atr))
                        continue
                    if opt_type == "PE" and opt["iv_skew"] < getattr(cfg, "IV_SKEW_PUT_MIN", -0.03) and not _relax("iv_skew_put"):
                        _count_option_reject("iv_skew_put")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_put", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_put", atr=atr))
                        continue
                if opt.get("iv_skew_norm") is not None:
                    if abs(opt["iv_skew_norm"]) > getattr(cfg, "IV_SKEW_MAX", 0.05) and not _relax("iv_skew_norm"):
                        _count_option_reject("iv_skew_norm")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_norm", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_norm", atr=atr))
                        continue
                if opt.get("iv_skew_curvature") is not None:
                    if abs(opt["iv_skew_curvature"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curvature"):
                        if bool(getattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", False)):
                            _count_option_reject("iv_skew_curvature")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_curvature", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curvature", atr=atr))
                            continue
                        _record_issue("iv_skew_curvature", role=ISSUE_CATEGORY_SOFT)
                        _append_unique(non_live_relaxed_gate_codes, "iv_skew_curvature")
                if opt_type == "CE" and opt.get("iv_skew_curvature_call") is not None:
                    if abs(opt["iv_skew_curvature_call"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curve_call"):
                        if bool(getattr(cfg, "OPTION_IV_SKEW_CURVE_HARD_REJECT", False)):
                            _count_option_reject("iv_skew_curve_call")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_curve_call", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curve_call", atr=atr))
                            continue
                        _record_issue("iv_skew_curvature", role=ISSUE_CATEGORY_SOFT)
                        _append_unique(non_live_relaxed_gate_codes, "iv_skew_curve_call")
                if opt_type == "PE" and opt.get("iv_skew_curvature_put") is not None:
                    if abs(opt["iv_skew_curvature_put"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curve_put"):
                        if bool(getattr(cfg, "OPTION_IV_SKEW_CURVE_HARD_REJECT", False)):
                            _count_option_reject("iv_skew_curve_put")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_curve_put", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curve_put", atr=atr))
                            continue
                        _record_issue("iv_skew_curvature", role=ISSUE_CATEGORY_SOFT)
                        _append_unique(non_live_relaxed_gate_codes, "iv_skew_curve_put")
                if opt.get("iv_term") is not None:
                    iv_term_out_of_bounds = bool(
                        opt["iv_term"] < getattr(cfg, "IV_TERM_MIN", -0.05)
                        or opt["iv_term"] > getattr(cfg, "IV_TERM_MAX", 0.05)
                    )
                    if iv_term_out_of_bounds:
                        _mark_dirty_option_blocker("iv_term")
                    if iv_term_out_of_bounds and not _relax("iv_term"):
                        _count_option_reject("iv_term")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_term", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_term", atr=atr))
                        continue
                elif (
                    bool(opt.get("iv_term_unavailable"))
                    or bool(opt.get("iv_term_missing"))
                    or bool(opt.get("next_expiry_missing"))
                    or bool(market_data.get("iv_term_unavailable"))
                    or bool(market_data.get("next_expiry_missing"))
                    or bool(str(opt.get("iv_term_unavailable_reason") or market_data.get("iv_term_unavailable_reason") or "").strip())
                ):
                    _record_issue("iv_term", role=ISSUE_CATEGORY_WARNING)
                    _mark_dirty_option_blocker("iv_term")
                if opt.get("iv_surface_slope") is not None:
                    iv_surface_out_of_bounds = abs(opt["iv_surface_slope"]) > getattr(cfg, "IV_SURFACE_SLOPE_MAX", 0.15)
                    if iv_surface_out_of_bounds:
                        _mark_dirty_option_blocker("iv_surface_slope")
                    if iv_surface_out_of_bounds and not _relax("iv_surface_slope"):
                        _count_option_reject("iv_surface_slope")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_surface_slope", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_surface_slope", atr=atr))
                        continue
                if opt.get("oi_build"):
                    enforce_oi_build_alignment = True
                    if exec_mode == "LIVE" and not bool(getattr(cfg, "LIVE_REQUIRE_OI_BUILD_ALIGNMENT", False)):
                        enforce_oi_build_alignment = False
                    if direction == "BUY_CALL" and opt["oi_build"] not in ("LONG", "SHORT_COVER"):
                        if enforce_oi_build_alignment and not _relax("oi_build"):
                            _count_option_reject("oi_build")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=oi_build", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "oi_build", atr=atr))
                            continue
                        _record_issue("oi_build", role=ISSUE_CATEGORY_SOFT)
                        _append_unique(non_live_relaxed_gate_codes, "oi_build")
                    if direction == "BUY_PUT" and opt["oi_build"] not in ("SHORT", "LONG_LIQ"):
                        if enforce_oi_build_alignment and not _relax("oi_build"):
                            _count_option_reject("oi_build")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=oi_build", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "oi_build", atr=atr))
                            continue
                        _record_issue("oi_build", role=ISSUE_CATEGORY_SOFT)
                        _append_unique(non_live_relaxed_gate_codes, "oi_build")
                if opt.get("delta") is not None:
                    delta_min = float(getattr(cfg, "DELTA_MIN", 0.25))
                    delta_max = float(getattr(cfg, "DELTA_MAX", 0.7))
                    if exec_mode == "LIVE":
                        delta_min = float(getattr(cfg, "LIVE_DELTA_MIN", delta_min))
                        delta_max = float(getattr(cfg, "LIVE_DELTA_MAX", delta_max))
                    if (abs(opt["delta"]) < delta_min or abs(opt["delta"]) > delta_max) and not _relax("delta"):
                        if exec_mode == "LIVE" and not bool(getattr(cfg, "LIVE_DELTA_HARD_REJECT_ENABLE", False)):
                            _record_issue("delta", role=ISSUE_CATEGORY_SOFT)
                            _append_unique(non_live_relaxed_gate_codes, "delta")
                        else:
                            _count_option_reject("delta")
                            if debug_reasons:
                                _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=delta", symbol, opt.get("strike"), opt_type)
                                rejected.append(self._reject_record(symbol, opt, opt_type, "delta", atr=atr))
                            continue

            # Premium gate: hard only for poor liquidity, otherwise soft-veto.
            min_p, max_p = premium_band_used
            min_p, max_p, band_context = self._adjust_premium_band(
                symbol=symbol,
                opt=opt,
                market_data=market_data,
                base_band=(float(min_p), float(max_p)),
                spread_pct=spread_pct,
            )
            premium_relax_pct = float(max(0.0, current_filter_profile.premium_relax_pct))
            if premium_relax_pct > 0:
                min_p = max(0.0, float(min_p) * max(0.0, 1.0 - premium_relax_pct))
                max_p = float(max_p) * (1.0 + premium_relax_pct)
            if (opt_ltp < min_p or opt_ltp > max_p) and not _relax("premium"):
                execution_mode = str(
                    market_data.get("execution_mode")
                    or ((market_data.get("market_context") or {}).get("execution_mode") if isinstance(market_data.get("market_context"), dict) else "")
                    or getattr(cfg, "EXECUTION_MODE", "")
                ).strip().upper()
                soft_premium_advisory = execution_mode in {"SIM", "PAPER"}
                spread_bad = bool(spread_pct > toxic_spread)
                volume_bad = bool((opt.get("volume") or 0) < int(getattr(cfg, "MIN_VOLUME_FILTER", 500)) * 0.25)
                quote_missing = bool(opt.get("quote_ok") is False or opt.get("bid") is None or opt.get("ask") is None)
                market_open = bool(getattr(market_ctx, "market_open", True))
                hard_liquidity_reject = bool(
                    execution_mode == "LIVE"
                    and market_open
                    and (spread_bad or volume_bad or quote_missing)
                )
                hard_reject_enabled = bool(getattr(cfg, "PREMIUM_BAND_HARD_REJECT_ENABLE", True)) and execution_mode == "LIVE"
                premium_hard_veto = hard_liquidity_reject and hard_reject_enabled
                if premium_hard_veto:
                    _record_premium_band_failure(
                        opt,
                        min_p=min_p,
                        max_p=max_p,
                        spread_pct=spread_pct,
                        hard_veto=True,
                        count_scan=False,
                    )
                    if emit_premium_candidate_logs:
                        self._log_premium_band_debug(
                            symbol=symbol,
                            opt=opt,
                            min_p=min_p,
                            max_p=max_p,
                            band_context=band_context,
                            spread_pct=spread_pct,
                            reason="premium_band_softened_hard_liquidity",
                            strategy_tag=candidate_strategy_tag,
                        )
                    premium_soft_veto = True
                    _record_issue("premium_out_of_band", role=ISSUE_CATEGORY_SOFT)
                if not premium_hard_veto:
                    premium_soft_veto = True
                    _record_premium_band_failure(
                        opt,
                        min_p=min_p,
                        max_p=max_p,
                        spread_pct=spread_pct,
                        hard_veto=False,
                        count_scan=False,
                    )
                    if emit_premium_candidate_logs:
                        self._log_premium_band_debug(
                            symbol=symbol,
                            opt=opt,
                            min_p=min_p,
                            max_p=max_p,
                            band_context=band_context,
                            spread_pct=spread_pct,
                            reason="premium_band_softened",
                            strategy_tag=candidate_strategy_tag,
                        )
                    _record_issue("premium_out_of_band", role=ISSUE_CATEGORY_SOFT)
                if opt_ltp < float(min_p):
                    premium_outside_ratio = (float(min_p) - float(opt_ltp)) / max(float(min_p), 1e-6)
                elif opt_ltp > float(max_p):
                    premium_outside_ratio = (float(opt_ltp) - float(max_p)) / max(float(max_p), 1e-6)
                penalty_scale = min(
                    1.0,
                    max(0.0, premium_outside_ratio) * float(getattr(cfg, "PREMIUM_SOFT_VETO_PENALTY_SCALE", 1.5)),
                )
                conf_floor = float(getattr(cfg, "PREMIUM_SOFT_VETO_CONF_FLOOR", 0.75))
                size_floor = float(getattr(cfg, "PREMIUM_SOFT_VETO_SIZE_FLOOR", 0.70))
                premium_soft_penalty_conf = max(conf_floor, 1.0 - (0.30 * penalty_scale))
                premium_soft_penalty_size = max(size_floor, 1.0 - (0.40 * penalty_scale))

            # Spread check: soft-veto in planning/permissive suggestion stage.
            if not self.execution.spread_ok(opt.get("bid"), opt.get("ask"), opt_ltp, max_spread_pct=max_spread) and not _relax("spread_ok"):
                hard_spread_reject = bool(runtime_profile.suggestion_require_depth and (not market_ctx.allow_stale_quotes))
                if hard_spread_reject:
                    _count_option_reject("spread_ok")
                    if debug_reasons:
                        _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=spread_ok", symbol, opt.get("strike"), opt_type)
                        rec = self._reject_record(symbol, opt, opt_type, "spread_ok", atr=atr)
                        debug_candidates.append(rec)
                        rejected.append(rec)
                    continue
                _record_issue("spread_ok", role=ISSUE_CATEGORY_WARNING)

            # ML confidence (only if enough history)
            feature_opt = opt
            if opt.get("bid") is None or opt.get("ask") is None:
                feature_opt = dict(opt)
                feature_price = (
                    self._coerce_positive_float(opt.get("mark_price"))
                    or self._coerce_positive_float(opt.get("mid_price"))
                    or self._coerce_positive_float(opt.get("ltp"))
                    or self._coerce_positive_float(opt.get("last_price"))
                )
                if feature_price is not None:
                    synth_abs = float(getattr(cfg, "OPTION_SYNTH_SPREAD_ABS", 0.5))
                    synth_pct = float(getattr(cfg, "OPTION_SYNTH_SPREAD_PCT", 0.01))
                    synth_spread = max(synth_abs, float(feature_price) * synth_pct)
                    feature_opt["bid"] = round(max(0.01, float(feature_price) - (synth_spread / 2.0)), 4)
                    feature_opt["ask"] = round(max(0.01, float(feature_price) + (synth_spread / 2.0)), 4)
            feats = pd.DataFrame([build_trade_features(market_data, feature_opt)])
            use_ml = True
            if getattr(cfg, "ML_USE_ONLY_WITH_HISTORY", True):
                use_ml = self._ml_history_count() >= getattr(cfg, "ML_MIN_TRAIN_TRADES", 200)
            model_type = "xgb"
            model_version = getattr(self.predictor, "model_version", None)
            shadow_version = getattr(self.predictor, "shadow_version", None)
            shadow_confidence = None
            alpha_conf = None
            alpha_unc = None
            size_mult = 1.0
            xgb_conf = None
            deep_conf = None
            micro_conf = None
            confidence_model_component = None
            confidence_micro_component = None
            confidence_micro_blend_method = None
            if use_ml:
                ok_features, feature_reason = self._validate_ml_features(feats)
                if not ok_features:
                    _count_option_reject(feature_reason)
                    self._reject_ctx = {
                        "symbol": symbol,
                        "reason": feature_reason,
                        "feature_contract_failed": True,
                    }
                    intent = self.trade_intent_flags(
                        market_data,
                        opt=opt,
                        risk_guard_passed=False,
                        additional_blockers=[feature_reason],
                    )
                    instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                        symbol,
                        "OPT",
                        self._option_expiry(opt, market_data),
                        opt.get("strike"),
                        opt.get("type"),
                        1,
                    )
                    if ident_err:
                        _count_option_reject("missing_contract_fields")
                        if debug_reasons:
                            rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
                            rejected.append(rec)
                        continue
                    expiry_resolved = self._option_expiry(opt, market_data) or self._resolve_expiry_for_symbol(symbol, market_data)
                    contract = self._resolve_option_contract(
                        symbol,
                        opt.get("strike"),
                        opt.get("type"),
                        expiry_resolved,
                        market_data,
                    )
                    expiry_resolved = contract.get("expiry") or expiry_resolved
                    tradingsymbol = contract.get("tradingsymbol") or opt.get("tradingsymbol")
                    instrument_token = contract.get("instrument_token") or opt.get("instrument_token")
                    atr = market_data.get("atr", max(1.0, ltp * 0.002))
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    if instrument_token is None:
                        _count_option_reject("missing_contract_fields")
                        if debug_reasons:
                            rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
                            rejected.append(rec)
                        continue
                    blocked_trade = Trade(
                        trade_id=f"{symbol}-{opt['strike']}-{opt['type']}-BLOCKED-{ts}",
                        timestamp=datetime.now(),
                        symbol=symbol,
                        instrument="OPT",
                        instrument_type=instrument_type,
                        right=opt.get("type"),
                        instrument_id=instrument_id,
                        instrument_token=instrument_token,
                        strike=opt["strike"],
                        expiry=expiry_resolved,
                        expiry_date=expiry_resolved,
                        tradingsymbol=tradingsymbol,
                        option_type=opt.get("type"),
                        side="BUY",
                        entry_price=round(opt.get("ask") or opt.get("ltp") or 0.0, 2),
                        stop_loss=round(max((opt.get("bid") or 0.0) * 0.95, 0.01), 2),
                        target=round((opt.get("ask") or opt.get("ltp") or 0.0) * 1.05, 2),
                        qty=1,
                        qty_lots=1,
                        qty_units=qty_units,
                        validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
                        capital_at_risk=0.01,
                        expected_slippage=0.0,
                        confidence=0.0,
                        strategy=strategy_tag,
                        regime=market_data.get("regime", "NEUTRAL"),
                        tier="MAIN",
                        day_type=market_data.get("day_type", "UNKNOWN"),
                        **self._option_liquidity_fields(opt),
                        quote_ok=opt.get("quote_ok", True),
                        tradable=False,
                        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                        planning_only=bool(intent["planning_only"]),
                        execution_allowed=bool(intent["execution_allowed"]),
                        reason=intent["execution_reason"],
                        source_flags=dict(intent["source_flags"]),
                        **self._staged_confidence_payload(
                            confidence=0.0,
                            model_raw=0.0,
                            model_component=0.0,
                            micro_blend_method="model_only",
                            before_soft_veto=0.0,
                            after_soft_veto=0.0,
                            penalty_soft_veto_total=0.0,
                            penalty_soft_veto_reasons=[],
                            base=0.0,
                            penalty_total=0.0,
                            penalty_reasons=[],
                        ),
                    )
                    blocked_trade = self._decorate_trade_context(blocked_trade, market_data, 0.0)
                    if blocked_trade is not None:
                        candidates.append(blocked_trade)
                    if debug_reasons:
                        rec = self._reject_record(symbol, opt, opt_type, feature_reason, atr=atr)
                        rejected.append(rec)
                    continue
                xgb_conf = self.predictor.predict_confidence(feats)
                if getattr(cfg, "ML_AB_ENABLE", False):
                    shadow_confidence = self.predictor.predict_confidence_shadow(feats)
                if cfg.USE_DEEP_MODEL and seq_buffer is not None:
                    deep_pred = self._get_deep_predictor()
                    deep_conf = deep_pred.predict_confidence(seq_buffer)
                    model_type = "deep"
                    model_version = getattr(deep_pred, "model_version", model_version)
                confidence = deep_conf if deep_conf is not None else xgb_conf
                confidence_model_raw = confidence
                confidence_model_component = self._clamp_confidence(confidence)
                confidence_after_micro = None
                # Microstructure overlay
                if cfg.USE_MICRO_MODEL:
                    micro_features = [
                        float(opt.get("spread_pct", (opt["ask"] - opt["bid"]) / opt["ltp"] if opt["ltp"] else 0)),
                        float(opt.get("volume", 0)),
                        float(opt.get("oi_change", 0)),
                        float(market_data.get("fx_ret_5m", 0.0) or market_data.get("x_usdinr_ret5") or 0.0),
                        float(market_data.get("vix_z", 0.0) or market_data.get("x_india_vix_z") or 0.0),
                        float(market_data.get("crude_ret_15m", 0.0) or market_data.get("x_crude_ret15") or 0.0),
                        float(market_data.get("corr_fx_nifty", 0.0) or market_data.get("x_usdinr_corr_nifty") or 0.0),
                    ]
                    micro_conf = self._get_micro_predictor().predict_confidence(micro_features)
                    opt["micro_pred"] = micro_conf
                    confidence_micro_component = self._clamp_confidence(micro_conf)
                    confidence, confidence_micro_blend_method = self._blend_micro_confidence(confidence, micro_conf)
                    confidence_after_micro = confidence
                if confidence is None:
                    confidence = 0.5
                if confidence_model_raw is None:
                    confidence_model_raw = confidence
            else:
                # Pure price/volume logic: use signal score as confidence proxy
                confidence = max(0.5, min(1.0, signal.get("score", 0.5)))
                confidence_model_raw = confidence
                confidence_model_component = self._clamp_confidence(confidence)
                confidence_micro_blend_method = "model_only"
                confidence_after_micro = None

            # Alpha ensemble fusion
            adj_conf, alpha_conf, alpha_unc, size_mult = self._apply_alpha_ensemble(
                confidence, xgb_conf, deep_conf, micro_conf, market_data, quick_mode=quick_mode
            )
            if adj_conf is None and not _relax("confidence"):
                _count_option_reject("alpha_uncertainty")
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "alpha_uncertainty", atr=atr)
                    rec["confidence"] = round(confidence, 3)
                    rec["alpha_uncertainty"] = alpha_unc
                    debug_candidates.append(rec)
                    rejected.append(rec)
                continue
            confidence = adj_conf
            confidence_after_alpha = confidence
            size_mult = min(size_mult, decay_size_mult)

            # Latency penalty
            confidence *= self.execution.latency_penalty(opt.get("timestamp", datetime.now().timestamp()))
            confidence_after_latency = confidence

            raw_gate_threshold = self._raw_confidence_gate_threshold(regime_day, quick_mode=quick_mode)
            if quick_mode:
                if getattr(cfg, "QUICK_USE_SIGNAL_SCORE", True):
                    try:
                        confidence = max(confidence, float(signal.get("score", 0.5)))
                    except Exception:
                        pass
            if not quick_mode:
                tune = _get_auto_tune()
                if tune.get("enabled"):
                    raw_gate_threshold = float(tune.get("min_proba", raw_gate_threshold))
            confidence_before_soft_veto = float(confidence)
            if confidence < raw_gate_threshold and not _relax("confidence"):
                _count_option_reject("confidence_raw_gate_shadow")
                if debug_reasons:
                    _log_advisory_debug(
                        "trade_builder_confidence_reject_shadow symbol=%s strike=%s type=%s stage=raw raw_model_conf=%s final_conf=%s threshold=%s regime=%s reason=%s",
                        symbol,
                        opt["strike"],
                        opt_type,
                        round(float(confidence_model_raw), 3) if confidence_model_raw is not None else None,
                        round(float(confidence), 3) if confidence is not None else None,
                        raw_gate_threshold,
                        signal.get("regime_day"),
                        signal.get("reason"),
                    )
                    rec = self._reject_record(symbol, opt, opt_type, "confidence_raw_gate_shadow", atr=atr)
                    rec["confidence"] = round(confidence, 3)
                    rec["min_proba"] = raw_gate_threshold
                    rec["confidence_stage"] = "raw"
                    debug_candidates.append(rec)
                # SHADOW MODE: ML simply observes. We do not append to rejected[] and we do not 'continue'.

            # Slippage adjustment for limit
            calc_bid = self._coerce_positive_float(opt.get("bid"))
            calc_ask = self._coerce_positive_float(opt.get("ask"))
            if calc_bid is None or calc_ask is None:
                display_price = (
                    self._coerce_positive_float(opt.get("mark_price"))
                    or self._coerce_positive_float(opt.get("mid_price"))
                    or self._coerce_positive_float(opt.get("ltp"))
                    or self._coerce_positive_float(opt.get("last_price"))
                )
                if display_price is not None:
                    synth_abs = float(getattr(cfg, "OPTION_SYNTH_SPREAD_ABS", 0.5))
                    synth_pct = float(getattr(cfg, "OPTION_SYNTH_SPREAD_PCT", 0.01))
                    synth_spread = max(synth_abs, float(display_price) * synth_pct)
                    calc_bid = round(max(0.01, float(display_price) - (synth_spread / 2.0)), 4)
                    calc_ask = round(max(0.01, float(display_price) + (synth_spread / 2.0)), 4)
            slippage = (
                self.execution.estimate_slippage(calc_bid, calc_ask, opt.get("volume", 0))
                if calc_bid is not None and calc_ask is not None
                else 0.0
            )
            base_entry_price, entry_price_source = self._option_executable_price(opt, side="BUY")
            if base_entry_price is None or base_entry_price <= 0:
                _count_option_reject("invalid_entry_proxy")
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "invalid_entry_proxy", atr=atr))
                continue
            entry_price = float(base_entry_price)
            _trigger_entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                entry_price, side="BUY", quick_mode=quick_mode
            )
            if entry_ref_price is None:
                entry_ref_price = entry_price
            if entry_condition and _trigger_entry_price is not None:
                entry_price = float(_trigger_entry_price)

            stop_mult = getattr(cfg, "OPT_STOP_ATR_MAIN", 1.0)
            target_mult = getattr(cfg, "OPT_TARGET_ATR_MAIN", 1.8)
            if quick_mode:
                stop_mult = getattr(cfg, "OPT_STOP_ATR_QUICK", stop_mult)
                target_mult = getattr(cfg, "OPT_TARGET_ATR_QUICK", target_mult)
            if regime_day == "TREND":
                stop_mult = stop_mult * float(getattr(cfg, "REGIME_TREND_STOP_MULT", 1.2))
                target_mult = target_mult * float(getattr(cfg, "REGIME_TREND_TARGET_MULT", 2.0))
            elif regime_day in ("RANGE", "RANGE_VOLATILE"):
                stop_mult = stop_mult * float(getattr(cfg, "REGIME_RANGE_STOP_MULT", 0.8))
                target_mult = target_mult * float(getattr(cfg, "REGIME_RANGE_TARGET_MULT", 1.3))
            elif regime_day == "EVENT":
                if not (getattr(cfg, "REGIME_EVENT_ROUTE_ALLOW", True) and getattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True)):
                    _count_option_reject("event_regime_blocked")
                    if debug_reasons:
                        rec = self._reject_record(symbol, opt, opt_type, "event_regime_blocked", atr=option_risk)
                        rejected.append(rec)
                    continue
                stop_mult = stop_mult * float(getattr(cfg, "REGIME_EVENT_STOP_MULT", 1.1))
                target_mult = target_mult * float(getattr(cfg, "REGIME_EVENT_TARGET_MULT", 1.4))
                size_mult = size_mult * float(getattr(cfg, "REGIME_EVENT_SIZE_MULT", 0.6))

            # Phase 2: Wire continuous_regime overlay
            if candidate_strategy_tag == "volatility_trend":
                prices = market_data.get("price_history", [])
                atrs = market_data.get("atr_history", [])
                if len(prices) >= 20 and len(atrs) >= 20:
                    regime_vec = extract_continuous_regime(prices, atrs)
                    target_mult = calculate_dynamic_multiplier(target_mult, regime_vec, sensitivity=0.5)

            option_risk = self._option_risk_proxy(entry_price, calc_bid or 0, calc_ask or 0)
            stop_loss, target = self._opt_risk_levels(
                entry_price, calc_bid or 0, calc_ask or 0, option_risk, stop_mult=stop_mult, target_mult=target_mult,
                regime=regime_day,
                day_type=signal.get("day_type", "UNKNOWN") if isinstance(signal, dict) else getattr(signal, "day_type", "UNKNOWN"),
                timestamp=opt.get("timestamp")
            )
            if not (target > entry_price > stop_loss):
                _count_option_reject("invalid_opt_levels")
                logger.error(
                    "invalid_opt_levels symbol=%s side=%s entry=%s stop=%s target=%s strike=%s right=%s",
                    symbol,
                    "BUY",
                    entry_price,
                    stop_loss,
                    target,
                    opt.get("strike"),
                    opt.get("type"),
                )
                continue

            # Risk/Reward gate (1:2)
            rr = None
            try:
                rr = abs(target - entry_price) / max(abs(entry_price - stop_loss), 1e-6)
            except Exception:
                rr = None
            min_rr = getattr(cfg, "MIN_RR_QUICK", getattr(cfg, "MIN_RR", 1.5)) if quick_mode else getattr(cfg, "MIN_RR", 1.5)
            if not quick_mode:
                tune = _get_auto_tune()
                if tune.get("enabled"):
                    min_rr = float(tune.get("min_rr", min_rr))
            if rr is None or rr < min_rr:
                _count_option_reject("rr_gate")
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "rr_gate", atr=option_risk)
                    rec["rr"] = rr
                    rec["min_rr"] = min_rr
                    rejected.append(rec)
                continue

            # Multi-factor trade score
            score_pack = compute_trade_score(
                market_data,
                opt,
                direction=direction,
                rr=rr,
                strategy_name=strategy_tag,
            )
            score = score_pack.get("score", 0)
            # Optional cross-asset penalties (do not block)
            try:
                cross_q = market_data.get("cross_asset_quality", {}) or {}
                optional = set(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
                stale = set(cross_q.get("stale_feeds", []) or [])
                missing_map = cross_q.get("missing") or {}
                missing = set(k for k, v in missing_map.items() if not str(v).startswith("disabled"))
                bad_optional = (stale | missing) & optional
                if bad_optional:
                    size_mult = min(size_mult, float(getattr(cfg, "CROSS_ASSET_OPTIONAL_SIZE_MULT", 0.85)))
            except Exception:
                pass
            min_score = getattr(cfg, "QUICK_TRADE_SCORE_MIN", 60) if quick_mode else getattr(cfg, "TRADE_SCORE_MIN", 75)
            # Day-type overrides for score threshold
            try:
                dt = (market_data.get("day_type") or "").upper()
                dt_map = getattr(cfg, "TRADE_SCORE_MIN_BY_DAYTYPE", {})
                if isinstance(dt_map, dict) and dt in dt_map:
                    min_score = float(dt_map[dt])
            except Exception:
                pass
            if not quick_mode:
                tune = _get_auto_tune()
                if tune.get("enabled"):
                    min_score = float(tune.get("trade_score_min", min_score))
            if is_live_mode:
                min_score = min(min_score, float(getattr(cfg, "LIVE_TRADE_SCORE_MIN", min_score)))
            if planning_relaxed:
                min_score = min(min_score, float(getattr(cfg, "PLANNING_TRADE_SCORE_MIN", 58)))
            relaxed_trade_score_gate = False
            if score < min_score:
                if is_live_mode and bool(getattr(cfg, "LIVE_TRADE_SCORE_HARD_REJECT_ENABLE", False)):
                    _count_option_reject("trade_score")
                    if debug_reasons:
                        rec = self._reject_record(symbol, opt, opt_type, "trade_score", atr=atr)
                        rec["trade_score"] = score
                        rec["min_score"] = min_score
                        rejected.append(rec)
                    continue
                _record_issue("trade_score", role=ISSUE_CATEGORY_SOFT)
                _append_unique(non_live_relaxed_gate_codes, "trade_score")
                relaxed_trade_score_gate = True

            confidence_base = float(confidence)
            confidence_penalty_reasons = list(dict.fromkeys(str(code) for code in soft_veto_codes if str(code)))
            confidence_penalty_soft_veto_reasons: list[str] = []
            confidence_penalty_soft_veto_total = 0.0
            if soft_veto_codes:
                orb_soft_veto_penalty = 0.0
                premium_soft_veto_penalty = 0.0
                if any(code.startswith("orb_") for code in soft_veto_codes):
                    orb_soft_veto_penalty = self._orb_soft_veto_conf_penalty()
                    confidence_penalty_soft_veto_reasons.extend(
                        str(code) for code in soft_veto_codes if str(code).startswith("orb_")
                    )
                    size_mult = min(size_mult, float(getattr(cfg, "ORB_SOFT_VETO_SIZE_MULT", 0.95)))
                if premium_soft_veto:
                    premium_soft_veto_penalty = self._premium_soft_veto_conf_penalty(penalty_scale)
                    confidence_penalty_soft_veto_reasons.extend(
                        str(code)
                        for code in soft_veto_codes
                        if str(code) in {"premium_out_of_band", "premium_band_fail"}
                    )
                    size_mult = min(size_mult, premium_soft_penalty_size)
                confidence_penalty_soft_veto_total = min(
                    max(0.0, float(getattr(cfg, "SOFT_VETO_CONF_PENALTY_MAX_TOTAL", 0.16))),
                    max(0.0, orb_soft_veto_penalty + premium_soft_veto_penalty),
                )
                confidence_penalty_soft_veto_reasons = list(
                    dict.fromkeys(str(code) for code in confidence_penalty_soft_veto_reasons if str(code))
                )
                confidence = max(0.0, min(1.0, float(confidence) - float(confidence_penalty_soft_veto_total)))
            confidence_after_soft_veto = float(confidence)
            confidence_penalty_total = max(0.0, float(confidence_base) - float(confidence))
            final_gate_threshold = self._final_confidence_gate_threshold(regime_day, quick_mode=quick_mode)
            if confidence < final_gate_threshold and not _relax("confidence"):
                _count_option_reject("confidence_final_gate")
                if debug_reasons:
                    _log_advisory_debug(
                        "trade_builder_confidence_reject symbol=%s strike=%s type=%s stage=final raw_model_conf=%s final_conf=%s threshold=%s regime=%s reason=%s",
                        symbol,
                        opt["strike"],
                        opt_type,
                        round(float(confidence_model_raw), 3) if confidence_model_raw is not None else None,
                        round(float(confidence), 3) if confidence is not None else None,
                        final_gate_threshold,
                        signal.get("regime_day"),
                        signal.get("reason"),
                    )
                    rec = self._reject_record(symbol, opt, opt_type, "confidence_final_gate", atr=atr)
                    rec["confidence"] = round(confidence, 3)
                    rec["min_proba"] = final_gate_threshold
                    rec["confidence_stage"] = "final"
                    debug_candidates.append(rec)
                    rejected.append(rec)
                continue

            tier = "EXPLORATION" if quick_mode else "MAIN"
            resolved_contract = opt.get("_resolved_contract") if isinstance(opt.get("_resolved_contract"), dict) else {}
            option_right = self._coerce_option_type(opt.get("type") or opt.get("option_type") or opt.get("right")) or opt_type
            expiry_resolved = (
                resolved_contract.get("expiry")
                or self._option_expiry(opt, market_data)
                or self._resolve_expiry_for_symbol(symbol, market_data)
            )
            contract = (
                dict(resolved_contract)
                if resolved_contract
                else self._resolve_option_contract(
                    symbol,
                    opt.get("strike"),
                    option_right,
                    expiry_resolved,
                    market_data,
                )
            )
            expiry_resolved = contract.get("expiry") or expiry_resolved
            tradingsymbol = contract.get("tradingsymbol") or opt.get("tradingsymbol")
            instrument_token = contract.get("instrument_token") or opt.get("instrument_token")
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                expiry_resolved,
                opt.get("strike"),
                option_right,
                1,
            )
            if not instrument_id and contract.get("instrument_id"):
                instrument_id = contract.get("instrument_id")
            if ident_err or not expiry_resolved or not tradingsymbol or not instrument_id:
                _count_option_reject("unresolved_contract")
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "unresolved_contract", atr=atr)
                    rejected.append(rec)
                self._log_blocked_candidate(
                    symbol,
                    "unresolved_contract",
                    "Option contract could not be resolved",
                    market_data=market_data,
                    extra={
                        "strike": opt.get("strike"),
                        "option_type": option_right,
                        "expiry": expiry_resolved,
                        "expiry_date": expiry_resolved,
                        "tradingsymbol": tradingsymbol,
                        "instrument_token": instrument_token,
                        "underlying_spot": underlying_spot,
                        "spot_source": spot_source,
                        "skip_derived_levels": True,
                    },
                )
                continue
            if instrument_token is None:
                _count_option_reject("missing_contract_fields")
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
                    rejected.append(rec)
                self._log_blocked_candidate(
                    symbol,
                    "missing_contract_fields",
                    "Option contract missing instrument token",
                    market_data=market_data,
                    extra={
                        "strike": opt.get("strike"),
                        "option_type": option_right,
                        "expiry": expiry_resolved,
                        "tradingsymbol": tradingsymbol,
                    },
                )
                continue
            intent = self.trade_intent_flags(
                market_data,
                opt=opt,
                additional_blockers=list(dict.fromkeys(execution_blockers)),
            )
            source_flags = dict(intent["source_flags"])
            raw_candidate_origin = dict(raw_opt.get("candidate_origin") or {}) if isinstance(raw_opt, dict) else {}
            candidate_origin = {
                "strike_offset": raw_candidate_origin.get("strike_offset"),
                "setup_family": setup_family,
                "expiry_bucket": raw_candidate_origin.get("expiry_bucket") or "other_expiry",
            }
            source_flags["candidate_origin"] = dict(candidate_origin)
            source_flags["strike_offset"] = candidate_origin.get("strike_offset")
            source_flags["setup_family"] = candidate_origin.get("setup_family")
            source_flags["expiry_bucket"] = candidate_origin.get("expiry_bucket")
            if soft_veto_codes:
                source_flags["soft_veto_codes"] = sorted(set(str(code) for code in soft_veto_codes if str(code)))
                source_flags["orb_bias"] = market_data.get("orb_bias")
                source_flags["orb_window_min"] = market_data.get("orb_window_min") or market_data.get("orb_lock_min")
                source_flags["orb_state"] = market_data.get("orb_state")
            if non_live_relaxed_gate_codes:
                source_flags["non_live_relaxed_gate_codes"] = list(
                    dict.fromkeys(str(code) for code in non_live_relaxed_gate_codes if str(code))
                )
            if warning_codes:
                source_flags["warning_codes"] = sorted(set(str(code) for code in warning_codes if str(code)))
            if advisory_flags:
                source_flags["advisory_flags"] = sorted(set(str(code) for code in advisory_flags if str(code)))
            if execution_block_type:
                source_flags["execution_block_type"] = execution_block_type
            if execution_blockers:
                source_flags["gates_failed"] = list(dict.fromkeys(str(code) for code in execution_blockers if str(code)))
            if premium_soft_veto:
                source_flags["premium_band"] = {
                    "min": round(float(min_p), 6),
                    "max": round(float(max_p), 6),
                    "ltp": round(float(opt_ltp), 6),
                    "dynamic": bool(band_key_used in {expiry_key, "__ALL__"}),
                    "band_key": str(band_key_used),
                    "band_fallback": bool(band_key_used == "__GLOBAL__"),
                    "outside_ratio": round(float(premium_outside_ratio), 6),
                    "penalty_conf_mult": round(float(premium_soft_penalty_conf), 6),
                    "penalty_conf": round(float(self._premium_soft_veto_conf_penalty(penalty_scale)), 6),
                    "penalty_size_mult": round(float(premium_soft_penalty_size), 6),
                }
                source_flags["premium_soft_veto"] = True
            source_flags["confidence_penalty_soft_veto_total"] = round(float(confidence_penalty_soft_veto_total), 6)
            source_flags["confidence_penalty_soft_veto_reasons"] = list(confidence_penalty_soft_veto_reasons)
            decision_trace = {
                "signal_score": float(signal.get("score", 0.0)),
                "regime_conf": market_data.get("regime_confidence") or market_data.get("day_confidence"),
                "orb_bias": market_data.get("orb_bias"),
                "orb_factor": None,
                "reg_penalty": None,
                "global_conf": None,
                "preliminary_permission": "EXECUTE" if bool(intent["execution_allowed"]) else "ADVISORY_ONLY",
                "preliminary_permission_reason": intent.get("execution_reason") or (
                    "execution_allowed" if bool(intent["execution_allowed"]) else "intent_blocked"
                ),
                "preliminary_exec_allowed": bool(intent["execution_allowed"]),
                "permission": None,
                "permission_reason": None,
                "entry_status": None,
                "entry_block_reason": None,
                "final_action": None,
                "initial_score": float(signal.get("score", 0.0)) * 100.0,
                "score_penalties": [
                    {"name": str(code), "type": "soft_veto"}
                    for code in list(dict.fromkeys(soft_veto_codes))
                ],
                "final_score": float(score),
                "hard_reject_reason": None,
                "soft_vetos": list(dict.fromkeys(soft_veto_codes)),
                "warnings": list(dict.fromkeys(warning_codes)),
                "confidence_penalty_soft_veto_total": round(float(confidence_penalty_soft_veto_total), 6),
                "confidence_penalty_soft_veto_reasons": list(confidence_penalty_soft_veto_reasons),
                "gates_failed": list(dict.fromkeys(execution_blockers)),
                "exec_allowed": bool(intent["execution_allowed"]),
            }
            if non_live_relaxed_gate_codes:
                decision_trace["non_live_relaxed_gate_codes"] = list(
                    dict.fromkeys(str(code) for code in non_live_relaxed_gate_codes if str(code))
                )
            if relaxed_trade_score_gate:
                decision_trace["trade_score_gate_relaxed"] = {
                    "score": float(score),
                    "min_score": float(min_score),
                    "mode": str(getattr(market_ctx, "mode", "") or exec_mode).upper(),
                }
            if "stale_option_quote" in advisory_flags:
                decision_trace["score_penalties"] = [
                    p
                    for p in decision_trace.get("score_penalties", [])
                    if str(p.get("name") or "") != "stale_option_quote"
                ]
                decision_trace["soft_vetos"] = [
                    v
                    for v in decision_trace.get("soft_vetos", [])
                    if str(v or "") != "stale_option_quote"
                ]
                decision_trace["warnings"] = [
                    v
                    for v in decision_trace.get("warnings", [])
                    if str(v or "") != "stale_option_quote"
                ]
            source_flags["decision_trace"] = decision_trace
            source_flags.update(
                {
                    "price_source": opt.get("price_source") or opt.get("quote_source"),
                    "entry_price_source": entry_price_source,
                    "expected_entry_source": entry_price_source,
                    "quote_age_sec": opt.get("quote_age_sec"),
                    "best_bid": opt.get("best_bid", opt.get("bid")),
                    "best_ask": opt.get("best_ask", opt.get("ask")),
                    "mid_price": opt.get("mid_price"),
                    "mark_price": opt.get("mark_price", opt.get("ltp")),
                    "entry_price_proxy": base_entry_price,
                }
            )
            quote_ts_epoch = self._coerce_nonnegative_float(
                opt.get("quote_ts_epoch")
                or opt.get("option_ltp_timestamp")
                or opt.get("quote_timestamp_epoch")
                or opt.get("timestamp_epoch")
                or opt.get("ts_epoch")
                or market_data.get("quote_ts_epoch")
                or market_data.get("quote_timestamp_epoch")
                or market_data.get("timestamp_epoch")
                or market_data.get("ts_epoch")
            )
            quote_age_sec = self._coerce_nonnegative_float(
                opt.get("quote_age_sec")
                or opt.get("option_age_sec")
                or opt.get("price_age_sec")
                or opt.get("option_ltp_age_sec")
                or market_data.get("quote_age_sec")
            )
            if quote_ts_epoch is None and quote_age_sec is not None:
                quote_ts_epoch = max(0.0, float(now_utc_epoch()) - float(quote_age_sec))
            if quote_age_sec is None and quote_ts_epoch is not None:
                quote_age_sec = max(0.0, float(now_utc_epoch()) - float(quote_ts_epoch))
            quote_source = ""
            if opt.get("best_bid") is not None or opt.get("best_ask") is not None:
                quote_source = "option_chain_live"
            elif bool(opt.get("quote_ok", True)) and (
                opt.get("ltp") is not None or opt.get("last_price") is not None
            ):
                quote_source = "option_chain_live"
            if not quote_source:
                quote_source = str(
                    opt.get("quote_source")
                    or opt.get("option_ltp_source")
                    or opt.get("price_source")
                    or ""
                ).strip()
            if not quote_source:
                if opt.get("mark_price") is not None:
                    quote_source = "mark"
                elif opt.get("ltp") is not None:
                    quote_source = "last"
                else:
                    quote_source = "unknown"
            option_ltp_source = str(
                opt.get("option_ltp_source")
                or opt.get("quote_source")
                or quote_source
                or ""
            ).strip()
            if not option_ltp_source or quote_source == "option_chain_live":
                option_ltp_source = "option_chain_live" if quote_source == "option_chain_live" else option_ltp_source
            quote_truth_snapshot = {
                "quote_snapshot_id": str(
                    f"{symbol}|{tradingsymbol}|{quote_ts_epoch if quote_ts_epoch is not None else 'na'}|"
                    f"{quote_source}|{opt.get('ltp') if opt.get('ltp') is not None else 'na'}|"
                    f"{opt.get('best_bid') if opt.get('best_bid') is not None else opt.get('bid', 'na')}|"
                    f"{opt.get('best_ask') if opt.get('best_ask') is not None else opt.get('ask', 'na')}"
                ),
                "quote_ts_epoch": quote_ts_epoch,
                "quote_age_sec": quote_age_sec,
                "best_bid": self._coerce_nonnegative_float(opt.get("best_bid", opt.get("bid"))),
                "best_ask": self._coerce_nonnegative_float(opt.get("best_ask", opt.get("ask"))),
                "current_ltp": self._coerce_nonnegative_float(opt.get("ltp") or opt.get("last_price")),
                "option_ltp_source": option_ltp_source or None,
                "quote_source": quote_source or None,
                "quote_validation_status": resolve_quote_validation_status(
                    existing_status=opt.get("quote_validation_status"),
                    current_ltp=self._coerce_nonnegative_float(opt.get("ltp") or opt.get("last_price")),
                    quote_age_sec=quote_age_sec,
                    best_bid=self._coerce_nonnegative_float(opt.get("best_bid", opt.get("bid"))),
                    best_ask=self._coerce_nonnegative_float(opt.get("best_ask", opt.get("ask"))),
                    max_quote_age_sec=getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0),
                ),
                "execution_entry": self._coerce_nonnegative_float(opt.get("quote_execution_entry") or opt.get("execution_entry")),
                "execution_entry_status": str(opt.get("execution_entry_status") or "").strip().lower() or None,
            }
            source_flags["quote_truth"] = dict(quote_truth_snapshot)
            source_flags["quote_truth_snapshot"] = dict(quote_truth_snapshot)

            # Phase 2: Inject AlphaDecayState telemetry
            if candidate_strategy_tag == "volatility_trend":
                init_edge = float(signal.get("initial_predicted_edge", 0.0))
                hold_sec = int(signal.get("expected_holding_period", 300))
                decay_state = AlphaDecayState(
                    initial_edge_bps=init_edge,
                    current_edge_bps=init_edge,
                    holding_time_sec=0,
                    expected_holding_time_sec=hold_sec,
                    execution_cost_bps=5.0
                )
                source_flags["alpha_decay_state"] = decay_state.__dict__

            trade = Trade(
                trade_id=(
                    f"{symbol}-{expiry_resolved}-{int(float(opt['strike']))}-{option_right}-"
                    f"{str(setup_family).replace(' ', '_')}-{int(datetime.now().timestamp())}"
                ),
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=option_right,
                instrument_id=instrument_id,
                instrument_token=instrument_token,
                strike=opt["strike"],
                expiry=expiry_resolved,
                expiry_date=expiry_resolved,
                tradingsymbol=tradingsymbol,
                option_type=option_right,
                side="BUY",
                entry_price=round(entry_price, 2),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                entry_price_proxy=round(float(base_entry_price), 4) if base_entry_price is not None else None,
                stop_price=round(stop_loss, 2),
                target_price=round(target, 2),
                price_source=opt.get("price_source") or opt.get("quote_source"),
                quote_age_sec=opt.get("quote_age_sec"),
                best_bid=opt.get("best_bid", opt.get("bid")),
                best_ask=opt.get("best_ask", opt.get("ask")),
                mark_price=opt.get("mark_price", opt.get("ltp")),
                qty=1,
                qty_lots=1,
                qty_units=qty_units,
                validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
                capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
                expected_slippage=round(slippage, 2),
                confidence=round(confidence, 3),
                strategy=candidate_strategy_tag,
                regime=market_data.get("regime", "NEUTRAL"),
                tier=tier,
                day_type=market_data.get("day_type", "UNKNOWN"),
                entry_condition=entry_condition,
                entry_ref_price=entry_ref_price,
                signal_price=self._option_signal_price(opt, market_data),
                entry_price_source=entry_price_source,
                expected_entry=round(entry_price, 2),
                expected_entry_source=entry_price_source,
                opt_ltp=opt.get("ltp"),
                opt_bid=opt.get("bid"),
                opt_ask=opt.get("ask"),
                **self._option_liquidity_fields(opt),
                quote_ok=opt.get("quote_ok", True),
                trade_score=round(score, 2),
                trade_alignment=round(score_pack.get("alignment", 0), 2),
                trade_score_detail=score_pack,
                model_type=model_type,
                model_version=model_version,
                shadow_model_version=shadow_version,
                shadow_confidence=shadow_confidence,
                alpha_confidence=alpha_conf,
                alpha_uncertainty=alpha_unc,
                size_mult=size_mult,
                tradable=bool(intent["tradable"]),
                tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                planning_only=bool(intent["planning_only"]),
                execution_allowed=bool(intent["execution_allowed"]),
                reason=intent["execution_reason"],
                source_flags=source_flags,
                underlying_spot=underlying_spot,
                spot_source=spot_source,
                option_ltp_source=opt.get("option_ltp_source") or opt.get("quote_source"),
                chain_source=market_data.get("chain_source") or opt.get("chain_source"),
                direction=direction,
                **self._staged_confidence_payload(
                    confidence=confidence,
                    model_raw=confidence_model_raw,
                    model_component=confidence_model_component,
                    micro_component=confidence_micro_component,
                    micro_blend_method=confidence_micro_blend_method,
                    after_micro=confidence_after_micro,
                    after_alpha=confidence_after_alpha,
                    after_latency=confidence_after_latency,
                    before_soft_veto=confidence_before_soft_veto,
                    after_soft_veto=confidence_after_soft_veto,
                    penalty_soft_veto_total=confidence_penalty_soft_veto_total,
                    penalty_soft_veto_reasons=confidence_penalty_soft_veto_reasons,
                    gate_threshold=final_gate_threshold,
                    raw_gate_threshold=raw_gate_threshold,
                    final_gate_threshold=final_gate_threshold,
                    rejection_stage=None,
                    base=confidence_base,
                    penalty_total=confidence_penalty_total,
                    penalty_reasons=confidence_penalty_reasons,
                    use_confidence_as_model=confidence_model_component is not None,
                    ml_model_name=model_type,
                    ml_model_version=model_version,
                ),
            )
            trade = self._decorate_trade_context(trade, market_data, confidence)
            if trade is not None:
                try:
                    loop_quote_truth_snapshot = self._stamp_quote_truth_snapshot(
                        trade,
                        market_data=market_data,
                        source_flags=dict(getattr(trade, "source_flags", {}) or {}),
                        lifecycle=None,
                    )
                    loop_flags = dict(getattr(trade, "source_flags", {}) or {})
                    loop_flags["quote_truth"] = dict(loop_quote_truth_snapshot)
                    loop_flags["quote_truth_snapshot"] = dict(loop_quote_truth_snapshot)
                    trade = replace(trade, source_flags=loop_flags)
                except Exception:
                    pass
                candidate_key = (
                    str(trade.instrument_id or ""),
                    str(trade.expiry or ""),
                    str(trade.right or trade.option_type or ""),
                    str(candidate_origin.get("setup_family") or ""),
                    str(candidate_origin.get("expiry_bucket") or ""),
                    candidate_origin.get("strike_offset"),
                )
                if candidate_key in candidate_seen_keys:
                    continue
                candidate_seen_keys.add(candidate_key)
                candidates.append(trade)

        if debug_reasons and rejected:
            self._write_rejected(rejected)
        if debug_mode:
            top_n = getattr(cfg, "DEBUG_TRADE_TOP_N", 5)
            pool = rejected if rejected else debug_candidates
            if pool:
                self._write_debug_candidates(pool, top_n=top_n)
        candidates = self._inject_option_scan_min_survivors(
            symbol=symbol,
            market_data=market_data,
            execution_mode=exec_mode,
            candidates=candidates,
            rejected=rejected,
            strategy_tag=candidate_strategy_tag,
            direction=direction,
        )
        option_reject_total = int(sum(option_reject_counts.values()))
        top_rejects: dict[str, int] = {}
        if option_reject_counts:
            ordered = sorted(
                option_reject_counts.items(),
                key=lambda item: (-int(item[1]), str(item[0])),
            )
            top_rejects = {str(code): int(count) for code, count in ordered[:8]}
        self._last_option_scan_summary = {
            "symbol": symbol,
            "considered": option_rows_considered,
            "survivors": len(candidates),
            "option_reject_total": option_reject_total,
            "top_rejects": top_rejects,
        }
        self._option_scan_summary_emitted = False
        if debug_mode and len(candidates) <= 1:
            logger.info(
                "TB_REJECT_SUMMARY %s",
                {
                    "symbol": symbol,
                    "total_candidates": int(option_rows_considered),
                    "survived": int(len(candidates)),
                    "survived_candidates": int(len(candidates)),
                    "reject_counts": {
                        str(code): int(count)
                        for code, count in sorted(
                            (self._scan_reject_counts or {}).items(),
                            key=lambda item: (-int(item[1]), str(item[0])),
                        )
                        if str(code)
                    },
                },
            )
        if premium_band_fail_count:
            logger.info(
                "PREMIUM_BAND_FAIL_SUMMARY symbol=%s premium_band_fail_count=%s samples=%s",
                symbol,
                premium_band_fail_count,
                premium_band_fail_samples if premium_band_fail_samples else None,
            )
        if not candidates and debug_reasons and debug_candidates:
            # show top 3 closest candidates by premium (proxy)
            top = sorted(debug_candidates, key=lambda x: x.get("ltp", 0) or 0, reverse=True)[:3]
            for rec in top:
                _log_option_chain_debug(
                    "trade_builder_top_candidate_rejected symbol=%s strike=%s type=%s reason=%s ltp=%s",
                    symbol,
                    rec.get("strike"),
                    rec.get("type"),
                    rec.get("reason"),
                    rec.get("ltp"),
                )

            if not candidates:
                if not allow_fallbacks:
                    summary = _option_reject_summary()
                    self._log_blocked_candidate(
                        symbol,
                        "no_viable_candidates",
                        "No viable trade candidates and fallback path disabled",
                        market_data=market_data,
                        extra=summary,
                    )
                    self._reject_exit(market_data, "no_viable_candidates")
                    reject_reason_ctx = str((self._reject_ctx or {}).get("reason") or "").lower()
                    if not (
                        exec_mode in {"SIM", "PAPER"}
                        and reject_reason_ctx in {"trend_vwap_fallback"}
                    ):
                        if allow_fallbacks:
                            softened = self._soften_reject_to_candidate(
                                market_data=market_data,
                                reject_ctx=dict(self._reject_ctx or {}),
                                strategy_tag=candidate_strategy_tag,
                                direction=direction,
                            )
                            if softened is not None:
                                return softened
                    return None
            # Quick fallback: synthesize ATM option if chain is empty
            if quick_mode:
                if strict_live_market_open and market_data.get("chain_source") != "live":
                    self._log_blocked_candidate(
                        symbol,
                        "non_live_option_chain",
                        "Quick fallback blocked because option chain is not live",
                        market_data=market_data,
                        extra={"chain_source": market_data.get("chain_source")},
                    )
                    return None
                try:
                    if not spot_ok:
                        self._log_blocked_candidate(
                            symbol,
                            "unresolved_contract",
                            f"Underlying spot missing or stale ({spot_issue})",
                            market_data=market_data,
                            extra={
                                "underlying_spot": underlying_spot,
                                "spot_source": spot_source,
                                "skip_derived_levels": True,
                            },
                        )
                        return None
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {})
                    step = step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50))
                    atm_strike = int(round(float(underlying_spot) / step) * step) if step else 0
                    expiry_resolved = self._resolve_expiry_for_symbol(symbol, market_data)
                    contract = self._resolve_option_contract(
                        symbol,
                        atm_strike,
                        opt_type,
                        expiry_resolved,
                        market_data,
                    )
                    expiry_resolved = contract.get("expiry") or expiry_resolved
                    tradingsymbol = contract.get("tradingsymbol")
                    instrument_token = contract.get("instrument_token")
                    instrument_id = contract.get("instrument_id")
                    instrument_type, _, qty_units, ident_err = self._identity_fields(
                        symbol,
                        "OPT",
                        expiry_resolved,
                        atm_strike,
                        opt_type,
                        1,
                    )
                    if ident_err or not expiry_resolved or not tradingsymbol or not instrument_id:
                        self._log_blocked_candidate(
                            symbol,
                            "unresolved_contract",
                            "Option contract could not be resolved",
                            market_data=market_data,
                            extra={
                                "strike": atm_strike,
                                "option_type": opt_type,
                                "expiry": expiry_resolved,
                                "expiry_date": expiry_resolved,
                                "tradingsymbol": tradingsymbol,
                                "instrument_token": instrument_token,
                                "underlying_spot": underlying_spot,
                                "spot_source": spot_source,
                                "skip_derived_levels": True,
                            },
                        )
                        if debug_reasons:
                            rec = self._reject_record(symbol, {"strike": atm_strike}, opt_type, "unresolved_contract", atr=atr)
                            rejected.append(rec)
                        return None
                    band_map = getattr(cfg, "PREMIUM_BANDS", {})
                    band = band_map.get(symbol, (getattr(cfg, "MIN_PREMIUM", 40), getattr(cfg, "MAX_PREMIUM", 150)))
                    min_p, max_p = band
                    ltp_opt = max(min_p, min(max_p, float(underlying_spot) * 0.004))
                    bid = round(ltp_opt * 0.995, 2)
                    ask = round(ltp_opt * 1.005, 2)
                    mark_price = round((bid + ask) / 2.0, 2)
                    synthetic_opt = {
                        "bid": bid,
                        "ask": ask,
                        "ltp": mark_price,
                        "last_price": mark_price,
                        "quote_ok": True,
                        "quote_live": True,
                        "volume": 1000,
                        "spread_pct": ((ask - bid) / mark_price) if mark_price else None,
                    }
                    slippage = self.execution.estimate_slippage(bid, ask, 1000)
                    entry_price = (ask if ask > 0 else mark_price) + slippage
                    entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                        entry_price, side="BUY", quick_mode=True
                    )
                    option_risk = self._option_risk_proxy(entry_price, bid, ask)
                    stop_loss, target = self._opt_risk_levels(
                        entry_price, bid, ask, option_risk, stop_mult=1.0, target_mult=1.5
                    )
                    if not (target > entry_price > stop_loss):
                        logger.error(
                            "invalid_opt_levels symbol=%s side=%s entry=%s stop=%s target=%s strike=%s right=%s",
                            symbol,
                            "BUY",
                            entry_price,
                            stop_loss,
                            target,
                            atm_strike,
                            opt_type,
                        )
                        return None
                    synthetic_offhours_seed = not bool(market_data.get("market_open", True)) or str(
                        ((market_data.get("market_context") or {}).get("mode") or "")
                    ).strip().upper() == "OFFHOURS"
                    extra_blockers = []
                    if instrument_token is None:
                        extra_blockers.append("instrument_token_missing")
                    intent_opt = {
                        "quote_ok": True,
                    }
                    if synthetic_offhours_seed:
                        intent_opt.update(
                            {
                                "option_ltp_source": "synthetic_offhours",
                                "quote_source": "synthetic_offhours",
                            }
                        )
                    intent = self.trade_intent_flags(
                        market_data,
                        opt=intent_opt,
                        additional_blockers=extra_blockers,
                    )
                    quick_final_gate_threshold = self._final_confidence_gate_threshold("NEUTRAL", quick_mode=True)
                    quick_raw_gate_threshold = self._raw_confidence_gate_threshold("NEUTRAL", quick_mode=True)
                    synthetic_confidence = float(max(0.5, quick_final_gate_threshold))
                    trade = Trade(
                        trade_id=f"{symbol}-{opt_type}-ATM-QK-{ts}",
                        timestamp=datetime.now(),
                        symbol=symbol,
                        instrument="OPT",
                        instrument_type=instrument_type,
                        right=opt_type,
                        instrument_id=instrument_id,
                        instrument_token=instrument_token,
                        strike=atm_strike,
                        expiry=expiry_resolved,
                        expiry_date=expiry_resolved,
                        tradingsymbol=tradingsymbol,
                        option_type=opt_type,
                        side="BUY",
                        entry_price=round(entry_price, 2),
                        stop_loss=round(stop_loss, 2),
                        target=round(target, 2),
                        qty=1,
                        qty_lots=1,
                        qty_units=qty_units,
                        validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
                        capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
                        expected_slippage=round(slippage, 2),
                        confidence=round(synthetic_confidence, 3),
                        strategy="QUICK_SYNTH",
                        regime=market_data.get("regime", "NEUTRAL"),
                        tier="EXPLORATION",
                        day_type=market_data.get("day_type", "UNKNOWN"),
                        signal_price=None,
                        entry_price_source="ask",
                        expected_entry=round(entry_price, 2),
                        expected_entry_source="ask",
                        **self._option_liquidity_fields(synthetic_opt),
                        entry_condition=entry_condition,
                        entry_ref_price=entry_ref_price,
                        alpha_confidence=None,
                        alpha_uncertainty=None,
                        size_mult=1.0,
                        tradable=bool(intent["tradable"]),
                        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                        planning_only=bool(intent["planning_only"]),
                        execution_allowed=bool(intent["execution_allowed"]),
                        reason=intent["execution_reason"],
                        source_flags=dict(intent["source_flags"]),
                        underlying_spot=underlying_spot,
                        spot_source=spot_source,
                        option_ltp_source="synthetic_offhours" if synthetic_offhours_seed else None,
                        chain_source=market_data.get("chain_source") or "synthetic",
                        **self._staged_confidence_payload(
                            confidence=synthetic_confidence,
                            model_raw=synthetic_confidence,
                            model_component=synthetic_confidence,
                            micro_blend_method="model_only",
                            before_soft_veto=synthetic_confidence,
                            after_soft_veto=synthetic_confidence,
                            penalty_soft_veto_total=0.0,
                            penalty_soft_veto_reasons=[],
                            gate_threshold=quick_final_gate_threshold,
                            raw_gate_threshold=quick_raw_gate_threshold,
                            final_gate_threshold=quick_final_gate_threshold,
                            base=synthetic_confidence,
                            penalty_total=0.0,
                            penalty_reasons=[],
                        ),
                    )
                    trade = self._decorate_trade_context(
                        trade,
                        market_data,
                        synthetic_confidence,
                    )
                    return trade
                except Exception:
                    pass
            # Futures/equity path
            if instrument in ("FUT", "EQ"):
                atr = market_data.get("atr", max(1.0, ltp * 0.002))
                vwap_dist = (ltp - vwap) / vwap if vwap else 0
                base_conf = min(0.8, max(0.5, 0.5 + abs(vwap_dist) * 10))
                strat_name = "FUT_TREND" if instrument == "FUT" else "EQ_TREND"
                allowed, adj_score, decay_size_mult, _ = self._apply_decay_gate(strat_name, base_conf, 1.0)
                if not allowed:
                    self._log_blocked_candidate(
                        symbol,
                        "strategy_quarantined",
                        "Strategy decay gate quarantined strategy",
                        market_data=market_data,
                        extra={"strategy": strat_name},
                    )
                    if debug_reasons:
                        _log_advisory_debug("trade_builder_strategy_quarantine symbol=%s strategy=%s", symbol, strat_name)
                    return None
                if adj_score is not None:
                    base_conf = adj_score
                side = "BUY" if direction == "BUY_CALL" else "SELL"
                stop_loss = ltp - atr if side == "BUY" else ltp + atr
                target = ltp + atr * 1.5 if side == "BUY" else ltp - atr * 1.5

                instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                    symbol,
                    instrument,
                    getattr(cfg, "FUT_EXPIRY", ""),
                    None,
                    None,
                    1,
                )
                if ident_err:
                    self._log_blocked_candidate(
                        symbol,
                        "missing_contract_fields",
                        str(ident_err),
                        market_data=market_data,
                        extra={"instrument": instrument},
                    )
                    if debug_reasons:
                        _log_advisory_debug("trade_builder_identity_reject symbol=%s instrument=%s reason=%s", symbol, instrument, ident_err)
                    return None
                intent = self.trade_intent_flags(
                    market_data,
                    opt={
                        "quote_ok": bool(market_data.get("quote_ok", True)),
                        "quote_age_sec": market_data.get("quote_age_sec"),
                    },
                )
                final_gate_threshold = self._final_confidence_gate_threshold(
                    market_data.get("regime"),
                    quick_mode=quick_mode,
                )
                trade = Trade(
                    trade_id=f"{symbol}-FUT-{int(datetime.now().timestamp())}",
                    timestamp=datetime.now(),
                    symbol=symbol,
                    instrument=instrument,
                    instrument_type=instrument_type,
                    instrument_id=instrument_id,
                    instrument_token=None,
                    strike=0,
                    expiry=str(getattr(cfg, "FUT_EXPIRY", "")),
                    side=side,
                    entry_price=round(ltp, 2),
                    stop_loss=round(stop_loss, 2),
                    target=round(target, 2),
                    qty=1,
                    qty_lots=1,
                    qty_units=qty_units,
                    validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
                    capital_at_risk=round(abs(ltp - stop_loss), 2),
                    expected_slippage=0.0,
                    confidence=round(base_conf, 3),
                    strategy=strat_name,
                    regime=market_data.get("regime", "NEUTRAL"),
                    tier="MAIN",
                    day_type=market_data.get("day_type", "UNKNOWN"),
                    alpha_confidence=None,
                    alpha_uncertainty=None,
                    size_mult=decay_size_mult,
                    tradable=bool(intent["tradable"]),
                    tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                    planning_only=bool(intent["planning_only"]),
                    execution_allowed=bool(intent["execution_allowed"]),
                    reason=intent["execution_reason"],
                    source_flags=dict(intent["source_flags"]),
                    **self._staged_confidence_payload(
                        confidence=base_conf,
                        model_raw=base_conf,
                        model_component=base_conf,
                        micro_blend_method="model_only",
                        before_soft_veto=base_conf,
                        after_soft_veto=base_conf,
                        penalty_soft_veto_total=0.0,
                        penalty_soft_veto_reasons=[],
                        gate_threshold=final_gate_threshold,
                        final_gate_threshold=final_gate_threshold,
                        base=base_conf,
                        penalty_total=0.0,
                        penalty_reasons=[],
                    ),
                )
                trade = self._decorate_trade_context(trade, market_data, base_conf)
                if trade is None:
                    return self._reject_exit(market_data, "decorate_trade_context_failed")
                if trade.confidence >= final_gate_threshold:
                    return trade
                self._log_blocked_candidate(
                    symbol,
                    "confidence_final_gate",
                    "Trade final confidence below configured threshold",
                    market_data=market_data,
                    extra={
                        "confidence": trade.confidence,
                        "min_confidence": final_gate_threshold,
                        "confidence_stage": "final",
                    },
                )
                if debug_reasons:
                    _log_advisory_debug("trade_builder_low_confidence symbol=%s instrument=%s stage=final", symbol, instrument)
                return self._reject_exit(market_data, "confidence_final_gate")
            self._log_blocked_candidate(
                symbol,
                "no_viable_candidates",
                "No viable trade candidates after all filters",
                market_data=market_data,
                extra=_option_reject_summary(),
            )
            self._reject_exit(market_data, "no_viable_candidates")
            reject_reason_ctx = str((self._reject_ctx or {}).get("reason") or "").lower()
            if not (
                exec_mode in {"SIM", "PAPER", "OFFHOURS"}
                and reject_reason_ctx == "trend_vwap_fallback"
            ):
                if allow_fallbacks:
                    softened = self._soften_reject_to_candidate(
                        market_data=market_data,
                        reject_ctx=dict(self._reject_ctx or {}),
                        strategy_tag=candidate_strategy_tag,
                        direction=direction,
                    )
                    if softened is not None:
                        return softened
            return None

        best_trade, ranked_candidates = select_best_opportunity(
            candidates,
            scope=f"build:{symbol}:{candidate_strategy_tag}",
            top_n=int(getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)),
        )
        self._set_last_ranked_candidates(ranked_candidates)
        if best_trade is not None:
            try:
                best_trade_source_flags = dict(getattr(best_trade, "source_flags", {}) or {})
                if not isinstance(best_trade_source_flags.get("quote_truth"), dict):
                    quote_truth_snapshot = self._stamp_quote_truth_snapshot(
                        best_trade,
                        market_data=market_data,
                        source_flags=best_trade_source_flags,
                        lifecycle=None,
                    )
                    best_trade_source_flags = dict(getattr(best_trade, "source_flags", {}) or {})
                    best_trade_source_flags["quote_truth"] = dict(quote_truth_snapshot)
                    best_trade_source_flags["quote_truth_snapshot"] = dict(quote_truth_snapshot)
                    try:
                        object.__setattr__(best_trade, "source_flags", best_trade_source_flags)
                    except Exception:
                        pass
            except Exception:
                pass
        if best_trade is None:
            # Real fallback must happen inside build(), not only in build_with_trace().
            if best_trade is None and ranked_candidates and allow_fallbacks:
                fallback_allowed_modes = {"SIM", "PAPER"}
                current_mode = str(
                    getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))
                ).upper()
                reject_reason = str((self._reject_ctx or {}).get("reason") or "").strip().lower()
                critical_no_fallback = {
                    "invalid_snapshot",
                    "unresolved_contract",
                    "missing_instrument_id",
                    "missing_contract_fields",
                    "missing_live_bidask",
                    "no_option_quote_source",
                    "no_option_quote",
                }
                if current_mode in fallback_allowed_modes and reject_reason not in critical_no_fallback:
                    try:
                        top_ranked = ranked_candidates[0]
                    except Exception:
                        top_ranked = None
                    if top_ranked is not None:
                        fallback_reason = (
                            "no_signal_top_ranked_fallback"
                            if reject_reason == "no_signal"
                            else "no_viable_candidates_top_ranked"
                        )
                        best_trade = self._apply_fallback_candidate_flags(
                            top_ranked,
                            reason=fallback_reason,
                            execution_allowed_override=False,
                            planning_only_override=True,
                            tradable_override=False,
                        )
                        best_trade = self._apply_candidate_contract(best_trade, market_data=market_data)
                        if isinstance(best_trade, dict):
                            best_trade["selected_for_execution"] = False
                            best_trade["selection_reason"] = "fallback_top_ranked"
                        else:
                            best_trade = replace(
                                best_trade,
                                selected_for_execution=False,
                                selection_reason="fallback_top_ranked",
                            )
                        logger.info(
                            "FALLBACK_TOP_RANKED_SELECTED symbol=%s trade_id=%s rank_score=%s",
                            symbol,
                            getattr(best_trade, "trade_id", None)
                            if not isinstance(best_trade, dict)
                            else best_trade.get("trade_id"),
                            getattr(best_trade, "rank_score", None)
                            if not isinstance(best_trade, dict)
                            else best_trade.get("rank_score"),
                        )
                        # terminal reject reason must not remain as no-trade once fallback is selected
                        self._reject_ctx = {}
            elif best_trade is None:
                current_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
                reject_reason = str((self._reject_ctx or {}).get("reason") or "").strip().lower()
                option_rows_considered = int((getattr(self, "_last_option_scan_summary", {}) or {}).get("considered") or 0)
                if current_mode in {"SIM", "PAPER"} and reject_reason not in {"trend_vwap_fallback"} and option_rows_considered > 0:
                    hard_trace_blockers = {
                        "unresolved_contract",
                        "missing_contract_fields",
                        "missing_instrument_id",
                        "missing_live_bidask",
                        "no_option_quote_source",
                        "no_option_quote",
                    }
                    if reject_reason in hard_trace_blockers:
                        best_trade = None
                    else:
                        try:
                            top_ranked = (self._last_ranked_candidates or [None])[0]
                        except Exception:
                            top_ranked = None
                        if top_ranked is not None and allow_fallbacks:
                            best_trade = self._soften_reject_to_candidate(
                                market_data=market_data or {},
                                reject_ctx=dict(self._reject_ctx or {}),
                                strategy_tag=strategy_tag,
                                direction=direction,
                            )
                        if best_trade is None and reject_reason not in {"no_candidates_survived", "no_signal"} and allow_fallbacks:
                            fallback_ctx = dict(self._reject_ctx or {})
                            fallback_ctx["reason"] = "no_candidates_survived"
                            best_trade = self._soften_reject_to_candidate(
                                market_data=market_data or {},
                                reject_ctx=fallback_ctx,
                                strategy_tag=strategy_tag,
                                direction=direction,
                            )
                            if best_trade is not None:
                                self._reject_ctx = {}

            if best_trade is None:
                option_reject_total = int(sum(option_reject_counts.values()))
                top_rejects: dict[str, int] = {}
                if option_reject_counts:
                    ordered = sorted(
                        option_reject_counts.items(),
                        key=lambda item: (-int(item[1]), str(item[0])),
                    )
                    top_rejects = {str(code): int(count) for code, count in ordered[:8]}
                logger.info(
                    "OPTION_SCAN_REJECT_SUMMARY symbol=%s considered=%s survivors=%s option_reject_total=%s top_rejects=%s",
                    symbol,
                    option_rows_considered,
                    len(candidates),
                    option_reject_total,
                    top_rejects,
                )
                self._last_option_scan_summary = {
                    "symbol": symbol,
                    "considered": option_rows_considered,
                    "survivors": len(candidates),
                    "option_reject_total": option_reject_total,
                    "top_rejects": top_rejects,
                }
                self._option_scan_summary_emitted = True
                reject_summary = {
                    "option_rows_considered": option_rows_considered,
                    "option_reject_total": option_reject_total,
                    "option_reject_top": top_rejects,
                }
                self._reject_exit(
                    market_data,
                    "no_viable_candidates" if ranked_candidates else "no_candidates_survived",
                    extra={
                        "symbol": symbol,
                        "gate_reasons": list(self._scan_reject_counts.keys()),
                        **reject_summary,
                    },
                )

            self._scan_accepted = int(len(ranked_candidates))
            return best_trade

        # Persist decision traces for all retained candidates (selected and non-selected).
        for cand in ranked_candidates:
            try:
                sf = dict(getattr(cand, "source_flags", {}) or {})
                decision_trace = dict(sf.get("decision_trace", {}) or {})
                gates_failed = list(dict.fromkeys(sf.get("gates_failed") or getattr(cand, "tradable_reasons_blocking", []) or []))
                soft_vetos = list(dict.fromkeys(sf.get("soft_veto_codes") or []))
                liquidity_flow_score = self._candidate_telemetry_field(cand, sf, decision_trace, "liquidity_flow_score")
                liquidity_book_score = self._candidate_telemetry_field(cand, sf, decision_trace, "liquidity_book_score")
                liquidity_spread_score = self._candidate_telemetry_field(cand, sf, decision_trace, "liquidity_spread_score")
                liquidity_volume_score = self._candidate_telemetry_field(cand, sf, decision_trace, "liquidity_volume_score")
                liquidity_oi_score = self._candidate_telemetry_field(cand, sf, decision_trace, "liquidity_oi_score")
                setup_telemetry_fields = self._setup_telemetry_fields(
                    cand,
                    sf,
                    decision_trace,
                    candidate_quality_score=getattr(cand, "opportunity_score", None),
                    trigger_base_score=decision_trace.get("trigger_base_score"),
                    invalidation_score=decision_trace.get("invalidation_score"),
                    overextension_score=decision_trace.get("overextension_score"),
                    timing_quality_score=decision_trace.get("timing_quality"),
                )
                record_candidate_decision(
                    {
                        "candidate_id": getattr(cand, "trade_id", None),
                        "ts_epoch": now_utc_epoch(),
                        "symbol": getattr(cand, "symbol", symbol),
                        "side": getattr(cand, "direction", direction),
                        "entry": getattr(cand, "entry_price", None),
                        "stop": getattr(cand, "stop_loss", None),
                        "target": getattr(cand, "target", None),
                        "regime": getattr(cand, "regime", market_data.get("regime")),
                        "confidence_score": getattr(cand, "confidence", None),
                        "gates_failed": gates_failed,
                        "soft_vetos": soft_vetos,
                        "first_blocking_gate": gates_failed[0] if gates_failed else None,
                        "hard_reject_reason": None,
                        "execution_allowed": bool(getattr(cand, "execution_allowed", False)),
                        "mode": market_ctx.mode,
                        "instrument_id": getattr(cand, "instrument_id", None),
                        "expiry": getattr(cand, "expiry", None),
                        "initial_score": decision_trace.get("initial_score"),
                        "final_score": decision_trace.get("final_score", getattr(cand, "trade_score", None)),
                        "score_penalties": decision_trace.get("score_penalties", []),
                        "signal_score": decision_trace.get("signal_score"),
                        "regime_conf": decision_trace.get("regime_conf"),
                        "orb_bias": decision_trace.get("orb_bias"),
                        "orb_factor": decision_trace.get("orb_factor"),
                        "reg_penalty": decision_trace.get("reg_penalty"),
                        "global_conf": decision_trace.get("global_conf"),
                        "builder_confidence": getattr(cand, "builder_confidence", None),
                        "permission_confidence": getattr(cand, "permission_confidence", None),
                        "gating_final_confidence": getattr(cand, "gating_final_confidence", None),
                        "liquidity_score": getattr(cand, "liquidity_score", None),
                        "quote_consistency_score": getattr(cand, "quote_consistency_score", None),
                        "quote_validation_status": getattr(cand, "quote_validation_status", None),
                        "liquidity_flow_score": liquidity_flow_score,
                        "liquidity_book_score": liquidity_book_score,
                        "liquidity_spread_score": liquidity_spread_score,
                        "liquidity_volume_score": liquidity_volume_score,
                        "liquidity_oi_score": liquidity_oi_score,
                        **setup_telemetry_fields,
                        "rank_score": getattr(cand, "rank_score", None),
                        "raw_rank_score": getattr(cand, "raw_rank_score", None),
                        "terminal_rank_score": getattr(cand, "terminal_rank_score", None),
                        "opportunity_score": getattr(cand, "opportunity_score", None),
                        "opportunity_rank": getattr(cand, "opportunity_rank", None),
                        "rank_global": getattr(cand, "rank_global", None),
                        "rank_within_symbol": getattr(cand, "rank_within_symbol", None),
                        "opportunity_bucket": getattr(cand, "opportunity_bucket", None),
                        "selected_for_execution": getattr(cand, "selected_for_execution", None),
                        "selection_reason": getattr(cand, "selection_reason", None),
                        "size_multiplier_reason": getattr(cand, "size_multiplier_reason", None),
                        "candidate_origin": (getattr(cand, "source_flags", {}) or {}).get("candidate_origin"),
                        "permission": decision_trace.get("permission"),
                        "permission_reason": decision_trace.get("permission_reason"),
                        "entry_status": decision_trace.get("entry_status"),
                        "entry_block_reason": decision_trace.get("entry_block_reason"),
                        "final_action": decision_trace.get("final_action"),
                        "ltp": market_data.get("ltp"),
                        "atr": market_data.get("atr"),
                    }
                )
                append_trade_lifecycle_event(
                    trade_id=str(getattr(cand, "trade_id", None)),
                    symbol=str(getattr(cand, "symbol", symbol) or ""),
                    strategy=str(getattr(cand, "strategy", "") or ""),
                    stage="scoring_ranking",
                    status="selected" if bool(getattr(cand, "selected_for_execution", False)) else "skipped",
                    reason=str(getattr(cand, "selection_reason", None) or "rank_below_cutoff"),
                    extra={
                        "opportunity_score": getattr(cand, "opportunity_score", None),
                        "opportunity_rank": getattr(cand, "opportunity_rank", None),
                        "rank_global": getattr(cand, "rank_global", None),
                        "rank_within_symbol": getattr(cand, "rank_within_symbol", None),
                        "opportunity_bucket": getattr(cand, "opportunity_bucket", None),
                        "candidate_origin": (getattr(cand, "source_flags", {}) or {}).get("candidate_origin"),
                        "selected_for_execution": bool(getattr(cand, "selected_for_execution", False)),
                    },
                )
            except Exception:
                pass

        self._scan_accepted = int(len(ranked_candidates))
        return best_trade

    def build_with_trace(
        self,
        market_data,
        quick_mode=False,
        debug_reasons=False,
        force_family: str | None = None,
        allow_fallbacks: bool = True,
        allow_baseline: bool = True,
    ):
        self._set_last_ranked_candidates([])
        trade = self.build(
            market_data,
            quick_mode=quick_mode,
            debug_reasons=debug_reasons,
            force_family=force_family,
            allow_fallbacks=allow_fallbacks,
            allow_baseline=allow_baseline,
        )
        if trade is None:
            self._ensure_reject_reason(market_data)
            reject_ctx = dict(self._reject_ctx or {})
            ranked_candidates = list(getattr(self, "_last_ranked_candidates", []) or [])
            strategy_tag = (
                str(
                    reject_ctx.get("strategy")
                    or reject_ctx.get("strategy_name")
                    or reject_ctx.get("strategy_id")
                    or "CORE"
                )
                .strip()
            )
            direction = str(reject_ctx.get("direction") or "UNKNOWN").strip()
            if not ranked_candidates:
                exec_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
                reject_reason_ctx = str(reject_ctx.get("reason") or "").lower()
                if allow_fallbacks and not (
                    exec_mode in {"SIM", "PAPER", "OFFHOURS"}
                    and reject_reason_ctx == "trend_vwap_fallback"
                ):
                    softened = self._soften_reject_to_candidate(
                        market_data=market_data or {},
                        reject_ctx=reject_ctx,
                        strategy_tag=strategy_tag,
                        direction=direction,
                    )
                    if softened is not None:
                        trade = softened
        trace = build_trade_decision_trace(
            market_data=market_data or {},
            trade=trade,
            reject_ctx=dict(self._reject_ctx or {}),
            run_id=(market_data or {}).get("run_id"),
        )

        # PAPER TELEMETRY: Hook OPENING_DRIVE_CONT candidates for option quote validation
        # STRICT GUARD: Only run for PAPER mode and if explicitly enabled.
        try:
            ctx = (market_data or {}).get("market_context")
            ctx_mode = ctx.get("execution_mode") if isinstance(ctx, dict) else ""
            exec_mode = str(
                (market_data or {}).get("execution_mode") or ctx_mode or getattr(cfg, "EXECUTION_MODE", "")
            ).strip().upper()

            paper_telemetry_enabled = bool(getattr(cfg, "PAPER_TELEMETRY_ENABLED", False))
            if exec_mode == "PAPER" and paper_telemetry_enabled:
                sig = self._signal_for_symbol(market_data) or {}
                sig_fam = sig.get("strategy_family", sig.get("family", ""))
                sig_strat = sig.get("strategy", "")

                cand_to_log = trade if trade is not None else dict(self._reject_ctx or {})
                t_fam = getattr(cand_to_log, "strategy_family", getattr(cand_to_log, "family", cand_to_log.get("family", "") if isinstance(cand_to_log, dict) else ""))
                t_strat = getattr(cand_to_log, "strategy", cand_to_log.get("strategy", "") if isinstance(cand_to_log, dict) else "")

                if "OPENING_DRIVE_CONT" not in str(t_strat) and "OPENING_DRIVE_CONT" not in str(t_fam):
                    if "OPENING_DRIVE_CONT" in str(sig_strat) or "OPENING_DRIVE_CONT" in str(sig_fam):
                        cand_to_log = {
                            "strategy": sig_strat,
                            "family": sig_fam,
                            "direction": sig.get("direction", ""),
                            "status": "REJECTED_STALE_QUOTE_OR_SIMILAR",
                            "is_fallback": False,
                            "fallback_used": False,
                            "is_advisory": False,
                            "execution_allowed": False,
                            "candidate_source": "raw_signal_rejection",
                            "rejection_reason": str((self._reject_ctx or {}).get("reason") or "unknown_rejection"),
                            "original_strategy": sig_strat,
                            "replacement_candidate_id": getattr(trade, "trade_id", trade.get("trade_id") if isinstance(trade, dict) else None) if trade else None
                        }
                        t_fam = sig_fam
                        t_strat = sig_strat

                if not t_fam and not t_strat:
                    t_fam = sig_fam
                    t_strat = sig_strat
                    if isinstance(cand_to_log, dict):
                        cand_to_log["strategy"] = t_strat
                        cand_to_log["family"] = t_fam

                if "OPENING_DRIVE_CONT" in str(t_fam) or "OPENING_DRIVE_CONT" in str(t_strat):
                    from core.htf_paper_telemetry import log_htf_opening_drive_paper_candidate
                    log_htf_opening_drive_paper_candidate(cand_to_log if isinstance(cand_to_log, dict) else vars(cand_to_log), market_data)

        except Exception as e:
            import logging
            logging.getLogger("htf_telemetry").warning("Failed to log paper candidate: %s", e)

        return trade, trace

    def build_zero_hero(self, market_data, debug_reasons=False):
        """
        Zero-to-hero (lotto): paper-only, high-convexity ideas.
        Uses OTM strikes (1-2% from ATM) and a dynamic low-premium band (p2-p25).
        """
        stats = self._strategy_candidate_debug(market_data, "zero_to_hero")
        symbol = (market_data or {}).get("symbol") if isinstance(market_data, dict) else None
        self._update_zero_hero_diag(
            market_data,
            activation_window={
                "strategy": "ZERO_TO_HERO",
                "variant": "generic",
                "expiry_day": bool(self._is_expiry_day_for_symbol(str(symbol or ""), market_data)),
                "minutes_since_open": int((market_data or {}).get("minutes_since_open", 0) or 0)
                if isinstance(market_data, dict)
                else 0,
            },
        )
        if not getattr(cfg, "ZERO_TO_HERO_ENABLE", False):
            self._update_strategy_candidate_debug(stats, rejected=1, reason="mode_disabled")
            self._update_zero_hero_diag(market_data, rejected_reason="mode_disabled")
            return None
        exec_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
        allowed_modes = getattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"])
        if isinstance(allowed_modes, str):
            allowed_modes = [s.strip().upper() for s in allowed_modes.split(",") if s.strip()]
        allowed_modes = {str(m).strip().upper() for m in (allowed_modes or ["PAPER"])}
        if exec_mode not in allowed_modes:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="mode_block")
            self._update_zero_hero_diag(market_data, rejected_reason="mode_block")
            if debug_reasons:
                self._log_blocked_candidate(
                    market_data.get("symbol"),
                    "mode_block",
                    "Zero-to-hero blocked: execution mode not allowed",
                    market_data=market_data,
                    extra={"execution_mode": exec_mode, "allowed_modes": sorted(allowed_modes)},
                )
            return None
        exploratory_mode = exec_mode in {"SIM", "PAPER"}

        symbol = market_data.get("symbol")
        if bool(getattr(cfg, "ZERO_HERO_EXPIRY_ENABLE", True)) and self._is_expiry_day_for_symbol(symbol, market_data):
            expiry_trade = self._build_zero_hero_expiry(market_data, debug_reasons=debug_reasons)
            if expiry_trade is not None:
                expiry_trade.source_flags.setdefault("zero_hero_variant", "expiry_day")
                self._update_zero_hero_diag(market_data, clear_rejected_reason=True)
                return expiry_trade
            self._update_zero_hero_diag(
                market_data,
                activation_window={
                    "strategy": "ZERO_TO_HERO",
                    "variant": "generic_fallback",
                    "expiry_day": True,
                    "minutes_since_open": int(market_data.get("minutes_since_open", 0) or 0),
                },
            )
        regime_raw = market_data.get("regime") or market_data.get("primary_regime") or market_data.get("regime_day")
        regime = normalize_regime(regime_raw)
        allowed_regimes = getattr(cfg, "ZERO_TO_HERO_ALLOWED_REGIMES", ["TREND", "EVENT"])
        if isinstance(allowed_regimes, str):
            allowed_regimes = [s.strip().upper() for s in allowed_regimes.split(",") if s.strip()]
        allowed_regimes = {str(r).strip().upper() for r in (allowed_regimes or [])}
        if allowed_regimes and regime not in allowed_regimes:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="regime_block")
            self._update_zero_hero_diag(market_data, rejected_reason="regime_block")
            return None

        if not self._zero_to_hero_daily_ok():
            self._update_strategy_candidate_debug(stats, rejected=1, reason="daily_limit")
            self._update_zero_hero_diag(market_data, rejected_reason="daily_limit")
            return None

        chain = market_data.get("option_chain") or []
        if not chain:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="missing_option_chain")
            self._update_zero_hero_diag(market_data, rejected_reason="missing_option_chain")
            return None

        segment = market_data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        ctx_payload = dict(market_data.get("market_context") or {}) if isinstance(market_data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = exec_mode
        if "market_open" not in ctx_payload:
            ctx_payload["market_open"] = market_data.get("market_open", True)
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = segment
        market_ctx = derive_market_context(ctx_payload)

        underlying_spot, spot_source, spot_ok, spot_issue = self._resolve_underlying_spot(market_data, market_ctx)
        if not spot_ok:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="spot_invalid")
            self._update_zero_hero_diag(market_data, rejected_reason="spot_invalid")
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_signal",
                    "Zero-to-hero blocked: spot missing or stale",
                    market_data=market_data,
                    extra={"underlying_spot": underlying_spot, "spot_source": spot_source, "spot_issue": spot_issue},
                )
            return None

        atr = float(market_data.get("atr") or max(1.0, float(underlying_spot) * 0.002))
        ltp_change_window = float(market_data.get("ltp_change_window") or 0.0)
        momentum_mult = float(getattr(cfg, "ZERO_TO_HERO_MOMENTUM_ATR_MULT", 0.12))
        weak_momentum = abs(ltp_change_window) < atr * momentum_mult
        if weak_momentum and debug_reasons:
            self._log_blocked_candidate(
                symbol,
                "no_signal",
                "Zero-to-hero blocked: momentum signal too weak",
                market_data=market_data,
                extra={
                    "ltp_change_window": ltp_change_window,
                    "atr": atr,
                    "momentum_mult": momentum_mult,
                    "exploratory_mode": exploratory_mode,
                },
            )
            _log_advisory_debug("zero_to_hero_reject symbol=%s reason=weak_momentum", symbol)
        if weak_momentum and not exploratory_mode:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="weak_momentum")
            self._update_zero_hero_diag(market_data, rejected_reason="weak_momentum")
            self._reject_ctx = {"symbol": symbol, "reason": "weak_momentum", "gate_reasons": ["weak_momentum"]}
            softened = self._soften_reject_to_candidate(
                market_data=market_data,
                reject_ctx=dict(self._reject_ctx),
                strategy_tag="ZERO_TO_HERO",
            )
            if softened is not None:
                return softened
            return None

        opt_type = "CE" if ltp_change_window >= 0 else "PE"
        expiry_resolved = self._option_expiry(None, market_data)
        if not expiry_resolved:
            expiry_resolved = self._resolve_expiry_for_symbol(symbol, market_data)

        strikes: list[float] = []
        for row in chain:
            if not isinstance(row, dict):
                continue
            if row.get("strike") is None:
                continue
            try:
                strikes.append(float(row.get("strike")))
            except Exception:
                continue
        if not strikes:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="missing_strikes")
            self._update_zero_hero_diag(market_data, rejected_reason="missing_strikes")
            return None
        atm_strike = min(strikes, key=lambda s: abs(s - float(underlying_spot)))
        otm_min_pct = float(getattr(cfg, "ZERO_TO_HERO_OTM_PCT_MIN", 0.01))
        otm_max_pct = float(getattr(cfg, "ZERO_TO_HERO_OTM_PCT_MAX", 0.02))
        if exploratory_mode:
            otm_min_pct = max(0.0, otm_min_pct * 0.5)
            otm_max_pct = otm_max_pct * 1.75
        if opt_type == "CE":
            strike_low = atm_strike * (1.0 + otm_min_pct)
            strike_high = atm_strike * (1.0 + otm_max_pct)
        else:
            strike_low = atm_strike * (1.0 - otm_max_pct)
            strike_high = atm_strike * (1.0 - otm_min_pct)
        if strike_low > strike_high:
            strike_low, strike_high = strike_high, strike_low

        band_low, band_high, band_source = self._zero_to_hero_premium_band(chain, opt_type, expiry_resolved)
        abs_min = float(getattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ABS", 5))
        abs_max = float(getattr(cfg, "ZERO_TO_HERO_PREMIUM_MAX_ABS", 80))
        if band_low is None or band_high is None:
            band_low, band_high, band_source = abs_min, abs_max, "fallback_abs"
        band_low = max(band_low, abs_min)
        band_high = min(band_high, abs_max)
        if exploratory_mode:
            band_low = max(abs_min, band_low * 0.5)
            band_high = max(band_high, min(abs_max * 1.75, band_high * 1.5))
        if band_high <= band_low:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="invalid_premium_band")
            self._update_zero_hero_diag(market_data, rejected_reason="invalid_premium_band")
            return None
        self._update_zero_hero_diag(
            market_data,
            selected_premium_band={
                "strategy": "ZERO_TO_HERO",
                "variant": "generic",
                "low": round(float(band_low), 4),
                "high": round(float(band_high), 4),
                "source": str(band_source),
            },
        )

        candidates = []
        for opt in chain:
            if not isinstance(opt, dict):
                continue
            if opt.get("type") != opt_type:
                continue
            self._update_strategy_candidate_debug(stats, considered=1)
            self._update_zero_hero_diag(market_data, considered=1)
            strike = opt.get("strike")
            if strike is None:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="missing_strike")
                self._update_zero_hero_diag(market_data, rejected_reason="missing_strike")
                continue
            try:
                strike_val = float(strike)
            except Exception:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="invalid_strike")
                self._update_zero_hero_diag(market_data, rejected_reason="invalid_strike")
                continue
            if strike_val < strike_low or strike_val > strike_high:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="strike_window")
                self._update_zero_hero_diag(market_data, rejected_reason="strike_window")
                continue
            premium = self._coerce_positive_float(
                opt.get("ltp")
                or opt.get("last_price")
                or opt.get("close")
                or opt.get("price")
            )
            if premium is None:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="invalid_option_ltp")
                self._update_zero_hero_diag(market_data, rejected_reason="invalid_option_ltp")
                continue
            premium_out_of_band = bool(premium is None or premium < band_low or premium > band_high)
            if premium_out_of_band and not exploratory_mode:
                self._update_zero_hero_diag(market_data, rejected_reason="premium_band_soft")
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "premium_band_soft",
                        "Zero-to-hero softened: premium outside allowed band",
                        market_data=market_data,
                        extra={"premium": premium, "band_low": band_low, "band_high": band_high},
                    )
            spread_ok = self.execution.spread_ok(
                opt.get("bid", 0),
                opt.get("ask", 0),
                premium,
                max_spread_pct=getattr(cfg, "ZERO_TO_HERO_SPREAD_PCT_MAX", 0.25),
                instrument="OPT",
                segment=segment,
                market_open=bool(market_ctx.is_market_open),
            )
            if (not spread_ok) and not exploratory_mode:
                self._update_zero_hero_diag(market_data, rejected_reason="spread_soft")
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "spread_soft",
                        "Zero-to-hero softened: spread too wide",
                        market_data=market_data,
                        extra={"strike": opt.get("strike"), "option_type": opt.get("type")},
                    )

            momentum_score = min(1.0, abs(ltp_change_window) / max(atr * momentum_mult, 1.0))
            cheapness = 1.0 - ((premium - band_low) / max((band_high - band_low), 1e-6))
            base_conf = float(getattr(cfg, "ZERO_TO_HERO_CONF_BASE", 0.55))
            mom_w = float(getattr(cfg, "ZERO_TO_HERO_CONF_MOMENTUM_WEIGHT", 0.3))
            cheap_w = float(getattr(cfg, "ZERO_TO_HERO_CONF_CHEAPNESS_WEIGHT", 0.2))
            confidence = base_conf + (mom_w * momentum_score) + (cheap_w * cheapness)
            if weak_momentum:
                confidence -= 0.10
            if premium_out_of_band:
                confidence -= 0.08
            if not spread_ok:
                confidence -= 0.10
            confidence = max(0.0, min(1.0, confidence))
            builder_confidence = confidence
            self._update_strategy_candidate_debug(stats, scored=1)

            candidates.append(
                {
                    "opt": opt,
                    "premium": premium,
                    "confidence": confidence,
                    "builder_confidence": builder_confidence,
                    "cheapness": cheapness,
                    "momentum_score": momentum_score,
                    "band_source": band_source,
                    "premium_band_fail": premium_out_of_band,
                    "spread_warning": not spread_ok,
                }
            )

        if not candidates:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="no_viable_candidates")
            if not ((market_data or {}).get("zero_hero_diagnostics") or {}).get("zero_hero_rejected_reason"):
                self._update_zero_hero_diag(market_data, rejected_reason="no_viable_candidates")
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_viable_candidates",
                    "Zero-to-hero blocked: no viable candidates",
                    market_data=market_data,
                    extra={"band_low": band_low, "band_high": band_high, "exploratory_mode": exploratory_mode},
                )
            self._reject_ctx = {
                "symbol": symbol,
                "reason": "no_viable_candidates",
                "gate_reasons": ["no_viable_candidates"],
                "strategy": "ZERO_TO_HERO",
            }
            return None
        chosen = sorted(candidates, key=lambda c: c["confidence"], reverse=True)[0]
        opt = chosen["opt"]
        premium = float(chosen["premium"])
        self._update_zero_hero_diag(market_data, clear_rejected_reason=True)

        bid = float(opt.get("bid") or 0.0)
        ask = float(opt.get("ask") or 0.0)
        entry_proxy, entry_price_source = self._option_executable_price(opt, side="BUY")
        entry_price = float(entry_proxy) if entry_proxy and entry_proxy > 0 else premium
        if entry_price_source is None and entry_proxy and entry_proxy > 0:
            entry_price_source = "ltp"
        slippage = self.execution.estimate_slippage(bid, ask, opt.get("volume", 0))
        _trigger_entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
            entry_price, side="BUY", quick_mode=True
        )
        if entry_ref_price is None:
            entry_ref_price = entry_price
        if entry_condition and _trigger_entry_price is not None:
            entry_price = float(_trigger_entry_price)
        option_risk = self._option_risk_proxy(entry_price, bid, ask)
        stop_loss, target = self._opt_risk_levels(
            entry_price,
            bid,
            ask,
            option_risk,
            stop_mult=float(getattr(cfg, "ZERO_TO_HERO_STOP_ATR", 0.8)),
            target_mult=float(getattr(cfg, "ZERO_TO_HERO_TARGET_ATR", 2.0)),
        )
        if not (target > entry_price > stop_loss):
            logger.error(
                "invalid_opt_levels symbol=%s side=%s entry=%s stop=%s target=%s strike=%s right=%s",
                symbol,
                "BUY",
                entry_price,
                stop_loss,
                target,
                opt.get("strike"),
                opt.get("type"),
            )
            return None

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        option_right = self._coerce_option_type(opt.get("type") or opt.get("option_type") or opt.get("right")) or opt_type
        expiry_resolved = self._option_expiry(opt, market_data) or expiry_resolved
        contract = self._resolve_option_contract(
            symbol,
            opt.get("strike"),
            option_right,
            expiry_resolved,
            market_data,
        )
        expiry_resolved = contract.get("expiry") or expiry_resolved
        tradingsymbol = contract.get("tradingsymbol") or opt.get("tradingsymbol")
        instrument_token = contract.get("instrument_token") or opt.get("instrument_token")
        instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
            symbol,
            "OPT",
            expiry_resolved,
            opt.get("strike"),
            option_right,
            1,
        )
        if ident_err or not expiry_resolved or not tradingsymbol or not instrument_id:
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_contract",
                    "Zero-to-hero blocked: unresolved contract",
                    market_data=market_data,
                    extra={"strike": opt.get("strike"), "option_type": option_right},
                )
            return None
        if instrument_token is None and debug_reasons:
            self._log_blocked_candidate(
                symbol,
                "no_token",
                "Zero-to-hero continuing without resolved instrument token",
                market_data=market_data,
                extra={"strike": opt.get("strike"), "option_type": option_right, "tradingsymbol": tradingsymbol},
            )

        intent = self.trade_intent_flags(market_data, opt=opt, additional_blockers=[])
        intent["planning_only"] = True
        intent["execution_allowed"] = False
        intent["execution_reason"] = "PAPER_ONLY"
        zero_hero_confidence = float(chosen["confidence"])

        trade = Trade(
            trade_id=f"{symbol}-{option_right}-{int(opt.get('strike'))}-ZTH-{ts}",
            timestamp=datetime.now(),
            symbol=symbol,
            instrument="OPT",
            instrument_type=instrument_type,
            right=option_right,
            instrument_id=instrument_id,
            instrument_token=instrument_token,
            strike=opt.get("strike"),
            expiry=expiry_resolved,
            expiry_date=expiry_resolved,
            tradingsymbol=tradingsymbol,
            option_type=option_right,
            side="BUY",
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target=round(target, 2),
            qty=1,
            qty_lots=1,
            qty_units=qty_units,
            validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
            capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
            expected_slippage=round(slippage, 2),
            confidence=round(zero_hero_confidence, 3),
            strategy=getattr(cfg, "STRATEGY_ZERO_TO_HERO", "ZERO_TO_HERO"),
            regime=market_data.get("regime", "NEUTRAL"),
            tier="EXPLORATION",
            day_type=market_data.get("day_type", "UNKNOWN"),
            entry_condition=entry_condition,
            entry_ref_price=entry_ref_price,
            signal_price=self._option_signal_price(opt, market_data),
            entry_price_source=entry_price_source,
            expected_entry=round(entry_price, 2),
            expected_entry_source=entry_price_source,
            opt_ltp=opt.get("ltp"),
            opt_bid=opt.get("bid"),
            opt_ask=opt.get("ask"),
            **self._option_liquidity_fields(opt),
            quote_ok=opt.get("quote_ok", True),
            tradable=bool(intent["tradable"]),
            tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
            planning_only=True,
            execution_allowed=False,
            reason=intent.get("execution_reason") or "PAPER_ONLY",
            source_flags=dict(intent.get("source_flags") or {}),
            underlying_spot=underlying_spot,
            spot_source=spot_source,
            option_ltp_source=opt.get("option_ltp_source") or opt.get("quote_source"),
            chain_source=market_data.get("chain_source") or opt.get("chain_source"),
            **self._staged_confidence_payload(
                confidence=zero_hero_confidence,
                model_raw=zero_hero_confidence,
                model_component=zero_hero_confidence,
                micro_blend_method="model_only",
                before_soft_veto=zero_hero_confidence,
                after_soft_veto=zero_hero_confidence,
                penalty_soft_veto_total=0.0,
                penalty_soft_veto_reasons=[],
                base=zero_hero_confidence,
                penalty_total=0.0,
                penalty_reasons=[],
            ),
        )
        trade = self._decorate_trade_context(trade, market_data, zero_hero_confidence)
        if trade is None:
            return None

        trade.source_flags.update(
            {
                "zero_to_hero": True,
                "zero_hero_considered": int(
                    ((market_data or {}).get("zero_hero_diagnostics") or {}).get("zero_hero_considered", 0)
                ),
                "zero_hero_selected_premium_band": dict(
                    (((market_data or {}).get("zero_hero_diagnostics") or {}).get("zero_hero_selected_premium_band") or {})
                ),
                "zero_hero_activation_window": dict(
                    (((market_data or {}).get("zero_hero_diagnostics") or {}).get("zero_hero_activation_window") or {})
                ),
                "zero_to_hero_band_source": chosen.get("band_source"),
                "zero_to_hero_otm_min": strike_low,
                "zero_to_hero_otm_max": strike_high,
                "premium_band_fail": bool(chosen.get("premium_band_fail")),
                "spread_warning": bool(chosen.get("spread_warning")),
            }
        )

        self._zero_to_hero_daily_count += 1
        try:
            _log_signal_event(
                "zero_to_hero_selected",
                symbol,
                {
                    "strategy": getattr(cfg, "STRATEGY_ZERO_TO_HERO", "ZERO_TO_HERO"),
                    "expiry": expiry_resolved,
                    "strike": opt.get("strike"),
                    "type": opt.get("type"),
                    "confidence": trade.confidence,
                    "premium_band": [band_low, band_high],
                },
            )
        except Exception:
            pass
        try:
            trade_sf = dict(getattr(trade, "source_flags", {}) or {})
            trade_trace = dict(trade_sf.get("decision_trace", {}) or {})
            liquidity_flow_score = self._candidate_telemetry_field(trade, trade_sf, trade_trace, "liquidity_flow_score")
            liquidity_book_score = self._candidate_telemetry_field(trade, trade_sf, trade_trace, "liquidity_book_score")
            liquidity_spread_score = self._candidate_telemetry_field(trade, trade_sf, trade_trace, "liquidity_spread_score")
            liquidity_volume_score = self._candidate_telemetry_field(trade, trade_sf, trade_trace, "liquidity_volume_score")
            liquidity_oi_score = self._candidate_telemetry_field(trade, trade_sf, trade_trace, "liquidity_oi_score")
            setup_telemetry_fields = self._setup_telemetry_fields(
                trade,
                trade_sf,
                trade_trace,
                candidate_quality_score=getattr(trade, "opportunity_score", None),
                trigger_base_score=trade_trace.get("trigger_base_score"),
                invalidation_score=trade_trace.get("invalidation_score"),
                overextension_score=trade_trace.get("overextension_score"),
                timing_quality_score=trade_trace.get("timing_quality"),
            )
            record_candidate_decision(
                {
                    "candidate_id": trade.trade_id,
                    "ts_epoch": now_utc_epoch(),
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "entry": trade.entry_price,
                    "stop": trade.stop_loss,
                    "target": trade.target,
                    "regime": trade.regime,
                    "execution_allowed": False,
                    "confidence_score": trade.confidence,
                    "instrument_id": trade.instrument_id,
                    "mode": exec_mode,
                    "gates_failed": [],
                    "soft_vetos": [],
                    "signal_score": trade.confidence,
                    "regime_conf": market_data.get("regime_confidence") or market_data.get("day_confidence"),
                    "orb_bias": market_data.get("orb_bias"),
                    "liquidity_flow_score": liquidity_flow_score,
                    "liquidity_book_score": liquidity_book_score,
                    "liquidity_spread_score": liquidity_spread_score,
                    "liquidity_volume_score": liquidity_volume_score,
                    "liquidity_oi_score": liquidity_oi_score,
                    **setup_telemetry_fields,
                    "permission": "ADVISORY_ONLY",
                    "permission_reason": "PAPER_ONLY",
                    "entry_status": (
                        "OK"
                        if (trade.execution_entry is not None and str(trade.execution_entry_status or "").lower() == "executable")
                        else ("NON_EXECUTABLE" if trade.display_entry is not None else str(trade.entry_clear_reason or "missing_entry").strip().upper())
                    ),
                    "entry_block_reason": (
                        None
                        if (trade.execution_entry is not None and str(trade.execution_entry_status or "").lower() == "executable")
                        else str(trade.entry_clear_reason or trade.entry_reason or "missing_execution_entry")
                    ),
                    "final_action": "ADVISORY_ONLY",
                }
            )
        except Exception:
            pass
        return trade

    def _is_expiry_day_for_symbol(self, symbol: str, market_data: dict | None) -> bool:
        data = market_data or {}
        day_type = str(data.get("day_type") or "").strip().upper()
        if "EXPIRY" in day_type:
            return True
        try:
            weekday_map = getattr(cfg, "EXPIRY_WEEKDAY_BY_SYMBOL", {}) or {}
            expected = int(weekday_map.get(str(symbol or "").upper()))
        except Exception:
            return False
        try:
            # Python Monday=0; config expects the same convention.
            return int(now_ist().weekday()) == expected
        except Exception:
            return False

    def build_expiry_lotto_candidates(self, market_data, debug_reasons: bool = False) -> list[Trade]:
        if not bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)):
            if debug_reasons:
                self._log_blocked_candidate(
                    (market_data or {}).get("symbol"),
                    "mode_block",
                    "Expiry lotto blocked: mode disabled",
                    market_data=market_data,
                    extra={"execution_mode": str(getattr(cfg, "EXECUTION_MODE", "PAPER")).upper()},
                )
            return []
        data = market_data if isinstance(market_data, dict) else {}
        symbol = str(data.get("symbol") or "").upper()
        execution_mode = str(
            data.get("execution_mode")
            or ((data.get("market_context") or {}).get("execution_mode") if isinstance(data.get("market_context"), dict) else "")
            or getattr(cfg, "EXECUTION_MODE", "PAPER")
        ).strip().upper()
        exploratory_mode = execution_mode in {"SIM", "PAPER"}
        if symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
            return []
        if not self._is_expiry_day_for_symbol(symbol, data):
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "mode_block",
                    "Expiry lotto blocked: not expiry day",
                    market_data=data,
                    extra={"execution_mode": execution_mode},
                )
                self._reject_ctx = {"reason": "expiry_lotto_not_expiry_day", "symbol": symbol}
            return []

        chain = data.get("option_chain") or []
        if not isinstance(chain, list) or not chain:
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_viable_candidates",
                    "Expiry lotto blocked: option chain unavailable",
                    market_data=data,
                    extra={"execution_mode": execution_mode},
                )
            self._reject_ctx = {"reason": "expiry_lotto_no_option_chain", "symbol": symbol}
            return []
        min_option_tokens = max(
            1,
            int(
                getattr(
                    cfg,
                    "EXPIRY_LOTTO_MIN_OPTION_TOKENS",
                    getattr(cfg, "MIN_OPTION_TOKENS", 12),
                )
            ),
        )
        if exploratory_mode:
            min_option_tokens = max(1, min_option_tokens // 2)
        option_tokens = set()
        for row in chain:
            if not isinstance(row, dict):
                continue
            tok = row.get("instrument_token")
            try:
                tok_int = int(tok)
            except Exception:
                tok_int = 0
            if tok_int > 0:
                option_tokens.add(tok_int)
        if len(option_tokens) < min_option_tokens:
            self._reject_ctx = {
                "reason": "expiry_lotto_option_tokens_under_min",
                "symbol": symbol,
                "option_tokens_count": len(option_tokens),
                "min_required": min_option_tokens,
            }
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_token",
                    "Expiry lotto blocked: option token coverage under minimum",
                    market_data=data,
                    extra={"option_tokens_count": len(option_tokens), "min_required": min_option_tokens},
                )
            now_epoch = float(now_utc_epoch())
            cooldown_sec = float(getattr(cfg, "OPTION_TOKEN_INCIDENT_COOLDOWN_SEC", 300.0))
            incident_key = f"{symbol}:{str(data.get('expiry_date') or '')}"
            last_incident = float(self._expiry_lotto_token_incident_ts.get(incident_key, 0.0) or 0.0)
            try:
                if (now_epoch - last_incident) >= cooldown_sec:
                    create_incident(
                        SEV2,
                        "EXPIRY_LOTTO_OPTION_TOKENS_UNDER_MIN",
                        {
                            "symbol": symbol,
                            "option_tokens_count": len(option_tokens),
                            "min_required": min_option_tokens,
                        },
                    )
                    self._expiry_lotto_token_incident_ts[incident_key] = now_epoch
            except Exception:
                pass
            return []

        target_count = max(1, int(getattr(cfg, "EXPIRY_LOTTO_TARGET_CANDIDATES", 4)))
        max_trades = max(1, int(getattr(cfg, "EXPIRY_LOTTO_MAX_TRADES", 4)))
        desired = min(target_count, max_trades)
        atr = float(data.get("atr") or max(1.0, float(data.get("ltp") or 0.0) * 0.002))
        ltp_change_window = float(data.get("ltp_change_window") or 0.0)
        min_momentum = float(getattr(cfg, "EXPIRY_LOTTO_MIN_MOMENTUM_ATR", 0.10))
        weak_momentum = abs(ltp_change_window) < (atr * min_momentum)
        if weak_momentum and debug_reasons:
            self._log_blocked_candidate(
                symbol,
                "no_signal",
                "Expiry lotto blocked: momentum too low",
                market_data=data,
                extra={"momentum": ltp_change_window, "atr": atr, "min_momentum": min_momentum, "exploratory_mode": exploratory_mode},
            )
        if weak_momentum and not exploratory_mode:
            self._reject_ctx = {
                "reason": "expiry_lotto_momentum_too_low",
                "symbol": symbol,
                "momentum": ltp_change_window,
                "atr": atr,
            }
            return []

        segment = data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        ctx_payload = dict(data.get("market_context") or {}) if isinstance(data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = str(getattr(cfg, "EXECUTION_MODE", "PAPER")).upper()
        if "market_open" not in ctx_payload:
            ctx_payload["market_open"] = data.get("market_open", True)
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = segment
        market_ctx = derive_market_context(ctx_payload)

        underlying_spot, spot_source, spot_ok, spot_issue = self._resolve_underlying_spot(data, market_ctx)
        if (not spot_ok) and spot_issue == "spot_stale":
            # Expiry lotto is advisory-only; allow build when spot exists but quote_age is missing.
            quote_age_raw = data.get("quote_age_sec")
            if underlying_spot is not None and quote_age_raw in (None, "", "None"):
                spot_ok = True
        if not spot_ok:
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_signal",
                    "Expiry lotto blocked: spot invalid",
                    market_data=data,
                    extra={"spot_issue": spot_issue, "spot_source": spot_source},
                )
            self._reject_ctx = {
                "reason": "expiry_lotto_spot_invalid",
                "symbol": symbol,
                "spot_issue": spot_issue,
            }
            return []

        strike_step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}
        strike_step = float(strike_step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50)))
        atm_steps_map = getattr(cfg, "EXPIRY_LOTTO_ATM_STRIKES_BY_SYMBOL", {}) or {}
        atm_steps = max(1, int(atm_steps_map.get(symbol, getattr(cfg, "EXPIRY_LOTTO_ATM_STRIKES", 2))))
        if exploratory_mode:
            atm_steps += 1
        atm = round(float(underlying_spot) / strike_step) * strike_step if strike_step > 0 else float(underlying_spot)
        low_strike = float(atm) - float(atm_steps * strike_step)
        high_strike = float(atm) + float(atm_steps * strike_step)

        preferred_type = "CE" if ltp_change_window >= 0 else "PE"
        orb_bias = str(data.get("orb_bias") or "").upper()
        trend_state = str(data.get("trend_state") or "").upper()
        require_trend_confirm = bool(getattr(cfg, "EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM", True))
        trend_soft_fail = False
        if require_trend_confirm:
            trend_up = ("UP" in trend_state) or ("BULL" in trend_state) or orb_bias == "UP"
            trend_down = ("DOWN" in trend_state) or ("BEAR" in trend_state) or orb_bias == "DOWN"
            if preferred_type == "CE" and not trend_up:
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "no_signal",
                        "Expiry lotto blocked: bullish trend not confirmed",
                        market_data=data,
                        extra={"direction": "UP", "exploratory_mode": exploratory_mode},
                    )
                if exploratory_mode:
                    trend_soft_fail = True
                else:
                    self._reject_ctx = {"reason": "expiry_lotto_trend_not_confirmed", "symbol": symbol, "direction": "UP"}
                    return []
            if preferred_type == "PE" and not trend_down:
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "no_signal",
                        "Expiry lotto blocked: bearish trend not confirmed",
                        market_data=data,
                        extra={"direction": "DOWN", "exploratory_mode": exploratory_mode},
                    )
                if exploratory_mode:
                    trend_soft_fail = True
                else:
                    self._reject_ctx = {"reason": "expiry_lotto_trend_not_confirmed", "symbol": symbol, "direction": "DOWN"}
                    return []

        max_spread_pct = float(getattr(cfg, "EXPIRY_LOTTO_MAX_SPREAD_PCT", 0.35))
        max_loss_per_trade = float(getattr(cfg, "EXPIRY_LOTTO_MAX_LOSS_PER_TRADE", 1500.0))
        expiry_resolved = self._option_expiry(None, data) or self._resolve_expiry_for_symbol(symbol, data)
        lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(symbol, 1))
        now_text = datetime.now().strftime("%Y%m%d-%H%M%S")

        scored: list[tuple[float, Trade]] = []
        reject_counts: dict[str, int] = {}
        for raw in chain:
            if not isinstance(raw, dict):
                continue
            opt_type = str(raw.get("type") or raw.get("option_type") or "").upper()
            if opt_type not in {"CE", "PE"}:
                continue
            try:
                strike = float(raw.get("strike"))
            except Exception:
                reject_counts["missing_strike"] = reject_counts.get("missing_strike", 0) + 1
                continue
            if strike < low_strike or strike > high_strike:
                continue
            ltp = self._coerce_positive_float(raw.get("ltp") or raw.get("last_price"))
            bid = self._coerce_positive_float(raw.get("bid"))
            ask = self._coerce_positive_float(raw.get("ask"))
            if ltp is None or bid is None or ask is None or ask < bid:
                reject_counts["invalid_quote"] = reject_counts.get("invalid_quote", 0) + 1
                continue
            if not self.execution.spread_ok(
                bid,
                ask,
                ltp,
                max_spread_pct=max_spread_pct,
                instrument="OPT",
                segment=segment,
                market_open=bool(market_ctx.is_market_open),
            ):
                reject_counts["spread"] = reject_counts.get("spread", 0) + 1
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "spread",
                        "Expiry lotto candidate spread too wide",
                        market_data=data,
                        extra={"strike": strike, "option_type": opt_type, "exploratory_mode": exploratory_mode},
                    )
                if not exploratory_mode:
                    continue
            if opt_type != preferred_type:
                continue

            slippage = self.execution.estimate_slippage(bid, ask, raw.get("volume", 0))
            entry_base, entry_price_source = self._option_executable_price(raw, side="BUY")
            if entry_base is None:
                reject_counts["premium_band_fail"] = reject_counts.get("premium_band_fail", 0) + 1
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "premium_band_fail",
                        "Expiry lotto candidate missing executable premium proxy",
                        market_data=data,
                        extra={"strike": strike, "option_type": opt_type},
                    )
                continue
            entry_price = max(0.01, float(entry_base))
            stop_loss = max(0.01, entry_price * 0.82)
            target = entry_price + max(entry_price * 0.32, 8.0)
            per_lot_risk = max(0.01, entry_price - stop_loss) * max(1, lot_size)
            if per_lot_risk > max_loss_per_trade:
                reject_counts["risk_cap_breach"] = reject_counts.get("risk_cap_breach", 0) + 1
                continue

            contract = self._resolve_option_contract(symbol, strike, opt_type, expiry_resolved, data)
            expiry_use = contract.get("expiry") or expiry_resolved
            tradingsymbol = contract.get("tradingsymbol") or raw.get("tradingsymbol")
            instrument_token = contract.get("instrument_token") or raw.get("instrument_token")
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                expiry_use,
                strike,
                opt_type,
                1,
            )
            if ident_err or not tradingsymbol or not instrument_id or not expiry_use:
                reject_counts["no_contract"] = reject_counts.get("no_contract", 0) + 1
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "no_contract",
                        "Expiry lotto candidate missing resolved contract",
                        market_data=data,
                        extra={"strike": strike, "option_type": opt_type},
                    )
                continue
            if instrument_token is None:
                reject_counts["no_token"] = reject_counts.get("no_token", 0) + 1
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "no_token",
                        "Expiry lotto candidate unresolved token",
                        market_data=data,
                        extra={"strike": strike, "option_type": opt_type, "tradingsymbol": tradingsymbol},
                    )
            confidence = max(0.55, min(0.95, abs(ltp_change_window) / max(atr, 1.0)))
            if weak_momentum:
                confidence -= 0.10
            if trend_soft_fail:
                confidence -= 0.08
            if reject_counts.get("spread", 0):
                confidence = max(0.0, confidence - 0.08)
            intent = self.trade_intent_flags(data, opt=raw, additional_blockers=[])
            intent["planning_only"] = True
            intent["execution_allowed"] = False
            intent["execution_reason"] = "EXPIRY_LOTTO_MODE"
            trade = Trade(
                trade_id=f"{symbol}-{opt_type}-{int(strike)}-LOTTO-{now_text}",
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=opt_type,
                instrument_id=instrument_id,
                instrument_token=instrument_token,
                strike=strike,
                expiry=expiry_use,
                expiry_date=expiry_use,
                tradingsymbol=tradingsymbol,
                option_type=opt_type,
                side="BUY",
                entry_price=round(entry_price, 2),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                qty=1,
                qty_lots=1,
                qty_units=qty_units,
                validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
                capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
                expected_slippage=round(float(slippage or 0.0), 2),
                confidence=round(confidence, 3),
                strategy="EXPIRY_LOTTO",
                regime=data.get("regime", "UNKNOWN"),
                tier="EXPLORATION",
                day_type=data.get("day_type", "EXPIRY_DAY"),
                signal_price=self._option_signal_price(raw, data),
                entry_price_source=entry_price_source,
                expected_entry=round(entry_price, 2),
                expected_entry_source=entry_price_source,
                **self._option_liquidity_fields(raw),
                opt_ltp=ltp,
                opt_bid=bid,
                opt_ask=ask,
                quote_ok=True,
                tradable=bool(intent["tradable"]),
                tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                planning_only=True,
                execution_allowed=False,
                reason="EXPIRY_LOTTO_MODE",
                source_flags=dict(intent.get("source_flags") or {}),
                underlying_spot=underlying_spot,
                spot_source=spot_source,
                option_ltp_source=raw.get("option_ltp_source") or raw.get("quote_source"),
                chain_source=data.get("chain_source") or raw.get("chain_source"),
                **self._staged_confidence_payload(
                    confidence=confidence,
                    model_raw=confidence,
                    model_component=confidence,
                    micro_blend_method="model_only",
                    before_soft_veto=confidence,
                    after_soft_veto=confidence,
                    penalty_soft_veto_total=0.0,
                    penalty_soft_veto_reasons=[],
                    base=confidence,
                    penalty_total=0.0,
                    penalty_reasons=[],
                ),
            )
            # score favors lower spread and nearer ATM
            spread_penalty = (ask - bid) / max(entry_price, 1e-6)
            atm_distance = abs(strike - float(atm)) / max(strike_step, 1.0)
            score = float(confidence) - (0.4 * spread_penalty) - (0.03 * atm_distance)
            decorated = self._decorate_trade_context(trade, data, confidence)
            if decorated is not None:
                scored.append((score, decorated))

        if not scored:
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_viable_candidates",
                    "Expiry lotto blocked: no viable candidates",
                    market_data=data,
                    extra={"reject_counts": reject_counts, "execution_mode": execution_mode},
                )
            self._reject_ctx = {
                "reason": "expiry_lotto_no_candidates",
                "symbol": symbol,
                "reject_counts": reject_counts,
            }
            return []
        scored.sort(key=lambda x: x[0], reverse=True)
        out = [row[1] for row in scored[:desired]]
        out = annotate_ranked_opportunities(
            out,
            scope=f"expiry_lotto:{symbol}",
            top_n=min(int(getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)), max(1, desired)),
        )
        self._set_last_ranked_candidates(out)
        if len(out) < 3:
            self._reject_ctx = {
                "reason": "expiry_lotto_insufficient_candidates",
                "symbol": symbol,
                "generated": len(out),
                "target": desired,
                "reject_counts": reject_counts,
            }
        return out

    def _build_zero_hero_expiry(self, market_data, debug_reasons=False):
        """
        Expiry-day zero-hero: low premium, high delta, fast move required.
        Focused on small premium with potential ~50pts underlying move.
        """
        data = market_data if isinstance(market_data, dict) else {}
        stats = self._strategy_candidate_debug(data, "zero_hero_expiry")
        symbol = data.get("symbol")
        ltp = float(data.get("ltp") or 0.0)
        atr = float(data.get("atr") or max(1.0, ltp * 0.002 or 1.0))
        minutes_since_open = int(data.get("minutes_since_open", 0) or 0)
        soft_cutoff = int(getattr(cfg, "ZERO_HERO_EXPIRY_TIME_CUTOFF_MIN", 120))
        hard_cutoff = max(soft_cutoff, int(getattr(cfg, "ZERO_HERO_EXPIRY_TIME_HARD_CUTOFF_MIN", 150)))
        self._update_zero_hero_diag(
            data,
            activation_window={
                "strategy": "ZERO_HERO_EXPIRY",
                "variant": "expiry_day",
                "expiry_day": True,
                "minutes_since_open": minutes_since_open,
                "soft_cutoff_min": soft_cutoff,
                "hard_cutoff_min": hard_cutoff,
            },
        )
        if minutes_since_open > hard_cutoff:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="time_window_hard")
            self._update_zero_hero_diag(data, rejected_reason="time_window_hard")
            return None
        late_window_soft = minutes_since_open > soft_cutoff
        if self._expiry_zero_hero_count >= getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES", 2):
            self._update_strategy_candidate_debug(stats, rejected=1, reason="max_trades")
            self._update_zero_hero_diag(data, rejected_reason="max_trades")
            return None
        max_per_symbol = getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES_PER_SYMBOL", 1)
        if symbol == "NIFTY":
            max_per_symbol = getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES_NIFTY", max_per_symbol)
        if symbol == "SENSEX":
            max_per_symbol = getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES_SENSEX", max_per_symbol)
        if self._expiry_zero_hero_by_symbol.get(symbol, 0) >= max_per_symbol:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="max_trades_symbol")
            self._update_zero_hero_diag(data, rejected_reason="max_trades_symbol")
            return None
        try:
            until = self._expiry_zero_hero_disabled_until.get(symbol)
            if until and time.time() < until:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="cooldown_active")
                self._update_zero_hero_diag(data, rejected_reason="cooldown_active")
                return None
        except Exception:
            pass

        execution_mode = str(
            data.get("execution_mode")
            or ((data.get("market_context") or {}).get("execution_mode") if isinstance(data.get("market_context"), dict) else "")
            or getattr(cfg, "EXECUTION_MODE", "PAPER")
        ).strip().upper()
        segment = data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        ctx_payload = dict(data.get("market_context") or {}) if isinstance(data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = execution_mode
        if "market_open" not in ctx_payload:
            ctx_payload["market_open"] = data.get("market_open", True)
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = segment
        market_ctx = derive_market_context(ctx_payload)
        underlying_spot, spot_source, spot_ok, spot_issue = self._resolve_underlying_spot(data, market_ctx)
        if not spot_ok:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="spot_invalid")
            self._update_zero_hero_diag(data, rejected_reason="spot_invalid")
            return None
        if ltp <= 0 and underlying_spot is not None:
            ltp = float(underlying_spot)

        ltp_change_window = float(data.get("ltp_change_window", 0) or 0.0)
        vwap = float(data.get("vwap", ltp) or ltp or underlying_spot or 0.0)
        orb_bias = str(data.get("orb_bias", "NEUTRAL") or "NEUTRAL").strip().upper()
        direction = "BUY_CALL" if (ltp_change_window >= 0 and ltp >= vwap) else "BUY_PUT"
        orb_pending_soft = orb_bias == "PENDING"
        orb_conflict_soft = (orb_bias == "UP" and direction == "BUY_PUT") or (
            orb_bias == "DOWN" and direction == "BUY_CALL"
        )
        opt_type = "CE" if direction == "BUY_CALL" else "PE"

        min_p = float(getattr(cfg, "ZERO_HERO_EXPIRY_MIN_PREMIUM", 5))
        max_p = float(
            getattr(cfg, "ZERO_HERO_EXPIRY_PREMIUM_MAX_BY_SYMBOL", {}).get(
                symbol,
                getattr(cfg, "ZERO_HERO_EXPIRY_MAX_PREMIUM", 40),
            )
        )
        min_delta = float(getattr(cfg, "ZERO_HERO_EXPIRY_MIN_DELTA", 0.2))
        max_delta = float(getattr(cfg, "ZERO_HERO_EXPIRY_MAX_DELTA", 0.5))
        tgt_points = float(getattr(cfg, "ZERO_HERO_EXPIRY_TARGET_POINTS", {}).get(symbol, 50))
        iv_min = float(getattr(cfg, "ZERO_HERO_IVCRUSH_MIN", 0.15))
        iv_margin = float(getattr(cfg, "ZERO_HERO_EXPIRY_SOFT_IV_MARGIN", 0.03))
        tte_max = float(getattr(cfg, "ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS", 6))
        tte_margin = float(getattr(cfg, "ZERO_HERO_EXPIRY_SOFT_TTE_MARGIN_HRS", 1.5))
        delta_margin = float(getattr(cfg, "ZERO_HERO_EXPIRY_SOFT_DELTA_MARGIN", 0.08))
        premium_margin_ratio = float(getattr(cfg, "ZERO_HERO_EXPIRY_PREMIUM_SOFT_MARGIN_RATIO", 0.20))
        min_p_soft = max(0.01, min_p * max(0.0, 1.0 - premium_margin_ratio))
        max_p_soft = max_p * (1.0 + max(0.0, premium_margin_ratio))
        momentum_threshold = atr * float(getattr(cfg, "ZERO_HERO_ATR_MULT", 0.08))
        soft_momentum_threshold = momentum_threshold * float(
            getattr(cfg, "ZERO_HERO_EXPIRY_SOFT_MOMENTUM_RATIO", 0.65)
        )
        self._update_zero_hero_diag(
            data,
            selected_premium_band={
                "strategy": "ZERO_HERO_EXPIRY",
                "variant": "expiry_day",
                "low": round(float(min_p), 4),
                "high": round(float(max_p), 4),
                "soft_low": round(float(min_p_soft), 4),
                "soft_high": round(float(max_p_soft), 4),
                "source": "expiry_config",
            },
        )
        if abs(ltp_change_window) < soft_momentum_threshold:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="momentum_too_low")
            self._update_zero_hero_diag(data, rejected_reason="momentum_too_low")
            return None
        weak_momentum = abs(ltp_change_window) < momentum_threshold
        allowed_life, _ = self._apply_lifecycle_gate("ZERO_HERO_EXPIRY", mode="QUICK")
        if not allowed_life:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="lifecycle_gate")
            self._update_zero_hero_diag(data, rejected_reason="lifecycle_gate")
            if debug_reasons:
                _log_advisory_debug("zero_hero_expiry_reject symbol=%s reason=lifecycle_gate", symbol)
            return None

        candidates = []
        chain = data.get("option_chain", [])
        for opt in chain:
            if not isinstance(opt, dict):
                continue
            if opt.get("type") != opt_type:
                continue
            self._update_strategy_candidate_debug(stats, considered=1)
            self._update_zero_hero_diag(data, considered=1)
            has_required_quote, _ = self._validate_required_option_quote_fields(opt)
            if not has_required_quote:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="partial_option_row")
                self._update_zero_hero_diag(data, rejected_reason="partial_option_row")
                continue
            premium = self._coerce_positive_float(opt.get("ltp") or opt.get("last_price"))
            if premium is None:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="invalid_option_ltp")
                self._update_zero_hero_diag(data, rejected_reason="invalid_option_ltp")
                continue
            soft_flags: list[str] = []
            penalty = 0.0
            if premium < min_p_soft or premium > max_p_soft:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="premium_out_of_range")
                self._update_zero_hero_diag(data, rejected_reason="premium_out_of_range")
                continue
            if premium < min_p or premium > max_p:
                soft_flags.append("premium_soft_band")
                penalty += 0.08

            bid = self._coerce_positive_float(opt.get("bid"))
            ask = self._coerce_positive_float(opt.get("ask"))
            if bid is None or ask is None or ask < bid:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="invalid_bid_ask")
                self._update_zero_hero_diag(data, rejected_reason="invalid_bid_ask")
                continue
            spread_ok = self.execution.spread_ok(
                bid,
                ask,
                premium or 1.0,
                instrument="OPT",
                segment=segment,
                market_open=bool(market_ctx.is_market_open),
            )
            spread_pct = max(0.0, ask - bid) / max(premium, 1e-6)
            if not spread_ok:
                if spread_pct > float(getattr(cfg, "ZERO_HERO_EXPIRY_SPREAD_HARD_PCT", 0.45)):
                    self._update_strategy_candidate_debug(stats, rejected=1, reason="spread_too_wide")
                    self._update_zero_hero_diag(data, rejected_reason="spread_too_wide")
                    continue
                soft_flags.append("spread_soft_fail")
                penalty += 0.10

            iv = opt.get("iv")
            if iv is not None:
                iv_val = float(iv)
                if iv_val < (iv_min - iv_margin):
                    self._update_strategy_candidate_debug(stats, rejected=1, reason="iv_too_low")
                    self._update_zero_hero_diag(data, rejected_reason="iv_too_low")
                    continue
                if iv_val < iv_min:
                    soft_flags.append("iv_soft_fail")
                    penalty += 0.06
            tte_hrs = opt.get("time_to_expiry_hrs")
            if tte_hrs is None:
                tte_hrs = data.get("time_to_expiry_hrs")
            if tte_hrs is None:
                tte_hrs = 0.0
            try:
                tte_val = float(tte_hrs)
            except Exception:
                tte_val = 0.0
            if tte_val > (tte_max + tte_margin):
                self._update_strategy_candidate_debug(stats, rejected=1, reason="time_to_expiry_too_high")
                self._update_zero_hero_diag(data, rejected_reason="time_to_expiry_too_high")
                continue
            if tte_val > tte_max:
                soft_flags.append("time_to_expiry_soft_fail")
                penalty += 0.05

            delta_raw = opt.get("delta")
            d = abs(float(delta_raw)) if delta_raw is not None else 0.0
            if d:
                if d < (min_delta - delta_margin) or d > (max_delta + delta_margin):
                    self._update_strategy_candidate_debug(stats, rejected=1, reason="delta_out_of_range")
                    self._update_zero_hero_diag(data, rejected_reason="delta_out_of_range")
                    continue
                if d < min_delta or d > max_delta:
                    soft_flags.append("delta_soft_fail")
                    penalty += 0.07

            if weak_momentum:
                soft_flags.append("momentum_soft_fail")
                penalty += 0.09
            if late_window_soft:
                soft_flags.append("late_window_soft_fail")
                penalty += 0.07
            if orb_pending_soft:
                soft_flags.append("orb_bias_pending")
                penalty += 0.05
            elif orb_conflict_soft:
                soft_flags.append("orb_bias_conflict")
                penalty += 0.10

            slippage = self.execution.estimate_slippage(bid, ask, opt.get("volume", 0))
            base_entry_price, entry_price_source = self._option_executable_price(opt, side="BUY")
            if base_entry_price is None or base_entry_price <= 0:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="invalid_entry_proxy")
                self._update_zero_hero_diag(data, rejected_reason="invalid_entry_proxy")
                continue
            entry_price = float(base_entry_price)
            _trigger_entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                entry_price, side="BUY", quick_mode=True
            )
            if entry_ref_price is None:
                entry_ref_price = entry_price
            if entry_condition and _trigger_entry_price is not None:
                entry_price = float(_trigger_entry_price)

            delta_proxy = d if d else 0.3
            target = entry_price + max(5, tgt_points * delta_proxy)
            stop_loss = max(entry_price - max(3, (tgt_points * delta_proxy) * 0.5), entry_price * 0.2)
            confidence_base = max(0.52, min(1.0, abs(ltp_change_window) / max(atr, 1.0)))
            confidence_before_soft_veto = confidence_base
            confidence_after_soft_veto = max(0.05, min(1.0, confidence_base - penalty))
            confidence = confidence_after_soft_veto

            alpha_conf = None
            alpha_unc = None
            size_mult = 1.0
            confidence_after_alpha = confidence
            adj_conf, alpha_conf, alpha_unc, size_mult = self._apply_alpha_ensemble(
                confidence, None, None, None, data, quick_mode=True
            )
            if adj_conf is not None:
                confidence = max(0.05, min(1.0, float(adj_conf)))
            confidence_after_alpha = confidence
            confidence_penalty_reasons = list(soft_flags)
            if (
                confidence_after_alpha is not None
                and confidence_after_soft_veto is not None
                and abs(float(confidence_after_alpha) - float(confidence_after_soft_veto)) > 1e-9
            ):
                confidence_penalty_reasons.append("alpha_adjustment")
            confidence_penalty_total = max(0.0, float(confidence_base) - float(confidence))

            expiry_resolved = self._option_expiry(opt, data)
            if not expiry_resolved:
                expiry_resolved = self._resolve_expiry_for_symbol(symbol, data)
            option_right = self._coerce_option_type(opt.get("type") or opt.get("option_type") or opt.get("right")) or opt_type
            contract = self._resolve_option_contract(
                symbol,
                opt.get("strike"),
                option_right,
                expiry_resolved,
                data,
            )
            expiry_resolved = contract.get("expiry") or expiry_resolved
            tradingsymbol = contract.get("tradingsymbol") or opt.get("tradingsymbol")
            instrument_token = contract.get("instrument_token") or opt.get("instrument_token")
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                expiry_resolved,
                opt.get("strike"),
                option_right,
                1,
            )
            if ident_err or not expiry_resolved or not tradingsymbol or not instrument_id:
                self._update_strategy_candidate_debug(stats, rejected=1, reason="unresolved_contract")
                self._update_zero_hero_diag(data, rejected_reason="unresolved_contract")
                continue
            extra_blockers = []
            if instrument_token is None:
                extra_blockers.append("instrument_token_missing")
            intent = self.trade_intent_flags(data, opt=opt, additional_blockers=extra_blockers)
            trade = Trade(
                trade_id=f"{symbol}-{option_right}-{int(opt['strike'])}-ZEROEXP-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=option_right,
                instrument_id=instrument_id,
                instrument_token=instrument_token,
                strike=opt["strike"],
                expiry=expiry_resolved,
                expiry_date=expiry_resolved,
                tradingsymbol=tradingsymbol,
                option_type=option_right,
                side="BUY",
                entry_price=round(entry_price, 2),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                qty=1,
                qty_lots=1,
                qty_units=qty_units,
                validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
                capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
                expected_slippage=round(slippage, 2),
                confidence=round(confidence, 3),
                strategy="ZERO_HERO_EXPIRY",
                regime=data.get("regime", "NEUTRAL"),
                tier="EXPLORATION",
                day_type=data.get("day_type", "UNKNOWN"),
                entry_condition=entry_condition,
                entry_ref_price=entry_ref_price,
                signal_price=self._option_signal_price(opt, data),
                entry_price_source=entry_price_source,
                expected_entry=round(entry_price, 2),
                expected_entry_source=entry_price_source,
                opt_ltp=opt.get("ltp"),
                opt_bid=opt.get("bid"),
                opt_ask=opt.get("ask"),
                **self._option_liquidity_fields(opt),
                quote_ok=opt.get("quote_ok", True),
                alpha_confidence=alpha_conf,
                alpha_uncertainty=alpha_unc,
                size_mult=size_mult,
                tradable=bool(intent["tradable"]),
                tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                planning_only=bool(intent["planning_only"]),
                execution_allowed=bool(intent["execution_allowed"]),
                reason=intent["execution_reason"],
                source_flags=dict(intent["source_flags"]),
                underlying_spot=underlying_spot,
                spot_source=spot_source,
                option_ltp_source=opt.get("option_ltp_source") or opt.get("quote_source"),
                chain_source=data.get("chain_source") or opt.get("chain_source"),
                **self._staged_confidence_payload(
                    confidence=confidence,
                    model_raw=confidence_base,
                    model_component=confidence_base,
                    micro_blend_method="model_only",
                    after_alpha=confidence_after_alpha,
                    before_soft_veto=confidence_before_soft_veto,
                    after_soft_veto=confidence_after_soft_veto,
                    penalty_soft_veto_total=penalty,
                    penalty_soft_veto_reasons=soft_flags,
                    base=confidence_base,
                    penalty_total=confidence_penalty_total,
                    penalty_reasons=confidence_penalty_reasons,
                ),
            )
            trade = self._decorate_trade_context(trade, data, confidence)
            if trade is not None:
                trade.source_flags.update(
                    {
                        "zero_hero_expiry": True,
                        "zero_hero_variant": "expiry_day",
                        "zero_hero_considered": int((self._zero_hero_diag(data) or {}).get("zero_hero_considered", 0)),
                        "zero_hero_selected_premium_band": dict(
                            (self._zero_hero_diag(data) or {}).get("zero_hero_selected_premium_band") or {}
                        ),
                        "zero_hero_activation_window": dict(
                            (self._zero_hero_diag(data) or {}).get("zero_hero_activation_window") or {}
                        ),
                        "candidate_soft_flags": list(soft_flags),
                        "spot_issue": spot_issue,
                    }
                )
                candidates.append(trade)
                self._update_strategy_candidate_debug(stats, scored=1)
        if not candidates:
            self._update_strategy_candidate_debug(stats, rejected=1, reason="no_viable_candidates")
            if not (self._zero_hero_diag(data) or {}).get("zero_hero_rejected_reason"):
                self._update_zero_hero_diag(data, rejected_reason="no_viable_candidates")
            return None
        trade, _ranked_candidates = select_best_opportunity(
            candidates,
            scope=f"zero_hero_expiry:{symbol}",
            top_n=int(getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)),
        )
        self._set_last_ranked_candidates(_ranked_candidates)
        if trade is None:
            return None
        self._update_zero_hero_diag(data, clear_rejected_reason=True)
        self._expiry_zero_hero_count += 1
        self._expiry_zero_hero_by_symbol[symbol] = self._expiry_zero_hero_by_symbol.get(symbol, 0) + 1
        return trade

    def build_spread_suggestions(self, market_data):
        """
        Build spread suggestions (iron condor / iron fly / bull-bear call spreads).
        Returns list of dicts suitable for review queue (non-executable).
        """
        if not getattr(cfg, "SPREAD_SUGGESTIONS_ENABLE", True):
            return []
        symbol = market_data.get("symbol")
        if symbol not in ("NIFTY", "BANKNIFTY", "SENSEX"):
            return []
        day_type = market_data.get("day_type", "UNKNOWN")
        ltp = market_data.get("ltp", 0)
        chain = market_data.get("option_chain", [])
        if not chain:
            return []
        min_iv = getattr(cfg, "SPREAD_MIN_IV", 0.15)
        chain_ivs = [c.get("iv") for c in chain if c.get("iv") is not None]
        chain_iv_mean = (sum(chain_ivs) / len(chain_ivs)) if chain_ivs else None
        iv_mean = market_data.get("iv_mean", None) or chain_iv_mean
        if iv_mean is not None and iv_mean < min_iv:
            return []
        strikes = sorted({c.get("strike") for c in chain if c.get("strike") is not None})
        if not strikes:
            return []
        # Helper: pick strike nearest to ltp
        def _nearest_strike(val):
            return min(strikes, key=lambda s: abs(s - val))
        # Helper: get option by strike/type
        def _opt(strike, opt_type):
            for c in chain:
                if c.get("strike") == strike and c.get("type") == opt_type:
                    return c
            return None
        # Basic pricing helpers
        def _credit(sell, buy):
            return max((sell.get("bid", 0) or 0) - (buy.get("ask", 0) or 0), 0)
        def _debit(buy, sell):
            return max((buy.get("ask", 0) or 0) - (sell.get("bid", 0) or 0), 0)
        def _fmt_money(val):
            if val is None:
                return None
            return f"\u20b9{round(val, 2)}"
        def _est_pnl_condor(spot, k_put, k_call, credit):
            if spot < k_put:
                return (spot - k_put) + credit
            if spot > k_call:
                return (k_call - spot) + credit
            return credit
        def _est_pnl_fly(spot, k_atm, credit, width_val):
            if spot < (k_atm - width_val):
                return (spot - (k_atm - width_val)) + credit
            if spot > (k_atm + width_val):
                return ((k_atm + width_val) - spot) + credit
            return credit
        def _est_pnl_call_spread(spot, k_buy, k_sell, debit):
            if spot <= k_buy:
                return -debit
            if spot >= k_sell:
                return (k_sell - k_buy) - debit
            return (spot - k_buy) - debit
        def _est_pnl_put_spread(spot, k_buy, k_sell, debit):
            if spot >= k_buy:
                return -debit
            if spot <= k_sell:
                return (k_buy - k_sell) - debit
            return (k_buy - spot) - debit

        ideas = []
        max_items = getattr(cfg, "SPREAD_MAX_PER_SYMBOL", 2)
        width = getattr(cfg, "IRON_CONDOR_WIDTH", 100)
        fly_width = getattr(cfg, "IRON_FLY_WIDTH", 100)
        min_credit = getattr(cfg, "SPREAD_MIN_CREDIT", 5)
        min_debit = getattr(cfg, "SPREAD_MIN_DEBIT", 5)

        atm = _nearest_strike(ltp)
        if day_type in ("RANGE_DAY", "RANGE_VOLATILE", "EXPIRY_DAY"):
            # Iron Condor: sell closer OTM, buy further OTM
            ce_sell = _opt(atm + width, "CE")
            ce_buy = _opt(atm + width * 2, "CE")
            pe_sell = _opt(atm - width, "PE")
            pe_buy = _opt(atm - width * 2, "PE")
            if ce_sell and ce_buy and pe_sell and pe_buy:
                credit = _credit(ce_sell, ce_buy) + _credit(pe_sell, pe_buy)
                if credit >= min_credit:
                    width_val = width
                    max_profit = credit
                    max_loss = (width_val * 2) - credit
                    breakeven_low = (atm - width_val) - credit
                    breakeven_high = (atm + width_val) + credit
                    est_pnl = _est_pnl_condor(ltp, atm - width_val, atm + width_val, credit)
                    ideas.append({
                        "trade_id": f"{symbol}-IRON_CONDOR-{int(datetime.now().timestamp())}",
                        "symbol": symbol,
                        "instrument": "SPREAD",
                        "side": "SELL",
                        "entry_price": round(credit, 2),
                        "stop_loss": round(credit * 1.5, 2),
                        "target": round(credit * 0.5, 2),
                        "confidence": 0.6,
                        "strategy": "IRON_CONDOR",
                        "regime": market_data.get("regime", "NEUTRAL"),
                        "tier": "MAIN",
                        "max_profit": round(max_profit, 2),
                        "max_loss": round(max_loss, 2),
                        "max_profit_label": _fmt_money(max_profit),
                        "max_loss_label": _fmt_money(max_loss),
                        "breakeven_low": round(breakeven_low, 2),
                        "breakeven_high": round(breakeven_high, 2),
                        "est_pnl_at_ltp": round(est_pnl, 2),
                        "legs": [
                            f"SELL CE {ce_sell['strike']}",
                            f"BUY CE {ce_buy['strike']}",
                            f"SELL PE {pe_sell['strike']}",
                            f"BUY PE {pe_buy['strike']}",
                        ],
                        "timestamp": datetime.now().isoformat(),
                    })
            # Iron Fly: sell ATM straddle, buy wings
            ce_sell = _opt(atm, "CE")
            pe_sell = _opt(atm, "PE")
            ce_buy = _opt(atm + fly_width, "CE")
            pe_buy = _opt(atm - fly_width, "PE")
            if ce_sell and pe_sell and ce_buy and pe_buy:
                credit = _credit(ce_sell, ce_buy) + _credit(pe_sell, pe_buy)
                if credit >= min_credit:
                    max_profit = credit
                    max_loss = (fly_width * 2) - credit
                    breakeven_low = atm - credit
                    breakeven_high = atm + credit
                    est_pnl = _est_pnl_fly(ltp, atm, credit, fly_width)
                    ideas.append({
                        "trade_id": f"{symbol}-IRON_FLY-{int(datetime.now().timestamp())}",
                        "symbol": symbol,
                        "instrument": "SPREAD",
                        "side": "SELL",
                        "entry_price": round(credit, 2),
                        "stop_loss": round(credit * 1.8, 2),
                        "target": round(credit * 0.5, 2),
                        "confidence": 0.6,
                        "strategy": "IRON_FLY",
                        "regime": market_data.get("regime", "NEUTRAL"),
                        "tier": "MAIN",
                        "max_profit": round(max_profit, 2),
                        "max_loss": round(max_loss, 2),
                        "max_profit_label": _fmt_money(max_profit),
                        "max_loss_label": _fmt_money(max_loss),
                        "breakeven_low": round(breakeven_low, 2),
                        "breakeven_high": round(breakeven_high, 2),
                        "est_pnl_at_ltp": round(est_pnl, 2),
                        "legs": [
                            f"SELL CE {ce_sell['strike']}",
                            f"SELL PE {pe_sell['strike']}",
                            f"BUY CE {ce_buy['strike']}",
                            f"BUY PE {pe_buy['strike']}",
                        ],
                        "timestamp": datetime.now().isoformat(),
                    })
        else:
            # Trend day: bull/bear call spreads based on bias
            vwap = market_data.get("vwap", ltp)
            bullish = ltp >= vwap
            if bullish:
                buy = _opt(atm, "CE")
                sell = _opt(atm + width, "CE")
                if buy and sell:
                    debit = _debit(buy, sell)
                    if debit >= min_debit:
                        max_profit = (sell['strike'] - buy['strike']) - debit
                        max_loss = debit
                        breakeven = buy['strike'] + debit
                        est_pnl = _est_pnl_call_spread(ltp, buy['strike'], sell['strike'], debit)
                        ideas.append({
                            "trade_id": f"{symbol}-BULL_CALL-{int(datetime.now().timestamp())}",
                            "symbol": symbol,
                            "instrument": "SPREAD",
                            "side": "BUY",
                            "entry_price": round(debit, 2),
                            "stop_loss": round(debit * 0.5, 2),
                            "target": round((sell['strike'] - buy['strike']) - debit, 2),
                            "confidence": 0.6,
                            "strategy": "BULL_CALL_SPREAD",
                            "regime": market_data.get("regime", "NEUTRAL"),
                            "tier": "MAIN",
                            "max_profit": round(max_profit, 2),
                            "max_loss": round(max_loss, 2),
                            "max_profit_label": _fmt_money(max_profit),
                            "max_loss_label": _fmt_money(max_loss),
                            "breakeven_low": round(breakeven, 2),
                            "breakeven_high": None,
                            "est_pnl_at_ltp": round(est_pnl, 2),
                            "legs": [
                                f"BUY CE {buy['strike']}",
                                f"SELL CE {sell['strike']}",
                            ],
                            "timestamp": datetime.now().isoformat(),
                        })
            else:
                buy = _opt(atm, "PE")
                sell = _opt(atm - width, "PE")
                if buy and sell:
                    debit = _debit(buy, sell)
                    if debit >= min_debit:
                        max_profit = (buy['strike'] - sell['strike']) - debit
                        max_loss = debit
                        breakeven = buy['strike'] - debit
                        est_pnl = _est_pnl_put_spread(ltp, buy['strike'], sell['strike'], debit)
                        ideas.append({
                            "trade_id": f"{symbol}-BEAR_PUT-{int(datetime.now().timestamp())}",
                            "symbol": symbol,
                            "instrument": "SPREAD",
                            "side": "BUY",
                            "entry_price": round(debit, 2),
                            "stop_loss": round(debit * 0.5, 2),
                            "target": round((buy['strike'] - sell['strike']) - debit, 2),
                            "confidence": 0.6,
                            "strategy": "BEAR_PUT_SPREAD",
                            "regime": market_data.get("regime", "NEUTRAL"),
                            "tier": "MAIN",
                            "max_profit": round(max_profit, 2),
                            "max_loss": round(max_loss, 2),
                            "max_profit_label": _fmt_money(max_profit),
                            "max_loss_label": _fmt_money(max_loss),
                            "breakeven_low": round(breakeven, 2),
                            "breakeven_high": None,
                            "est_pnl_at_ltp": round(est_pnl, 2),
                            "legs": [
                                f"BUY PE {buy['strike']}",
                                f"SELL PE {sell['strike']}",
                            ],
                            "timestamp": datetime.now().isoformat(),
                        })

        return ideas[:max_items]

    def build_scalp(self, market_data, debug_reasons=False):
        """
        Scalp trades for low-momentum/range conditions.
        """
        if not getattr(cfg, "SCALP_ENABLE", True):
            return None
        symbol = market_data.get("symbol")
        ltp = market_data.get("ltp", 0)
        atr = market_data.get("atr", max(1.0, ltp * 0.002))
        ltp_change_window = market_data.get("ltp_change_window", 0) or 0
        if atr <= 0:
            return None
        if abs(ltp_change_window) > atr * getattr(cfg, "SCALP_MAX_MOM_ATR", 0.08):
            if debug_reasons:
                _log_advisory_debug("scalp_reject symbol=%s reason=momentum_too_high", symbol)
                _log_signal_event(
                    "scalp_reject",
                    symbol,
                    {
                        "reason": "momentum_too_high",
                        "ltp_change_window": ltp_change_window,
                        "atr": atr,
                        "threshold": atr * getattr(cfg, "SCALP_MAX_MOM_ATR", 0.08),
                    },
                )
            return None

        # Direction: prefer short-term momentum, then vwap slope, then vwap tilt
        vwap = market_data.get("vwap", ltp)
        vwap_slope = market_data.get("vwap_slope", 0) or 0
        ltp_change_5m = market_data.get("ltp_change_5m", 0) or 0
        dir_atr = getattr(cfg, "SCALP_DIR_ATR", 0.05)
        direction = None
        if abs(ltp_change_window) >= atr * dir_atr:
            direction = "BUY_CALL" if ltp_change_window > 0 else "BUY_PUT"
        elif abs(ltp_change_5m) >= atr * dir_atr:
            direction = "BUY_CALL" if ltp_change_5m > 0 else "BUY_PUT"
        elif abs(vwap_slope) > 0:
            direction = "BUY_CALL" if vwap_slope > 0 else "BUY_PUT"
        else:
            direction = "BUY_CALL" if ltp >= vwap else "BUY_PUT"
        opt_type = "CE" if direction == "BUY_CALL" else "PE"

        min_p = getattr(cfg, "SCALP_MIN_PREMIUM", 20)
        max_p = getattr(cfg, "SCALP_MAX_PREMIUM", 180)
        candidates = []
        rejected = []
        for opt in market_data.get("option_chain", []):
            if opt.get("type") != opt_type:
                continue
            if opt.get("ltp", 0) < min_p or opt.get("ltp", 0) > max_p:
                continue
            if not self.execution.spread_ok(opt.get("bid", 0), opt.get("ask", 0), opt.get("ltp", 0) or 1):
                continue
            feats = pd.DataFrame([build_trade_features(market_data, opt)])
            use_ml = True
            if getattr(cfg, "ML_USE_ONLY_WITH_HISTORY", True):
                use_ml = self._ml_history_count() >= getattr(cfg, "ML_MIN_TRAIN_TRADES", 200)
            model_type = "xgb"
            model_version = getattr(self.predictor, "model_version", None)
            shadow_version = getattr(self.predictor, "shadow_version", None)
            shadow_confidence = None
            alpha_conf = None
            alpha_unc = None
            size_mult = 1.0
            xgb_conf = None
            micro_conf = None
            confidence_after_micro = None
            confidence_after_alpha = None
            confidence_model_component = None
            confidence_micro_component = None
            confidence_micro_blend_method = None
            if use_ml:
                ok_features, feature_reason = self._validate_ml_features(feats)
                if not ok_features:
                    self._reject_ctx = {
                        "symbol": symbol,
                        "reason": feature_reason,
                        "feature_contract_failed": True,
                    }
                    if debug_reasons:
                        rec = self._reject_record(symbol, opt, opt_type, feature_reason, atr=atr)
                        rejected.append(rec)
                    continue
                xgb_conf = self.predictor.predict_confidence(feats)
                confidence = xgb_conf
                confidence_model_component = self._clamp_confidence(confidence)
                if getattr(cfg, "ML_AB_ENABLE", False):
                    shadow_confidence = self.predictor.predict_confidence_shadow(feats)
            else:
                confidence = max(0.5, min(1.0, 0.6 + (atr / max(ltp, 1)) * 10))
                confidence_model_component = self._clamp_confidence(confidence)
                confidence_micro_blend_method = "model_only"
            if cfg.USE_MICRO_MODEL:
                micro_features = [
                    float(opt.get("spread_pct", (opt["ask"] - opt["bid"]) / opt["ltp"] if opt["ltp"] else 0)),
                    float(opt.get("volume", 0)),
                    float(opt.get("oi_change", 0))
                ]
                micro_conf = self._get_micro_predictor().predict_confidence(micro_features)
                confidence_micro_component = self._clamp_confidence(micro_conf)
                confidence, confidence_micro_blend_method = self._blend_micro_confidence(confidence, micro_conf)
                confidence_after_micro = confidence
            # Alpha ensemble fusion (exploratory: downsize but don't veto)
            adj_conf, alpha_conf, alpha_unc, size_mult = self._apply_alpha_ensemble(
                confidence, xgb_conf, None, micro_conf, market_data, quick_mode=True
            )
            if adj_conf is not None:
                confidence = adj_conf
            confidence_after_alpha = confidence
            allowed_life, _ = self._apply_lifecycle_gate("SCALP", mode="QUICK")
            if not allowed_life:
                if debug_reasons:
                    _log_advisory_debug("scalp_reject symbol=%s reason=lifecycle_gate", symbol)
                return None
            allowed, adj_score, decay_size_mult, _ = self._apply_decay_gate("SCALP", confidence, size_mult)
            if not allowed:
                if debug_reasons:
                    _log_advisory_debug("scalp_reject symbol=%s reason=strategy_quarantined", symbol)
                return None
            if adj_score is not None:
                confidence = adj_score
            size_mult = min(size_mult, decay_size_mult)
            scalp_final_gate_threshold = float(getattr(cfg, "SCALP_MIN_PROBA", 0.58))
            if confidence < scalp_final_gate_threshold:
                continue
            slippage = self.execution.estimate_slippage(opt["bid"], opt["ask"], opt.get("volume", 0))
            base_entry_price, entry_price_source = self._option_executable_price(opt, side="BUY")
            if base_entry_price is None or base_entry_price <= 0:
                continue
            entry_price = float(base_entry_price)
            _trigger_entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                entry_price, side="BUY", quick_mode=True
            )
            if entry_ref_price is None:
                entry_ref_price = entry_price
            if entry_condition and _trigger_entry_price is not None:
                entry_price = float(_trigger_entry_price)
            option_risk = self._option_risk_proxy(entry_price, opt.get("bid", 0), opt.get("ask", 0))
            stop_loss, target = self._opt_risk_levels(
                entry_price, opt.get("bid", 0), opt.get("ask", 0), option_risk,
                stop_mult=getattr(cfg, "SCALP_STOP_ATR", 0.3),
                target_mult=getattr(cfg, "SCALP_TARGET_ATR", 0.6),
            )
            if not (target > entry_price > stop_loss):
                logger.error(
                    "invalid_opt_levels symbol=%s side=%s entry=%s stop=%s target=%s strike=%s right=%s",
                    symbol,
                    "BUY",
                    entry_price,
                    stop_loss,
                    target,
                    opt.get("strike"),
                    opt.get("type"),
                )
                continue
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            option_right = self._coerce_option_type(opt.get("type") or opt.get("option_type") or opt.get("right")) or opt_type
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                self._option_expiry(opt, market_data),
                opt.get("strike"),
                option_right,
                1,
            )
            if ident_err:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=option_risk)
                    rejected.append(rec)
                continue
            if opt.get("instrument_token") is None:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=option_risk)
                    rejected.append(rec)
                continue
            intent = self.trade_intent_flags(market_data, opt=opt)
            trade = Trade(
                trade_id=f"{symbol}-{option_right}-{int(opt['strike'])}-SCALP-{ts}",
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=option_right,
                instrument_id=instrument_id,
                instrument_token=opt.get("instrument_token"),
                strike=opt["strike"],
                expiry=self._option_expiry(opt, market_data),
                option_type=option_right,
                side="BUY",
                entry_price=round(entry_price, 2),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                qty=1,
                qty_lots=1,
                qty_units=qty_units,
                validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
                capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
                expected_slippage=round(slippage, 2),
                confidence=round(confidence, 3),
                strategy="SCALP",
                regime=market_data.get("regime", "NEUTRAL"),
                tier="EXPLORATION",
                day_type=market_data.get("day_type", "UNKNOWN"),
                entry_condition=entry_condition,
                entry_ref_price=entry_ref_price,
                signal_price=self._option_signal_price(opt, market_data),
                entry_price_source=entry_price_source,
                expected_entry=round(entry_price, 2),
                expected_entry_source=entry_price_source,
                opt_ltp=opt.get("ltp"),
                opt_bid=opt.get("bid"),
                opt_ask=opt.get("ask"),
                **self._option_liquidity_fields(opt),
                quote_ok=opt.get("quote_ok", True),
                model_type=model_type,
                model_version=model_version,
                shadow_model_version=shadow_version,
                shadow_confidence=shadow_confidence,
                alpha_confidence=alpha_conf,
                alpha_uncertainty=alpha_unc,
                size_mult=size_mult,
                tradable=bool(intent["tradable"]),
                tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                planning_only=bool(intent["planning_only"]),
                execution_allowed=bool(intent["execution_allowed"]),
                reason=intent["execution_reason"],
                source_flags=dict(intent["source_flags"]),
                **self._staged_confidence_payload(
                    confidence=confidence,
                    model_raw=confidence_model_component,
                    model_component=confidence_model_component,
                    micro_component=confidence_micro_component,
                    micro_blend_method=confidence_micro_blend_method,
                    after_micro=confidence_after_micro,
                    after_alpha=confidence_after_alpha,
                    before_soft_veto=confidence,
                    after_soft_veto=confidence,
                    penalty_soft_veto_total=0.0,
                    penalty_soft_veto_reasons=[],
                    gate_threshold=scalp_final_gate_threshold,
                    final_gate_threshold=scalp_final_gate_threshold,
                    base=confidence,
                    penalty_total=0.0,
                    penalty_reasons=[],
                    use_confidence_as_model=confidence_model_component is not None,
                    ml_model_name=model_type,
                    ml_model_version=model_version,
                ),
            )
            trade = self._decorate_trade_context(trade, market_data, confidence)
            if trade is not None:
                candidates.append(trade)
        if not candidates:
            return None
        trade, _ranked_candidates = select_best_opportunity(
            candidates,
            scope=f"scalp:{symbol}",
            top_n=int(getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)),
        )
        self._set_last_ranked_candidates(_ranked_candidates)
        return trade

    def _reject_record(self, symbol, opt, opt_type, reason, atr=None):
        try:
            ltp = opt.get("ltp")
            bid = opt.get("bid", 0)
            ask = opt.get("ask", 0)
            base_atr = atr if atr is not None else 0
            if ltp:
                stop_loss, target = self._opt_risk_levels(
                    ltp, bid, ask, base_atr, stop_mult=1.0, target_mult=1.5
                )
            else:
                stop_loss, target = (None, None)
        except Exception:
            stop_loss, target = (None, None)
        rec = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "strike": opt.get("strike"),
            "type": opt_type,
            "reason": reason,
            "ltp": opt.get("ltp"),
            "bid": opt.get("bid"),
            "ask": opt.get("ask"),
            "quote_ok": opt.get("quote_ok", True),
            "volume": opt.get("volume"),
            "oi": opt.get("oi"),
            "iv": opt.get("iv"),
            "moneyness": opt.get("moneyness"),
            "atr": atr,
            "stop": stop_loss,
            "target": target,
        }
        try:
            if isinstance(self._reject_ctx, dict):
                for k, v in self._reject_ctx.items():
                    if k not in rec:
                        rec[k] = v
        except Exception:
            pass
        return rec

    def _write_rejected(self, rejected):
        try:
            path = logs_dir() / "rejected_candidates.jsonl"
            path.parent.mkdir(exist_ok=True)
            # Keep only top 5 by confidence then ltp
            def _score(x):
                return (x.get("confidence") or 0, x.get("ltp") or 0)
            top = sorted(rejected, key=_score, reverse=True)[:5]
            with open(path, "a") as f:
                for rec in top:
                    f.write(json.dumps(rec) + "\n")
        except Exception:
            pass

    def _write_debug_candidates(self, rejected, top_n=5):
        try:
            path = logs_dir() / "debug_candidates.jsonl"
            path.parent.mkdir(exist_ok=True)
            def _score(x):
                return (x.get("confidence") or 0, x.get("ltp") or 0, x.get("volume") or 0)
            top = sorted(rejected, key=_score, reverse=True)[:top_n]
            with open(path, "a") as f:
                for rec in top:
                    rec = dict(rec)
                    rec["debug"] = True
                    f.write(json.dumps(rec) + "\n")
        except Exception:
            pass


TradeBuilder.build = _wrap_trade_builder_build_with_status(TradeBuilder.build)
