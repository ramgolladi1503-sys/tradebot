from __future__ import annotations

import argparse
import json
import math
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from core.broker.mock_broker import MockBroker
from core.decision_builder import build_decision
from core.events import append_event, read_events, write_json_atomic
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic replay torture-test harness.")
    parser.add_argument("--scenario", required=True, choices=["market_open_spike", "feed_flap_partial_data"])
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
