from core.paths import logs_dir, data_root
# Migration note:
# Trade builder now consumes central market context for LIVE/OFFHOURS/SIM gating.
# Zero-to-hero (lotto) ideas are PAPER-only with explicit OTM + premium-band filters.

from datetime import datetime, date
from dataclasses import replace
from functools import wraps
from pathlib import Path
import hashlib
import json
import logging
import os
import sys
import pandas as pd
from config import config as cfg
from config.profile import get_runtime_profile, get_option_filter_profile
from core.execution_engine import ExecutionEngine
from core.alpha_ensemble import AlphaEnsemble
from core.decision_trace import build_trade_decision_trace
from core.decision_telemetry import build_scan_summary, emit_scan_summary
from core.reject_shadow import record_candidate_decision
from core.trade_schema import Trade, build_instrument_id, validate_trade_identity
from typing import Optional
from strategies.ensemble import ensemble_signal, equity_signal, futures_signal, mean_reversion_signal, event_breakout_signal, micro_pattern_signal
from core.feature_builder import build_trade_features, validate_trade_features
from core.trade_scoring import compute_trade_score
from core.strategy_tracker import StrategyTracker
from core.strategy_lifecycle import StrategyLifecycle
from core.instruments import select_expiry as select_registry_expiry
from core.market_context import derive_market_context
from core.incidents import SEV2, create_incident
from core.reject_logger import append_reject_reasons
from core.reject_telemetry import append_reject_telemetry
from core.option_entry import get_option_ltp_sla_sec
from core.option_liquidity_cache import hydrate_option_liquidity_fields
from core.heartbeat_status import derive_cycle_semantics, top_blockers_from_counts
from core.time_utils import compute_age_sec, is_market_open_ist, now_ist, now_utc_epoch
from core.regime import RegimeClassifier, normalize_regime
from core.kite_client import kite_client
from core.events import write_json_atomic
import time as _time
import time


logger = logging.getLogger(__name__)

