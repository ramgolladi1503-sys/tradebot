from datetime import datetime
from pathlib import Path
import json
import os
import sys
import pandas as pd
from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.alpha_ensemble import AlphaEnsemble
from core.decision_trace import build_trade_decision_trace
from core.trade_schema import Trade, build_instrument_id, validate_trade_identity
from typing import Optional
from strategies.ensemble import ensemble_signal, equity_signal, futures_signal, mean_reversion_signal, event_breakout_signal, micro_pattern_signal
from core.feature_builder import build_trade_features, validate_trade_features
from core.trade_scoring import compute_trade_score
from core.strategy_tracker import StrategyTracker
from core.strategy_lifecycle import StrategyLifecycle
from core.time_utils import is_market_open_ist
from core.regime import RegimeClassifier, normalize_regime
import time as _time
import time

_AUTO_TUNE_CACHE = {"ts": 0, "data": {}}

def _get_auto_tune():
    try:
        now = _time.time()
        if now - _AUTO_TUNE_CACHE.get("ts", 0) < 60:
            return _AUTO_TUNE_CACHE.get("data") or {}
        path = Path("logs/auto_tune.json")
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
        path = Path("logs/signal_path.jsonl")
        path.parent.mkdir(exist_ok=True)
        obj = {"timestamp": datetime.now().isoformat(), "kind": kind, "symbol": symbol}
        if payload:
            obj.update(payload)
        with path.open("a") as f:
            f.write(json.dumps(obj) + "\n")
    except Exception:
        pass

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
        self._reject_ctx = {}

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

    def trade_intent_flags(
        self,
        market_data: dict,
        opt: dict | None = None,
        risk_guard_passed: bool | None = None,
        additional_blockers: list[str] | None = None,
    ) -> dict:
        segment = market_data.get("segment") or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        market_open = bool(is_market_open_ist(segment=segment))
        chain_source = market_data.get("chain_source", "empty")
        require_live_quotes = bool(getattr(cfg, "REQUIRE_LIVE_QUOTES", True))
        quote_ok = market_data.get("quote_ok", True)
        quote_age_sec = market_data.get("quote_age_sec")
        if opt is not None:
            quote_ok = opt.get("quote_ok", quote_ok)
            quote_age_sec = opt.get("quote_age_sec", quote_age_sec)
        ltp = market_data.get("ltp", 0)
        ltp_source = market_data.get("ltp_source", "none")
        reasons: list[str] = []
        if market_data.get("valid") is False:
            reasons.append(str(market_data.get("invalid_reason") or "invalid_snapshot"))
        if not market_open:
            reasons.append("market_closed")
        if chain_source != "live":
            reasons.append("chain_not_live")
        if quote_ok is not True:
            reasons.append("quote_not_ok")
        max_quote_age = float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8))
        if quote_age_sec is None:
            reasons.append("quote_age_missing")
        elif float(quote_age_sec) > max_quote_age:
            reasons.append("stale_option_quote")
        if ltp_source != "live":
            reasons.append("ltp_not_live")
        if ltp is None or float(ltp) <= 0:
            reasons.append("invalid_ltp")
        if risk_guard_passed is False:
            reasons.append("risk_guard_failed")
        for blocker in additional_blockers or []:
            if blocker and blocker not in reasons:
                reasons.append(str(blocker))
        return {
            "tradable": len(reasons) == 0,
            "tradable_reasons_blocking": reasons,
            "source_flags": {
                "chain_source": chain_source,
                "quote_ok": bool(quote_ok),
                "quote_age_sec": quote_age_sec,
                "market_open": market_open,
                "require_live_quotes": require_live_quotes,
                "ltp_source": ltp_source,
                "snapshot_valid": bool(market_data.get("valid", True)),
                "risk_guard_passed": risk_guard_passed,
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
            path = Path("data/trade_log.json")
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
            return None
        return {"direction": sig.direction, "reason": sig.reason, "score": sig.score, "regime_day": normalize_regime(regime_day)}

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

    def build(self, market_data, quick_mode=False, debug_reasons=False, force_family: str | None = None, allow_fallbacks: bool = True, allow_baseline: bool = True):
        """
        Build a single best Trade candidate from market snapshot.
        Returns Trade or None.
        """
        self._reject_ctx = {}
        debug_mode = getattr(cfg, "DEBUG_TRADE_MODE", False)
        if debug_mode:
            debug_reasons = True
        exec_mode = getattr(cfg, "EXECUTION_MODE", "SIM").upper()
        # Hard disable quick/baseline paths in LIVE mode
        if exec_mode == "LIVE":
            if quick_mode:
                return None
            allow_fallbacks = False
            allow_baseline = False
        # Paper strict mode: disable baseline and relax reasons
        if exec_mode == "PAPER" and getattr(cfg, "PAPER_STRICT_MODE", False):
            allow_baseline = False
            allow_fallbacks = False
        symbol = market_data["symbol"]
        if market_data.get("valid") is False:
            self._reject_ctx = {"symbol": symbol, "reason": market_data.get("invalid_reason") or "invalid_snapshot"}
            if debug_reasons:
                print(f"[TradeBuilder] Reject {symbol}: {self._reject_ctx['reason']}")
            return None
        ltp = market_data.get("ltp", 0)
        vwap = market_data.get("vwap", ltp)
        bias = market_data.get("bias", "Bullish")
        instrument = market_data.get("instrument", "OPT")
        if market_data.get("quote_ok") is False:
            if debug_reasons:
                print(f"[TradeBuilder] Reject {symbol}: missing index bid/ask")
            return None

        signal = self._signal_for_symbol(market_data, force_family=force_family)
        relax_reason = "" if exec_mode == "LIVE" else (getattr(cfg, "RELAX_BLOCK_REASON", "") or "")
        if exec_mode == "PAPER" and getattr(cfg, "PAPER_STRICT_MODE", False):
            relax_reason = ""
        def _relax(reason: str) -> bool:
            return bool(relax_reason) and reason == relax_reason
        if not signal and quick_mode and allow_fallbacks:
            # quick fallback signal based on simple bias / short-term move
            bias = market_data.get("bias", "NEUTRAL")
            ltp_change = market_data.get("ltp_change", 0)
            if bias in ("Bullish", "BULLISH") or ltp_change > 0:
                signal = {"direction": "BUY_CALL", "reason": "Quick bias fallback", "score": 0.55}
            elif bias in ("Bearish", "BEARISH") or ltp_change < 0:
                signal = {"direction": "BUY_PUT", "reason": "Quick bias fallback", "score": 0.55}
            else:
                # neutral fallback: use ltp vs vwap direction
                try:
                    if ltp >= vwap:
                        signal = {"direction": "BUY_CALL", "reason": "Quick neutral fallback", "score": 0.52}
                    else:
                        signal = {"direction": "BUY_PUT", "reason": "Quick neutral fallback", "score": 0.52}
                except Exception:
                    pass
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
            if debug_reasons:
                print(f"[TradeBuilder] No signal for {symbol} | ltp={ltp} vwap={vwap} atr={market_data.get('atr')} ltp_change={market_data.get('ltp_change')} ltp_change_window={market_data.get('ltp_change_window')}")
            return None
        strategy_tag = "QUICK_OPT" if quick_mode else "ENSEMBLE_OPT"
        allowed_life, _ = self._apply_lifecycle_gate(strategy_tag, mode="MAIN" if not quick_mode else "QUICK")
        if not allowed_life:
            if debug_reasons:
                print(f"[TradeBuilder] Reject {symbol}: lifecycle_gate ({strategy_tag})")
            return None
        decay_size_mult = 1.0
        allowed, adj_score, decay_size_mult, _decay_reason = self._apply_decay_gate(strategy_tag, signal.get("score"), decay_size_mult)
        if not allowed:
            if debug_reasons:
                print(f"[TradeBuilder] Reject {symbol}: strategy_quarantined ({strategy_tag})")
            return None
        if adj_score is not None:
            signal["score"] = adj_score
        min_score = getattr(cfg, "STRICT_STRATEGY_SCORE", 0.7)
        regime_day = signal.get("regime_day") or market_data.get("regime_day") or market_data.get("regime") or "NEUTRAL"
        score_mult = getattr(cfg, "REGIME_SCORE_MULT", {}).get(regime_day, 1.0)
        min_score = min_score * score_mult
        if quick_mode:
            min_score = min(min_score, 0.5)
        if debug_reasons:
            print(f"[SignalPath] {symbol} regime={signal.get('regime_day')} direction={signal.get('direction')} score={signal.get('score'):.3f} reason={signal.get('reason')}")
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
            if debug_reasons:
                print(f"[TradeBuilder] Signal score below min ({signal.get('score', 0)} < {min_score}) for {symbol}")
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
        # Require live option chain by default (no synthetic trades)
        try:
            if market_data.get("chain_source") != "live":
                if debug_reasons:
                    print(f"[TradeBuilder] Reject {symbol}: non-live option chain")
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
                    if debug_reasons:
                        print(f"[TradeBuilder] Direction sanity block: PE while price>VWAP and HTF UP for {symbol}")
                    return None
            except Exception:
                pass
        # ORB bias lock
        try:
            if getattr(cfg, "ORB_BIAS_LOCK", True):
                orb_bias = market_data.get("orb_bias", "NEUTRAL")
                if orb_bias == "PENDING":
                    return None
                if orb_bias == "UP" and direction == "BUY_PUT":
                    return None
                if orb_bias == "DOWN" and direction == "BUY_CALL":
                    return None
                if orb_bias == "NEUTRAL" and not getattr(cfg, "ORB_NEUTRAL_ALLOW", True):
                    return None
        except Exception:
            pass
        # Higher timeframe alignment
        if getattr(cfg, "HTF_ALIGN_REQUIRED", True) and not quick_mode:
            htf_dir = market_data.get("htf_dir", "FLAT")
            if direction == "BUY_CALL" and htf_dir == "DOWN":
                return None
            if direction == "BUY_PUT" and htf_dir == "UP":
                return None
        opt_type = "CE" if direction == "BUY_CALL" else "PE"
        candidates = []
        debug_candidates = []
        rejected = []
        strategy_tag = "ENSEMBLE_OPT"

        seq_buffer = market_data.get("seq_buffer")
        atr = market_data.get("atr", max(1.0, ltp * 0.002))
        for opt in market_data.get("option_chain", []):
            if opt["type"] != opt_type:
                continue
            # Hard reject stale quotes before any scoring
            quote_age = opt.get("quote_age_sec")
            quote_ts_epoch = opt.get("quote_ts_epoch")
            strict_quotes = getattr(cfg, "STRICT_LIVE_QUOTES", True)
            if exec_mode == "PAPER" and not getattr(cfg, "PAPER_STRICT_QUOTES", True):
                strict_quotes = False
            if strict_quotes:
                if quote_ts_epoch is None:
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "stale_option_quote", atr=atr))
                    continue
                if quote_age is None or quote_age > getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8):
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "stale_option_quote", atr=atr))
                    continue
            # Hard reject missing bid/ask
            if opt.get("quote_ok") is False:
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                continue
            # Skip synthetic quotes (no live price)
            if not opt.get("quote_ok", True) or (getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", False) and not opt.get("quote_live", True)):
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                continue
            if getattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", False) and not opt.get("depth_ok", False):
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "no_depth", atr=atr))
                continue
            if opt.get("bid") is None or opt.get("ask") is None:
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "no_bid_ask", atr=atr))
                continue
            if getattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", False) and not opt.get("volume", 0):
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "no_volume", atr=atr))
                continue
            # Liquidity guard
            spread_pct = (opt["ask"] - opt["bid"]) / opt["ltp"] if opt["ltp"] else 1
            max_spread = getattr(cfg, "MAX_SPREAD_PCT_QUICK", getattr(cfg, "MAX_SPREAD_PCT", 0.015)) if quick_mode else getattr(cfg, "MAX_SPREAD_PCT", 0.015)
            if exec_mode == "PAPER" and getattr(cfg, "PAPER_STRICT_MODE", False):
                if not opt.get("quote_ok", False):
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                    continue
                if spread_pct > max_spread:
                    if debug_reasons:
                        rejected.append(self._reject_record(symbol, opt, opt_type, "spread_pct", atr=atr))
                    continue
            if not quick_mode:
                vol = opt.get("volume", 0)
                if vol and vol < getattr(cfg, "MIN_VOLUME_FILTER", 500) and not _relax("low_volume"):
                    if debug_reasons:
                        print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: low volume")
                        rejected.append(self._reject_record(symbol, opt, opt_type, "low_volume", atr=atr))
                    continue
                if spread_pct > max_spread and not _relax("spread_pct"):
                    if debug_reasons:
                        print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: spread {spread_pct:.4f}")
                        rejected.append(self._reject_record(symbol, opt, opt_type, "spread_pct", atr=atr))
                    continue

            # OI / Greeks filters
            if not quick_mode:
                if opt.get("oi", 0) and opt.get("oi", 0) < getattr(cfg, "MIN_OI", 1000) and not _relax("low_oi"):
                    if debug_reasons:
                        print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: low OI")
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
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: OI change below min")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "oi_change_min", atr=atr))
                        continue
                if opt.get("iv") is not None:
                    if (opt["iv"] < getattr(cfg, "MIN_IV", 0.1) or opt["iv"] > getattr(cfg, "MAX_IV", 0.6)) and not _relax("iv_bounds"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: IV out of bounds")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_bounds", atr=atr))
                        continue
                if opt.get("iv_z") is not None:
                    if (opt["iv_z"] < getattr(cfg, "IV_Z_MIN", -1.5) or opt["iv_z"] > getattr(cfg, "IV_Z_MAX", 1.5)) and not _relax("iv_z_bounds"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: IV z out of bounds")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_z_bounds", atr=atr))
                        continue
                if opt.get("iv_skew") is not None:
                    if abs(opt["iv_skew"]) > getattr(cfg, "IV_SKEW_MAX", 0.05) and not _relax("iv_skew_max"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: IV skew max")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_max", atr=atr))
                        continue
                    if direction == "BUY_CALL" and opt["iv_skew"] > getattr(cfg, "IV_SKEW_BULL_MAX", 0.02) and not _relax("iv_skew_bull"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew bull max")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_bull", atr=atr))
                        continue
                    if direction == "BUY_PUT" and opt["iv_skew"] < getattr(cfg, "IV_SKEW_BEAR_MIN", -0.02) and not _relax("iv_skew_bear"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew bear min")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_bear", atr=atr))
                        continue
                    if opt_type == "CE" and opt["iv_skew"] > getattr(cfg, "IV_SKEW_CALL_MAX", 0.03) and not _relax("iv_skew_call"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew call max")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_call", atr=atr))
                        continue
                    if opt_type == "PE" and opt["iv_skew"] < getattr(cfg, "IV_SKEW_PUT_MIN", -0.03) and not _relax("iv_skew_put"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew put min")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_put", atr=atr))
                        continue
                if opt.get("iv_skew_norm") is not None:
                    if abs(opt["iv_skew_norm"]) > getattr(cfg, "IV_SKEW_MAX", 0.05) and not _relax("iv_skew_norm"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew norm")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_norm", atr=atr))
                        continue
                if opt.get("iv_skew_curvature") is not None:
                    if abs(opt["iv_skew_curvature"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curvature"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew curvature")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curvature", atr=atr))
                        continue
                if opt_type == "CE" and opt.get("iv_skew_curvature_call") is not None:
                    if abs(opt["iv_skew_curvature_call"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curve_call"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew curvature call")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curve_call", atr=atr))
                        continue
                if opt_type == "PE" and opt.get("iv_skew_curvature_put") is not None:
                    if abs(opt["iv_skew_curvature_put"]) > getattr(cfg, "IV_SKEW_CURVE_MAX", 0.5) and not _relax("iv_skew_curve_put"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: skew curvature put")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_skew_curve_put", atr=atr))
                        continue
                if opt.get("iv_term") is not None:
                    if (opt["iv_term"] < getattr(cfg, "IV_TERM_MIN", -0.05) or opt["iv_term"] > getattr(cfg, "IV_TERM_MAX", 0.05)) and not _relax("iv_term"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: iv term")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_term", atr=atr))
                        continue
                if opt.get("iv_surface_slope") is not None:
                    if abs(opt["iv_surface_slope"]) > getattr(cfg, "IV_SURFACE_SLOPE_MAX", 0.15) and not _relax("iv_surface_slope"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: iv surface slope")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "iv_surface_slope", atr=atr))
                        continue
                if opt.get("oi_build"):
                    if direction == "BUY_CALL" and opt["oi_build"] not in ("LONG", "SHORT_COVER") and not _relax("oi_build"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: oi build")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "oi_build", atr=atr))
                        continue
                    if direction == "BUY_PUT" and opt["oi_build"] not in ("SHORT", "LONG_LIQ") and not _relax("oi_build"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: oi build")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "oi_build", atr=atr))
                        continue
                if opt.get("delta") is not None:
                    if (abs(opt["delta"]) < getattr(cfg, "DELTA_MIN", 0.25) or abs(opt["delta"]) > getattr(cfg, "DELTA_MAX", 0.7)) and not _relax("delta"):
                        if debug_reasons:
                            print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: delta")
                            rejected.append(self._reject_record(symbol, opt, opt_type, "delta", atr=atr))
                        continue

            # Premium filter (allow per-symbol bands)
            band_map = getattr(cfg, "PREMIUM_BANDS", {})
            band = band_map.get(symbol, (getattr(cfg, "MIN_PREMIUM", 40), getattr(cfg, "MAX_PREMIUM", 150)))
            min_p, max_p = band
            if (opt["ltp"] < min_p or opt["ltp"] > max_p) and not _relax("premium"):
                if debug_reasons:
                    print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: premium")
                    rec = self._reject_record(symbol, opt, opt_type, "premium", atr=atr)
                    debug_candidates.append(rec)
                    rejected.append(rec)
                continue

            # Spread check
            if not self.execution.spread_ok(opt["bid"], opt["ask"], opt["ltp"], max_spread_pct=max_spread) and not _relax("spread_ok"):
                if debug_reasons:
                    print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: spread_ok")
                    rec = self._reject_record(symbol, opt, opt_type, "spread_ok", atr=atr)
                    debug_candidates.append(rec)
                    rejected.append(rec)
                continue

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
                        str(opt.get("expiry", "")),
                        opt.get("strike"),
                        opt.get("type"),
                        1,
                    )
                    if ident_err:
                        if debug_reasons:
                            rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
                            rejected.append(rec)
                        continue
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    blocked_trade = Trade(
                        trade_id=f"{symbol}-{opt['strike']}-{opt['type']}-BLOCKED-{ts}",
                        timestamp=datetime.now(),
                        symbol=symbol,
                        instrument="OPT",
                        instrument_type=instrument_type,
                        right=opt.get("type"),
                        instrument_id=instrument_id,
                        instrument_token=opt.get("instrument_token"),
                        strike=opt["strike"],
                        expiry=str(opt.get("expiry", "")),
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
                        quote_ok=opt.get("quote_ok", True),
                        tradable=False,
                        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                        source_flags=dict(intent["source_flags"]),
                    )
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
                if debug_reasons:
                    print(f"[TradeBuilder] Reject {symbol} {opt['strike']} {opt_type}: confidence {confidence:.3f} < {min_proba} | regime={signal.get('regime_day')} reason={signal.get('reason')}")
                    rec = self._reject_record(symbol, opt, opt_type, "confidence", atr=atr)
                    rec["confidence"] = round(confidence, 3)
                    rec["min_proba"] = min_proba
                    debug_candidates.append(rec)
                    rejected.append(rec)
                continue

            # Slippage adjustment for limit
            slippage = self.execution.estimate_slippage(opt["bid"], opt["ask"], opt.get("volume", 0))
            entry_price = opt["ask"] + slippage
            entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                entry_price, side="BUY", quick_mode=quick_mode
            )

            atr = market_data.get("atr", max(1.0, ltp * 0.002))
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
                    if debug_reasons:
                        rec = self._reject_record(symbol, opt, opt_type, "event_regime_blocked", atr=atr)
                        rejected.append(rec)
                    continue
                stop_mult = stop_mult * float(getattr(cfg, "REGIME_EVENT_STOP_MULT", 1.1))
                target_mult = target_mult * float(getattr(cfg, "REGIME_EVENT_TARGET_MULT", 1.4))
                size_mult = size_mult * float(getattr(cfg, "REGIME_EVENT_SIZE_MULT", 0.6))
            stop_loss, target = self._opt_risk_levels(
                entry_price, opt.get("bid", 0), opt.get("ask", 0), atr, stop_mult=stop_mult, target_mult=target_mult
            )

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
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "rr_gate", atr=atr)
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
            if score < min_score:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "trade_score", atr=atr)
                    rec["trade_score"] = score
                    rec["min_score"] = min_score
                    rejected.append(rec)
                continue

            tier = "EXPLORATION" if quick_mode else "MAIN"
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                str(opt.get("expiry", "")),
                opt.get("strike"),
                opt.get("type"),
                1,
            )
            if ident_err:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
                    rejected.append(rec)
                continue
            intent = self.trade_intent_flags(market_data, opt=opt)
            trade = Trade(
                trade_id=f"{symbol}-{opt['strike']}-{opt['type']}-{int(datetime.now().timestamp())}",
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=opt.get("type"),
                instrument_id=instrument_id,
                instrument_token=opt.get("instrument_token"),
                strike=opt["strike"],
                expiry=str(opt.get("expiry", "")),
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
                strategy=strategy_tag,
                regime=market_data.get("regime", "NEUTRAL"),
                tier=tier,
                day_type=market_data.get("day_type", "UNKNOWN"),
                entry_condition=entry_condition,
                entry_ref_price=entry_ref_price,
                opt_ltp=opt.get("ltp"),
                opt_bid=opt.get("bid"),
                opt_ask=opt.get("ask"),
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
                source_flags=dict(intent["source_flags"]),
            )
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
                print(f"[TradeBuilder] Top candidate {symbol} {rec.get('strike')} {rec.get('type')} rejected by {rec.get('reason')} (ltp={rec.get('ltp')})")

        if not candidates:
            if not allow_fallbacks:
                return None
            # Quick fallback: synthesize ATM option if chain is empty
            if quick_mode and market_data.get("ltp", 0):
                if market_data.get("chain_source") != "live":
                    return None
                try:
                    band_map = getattr(cfg, "PREMIUM_BANDS", {})
                    band = band_map.get(symbol, (getattr(cfg, "MIN_PREMIUM", 40), getattr(cfg, "MAX_PREMIUM", 150)))
                    min_p, max_p = band
                    ltp_opt = max(min_p, min(max_p, ltp * 0.004))
                    bid = round(ltp_opt * 0.995, 2)
                    ask = round(ltp_opt * 1.005, 2)
                    slippage = self.execution.estimate_slippage(bid, ask, 1000)
                    entry_price = ask + slippage
                    entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                        entry_price, side="BUY", quick_mode=True
                    )
                    atr = market_data.get("atr", max(1.0, ltp * 0.002))
                    stop_loss, target = self._opt_risk_levels(
                        entry_price, bid, ask, atr, stop_mult=1.0, target_mult=1.5
                    )
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {})
                    step = step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50))
                    atm_strike = int(round(ltp / step) * step) if step else 0
                    instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                        symbol,
                        "OPT",
                        str(market_data.get("expiry", "")),
                        atm_strike,
                        opt_type,
                        1,
                    )
                    if ident_err:
                        if debug_reasons:
                            rec = self._reject_record(symbol, {"strike": atm_strike}, opt_type, "missing_contract_fields", atr=atr)
                            rejected.append(rec)
                        return None
                    intent = self.trade_intent_flags(
                        market_data,
                        opt={
                            "quote_ok": True,
                            "quote_age_sec": 10**9,
                        },
                    )
                    trade = Trade(
                        trade_id=f"{symbol}-{opt_type}-ATM-QK-{ts}",
                        timestamp=datetime.now(),
                        symbol=symbol,
                        instrument="OPT",
                        instrument_type=instrument_type,
                        right=opt_type,
                        instrument_id=instrument_id,
                        instrument_token=None,
                        strike=atm_strike,
                        expiry=str(market_data.get("expiry", "")),
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
                        entry_condition=entry_condition,
                        entry_ref_price=entry_ref_price,
                        alpha_confidence=None,
                        alpha_uncertainty=None,
                        size_mult=1.0,
                        tradable=bool(intent["tradable"]),
                        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                        source_flags=dict(intent["source_flags"]),
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
                    if debug_reasons:
                        print(f"[TradeBuilder] Reject {symbol}: strategy_quarantined ({strat_name})")
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
                    if debug_reasons:
                        print(f"[TradeBuilder] Reject {symbol} {instrument}: {ident_err}")
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
                    source_flags=dict(intent["source_flags"]),
                )
                if trade.confidence >= getattr(cfg, "ML_MIN_PROBA", 0.6):
                    return trade
                if debug_reasons:
                    print(f"[TradeBuilder] Reject {symbol} {instrument}: low confidence")
                return None
            return None

        # Choose highest-confidence candidate
        return sorted(candidates, key=lambda t: (1 if getattr(t, "tradable", True) else 0, t.confidence), reverse=True)[0]

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
        Zero-hero: cheap option momentum (high reward, low premium).
        Defaults to bullish calls with strict confidence + momentum.
        """
        if not getattr(cfg, "ZERO_HERO_ENABLE", True):
            return None
        # Expiry-day special logic
        if (
            getattr(cfg, "ZERO_HERO_EXPIRY_ENABLE", True)
            and market_data.get("day_type") == "EXPIRY_DAY"
            and market_data.get("symbol") in ("NIFTY", "SENSEX", "BANKNIFTY")
        ):
            return self._build_zero_hero_expiry(market_data, debug_reasons=debug_reasons)
        symbol = market_data.get("symbol")
        ltp = market_data.get("ltp", 0)
        atr = market_data.get("atr", max(1.0, ltp * 0.002))
        ltp_change_window = market_data.get("ltp_change_window", 0) or 0
        htf_dir = market_data.get("htf_dir", "FLAT")
        if htf_dir == "DOWN":
            return None
        # Require meaningful move over window
        if atr and abs(ltp_change_window) < atr * getattr(cfg, "ZERO_HERO_ATR_MULT", 0.08):
            if debug_reasons:
                print(f"[ZeroHero] Reject {symbol}: weak momentum")
            return None

        opt_type = "CE" if ltp_change_window >= 0 else "PE"
        min_p = getattr(cfg, "ZERO_HERO_MIN_PREMIUM", 5)
        max_p = getattr(cfg, "ZERO_HERO_MAX_PREMIUM", 60)

        candidates = []
        rejected = []
        for opt in market_data.get("option_chain", []):
            if opt.get("type") != opt_type:
                continue
            if not opt.get("quote_ok", True):
                if debug_reasons:
                    rejected.append(self._reject_record(symbol, opt, opt_type, "no_quote", atr=atr))
                continue
            if opt.get("ltp", 0) < min_p or opt.get("ltp", 0) > max_p:
                continue
            if not self.execution.spread_ok(opt.get("bid", 0), opt.get("ask", 0), opt.get("ltp", 0) or 1):
                continue
            feats = pd.DataFrame([build_trade_features(market_data, opt)])
            # Use ML only when enough labeled history is available
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
                confidence = max(0.55, min(1.0, abs(ltp_change_window) / max(atr, 1.0)))
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
            allowed_life, _ = self._apply_lifecycle_gate("ZERO_HERO", mode="QUICK")
            if not allowed_life:
                if debug_reasons:
                    print(f"[ZeroHero] Reject {symbol}: lifecycle_gate (ZERO_HERO)")
                return None
            # Decay gating for ZERO_HERO
            allowed, adj_score, decay_size_mult, _ = self._apply_decay_gate("ZERO_HERO", confidence, size_mult)
            if not allowed:
                if debug_reasons:
                    print(f"[ZeroHero] Reject {symbol}: strategy_quarantined (ZERO_HERO)")
                return None
            if adj_score is not None:
                confidence = adj_score
            size_mult = min(size_mult, decay_size_mult)
            if confidence < getattr(cfg, "ZERO_HERO_MIN_PROBA", 0.6):
                continue
            slippage = self.execution.estimate_slippage(opt["bid"], opt["ask"], opt.get("volume", 0))
            entry_price = opt["ask"] + slippage
            entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                entry_price, side="BUY", quick_mode=True
            )
            stop_loss, target = self._opt_risk_levels(
                entry_price, opt.get("bid", 0), opt.get("ask", 0), atr,
                stop_mult=getattr(cfg, "ZERO_HERO_STOP_ATR", 0.6),
                target_mult=getattr(cfg, "ZERO_HERO_TARGET_ATR", 2.0),
            )
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                str(opt.get("expiry", "")),
                opt.get("strike"),
                opt.get("type"),
                1,
            )
            if ident_err:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
                    rejected.append(rec)
                continue
            intent = self.trade_intent_flags(market_data, opt=opt)
            trade = Trade(
                trade_id=f"{symbol}-{opt['type']}-{int(opt['strike'])}-ZERO-{ts}",
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=opt.get("type"),
                instrument_id=instrument_id,
                instrument_token=opt.get("instrument_token"),
                strike=opt["strike"],
                expiry=str(opt.get("expiry", "")),
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
                strategy="ZERO_HERO",
                regime=market_data.get("regime", "NEUTRAL"),
                tier="EXPLORATION",
                day_type=market_data.get("day_type", "UNKNOWN"),
                entry_condition=entry_condition,
                entry_ref_price=entry_ref_price,
                opt_ltp=opt.get("ltp"),
                opt_bid=opt.get("bid"),
                opt_ask=opt.get("ask"),
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
                source_flags=dict(intent["source_flags"]),
            )
            candidates.append(trade)
        if not candidates:
            return None
        return sorted(candidates, key=lambda t: (1 if getattr(t, "tradable", True) else 0, t.confidence), reverse=True)[0]

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
            entry_price = opt["ask"] + slippage
            entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                entry_price, side="BUY", quick_mode=True
            )
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
                    print(f"[ZeroHeroExpiry] Reject {symbol}: lifecycle_gate (ZERO_HERO_EXPIRY)")
                return None
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                str(opt.get("expiry", "")),
                opt.get("strike"),
                opt.get("type"),
                1,
            )
            if ident_err:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
                    rejected.append(rec)
                continue
            intent = self.trade_intent_flags(market_data, opt=opt)
            trade = Trade(
                trade_id=f"{symbol}-{opt['type']}-{int(opt['strike'])}-ZEROEXP-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                timestamp=datetime.now(),
                symbol=symbol,
                instrument="OPT",
                instrument_type=instrument_type,
                right=opt.get("type"),
                instrument_id=instrument_id,
                instrument_token=opt.get("instrument_token"),
                strike=opt["strike"],
                expiry=str(opt.get("expiry", "")),
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
                opt_ltp=opt.get("ltp"),
                opt_bid=opt.get("bid"),
                opt_ask=opt.get("ask"),
                quote_ok=opt.get("quote_ok", True),
                alpha_confidence=alpha_conf,
                alpha_uncertainty=alpha_unc,
                size_mult=size_mult,
                tradable=bool(intent["tradable"]),
                tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
                source_flags=dict(intent["source_flags"]),
            )
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
                print(f"[Scalp] Reject {symbol}: momentum too high")
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
                    print(f"[Scalp] Reject {symbol}: lifecycle_gate (SCALP)")
                return None
            allowed, adj_score, decay_size_mult, _ = self._apply_decay_gate("SCALP", confidence, size_mult)
            if not allowed:
                if debug_reasons:
                    print(f"[Scalp] Reject {symbol}: strategy_quarantined (SCALP)")
                return None
            if adj_score is not None:
                confidence = adj_score
            size_mult = min(size_mult, decay_size_mult)
            if confidence < getattr(cfg, "SCALP_MIN_PROBA", 0.58):
                continue
            slippage = self.execution.estimate_slippage(opt["bid"], opt["ask"], opt.get("volume", 0))
            entry_price = opt["ask"] + slippage
            entry_price, entry_condition, entry_ref_price = self._apply_entry_trigger(
                entry_price, side="BUY", quick_mode=True
            )
            stop_loss, target = self._opt_risk_levels(
                entry_price, opt.get("bid", 0), opt.get("ask", 0), atr,
                stop_mult=getattr(cfg, "SCALP_STOP_ATR", 0.3),
                target_mult=getattr(cfg, "SCALP_TARGET_ATR", 0.6),
            )
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            instrument_type, instrument_id, qty_units, ident_err = self._identity_fields(
                symbol,
                "OPT",
                str(opt.get("expiry", "")),
                opt.get("strike"),
                opt.get("type"),
                1,
            )
            if ident_err:
                if debug_reasons:
                    rec = self._reject_record(symbol, opt, opt_type, "missing_contract_fields", atr=atr)
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
                expiry=str(opt.get("expiry", "")),
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
                opt_ltp=opt.get("ltp"),
                opt_bid=opt.get("bid"),
                opt_ask=opt.get("ask"),
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
                source_flags=dict(intent["source_flags"]),
            )
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
            path = Path("logs/rejected_candidates.jsonl")
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
            path = Path("logs/debug_candidates.jsonl")
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
