"""Track blocked candidates and feed outcomes back into strategy/ML learning.

Migration note:
- Canonical runtime paths are resolved via `core.learning_paths`.
- Legacy `./logs/*` files are still read for backward compatibility.
"""

from __future__ import annotations

from core.paths import data_root, logs_dir
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import config as cfg
from core.kite_client import kite_client
from core.learning_paths import (
    blocked_outcomes_path,
    blocked_outcomes_processed_path,
    blocked_tracking_path,
    feedback_train_state_path,
    rejected_candidates_paths,
    suggestion_eval_log_paths,
)
from core.outcome_labels import attach_candidate_outcome_labels
from core.strategy_tracker import StrategyTracker


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        rows.append(obj)
                except Exception:
                    continue
    except Exception:
        return []
    return rows


class BlockedTradeTracker:
    def __init__(self):
        self._last_reject_ts = 0.0

    def _parse_ts_epoch(self, raw, default_epoch: float) -> float:
        if raw in (None, ""):
            return default_epoch
        try:
            return float(raw)
        except Exception:
            pass
        try:
            return datetime.fromisoformat(str(raw)).timestamp()
        except Exception:
            return default_epoch

    def _read_rejections(self) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for path in self._rejection_source_paths():
            for rec in _read_jsonl(path):
                key = str(
                    rec.get("blocked_id")
                    or rec.get("trade_id")
                    or f"{rec.get('symbol')}|{rec.get('strike')}|{rec.get('type')}|{rec.get('timestamp')}"
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(rec)
        now = time.time()
        rows.sort(key=lambda r: self._parse_ts_epoch(r.get("timestamp"), now))
        return rows

    def _rejection_source_paths(self) -> list[Path]:
        def _normalize(paths: list[Path]) -> list[Path]:
            out: list[Path] = []
            seen: set[str] = set()
            for raw_path in paths:
                try:
                    path = Path(raw_path).expanduser()
                except Exception:
                    continue
                key = str(path)
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(path)
            return out

        source_paths = _normalize(list(rejected_candidates_paths()))
        desk_path = None
        try:
            desk_log_dir = str(getattr(cfg, "DESK_LOG_DIR", "") or "").strip()
        except Exception:
            desk_log_dir = ""
        if desk_log_dir:
            desk_path = Path(desk_log_dir).expanduser() / "blocked_candidates.jsonl"

        # When a desk blocked-candidates source exists, it is the canonical blocked feed.
        # Do not also ingest generic or inherited rejected-candidates fallbacks in the same pass.
        if desk_path is not None and desk_path.exists():
            return _normalize([desk_path])

        return source_paths

    def capture_from_log(self):
        if not getattr(cfg, "BLOCKED_TRACK_ENABLE", True):
            return
        now = time.time()
        if now - getattr(self, "_last_update", 0.0) < getattr(cfg, "BLOCKED_TRACK_POLL_SEC", 15):
            return
        self._last_update = now

        rows = self._read_rejections()
        if not rows:
            return

        track_path = blocked_tracking_path()
        existing_ids = set()
        for rec in _read_jsonl(track_path):
            bid = rec.get("blocked_id")
            if bid:
                existing_ids.add(str(bid))

        capture_n = max(1, int(getattr(cfg, "BLOCKED_CAPTURE_BATCH", 5)))
        for rec in rows[-capture_n:]:
            ts_epoch = self._parse_ts_epoch(rec.get("timestamp"), now)
            if ts_epoch <= self._last_reject_ts:
                continue
            self._last_reject_ts = max(self._last_reject_ts, ts_epoch)

            symbol = rec.get("symbol")
            strike = rec.get("strike")
            opt_type = rec.get("type") or rec.get("opt_type")
            trade_id = rec.get("trade_id")
            blocked_id = str(
                rec.get("blocked_id")
                or trade_id
                or f"BLK-{symbol}-{strike}-{opt_type}-{int(ts_epoch)}"
            )
            if blocked_id in existing_ids:
                continue

            entry_price = (
                rec.get("ltp")
                if rec.get("ltp") is not None
                else rec.get("entry")
                if rec.get("entry") is not None
                else rec.get("entry_price")
            )
            entry_f = _safe_float(entry_price)
            if entry_f is None:
                continue

            existing_ids.add(blocked_id)
            entry = {
                "blocked_id": blocked_id,
                "trade_id": trade_id,
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "strike": strike,
                "type": opt_type,
                "reason": rec.get("reason") or rec.get("reasons") or "UNKNOWN",
                "entry": entry_f,
                "stop": _safe_float(rec.get("stop")),
                "target": _safe_float(rec.get("target")),
                "atr": _safe_float(rec.get("atr")) or 0.0,
                "start_ts": now,
                "end_ts": now + float(getattr(cfg, "BLOCKED_TRACK_SECONDS", 3600)),
                "mfe": 0.0,
                "mae": 0.0,
                "status": "TRACKING",
            }
            track_path.parent.mkdir(parents=True, exist_ok=True)
            with track_path.open("a") as f:
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

        track_path = blocked_tracking_path()
        rows = _read_jsonl(track_path)

        now = time.time()
        updated: list[dict] = []
        outcomes: list[dict] = []

        for rec in rows:
            if rec.get("status") != "TRACKING":
                updated.append(rec)
                continue
            if now > float(rec.get("end_ts", 0) or 0):
                rec["status"] = "NO_HIT"
                outcomes.append(self._finalize(rec, outcome="NO_HIT"))
                continue

            ltp = self._ltp_for_blocked(rec)
            entry = _safe_float(rec.get("entry"))
            if ltp is None or entry is None:
                updated.append(rec)
                continue

            mfe = max(_safe_float(rec.get("mfe")) or 0.0, float(ltp) - entry)
            mae = min(_safe_float(rec.get("mae")) or 0.0, float(ltp) - entry)
            rec["mfe"] = round(float(mfe), 3)
            rec["mae"] = round(float(mae), 3)

            target = _safe_float(rec.get("target"))
            stop = _safe_float(rec.get("stop"))
            if target is not None and float(ltp) >= target:
                rec["status"] = "TARGET_HIT"
                rec["exit"] = target
                outcomes.append(self._finalize(rec, outcome="TARGET_HIT"))
                continue
            if stop is not None and float(ltp) <= stop:
                rec["status"] = "STOP_HIT"
                rec["exit"] = stop
                outcomes.append(self._finalize(rec, outcome="STOP_HIT"))
                continue
            updated.append(rec)

        if rows:
            track_path.parent.mkdir(parents=True, exist_ok=True)
            track_path.write_text("")
            if updated:
                with track_path.open("a") as f:
                    for row in updated:
                        f.write(json.dumps(row) + "\n")

        if outcomes:
            out_path = blocked_outcomes_path()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("a") as f:
                for out in outcomes:
                    f.write(json.dumps(out) + "\n")
            self._merge_strategy_perf(outcomes)

        if predictor is not None:
            self._train_ml_feedback(predictor)

    def _finalize(self, rec, outcome):
        entry = _safe_float(rec.get("entry")) or 0.0
        exit_px = _safe_float(rec.get("exit"))
        if exit_px is None:
            exit_px = entry
        pnl = float(exit_px) - float(entry)
        payload = {
            "blocked_id": rec.get("blocked_id"),
            "timestamp": datetime.now().isoformat(),
            "symbol": rec.get("symbol"),
            "strike": rec.get("strike"),
            "type": rec.get("type"),
            "reason": rec.get("reason"),
            "permission": "BLOCK",
            "execution_status": "blocked",
            "entry": entry,
            "exit": float(exit_px),
            "pnl": round(pnl, 3),
            "outcome": outcome,
            "mfe": _safe_float(rec.get("mfe")) or 0.0,
            "mae": _safe_float(rec.get("mae")) or 0.0,
            "atr": _safe_float(rec.get("atr")) or 0.0,
        }
        return attach_candidate_outcome_labels(payload)

    def _processed_ids(self):
        path = blocked_outcomes_processed_path()
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text())
            return set(data)
        except Exception:
            return set()

    def _save_processed(self, ids):
        path = blocked_outcomes_processed_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(list(ids))))

    def _strategy_perf_path(self) -> str:
        return str(getattr(cfg, "STRATEGY_PERF_PATH", str(logs_dir() / "strategy_perf.json")))

    def _merge_strategy_perf(self, outcomes):
        tracker = StrategyTracker()
        tracker.load(self._strategy_perf_path())
        processed = self._processed_ids()
        for out in outcomes:
            bid = out.get("blocked_id")
            if bid in processed:
                continue
            pnl = _safe_float(out.get("pnl")) or 0.0
            reason = out.get("reason") or "UNKNOWN"
            tracker.record("BLOCKED_ALL", pnl)
            tracker.record(f"BLOCKED::{reason}", pnl)
            processed.add(bid)
        tracker.save(self._strategy_perf_path())
        self._save_processed(processed)

    def _load_feedback_state(self) -> dict:
        path = feedback_train_state_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def _save_feedback_state(self, state: dict):
        path = feedback_train_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True))

    def _build_blocked_training_rows(self, window: int) -> tuple[list[dict], int]:
        outcomes = _read_jsonl(blocked_outcomes_path())
        total = len(outcomes)
        if window > 0:
            outcomes = outcomes[-window:]

        weight = float(getattr(cfg, "BLOCKED_TRAIN_WEIGHT", 0.5))
        rows: list[dict] = []
        for out in outcomes:
            entry = _safe_float(out.get("entry"))
            if entry is None:
                continue
            is_call = 1 if str(out.get("type", "")).upper() == "CE" else 0
            outcome = str(out.get("outcome", "")).upper()
            rows.append(
                {
                    "ltp": entry,
                    "bid": entry * 0.999,
                    "ask": entry * 1.001,
                    "spread_pct": 0.002,
                    "volume": 0,
                    "atr": _safe_float(out.get("atr")) or 0.0,
                    "vwap_dist": 0,
                    "moneyness": 0,
                    "vwap_slope": 0,
                    "rsi_mom": 0,
                    "vol_z": 0,
                    "is_call": is_call,
                    "actual": 1 if outcome in {"TARGET_HIT", "TARGET"} else 0,
                    "sample_weight": weight,
                }
            )
        return rows, total

    def _build_suggestion_training_rows(self, window: int) -> tuple[list[dict], int]:
        records: list[dict] = []
        seen: set[str] = set()
        for path in suggestion_eval_log_paths():
            for rec in _read_jsonl(path):
                key = str(
                    rec.get("trade_id")
                    or f"{rec.get('symbol')}|{rec.get('strike')}|{rec.get('opt_type')}|{rec.get('outcome')}|{rec.get('timestamp')}"
                )
                if key in seen:
                    continue
                seen.add(key)
                records.append(rec)
        total = len(records)
        if window > 0:
            records = records[-window:]

        weight = float(getattr(cfg, "SUGGESTION_TRAIN_WEIGHT", 0.35))
        rows: list[dict] = []
        for rec in records:
            ltp = _safe_float(rec.get("ltp"))
            if ltp is None:
                continue
            opt_type = str(rec.get("opt_type") or "").upper()
            outcome = str(rec.get("outcome") or "").lower()
            rows.append(
                {
                    "ltp": ltp,
                    "bid": ltp * 0.999,
                    "ask": ltp * 1.001,
                    "spread_pct": 0.002,
                    "volume": 0,
                    "atr": 0.0,
                    "vwap_dist": 0,
                    "moneyness": 0,
                    "vwap_slope": 0,
                    "rsi_mom": 0,
                    "vol_z": 0,
                    "is_call": 1 if opt_type == "CE" else 0,
                    "actual": 1 if outcome in {"target", "target_hit"} else 0,
                    "sample_weight": weight,
                }
            )
        return rows, total

    def _train_ml_feedback(self, predictor):
        state = self._load_feedback_state()
        window = max(1, int(getattr(cfg, "BLOCKED_TRAIN_WINDOW", 300)))
        changed = False

        if bool(getattr(cfg, "BLOCKED_TRAIN_ENABLE", True)):
            blocked_rows, blocked_total = self._build_blocked_training_rows(window)
            prev_total = int(state.get("blocked_total", 0) or 0)
            min_rows = max(1, int(getattr(cfg, "BLOCKED_TRAIN_MIN", 20)))
            if blocked_total > prev_total and len(blocked_rows) >= min_rows:
                df = pd.DataFrame(blocked_rows)
                predictor.update_model_online(df, target_col="actual")
                try:
                    from ml.trade_predictor import TradePredictor

                    blocked_model = TradePredictor(
                        model_path=str(
                            getattr(cfg, "BLOCKED_ML_MODEL_PATH", "models/xgb_blocked_model.pkl")
                        )
                    )
                    blocked_model.update_model_online(df, target_col="actual")
                except Exception:
                    pass
            if blocked_total > prev_total:
                state["blocked_total"] = blocked_total
                state["blocked_rows"] = len(blocked_rows)
                state["blocked_seen_at"] = time.time()
                changed = True

        if bool(getattr(cfg, "SUGGESTION_TRAIN_ENABLE", True)):
            suggestion_rows, suggestion_total = self._build_suggestion_training_rows(window)
            prev_total = int(state.get("suggestion_total", 0) or 0)
            min_rows = max(1, int(getattr(cfg, "SUGGESTION_TRAIN_MIN", 5)))
            if suggestion_total > prev_total and len(suggestion_rows) >= min_rows:
                df = pd.DataFrame(suggestion_rows)
                predictor.update_model_online(df, target_col="actual")
            if suggestion_total > prev_total:
                state["suggestion_total"] = suggestion_total
                state["suggestion_rows"] = len(suggestion_rows)
                state["suggestion_seen_at"] = time.time()
                changed = True

        if changed:
            self._save_feedback_state(state)