_AUTO_TUNE_CACHE = {"ts": 0, "data": {}}


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

    def _heartbeat_feed_snapshot(self) -> dict:
        payload = {}
        try:
            payload = json.loads((logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        return {
            "feed_ok": payload.get("feed_ok"),
            "ws_connected": payload.get("ws_connected"),
            "subscribed_option_tokens_count": payload.get("subscribed_option_tokens_count"),
            "missing_option_tokens_count": payload.get("missing_option_tokens_count"),
        }

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
            return replace(
                trade,
                regime_confidence=reg_conf,
                day_confidence=data.get("day_confidence"),
                orb_bias=data.get("orb_bias"),
                raw_signal_confidence=conf,
            )
        except Exception:
            return trade

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
        skip_derivation = bool(
            str(reason_code or "").strip() == "unresolved_contract"
            or meta.get("unresolved_contract")
            or meta.get("skip_derived_levels")
        )
        if not skip_derivation and (stop is None or target is None):
            try:
                entry_f = float(entry)
                atr_f = float(data.get("atr") or 0.0)
                if atr_f > 0:
                    if stop is None:
                        stop = round(max(0.01, entry_f - atr_f), 4)
                        derived_levels = True
                    if target is None:
                        target = round(entry_f + (atr_f * 1.5), 4)
                        derived_levels = True
            except Exception:
                pass
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
            "entry": entry,
            "stop": stop,
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
        if opt_side != str(expected_type or "").upper():
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
            self._coerce_positive_float(opt.get("mark_price"))
            or self._coerce_positive_float(opt.get("ltp"))
            or self._coerce_positive_float(opt.get("last_price"))
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
        live_sla_default = float(getattr(cfg, "OPTION_LTP_SLA_SEC", getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)))
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
        if quote_age_sec is None or quote_age_sec > option_tick_sla_sec:
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
        if isinstance(chain, (list, tuple)):
            for row in chain:
                if not isinstance(row, dict):
                    continue
                if row.get("type") != opt_type:
                    continue
                if row.get("strike") is None:
                    continue
                try:
                    if float(row.get("strike")) != float(strike_val):
                        continue
                except Exception:
                    continue
                row_exp = self._option_expiry(row, data)
                if exp_text and row_exp and str(row_exp) != exp_text:
                    continue
                if not exp_text and row_exp:
                    exp_text = self._coerce_date_str(row_exp)
                tradingsymbol = row.get("tradingsymbol") or tradingsymbol
                instrument_token = row.get("instrument_token") or instrument_token
                if tradingsymbol or instrument_token:
                    break
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
        instrument_id = build_instrument_id(symbol, "OPT", exp_text, strike_val, opt_type) if exp_text else None
        return {
            "expiry": exp_text,
            "expiry_date": exp_text,
            "tradingsymbol": tradingsymbol,
            "instrument_token": instrument_token,
            "instrument_id": instrument_id,
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

    def _build_planning_no_signal_trade(
        self,
        market_data: dict,
        *,
        ltp: float,
        vwap: float,
    ):
        if not bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)):
            return None
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        underlying_ltp = float(ltp or 0.0)
        underlying_vwap = float(vwap or underlying_ltp or 0.0)
        if underlying_ltp <= 0:
            return None
        direction = "BUY_CALL" if underlying_ltp >= underlying_vwap else "BUY_PUT"
        side = "BUY" if direction == "BUY_CALL" else "SELL"
        underlying_atr = float(market_data.get("atr") or max(1.0, underlying_ltp * 0.002))
        entry_price = underlying_ltp
        stop_loss = max(0.01, entry_price - underlying_atr) if side == "BUY" else max(0.01, entry_price + underlying_atr)
        target = entry_price + (underlying_atr * 1.5) if side == "BUY" else max(0.01, entry_price - (underlying_atr * 1.5))
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

        instrument = "EQ"
        expiry = ""
        strike = 0
        right = None
        option_type = None
        chosen_opt = None
        tradingsymbol = None
        instrument_token = None
        opt_type = "CE" if direction == "BUY_CALL" else "PE"
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
                    target = round(entry_price + max(option_risk_proxy * 1.4, option_width, 0.01), 2)
                if side == "BUY" and stop_loss >= entry_price:
                    stop_loss = round(max(0.01, entry_price - max(option_risk_proxy, option_width, 0.01)), 2)
                if side == "SELL" and target >= entry_price:
                    target = round(max(0.01, entry_price - max(option_risk_proxy * 1.4, option_width, 0.01)), 2)
                if side == "SELL" and stop_loss <= entry_price:
                    stop_loss = round(entry_price + max(option_risk_proxy, option_width, 0.01), 2)
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
            # Final fallback: directional planning-only index candidate.
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
                logger.error(
                    "invalid_opt_levels symbol=%s side=%s entry=%s stop=%s target=%s strike=%s right=%s",
                    symbol,
                    side,
                    entry_price,
                    stop_loss,
                    target,
                    strike,
                    right,
                )
                return None
            if side == "SELL" and not (stop_loss > entry_price > target):
                logger.error(
                    "invalid_opt_levels symbol=%s side=%s entry=%s stop=%s target=%s strike=%s right=%s",
                    symbol,
                    side,
                    entry_price,
                    stop_loss,
                    target,
                    strike,
                    right,
                )
                return None

        intent = self.trade_intent_flags(market_data, opt=chosen_opt)
        intent["planning_only"] = True
        intent["execution_allowed"] = False
        intent["execution_reason"] = "NO_SIGNAL_PLANNING_FALLBACK"
        liquidity_fields = self._option_liquidity_fields(chosen_opt) if instrument == "OPT" else {}
        trade = Trade(
            trade_id=f"{symbol}-PLAN-{ts}",
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
            confidence=round(float(getattr(cfg, "PLANNING_SIGNAL_SCORE_BASE", 0.56)), 3),
            strategy="NO_SIGNAL_PLANNING",
            regime=str(market_data.get("regime") or "NEUTRAL"),
            tier="EXPLORATION",
            day_type=str(market_data.get("day_type") or "UNKNOWN"),
            **liquidity_fields,
            quote_ok=bool(market_data.get("quote_ok", True)),
            tradable=bool(intent.get("tradable", True)),
            tradable_reasons_blocking=list(intent.get("tradable_reasons_blocking") or []),
            planning_only=True,
            execution_allowed=False,
            reason="NO_SIGNAL_PLANNING_FALLBACK",
            source_flags=dict(intent.get("source_flags") or {}),
        )
        return self._decorate_trade_context(trade, market_data, float(getattr(cfg, "PLANNING_SIGNAL_SCORE_BASE", 0.56)))

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
        if strict_quote_checks and ltp_source != "live":
            reasons.append("ltp_not_live")
        if strict_quote_checks and (ltp is None or float(ltp) <= 0):
            reasons.append("invalid_ltp")
        if risk_guard_passed is False:
            reasons.append("risk_guard_failed")
        for blocker in additional_blockers or []:
            if blocker and blocker not in reasons:
                reasons.append(str(blocker))

        planning_only = bool(planning_only_mode)
        execution_allowed = bool((market_ctx.mode == "LIVE") and market_open and (len(reasons) == 0) and (not planning_only))
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
        self._log_blocked_candidate(
            symbol,
            "trend_vwap_fallback",
            "Fallback signal emitted from trend/event regime with VWAP/ORB guardrails",
            market_data=market_data,
            extra=payload,
        )
        return {
            "direction": direction,
            "reason": reason,
            "score": score,
            "regime_day": primary_regime,
        }

    def _signal_for_symbol(self, market_data, force_family: str | None = None):
        instrument = market_data.get("instrument", "OPT")
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
                if unstable_regime or regime_entropy > getattr(cfg, "REGIME_ENTROPY_MAX", 1.3):
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
        return {"direction": direction, "reason": reason, "score": score, "regime_day": sig_regime}

    def _opt_risk_levels(self, entry_price, bid, ask, base_atr, stop_mult=1.0, target_mult=1.5):
        """
        Option-specific risk levels using option premium + spread proxy.
        """
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
        planning_mode = bool(market_ctx.planning_only)
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
                return None
            allow_fallbacks = False
            allow_baseline = False
        # Paper strict mode: disable baseline and relax reasons
        if paper_strict_mode:
            allow_baseline = False
            allow_fallbacks = False
        symbol = market_data["symbol"]
        market_data = self._resolve_index_bid_ask(market_data, exec_mode)
        if market_data.get("valid") is False:
            self._reject_ctx = {"symbol": symbol, "reason": market_data.get("invalid_reason") or "invalid_snapshot"}
            self._log_blocked_candidate(
                symbol,
                "invalid_snapshot",
                str(market_data.get("invalid_reason") or "invalid_snapshot"),
                market_data=market_data,
            )
            if debug_reasons:
                _log_advisory_debug("trade_builder_reject symbol=%s reason=%s", symbol, self._reject_ctx["reason"])
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
                if reject_reason not in pre_soft_veto_codes:
                    pre_soft_veto_codes.append(reject_reason)
                if reject_reason not in pre_execution_blockers:
                    pre_execution_blockers.append(reject_reason)
                _log_signal_event("trade_offhours_missing_bidask", symbol, reject_payload)
                if debug_reasons:
                    _log_freshness_debug(
                        "trade_builder_soft_veto_missing_bidask symbol=%s candidate_generation_continues=true",
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
                self._reject_ctx = {"symbol": symbol, "reason": reject_reason, **reject_payload}
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
        if not signal:
            fallback_allowed = bool(market_data.get("allow_planning_no_signal_fallback"))
            reject_reason = "no_signal"
            if planning_relaxed and bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)):
                logger.info(
                    "planning_no_signal_fallback_check symbol=%s planning_relaxed=%s allow_planning_no_signal_fallback=%s planning_no_signal_fallback_enable=%s",
                    symbol,
                    bool(planning_relaxed),
                    fallback_allowed,
                    bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)),
                )
                if not fallback_allowed:
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
            if planning_relaxed and fallback_allowed:
                fallback_trade = self._build_planning_no_signal_trade(
                    market_data,
                    ltp=float(ltp or 0.0),
                    vwap=float(vwap or ltp or 0.0),
                )
                logger.info(
                    "planning_no_signal_fallback_result symbol=%s planning_relaxed=%s allow_planning_no_signal_fallback=%s returned_trade=%s",
                    symbol,
                    bool(planning_relaxed),
                    fallback_allowed,
                    bool(fallback_trade is not None),
                )
                if fallback_trade is not None:
                    return fallback_trade
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
            return None
        strategy_tag = "QUICK_OPT" if quick_mode else "ENSEMBLE_OPT"
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
            return None
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
            return None
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
            return None

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
                return None
        except Exception:
            pass
        # reject context for debug reports
        try:
            self._reject_ctx = {
                "strategy": "QUICK_OPT" if quick_mode else "ENSEMBLE_OPT",
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
                    return None
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
                        return None
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
                        return None
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
                        return None
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
                        return None
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
                return None
            if direction == "BUY_PUT" and htf_dir == "UP":
                self._log_blocked_candidate(
                    symbol,
                    "htf_alignment_fail",
                    "HTF alignment rejected BUY_PUT while HTF trend is UP",
                    market_data=market_data,
                    extra={"direction": direction, "htf_dir": htf_dir},
                )
                return None
        opt_type = "CE" if direction == "BUY_CALL" else "PE"
        candidates = []
        debug_candidates = []
        rejected = []
        candidate_strategy_tag = strategy_tag
        option_reject_counts: dict[str, int] = {}

        def _count_option_reject(reason_code: str | None) -> None:
            code = str(reason_code or "").strip()
            if not code:
                return
            option_reject_counts[code] = int(option_reject_counts.get(code, 0)) + 1
            self._scan_reject_counts[code] = int(self._scan_reject_counts.get(code, 0)) + 1

        def _option_reject_summary() -> dict:
            if not option_reject_counts:
                return {}
            ordered = sorted(
                option_reject_counts.items(),
                key=lambda item: (-int(item[1]), str(item[0])),
            )
            top = ordered[:5]
            top_reasons = [str(code) for code, _count in top]
            summary = {
                "top_option_reject_reasons": top_reasons,
                "option_reject_reason_counts": {str(code): int(count) for code, count in top},
                "option_reject_total": int(sum(option_reject_counts.values())),
            }
            self._reject_ctx = {
                "symbol": symbol,
                "reason": "no_viable_candidates",
                "gate_reasons": list(top_reasons),
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
                reasons=top_reasons,
                mode=mode,
                source="trade_builder_option_scan",
                extra=dict(summary),
            )
            return summary

        seq_buffer = market_data.get("seq_buffer")
        atr = market_data.get("atr", max(1.0, ltp * 0.002))
        chain_rows = market_data.get("option_chain", [])
        if not isinstance(chain_rows, (list, tuple)):
            chain_rows = []
        premium_band_cache = self._dynamic_premium_bands(symbol, chain_rows)
        for raw_opt in chain_rows:
            opt, opt_row_error = self._normalize_option_row(raw_opt, opt_type)
            if opt is None:
                _count_option_reject(opt_row_error)
                if debug_reasons and opt_row_error not in {"type_mismatch"}:
                    rejected.append(self._reject_record(symbol, {}, opt_type, opt_row_error, atr=atr))
                continue
            allow_missing_bid_ask = bool(
                exec_mode == "PAPER"
                and not bool(getattr(cfg, "PAPER_STRICT_MODE", False))
            )
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
                if "stale_option_quote" not in soft_veto_codes:
                    soft_veto_codes.append("stale_option_quote")
                if "stale_option_quote" not in execution_blockers:
                    execution_blockers.append("stale_option_quote")
            # Hard reject missing bid/ask
            if opt.get("quote_ok") is False:
                if strict_quotes:
                    _count_option_reject("no_quote")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                    continue
                if "option_quote_missing" not in soft_veto_codes:
                    soft_veto_codes.append("option_quote_missing")
                if "option_quote_missing" not in execution_blockers:
                    execution_blockers.append("option_quote_missing")
            # Skip synthetic quotes (no live price)
            require_live_option_quotes = bool(
                runtime_profile.suggestion_require_live_quotes
                and getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", False)
                and (not market_ctx.allow_stale_quotes)
            )
            if not opt.get("quote_ok", True) or (require_live_option_quotes and ("synthetic" not in quote_source.lower()) and not opt.get("quote_live", True)):
                if require_live_option_quotes:
                    _count_option_reject("no_quote")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                    continue
                if "option_quote_not_live" not in soft_veto_codes:
                    soft_veto_codes.append("option_quote_not_live")
                if "option_quote_not_live" not in execution_blockers:
                    execution_blockers.append("option_quote_not_live")
            if getattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", False) and not opt.get("depth_ok", False):
                if runtime_profile.suggestion_require_depth:
                    _count_option_reject("no_depth")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_depth", atr=atr))
                    continue
                if "option_depth_missing" not in soft_veto_codes:
                    soft_veto_codes.append("option_depth_missing")
                if "option_depth_missing" not in execution_blockers:
                    execution_blockers.append("option_depth_missing")
            if opt.get("bid") is None or opt.get("ask") is None:
                if strict_quotes:
                    _count_option_reject("no_bid_ask")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_bid_ask", atr=atr))
                    continue
                synth_abs = float(getattr(cfg, "OPTION_SYNTH_SPREAD_ABS", 0.5))
                synth_pct = float(getattr(cfg, "OPTION_SYNTH_SPREAD_PCT", 0.01))
                synth_spread = max(synth_abs, opt_ltp * synth_pct)
                opt["bid"] = round(max(0.01, opt_ltp - (synth_spread / 2.0)), 4)
                opt["ask"] = round(max(0.01, opt_ltp + (synth_spread / 2.0)), 4)
                opt["quote_ok"] = True
                if "option_bidask_missing" not in soft_veto_codes:
                    soft_veto_codes.append("option_bidask_missing")
                if "option_bidask_missing" not in execution_blockers:
                    execution_blockers.append("option_bidask_missing")
            if getattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", False) and not opt.get("volume", 0):
                if runtime_profile.suggestion_require_volume:
                    _count_option_reject("no_volume")
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_volume", atr=atr))
                    continue
                if "option_volume_missing" not in soft_veto_codes:
                    soft_veto_codes.append("option_volume_missing")
                if "option_volume_missing" not in execution_blockers:
                    execution_blockers.append("option_volume_missing")

            tradability_ok, tradability_ctx = self._option_tradability_precondition(
                symbol=symbol,
                opt=opt,
                market_data=market_data,
                market_ctx=market_ctx,
                direction=direction,
            )
            if not tradability_ok:
                reason_code = str(tradability_ctx.get("reason_code") or "option_tradability_precondition_failed")
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
                    continue
            if not quick_mode:
                vol = opt.get("volume", 0)
                min_volume_filter = int(max(0, current_filter_profile.min_volume_filter))
                if vol and vol < min_volume_filter and not _relax("low_volume"):
                    if runtime_profile.suggestion_require_volume:
                        _count_option_reject("low_volume")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=low_volume", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "low_volume", atr=atr))
                        continue
                    if "low_volume" not in soft_veto_codes:
                        soft_veto_codes.append("low_volume")
                    if "low_volume" not in execution_blockers:
                        execution_blockers.append("low_volume")
                if spread_pct > max_spread and not _relax("spread_pct"):
                    if spread_pct > toxic_spread and runtime_profile.suggestion_require_depth:
                        _count_option_reject("spread_pct")
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=spread_pct spread_pct=%.4f", symbol, opt.get("strike"), opt_type, spread_pct)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "spread_pct", atr=atr))
                        continue
                    if "spread_pct" not in soft_veto_codes:
                        soft_veto_codes.append("spread_pct")
                    if "spread_pct" not in execution_blockers:
                        execution_blockers.append("spread_pct")

            # OI / Greeks filters
            if not quick_mode:
                if opt.get("oi", 0) and opt.get("oi", 0) < getattr(cfg, "MIN_OI", 1000) and not _relax("low_oi"):
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
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=oi_change_min", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "oi_change_min", atr=atr))
                        continue
                if opt.get("iv") is not None:
                    if (opt["iv"] < getattr(cfg, "MIN_IV", 0.1) or opt["iv"] > getattr(cfg, "MAX_IV", 0.6)) and not _relax("iv_bounds"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_bounds", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_bounds", atr=atr))
                        continue
                if opt.get("iv_z") is not None:
                    if (opt["iv_z"] < getattr(cfg, "IV_Z_MIN", -1.5) or opt["iv_z"] > getattr(cfg, "IV_Z_MAX", 1.5)) and not _relax("iv_z_bounds"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_z_bounds", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_z_bounds", atr=atr))
                        continue
                if opt.get("iv_skew") is not None:
                    if abs(opt["iv_skew"]) > getattr(cfg, "IV_SKEW_MAX", 0.05) and not _relax("iv_skew_max"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_max", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_max", atr=atr))
                        continue
                    if direction == "BUY_CALL" and opt["iv_skew"] > getattr(cfg, "IV_SKEW_BULL_MAX", 0.02) and not _relax("iv_skew_bull"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_bull", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_bull", atr=atr))
                        continue
                    if direction == "BUY_PUT" and opt["iv_skew"] < getattr(cfg, "IV_SKEW_BEAR_MIN", -0.02) and not _relax("iv_skew_bear"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_bear", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_bear", atr=atr))
                        continue
                    if opt_type == "CE" and opt["iv_skew"] > getattr(cfg, "IV_SKEW_CALL_MAX", 0.03) and not _relax("iv_skew_call"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_call", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_call", atr=atr))
                        continue
                    if opt_type == "PE" and opt["iv_skew"] < getattr(cfg, "IV_SKEW_PUT_MIN", -0.03) and not _relax("iv_skew_put"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_put", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_put", atr=atr))
                        continue
                if opt.get("iv_skew_norm") is not None:
                    if abs(opt["iv_skew_norm"]) > getattr(cfg, "IV_SKEW_MAX", 0.05) and not _relax("iv_skew_norm"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_norm", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_norm", atr=atr))
                        continue
                if opt.get("iv_skew_curvature") is not None:
                    if abs(opt["iv_skew_curvature"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curvature"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_curvature", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curvature", atr=atr))
                        continue
                if opt_type == "CE" and opt.get("iv_skew_curvature_call") is not None:
                    if abs(opt["iv_skew_curvature_call"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curve_call"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_curve_call", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curve_call", atr=atr))
                        continue
                if opt_type == "PE" and opt.get("iv_skew_curvature_put") is not None:
                    if abs(opt["iv_skew_curvature_put"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curve_put"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_skew_curve_put", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curve_put", atr=atr))
                        continue
                if opt.get("iv_term") is not None:
                    if (opt["iv_term"] < getattr(cfg, "IV_TERM_MIN", -0.05) or opt["iv_term"] > getattr(cfg, "IV_TERM_MAX", 0.05)) and not _relax("iv_term"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_term", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_term", atr=atr))
                        continue
                if opt.get("iv_surface_slope") is not None:
                    if abs(opt["iv_surface_slope"]) > getattr(cfg, "IV_SURFACE_SLOPE_MAX", 0.15) and not _relax("iv_surface_slope"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=iv_surface_slope", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_surface_slope", atr=atr))
                        continue
                if opt.get("oi_build"):
                    if direction == "BUY_CALL" and opt["oi_build"] not in ("LONG", "SHORT_COVER") and not _relax("oi_build"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=oi_build", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "oi_build", atr=atr))
                        continue
                    if direction == "BUY_PUT" and opt["oi_build"] not in ("SHORT", "LONG_LIQ") and not _relax("oi_build"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=oi_build", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "oi_build", atr=atr))
                        continue
                if opt.get("delta") is not None:
                    if (abs(opt["delta"]) < getattr(cfg, "DELTA_MIN", 0.25) or abs(opt["delta"]) > getattr(cfg, "DELTA_MAX", 0.7)) and not _relax("delta"):
                        if debug_reasons:
                            _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=delta", symbol, opt.get("strike"), opt_type)
                            rejected.append(self._reject_record(symbol, opt, opt_type, "delta", atr=atr))
                        continue

            # Premium gate: hard only for poor liquidity, otherwise soft-veto.
            min_p, max_p = premium_band_used
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
                hard_liquidity_reject = bool(execution_mode == "LIVE" and (spread_bad or volume_bad or quote_missing))
                if hard_liquidity_reject:
                    _count_option_reject("premium")
                    self._log_blocked_candidate(
                        symbol,
                        "premium_band_fail",
                        "Option premium outside configured premium band (hard liquidity veto)",
                        market_data=market_data,
                        extra={
                            "direction": direction,
                            "strike": opt.get("strike"),
                            "option_type": opt.get("type"),
                            "option_ltp": opt.get("ltp"),
                            "premium_min": min_p,
                            "premium_max": max_p,
                            "spread_pct": spread_pct,
                            "volume": opt.get("volume"),
                            "hard_veto": True,
                            "reason_codes": ["premium_band_fail", "liquidity_hard_veto"],
                            "gate_name": "premium_band_gate",
                            "instrument_token": opt.get("instrument_token"),
                            "tradingsymbol": opt.get("tradingsymbol"),
                            "expiry_date": opt.get("expiry_date") or opt.get("expiry"),
                            "quote_source": opt.get("quote_source"),
                            "option_ltp_source": opt.get("option_ltp_source"),
                        },
                    )
                    if debug_reasons:
                        _log_option_chain_debug("trade_builder_option_reject symbol=%s strike=%s type=%s reason=premium_hard_liquidity", symbol, opt.get("strike"), opt_type)
                        rec = self._reject_record(symbol, opt, opt_type, "premium", atr=atr)
                        rec["hard_veto"] = True
                        rec["spread_pct"] = spread_pct
                        rec["volume"] = opt.get("volume")
                        debug_candidates.append(rec)
                        rejected.append(rec)
                    continue
                premium_soft_veto = True
                soft_veto_codes.append("premium_out_of_band")
                if soft_premium_advisory and "premium_band_fail" not in soft_veto_codes:
                    soft_veto_codes.append("premium_band_fail")
                if soft_premium_advisory:
                    self._log_blocked_candidate(
                        symbol,
                        "premium_band_fail",
                        "Option premium outside configured premium band (soft advisory penalty)",
                        market_data=market_data,
                        extra={
                            "direction": direction,
                            "strike": opt.get("strike"),
                            "option_type": opt.get("type"),
                            "option_ltp": opt.get("ltp"),
                            "premium_min": min_p,
                            "premium_max": max_p,
                            "spread_pct": spread_pct,
                            "volume": opt.get("volume"),
                            "hard_veto": False,
                            "reason_codes": ["premium_band_fail"],
                            "gate_name": "premium_band_gate",
                            "instrument_token": opt.get("instrument_token"),
                            "tradingsymbol": opt.get("tradingsymbol"),
                            "expiry_date": opt.get("expiry_date") or opt.get("expiry"),
                            "quote_source": opt.get("quote_source"),
                            "option_ltp_source": opt.get("option_ltp_source"),
                        },
                    )
                if "premium_out_of_band" not in execution_blockers:
                    execution_blockers.append("premium_out_of_band")
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
                if "spread_ok" not in soft_veto_codes:
                    soft_veto_codes.append("spread_ok")
                if "spread_ok" not in execution_blockers:
                    execution_blockers.append("spread_ok")

            # ML confidence (only if enough history)
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
            deep_conf = None
            micro_conf = None
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
                    if confidence is None:
                        confidence = micro_conf
                    else:
                        confidence = (confidence + micro_conf) / 2.0
                if confidence is None:
                    confidence = 0.5
            else:
                # Pure price/volume logic: use signal score as confidence proxy
                confidence = max(0.5, min(1.0, signal.get("score", 0.5)))

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
            size_mult = min(size_mult, decay_size_mult)

            # Latency penalty
            confidence *= self.execution.latency_penalty(opt.get("timestamp", datetime.now().timestamp()))

            min_proba = getattr(cfg, "ML_MIN_PROBA", 0.6)
            proba_mult = getattr(cfg, "REGIME_PROBA_MULT", {}).get(regime_day, 1.0)
            min_proba = min_proba * proba_mult
            if quick_mode:
                min_proba = min(min_proba, getattr(cfg, "QUICK_MIN_PROBA", 0.35))
                if getattr(cfg, "QUICK_USE_SIGNAL_SCORE", True):
                    try:
                        confidence = max(confidence, float(signal.get("score", 0.5)))
                    except Exception:
                        pass
            if not quick_mode:
                tune = _get_auto_tune()
                if tune.get("enabled"):
                    min_proba = float(tune.get("min_proba", min_proba))
            if confidence < min_proba and not _relax("confidence"):
                _count_option_reject("confidence")
                if debug_reasons:
                    _log_advisory_debug(
                        "trade_builder_confidence_reject symbol=%s strike=%s type=%s confidence=%.3f min_proba=%s regime=%s reason=%s",
                        symbol,
                        opt["strike"],
                        opt_type,
                        confidence,
                        min_proba,
                        signal.get("regime_day"),
                        signal.get("reason"),
                    )
                    rec = self._reject_record(symbol, opt, opt_type, "confidence", atr=atr)
                    rec["confidence"] = round(confidence, 3)
                    rec["min_proba"] = min_proba
                    debug_candidates.append(rec)
                    rejected.append(rec)
                continue

            # Slippage adjustment for limit
            slippage = self.execution.estimate_slippage(opt["bid"], opt["ask"], opt.get("volume", 0))
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
            option_risk = self._option_risk_proxy(entry_price, opt.get("bid", 0), opt.get("ask", 0))
            stop_loss, target = self._opt_risk_levels(
                entry_price, opt.get("bid", 0), opt.get("ask", 0), option_risk, stop_mult=stop_mult, target_mult=target_mult
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
            if planning_relaxed:
                min_score = min(min_score, float(getattr(cfg, "PLANNING_TRADE_SCORE_MIN", 58)))
            if score < min_score:
                _count_option_reject("trade_score")
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "trade_score", atr=atr)
                    rec["trade_score"] = score
                    rec["min_score"] = min_score
                    rejected.append(rec)
                continue

            confidence_base = float(confidence)
            confidence_penalty_reasons = list(dict.fromkeys(str(code) for code in soft_veto_codes if str(code)))
            if soft_veto_codes:
                if any(code.startswith("orb_") for code in soft_veto_codes):
                    confidence *= float(getattr(cfg, "ORB_SOFT_VETO_CONF_MULT", 0.95))
                    size_mult = min(size_mult, float(getattr(cfg, "ORB_SOFT_VETO_SIZE_MULT", 0.95)))
                if premium_soft_veto:
                    confidence *= premium_soft_penalty_conf
                    size_mult = min(size_mult, premium_soft_penalty_size)
            confidence_penalty_total = max(0.0, float(confidence_base) - float(confidence))

            tier = "EXPLORATION" if quick_mode else "MAIN"
            resolved_contract = opt.get("_resolved_contract") if isinstance(opt.get("_resolved_contract"), dict) else {}
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
                    opt.get("type"),
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
                opt.get("type"),
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
                        "option_type": opt.get("type"),
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
                        "option_type": opt.get("type"),
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
            if soft_veto_codes:
                source_flags["soft_veto_codes"] = sorted(set(str(code) for code in soft_veto_codes if str(code)))
                source_flags["orb_bias"] = market_data.get("orb_bias")
                source_flags["orb_window_min"] = market_data.get("orb_window_min") or market_data.get("orb_lock_min")
                source_flags["orb_state"] = market_data.get("orb_state")
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
                    "penalty_size_mult": round(float(premium_soft_penalty_size), 6),
                }
                source_flags["premium_soft_veto"] = True
            source_flags["decision_trace"] = {
                "signal_score": float(signal.get("score", 0.0)),
                "regime_conf": market_data.get("regime_confidence") or market_data.get("day_confidence"),
                "orb_bias": market_data.get("orb_bias"),
                "orb_factor": None,
                "reg_penalty": None,
                "global_conf": None,
                "permission": "EXECUTE" if bool(intent["execution_allowed"]) else "ADVISORY_ONLY",
                "permission_reason": intent.get("execution_reason") or (
                    "execution_allowed" if bool(intent["execution_allowed"]) else "intent_blocked"
                ),
                "entry_status": "OK" if bool(intent["execution_allowed"]) else "INTENT_BLOCKED",
                "entry_block_reason": None if bool(intent["execution_allowed"]) else (intent.get("execution_reason") or "intent_blocked"),
                "final_action": "EXECUTE" if bool(intent["execution_allowed"]) else "ADVISORY_ONLY",
                "initial_score": float(signal.get("score", 0.0)) * 100.0,
                "score_penalties": [
                    {"name": str(code), "type": "soft_veto"}
                    for code in list(dict.fromkeys(soft_veto_codes))
                ],
                "final_score": float(score),
                "hard_reject_reason": None,
                "soft_vetos": list(dict.fromkeys(soft_veto_codes)),
                "gates_failed": list(dict.fromkeys(execution_blockers)),
                "exec_allowed": bool(intent["execution_allowed"]),
            }
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
            trade = Trade(
                trade_id=f"{symbol}-{opt['strike']}-{opt['type']}-{int(datetime.now().timestamp())}",
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
                confidence_base=round(confidence_base, 6),
                confidence_penalty_total=round(confidence_penalty_total, 6),
                confidence_penalty_reasons=confidence_penalty_reasons,
            )
            trade = self._decorate_trade_context(trade, market_data, confidence)
            if trade is not None:
                candidates.append(trade)

        if debug_reasons and rejected:
            self._write_rejected(rejected)
        if debug_mode:
            top_n = getattr(cfg, "DEBUG_TRADE_TOP_N", 5)
            pool = rejected if rejected else debug_candidates
            if pool:
                self._write_debug_candidates(pool, top_n=top_n)
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
                        confidence=round(max(0.5, getattr(cfg, "ML_MIN_PROBA", 0.5)), 3),
                        strategy="QUICK_SYNTH",
                        regime=market_data.get("regime", "NEUTRAL"),
                        tier="EXPLORATION",
                        day_type=market_data.get("day_type", "UNKNOWN"),
                        signal_price=None,
                        entry_price_source="ask",
                        expected_entry=round(entry_price, 2),
                        expected_entry_source="ask",
                        **self._option_liquidity_fields(opt),
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
                    )
                    trade = self._decorate_trade_context(
                        trade,
                        market_data,
                        float(max(0.5, getattr(cfg, "ML_MIN_PROBA", 0.5))),
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
                )
                trade = self._decorate_trade_context(trade, market_data, base_conf)
                if trade is None:
                    return None
                if trade.confidence >= getattr(cfg, "ML_MIN_PROBA", 0.6):
                    return trade
                self._log_blocked_candidate(
                    symbol,
                    "low_confidence",
                    "Trade confidence below configured threshold",
                    market_data=market_data,
                    extra={"confidence": trade.confidence, "min_confidence": getattr(cfg, "ML_MIN_PROBA", 0.6)},
                )
                if debug_reasons:
                    _log_advisory_debug("trade_builder_low_confidence symbol=%s instrument=%s", symbol, instrument)
                return None
            self._log_blocked_candidate(
                symbol,
                "no_viable_candidates",
                "No viable trade candidates after all filters",
                market_data=market_data,
                extra=_option_reject_summary(),
            )
            return None

        # Persist decision traces for all retained candidates (selected and non-selected).
        for cand in candidates:
            try:
                sf = dict(getattr(cand, "source_flags", {}) or {})
                decision_trace = dict(sf.get("decision_trace", {}) or {})
                gates_failed = list(dict.fromkeys(sf.get("gates_failed") or getattr(cand, "tradable_reasons_blocking", []) or []))
                soft_vetos = list(dict.fromkeys(sf.get("soft_veto_codes") or []))
                record_candidate_decision(
                    {
                        "candidate_id": getattr(cand, "trade_id", None),
                        "ts_epoch": now_utc_epoch(),
                        "symbol": getattr(cand, "symbol", symbol),
                        "side": direction,
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
                        "permission": decision_trace.get("permission"),
                        "permission_reason": decision_trace.get("permission_reason"),
                        "entry_status": decision_trace.get("entry_status"),
                        "entry_block_reason": decision_trace.get("entry_block_reason"),
                        "final_action": decision_trace.get("final_action"),
                        "ltp": market_data.get("ltp"),
                        "atr": market_data.get("atr"),
                    }
                )
            except Exception:
                pass

        # Choose highest-confidence candidate
        self._scan_accepted = int(len(candidates))
        best_trade = sorted(
            candidates,
            key=lambda t: (1 if getattr(t, "tradable", True) else 0, t.confidence),
            reverse=True,
        )[0]
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
        trade = self.build(
            market_data,
            quick_mode=quick_mode,
            debug_reasons=debug_reasons,
            force_family=force_family,
            allow_fallbacks=allow_fallbacks,
            allow_baseline=allow_baseline,
        )
        trace = build_trade_decision_trace(
            market_data=market_data or {},
            trade=trade,
            reject_ctx=dict(self._reject_ctx or {}),
            run_id=(market_data or {}).get("run_id"),
        )
        return trade, trace

    def build_zero_hero(self, market_data, debug_reasons=False):
        """
        Zero-to-hero (lotto): paper-only, high-convexity ideas.
        Uses OTM strikes (1-2% from ATM) and a dynamic low-premium band (p2-p25).
        """
        if not getattr(cfg, "ZERO_TO_HERO_ENABLE", False):
            return None
        exec_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
        allowed_modes = getattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"])
        if isinstance(allowed_modes, str):
            allowed_modes = [s.strip().upper() for s in allowed_modes.split(",") if s.strip()]
        allowed_modes = {str(m).strip().upper() for m in (allowed_modes or ["PAPER"])}
        if exec_mode not in allowed_modes:
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
        regime_raw = market_data.get("regime") or market_data.get("primary_regime") or market_data.get("regime_day")
        regime = normalize_regime(regime_raw)
        allowed_regimes = getattr(cfg, "ZERO_TO_HERO_ALLOWED_REGIMES", ["TREND", "EVENT"])
        if isinstance(allowed_regimes, str):
            allowed_regimes = [s.strip().upper() for s in allowed_regimes.split(",") if s.strip()]
        allowed_regimes = {str(r).strip().upper() for r in (allowed_regimes or [])}
        if allowed_regimes and regime not in allowed_regimes:
            return None

        if not self._zero_to_hero_daily_ok():
            return None

        chain = market_data.get("option_chain") or []
        if not chain:
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
            return None

        candidates = []
        for opt in chain:
            if not isinstance(opt, dict):
                continue
            if opt.get("type") != opt_type:
                continue
            strike = opt.get("strike")
            if strike is None:
                continue
            try:
                strike_val = float(strike)
            except Exception:
                continue
            if strike_val < strike_low or strike_val > strike_high:
                continue
            premium = self._coerce_positive_float(
                opt.get("ltp")
                or opt.get("last_price")
                or opt.get("close")
                or opt.get("price")
            )
            premium_out_of_band = bool(premium is None or premium < band_low or premium > band_high)
            if premium_out_of_band and not exploratory_mode:
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "premium_band_fail",
                        "Zero-to-hero blocked: premium outside allowed band",
                        market_data=market_data,
                        extra={"premium": premium, "band_low": band_low, "band_high": band_high},
                    )
                continue
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
                if debug_reasons:
                    self._log_blocked_candidate(
                        symbol,
                        "spread",
                        "Zero-to-hero blocked: spread too wide",
                        market_data=market_data,
                        extra={"strike": opt.get("strike"), "option_type": opt.get("type")},
                    )
                continue

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

            candidates.append(
                {
                    "opt": opt,
                    "premium": premium,
                    "confidence": confidence,
                    "cheapness": cheapness,
                    "momentum_score": momentum_score,
                    "band_source": band_source,
                    "premium_band_fail": premium_out_of_band,
                    "spread_warning": not spread_ok,
                }
            )

        if not candidates:
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_viable_candidates",
                    "Zero-to-hero blocked: no viable candidates",
                    market_data=market_data,
                    extra={"band_low": band_low, "band_high": band_high, "exploratory_mode": exploratory_mode},
                )
            return None
        chosen = sorted(candidates, key=lambda c: c["confidence"], reverse=True)[0]
        opt = chosen["opt"]
        premium = float(chosen["premium"])

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
        expiry_resolved = self._option_expiry(opt, market_data) or expiry_resolved
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
        instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
            symbol,
            "OPT",
            expiry_resolved,
            opt.get("strike"),
            opt.get("type"),
            1,
        )
        if ident_err or not expiry_resolved or not tradingsymbol or not instrument_id:
            if debug_reasons:
                self._log_blocked_candidate(
                    symbol,
                    "no_contract",
                    "Zero-to-hero blocked: unresolved contract",
                    market_data=market_data,
                    extra={"strike": opt.get("strike"), "option_type": opt.get("type")},
                )
            return None
        if instrument_token is None and debug_reasons:
            self._log_blocked_candidate(
                symbol,
                "no_token",
                "Zero-to-hero continuing without resolved instrument token",
                market_data=market_data,
                extra={"strike": opt.get("strike"), "option_type": opt.get("type"), "tradingsymbol": tradingsymbol},
            )

        intent = self.trade_intent_flags(market_data, opt=opt, additional_blockers=[])
        intent["planning_only"] = True
        intent["execution_allowed"] = False
        intent["execution_reason"] = "PAPER_ONLY"

        trade = Trade(
            trade_id=f"{symbol}-{opt.get('type')}-{int(opt.get('strike'))}-ZTH-{ts}",
            timestamp=datetime.now(),
            symbol=symbol,
            instrument="OPT",
            instrument_type=instrument_type,
            right=opt.get("type"),
            instrument_id=instrument_id,
            instrument_token=instrument_token,
            strike=opt.get("strike"),
            expiry=expiry_resolved,
            expiry_date=expiry_resolved,
            tradingsymbol=tradingsymbol,
            option_type=opt.get("type"),
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
            confidence=round(float(chosen["confidence"]), 3),
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
        )
        trade = self._decorate_trade_context(trade, market_data, float(chosen["confidence"]))
        if trade is None:
            return None

        trade.source_flags.update(
            {
                "zero_to_hero": True,
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
                    "permission": "ADVISORY_ONLY",
                    "permission_reason": "PAPER_ONLY",
                    "entry_status": "OK",
                    "entry_block_reason": None,
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
        symbol = market_data.get("symbol")
        ltp = market_data.get("ltp", 0)
        atr = market_data.get("atr", max(1.0, ltp * 0.002))
        minutes_since_open = market_data.get("minutes_since_open", 0) or 0
        if minutes_since_open > getattr(cfg, "ZERO_HERO_EXPIRY_TIME_CUTOFF_MIN", 120):
            return None
        if self._expiry_zero_hero_count >= getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES", 2):
            return None
        max_per_symbol = getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES_PER_SYMBOL", 1)
        if symbol == "NIFTY":
            max_per_symbol = getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES_NIFTY", max_per_symbol)
        if symbol == "SENSEX":
            max_per_symbol = getattr(cfg, "ZERO_HERO_EXPIRY_MAX_TRADES_SENSEX", max_per_symbol)
        if self._expiry_zero_hero_by_symbol.get(symbol, 0) >= max_per_symbol:
            return None
        # cooldown after loss streak
        try:
            until = self._expiry_zero_hero_disabled_until.get(symbol)
            if until and time.time() < until:
                return None
        except Exception:
            pass
        # Direction by momentum + ORB bias
        ltp_change_window = market_data.get("ltp_change_window", 0) or 0
        vwap = market_data.get("vwap", ltp)
        orb_bias = market_data.get("orb_bias", "NEUTRAL")
        if orb_bias == "PENDING":
            return None
        direction = "BUY_CALL" if (ltp_change_window >= 0 and ltp >= vwap) else "BUY_PUT"
        if orb_bias == "UP" and direction == "BUY_PUT":
            return None
        if orb_bias == "DOWN" and direction == "BUY_CALL":
            return None
        opt_type = "CE" if direction == "BUY_CALL" else "PE"

        min_p = getattr(cfg, "ZERO_HERO_EXPIRY_MIN_PREMIUM", 5)
        max_p = getattr(cfg, "ZERO_HERO_EXPIRY_PREMIUM_MAX_BY_SYMBOL", {}).get(symbol, getattr(cfg, "ZERO_HERO_EXPIRY_MAX_PREMIUM", 40))
        min_delta = getattr(cfg, "ZERO_HERO_EXPIRY_MIN_DELTA", 0.2)
        max_delta = getattr(cfg, "ZERO_HERO_EXPIRY_MAX_DELTA", 0.5)
        tgt_points = getattr(cfg, "ZERO_HERO_EXPIRY_TARGET_POINTS", {}).get(symbol, 50)

        candidates = []
        for opt in market_data.get("option_chain", []):
            if opt.get("type") != opt_type:
                continue
            has_required_quote, _ = self._validate_required_option_quote_fields(opt)
            if not has_required_quote:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "partial_option_row", atr=atr)
                    rejected.append(rec)
                continue
            if opt.get("ltp", 0) < min_p or opt.get("ltp", 0) > max_p:
                continue
            if not self.execution.spread_ok(opt.get("bid", 0), opt.get("ask", 0), opt.get("ltp", 0) or 1):
                continue
            # Premium decay filter: IV crush + time to expiry
            iv = opt.get("iv")
            iv_z = opt.get("iv_z")
            tte_hrs = opt.get("time_to_expiry_hrs")
            if tte_hrs is None:
                tte_hrs = market_data.get("time_to_expiry_hrs")
            if tte_hrs is None:
                tte_hrs = 0
            if iv is not None and iv < getattr(cfg, "ZERO_HERO_IVCRUSH_MIN", 0.15):
                continue
            if tte_hrs > getattr(cfg, "ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS", 6):
                continue
            d = abs(opt.get("delta", 0.0)) if opt.get("delta") is not None else 0.0
            if d and (d < min_delta or d > max_delta):
                continue
            # require strong immediate momentum
            if abs(ltp_change_window) < atr * getattr(cfg, "ZERO_HERO_ATR_MULT", 0.08):
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
            # target based on underlying points * delta proxy
            delta = d if d else 0.3
            target = entry_price + max(5, tgt_points * delta)
            stop_loss = max(entry_price - max(3, (tgt_points * delta) * 0.5), entry_price * 0.2)

            confidence = max(0.6, min(1.0, abs(ltp_change_window) / max(atr, 1.0)))
            alpha_conf = None
            alpha_unc = None
            size_mult = 1.0
            adj_conf, alpha_conf, alpha_unc, size_mult = self._apply_alpha_ensemble(
                confidence, None, None, None, market_data, quick_mode=True
            )
            if adj_conf is not None:
                confidence = adj_conf
            allowed_life, _ = self._apply_lifecycle_gate("ZERO_HERO_EXPIRY", mode="QUICK")
            if not allowed_life:
                if debug_reasons:
                    _log_advisory_debug("zero_hero_expiry_reject symbol=%s reason=lifecycle_gate", symbol)
                return None
            expiry_resolved = self._option_expiry(opt, market_data)
            if not expiry_resolved:
                expiry_resolved = self._resolve_expiry_for_symbol(symbol, market_data)
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
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                expiry_resolved,
                opt.get("strike"),
                opt.get("type"),
                1,
            )
            if ident_err or not expiry_resolved or not tradingsymbol or not instrument_id:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "unresolved_contract", atr=atr)
                    rejected.append(rec)
                continue
            extra_blockers = []
            if instrument_token is None:
                extra_blockers.append("instrument_token_missing")
            intent = self.trade_intent_flags(market_data, opt=opt, additional_blockers=extra_blockers)
            trade = Trade(
                trade_id=f"{symbol}-{opt['type']}-{int(opt['strike'])}-ZEROEXP-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
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
                chain_source=market_data.get("chain_source") or opt.get("chain_source"),
            )
            trade = self._decorate_trade_context(trade, market_data, confidence)
            if trade is not None:
                candidates.append(trade)
        if not candidates:
            return None
        trade = sorted(candidates, key=lambda t: t.confidence, reverse=True)[0]
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
                if getattr(cfg, "ML_AB_ENABLE", False):
                    shadow_confidence = self.predictor.predict_confidence_shadow(feats)
            else:
                confidence = max(0.5, min(1.0, 0.6 + (atr / max(ltp, 1)) * 10))
            if cfg.USE_MICRO_MODEL:
                micro_features = [
                    float(opt.get("spread_pct", (opt["ask"] - opt["bid"]) / opt["ltp"] if opt["ltp"] else 0)),
                    float(opt.get("volume", 0)),
                    float(opt.get("oi_change", 0))
                ]
                micro_conf = self._get_micro_predictor().predict_confidence(micro_features)
                confidence = (confidence + micro_conf) / 2.0
            # Alpha ensemble fusion (exploratory: downsize but don't veto)
            adj_conf, alpha_conf, alpha_unc, size_mult = self._apply_alpha_ensemble(
                confidence, xgb_conf, None, micro_conf, market_data, quick_mode=True
            )
            if adj_conf is not None:
                confidence = adj_conf
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
            if confidence < getattr(cfg, "SCALP_MIN_PROBA", 0.58):
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
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                self._option_expiry(opt, market_data),
                opt.get("strike"),
                opt.get("type"),
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
                trade_id=f"{symbol}-{opt['type']}-{int(opt['strike'])}-SCALP-{ts}",
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=opt.get("type"),
                instrument_id=instrument_id,
                instrument_token=opt.get("instrument_token"),
                strike=opt["strike"],
                expiry=self._option_expiry(opt, market_data),
                option_type=opt.get("type"),
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
            )
            trade = self._decorate_trade_context(trade, market_data, confidence)
            if trade is not None:
                candidates.append(trade)
        if not candidates:
            return None
        return sorted(candidates, key=lambda t: (1 if getattr(t, "tradable", True) else 0, t.confidence), reverse=True)[0]

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
