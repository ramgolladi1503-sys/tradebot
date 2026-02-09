from __future__ import annotations

import csv
import json
import random
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from config import config as cfg
from core.indicators_live import compute_indicators
from core.option_chain import fetch_option_chain
from core.ohlc_buffer import ohlc_buffer
from core.regime_prob_model import RegimeProbModel
from core.strategy_gatekeeper import StrategyGatekeeper
from core.trade_scoring import compute_trade_score
from core.risk_engine import RiskEngine
from core.execution_guard import ExecutionGuard
from strategies.trade_builder import TradeBuilder


def _load_instruments_map(path: Path) -> Dict[int, dict]:
    if not path.exists():
        return {}
    out = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                token = int(row.get("instrument_token"))
            except Exception:
                continue
            out[token] = row
    return out


def _symbol_from_token(token: int, symbol_set: set, inst_map: Dict[int, dict]) -> Optional[str]:
    row = inst_map.get(token)
    if not row:
        return None
    name = (row.get("name") or "").upper()
    ts = (row.get("tradingsymbol") or "").upper()
    for sym in symbol_set:
        if name == sym:
            return sym
        if ts.startswith(sym):
            return sym
    return None


def _date_bounds(date_str: str) -> Tuple[float, float]:
    # Use Asia/Kolkata for trading-day boundaries
    try:
        tz = timezone(timedelta(hours=5, minutes=30))
        day = datetime.fromisoformat(date_str).date()
        start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz)
        end = start + timedelta(days=1)
        return start.timestamp(), end.timestamp()
    except Exception:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        return now.timestamp(), (now + timedelta(days=1)).timestamp()


