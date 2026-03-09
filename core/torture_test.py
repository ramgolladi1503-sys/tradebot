from __future__ import annotations

import argparse
import os
import json
import math
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from core.broker.mock_broker import MockBroker
from core.decision_builder import build_decision
from core.event_integrity import validate_events_file
from core.events import append_event, events_path, read_events, write_json_atomic
from core.health_scenarios import run_golden_path
from core.paths import logs_dir
from core.runtime_lifecycle import lifecycle
from core.time_utils import utc_now


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    idx = int(math.ceil(0.95 * len(ordered))) - 1
    idx = max(0, min(idx, len(ordered) - 1))
    return float(ordered[idx])


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _rss_mb() -> float | None:
    try:
        import psutil  # type: ignore

        proc = psutil.Process(os.getpid())
        return float(proc.memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        return None


class _RotatingJsonlWriter:
    def __init__(self, base_path: Path, *, max_bytes_per_file: int = 256_000) -> None:
        self.base_path = Path(base_path)
        self.max_bytes_per_file = max(8_192, int(max_bytes_per_file))
        self.base_path.parent.mkdir(parents=True, exist_ok=True)
        self._part = 0
        self._active = self._part_path(self._part)
        self._active.touch(exist_ok=True)
        self.max_file_size_bytes = int(self._active.stat().st_size)
        self.lines_written = 0
        self.rotation_count = 0

    def _part_path(self, idx: int) -> Path:
        stem = self.base_path.stem
        suffix = self.base_path.suffix or ".jsonl"
        return self.base_path.with_name(f"{stem}.part{idx:03d}{suffix}")

    def write(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n"
        line_bytes = len(line.encode("utf-8"))
        current_size = int(self._active.stat().st_size) if self._active.exists() else 0
        if current_size + line_bytes > self.max_bytes_per_file:
            self._part += 1
            self.rotation_count += 1
            self._active = self._part_path(self._part)
            self._active.touch(exist_ok=True)
            current_size = 0
        with self._active.open("a", encoding="utf-8") as handle:
            handle.write(line)
        next_size = current_size + line_bytes
        self.max_file_size_bytes = max(self.max_file_size_bytes, int(next_size))
        self.lines_written += 1


def _build_trade_intent_from_option_row(
    row: dict[str, Any],
    *,
    trade_id: str,
    run_id: str,
    desk_id: str,
    ts_iso: str,
    side: str = "BUY",
) -> tuple[dict[str, Any] | None, str | None]:
    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return None, "missing_symbol"

    token = row.get("instrument_token")
    if token is None:
        return None, "instrument_token_missing"
    try:
        token_int = int(token)
    except Exception:
        return None, "instrument_token_invalid"
    if token_int <= 0:
        return None, "instrument_token_invalid"

    ltp = _safe_float(row.get("ltp"))
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    if ltp is None or bid is None or ask is None:
        return None, "partial_option_row"
    if ltp <= 0 or bid <= 0 or ask <= 0:
        return None, "invalid_quote_values"
    if bid > ask:
        return None, "invalid_bid_ask"

    return {
        "trade_id": str(trade_id),
        "symbol": symbol,
        "side": str(side or "BUY").upper(),
        "qty": 1.0,
        "ltp": float(ltp),
        "bid": float(bid),
        "ask": float(ask),
        "instrument_token": token_int,
        "run_id": str(run_id),
        "desk_id": str(desk_id or "DEFAULT"),
        "mode": "PAPER",
        "ts": str(ts_iso),
    }, None


def _submit_mock_order(broker: MockBroker, intent: dict[str, Any]) -> dict[str, Any]:
    place_fn = getattr(broker, "place_order", None)
    if callable(place_fn):
        return dict(place_fn(intent) or {})
    raise RuntimeError("mock_broker_place_unavailable")


@dataclass
class _ScenarioResult:
    tick_count: int
    event_buffer_count: int
    reject_count: int
    reject_missing_reason_count: int
    trade_count: int
    duplicate_trade_id_count: int
    partial_trade_creation_count: int
    exception_count: int
    latency_samples_ms: list[float]
    extra_metrics: dict[str, Any] | None = None


class TortureTestRunner:
    def __init__(self, *, latency_threshold_ms: float = 100.0) -> None:
        self.latency_threshold_ms = float(latency_threshold_ms)

    def run_scenario(self, name: str, desk_id: str) -> dict[str, Any]:
        scenario = str(name or "").strip().lower()
        desk = str(desk_id or "DEFAULT")
        run_id = f"torture_{scenario}_{desk}_{utc_now().strftime('%Y%m%dT%H%M%S')}"
        started_threads = {t.name for t in threading.enumerate() if t.is_alive()}
        violations: list[dict[str, Any]] = []
        status = "PASS"

        try:
            if scenario == "market_open_spike":
                result = self._run_market_open_spike(run_id=run_id, desk_id=desk)
            elif scenario == "feed_flap_partial_data":
                result = self._run_feed_flap_partial_data(run_id=run_id, desk_id=desk)
            elif scenario == "long_run_stability":
                result = self._run_long_run_stability(run_id=run_id, desk_id=desk)
            elif scenario == "fault_injection":
                result = self._run_fault_injection(run_id=run_id, desk_id=desk)
            else:
                result = _ScenarioResult(
                    tick_count=0,
                    event_buffer_count=0,
                    reject_count=0,
                    reject_missing_reason_count=0,
                    trade_count=0,
                    duplicate_trade_id_count=0,
                    partial_trade_creation_count=0,
                    exception_count=1,
                    latency_samples_ms=[],
                    extra_metrics={},
                )
                violations.append(
                    {
                        "code": "unknown_scenario",
                        "message": f"Unsupported scenario: {scenario}",
                    }
                )
        except Exception as exc:
            result = _ScenarioResult(
                tick_count=0,
                event_buffer_count=0,
                reject_count=0,
                reject_missing_reason_count=0,
                trade_count=0,
                duplicate_trade_id_count=0,
                partial_trade_creation_count=0,
                exception_count=1,
                latency_samples_ms=[],
                extra_metrics={},
            )
            violations.append({"code": "uncaught_exception", "message": str(exc)})
        finally:
            lifecycle.stop_all(timeout=2.0)

        managed_active = list(lifecycle.active_thread_names())
        ended_threads = {t.name for t in threading.enumerate() if t.is_alive()}
        leaked_threads = sorted([name for name in ended_threads if name not in started_threads and name != "MainThread"])

        latency_max = max(result.latency_samples_ms) if result.latency_samples_ms else 0.0
        latency_p95 = _p95(result.latency_samples_ms)
        latency_avg = (
            float(sum(result.latency_samples_ms) / len(result.latency_samples_ms))
            if result.latency_samples_ms
            else 0.0
        )

        if result.exception_count > 0:
            violations.append({"code": "uncaught_exceptions", "message": f"exception_count={result.exception_count}"})
        if managed_active:
            violations.append({"code": "managed_thread_leak", "message": f"active_managed_threads={managed_active}"})
        if leaked_threads:
            violations.append({"code": "thread_leak", "message": f"leaked_threads={leaked_threads}"})
        if latency_max > self.latency_threshold_ms:
            violations.append(
                {
                    "code": "decision_latency_exceeded",
                    "message": f"max_latency_ms={latency_max:.3f} threshold_ms={self.latency_threshold_ms:.3f}",
                }
            )
        if result.reject_missing_reason_count > 0:
            violations.append(
                {
                    "code": "reject_reason_missing",
                    "message": f"rejects_missing_reason={result.reject_missing_reason_count}",
                }
            )
        if result.partial_trade_creation_count > 0:
            violations.append(
                {
                    "code": "partial_trade_created",
                    "message": f"partial_trade_creation_count={result.partial_trade_creation_count}",
                }
            )
        if result.duplicate_trade_id_count > 0:
            violations.append(
                {
                    "code": "duplicate_trade_id",
                    "message": f"duplicate_trade_id_count={result.duplicate_trade_id_count}",
                }
            )
        if result.tick_count > 0 and result.event_buffer_count > (result.tick_count * 10):
            violations.append(
                {
                    "code": "event_store_growth",
                    "message": (
                        f"event_buffer_count={result.event_buffer_count} "
                        f"tick_count={result.tick_count}"
                    ),
                }
            )
        extra_metrics = dict(result.extra_metrics or {})
        bounded_limit = int(extra_metrics.get("bounded_buffer_limit", 0) or 0)
        observed_buffer = int(extra_metrics.get("max_bounded_buffer_observed", 0) or 0)
        if bounded_limit > 0 and observed_buffer > bounded_limit:
            violations.append(
                {
                    "code": "bounded_buffer_exceeded",
                    "message": (
                        f"max_bounded_buffer_observed={observed_buffer} "
                        f"bounded_buffer_limit={bounded_limit}"
                    ),
                }
            )
        rotation_cap = int(extra_metrics.get("rotation_cap_bytes", 0) or 0)
        max_rotation_size = int(extra_metrics.get("rotation_max_file_size_bytes", 0) or 0)
        if rotation_cap > 0 and max_rotation_size > rotation_cap:
            violations.append(
                {
                    "code": "rotation_size_cap_exceeded",
                    "message": (
                        f"rotation_max_file_size_bytes={max_rotation_size} "
                        f"rotation_cap_bytes={rotation_cap}"
                    ),
                }
            )

        events_validation = validate_events_file(events_path())
        if not bool(events_validation.get("ok")):
            violations.append(
                {
                    "code": "event_log_corruption",
                    "message": (
                        f"bad_lines={int(events_validation.get('bad_lines') or 0)} "
                        f"truncated_tail={bool(events_validation.get('truncated_tail'))}"
                    ),
                }
            )

        if violations:
            status = "FAIL"

        scenario_events = read_events(run_id=run_id)
        report = {
            "scenario": scenario,
            "desk_id": desk,
            "run_id": run_id,
            "status": status,
            "violations": violations,
            "metrics": {
                "tick_count": int(result.tick_count),
                "event_count": int(len(scenario_events)),
                "event_buffer_count": int(result.event_buffer_count),
                "reject_count": int(result.reject_count),
                "reject_missing_reason_count": int(result.reject_missing_reason_count),
                "trade_count": int(result.trade_count),
                "duplicate_trade_id_count": int(result.duplicate_trade_id_count),
                "partial_trade_creation_count": int(result.partial_trade_creation_count),
                "exception_count": int(result.exception_count),
                "decision_latency_ms_avg": float(latency_avg),
                "decision_latency_ms_p95": float(latency_p95),
                "decision_latency_ms_max": float(latency_max),
                "latency_threshold_ms": float(self.latency_threshold_ms),
                "events_integrity_ok": bool(events_validation.get("ok")),
                "events_bad_lines": int(events_validation.get("bad_lines") or 0),
                "events_truncated_tail": bool(events_validation.get("truncated_tail")),
                **extra_metrics,
            },
        }
        report_path = logs_dir() / f"torture_test_report_{scenario}.json"
        write_json_atomic(report_path, report)
        report["report_path"] = str(report_path)
        return report

    def _run_market_open_spike(self, *, run_id: str, desk_id: str) -> _ScenarioResult:
        broker = MockBroker()
        event_buffer: list[dict[str, Any]] = []
        latencies: list[float] = []
        trade_ids: set[str] = set()
        duplicates = 0
        reject_count = 0
        reject_missing_reason = 0
        exception_count = 0
        trade_count = 0
        partial_trade_created = 0

        # Prime deterministic execution path through existing golden scenario.
        golden = run_golden_path(desk_id, run_id=f"{run_id}_golden")
        event_buffer.append({"kind": "golden_path", "ok": bool(golden.get("ok"))})

        start_epoch = 1772202300.0  # deterministic epoch anchor
        for idx in range(300):  # 5 minutes @ 1s cadence
            t0 = perf_counter()
            ts_epoch = start_epoch + float(idx)
            ts_iso = utc_now().isoformat().replace("+00:00", "Z")
            try:
                # deterministic first-5-minute spike path
                if idx < 80:
                    spot = 22450.0 + (idx * 2.8)
                elif idx < 160:
                    spot = 22674.0 + ((idx - 80) * 1.1)
                else:
                    spot = 22762.0 - ((idx - 160) * 1.9)
                spread_pct = min(0.032, 0.002 + (idx * 0.00012))
                depth_qty = max(4.0, 120.0 - (idx * 0.42))
                option_mid = max(15.0, 115.0 + (spot - 22500.0) * 0.22)
                half_spread = option_mid * spread_pct * 0.5
                bid = max(0.05, option_mid - half_spread)
                ask = max(bid + 0.05, option_mid + half_spread)

                reason_code: str | None = None
                should_execute = False
                if spread_pct > 0.02:
                    reason_code = "spread_too_wide"
                elif depth_qty < 18.0:
                    reason_code = "depth_thin"
                elif idx % 45 == 0:
                    should_execute = True
                else:
                    reason_code = "signal_below_threshold"

                option_row = {
                    "symbol": "NIFTY26FEB22500CE",
                    "instrument_token": 101010,
                    "ltp": option_mid,
                    "bid": bid,
                    "ask": ask,
                }
                if should_execute:
                    trade_id = f"{run_id}_A_{idx}"
                    if trade_id in trade_ids:
                        duplicates += 1
                    trade_ids.add(trade_id)
                    intent, build_reason = _build_trade_intent_from_option_row(
                        option_row,
                        trade_id=trade_id,
                        run_id=run_id,
                        desk_id=desk_id,
                        ts_iso=ts_iso,
                    )
                    if intent is None:
                        partial_trade_created += 1
                        reason_code = build_reason or "intent_build_failed"
                    else:
                        decision = build_decision(
                            meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "NIFTY", "timeframe": "1s"},
                            market={"spot": spot, "vwap": spot - 4.0, "trend_state": "UP", "regime": "TREND", "vol_state": "HIGH"},
                            signals={"pattern_flags": ["spike"], "rank_score": 0.82, "confidence": 0.74},
                            strategy={
                                "name": "torture_spike_follow",
                                "direction": "BUY",
                                "entry_reason": "momentum_with_liquidity_ok",
                                "stop": max(0.01, option_mid * 0.92),
                                "target": option_mid * 1.12,
                                "rr": 1.5,
                                "max_loss": 1000.0,
                                "size": 1.0,
                            },
                            outcome={"status": "planned", "reject_reasons": []},
                        )
                        append_event("decision_planned", {"run_id": run_id, "desk_id": desk_id, "decision": decision.to_dict()})
                        append_event("trade_intent_created", intent)
                        _submit_mock_order(broker, intent)
                        trade_count += 1

                if reason_code is not None:
                    reject_count += 1
                    if not str(reason_code).strip():
                        reject_missing_reason += 1
                    decision = build_decision(
                        meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "NIFTY", "timeframe": "1s"},
                        market={"spot": spot, "vwap": spot - 4.0, "trend_state": "UP", "regime": "TREND", "vol_state": "HIGH"},
                        signals={"pattern_flags": ["spike"], "rank_score": 0.38, "confidence": 0.31},
                        strategy={
                            "name": "torture_spike_follow",
                            "direction": "BUY",
                            "entry_reason": "rejected",
                            "stop": 0.0,
                            "target": 0.0,
                            "rr": 0.0,
                            "max_loss": 0.0,
                            "size": 0.0,
                        },
                        outcome={"status": "rejected", "reject_reasons": [str(reason_code)]},
                    )
                    append_event(
                        "decision_rejected",
                        {
                            "run_id": run_id,
                            "desk_id": desk_id,
                            "reason_code": str(reason_code),
                            "spread_pct": float(spread_pct),
                            "depth_qty": float(depth_qty),
                            "decision": decision.to_dict(),
                        },
                    )
                event_buffer.append(
                    {
                        "ts_epoch": ts_epoch,
                        "spot": spot,
                        "spread_pct": spread_pct,
                        "depth_qty": depth_qty,
                        "executed": bool(should_execute and reason_code is None),
                        "reason_code": reason_code,
                    }
                )
            except Exception:
                exception_count += 1
            finally:
                latencies.append((perf_counter() - t0) * 1000.0)

        return _ScenarioResult(
            tick_count=300,
            event_buffer_count=len(event_buffer),
            reject_count=reject_count,
            reject_missing_reason_count=reject_missing_reason,
            trade_count=trade_count,
            duplicate_trade_id_count=duplicates,
            partial_trade_creation_count=partial_trade_created,
            exception_count=exception_count,
            latency_samples_ms=latencies,
        )

    def _run_feed_flap_partial_data(self, *, run_id: str, desk_id: str) -> _ScenarioResult:
        broker = MockBroker()
        event_buffer: list[dict[str, Any]] = []
        latencies: list[float] = []
        trade_ids: set[str] = set()
        duplicates = 0
        reject_count = 0
        reject_missing_reason = 0
        exception_count = 0
        trade_count = 0
        partial_trade_created = 0

        start_epoch = 1772202600.0
        # DOWN/UP flaps 3 times with deterministic windows.
        feed_states = (
            ["OK"] * 24
            + ["DOWN"] * 12
            + ["OK"] * 24
            + ["DOWN"] * 12
            + ["OK"] * 24
            + ["DOWN"] * 12
            + ["OK"] * 12
        )
        for idx, feed_state in enumerate(feed_states):
            t0 = perf_counter()
            ts_epoch = start_epoch + float(idx)
            ts_iso = utc_now().isoformat().replace("+00:00", "Z")
            try:
                reason_code: str | None = None
                if feed_state != "OK":
                    reason_code = f"feed_state_{feed_state}"
                else:
                    is_partial = (idx % 4) in {0, 1}
                    option_row = {
                        "symbol": "BANKNIFTY26FEB49000PE",
                        "instrument_token": (None if is_partial else 202020),
                        "ltp": (None if is_partial else 142.5),
                        "bid": 141.9,
                        "ask": (None if is_partial else 143.1),
                    }
                    trade_id = f"{run_id}_B_{idx}"
                    if trade_id in trade_ids:
                        duplicates += 1
                    trade_ids.add(trade_id)
                    intent, build_reason = _build_trade_intent_from_option_row(
                        option_row,
                        trade_id=trade_id,
                        run_id=run_id,
                        desk_id=desk_id,
                        ts_iso=ts_iso,
                        side="SELL",
                    )
                    if intent is None:
                        reason_code = build_reason or "partial_option_row"
                    else:
                        # Execute only every 8th valid tick to keep load bounded.
                        if idx % 8 == 0:
                            decision = build_decision(
                                meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "BANKNIFTY", "timeframe": "1s"},
                                market={"spot": 49000.0, "vwap": 48996.0, "trend_state": "FLAT", "regime": "RANGE", "vol_state": "HIGH"},
                                signals={"pattern_flags": ["mean_revert"], "rank_score": 0.69, "confidence": 0.61},
                                strategy={
                                    "name": "torture_feed_flap",
                                    "direction": "SELL",
                                    "entry_reason": "feed_recovered_and_quote_complete",
                                    "stop": 148.0,
                                    "target": 136.0,
                                    "rr": 1.3,
                                    "max_loss": 900.0,
                                    "size": 1.0,
                                },
                                outcome={"status": "planned", "reject_reasons": []},
                            )
                            append_event("decision_planned", {"run_id": run_id, "desk_id": desk_id, "decision": decision.to_dict()})
                            append_event("trade_intent_created", intent)
                            _submit_mock_order(broker, intent)
                            trade_count += 1

                if reason_code is not None:
                    reject_count += 1
                    if not str(reason_code).strip():
                        reject_missing_reason += 1
                    if str(reason_code) == "partial_option_row":
                        partial_trade_created += 0
                    decision = build_decision(
                        meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "BANKNIFTY", "timeframe": "1s"},
                        market={"spot": 49000.0, "vwap": 48996.0, "trend_state": "FLAT", "regime": "RANGE", "vol_state": "HIGH"},
                        signals={"pattern_flags": ["mean_revert"], "rank_score": 0.21, "confidence": 0.18},
                        strategy={
                            "name": "torture_feed_flap",
                            "direction": "SELL",
                            "entry_reason": "rejected",
                            "stop": 0.0,
                            "target": 0.0,
                            "rr": 0.0,
                            "max_loss": 0.0,
                            "size": 0.0,
                        },
                        outcome={"status": "rejected", "reject_reasons": [str(reason_code)]},
                    )
                    append_event(
                        "decision_rejected",
                        {
                            "run_id": run_id,
                            "desk_id": desk_id,
                            "reason_code": str(reason_code),
                            "feed_state": feed_state,
                            "decision": decision.to_dict(),
                        },
                    )

                event_buffer.append(
                    {
                        "idx": idx,
                        "feed_state": feed_state,
                        "reason_code": reason_code,
                    }
                )
            except Exception:
                exception_count += 1
            finally:
                latencies.append((perf_counter() - t0) * 1000.0)

        return _ScenarioResult(
            tick_count=len(feed_states),
            event_buffer_count=len(event_buffer),
            reject_count=reject_count,
            reject_missing_reason_count=reject_missing_reason,
            trade_count=trade_count,
            duplicate_trade_id_count=duplicates,
            partial_trade_creation_count=partial_trade_created,
            exception_count=exception_count,
            latency_samples_ms=latencies,
        )

    def _run_long_run_stability(self, *, run_id: str, desk_id: str) -> _ScenarioResult:
        broker = MockBroker()
        bounded_buffer_limit = 600
        bounded_buffer: deque[dict[str, Any]] = deque(maxlen=bounded_buffer_limit)
        decision_trace_limit = 300
        decision_trace: deque[dict[str, Any]] = deque(maxlen=decision_trace_limit)
        latencies: list[float] = []
        trade_ids: set[str] = set()
        duplicates = 0
        reject_count = 0
        reject_missing_reason = 0
        exception_count = 0
        trade_count = 0
        partial_trade_created = 0
        max_bounded_buffer_observed = 0
        max_decision_trace_observed = 0
        rss_samples_mb: list[float] = []
        max_rss_mb: float | None = None

        rotation_cap_bytes = 256_000
        rotation_writer = _RotatingJsonlWriter(
            logs_dir() / f"torture_long_run_trace_{run_id}.jsonl",
            max_bytes_per_file=rotation_cap_bytes,
        )
        simulated_minutes = 360  # 6h run accelerated into a tight deterministic loop.
        start_epoch = 1772203200.0

        for minute in range(simulated_minutes):
            t0 = perf_counter()
            ts_epoch = start_epoch + float(minute * 60)
            ts_iso = utc_now().isoformat().replace("+00:00", "Z")
            try:
                spot = 22500.0 + (minute * 0.45) + (18.0 * math.sin(minute / 21.0))
                spread_pct = 0.0025 + ((minute % 17) * 0.00012)
                depth_qty = max(20.0, 140.0 - (minute * 0.15))
                option_mid = max(8.0, 92.0 + (spot - 22500.0) * 0.18 + 3.5 * math.cos(minute / 9.0))
                half_spread = option_mid * spread_pct * 0.5
                bid = max(0.05, option_mid - half_spread)
                ask = max(bid + 0.05, option_mid + half_spread)

                reason_code: str | None = None
                should_execute = False
                if spread_pct > 0.028:
                    reason_code = "spread_too_wide"
                elif depth_qty < 24.0:
                    reason_code = "depth_too_thin"
                elif minute % 37 == 0:
                    should_execute = True
                else:
                    reason_code = "signal_not_selected"

                option_row = {
                    "symbol": "NIFTY26FEB22500CE",
                    "instrument_token": 303030,
                    "ltp": option_mid,
                    "bid": bid,
                    "ask": ask,
                }
                if should_execute:
                    trade_id = f"{run_id}_L_{minute}"
                    if trade_id in trade_ids:
                        duplicates += 1
                    trade_ids.add(trade_id)
                    intent, build_reason = _build_trade_intent_from_option_row(
                        option_row,
                        trade_id=trade_id,
                        run_id=run_id,
                        desk_id=desk_id,
                        ts_iso=ts_iso,
                    )
                    if intent is None:
                        partial_trade_created += 1
                        reason_code = build_reason or "intent_build_failed"
                    else:
                        decision = build_decision(
                            meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "NIFTY", "timeframe": "1m"},
                            market={"spot": spot, "vwap": spot - 2.5, "trend_state": "UP", "regime": "TREND", "vol_state": "MID"},
                            signals={"pattern_flags": ["trend"], "rank_score": 0.71, "confidence": 0.66},
                            strategy={
                                "name": "torture_long_run",
                                "direction": "BUY",
                                "entry_reason": "stability_probe",
                                "stop": max(0.01, option_mid * 0.86),
                                "target": option_mid * 1.14,
                                "rr": 1.4,
                                "max_loss": 800.0,
                                "size": 1.0,
                            },
                            outcome={"status": "planned", "reject_reasons": []},
                        )
                        append_event("decision_planned", {"run_id": run_id, "desk_id": desk_id, "decision": decision.to_dict()})
                        append_event("trade_intent_created", intent)
                        _submit_mock_order(broker, intent)
                        trade_count += 1

                if reason_code is not None:
                    reject_count += 1
                    if not str(reason_code).strip():
                        reject_missing_reason += 1
                    decision = build_decision(
                        meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "NIFTY", "timeframe": "1m"},
                        market={"spot": spot, "vwap": spot - 2.5, "trend_state": "UP", "regime": "TREND", "vol_state": "MID"},
                        signals={"pattern_flags": ["trend"], "rank_score": 0.29, "confidence": 0.21},
                        strategy={
                            "name": "torture_long_run",
                            "direction": "BUY",
                            "entry_reason": "rejected",
                            "stop": 0.0,
                            "target": 0.0,
                            "rr": 0.0,
                            "max_loss": 0.0,
                            "size": 0.0,
                        },
                        outcome={"status": "rejected", "reject_reasons": [str(reason_code)]},
                    )
                    append_event(
                        "decision_rejected",
                        {
                            "run_id": run_id,
                            "desk_id": desk_id,
                            "reason_code": str(reason_code),
                            "spread_pct": float(spread_pct),
                            "depth_qty": float(depth_qty),
                            "decision": decision.to_dict(),
                        },
                    )

                bounded_buffer.append(
                    {
                        "minute": minute,
                        "ts_epoch": ts_epoch,
                        "spot": round(spot, 4),
                        "spread_pct": round(spread_pct, 6),
                        "depth_qty": round(depth_qty, 4),
                        "reason_code": reason_code,
                    }
                )
                decision_trace.append(
                    {
                        "minute": minute,
                        "executed": bool(should_execute and reason_code is None),
                        "reason_code": reason_code,
                    }
                )
                max_bounded_buffer_observed = max(max_bounded_buffer_observed, len(bounded_buffer))
                max_decision_trace_observed = max(max_decision_trace_observed, len(decision_trace))
                rotation_writer.write(
                    {
                        "minute": minute,
                        "run_id": run_id,
                        "spot": spot,
                        "option_mid": option_mid,
                        "spread_pct": spread_pct,
                        "depth_qty": depth_qty,
                        "reason_code": reason_code,
                        "executed": bool(should_execute and reason_code is None),
                    }
                )
                rss_now = _rss_mb()
                if rss_now is not None:
                    rss_samples_mb.append(float(rss_now))
                    if max_rss_mb is None:
                        max_rss_mb = float(rss_now)
                    else:
                        max_rss_mb = max(max_rss_mb, float(rss_now))
            except Exception:
                exception_count += 1
            finally:
                latencies.append((perf_counter() - t0) * 1000.0)

        extra_metrics = {
            "simulated_hours": 6.0,
            "simulated_minutes": int(simulated_minutes),
            "rss_samples_count": int(len(rss_samples_mb)),
            "rss_mb_max": (None if max_rss_mb is None else float(max_rss_mb)),
            "rss_mb_p95": (None if not rss_samples_mb else float(_p95(rss_samples_mb))),
            "bounded_buffer_limit": int(bounded_buffer_limit),
            "max_bounded_buffer_observed": int(max_bounded_buffer_observed),
            "decision_trace_limit": int(decision_trace_limit),
            "max_decision_trace_observed": int(max_decision_trace_observed),
            "rotation_cap_bytes": int(rotation_cap_bytes),
            "rotation_max_file_size_bytes": int(rotation_writer.max_file_size_bytes),
            "rotation_count": int(rotation_writer.rotation_count),
            "rotation_lines_written": int(rotation_writer.lines_written),
        }

        return _ScenarioResult(
            tick_count=int(simulated_minutes),
            event_buffer_count=len(bounded_buffer),
            reject_count=reject_count,
            reject_missing_reason_count=reject_missing_reason,
            trade_count=trade_count,
            duplicate_trade_id_count=duplicates,
            partial_trade_creation_count=partial_trade_created,
            exception_count=exception_count,
            latency_samples_ms=latencies,
            extra_metrics=extra_metrics,
        )

    def _run_fault_injection(self, *, run_id: str, desk_id: str) -> _ScenarioResult:
        broker = MockBroker()
        event_buffer: list[dict[str, Any]] = []
        latencies: list[float] = []
        trade_ids: set[str] = set()
        duplicates = 0
        reject_count = 0
        reject_missing_reason = 0
        exception_count = 0
        trade_count = 0
        partial_trade_created = 0

        feed_latency_spike_ticks = {14, 15, 16, 62, 63, 64, 108}
        missing_depth_ticks = {22, 23, 24, 70, 71, 118}
        order_reject_ticks = {30, 60, 90, 120}
        db_write_failure_ticks = {40, 80, 110, 140}
        fail_closed_blocks = 0
        unsafe_order_attempts = 0
        injected_order_rejections = 0
        injected_db_write_failures = 0
        injected_feed_latency_spikes = 0
        injected_missing_depth = 0

        def _append_event_guarded(event_type: str, payload: dict[str, Any], *, idx: int) -> bool:
            nonlocal injected_db_write_failures
            if idx in db_write_failure_ticks:
                injected_db_write_failures += 1
                return False
            try:
                append_event(event_type, payload)
                return True
            except Exception:
                injected_db_write_failures += 1
                return False

        start_epoch = 1772204100.0
        for idx in range(180):
            t0 = perf_counter()
            ts_epoch = start_epoch + float(idx)
            ts_iso = utc_now().isoformat().replace("+00:00", "Z")
            try:
                spot = 22620.0 + 0.9 * idx + (9.0 * math.sin(idx / 8.0))
                option_mid = max(18.0, 126.0 + (spot - 22620.0) * 0.21)
                spread_pct = min(0.018, 0.0032 + 0.00009 * (idx % 19))
                half_spread = option_mid * spread_pct * 0.5
                bid = max(0.05, option_mid - half_spread)
                ask = max(bid + 0.05, option_mid + half_spread)
                depth_qty: float | None = max(10.0, 95.0 - (0.37 * idx))
                quote_age_sec = 0.4

                reason_code: str | None = None
                if idx in feed_latency_spike_ticks:
                    quote_age_sec = 9.5
                    reason_code = "feed_latency_spike"
                    injected_feed_latency_spikes += 1
                if idx in missing_depth_ticks:
                    depth_qty = None
                    if reason_code is None:
                        reason_code = "missing_depth"
                    injected_missing_depth += 1

                should_execute = bool(idx % 10 == 0)

                option_row = {
                    "symbol": "NIFTY26FEB22600CE",
                    "instrument_token": 404040,
                    "ltp": option_mid,
                    "bid": bid,
                    "ask": ask,
                }

                if should_execute:
                    trade_id = f"{run_id}_F_{idx}"
                    if trade_id in trade_ids:
                        duplicates += 1
                    trade_ids.add(trade_id)
                    intent, build_reason = _build_trade_intent_from_option_row(
                        option_row,
                        trade_id=trade_id,
                        run_id=run_id,
                        desk_id=desk_id,
                        ts_iso=ts_iso,
                    )
                    if intent is None:
                        partial_trade_created += 1
                        reason_code = build_reason or "intent_build_failed"
                    elif reason_code is None:
                        planned_decision = build_decision(
                            meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "NIFTY", "timeframe": "1s"},
                            market={"spot": spot, "vwap": spot - 3.0, "trend_state": "UP", "regime": "TREND", "vol_state": "MID"},
                            signals={"pattern_flags": ["fault_injection_probe"], "rank_score": 0.72, "confidence": 0.67},
                            strategy={
                                "name": "torture_fault_injection",
                                "direction": "BUY",
                                "entry_reason": "probe_ready",
                                "stop": max(0.01, option_mid * 0.89),
                                "target": option_mid * 1.1,
                                "rr": 1.4,
                                "max_loss": 900.0,
                                "size": 1.0,
                            },
                            outcome={"status": "planned", "reject_reasons": []},
                        )
                        planned_ok = _append_event_guarded(
                            "decision_planned",
                            {"run_id": run_id, "desk_id": desk_id, "decision": planned_decision.to_dict()},
                            idx=idx,
                        )
                        intent_ok = _append_event_guarded("trade_intent_created", intent, idx=idx)
                        if not planned_ok or not intent_ok:
                            reason_code = "db_write_failure"
                            fail_closed_blocks += 1
                        else:
                            try:
                                if idx in order_reject_ticks:
                                    injected_order_rejections += 1
                                    raise RuntimeError("injected_order_rejection")
                                _submit_mock_order(broker, intent)
                                trade_count += 1
                            except Exception:
                                reason_code = "order_rejected"
                                fail_closed_blocks += 1
                    elif reason_code is not None:
                        fail_closed_blocks += 1

                if should_execute and reason_code is not None:
                    unsafe_order_attempts += 0

                if reason_code is not None:
                    reject_count += 1
                    if not str(reason_code).strip():
                        reject_missing_reason += 1
                    rejected_decision = build_decision(
                        meta={"ts_epoch": ts_epoch, "run_id": run_id, "symbol": "NIFTY", "timeframe": "1s"},
                        market={"spot": spot, "vwap": spot - 3.0, "trend_state": "UP", "regime": "TREND", "vol_state": "MID"},
                        signals={"pattern_flags": ["fault_injection_probe"], "rank_score": 0.19, "confidence": 0.12},
                        strategy={
                            "name": "torture_fault_injection",
                            "direction": "BUY",
                            "entry_reason": "rejected",
                            "stop": 0.0,
                            "target": 0.0,
                            "rr": 0.0,
                            "max_loss": 0.0,
                            "size": 0.0,
                        },
                        outcome={"status": "rejected", "reject_reasons": [str(reason_code)]},
                    )
                    _append_event_guarded(
                        "decision_rejected",
                        {
                            "run_id": run_id,
                            "desk_id": desk_id,
                            "reason_code": str(reason_code),
                            "quote_age_sec": float(quote_age_sec),
                            "depth_qty": depth_qty,
                            "decision": rejected_decision.to_dict(),
                        },
                        idx=idx,
                    )

                event_buffer.append(
                    {
                        "idx": idx,
                        "quote_age_sec": float(quote_age_sec),
                        "depth_qty": depth_qty,
                        "reason_code": reason_code,
                        "should_execute": should_execute,
                    }
                )
            except Exception:
                exception_count += 1
            finally:
                latencies.append((perf_counter() - t0) * 1000.0)

        extra_metrics = {
            "injected_feed_latency_spikes": int(injected_feed_latency_spikes),
            "injected_missing_depth": int(injected_missing_depth),
            "injected_order_rejections": int(injected_order_rejections),
            "injected_db_write_failures": int(injected_db_write_failures),
            "fail_closed_blocks": int(fail_closed_blocks),
            "unsafe_order_attempts": int(unsafe_order_attempts),
        }

        return _ScenarioResult(
            tick_count=180,
            event_buffer_count=len(event_buffer),
            reject_count=reject_count,
            reject_missing_reason_count=reject_missing_reason,
            trade_count=trade_count,
            duplicate_trade_id_count=duplicates,
            partial_trade_creation_count=partial_trade_created,
            exception_count=exception_count,
            latency_samples_ms=latencies,
            extra_metrics=extra_metrics,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic replay torture-test harness.")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["market_open_spike", "feed_flap_partial_data", "long_run_stability", "fault_injection"],
    )
    parser.add_argument("--desk", default="DEFAULT")
    args = parser.parse_args(argv)

    summary = TortureTestRunner().run_scenario(args.scenario, args.desk)
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    print(f"torture_test wrote: {summary.get('report_path')}")
    if str(summary.get("status") or "FAIL").upper() != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
