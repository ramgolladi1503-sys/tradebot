import json
import time
from pathlib import Path
from datetime import datetime
from config import config as cfg
from core.kite_client import kite_client
from core.strategy_tracker import StrategyTracker
import pandas as pd

REJECTED_PATH = Path("logs/rejected_candidates.jsonl")
TRACK_PATH = Path("logs/blocked_tracking.jsonl")
OUTCOME_PATH = Path("logs/blocked_outcomes.jsonl")
PROCESSED_PATH = Path("logs/blocked_outcomes_processed.json")


class BlockedTradeTracker:
    def __init__(self):
        self._last_reject_ts = 0

    def _read_rejections(self):
        if not REJECTED_PATH.exists():
            return []
        rows = []
        with REJECTED_PATH.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows

    def capture_from_log(self):
        if not getattr(cfg, "BLOCKED_TRACK_ENABLE", True):
            return
        now = time.time()
        if now - getattr(self, "_last_update", 0) < getattr(cfg, "BLOCKED_TRACK_POLL_SEC", 15):
            return
        self._last_update = now
        rows = self._read_rejections()
        if not rows:
            return
        # avoid duplicates by blocked_id already in tracking file
        existing_ids = set()
        if TRACK_PATH.exists():
            try:
                with TRACK_PATH.open() as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            r = json.loads(line)
                            if r.get("blocked_id"):
                                existing_ids.add(r.get("blocked_id"))
                        except Exception:
                            continue
            except Exception:
                pass
        # capture only the most recent items (last 5)
        for rec in rows[-5:]:
            ts = rec.get("timestamp")
            try:
                ts_dt = datetime.fromisoformat(ts)
                ts_epoch = ts_dt.timestamp()
            except Exception:
                ts_epoch = now
            if ts_epoch <= self._last_reject_ts:
                continue
            self._last_reject_ts = ts_epoch
            trade_id = f"BLK-{rec.get('symbol')}-{rec.get('strike')}-{rec.get('type')}-{int(ts_epoch)}"
            entry = {
                "blocked_id": trade_id,
                "timestamp": datetime.now().isoformat(),
                "symbol": rec.get("symbol"),
                "strike": rec.get("strike"),
                "type": rec.get("type"),
                "reason": rec.get("reason"),
                "entry": rec.get("ltp"),
                "stop": rec.get("stop"),
                "target": rec.get("target"),
                "atr": rec.get("atr"),
                "start_ts": now,
                "end_ts": now + getattr(cfg, "BLOCKED_TRACK_SECONDS", 3600),
                "mfe": 0.0,
                "mae": 0.0,
                "status": "TRACKING",
            }
            if trade_id in existing_ids:
                continue
            TRACK_PATH.parent.mkdir(exist_ok=True)
            with TRACK_PATH.open("a") as f:
                f.write(json.dumps(entry) + "\n")

    def _ltp_for_blocked(self, rec):
        if not kite_client.kite:
            return None
        symbol = rec.get("symbol")
        strike = rec.get("strike")
        opt_type = rec.get("type")
        if not symbol or strike is None or not opt_type:
            return None
        exchange = "BFO" if str(symbol).upper() == "SENSEX" else "NFO"
        ts = None
        try:
            ts = kite_client.find_option_symbol(symbol, strike, opt_type, exchange=exchange)
        except Exception:
            ts = None
        if not ts:
            ts = f"{exchange}:{symbol}{int(float(strike))}{opt_type}"
        try:
            q = kite_client.quote([ts])
            return q.get(ts, {}).get("last_price")
        except Exception:
            return None

    def update(self, predictor=None):
        if not getattr(cfg, "BLOCKED_TRACK_ENABLE", True):
            return
        if not TRACK_PATH.exists():
            return
        rows = []
        with TRACK_PATH.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if not rows:
            return
        now = time.time()
        updated = []
        outcomes = []
        for rec in rows:
            if rec.get("status") != "TRACKING":
                updated.append(rec)
                continue
            if now > rec.get("end_ts", 0):
                rec["status"] = "NO_HIT"
                outcomes.append(self._finalize(rec, outcome="NO_HIT"))
                continue
            ltp = self._ltp_for_blocked(rec)
            if ltp is None or rec.get("entry") is None:
                updated.append(rec)
                continue
            entry = rec.get("entry")
            mfe = max(rec.get("mfe", 0.0), ltp - entry)
            mae = min(rec.get("mae", 0.0), ltp - entry)
            rec["mfe"] = round(mfe, 3)
            rec["mae"] = round(mae, 3)
            # First-hit logic
            if rec.get("target") is not None and ltp >= rec["target"]:
                rec["status"] = "TARGET_HIT"
                rec["exit"] = rec["target"]
                outcomes.append(self._finalize(rec, outcome="TARGET_HIT"))
                continue
            if rec.get("stop") is not None and ltp <= rec["stop"]:
                rec["status"] = "STOP_HIT"
                rec["exit"] = rec["stop"]
                outcomes.append(self._finalize(rec, outcome="STOP_HIT"))
                continue
            updated.append(rec)

        # persist tracking state
        TRACK_PATH.write_text("")
        with TRACK_PATH.open("a") as f:
            for r in updated:
                f.write(json.dumps(r) + "\n")
        if outcomes:
            OUTCOME_PATH.parent.mkdir(exist_ok=True)
            with OUTCOME_PATH.open("a") as f:
                for o in outcomes:
                    f.write(json.dumps(o) + "\n")
            # Merge into strategy performance
            self._merge_strategy_perf(outcomes)
            # Auto-train ML using blocked outcomes
            if predictor:
                self._train_ml_from_blocked(outcomes, predictor)

    def _finalize(self, rec, outcome):
        entry = rec.get("entry") or 0
        exit_px = rec.get("exit", entry)
        pnl = exit_px - entry
        return {
            "blocked_id": rec.get("blocked_id"),
            "timestamp": datetime.now().isoformat(),
            "symbol": rec.get("symbol"),
            "strike": rec.get("strike"),
            "type": rec.get("type"),
            "reason": rec.get("reason"),
            "entry": entry,
            "exit": exit_px,
            "pnl": round(pnl, 3),
            "outcome": outcome,
            "mfe": rec.get("mfe", 0.0),
            "mae": rec.get("mae", 0.0),
            "atr": rec.get("atr"),
        }

    def _processed_ids(self):
        if not PROCESSED_PATH.exists():
            return set()
        try:
            data = json.loads(PROCESSED_PATH.read_text())
            return set(data)
        except Exception:
            return set()

    def _save_processed(self, ids):
        PROCESSED_PATH.parent.mkdir(exist_ok=True)
        PROCESSED_PATH.write_text(json.dumps(sorted(list(ids))))

    def _merge_strategy_perf(self, outcomes):
        tracker = StrategyTracker()
        tracker.load("logs/strategy_perf.json")
        processed = self._processed_ids()
        for o in outcomes:
            bid = o.get("blocked_id")
            if bid in processed:
                continue
            pnl = o.get("pnl", 0.0) or 0.0
            reason = o.get("reason") or "UNKNOWN"
            tracker.record("BLOCKED_ALL", pnl)
            tracker.record(f"BLOCKED::{reason}", pnl)
            processed.add(bid)
        tracker.save("logs/strategy_perf.json")
        self._save_processed(processed)

    def _train_ml_from_blocked(self, outcomes, predictor):
        if not getattr(cfg, "BLOCKED_TRAIN_ENABLE", True):
            return
        if len(outcomes) < getattr(cfg, "BLOCKED_TRAIN_MIN", 20):
            return
        weight = float(getattr(cfg, "BLOCKED_TRAIN_WEIGHT", 0.5))
        rows = []
        for o in outcomes:
            entry = o.get("entry")
            if entry is None:
                continue
            is_call = 1 if str(o.get("type", "")).upper() == "CE" else 0
            rows.append({
                "ltp": entry,
                "bid": entry * 0.999,
                "ask": entry * 1.001,
                "spread_pct": 0.002,
                "volume": 0,
                "atr": o.get("atr") or 0,
                "vwap_dist": 0,
                "moneyness": 0,
                "vwap_slope": 0,
                "rsi_mom": 0,
                "vol_z": 0,
                "is_call": is_call,
                "actual": 1 if o.get("outcome") == "TARGET_HIT" else 0,
                "sample_weight": weight,
            })
        if not rows:
            return
        df = pd.DataFrame(rows)
        predictor.update_model_online(df, target_col="actual")
        # Also train blocked-only model
        try:
            from ml.trade_predictor import TradePredictor
            blocked_model = TradePredictor(model_path=getattr(cfg, "BLOCKED_ML_MODEL_PATH", "models/xgb_blocked_model.pkl"))
            blocked_model.update_model_online(df, target_col="actual")
        except Exception:
            pass
