from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import config as cfg
from core.events import write_json_atomic
from core.paths import logs_dir, regime_runtime_evidence_path
from core.time_utils import now_utc_epoch


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    n = float(len(x))
    sx = sum(x)
    sy = sum(y)
    sxy = sum(a * b for a, b in zip(x, y))
    sx2 = sum(a * a for a in x)
    sy2 = sum(b * b for b in y)
    denom = ((n * sx2 - sx * sx) * (n * sy2 - sy * sy)) ** 0.5
    if denom <= 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


def _normalize_regime(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"TREND", "RANGE", "EVENT", "NEUTRAL"}:
        return raw
    return "NEUTRAL"


@dataclass(frozen=True)
class RegimeOutcome:
    symbol: str
    ts_epoch: float
    predicted_regime: str
    confidence: float
    realized_return: float
    correct: bool


class RegimeMonitor:
    """
    Tracks regime prediction reliability over rolling windows.
    """

    def __init__(
        self,
        *,
        window_size: int | None = None,
        min_samples: int | None = None,
        collapse_accuracy_min: float | None = None,
        severe_accuracy_min: float | None = None,
        collapse_corr_min: float | None = None,
        severe_windows: int | None = None,
        status_path=None,
        log_path=None,
    ) -> None:
        self.window_size = max(10, int(window_size or getattr(cfg, "REGIME_MONITOR_WINDOW_SIZE", 120)))
        self.min_samples = max(5, int(min_samples or getattr(cfg, "REGIME_MONITOR_MIN_SAMPLES", 24)))
        self.collapse_accuracy_min = _to_float(
            collapse_accuracy_min,
            getattr(cfg, "REGIME_MONITOR_COLLAPSE_ACCURACY_MIN", 0.45),
        )
        self.severe_accuracy_min = _to_float(
            severe_accuracy_min,
            getattr(cfg, "REGIME_MONITOR_SEVERE_ACCURACY_MIN", 0.30),
        )
        self.collapse_corr_min = _to_float(
            collapse_corr_min,
            getattr(cfg, "REGIME_MONITOR_COLLAPSE_CORR_MIN", -0.10),
        )
        self.severe_windows = max(1, int(severe_windows or getattr(cfg, "REGIME_MONITOR_SEVERE_WINDOWS", 3)))
        self.trend_move_min = _to_float(getattr(cfg, "REGIME_MONITOR_TREND_MOVE_MIN", 0.0007), 0.0007)
        self.range_move_max = _to_float(getattr(cfg, "REGIME_MONITOR_RANGE_MOVE_MAX", 0.0008), 0.0008)
        self.event_move_min = _to_float(getattr(cfg, "REGIME_MONITOR_EVENT_MOVE_MIN", 0.0015), 0.0015)
        self.neutral_move_max = _to_float(getattr(cfg, "REGIME_MONITOR_NEUTRAL_MOVE_MAX", 0.0010), 0.0010)
        self.status_path = status_path or (logs_dir() / "regime_monitor_status.json")
        self.log_path = log_path or (logs_dir() / "regime_monitor.jsonl")
        self._pending_by_symbol: dict[str, dict[str, float | str]] = {}
        self._outcomes: deque[RegimeOutcome] = deque(maxlen=self.window_size)
        self._collapse_streak = 0
        self._last_status = self._empty_status()
        self._lock = threading.RLock()

    def _empty_status(self) -> dict[str, Any]:
        return {
            "ts_epoch": now_utc_epoch(),
            "sample_count": 0,
            "accuracy": 0.0,
            "confidence_correlation": 0.0,
            "collapsed": False,
            "severe": False,
            "collapse_streak": 0,
            "thresholds": {
                "min_samples": int(self.min_samples),
                "collapse_accuracy_min": float(self.collapse_accuracy_min),
                "severe_accuracy_min": float(self.severe_accuracy_min),
                "collapse_corr_min": float(self.collapse_corr_min),
                "severe_windows": int(self.severe_windows),
            },
            "size_multiplier": float(getattr(cfg, "REGIME_MONITOR_SIZE_MULT_ON_COLLAPSE", 0.5)),
            "block_regime_dependent": bool(getattr(cfg, "REGIME_MONITOR_BLOCK_ON_COLLAPSE", True)),
            "latest_outcome": None,
            "source": "regime_monitor",
        }

    def _score(self, regime: str, realized_return: float) -> bool:
        move = abs(float(realized_return))
        if regime == "TREND":
            return bool(move >= self.trend_move_min)
        if regime == "RANGE":
            return bool(move <= self.range_move_max)
        if regime == "EVENT":
            return bool(move >= self.event_move_min)
        return bool(move <= self.neutral_move_max)

    def _persist_status(self, status: dict[str, Any]) -> None:
        try:
            write_json_atomic(self.status_path, status)
        except Exception:
            pass

    def _append_log(self, row: dict[str, Any]) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        except Exception:
            pass

    def record_market_snapshot(
        self,
        *,
        symbol: str,
        predicted_regime: str,
        confidence: float | None,
        ltp: float | None,
        ts_epoch: float | None = None,
    ) -> dict[str, Any]:
        sym = str(symbol or "").strip().upper()
        if not sym:
            return self.get_status()
        regime = _normalize_regime(predicted_regime)
        conf = max(0.0, min(1.0, _to_float(confidence, 0.0)))
        tick = _to_float(ltp, 0.0)
        ts_val = _to_float(ts_epoch, now_utc_epoch())

        with self._lock:
            pending = self._pending_by_symbol.get(sym)
            latest_outcome = None
            if pending and tick > 0 and _to_float(pending.get("ltp"), 0.0) > 0:
                base = _to_float(pending.get("ltp"), 0.0)
                realized_return = (tick - base) / base if base else 0.0
                prev_regime = _normalize_regime(pending.get("predicted_regime"))
                prev_conf = max(0.0, min(1.0, _to_float(pending.get("confidence"), 0.0)))
                correct = self._score(prev_regime, realized_return)
                outcome = RegimeOutcome(
                    symbol=sym,
                    ts_epoch=ts_val,
                    predicted_regime=prev_regime,
                    confidence=prev_conf,
                    realized_return=float(realized_return),
                    correct=bool(correct),
                )
                self._outcomes.append(outcome)
                latest_outcome = {
                    "symbol": sym,
                    "predicted_regime": prev_regime,
                    "confidence": prev_conf,
                    "realized_return": float(realized_return),
                    "correct": bool(correct),
                    "ts_epoch": ts_val,
                }
                self._append_log({"event": "regime_outcome", **latest_outcome})
                
                try:
                    timeline_path = regime_runtime_evidence_path()
                    timeline_path.parent.mkdir(parents=True, exist_ok=True)
                    row = {
                        "market_timestamp": str(ts_val),
                        "symbol": sym,
                        "tradebot_regime": prev_regime,
                        "selected_strategy": "Unknown",
                        "source": "runtime",
                        "source_file": "regime_monitor",
                    }
                    with timeline_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(row, sort_keys=True) + "\n")
                except Exception:
                    pass


            self._pending_by_symbol[sym] = {
                "predicted_regime": regime,
                "confidence": conf,
                "ltp": tick,
                "ts_epoch": ts_val,
            }
            status = self._compute_status(latest_outcome=latest_outcome)
            self._last_status = status
            self._persist_status(status)
            return status

    def _compute_status(self, *, latest_outcome: dict[str, Any] | None = None) -> dict[str, Any]:
        sample_count = int(len(self._outcomes))
        if sample_count <= 0:
            status = self._empty_status()
            status["latest_outcome"] = latest_outcome
            return status
        correct_flags = [1.0 if row.correct else 0.0 for row in self._outcomes]
        confidences = [float(row.confidence) for row in self._outcomes]
        accuracy = sum(correct_flags) / float(sample_count)
        corr = _pearson(confidences, correct_flags)
        collapsed = False
        severe = False
        if sample_count >= self.min_samples:
            collapsed = bool(accuracy < self.collapse_accuracy_min or corr < self.collapse_corr_min)
            if collapsed:
                self._collapse_streak += 1
            else:
                self._collapse_streak = 0
            severe = bool(
                accuracy < self.severe_accuracy_min
                or self._collapse_streak >= self.severe_windows
            )
        else:
            self._collapse_streak = 0

        return {
            "ts_epoch": now_utc_epoch(),
            "sample_count": sample_count,
            "accuracy": round(float(accuracy), 6),
            "confidence_correlation": round(float(corr), 6),
            "collapsed": bool(collapsed),
            "severe": bool(severe),
            "collapse_streak": int(self._collapse_streak),
            "thresholds": {
                "min_samples": int(self.min_samples),
                "collapse_accuracy_min": float(self.collapse_accuracy_min),
                "severe_accuracy_min": float(self.severe_accuracy_min),
                "collapse_corr_min": float(self.collapse_corr_min),
                "severe_windows": int(self.severe_windows),
            },
            "size_multiplier": float(getattr(cfg, "REGIME_MONITOR_SIZE_MULT_ON_COLLAPSE", 0.5)),
            "block_regime_dependent": bool(getattr(cfg, "REGIME_MONITOR_BLOCK_ON_COLLAPSE", True)),
            "latest_outcome": latest_outcome,
            "source": "regime_monitor",
        }

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_status)


_REGIME_MONITOR_SINGLETON: RegimeMonitor | None = None
_REGIME_MONITOR_SINGLETON_LOCK = threading.RLock()


def get_regime_monitor() -> RegimeMonitor:
    global _REGIME_MONITOR_SINGLETON
    with _REGIME_MONITOR_SINGLETON_LOCK:
        if _REGIME_MONITOR_SINGLETON is None:
            _REGIME_MONITOR_SINGLETON = RegimeMonitor()
        return _REGIME_MONITOR_SINGLETON


def get_regime_monitor_status(*, prefer_disk: bool = False) -> dict[str, Any]:
    status_path = Path(str(getattr(cfg, "REGIME_MONITOR_STATUS_PATH", logs_dir() / "regime_monitor_status.json")))
    if prefer_disk and status_path.exists():
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return get_regime_monitor().get_status()
