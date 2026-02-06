import time
import json
import pandas as pd
from dataclasses import replace
from strategies.trade_builder import TradeBuilder
from core.market_data import fetch_live_market_data
from core.risk_engine import RiskEngine
from core.execution_guard import ExecutionGuard
from core.trade_logger import log_trade, update_trade_outcome, update_trade_fill
from core.telegram_alerts import send_telegram_message
from core.auto_retrain import AutoRetrain
from ml.trade_predictor import TradePredictor
from core.execution_engine import ExecutionEngine
from core.execution_router import ExecutionRouter
from config import config as cfg
from core.strategy_tracker import StrategyTracker
from core.kite_client import kite_client
from core.strategy_allocator import StrategyAllocator
from core.review_queue import add_to_queue, is_approved, QUICK_QUEUE_PATH, ZERO_HERO_QUEUE_PATH, SCALP_QUEUE_PATH
from core.blocked_tracker import BlockedTradeTracker
from core.trade_store import insert_execution_stat
from core.depth_store import depth_store
from core.kite_depth_ws import start_depth_ws
from core.auto_tune import maybe_auto_tune
from core import risk_halt

class Orchestrator:
    def __init__(self, total_capital=100000, poll_interval=30):
        """
        Main orchestrator initializing all components
        """
        self.total_capital = total_capital
        self.poll_interval = poll_interval

        # Phase C: Trade generation
        self.predictor = TradePredictor()
        self.execution_engine = ExecutionEngine()
        self.execution_router = ExecutionRouter()
        self.trade_builder = TradeBuilder(self.predictor, self.execution_engine)

        # Phase B: Risk and execution
        self.risk_engine = RiskEngine()
        self.execution_guard = ExecutionGuard()

        # Phase F: Auto-retraining
        self.retrainer = AutoRetrain(self.predictor)
        self.strategy_tracker = StrategyTracker()
        self.strategy_tracker.load("logs/strategy_perf.json")
        self.strategy_allocator = StrategyAllocator(self.strategy_tracker)
        self.open_trades = {}
        self.trade_meta = {}
        self.last_trade_sync = 0
        self.blocked_tracker = BlockedTradeTracker()
        self.best_trade_logged = False
        self.best_trade_by_regime = {}

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
        self._start_depth_ws()
        self.eps_history = []
        self._load_suggestion_eval()

    def live_monitoring(self):
        """
        Phase E: Live trading loop
        Fetch market data, generate trades, risk-check, execute, log, alert
        """
        print("[Orchestrator] Starting live monitoring...")
        while True:
            try:
                # Hot-reload config to pick up FORCE_REGIME changes
                try:
                    import importlib
                    from config import config as cfg
                    importlib.reload(cfg)
                except Exception:
                    pass
                if risk_halt.is_halted():
                    time.sleep(self.poll_interval)
                    continue
                market_data_list = fetch_live_market_data()  # List of dicts for multiple symbols
                self._evaluate_suggestions(market_data_list)
                try:
                    maybe_auto_tune()
                except Exception:
                    pass

                # Reset daily flags at new day
                try:
                    today = datetime.now().date()
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

                for market_data in market_data_list:
                    self._sync_trades()
                    sym = market_data.get("symbol")
                    # Check exits for any open trades on this symbol/instrument
                    self._check_open_trades(market_data)
                    cooldown = getattr(cfg, "MIN_COOLDOWN_SEC", 300)
                    last_t = self.last_trade_time.get(sym)
                    if last_t and time.time() - last_t < cooldown:
                        continue
                    # Phase C: Build trade suggestion
                    debug_flag = getattr(cfg, "DEBUG_TRADE_REASONS", False) or getattr(cfg, "DEBUG_TRADE_MODE", False)
                    trade = self.trade_builder.build(
                        market_data,
                        quick_mode=False,
                        debug_reasons=debug_flag
                    )
                    # Spread suggestions (advisory only)
                    try:
                        spreads = self.trade_builder.build_spread_suggestions(market_data)
                        for sp in spreads:
                            add_to_queue(type("Obj", (), sp))
                    except Exception:
                        pass
                    if not trade:
                        # Track blocked candidates for paper outcome evaluation
                        try:
                            self.blocked_tracker.capture_from_log()
                        except Exception:
                            pass
                        # Emit quick suggestion even if strong trade is blocked
                        try:
                            quick_trade = self.trade_builder.build(
                                market_data,
                                quick_mode=True,
                                debug_reasons=debug_flag
                            )
                            if quick_trade:
                                add_to_queue(quick_trade, queue_path=QUICK_QUEUE_PATH, extra={"tier": "EXPLORATION"})
                            zero_trade = self.trade_builder.build_zero_hero(
                                market_data,
                                debug_reasons=debug_flag
                            )
                            if zero_trade:
                                add_to_queue(zero_trade, queue_path=ZERO_HERO_QUEUE_PATH, extra={"category": "zero_hero", "tier": "EXPLORATION"})
                            scalp_trade = self.trade_builder.build_scalp(
                                market_data,
                                debug_reasons=debug_flag
                            )
                            if scalp_trade:
                                add_to_queue(scalp_trade, queue_path=SCALP_QUEUE_PATH, extra={"category": "scalp", "tier": "EXPLORATION"})
                        except Exception:
                            pass
                        continue
                    if self.strategy_tracker.is_disabled(
                        trade.strategy,
                        min_trades=getattr(cfg, "STRATEGY_MIN_TRADES", 30),
                        threshold=getattr(cfg, "STRATEGY_DISABLE_THRESHOLD", 0.45)
                    ):
                        print(f"[StrategyTracker] Disabled strategy: {trade.strategy}")
                        continue
                    # Best trade per day filter
                    if getattr(cfg, "BEST_TRADE_PER_DAY", True) and self.best_trade_logged:
                        continue
                    # Best trade per regime filter
                    if getattr(cfg, "BEST_TRADE_PER_REGIME", True):
                        rkey = trade.regime or "NEUTRAL"
                        if self.best_trade_by_regime.get(rkey):
                            continue
                    # Adjust epsilon by regime (lower in choppy regimes)
                    base_eps = self.symbol_epsilon.get(sym, cfg.STRATEGY_EPSILON)
                    regime = market_data.get("regime")
                    if regime == "CHOPPY":
                        cfg.STRATEGY_EPSILON = max(0.02, base_eps * 0.5)
                    elif regime == "TREND":
                        cfg.STRATEGY_EPSILON = min(0.2, base_eps * 1.2)
                    if not self.strategy_allocator.should_trade(trade.strategy):
                        continue
                    self.symbol_epsilon[sym] = cfg.STRATEGY_EPSILON
                    self._save_symbol_eps()
                    cfg.STRATEGY_EPSILON = base_eps

                    # Manual approval gate (strong trades)
                    if cfg.MANUAL_APPROVAL and not is_approved(trade.trade_id):
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
                        }
                        add_to_queue(trade, extra=dict(validation, **{"tier": "MAIN"}))
                        print(f"[ReviewQueue] Trade queued: {trade.trade_id}")
                        # also emit a quick suggestion preview (non-executable)
                        try:
                            quick_trade = self.trade_builder.build(
                                market_data,
                                quick_mode=True,
                                debug_reasons=debug_flag
                            )
                            if quick_trade:
                                add_to_queue(quick_trade, queue_path=QUICK_QUEUE_PATH, extra=validation)
                        except Exception:
                            pass
                        continue

                    # Phase B: Risk validation
                    allowed, reason = self.risk_engine.allow_trade(self.portfolio)
                    if not allowed:
                        print(f"[RiskEngine] Trade blocked: {reason}")
                        if reason.lower().startswith("daily loss"):
                            risk_halt.set_halt("Daily loss limit hit")
                            send_telegram_message("Auto-halt: daily loss limit hit.")
                        continue

                    # Phase B: Execution guard
                    approved, reason = self.execution_guard.validate(trade, self.portfolio, trade.regime)
                    if not approved:
                        print(f"[ExecutionGuard] Trade blocked: {reason}")
                        continue

                    # Risk-based sizing
                    lot_size = getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1)
                    current_vol = (market_data.get("atr", 0) / market_data.get("ltp", 1)) if market_data.get("ltp") else None
                    streak = self.loss_streak.get(trade.symbol, 0)
                    sized_qty = self.risk_engine.size_trade(trade, self.portfolio["capital"], lot_size, current_vol=current_vol, loss_streak=streak)
                    trade = replace(trade, qty=sized_qty, capital_at_risk=round((trade.entry_price - trade.stop_loss) * sized_qty * lot_size, 2))

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
                    bid = market_data.get("bid", trade.entry_price * 0.999)
                    ask = market_data.get("ask", trade.entry_price * 1.001)
                    volume = market_data.get("volume", 0)
                    depth = None
                    if trade.instrument_token:
                        d = depth_store.get(trade.instrument_token)
                        depth = d.get("depth") if d else None
                    filled, fill_price = self.execution_router.execute(trade, bid, ask, volume, depth=depth)
                    if not filled:
                        print("[ExecutionEngine] Limit order not filled.")
                        continue
                    trade = replace(trade, entry_price=fill_price)

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
                    log_trade(trade, extra=extra)
                    self._track_open_trade(trade, market_data)

                    # Telegram alert
                    send_telegram_message(
                        f"Trade executed: {trade.symbol} | {trade.side} | "
                        f"LTP: {trade.entry_price} | Confidence: {getattr(trade, 'confidence', 0):.2f} | "
                        f"Regime: {getattr(trade, 'regime', 'N/A')}"
                    )

                # Phase F: Check and retrain model if needed
                self.retrainer.update_model("data/trade_log.csv")

                # Evaluate blocked paper trades
                try:
                    self.blocked_tracker.update(self.predictor)
                except Exception:
                    pass

            except Exception as e:
                print(f"[Orchestrator ERROR] {e}")

            # Wait before next polling
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
        try:
            if not cfg.KITE_USE_DEPTH:
                return
            # Resolve tokens from option chain instruments (preferred)
            tokens = []
            md_list = fetch_live_market_data()
            for md in md_list:
                for opt in md.get("option_chain", []):
                    if opt.get("instrument_token"):
                        tokens.append(opt.get("instrument_token"))
            tokens = list(set(tokens))
            if not tokens:
                tokens = kite_client.resolve_tokens(cfg.SYMBOLS, exchange="NFO")
            if not tokens:
                return
            start_depth_ws(tokens)
        except Exception:
            pass

    def _track_open_trade(self, trade, market_data):
        key = f"{trade.symbol}:{trade.instrument}"
        if key not in self.open_trades:
            self.open_trades[key] = []
        self.open_trades[key].append(trade)
        meta = {
            "entry_time": time.time(),
            "trail_stop": trade.stop_loss,
            "instrument_token": trade.instrument_token
        }
        if trade.strategy == "SCALP":
            meta["max_hold_sec"] = getattr(cfg, "SCALP_MAX_HOLD_MINUTES", 12) * 60
        self.trade_meta[trade.trade_id] = meta

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
                new_trail = max(meta.get("trail_stop", tr.stop_loss), current_price - trail_dist)
                meta["trail_stop"] = new_trail
                self.trade_meta[tr.trade_id] = meta

            # Time exit
            max_hold = meta.get("max_hold_sec") or (getattr(cfg, "MAX_HOLD_MINUTES", 60) * 60)
            if time.time() - meta.get("entry_time", time.time()) >= max_hold:
                hit_target = False
                hit_stop = True
            else:
                hit_target = current_price >= tr.target if tr.side == "BUY" else current_price <= tr.target
                stop_level = meta.get("trail_stop", tr.stop_loss)
                hit_stop = current_price <= stop_level if tr.side == "BUY" else current_price >= stop_level
            if not (hit_target or hit_stop):
                remaining.append(tr)
                continue

            stop_level = meta.get("trail_stop", tr.stop_loss)
            exit_price = tr.target if hit_target else stop_level
            actual = 1 if hit_target else 0

            # Update trade log
            updated = update_trade_outcome(tr.trade_id, exit_price, actual)

            # Update strategy performance
            lot_size = getattr(cfg, "LOT_SIZE", {}).get(tr.symbol, 1)
            qty = tr.qty * (lot_size if tr.instrument == "OPT" else 1)
            pnl = (exit_price - tr.entry_price) * qty if tr.side == "BUY" else (tr.entry_price - exit_price) * qty
            # Update portfolio stats
            self.portfolio["capital"] += pnl
            self.portfolio["daily_loss"] += pnl
            if self.portfolio["capital"] > self.portfolio.get("equity_high", self.portfolio["capital"]):
                self.portfolio["equity_high"] = self.portfolio["capital"]
            dd = (self.portfolio["capital"] - self.portfolio["equity_high"]) / max(1.0, self.portfolio["equity_high"])
            if dd <= getattr(cfg, "PORTFOLIO_MAX_DRAWDOWN", -0.2):
                risk_halt.set_halt("Max drawdown breach", {"drawdown": dd})
                send_telegram_message(f"Auto-halt: drawdown breach {dd:.2%}")
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

        self.open_trades[key] = remaining

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
                allowed, _ = self.risk_engine.allow_trade(self.portfolio)
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
