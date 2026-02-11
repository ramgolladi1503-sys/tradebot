import time
import json
import argparse
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import replace
from strategies.trade_builder import TradeBuilder
from core.market_data import fetch_live_market_data
from core.risk_engine import RiskEngine
from core.execution_guard import ExecutionGuard
from core.trade_logger import log_trade, update_trade_outcome, update_trade_fill
from core.telegram_alerts import send_telegram_message, send_trade_ticket
from core.trade_ticket import TradeTicket
from core.trade_schema import build_instrument_id, validate_trade_identity
from core.auto_retrain import AutoRetrain
from ml.trade_predictor import TradePredictor
from core.execution_engine import ExecutionEngine
from core.execution_router import ExecutionRouter
from core.fill_quality import log_fill_quality
from core.risk_state import RiskState
from core.strategy_gatekeeper import StrategyGatekeeper
from core.portfolio_risk_allocator import PortfolioRiskAllocator
from core.exposure_ledger import ExposureLedger
from core.circuit_breaker import CircuitBreaker
from core.run_lock import RunLock
from core.governance import record_governance
from core.audit_log import append_event as audit_append, verify_chain as verify_audit_chain
from core.feed_health import check_and_trigger as check_feed_health
from core.incidents import create_incident, trigger_audit_chain_fail
from core.ml_governance import log_ab_trial
from rl.size_agent import SizeRLAgent, build_features
from config import config as cfg
from core.strategy_tracker import StrategyTracker
from ml.strategy_decay_predictor import generate_decay_report, telegram_summary
from core.kite_client import kite_client
from core import model_registry
from core.strategy_allocator import StrategyAllocator
from core.review_queue import add_to_queue, approval_status, order_payload_hash, QUICK_QUEUE_PATH, ZERO_HERO_QUEUE_PATH, SCALP_QUEUE_PATH
from core.blocked_tracker import BlockedTradeTracker
from core.trade_store import insert_execution_stat, update_trailing_state, insert_trail_event, insert_trade_leg, update_trade_close
from core.depth_store import depth_store
from core.kite_depth_ws import start_depth_ws, restart_depth_ws
from core.auto_tune import maybe_auto_tune
from core import risk_halt
from core.decision_logger import log_decision, update_execution, update_outcome
from core.risk_utils import to_pct
from core.time_utils import now_ist, now_utc_epoch, is_market_open_ist
from core.meta_model import MetaModel
from core.decision_trace import decision_config_snapshot
from core.reports.daily_audit import build_daily_audit, write_daily_audit_placeholder
from core.reports.execution_report import build_execution_report, write_execution_report_placeholder
from core.orchestrator_parts.cycle import run_live_monitoring
from core.orchestrator_parts import data as orchestrator_data
from core.orchestrator_parts import decisions as orchestrator_decisions
from core.orchestrator_parts import finalize as orchestrator_finalize
from core.session_guard import auto_clear_risk_halt_if_safe
from core.decision_store import DecisionStore
from core.decision_builder import build_decision
from core.decision_store import DecisionStore
from core.decision_builder import build_decision
from core.review_packet import build_review_packet, format_review_packet