class ReplayEngine:
    def __init__(self, db_path: Optional[Path] = None, seed: int = 1):
        self.db_path = Path(db_path) if db_path else Path(cfg.TRADE_DB_PATH)
        self.seed = seed
        self.trade_builder = TradeBuilder()
        self.gatekeeper = StrategyGatekeeper()
        self.risk_engine = RiskEngine()
        self.exec_guard = ExecutionGuard()
        self.regime_model = RegimeProbModel(getattr(cfg, "REGIME_MODEL_PATH", "models/regime_model.json"))
        self.portfolio = {
            "capital": float(getattr(cfg, "CAPITAL", 100000)),
            "daily_loss": 0.0,
            "daily_profit": 0.0,
            "trades_today": 0,
            "equity_high": float(getattr(cfg, "CAPITAL", 100000)),
        }

    def _load_ticks(self, start_epoch: float, end_epoch: float) -> List[Tuple[float, int, float, int]]:
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT timestamp_epoch, instrument_token, last_price, volume FROM ticks "
            "WHERE timestamp_epoch >= ? AND timestamp_epoch < ? ORDER BY timestamp_epoch ASC",
            (start_epoch, end_epoch),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def _load_depth(self, start_epoch: float, end_epoch: float) -> List[Tuple[float, int, str]]:
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT timestamp_epoch, instrument_token, depth_json FROM depth_snapshots "
            "WHERE timestamp_epoch >= ? AND timestamp_epoch < ? ORDER BY timestamp_epoch ASC",
            (start_epoch, end_epoch),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def replay_day(self, date_str: str, symbols: List[str], speed: float = 1.0) -> Path:
        random.seed(self.seed)
        symbol_set = {s.upper() for s in symbols}
        inst_map = _load_instruments_map(Path("data/kite_instruments.csv"))
        start_epoch, end_epoch = _date_bounds(date_str)
        ticks = self._load_ticks(start_epoch, end_epoch)
        depth = self._load_depth(start_epoch, end_epoch)

        # index depth by time
        depth_idx = 0
        latest_depth = {}
        out_path = Path(f"logs/decisions_replay_{date_str}.json")
        out_path.parent.mkdir(exist_ok=True)

        # temporarily disable cross-asset gating for replay
        prev_require = getattr(cfg, "REQUIRE_CROSS_ASSET", True)
        cfg.REQUIRE_CROSS_ASSET = False
        prev_mode = getattr(cfg, "EXECUTION_MODE", "SIM")
        cfg.EXECUTION_MODE = "SIM"

        trace_counter = 0
        with out_path.open("w") as f:
            for ts_epoch, token, price, volume in ticks:
                # update depth snapshots up to this time
                while depth_idx < len(depth) and depth[depth_idx][0] <= ts_epoch:
                    d_ts, d_token, d_json = depth[depth_idx]
                    latest_depth[d_token] = (d_ts, d_json)
                    depth_idx += 1
                sym = _symbol_from_token(int(token), symbol_set, inst_map)
                if not sym:
                    continue
                if price is None:
                    continue
                ohlc_buffer.update_tick(sym, price, volume or 0, ts=ts_epoch)
                bars = ohlc_buffer.get_bars(sym)
                indicators_ok = len(bars) >= getattr(cfg, "OHLC_MIN_BARS", 30)
                ind = compute_indicators(
                    bars,
                    vwap_window=getattr(cfg, "VWAP_WINDOW", 20),
                    atr_period=getattr(cfg, "ATR_PERIOD", 14),
                    adx_period=getattr(cfg, "ADX_PERIOD", 14),
                    vol_window=getattr(cfg, "VOL_WINDOW", 30),
                    slope_window=getattr(cfg, "VWAP_SLOPE_WINDOW", 10),
                ) if bars else {}

                vwap = ind.get("vwap") or price
                atr = ind.get("atr") or max(1.0, price * 0.002)
                adx = ind.get("adx") or 0.0
                vol_z = ind.get("vol_z") or 0.0
                vwap_slope = ind.get("vwap_slope") or 0.0

                depth_imb = None
                if token in latest_depth:
                    try:
                        depth_obj = json.loads(latest_depth[token][1])
                        depth_imb = depth_obj.get("imbalance")
                    except Exception:
                        depth_imb = None

                features = {
                    "adx": adx,
                    "vwap_slope": vwap_slope,
                    "vol_z": vol_z,
                    "atr_pct": (atr / price) if price else 0.0,
                    "iv_mean": 0.0,
                    "ltp_acceleration": 0.0,
                    "option_chain_skew": 0.0,
                    "oi_delta": 0.0,
                    "depth_imbalance": depth_imb or 0.0,
                    "regime_transition_rate": 0.0,
                    "shock_score": 0.0,
                    "uncertainty_index": 0.0,
                    "macro_direction_bias": 0.0,
                    "x_regime_align": 0.0,
                    "x_vol_spillover": 0.0,
                    "x_lead_lag": 0.0,
                }
                regime_out = self.regime_model.predict(features)

                market_data = {
                    "symbol": sym,
                    "ltp": price,
                    "vwap": vwap,
                    "atr": atr,
                    "vwap_slope": vwap_slope,
                    "vol_z": vol_z,
                    "adx_14": adx,
                    "depth_imbalance": depth_imb,
                    "indicators_ok": indicators_ok,
                    "indicators_age_sec": 0.0,
                    "regime_probs": regime_out.get("regime_probs"),
                    "primary_regime": regime_out.get("primary_regime"),
                    "regime_entropy": regime_out.get("regime_entropy"),
                    "unstable_regime_flag": regime_out.get("unstable_regime_flag"),
                    "shock_score": 0.0,
                    "uncertainty_index": 0.0,
                    "cross_asset_quality": {"stale_feeds": [], "missing": {}},
                }

                # option chain (synthetic)
                try:
                    market_data["option_chain"] = fetch_option_chain(sym, price, force_synthetic=True)
                except Exception:
                    market_data["option_chain"] = []

                gate = self.gatekeeper.evaluate(market_data, mode="MAIN")
                decision = {
                    "trace_id": f"replay-{date_str}-{sym}-{trace_counter}",
                    "ts_epoch": ts_epoch,
                    "ts_iso": datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    "symbol": sym,
                    "ltp": price,
                    "features": features,
                    "regime": regime_out.get("primary_regime"),
                    "regime_probs": regime_out.get("regime_probs"),
                    "regime_entropy": regime_out.get("regime_entropy"),
                    "unstable_regime_flag": regime_out.get("unstable_regime_flag"),
                    "gatekeeper_allowed": gate.allowed,
                    "gatekeeper_reasons": gate.reasons,
                    "risk_allowed": None,
                    "exec_guard_allowed": None,
                    "trade": None,
                    "why": {},
                }

                if gate.allowed:
                    trade = self.trade_builder.build(
                        market_data,
                        quick_mode=False,
                        debug_reasons=False,
                        force_family=gate.family,
                        allow_fallbacks=False,
                        allow_baseline=False,
                    )
                    if trade:
                        decision["trade"] = asdict(trade)
                        allowed, reason = self.risk_engine.allow_trade(self.portfolio)
                        decision["risk_allowed"] = bool(allowed)
                        decision["risk_reason"] = reason
                        if allowed:
                            ok, guard_reason = self.exec_guard.validate(trade, self.portfolio, trade.regime)
                            decision["exec_guard_allowed"] = bool(ok)
                            decision["exec_guard_reason"] = guard_reason
                        # compute score explanation
                        try:
                            opt = market_data.get("option_chain", [{}])[0] if market_data.get("option_chain") else {}
                            rr = None
                            try:
                                rr = abs(trade.target - trade.entry_price) / max(abs(trade.entry_price - trade.stop_loss), 1e-6)
                            except Exception:
                                rr = None
                            detail = compute_trade_score(market_data, opt, trade.side, rr, getattr(trade, "strategy", None))
                            decision["why"] = {"score": detail.get("score"), "detail": detail}
                        except Exception:
                            decision["why"] = {}

                f.write(json.dumps(decision, default=str) + "\n")
                trace_counter += 1
                if speed > 0:
                    time.sleep(1.0 / speed)

        cfg.REQUIRE_CROSS_ASSET = prev_require
        cfg.EXECUTION_MODE = prev_mode
        return out_path