class Orchestrator:
    def __init__(self, total_capital=100000, poll_interval=30, start_depth_ws_enabled=True):
        """
        Main orchestrator initializing all components
        """
        try:
            auto_clear_risk_halt_if_safe()
        except Exception as exc:
            print(f"[SessionGuard] startup check error: {exc}")
        self.total_capital = total_capital
        self.poll_interval = poll_interval

        # Unified RiskState
        self.risk_state = RiskState(start_capital=total_capital)

        # Phase C: Trade generation
        self.predictor = TradePredictor()
        self.execution_engine = ExecutionEngine()
        self.execution_router = ExecutionRouter()
        self.gatekeeper = StrategyGatekeeper()
        self.trade_builder = None

        # Phase B: Risk and execution
        self.risk_engine = RiskEngine(risk_state=self.risk_state)
        self.execution_guard = ExecutionGuard(risk_state=self.risk_state)
        self.portfolio_allocator = PortfolioRiskAllocator()

        # Phase F: Strategy tracking + Auto-retraining
        self.strategy_tracker = StrategyTracker()
        self.strategy_tracker.load("logs/strategy_perf.json")
        self.trade_builder = TradeBuilder(self.predictor, self.execution_engine, strategy_tracker=self.strategy_tracker)
        self.retrainer = AutoRetrain(self.predictor, risk_state=self.risk_state, strategy_tracker=self.strategy_tracker)
        self.strategy_allocator = StrategyAllocator(self.strategy_tracker, risk_state=self.risk_state)
        self.meta_model = MetaModel() if getattr(cfg, "META_MODEL_ENABLED", False) else None
        self.open_trades = {}
        self.trade_meta = {}
        self.last_trade_sync = 0
        self.blocked_tracker = BlockedTradeTracker()
        self.last_md_by_symbol = {}
        self.best_trade_logged = False
        self.best_trade_by_regime = {}
        self._last_decay_date = None
        self._pilot_check_cache = {"ts": 0, "ok": True, "reasons": []}
        self._decision_traces = []
        self.circuit_breaker = CircuitBreaker()
        self.run_lock = RunLock()
        self.exposure_ledger = ExposureLedger(total_capital=total_capital)
        self.decision_store = None
        if getattr(cfg, "DECISION_LOG_ENABLED", False):
            try:
                self.decision_store = DecisionStore(getattr(cfg, "DECISION_DB_PATH", cfg.TRADE_DB_PATH))
            except Exception as exc:
                print(f"[DecisionStore] init failed: {exc}")
                self.decision_store = None
        self.decision_store = None
        if getattr(cfg, "DECISION_LOG_ENABLED", False):
            try:
                self.decision_store = DecisionStore(getattr(cfg, "DECISION_DB_PATH", cfg.TRADE_DB_PATH))
            except Exception as exc:
                print(f"[DecisionStore] init failed: {exc}")
                self.decision_store = None

        # Portfolio tracking
        self.portfolio = {
            "capital": total_capital,
            "trades": [],
            "daily_loss": 0.0,
            "daily_profit": 0.0,
            "symbol_profit": {},
            "trades_today": 0,
            "equity_high": total_capital
        }
        self.last_trade_time = {}
        self.symbol_epsilon = {}
        self._load_symbol_eps()
        self.loss_streak = {}
        self._audit_chain_ok = True
        self._audit_chain_status = None
        try:
            ok, status, _ = verify_audit_chain()
            self._audit_chain_ok = ok
            self._audit_chain_status = status
            if not ok:
                try:
                    trigger_audit_chain_fail({"status": status})
                except Exception:
                    pass
        except Exception:
            pass
        if start_depth_ws_enabled:
            self._start_depth_ws()
        self.eps_history = []
        self._load_suggestion_eval()
        self.rl_size_agent = SizeRLAgent(cfg.RL_SIZE_MODEL_PATH) if getattr(cfg, "RL_ENABLED", False) else None

    def _infer_opt_type(self, trade_id: str | None):
        if not trade_id:
            return None
        tid = trade_id.upper()
        if "-CE-" in tid or tid.endswith("CE") or "CE-" in tid:
            return "CE"
        if "-PE-" in tid or tid.endswith("PE") or "PE-" in tid:
            return "PE"
        return None

    def _match_option_snapshot(self, trade, market_data: dict):
        chain = market_data.get("option_chain", []) or []
        if not chain:
            return None
        # Prefer instrument_token
        tok = getattr(trade, "instrument_token", None)
        if tok:
            for opt in chain:
                if opt.get("instrument_token") == tok:
                    return opt
        # Fallback: strike + type
        opt_type = self._infer_opt_type(getattr(trade, "trade_id", None))
        for opt in chain:
            if opt.get("strike") == getattr(trade, "strike", None):
                if opt_type and opt.get("type") != opt_type:
                    continue
                return opt
        return None

    def _calc_dte(self, expiry: str | None):
        if not expiry:
            return None
        try:
            exp = datetime.fromisoformat(expiry)
        except Exception:
            try:
                exp = datetime.strptime(expiry, "%Y-%m-%d")
            except Exception:
                return None
        return max((exp.date() - now_ist().date()).days, 0)

    def _open_risk(self):
        total = 0.0
        try:
            for lst in self.open_trades.values():
                for tr in lst:
                    total += float(getattr(tr, "capital_at_risk", 0.0) or 0.0)
        except Exception:
            pass
        return total

    def _refresh_exposure_snapshot(self):
        try:
            capital_base = self.portfolio.get("equity_high", self.portfolio.get("capital", self.total_capital))
            snap = self.exposure_ledger.snapshot_from_open_trades(
                self.open_trades,
                total_capital=capital_base,
            ).to_dict()
            self.portfolio["exposure_snapshot"] = snap
            self.portfolio["exposure_by_underlying"] = dict(snap.get("exposure_by_underlying") or {})
            self.portfolio["exposure_by_expiry"] = dict(snap.get("exposure_by_expiry") or {})
            self.portfolio["open_positions_count_by_underlying"] = dict(snap.get("open_positions_count_by_underlying") or {})
            self.portfolio["total_open_exposure"] = float(snap.get("total_open_exposure") or 0.0)
            return snap
        except Exception:
            return {}

    def _update_risk_pct_fields(self):
        return orchestrator_data.update_risk_pct_fields(self)

    def _quote_age_sec(self, quote_ts):
        return orchestrator_data.quote_age_sec(quote_ts)

    def _quote_ts_epoch(self, quote_ts):
        return orchestrator_data.quote_ts_epoch(quote_ts)

    def _pilot_audit_ok(self):
        if not getattr(cfg, "AUDIT_REQUIRED_TO_TRADE", True):
            return True, []
        day = (now_ist() - timedelta(days=1)).date().isoformat()
        audit_path = Path(f"logs/daily_audit_{day}.json")
        exec_path = Path(f"logs/execution_report_{day}.json")
        missing = []
        if not audit_path.exists():
            missing.append(audit_path.name)
        if not exec_path.exists():
            missing.append(exec_path.name)
        if missing:
            return False, [f"audit_missing:{','.join(missing)}"]
        return True, []

    def _pilot_models_ok(self):
        active = {
            "xgb": model_registry.get_active("xgb"),
            "deep": model_registry.get_active("deep"),
            "micro": model_registry.get_active("micro"),
            "ensemble": model_registry.get_active("ensemble"),
        }
        if not any(active.values()):
            return False, ["model_registry_empty"]
        return True, []

    def _pilot_feed_ok(self):
        from core.freshness_sla import get_freshness_status
        data = get_freshness_status(force=False)
        max_age = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
        depth_lag = (data.get("depth") or {}).get("age_sec")
        tick_lag = (data.get("ltp") or {}).get("age_sec")
        market_open = bool(data.get("market_open", is_market_open_ist()))
        if not market_open:
            return True, []
        if depth_lag is None or depth_lag > max_age:
            return False, ["depth_feed_stale"]
        if tick_lag is not None and tick_lag > max_age:
            return False, ["tick_feed_stale"]
        return True, []

    def _pilot_checks(self):
        if not getattr(cfg, "LIVE_PILOT_MODE", False):
            return True, []
        now = time.time()
        if now - self._pilot_check_cache.get("ts", 0) < 60:
            return self._pilot_check_cache["ok"], list(self._pilot_check_cache["reasons"])
        reasons = []
        if getattr(cfg, "RISK_PROFILE", "PILOT") != "PILOT":
            reasons.append("risk_profile_not_pilot")
        if not getattr(cfg, "LIVE_STRATEGY_WHITELIST", []):
            reasons.append("strategy_whitelist_empty")
        ok, r = self._pilot_audit_ok()
        if not ok:
            reasons.extend(r)
        ok, r = self._pilot_models_ok()
        if not ok:
            reasons.extend(r)
        ok, r = self._pilot_feed_ok()
        if not ok:
            reasons.extend(r)
        ok = len(reasons) == 0
        self._pilot_check_cache = {"ts": now, "ok": ok, "reasons": reasons}
        return ok, reasons

    def _pilot_exec_degradation(self):
        if not getattr(cfg, "LIVE_PILOT_MODE", False):
            return
        path = Path("logs/fill_quality_daily.json")
        if not path.exists():
            self.risk_state.set_mode("HARD_HALT", "pilot_fill_quality_missing")
            return
        try:
            data = json.loads(path.read_text())
        except Exception:
            self.risk_state.set_mode("HARD_HALT", "pilot_fill_quality_unreadable")
            return
        day = now_ist().date().isoformat()
        row = data.get(day)
        if not row:
            self.risk_state.set_mode("HARD_HALT", "pilot_fill_quality_empty")
            return
        fill_rate = row.get("fill_rate")
        max_miss = float(getattr(cfg, "EXEC_DEGRADATION_MAX_MISSED_FILL_RATE", 0.5))
        if fill_rate is not None:
            missed_rate = 1.0 - float(fill_rate)
            if missed_rate > max_miss:
                self.risk_state.set_mode("HARD_HALT", "pilot_missed_fill_rate")
                return
        baseline = float(getattr(cfg, "EXEC_BASELINE_SLIPPAGE", 0.0))
        if baseline <= 0:
            self.risk_state.set_mode("HARD_HALT", "pilot_slippage_baseline_missing")
            return
        slippage = row.get("avg_slippage_vs_mid")
        if slippage is not None:
            max_mult = float(getattr(cfg, "EXEC_DEGRADATION_MAX_SLIPPAGE_MULT", 2.0))
            if float(slippage) > baseline * max_mult:
                self.risk_state.set_mode("HARD_HALT", "pilot_slippage_degradation")
                return

    def _load_truth_dataset_for_reports(self):
        return orchestrator_data.load_truth_dataset_for_reports()

    def _write_cycle_reports(
        self,
        cycle_reason: str | None = None,
        decision_traces: list[dict] | None = None,
        config_snapshot: dict | None = None,
    ):
        return orchestrator_data.write_cycle_reports(
            cycle_reason=cycle_reason,
            decision_traces=decision_traces,
            config_snapshot=config_snapshot,
        )

    def _validate_market_snapshot(self, market_data: dict):
        return orchestrator_finalize.validate_market_snapshot(self, market_data)

    def _pilot_trade_gate(self, trade, market_data):
        return orchestrator_finalize.pilot_trade_gate(self, trade, market_data)

    def _build_decision_event(self, trade, market_data: dict, gatekeeper_allowed: bool, veto_reasons=None, pilot_allowed=None, pilot_reasons=None):
        return orchestrator_decisions.build_decision_event(
            self,
            trade,
            market_data,
            gatekeeper_allowed,
            veto_reasons=veto_reasons,
            pilot_allowed=pilot_allowed,
            pilot_reasons=pilot_reasons,
        )

    def _log_identity_error(self, trade, extra: dict | None = None) -> None:
        return orchestrator_decisions.log_identity_error(self, trade, extra=extra)

    def _log_decision_safe(self, event: dict, trade=None):
        return orchestrator_decisions.log_decision_safe(self, event, trade=trade, log_decision_fn=log_decision)

    def _instrument_id(self, trade):
        return orchestrator_decisions.instrument_id(self, trade)

    def _build_trade_ticket(self, trade, market_data: dict) -> TradeTicket:
        return orchestrator_decisions.build_trade_ticket(self, trade, market_data)

    def _log_meta_shadow(self, trade, market_data):
        return orchestrator_decisions.log_meta_shadow(self, trade, market_data)

    def _refresh_decay_report(self):
        return orchestrator_finalize.refresh_decay_report(self)

    def _runtime_safety_snapshot(self):
        snapshot = {}
        try:
            snapshot["circuit_breaker"] = self.circuit_breaker.state_dict()
        except Exception as exc:
            snapshot["circuit_breaker"] = {"error": f"circuit_breaker_state_error:{type(exc).__name__}"}
        try:
            snapshot["run_lock"] = self.run_lock.state_dict()
        except Exception as exc:
            snapshot["run_lock"] = {"error": f"run_lock_state_error:{type(exc).__name__}"}
        return snapshot

    def live_monitoring(self, run_once: bool = False):
        acquired, reason = self.run_lock.acquire()
        if not acquired:
            print(f"[RunLock] {reason}")
            try:
                audit_append(
                    {
                        "event": "RUN_LOCK_ACTIVE",
                        "reason": reason,
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception as exc:
                print(f"[RunLock] audit_error:{type(exc).__name__}")
            try:
                snap = decision_config_snapshot()
                snap.update(self._runtime_safety_snapshot())
                self._write_cycle_reports(
                    cycle_reason=reason,
                    decision_traces=[],
                    config_snapshot=snap,
                )
            except Exception as exc:
                print(f"[RunLock] report_error:{type(exc).__name__}")
            return {"ok": False, "reason": reason}
        try:
            return run_live_monitoring(self, run_once=run_once, time_module=time)
        finally:
            try:
                self.run_lock.release()
            except Exception as exc:
                print(f"[RunLock] release_error:{type(exc).__name__}")

    def _legacy_live_monitoring(self, run_once: bool = False):
        """
        Phase E: Live trading loop
        Fetch market data, generate trades, risk-check, execute, log, alert
        """
        print("[Orchestrator] Starting live monitoring...")
        while True:
            cycle_reason = "cycle_complete"
            self._decision_traces = []
            try:
                # Hot-reload config to pick up FORCE_REGIME changes
                try:
                    import importlib
                    from config import config as cfg
                    importlib.reload(cfg)
                except Exception:
                    pass
                if getattr(cfg, "KILL_SWITCH", False):
                    try:
                        self._log_decision_safe(self._build_decision_event(None, {"symbol": "GLOBAL"}, gatekeeper_allowed=False, veto_reasons=["kill_switch"]))
                        audit_append({"event": "KILL_SWITCH", "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})
                        create_incident("SEV1", "KILL_SWITCH", {"desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})
                    except Exception:
                        pass
                    time.sleep(self.poll_interval)
                    continue
                if risk_halt.is_halted():
                    time.sleep(self.poll_interval)
                    continue
                try:
                    if self.circuit_breaker.is_halted():
                        cycle_reason = self.circuit_breaker.halt_reason or "CB_ACTIVE"
                        continue
                except Exception as cb_exc:
                    print(f"[CircuitBreaker] state_error:{type(cb_exc).__name__}")
                # Feed health check (block pilot/live on stale feeds)
                try:
                    feed_health = check_feed_health()
                    live_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE"
                    pilot_mode = bool(getattr(cfg, "LIVE_PILOT_MODE", False))
                    reasons = set(feed_health.get("reasons") or [])
                    if is_market_open_ist() and (live_mode or pilot_mode):
                        if "tick_feed_stale" in reasons or "depth_feed_stale" in reasons:
                            restart_depth_ws(reason="sla:" + ",".join(sorted(reasons)))
                    tripped, cb_reason = self.circuit_breaker.observe_feed_health(bool(feed_health.get("ok", False)))
                    if tripped:
                        cycle_reason = cb_reason or "CB_FEED_UNHEALTHY"
                        try:
                            audit_append(
                                {
                                    "event": "CIRCUIT_BREAKER_TRIP",
                                    "reason": cycle_reason,
                                    "feed_health": feed_health,
                                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                }
                            )
                        except Exception as exc:
                            print(f"[CircuitBreaker] audit_error:{type(exc).__name__}")
                        try:
                            create_incident(
                                "SEV2",
                                cycle_reason,
                                {"feed_health": feed_health, "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")},
                            )
                        except Exception as exc:
                            print(f"[CircuitBreaker] incident_error:{type(exc).__name__}")
                    if (live_mode or pilot_mode) and (not feed_health.get("ok", True) or self.circuit_breaker.is_halted()):
                        if not feed_health.get("ok", True):
                            cycle_reason = "feed_unhealthy"
                        if self.circuit_breaker.is_halted():
                            cycle_reason = self.circuit_breaker.halt_reason or "CB_ACTIVE"
                        continue
                except Exception as feed_exc:
                    tripped, cb_reason = self.circuit_breaker.record_error("FEED_HEALTH_EXCEPTION")
                    cycle_reason = f"feed_health_exception:{type(feed_exc).__name__}"
                    if tripped:
                        cycle_reason = cb_reason or "CB_ERROR_STORM"
                    print(f"[FeedHealth ERROR] {type(feed_exc).__name__}")
                    continue
                # Daily decay report / strategy gating
                self._refresh_decay_report()
                market_data_list = fetch_live_market_data()  # List of dicts for multiple symbols
                self._evaluate_suggestions(market_data_list)
                try:
                    # Update consolidated loss streak (max across symbols)
                    try:
                        self.portfolio["loss_streak"] = max(self.loss_streak.values()) if self.loss_streak else 0
                    except Exception:
                        self.portfolio["loss_streak"] = self.portfolio.get("loss_streak", 0)
                    self.risk_state.update_portfolio(self.portfolio)
                except Exception:
                    pass
                try:
                    self._update_risk_pct_fields()
                except Exception:
                    pass
                try:
                    maybe_auto_tune()
                except Exception:
                    pass
                try:
                    self._pilot_exec_degradation()
                except Exception:
                    pass

                # Reset daily flags at new day
                try:
                    today = now_ist().date()
                    if not hasattr(self, "_last_day"):
                        self._last_day = today
                    if today != self._last_day:
                        self._last_day = today
                        self.best_trade_logged = False
                        self.best_trade_by_regime = {}
                        self.portfolio["daily_profit"] = 0.0
                        self.portfolio["daily_loss"] = 0.0
                        self.portfolio["trades_today"] = 0
                        self.portfolio["symbol_profit"] = {}
                        # reset expiry zero-hero trackers
                        if hasattr(self.trade_builder, "_expiry_zero_hero_loss_streak"):
                            self.trade_builder._expiry_zero_hero_loss_streak = {}
                        if hasattr(self.trade_builder, "_expiry_zero_hero_disabled_until"):
                            self.trade_builder._expiry_zero_hero_disabled_until = {}
                        if hasattr(self.trade_builder, "_expiry_zero_hero_pnl"):
                            self.trade_builder._expiry_zero_hero_pnl = {}
                except Exception:
                    pass

                max_trades_day = getattr(cfg, "MAX_TRADES_PER_DAY", 0)
                if getattr(cfg, "LIVE_PILOT_MODE", False):
                    max_trades_day = min(max_trades_day, int(getattr(cfg, "LIVE_MAX_TRADES_PER_DAY", 2)))

                for market_data in market_data_list:
                    snap_ok, halt_cycle = self._validate_market_snapshot(market_data)
                    if not snap_ok:
                        if halt_cycle:
                            break
                        continue
                    try:
                        self.risk_state.update_market(market_data.get("symbol"), market_data)
                    except Exception:
                        pass
                    if self.risk_state.mode == "HARD_HALT":
                        try:
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["hard_halt"])
                            self._log_decision_safe(event)
                            audit_append({"event": "HARD_HALT", "symbol": market_data.get("symbol"), "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})
                            create_incident("SEV1", "HARD_HALT", {"symbol": market_data.get("symbol")})
                        except Exception:
                            pass
                        continue
                    if self.portfolio.get("trades_today", 0) >= max_trades_day:
                        try:
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["max_trades_per_day"])
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        continue
                    if getattr(cfg, "LIVE_PILOT_MODE", False):
                        ok, reasons = self._pilot_checks()
                        if not ok:
                            try:
                                event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["pilot_precheck"], pilot_allowed=0, pilot_reasons=reasons)
                                self._log_decision_safe(event)
                            except Exception:
                                pass
                            continue
                    self._sync_trades()
                    sym = market_data.get("symbol")
                    if sym and sym.upper() in getattr(cfg, "HALT_SYMBOLS", []):
                        try:
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["halt_symbol"])
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        continue
                    if sym:
                        self.last_md_by_symbol[sym] = market_data
                    # Check exits for any open trades on this symbol/instrument
                    self._check_open_trades(market_data)
                    cooldown = getattr(cfg, "MIN_COOLDOWN_SEC", 300)
                    last_t = self.last_trade_time.get(sym)
                    if last_t and time.time() - last_t < cooldown:
                        continue
                    # Phase C: Build trade suggestion
                    indicators_ok = market_data.get("indicators_ok", True)
                    indicators_age = market_data.get("indicators_age_sec")
                    if indicators_age is None:
                        indicators_age = 0
                    indicators_stale = indicators_age > getattr(cfg, "INDICATOR_STALE_SEC", 120)
                    allow_main = indicators_ok and not indicators_stale
                    if not allow_main:
                        try:
                            veto = "indicators_missing" if not indicators_ok else "indicators_stale"
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=[veto])
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        continue
                    debug_flag = getattr(cfg, "DEBUG_TRADE_REASONS", False) or getattr(cfg, "DEBUG_TRADE_MODE", False)
                    trade = None
                    if allow_main:
                        gate = self.gatekeeper.evaluate(market_data, mode="MAIN")
                        if not gate.allowed:
                            if debug_flag:
                                print(f"[Gatekeeper] Blocked {sym}: {','.join(gate.reasons)}")
                            try:
                                event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=gate.reasons)
                                self._log_decision_safe(event)
                                audit_append({"event": "GATEKEEPER_BLOCK", "symbol": sym, "reasons": gate.reasons, "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})
                            except Exception:
                                pass
                            continue
                        trade, decision_trace = self.trade_builder.build_with_trace(
                            market_data,
                            quick_mode=False,
                            debug_reasons=debug_flag,
                            force_family=gate.family,
                            allow_fallbacks=False,
                            allow_baseline=False,
                        )
                        if decision_trace is not None:
                            try:
                                self._decision_traces.append(decision_trace.to_dict())
                            except Exception:
                                pass
                    if trade is None:
                        if self.decision_store is not None:
                            try:
                                decision = build_decision(
                                    meta={
                                        "ts_epoch": time.time(),
                                        "run_id": f"{sym}-NO_TRADE",
                                        "symbol": sym,
                                        "timeframe": str(market_data.get("timeframe", "")),
                                    },
                                    market={
                                        "spot": float(market_data.get("spot", market_data.get("ltp", 0.0)) or 0.0),
                                        "vwap": market_data.get("vwap"),
                                        "trend_state": str(market_data.get("trend_state", "")),
                                        "regime": str(market_data.get("regime", "")),
                                        "vol_state": str(market_data.get("vol_state", "")),
                                        "iv": market_data.get("iv"),
                                        "ivp": market_data.get("ivp"),
                                    },
                                    outcome={"status": "skipped", "reject_reasons": ["no_trade_generated"]},
                                )
                                self.decision_store.save_decision(decision)
                            except Exception as exc:
                                print(f"[DecisionStore] save skipped decision failed: {exc}")
                        continue
                    if str(trade.strategy).upper() in getattr(cfg, "HALT_STRATEGIES", []):
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": ["halt_strategy"]})
                        except Exception:
                            pass
                        continue
                    # Optional cross-asset staleness: downsize but do not block.
                    try:
                        cross_q = market_data.get("cross_asset_quality", {}) or {}
                        optional = set(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
                        stale = set(cross_q.get("stale_feeds", []) or [])
                        missing = set((cross_q.get("missing") or {}).keys())
                        if (stale | missing) & optional:
                            mult = float(getattr(cfg, "CROSS_ASSET_OPTIONAL_SIZE_MULT", 0.85))
                            current = float(getattr(trade, "size_mult", 1.0) or 1.0)
                            trade = replace(trade, size_mult=min(current, mult))
                    except Exception:
                        pass
                    # Spread suggestions (advisory only; defined-risk)
                    try:
                        gate_for_spread = self.gatekeeper.evaluate(market_data, mode="SPREAD")
                        if gate_for_spread.allowed and gate_for_spread.family in ("DEFINED_RISK",):
                            spreads = self.trade_builder.build_spread_suggestions(market_data)
                            for sp in spreads:
                                add_to_queue(type("Obj", (), sp))
                    except Exception:
                        pass
                    if not trade:
                        try:
                            reason = None
                            try:
                                reason = (self.trade_builder._reject_ctx or {}).get("reason")
                            except Exception:
                                reason = None
                            veto = [reason] if reason else ["no_trade_generated"]
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=True, veto_reasons=veto)
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        # Track blocked candidates for paper outcome evaluation
                        try:
                            self.blocked_tracker.capture_from_log()
                        except Exception:
                            pass
                        # No quick/baseline fallback trades in live mode
                        # Keep only strategy-specific queues if allowed by gatekeeper
                        try:
                            if str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE" and not getattr(cfg, "ALLOW_AUX_TRADES_LIVE", False):
                                continue
                            gate = self.gatekeeper.evaluate(market_data, mode="AUX")
                            if gate.allowed and gate.family == "TREND":
                                zero_trade = self.trade_builder.build_zero_hero(
                                    market_data,
                                    debug_reasons=debug_flag
                                )
                                if zero_trade:
                                    add_to_queue(zero_trade, queue_path=ZERO_HERO_QUEUE_PATH, extra={"category": "zero_hero", "tier": "EXPLORATION"})
                            if gate.allowed and gate.family == "MEAN_REVERT":
                                scalp_trade = self.trade_builder.build_scalp(
                                    market_data,
                                    debug_reasons=debug_flag
                                )
                                if scalp_trade:
                                    add_to_queue(scalp_trade, queue_path=SCALP_QUEUE_PATH, extra={"category": "scalp", "tier": "EXPLORATION"})
                        except Exception:
                            pass
                        continue
                    # RiskState: register attempt and approve
                    decision_id = None
                    try:
                        event = self._build_decision_event(trade, market_data, gatekeeper_allowed=True, veto_reasons=[])
                        if event.get("instrument_id") is None:
                            veto = event.get("veto_reasons") or []
                            if "missing_contract_fields" not in veto:
                                veto.append("missing_contract_fields")
                            event["veto_reasons"] = veto
                            self._log_identity_error(trade, event)
                            try:
                                self._log_decision_safe(event, trade)
                            except Exception:
                                pass
                            continue
                        decision_id = self._log_decision_safe(event, trade)
                        self._log_meta_shadow(trade, market_data)
                    except Exception:
                        decision_id = trade.trade_id
                    if self.decision_store is not None:
                        try:
                            decision = build_decision(
                                meta={
                                    "ts_epoch": time.time(),
                                    "run_id": decision_id or trade.trade_id,
                                    "symbol": sym,
                                    "timeframe": str(market_data.get("timeframe", "")),
                                },
                                market={
                                    "spot": float(market_data.get("spot", market_data.get("ltp", 0.0)) or 0.0),
                                    "vwap": market_data.get("vwap"),
                                    "trend_state": str(market_data.get("trend_state", "")),
                                    "regime": str(market_data.get("regime", "")),
                                    "vol_state": str(market_data.get("vol_state", "")),
                                    "iv": market_data.get("iv"),
                                    "ivp": market_data.get("ivp"),
                                },
                                signals={
                                    "pattern_flags": list(getattr(trade, "pattern_flags", []) or []),
                                    "rank_score": getattr(trade, "trade_score", None),
                                    "confidence": getattr(trade, "confidence", None),
                                },
                                strategy={
                                    "name": str(getattr(trade, "strategy", "")),
                                    "legs": list(getattr(trade, "legs", []) or []),
                                    "direction": str(getattr(trade, "side", "")),
                                    "entry_reason": str(getattr(trade, "entry_reason", "")),
                                    "stop": float(getattr(trade, "stop_loss", 0.0) or 0.0),
                                    "target": float(getattr(trade, "target", 0.0) or 0.0),
                                    "rr": float(getattr(trade, "rr", 0.0) or 0.0),
                                    "max_loss": float(getattr(trade, "max_loss", 0.0) or 0.0),
                                    "size": float(getattr(trade, "qty", 0.0) or 0.0),
                                },
                                risk={
                                    "daily_loss_limit": float(getattr(cfg, "MAX_DAILY_LOSS_PCT", 0.0)),
                                    "position_limit": float(getattr(cfg, "MAX_TRADES_PER_DAY", 0.0)),
                                    "slippage_bps_assumed": float(getattr(cfg, "SLIPPAGE_BPS", 0.0)),
                                },
                                outcome={"status": "planned", "reject_reasons": []},
                            )
                            self.decision_store.save_decision(decision)
                        except Exception as exc:
                            print(f"[DecisionStore] save decision failed: {exc}")
                    try:
                        self.risk_state.record_trade_attempt(trade)
                        ok, reason = self.risk_state.approve(trade)
                        if not ok:
                            if debug_flag:
                                print(f"[RiskState] Trade blocked: {reason}")
                            try:
                                update_execution(trade.trade_id, {"risk_allowed": 0, "veto_reasons": [reason]})
                            except Exception:
                                pass
                            if self.decision_store is not None and decision_id:
                                try:
                                    self.decision_store.update_status(decision_id, "rejected", reject_reasons=[reason])
                                except Exception as exc:
                                    print(f"[DecisionStore] update rejected failed: {exc}")
                            continue
                        try:
                            update_execution(trade.trade_id, {"risk_allowed": 1})
                        except Exception:
                            pass
                    except Exception:
                        pass
                    if self.strategy_tracker.is_disabled(
                        trade.strategy,
                        min_trades=getattr(cfg, "STRATEGY_MIN_TRADES", 30),
                        threshold=getattr(cfg, "STRATEGY_DISABLE_THRESHOLD", 0.45)
                    ):
                        print(f"[StrategyTracker] Disabled strategy: {trade.strategy}")
                        continue
                    # Decay-based gating
                    action, _prob = self.strategy_tracker.decay_action(trade.strategy)
                    if action == "hard":
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": ["decay_quarantine"]})
                        except Exception:
                            pass
                        continue
                    elif action == "soft":
                        try:
                            trade.size_mult = (trade.size_mult or 1.0) * float(getattr(cfg, "DECAY_DOWNSIZE_MULT", 0.6))
                            update_execution(trade.trade_id, {"action_size_multiplier": trade.size_mult})
                        except Exception:
                            pass
                    # Best trade per day filter
                    if getattr(cfg, "BEST_TRADE_PER_DAY", True) and self.best_trade_logged:
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": ["best_trade_per_day"]})
                        except Exception:
                            pass
                        continue
                    # Best trade per regime filter
                    if getattr(cfg, "BEST_TRADE_PER_REGIME", True):
                        rkey = trade.regime or "NEUTRAL"
                        if self.best_trade_by_regime.get(rkey):
                            try:
                                update_execution(trade.trade_id, {"veto_reasons": ["best_trade_per_regime"]})
                            except Exception:
                                pass
                            continue
                    # Adjust epsilon by regime (lower in choppy regimes)
                    base_eps = self.symbol_epsilon.get(sym, cfg.STRATEGY_EPSILON)
                    regime = market_data.get("primary_regime") or market_data.get("regime") or "NEUTRAL"
                    if regime == "CHOPPY":
                        cfg.STRATEGY_EPSILON = max(0.02, base_eps * 0.5)
                    elif regime == "TREND":
                        cfg.STRATEGY_EPSILON = min(0.2, base_eps * 1.2)
                    if not self.strategy_allocator.should_trade(trade.strategy):
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": ["strategy_allocator"]})
                        except Exception:
                            pass
                        continue
                    self.symbol_epsilon[sym] = cfg.STRATEGY_EPSILON
                    self._save_symbol_eps()
                    cfg.STRATEGY_EPSILON = base_eps

                    # A/B paper trading log (shadow model)
                    try:
                        if getattr(cfg, "ML_AB_ENABLE", False) and getattr(trade, "shadow_confidence", None) is not None:
                            mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
                            log_ab_trial(
                                trade.trade_id,
                                trade.symbol,
                                now_ist().isoformat(),
                                trade.confidence,
                                trade.shadow_confidence,
                                getattr(trade, "model_version", None),
                                getattr(trade, "shadow_model_version", None),
                                mode=mode,
                                extra={"strategy": trade.strategy, "regime": trade.regime},
                            )
                    except Exception:
                            pass

                    # Pilot gating (strategy whitelist + quote/spread strictness)
                    if getattr(cfg, "LIVE_PILOT_MODE", False):
                        pilot_allowed, pilot_reasons = self._pilot_trade_gate(trade, market_data)
                        if not pilot_allowed:
                            try:
                                update_execution(trade.trade_id, {"pilot_allowed": 0, "pilot_reasons": pilot_reasons, "veto_reasons": pilot_reasons})
                            except Exception:
                                pass
                            continue
                        try:
                            update_execution(trade.trade_id, {"pilot_allowed": 1})
                        except Exception:
                            pass

                    # Manual approval gate (strong trades)
                    approval_payload_hash = order_payload_hash(trade)
                    approved, approval_reason = approval_status(trade.trade_id, payload_hash=approval_payload_hash)
                    if cfg.MANUAL_APPROVAL and not approved:
                        # Pre-trade validation report
                        rr = None
                        try:
                            rr = abs(trade.target - trade.entry_price) / max(abs(trade.entry_price - trade.stop_loss), 1e-6)
                        except Exception:
                            rr = None
                        # Regime-aware confidence threshold
                        min_conf = getattr(cfg, "ML_MIN_PROBA", 0.6)
                        mult = getattr(cfg, "REGIME_PROBA_MULT", {}).get(trade.regime or "NEUTRAL", 1.0)
                        min_conf = min_conf * mult
                        validation = {
                            "pretrade_conf_ok": trade.confidence >= min_conf,
                            "pretrade_rr": round(rr, 2) if rr is not None else None,
                            "pretrade_rr_ok": rr is not None and rr >= 1.2,
                            "pretrade_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "approval_payload_hash": approval_payload_hash,
                            "approval_reason": approval_reason,
                        }
                        review_packet = build_review_packet(
                            trade,
                            market_data=market_data,
                            risk_policy={
                                "position_sizing_cap": getattr(cfg, "MAX_QTY", None),
                                "time_window_validity_sec": getattr(trade, "validity_sec", None),
                                "allow_reason": "manual_approval_required",
                            },
                        )
                        review_packet_text = format_review_packet(review_packet)
                        validation["review_packet"] = review_packet
                        validation["review_packet_text"] = review_packet_text
                        add_to_queue(trade, extra=dict(validation, **{"tier": "MAIN"}))
                        print(f"[ReviewQueue] Trade queued: {trade.trade_id}")
                        try:
                            send_telegram_message(review_packet_text)
                        except Exception:
                            pass
                        try:
                            audit_append(
                                {
                                    "event": "APPROVAL_REVIEW_PACKET",
                                    "trade_id": trade.trade_id,
                                    "symbol": trade.symbol,
                                    "strategy": trade.strategy,
                                    "review_packet": review_packet,
                                    "approval_payload_hash": approval_payload_hash,
                                    "approval_reason": approval_reason,
                                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                }
                            )
                        except Exception:
                            pass
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": [f"manual_approval_pending:{approval_reason}"]})
                        except Exception:
                            pass
                        continue

                    # Phase B: Risk validation
                    exposure_snapshot = self._refresh_exposure_snapshot()
                    allowed, reason = self.risk_engine.allow_trade(
                        self.portfolio,
                        trade=trade,
                        exposure_state=exposure_snapshot,
                    )
                    if not allowed:
                        print(f"[RiskEngine] Trade blocked: {reason}")
                        if reason.lower().startswith("daily loss"):
                            risk_halt.set_halt("Daily loss limit hit")
                            send_telegram_message("Auto-halt: daily loss limit hit.")
                        try:
                            self._decision_traces.append(
                                {
                                    "run_id": f"{trade.trade_id}-risk",
                                    "symbol": sym,
                                    "ts": now_utc_epoch(),
                                    "inputs_snapshot": {
                                        "symbol": sym,
                                        "instrument_id": self._instrument_id(trade),
                                    },
                                    "features_snapshot": {},
                                    "score_breakdown": {
                                        "confidence": getattr(trade, "confidence", None),
                                        "trade_score": getattr(trade, "trade_score", None),
                                    },
                                    "gate_results": {
                                        "risk_engine_allowed": False,
                                        "exposure_snapshot": exposure_snapshot,
                                    },
                                    "final_decision": "BLOCKED",
                                    "reasons": [str(reason)],
                                }
                            )
                        except Exception:
                            pass
                        try:
                            update_execution(trade.trade_id, {"risk_allowed": 0, "veto_reasons": [reason]})
                        except Exception:
                            pass
                        continue
                    else:
                        try:
                            update_execution(trade.trade_id, {"risk_allowed": 1})
                        except Exception:
                            pass

                    # Phase B: Portfolio-level allocator (correlation + factor exposure + stress)
                    alloc = self.portfolio_allocator.allocate(trade, self.portfolio, market_data, self.last_md_by_symbol)
                    if not alloc.allowed:
                        print(f"[PortfolioAllocator] Trade blocked: {alloc.reason}")
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": [alloc.reason]})
                        except Exception:
                            pass
                        continue
                    try:
                        detail = trade.trade_score_detail or {}
                        detail = {**detail, "portfolio_alloc": alloc.report}
                        trade = replace(trade, trade_score_detail=detail)
                    except Exception:
                        pass
                    try:
                        current = alloc.report.get("current_exposure", {}) if isinstance(alloc.report, dict) else {}
                        update_execution(trade.trade_id, {
                            "delta_exposure": current.get("delta"),
                            "gamma_exposure": current.get("gamma"),
                            "vega_exposure": current.get("vega"),
                            "open_risk": self._open_risk(),
                        })
                    except Exception:
                        pass

                    # Risk-based sizing
                    lot_size = getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1)
                    current_vol = (market_data.get("atr", 0) / market_data.get("ltp", 1)) if market_data.get("ltp") else None
                    streak = self.loss_streak.get(trade.symbol, 0)
                    sized_qty = self.risk_engine.size_trade(trade, self.portfolio["capital"], lot_size, current_vol=current_vol, loss_streak=streak)
                    final_qty = min(sized_qty, alloc.max_qty) if alloc.max_qty else sized_qty
                    if getattr(cfg, "LIVE_PILOT_MODE", False):
                        final_qty = min(final_qty, int(getattr(cfg, "LIVE_MAX_LOTS", 1)))
                    if final_qty <= 0:
                        print("[PortfolioAllocator] Trade blocked: qty<=0 after allocation")
                        continue
                    # RL sizing agent (shadow or live)
                    if getattr(cfg, "RL_ENABLED", False):
                        mult = 1.0
                        feats = None
                        if self.rl_size_agent:
                            try:
                                feats = build_features(trade, market_data, self.risk_state, self.portfolio, self.last_md_by_symbol)
                                mult = self.rl_size_agent.select_multiplier(feats, explore=False)
                            except Exception:
                                mult = 1.0
                                feats = None
                        try:
                            update_execution(trade.trade_id, {"action_size_multiplier": mult})
                        except Exception:
                            pass
                        if getattr(cfg, "RL_SHADOW_ONLY", True):
                            # log shadow decision, no sizing change
                            try:
                                with open("logs/rl_size_shadow.jsonl", "a") as f:
                                    f.write(json.dumps({
                                        "timestamp": time.time(),
                                        "trade_id": trade.trade_id,
                                        "symbol": trade.symbol,
                                        "baseline_qty": final_qty,
                                        "suggested_qty": int(round(final_qty * mult)),
                                        "multiplier": mult,
                                        "features": feats
                                    }) + "\n")
                            except Exception:
                                pass
                        else:
                            final_qty = int(round(final_qty * mult))
                            if final_qty <= 0:
                                print("[RLSize] Trade blocked: qty<=0 after RL sizing")
                                continue
                    trade = replace(trade, qty=final_qty, capital_at_risk=round((trade.entry_price - trade.stop_loss) * final_qty * lot_size, 2))
                    # Phase B: Execution guard (after sizing)
                    approved, reason = self.execution_guard.validate(trade, self.portfolio, trade.regime)
                    if not approved:
                        print(f"[ExecutionGuard] Trade blocked: {reason}")
                        try:
                            blocked_reasons = list(getattr(trade, "tradable_reasons_blocking", []) or [])
                            blocked_reasons.append(f"risk_guard_failed:{reason}")
                            source_flags = dict(getattr(trade, "source_flags", {}) or {})
                            source_flags["risk_guard_passed"] = False
                            blocked_trade = replace(
                                trade,
                                tradable=False,
                                tradable_reasons_blocking=blocked_reasons,
                                source_flags=source_flags,
                            )
                            ticket = self._build_trade_ticket(blocked_trade, market_data)
                            send_trade_ticket(ticket)
                        except Exception:
                            pass
                        try:
                            update_execution(trade.trade_id, {"exec_guard_allowed": 0, "veto_reasons": [reason]})
                        except Exception:
                            pass
                        continue
                    else:
                        try:
                            update_execution(trade.trade_id, {"exec_guard_allowed": 1})
                        except Exception:
                            pass
                        try:
                            source_flags = dict(getattr(trade, "source_flags", {}) or {})
                            source_flags["risk_guard_passed"] = True
                            trade = replace(trade, source_flags=source_flags)
                        except Exception:
                            pass

                    # Price confirmation entry (avoid false starts)
                    if getattr(cfg, "PRICE_CONFIRM_ENABLE", True):
                        if getattr(cfg, "PRICE_CONFIRM_VWAP", True):
                            vwap = market_data.get("vwap", trade.entry_price)
                            ltp = market_data.get("ltp", 0)
                            if trade.side == "BUY" and ltp < vwap:
                                continue
                            if trade.side == "SELL" and ltp > vwap:
                                continue
                        else:
                            confirm = getattr(cfg, "PRICE_CONFIRM_PCT", 0.001)
                            if trade.side == "BUY" and market_data.get("ltp", 0) < trade.entry_price * (1 + confirm):
                                continue
                            if trade.side == "SELL" and market_data.get("ltp", 0) > trade.entry_price * (1 - confirm):
                                continue

                    # Execute trade (simulation only)
                    # Require real quotes (no synthetic bid/ask)
                    if trade.instrument == "OPT":
                        bid = trade.opt_bid
                        ask = trade.opt_ask
                        if not bid or not ask or not getattr(trade, "quote_ok", True):
                            log_fill_quality({
                                "ts": time.time(),
                                "trade_id": getattr(trade, "trade_id", None),
                                "symbol": getattr(trade, "symbol", None),
                                "instrument": getattr(trade, "instrument", None),
                                "side": getattr(trade, "side", None),
                                "decision_bid": bid,
                                "decision_ask": ask,
                                "decision_mid": None,
                                "decision_spread": None,
                                "limit_price": getattr(trade, "entry_price", None),
                                "fill_price": None,
                                "not_filled_reason": "missing_option_quotes",
                                "time_to_fill": None,
                                "slippage_vs_mid": None,
                            })
                            print("[ExecutionEngine] Missing/invalid option quotes. Skipping.")
                            continue
                    else:
                        bid = market_data.get("bid")
                        ask = market_data.get("ask")
                        if not bid or not ask:
                            log_fill_quality({
                                "ts": time.time(),
                                "trade_id": getattr(trade, "trade_id", None),
                                "symbol": getattr(trade, "symbol", None),
                                "instrument": getattr(trade, "instrument", None),
                                "side": getattr(trade, "side", None),
                                "decision_bid": bid,
                                "decision_ask": ask,
                                "decision_mid": None,
                                "decision_spread": None,
                                "limit_price": getattr(trade, "entry_price", None),
                                "fill_price": None,
                                "not_filled_reason": "missing_index_quotes",
                                "time_to_fill": None,
                                "slippage_vs_mid": None,
                            })
                            print("[ExecutionEngine] Missing live quotes. Skipping.")
                            continue
                    volume = market_data.get("volume", 0)
                    depth = None
                    if trade.instrument_token:
                        d = depth_store.get(trade.instrument_token)
                        depth = d.get("depth") if d else None
                    bid0 = bid
                    ask0 = ask
                    def _snapshot():
                        try:
                            if trade.instrument_token:
                                d = depth_store.get(trade.instrument_token)
                                if d and d.get("depth"):
                                    dep = d.get("depth")
                                    b = dep.get("buy", [{}])[0].get("price", bid0)
                                    a = dep.get("sell", [{}])[0].get("price", ask0)
                                    return {"bid": b, "ask": a, "ts": time.time(), "depth": dep}
                        except Exception:
                            pass
                        return {"bid": bid0, "ask": ask0, "ts": time.time(), "depth": depth}

                    filled, fill_price, fill_report = self.execution_router.execute(
                        trade,
                        bid,
                        ask,
                        volume,
                        depth=depth,
                        snapshot_fn=_snapshot,
                        spread_pct=market_data.get("spread_pct"),
                        depth_imbalance=market_data.get("depth_imbalance"),
                        vol_z=market_data.get("vol_z"),
                    )
                    try:
                        self.risk_state.record_fill(filled)
                    except Exception:
                        pass
                    if not filled:
                        if fill_report and fill_report.get("reason_if_aborted"):
                            print(f"[ExecutionEngine] Fill aborted: {fill_report.get('reason_if_aborted')}")
                        else:
                            print("[ExecutionEngine] Limit order not filled.")
                        try:
                            update_execution(trade.trade_id, {
                                "filled_bool": 0,
                                "fill_price": None,
                                "time_to_fill": fill_report.get("time_to_fill") if fill_report else None,
                                "slippage_vs_mid": fill_report.get("slippage_vs_mid") if fill_report else None,
                                "veto_reasons": [fill_report.get("reason_if_aborted")] if fill_report else ["not_filled"],
                            })
                        except Exception:
                            pass
                        if self.decision_store is not None and decision_id:
                            try:
                                self.decision_store.update_status(
                                    decision_id,
                                    "rejected",
                                    reject_reasons=[fill_report.get("reason_if_aborted") if fill_report else "not_filled"],
                                )
                            except Exception as exc:
                                print(f"[DecisionStore] update not_filled failed: {exc}")
                        continue
                    trade = replace(trade, entry_price=fill_price)
                    try:
                        update_execution(trade.trade_id, {
                            "filled_bool": 1,
                            "fill_price": fill_price,
                            "time_to_fill": fill_report.get("time_to_fill") if fill_report else None,
                            "slippage_vs_mid": fill_report.get("slippage_vs_mid") if fill_report else None,
                        })
                    except Exception:
                        pass
                    if self.decision_store is not None and decision_id:
                        try:
                            self.decision_store.update_status(decision_id, "filled")
                        except Exception as exc:
                            print(f"[DecisionStore] update filled failed: {exc}")

                    self.portfolio["trades"].append(trade)
                    self.portfolio["capital"] -= getattr(trade, "capital_at_risk", 0)
                    self.portfolio["trades_today"] += 1
                    self.last_trade_time[sym] = time.time()
                    if getattr(cfg, "BEST_TRADE_PER_DAY", True):
                        self.best_trade_logged = True
                    if getattr(cfg, "BEST_TRADE_PER_REGIME", True):
                        rkey = trade.regime or "NEUTRAL"
                        self.best_trade_by_regime[rkey] = True

                    # Log trade
                    extra = {}
                    if market_data.get("option_chain"):
                        for opt in market_data["option_chain"]:
                            if opt.get("strike") == trade.strike and opt.get("type") in ("CE", "PE"):
                                if "micro_pred" in opt:
                                    extra["micro_pred"] = opt["micro_pred"]
                                break
                    if getattr(trade, "model_version", None):
                        extra["model_version"] = getattr(trade, "model_version", None)
                    if getattr(trade, "shadow_model_version", None):
                        extra["shadow_model_version"] = getattr(trade, "shadow_model_version", None)
                    if getattr(trade, "shadow_confidence", None) is not None:
                        extra["shadow_confidence"] = getattr(trade, "shadow_confidence", None)
                    if getattr(trade, "alpha_confidence", None) is not None:
                        extra["alpha_confidence"] = getattr(trade, "alpha_confidence", None)
                    if getattr(trade, "alpha_uncertainty", None) is not None:
                        extra["alpha_uncertainty"] = getattr(trade, "alpha_uncertainty", None)
                    if getattr(trade, "size_mult", None) is not None:
                        extra["size_mult"] = getattr(trade, "size_mult", None)
                    # Paper strict: mark aux/quick/scalp/zero-hero so they don't affect main perf stats
                    if str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "PAPER" and getattr(cfg, "PAPER_STRICT_MODE", False):
                        if getattr(trade, "tier", "MAIN") != "MAIN" or trade.strategy in ("SCALP", "ZERO_HERO", "ZERO_HERO_EXPIRY") or trade.strategy.startswith("QUICK"):
                            extra["paper_aux"] = True
                    if fill_report:
                        extra["fill_quality"] = fill_report
                        try:
                            score = fill_report.get("execution_quality_score")
                            if score is not None:
                                extra["execution_quality_score"] = score
                                self.strategy_tracker.record_execution_quality(trade.strategy, score)
                        except Exception:
                            pass
                    try:
                        ledger_hash = record_governance(trade, market_data, self.risk_state, fill_report, extra=extra)
                        extra["ledger_hash"] = ledger_hash
                    except Exception:
                        pass
                    log_trade(trade, extra=extra)
                    self._track_open_trade(trade, market_data)

                    # Telegram alert (actionable trades only)
                    try:
                        ticket = self._build_trade_ticket(trade, market_data)
                        actionable, reason = ticket.is_actionable()
                        if not actionable:
                            self._log_identity_error(trade, {"reason": reason})
                        else:
                            send_trade_ticket(ticket)
                    except Exception:
                        pass

                # Phase F: Check and retrain model if needed
                self.retrainer.update_model("data/trade_log.json")

                # Evaluate blocked paper trades
                try:
                    self.blocked_tracker.update(self.predictor)
                except Exception:
                    pass

            except Exception as e:
                cycle_reason = f"cycle_exception:{type(e).__name__}"
                print(f"[Orchestrator ERROR] {e}")
                tripped, cb_reason = self.circuit_breaker.record_error("CYCLE_EXCEPTION")
                if tripped:
                    cycle_reason = cb_reason or "CB_ERROR_STORM"
                    try:
                        audit_append(
                            {
                                "event": "CIRCUIT_BREAKER_TRIP",
                                "reason": cycle_reason,
                                "detail": str(e),
                                "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                            }
                        )
                    except Exception as exc:
                        print(f"[CircuitBreaker] audit_error:{type(exc).__name__}")
                    try:
                        create_incident(
                            "SEV1",
                            cycle_reason,
                            {"detail": str(e), "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")},
                        )
                    except Exception as exc:
                        print(f"[CircuitBreaker] incident_error:{type(exc).__name__}")
            finally:
                try:
                    config_snapshot = decision_config_snapshot()
                    config_snapshot.update(self._runtime_safety_snapshot())
                    self._write_cycle_reports(
                        cycle_reason=cycle_reason,
                        decision_traces=list(self._decision_traces),
                        config_snapshot=config_snapshot,
                    )
                except Exception as report_exc:
                    print(f"[Orchestrator REPORT ERROR] {report_exc}")
                if run_once:
                    break
                time.sleep(self.poll_interval)

    def _sync_trades(self):
        if not cfg.KITE_TRADES_SYNC or not kite_client.kite:
            return
        if time.time() - self.last_trade_sync < 10:
            return
        self.last_trade_sync = time.time()
        try:
            trades = kite_client.trades()
        except Exception:
            return

        for tr in trades:
            symbol = tr.get("tradingsymbol")
            token = tr.get("instrument_token")
            price = tr.get("average_price")
            ts = tr.get("exchange_timestamp")
            if not symbol or price is None:
                continue

            # Match by instrument_token when available, fallback to symbol
            for key, open_list in self.open_trades.items():
                for ot in open_list:
                    if ot.instrument_token and token and ot.instrument_token == token:
                        match = True
                    else:
                        match = ot.symbol in symbol
                    if match:
                        meta = self.trade_meta.get(ot.trade_id, {})
                        if meta.get("fill_price"):
                            continue
                        latency_ms = None
                        if ts:
                            latency_ms = int((time.time() - ts.timestamp()) * 1000)
                        slippage = price - ot.entry_price
                        meta["fill_price"] = price
                        meta["latency_ms"] = latency_ms
                        meta["slippage"] = slippage
                        self.trade_meta[ot.trade_id] = meta
                        update_trade_fill(ot.trade_id, price, latency_ms=latency_ms, slippage=slippage)
                        self.execution_engine.calibrate_slippage(slippage, instrument=ot.instrument)
                        try:
                            insert_execution_stat({
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "instrument": ot.instrument,
                                "slippage_bps": self.execution_engine.slippage_bps,
                                "latency_ms": latency_ms,
                                "fill_ratio": 1.0
                            })
                        except Exception:
                            pass

    def _load_symbol_eps(self):
        import json
        from pathlib import Path
        path = Path("logs/symbol_eps.json")
        if path.exists():
            try:
                self.symbol_epsilon = json.loads(path.read_text())
            except Exception:
                self.symbol_epsilon = {}

    def _save_symbol_eps(self):
        import json
        from pathlib import Path
        path = Path("logs/symbol_eps.json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(self.symbol_epsilon))

        # append history
        hist_path = Path("logs/symbol_eps_history.json")
        self.eps_history.append({"ts": time.time(), "eps": self.symbol_epsilon})
        try:
            hist_path.write_text(json.dumps(self.eps_history[-500:]))
        except Exception:
            pass

    def _load_suggestion_eval(self):
        from pathlib import Path
        self.suggestion_eval_path = Path("logs/suggestion_eval.jsonl")
        self.suggestion_evaluated = set()
        if self.suggestion_eval_path.exists():
            try:
                with open(self.suggestion_eval_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            tid = obj.get("trade_id")
                            if tid:
                                self.suggestion_evaluated.add(tid)
                        except Exception:
                            continue
            except Exception:
                pass

    def _evaluate_suggestions(self, market_data_list):
        """
        Evaluate suggested trades vs live option prices to see if targets/stops are hit.
        """
        from pathlib import Path
        import re
        sug_path = Path("logs/suggestions.jsonl")
        if not sug_path.exists():
            return
        try:
            suggestions = []
            with open(sug_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        suggestions.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            return
        if not suggestions:
            return
        # Build map for quick lookup
        md_map = {m.get("symbol"): m for m in market_data_list if m.get("instrument") == "OPT"}
        tracker = StrategyTracker()
        tracker.load("logs/suggestion_strategy_perf.json")
        for s in suggestions:
            tid = s.get("trade_id")
            if not tid or tid in self.suggestion_evaluated:
                continue
            sym = s.get("symbol")
            md = md_map.get(sym)
            if not md:
                continue
            chain = md.get("option_chain", [])
            if not chain:
                continue
            # infer option type from trade_id
            opt_type = None
            m = re.search(r"-(CE|PE)(?:-|$)", tid)
            if m:
                opt_type = m.group(1)
            strike = s.get("strike")
            # find candidate option
            opt = None
            if strike in (None, "", 0, "ATM"):
                # pick closest strike of opt_type
                ltp = md.get("ltp", 0)
                if ltp:
                    step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {})
                    step = step_map.get(sym, getattr(cfg, "STRIKE_STEP", 50))
                    atm = int(round(ltp / step) * step) if step else 0
                    candidates = [o for o in chain if (opt_type is None or o.get("type") == opt_type)]
                    if candidates:
                        opt = min(candidates, key=lambda o: abs(o.get("strike", 0) - atm))
            else:
                candidates = [o for o in chain if (opt_type is None or o.get("type") == opt_type) and o.get("strike") == strike]
                if candidates:
                    opt = candidates[0]
            if not opt:
                continue
            ltp_opt = opt.get("ltp")
            if ltp_opt is None:
                continue
            entry = s.get("entry")
            stop = s.get("stop")
            target = s.get("target")
            if entry is None or stop is None or target is None:
                continue
            outcome = None
            if ltp_opt >= target:
                outcome = "target"
            elif ltp_opt <= stop:
                outcome = "stop"
            if not outcome:
                continue
            # record evaluation
            payload = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trade_id": tid,
                "symbol": sym,
                "strike": strike,
                "opt_type": opt_type,
                "ltp": ltp_opt,
                "outcome": outcome,
                "strategy": s.get("strategy"),
            }
            try:
                self.suggestion_eval_path.parent.mkdir(exist_ok=True)
                with open(self.suggestion_eval_path, "a") as f:
                    f.write(json.dumps(payload) + "\n")
            except Exception:
                pass
            self.suggestion_evaluated.add(tid)
            # update strategy evaluator (hit target = +1, stop = -1)
            pnl = 1 if outcome == "target" else -1
            tracker.record(s.get("strategy"), pnl)
            tracker.save("logs/suggestion_strategy_perf.json")

    def _start_depth_ws(self):
        if not cfg.KITE_USE_DEPTH:
            return
        kite_client.ensure()
        ws_client = kite_client.kite
        if not ws_client:
            detail = getattr(kite_client, "last_init_error", None) or "kite_not_initialized"
            raise RuntimeError(f"kite_depth_ws_init_failed:{detail}")
        from core.auth_health import get_kite_auth_health
        auth_payload = get_kite_auth_health(force=True)
        if not auth_payload.get("ok"):
            raise RuntimeError(
                f"kite_depth_ws_profile_failed:{auth_payload.get('error')} | "
                "Check: (1) cfg/env api_key present (2) token not expired (3) token generated using same api_key."
            )
        user_id = str((auth_payload or {}).get("user_id", "") or "")
        print(f"[KITE_WS] profile verified user_last4={user_id[-4:] if user_id else 'NONE'}")
        # Resolve a minimal depth subscription universe (index + ATM window).
        from core.kite_depth_ws import build_depth_subscription_tokens
        tokens, _resolution = build_depth_subscription_tokens(list(cfg.SYMBOLS))
        if not tokens:
            fallback = []
            for sym in cfg.SYMBOLS:
                tok = kite_client.resolve_index_token(sym)
                if tok:
                    fallback.append(tok)
            tokens = list(dict.fromkeys(fallback))
            if tokens:
                print(f"[KITE_WS] fallback index tokens={len(tokens)}")
        if not tokens:
            raise RuntimeError("kite_depth_ws_init_failed:no_tokens_resolved")
        start_depth_ws(tokens, profile_verified=True)

    def _track_open_trade(self, trade, market_data):
        key = f"{trade.symbol}:{trade.instrument}"
        if key not in self.open_trades:
            self.open_trades[key] = []
        self.open_trades[key].append(trade)
        trail_init = float(getattr(trade, "stop_loss", 0.0) or 0.0)
        meta = {
            "entry_time": time.time(),
            "trail_stop": trail_init,
            "instrument_token": trade.instrument_token,
            "entry_price": trade.entry_price,
            "mfe": 0.0,
            "mae": 0.0,
            "pnl_5m": None,
            "pnl_15m": None,
            "mfe_15m": None,
            "mae_15m": None,
            "trail_stop_init": trail_init,
            "trail_updates": 0,
            "trailing_enabled": True,
            "trailing_method": "ATR",
            "trailing_atr_mult": float(getattr(cfg, "TRAILING_STOP_ATR_MULT", 0.8)),
            "partial_enabled": bool(getattr(cfg, "PARTIAL_PROFIT_ENABLED", True)),
            "tp1_done": False,
            "remaining_qty_units": int(getattr(trade, "qty_units", 0) or 0),
            "realized_pnl_legs": 0.0,
            "legs_count": 0,
            "weighted_exit_sum": 0.0,
        }
        if trade.strategy == "SCALP":
            meta["max_hold_sec"] = getattr(cfg, "SCALP_MAX_HOLD_MINUTES", 12) * 60
        if meta["remaining_qty_units"] <= 0:
            lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1))
            meta["remaining_qty_units"] = int(getattr(trade, "qty", 0) or 0) * (lot_size if trade.instrument == "OPT" else 1)
        self.trade_meta[trade.trade_id] = meta
        try:
            update_trailing_state(
                trade.trade_id,
                trailing_enabled=True,
                trailing_method=str(meta.get("trailing_method", "ATR")),
                trailing_atr_mult=float(meta.get("trailing_atr_mult", 0.8)),
                trail_stop_init=trail_init,
                trail_stop_last=trail_init,
                trail_updates=0,
            )
        except Exception:
            pass

    def _check_open_trades(self, market_data):
        sym = market_data.get("symbol")
        instrument = market_data.get("instrument", "OPT")
        key = f"{sym}:{instrument}"
        if key not in self.open_trades:
            return

        remaining = []
        for tr in self.open_trades[key]:
            meta = self.trade_meta.get(tr.trade_id, {"trail_stop": tr.stop_loss, "entry_time": time.time()})
            if instrument == "OPT":
                current_price = None
                for opt in market_data.get("option_chain", []):
                    if tr.instrument_token and opt.get("instrument_token") == tr.instrument_token:
                        current_price = opt.get("ltp")
                        break
                    if opt.get("strike") == tr.strike and opt.get("type") in ("CE", "PE"):
                        current_price = opt.get("ltp")
                        break
                if current_price is None:
                    remaining.append(tr)
                    continue
            else:
                current_price = market_data.get("ltp")
                if current_price is None:
                    remaining.append(tr)
                    continue

            # Trailing stop update (for BUY)
            if tr.side == "BUY":
                trail_dist = market_data.get("atr", 0) * getattr(cfg, "TRAILING_STOP_ATR_MULT", 0.8)
                prev_trail = float(meta.get("trail_stop", tr.stop_loss))
                new_trail = max(prev_trail, current_price - trail_dist)
                meta["trail_stop"] = new_trail
                if new_trail > prev_trail:
                    meta["trail_updates"] = int(meta.get("trail_updates", 0)) + 1
                    try:
                        insert_trail_event(tr.trade_id, float(new_trail), float(current_price), "TRAIL_UPDATE")
                    except Exception:
                        pass
                    try:
                        update_trailing_state(
                            tr.trade_id,
                            trailing_enabled=bool(meta.get("trailing_enabled", True)),
                            trailing_method=str(meta.get("trailing_method", "ATR")),
                            trailing_atr_mult=float(meta.get("trailing_atr_mult", getattr(cfg, "TRAILING_STOP_ATR_MULT", 0.8))),
                            trail_stop_init=float(meta.get("trail_stop_init", tr.stop_loss)),
                            trail_stop_last=float(new_trail),
                            trail_updates=int(meta.get("trail_updates", 0)),
                        )
                    except Exception:
                        pass
                self.trade_meta[tr.trade_id] = meta
            # Store last price for unrealized PnL computation
            meta["last_price"] = current_price
            lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(tr.symbol, 1))
            qty_total_units = int(meta.get("remaining_qty_units", 0) or 0)
            if qty_total_units <= 0:
                qty_total_units = int(getattr(tr, "qty_units", 0) or 0)
            if qty_total_units <= 0:
                qty_total_units = int(getattr(tr, "qty", 0) or 0) * (lot_size if tr.instrument == "OPT" else 1)
            # Track MFE/MAE and horizon PnL snapshots
            try:
                entry_px = meta.get("entry_price", tr.entry_price)
                pnl_now = (current_price - entry_px) if tr.side == "BUY" else (entry_px - current_price)
                meta["mfe"] = max(meta.get("mfe", 0.0), pnl_now)
                meta["mae"] = min(meta.get("mae", 0.0), pnl_now)
                elapsed = time.time() - meta.get("entry_time", time.time())
                if elapsed >= 300 and meta.get("pnl_5m") is None:
                    meta["pnl_5m"] = pnl_now
                if elapsed >= 900 and meta.get("pnl_15m") is None:
                    meta["pnl_15m"] = pnl_now
                    meta["mfe_15m"] = meta.get("mfe")
                    meta["mae_15m"] = meta.get("mae")
            except Exception:
                pass
            self.trade_meta[tr.trade_id] = meta

            # Partial-profit leg at TP1 before final exit.
            try:
                if bool(meta.get("partial_enabled", False)) and not bool(meta.get("tp1_done", False)):
                    risk_abs = abs(float(meta.get("entry_price", tr.entry_price)) - float(tr.stop_loss))
                    tp1_mult = float(getattr(cfg, "TP1_R_MULT", 0.7))
                    tp1_px = float(meta.get("entry_price", tr.entry_price)) + (risk_abs * tp1_mult if tr.side == "BUY" else -risk_abs * tp1_mult)
                    hit_tp1 = (current_price >= tp1_px) if tr.side == "BUY" else (current_price <= tp1_px)
                    if hit_tp1 and qty_total_units > 1:
                        frac = float(getattr(cfg, "TP1_FRACTION", 0.5))
                        leg_qty = int(max(1, round(qty_total_units * frac)))
                        leg_qty = min(leg_qty, qty_total_units - 1)
                        leg_pnl = (
                            (current_price - float(meta.get("entry_price", tr.entry_price))) * leg_qty
                            if tr.side == "BUY"
                            else (float(meta.get("entry_price", tr.entry_price)) - current_price) * leg_qty
                        )
                        meta["tp1_done"] = True
                        meta["remaining_qty_units"] = qty_total_units - leg_qty
                        meta["realized_pnl_legs"] = float(meta.get("realized_pnl_legs", 0.0)) + float(leg_pnl)
                        meta["legs_count"] = int(meta.get("legs_count", 0)) + 1
                        meta["weighted_exit_sum"] = float(meta.get("weighted_exit_sum", 0.0)) + (float(current_price) * leg_qty)
                        if bool(getattr(cfg, "MOVE_SL_TO_BE", True)):
                            meta["trail_stop"] = float(meta.get("entry_price", tr.entry_price))
                        try:
                            insert_trade_leg(tr.trade_id, int(meta["legs_count"]), int(leg_qty), float(current_price), "TP1")
                        except Exception:
                            pass
                        self.trade_meta[tr.trade_id] = meta
            except Exception:
                pass

            # Time exit
            max_hold = meta.get("max_hold_sec") or (getattr(cfg, "MAX_HOLD_MINUTES", 60) * 60)
            time_exit = False
            target_level = tr.target
            if time.time() - meta.get("entry_time", time.time()) >= max_hold:
                hit_target = False
                hit_stop = True
                time_exit = True
            else:
                if bool(meta.get("tp1_done", False)):
                    risk_abs = abs(float(meta.get("entry_price", tr.entry_price)) - float(tr.stop_loss))
                    tp2_mult = float(getattr(cfg, "TP2_R_MULT", 1.5))
                    target_level = float(meta.get("entry_price", tr.entry_price)) + (risk_abs * tp2_mult if tr.side == "BUY" else -risk_abs * tp2_mult)
                hit_target = current_price >= target_level if tr.side == "BUY" else current_price <= target_level
                stop_level = meta.get("trail_stop", tr.stop_loss)
                hit_stop = current_price <= stop_level if tr.side == "BUY" else current_price >= stop_level
            if not (hit_target or hit_stop):
                remaining.append(tr)
                continue

            stop_level = meta.get("trail_stop", tr.stop_loss)
            exit_price = target_level if hit_target else stop_level
            actual = 1 if hit_target else 0
            if hit_target:
                exit_reason = "TARGET"
            elif time_exit:
                exit_reason = "TIME"
            elif tr.side == "BUY" and stop_level > tr.stop_loss:
                exit_reason = "TRAIL_STOP"
            elif tr.side == "SELL" and stop_level < tr.stop_loss:
                exit_reason = "TRAIL_STOP"
            else:
                exit_reason = "STOP"

            remaining_units = int(meta.get("remaining_qty_units", 0) or 0)
            if remaining_units <= 0:
                remaining_units = qty_total_units
            final_leg_pnl = (
                (float(exit_price) - float(meta.get("entry_price", tr.entry_price))) * remaining_units
                if tr.side == "BUY"
                else (float(meta.get("entry_price", tr.entry_price)) - float(exit_price)) * remaining_units
            )
            total_realized_pnl = float(meta.get("realized_pnl_legs", 0.0)) + float(final_leg_pnl)
            total_units = max(1, int(getattr(tr, "qty_units", 0) or qty_total_units))
            total_risk = abs(float(meta.get("entry_price", tr.entry_price)) - float(tr.stop_loss)) * total_units
            r_multiple_realized = (total_realized_pnl / total_risk) if total_risk > 0 else 0.0
            outcome_label = "WIN" if total_realized_pnl > float(getattr(cfg, "OUTCOME_PNL_EPSILON", 1e-6)) else ("LOSS" if total_realized_pnl < -float(getattr(cfg, "OUTCOME_PNL_EPSILON", 1e-6)) else "BREAKEVEN")
            if r_multiple_realized >= 1.5:
                outcome_grade = "A"
            elif r_multiple_realized >= 1.0:
                outcome_grade = "B"
            elif r_multiple_realized >= 0.0:
                outcome_grade = "C"
            else:
                outcome_grade = "D"
            leg_count_final = int(meta.get("legs_count", 0)) + 1
            weighted_exit_sum = float(meta.get("weighted_exit_sum", 0.0)) + (float(exit_price) * remaining_units)
            avg_exit = weighted_exit_sum / max(1, total_units)
            try:
                insert_trade_leg(tr.trade_id, leg_count_final, remaining_units, float(exit_price), exit_reason)
            except Exception:
                pass

            # Update trade log
            updated = update_trade_outcome(
                tr.trade_id,
                exit_price,
                actual,
                exit_reason=exit_reason,
                realized_pnl_override=total_realized_pnl,
                r_multiple_realized_override=r_multiple_realized,
                outcome_label_override=outcome_label,
                outcome_grade_override=outcome_grade,
                legs_count=leg_count_final,
                avg_exit=avg_exit,
                exit_reason_final=exit_reason,
            )
            try:
                update_outcome(tr.trade_id, {
                    "pnl_horizon_5m": meta.get("pnl_5m"),
                    "pnl_horizon_15m": meta.get("pnl_15m"),
                    "mae_15m": meta.get("mae_15m"),
                    "mfe_15m": meta.get("mfe_15m"),
                })
            except Exception:
                pass

            # Update strategy performance
            pnl = total_realized_pnl
            # Update portfolio stats
            self.portfolio["capital"] += pnl
            self.portfolio["daily_loss"] += pnl
            if self.portfolio["capital"] > self.portfolio.get("equity_high", self.portfolio["capital"]):
                self.portfolio["equity_high"] = self.portfolio["capital"]
            dd = (self.portfolio["capital"] - self.portfolio["equity_high"]) / max(1.0, self.portfolio["equity_high"])
            if dd <= getattr(cfg, "MAX_DRAWDOWN_PCT", getattr(cfg, "PORTFOLIO_MAX_DRAWDOWN", -0.2)):
                risk_halt.set_halt("Max drawdown breach", {"drawdown": dd})
                send_telegram_message(f"Auto-halt: drawdown breach {dd:.2%}")
            # Skip aux trades in PAPER_STRICT_MODE from main perf stats
            if not (str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "PAPER"
                    and getattr(cfg, "PAPER_STRICT_MODE", False)
                    and (getattr(tr, "tier", "MAIN") != "MAIN" or tr.strategy in ("SCALP", "ZERO_HERO", "ZERO_HERO_EXPIRY") or tr.strategy.startswith("QUICK"))):
                self.strategy_tracker.record(tr.strategy, pnl)
                self.strategy_tracker.record_symbol(tr.symbol, pnl)
                self.strategy_tracker.save("logs/strategy_perf.json")
            # Expiry zero-hero: auto-disable after loss streak with cooldown
            try:
                if tr.strategy == "ZERO_HERO_EXPIRY":
                    streak = self.trade_builder._expiry_zero_hero_loss_streak.get(tr.symbol, 0)
                    if pnl <= 0:
                        streak += 1
                    else:
                        streak = 0
                    self.trade_builder._expiry_zero_hero_loss_streak[tr.symbol] = streak
                    max_streak = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK", 2)
                    if tr.symbol == "NIFTY":
                        max_streak = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_NIFTY", max_streak)
                    if tr.symbol == "SENSEX":
                        max_streak = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_SENSEX", max_streak)
                    # Drawdown disable (net pnl)
                    pnl_sum = self.trade_builder._expiry_zero_hero_pnl.get(tr.symbol, 0.0) + pnl
                    self.trade_builder._expiry_zero_hero_pnl[tr.symbol] = pnl_sum
                    dd_limit = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_DRAWDOWN", -0.5)
                    hit_drawdown = pnl_sum <= dd_limit
                    if streak >= max_streak or hit_drawdown:
                        cooldown = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_COOLDOWN_MIN", 45) * 60
                        self.trade_builder._expiry_zero_hero_disabled_until[tr.symbol] = time.time() + cooldown
            except Exception:
                pass
            # update loss streak
            if pnl <= 0:
                self.loss_streak[tr.symbol] = self.loss_streak.get(tr.symbol, 0) + 1
            else:
                self.loss_streak[tr.symbol] = 0
            if pnl > 0:
                self.portfolio["daily_profit"] += pnl
                try:
                    self.portfolio["symbol_profit"][tr.symbol] = self.portfolio["symbol_profit"].get(tr.symbol, 0.0) + pnl
                except Exception:
                    pass
            try:
                self.risk_state.record_realized_pnl(tr.strategy, pnl)
            except Exception:
                pass

        self.open_trades[key] = remaining
        # Update unrealized PnL across all open trades using last known prices
        try:
            total_unrealized = 0.0
            for _, open_list in self.open_trades.items():
                for ot in open_list:
                    meta = self.trade_meta.get(ot.trade_id, {})
                    last_price = meta.get("last_price")
                    if last_price is None:
                        continue
                    lot_size = getattr(cfg, "LOT_SIZE", {}).get(ot.symbol, 1)
                    qty = ot.qty * (lot_size if ot.instrument == "OPT" else 1)
                    if ot.side == "BUY":
                        total_unrealized += (last_price - ot.entry_price) * qty
                    else:
                        total_unrealized += (ot.entry_price - last_price) * qty
            self.risk_state.update_unrealized(total_unrealized)
        except Exception:
            pass

    def backtest(self, historical_file: str, window_size: int = 50):
        """
        Phase D: Walk-forward backtest integration
        """
        print(f"[Orchestrator] Running backtest on {historical_file}")
        historical = pd.read_csv(historical_file)

        # Use TradeBuilder + Phase B + Phase C logic for each window
        results = []
        for start in range(0, len(historical), window_size):
            end = start + window_size
            window_data = historical.iloc[start:end]
            for _, row in window_data.iterrows():
                market_data = row.to_dict()
                trade = self.trade_builder.build(market_data)
                allowed, _ = self.risk_engine.allow_trade(self.portfolio, trade=trade)
                if allowed:
                    results.append({
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "entry": trade.entry_price,
                        "target": getattr(trade, "target", 0),
                        "pl": getattr(trade, "pl", 0),
                        "confidence": getattr(trade, "confidence", 0),
                        "regime": getattr(trade, "regime", "N/A"),
                        "capital": self.portfolio["capital"]
                    })
        df_results = pd.DataFrame(results)
        df_results.to_csv("logs/backtest_results.csv", index=False)
        print("[Orchestrator] Backtest complete, results saved.")
        return df_results


def _main():
    parser = argparse.ArgumentParser(description="Run orchestrator")
    parser.add_argument("--run-once", action="store_true", help="Run a single live-monitoring cycle and exit")
    parser.add_argument("--poll-interval", type=int, default=30, help="Polling interval in seconds")
    parser.add_argument("--capital", type=float, default=100000.0, help="Starting capital")
    args = parser.parse_args()
    if args.run_once:
        setattr(cfg, "KITE_USE_DEPTH", False)
    orch = Orchestrator(
        total_capital=args.capital,
        poll_interval=args.poll_interval,
        start_depth_ws_enabled=not args.run_once,
    )
    orch.live_monitoring(run_once=args.run_once)


if __name__ == "__main__":
    _main()
