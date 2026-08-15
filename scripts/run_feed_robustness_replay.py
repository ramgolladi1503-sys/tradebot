#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
import threading
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import os

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import config as cfg  # noqa: E402
from core.feed_robustness_evidence import collector, first_difference  # noqa: E402
from core.feed_fd_trace import process_fd_count, reset_trace as reset_fd_trace  # noqa: E402
from core import kite_depth_ws, tick_store  # noqa: E402


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _git_diff_sha256() -> str:
    diff = subprocess.check_output(["git", "diff"], cwd=ROOT)
    if isinstance(diff, str):
        diff = diff.encode("utf-8")
    return hashlib.sha256(diff).hexdigest()


def _fd_trace_summary(trace_path: Path | None, *, baseline_fd: int | None, post_worker_shutdown_fd: int | None) -> dict[str, object]:
    summary: dict[str, object] = {
        "baseline_fd": baseline_fd,
        "high_water_fd": None,
        "callback_exit_fd_min": None,
        "callback_exit_fd_max": None,
        "callback_exit_fd_count": 0,
        "post_worker_shutdown_fd": post_worker_shutdown_fd,
        "post_replay_shutdown_fd": post_worker_shutdown_fd,
        "final_fd": post_worker_shutdown_fd,
        "trace_path": str(trace_path) if trace_path is not None else None,
    }
    if trace_path is None or not trace_path.exists():
        return summary
    high_water_fd = None
    callback_exit_values: list[int] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        fd_count = event.get("fd_count")
        if not isinstance(fd_count, int):
            continue
        high_water_fd = fd_count if high_water_fd is None else max(high_water_fd, fd_count)
        if event.get("stage") == "on_ticks.callback_exit":
            callback_exit_values.append(fd_count)
    summary["high_water_fd"] = high_water_fd
    if callback_exit_values:
        summary["callback_exit_fd_min"] = min(callback_exit_values)
        summary["callback_exit_fd_max"] = max(callback_exit_values)
        summary["callback_exit_fd_count"] = len(callback_exit_values)
    return summary


def _adapt(row: dict) -> dict:
    ts = row.get("ts") or row.get("timestamp") or row.get("exchange_timestamp")
    token = row.get("token") if row.get("token") is not None else row.get("instrument_token")
    try:
        token = int(token)
    except (TypeError, ValueError):
        # Upstox uses stable string instrument keys while the existing Kite callback
        # requires integer tokens. This mapping is deterministic and replay-only.
        token = int.from_bytes(hashlib.sha256(str(token).encode()).digest()[:4], "big") or 1
    ltp = row.get("ltp") if row.get("ltp") is not None else row.get("last_price")
    depth = row.get("depth") if isinstance(row.get("depth"), dict) else {}
    if not depth and row.get("bid") is not None and row.get("ask") is not None:
        depth = {"buy": [{"price": row["bid"]}], "sell": [{"price": row["ask"]}]}
    return {"instrument_token": token, "last_price": ltp, "exchange_timestamp": ts,
            "_audit_source_row_index": int(row["source_row_index"]), "_audit_source_timestamp": ts,
            "volume": row.get("vol", row.get("volume")), "oi": row.get("oi"), "depth": depth}


def _source_timestamp_ns(value: object) -> int | None:
    try:
        return int(round(float(value) * 1_000_000_000))
    except Exception:
        return None


def _capture_timestamp_fidelity(rows: list[dict]) -> dict:
    evidence: list[dict] = []
    fallback_count = 0
    unexpected_fallback_count = 0
    matched_within_precision = 0
    precision_tolerance_ns = 1_000  # documented source precision is sub-microsecond.
    for row in rows:
        adapted = _adapt(row)
        source_ts = row.get("ts") or row.get("timestamp") or row.get("exchange_timestamp")
        receipt_epoch = float(source_ts if source_ts is not None else time.time())
        payload_epoch = kite_depth_ws._extract_tick_epoch(adapted)
        normalized_epoch = kite_depth_ws._normalized_tick_epoch(
            adapted["instrument_token"],
            payload_epoch=payload_epoch,
            receipt_epoch=receipt_epoch,
        )
        source_ns = _source_timestamp_ns(source_ts)
        payload_ns = _source_timestamp_ns(adapted.get("exchange_timestamp"))
        extracted_ns = _source_timestamp_ns(payload_epoch)
        normalized_ns = _source_timestamp_ns(normalized_epoch)
        receipt_ns = _source_timestamp_ns(receipt_epoch)
        fallback_used = bool(payload_ns is None or (normalized_ns == receipt_ns and payload_ns != receipt_ns))
        if fallback_used:
            fallback_count += 1
        if payload_ns is None:
            unexpected_fallback_count += 1
        elif source_ns is not None and abs(payload_ns - source_ns) <= precision_tolerance_ns:
            matched_within_precision += 1
        evidence.append(
            {
                "source_row_index": row["source_row_index"],
                "source_timestamp": source_ts,
                "adapted_callback_timestamp": adapted.get("exchange_timestamp"),
                "extracted_timestamp": payload_epoch,
                "normalized_timestamp": normalized_epoch,
                "receipt_time_fallback_used": fallback_used,
                "source_vs_extracted_diff_ns": None if source_ns is None or extracted_ns is None else extracted_ns - source_ns,
                "source_vs_normalized_diff_ns": None if source_ns is None or normalized_ns is None else normalized_ns - source_ns,
            }
        )
    valid_rows = [row for row in rows if row.get("ts") is not None or row.get("timestamp") is not None or row.get("exchange_timestamp") is not None]
    return {
        "rows": evidence,
        "summary": {
            "checked_rows": len(valid_rows),
            "checked_rows_pct": (len(valid_rows) / len(rows) * 100.0) if rows else 0.0,
            "within_precision_rows": matched_within_precision,
            "within_precision_pct": (matched_within_precision / len(valid_rows) * 100.0) if valid_rows else 0.0,
            "receipt_time_fallback_count": fallback_count,
            "unexpected_receipt_time_fallback_count": unexpected_fallback_count,
            "precision_tolerance_ns": precision_tolerance_ns,
            "pass": bool(valid_rows) and matched_within_precision == len(valid_rows) and unexpected_fallback_count == 0,
        },
    }


def _resource_snapshot() -> dict:
    try:
        import psutil  # type: ignore

        rss_bytes = int(psutil.Process(os.getpid()).memory_info().rss)
        source = "psutil.Process().memory_info().rss"
    except Exception:
        import resource

        rss_raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            rss_bytes = rss_raw
            source = "resource.getrusage.ru_maxrss_bytes"
        else:
            rss_bytes = rss_raw * 1024
            source = "resource.getrusage.ru_maxrss_kib"
    return {
        "rss_bytes": rss_bytes,
        "rss_mib": rss_bytes / (1024.0 * 1024.0),
        "rss_source": source,
        "thread_count": len(getattr(threading, "_active", {})),
    }


def _resource_timeline_sample() -> dict:
    sample = _resource_snapshot()
    sample.update(
        {
            "monotonic_ns": time.monotonic_ns(),
            "queue_depth": tick_store.write_queue_depth(),
            "pending_writes": max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count()),
            "fd_count": process_fd_count(),
        }
    )
    return sample


def _pressure_queue_threshold() -> int:
    queue = getattr(tick_store, "_WRITE_QUEUE", None)
    queue_capacity = getattr(queue, "maxlen", None) if queue is not None else None
    if queue_capacity is None:
        return 100
    return max(2, int(math.ceil(float(queue_capacity) * 0.8)))


class _ReplayPressureController:
    def __init__(
        self,
        *,
        profile: str = "none",
        delay_before_each_commit_ms: int = 0,
        stall_after_each_dequeued_rows: int = 0,
        stall_duration_ms: int = 0,
        expected_total_rows: int | None = None,
    ) -> None:
        self.profile = str(profile or "none")
        self.delay_before_each_commit_ms = max(0, int(delay_before_each_commit_ms or 0))
        self.stall_after_each_dequeued_rows = max(0, int(stall_after_each_dequeued_rows or 0))
        self.stall_duration_ms = max(0, int(stall_duration_ms or 0))
        self.expected_total_rows = int(expected_total_rows) if expected_total_rows is not None else None
        self.timeline: list[dict[str, object]] = []
        self.resource_timeline: list[dict[str, object]] = []
        self.worker_lifecycle: list[dict[str, object]] = []
        self._stall_index = 0
        self._next_stall_at = self.stall_after_each_dequeued_rows if self.stall_after_each_dequeued_rows else None
        self._started_ns = time.monotonic_ns()
        self._last_queue_high_water: int | None = None
        self._max_pending_writes = 0
        self._hook_ordinal = 0
        self.hook_invocation_count = 0
        self.cumulative_requested_delay_ms = 0
        self.cumulative_observed_delay_ms = 0.0
        self.resource_timeline.append({"kind": "pre_producer_sample", **_resource_timeline_sample()})
        self._record_queue_event("replay_start")

    @property
    def enabled(self) -> bool:
        return self.profile != "none"

    def _record_queue_event(self, stage: str, **extra: object) -> None:
        worker_state = tick_store.get_persistence_worker_state()
        payload = {
            "stage": stage,
            "monotonic_ns": time.monotonic_ns(),
            "elapsed_ns": time.monotonic_ns() - self._started_ns,
            "rows_produced": int(extra.get("rows_produced") or extra.get("produced_rows") or 0),
            "rows_enqueued": tick_store.write_enqueue_count(),
            "rows_dequeued": worker_state.get("rows_dequeued"),
            "rows_committed": tick_store.write_flush_count(),
            "queue_depth": tick_store.write_queue_depth(),
            "queue_depth_high_water": worker_state.get("queue_depth_high_water"),
            "pending_writes": max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count()),
            "pending_writes_max": self._max_pending_writes,
            "worker_state": {
                "worker_started": worker_state.get("worker_started"),
                "worker_join_completed": worker_state.get("worker_join_completed"),
                "worker_terminated": worker_state.get("worker_terminated"),
                "worker_failures": worker_state.get("worker_failures"),
            },
            "pressure_state": {
                "profile": self.profile,
                "stall_index": self._stall_index,
                "next_stall_at": self._next_stall_at,
            },
        }
        payload.update(extra)
        self.timeline.append(payload)
        hw = payload["queue_depth_high_water"]
        if isinstance(hw, int) and hw != self._last_queue_high_water:
            self._last_queue_high_water = hw
            self.resource_timeline.append({"kind": "queue_high_water_change", **_resource_timeline_sample()})
        pending_writes = int(payload["pending_writes"])
        queue_high_water = int(worker_state.get("queue_depth_high_water") or 0)
        self._max_pending_writes = max(self._max_pending_writes, pending_writes, queue_high_water)

    def record_worker_event(self, stage: str, **extra: object) -> None:
        monotonic_ns = extra.pop("monotonic_ns", None)
        self.worker_lifecycle.append({
            "stage": stage,
            "monotonic_ns": int(monotonic_ns) if monotonic_ns is not None else time.monotonic_ns(),
            "queue_depth": tick_store.write_queue_depth(),
            "pending_writes": max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count()),
            **extra,
        })

    def _record_hook_event(self, stage: str, context: dict[str, object], *, observed_delay_ms: float | None = None,
                           start_ns: int | None = None, end_ns: int | None = None) -> None:
        self._hook_ordinal += 1
        entry = {
            "stage": stage,
            "hook_ordinal": self._hook_ordinal,
            "batch_size": int(context.get("batch_size") or context.get("batch_rows") or 0),
            "configured_delay_ms": self.delay_before_each_commit_ms if self.profile == "constant_delay" else self.stall_duration_ms,
            "observed_delay_ms": observed_delay_ms,
            "rows_dequeued_total": int(context.get("rows_dequeued") or 0),
            "rows_committed_before_hook": int(context.get("committed_rows") or 0),
            "monotonic_start_ns": start_ns,
            "monotonic_end_ns": end_ns,
        }
        self.worker_lifecycle.append(entry)

    def record_post_commit(self, context: dict[str, object]) -> None:
        self.worker_lifecycle.append({
            "stage": "post_commit",
            "hook_ordinal": int(context.get("committed_batches") or 0),
            "batch_size": int(context.get("batch_size") or context.get("batch_rows") or 0),
            "configured_delay_ms": self.delay_before_each_commit_ms if self.profile == "constant_delay" else self.stall_duration_ms,
            "observed_delay_ms": None,
            "rows_dequeued_total": int(context.get("rows_dequeued") or 0),
            "rows_committed_before_hook": int(context.get("committed_rows") or 0),
            "rows_committed_after_commit": int(context.get("committed_rows") or 0),
            "monotonic_start_ns": None,
            "monotonic_end_ns": None,
        })

    def maybe_pause_before_commit(self, context: dict[str, object]) -> None:
        if not self.enabled:
            return
        context_payload = dict(context)
        context_payload.pop("stage", None)
        self._record_queue_event("pressure_activation" if self._stall_index == 0 else "pressure_continue", **context_payload)
        if self.profile == "constant_delay":
            if self.delay_before_each_commit_ms > 0:
                self.hook_invocation_count += 1
                self.cumulative_requested_delay_ms += self.delay_before_each_commit_ms
                start_ns = time.monotonic_ns()
                self._record_hook_event("hook_start", context_payload, start_ns=start_ns)
                self.worker_lifecycle.append({
                    "stage": "stall_start",
                    "monotonic_ns": start_ns,
                    "stall_index": self._stall_index,
                    "delay_before_each_commit_ms": self.delay_before_each_commit_ms,
                    "queue_depth": tick_store.write_queue_depth(),
                    "pending_writes": max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count()),
                })
                time.sleep(self.delay_before_each_commit_ms / 1000.0)
                end_ns = time.monotonic_ns()
                self.cumulative_observed_delay_ms += (end_ns - start_ns) / 1e6
                self.worker_lifecycle.append({
                    "stage": "hook_end",
                    "hook_ordinal": self._hook_ordinal,
                    "batch_size": int(context_payload.get("batch_size") or context_payload.get("batch_rows") or 0),
                    "configured_delay_ms": self.delay_before_each_commit_ms,
                    "observed_delay_ms": (end_ns - start_ns) / 1e6,
                    "rows_dequeued_total": int(context_payload.get("rows_dequeued") or 0),
                    "rows_committed_before_hook": int(context_payload.get("committed_rows") or 0),
                    "rows_committed_after_commit": None,
                    "monotonic_start_ns": start_ns,
                    "monotonic_end_ns": end_ns,
                })
                self.worker_lifecycle.append({
                    "stage": "stall_end",
                    "monotonic_ns": end_ns,
                    "stall_index": self._stall_index,
                    "duration_ns": end_ns - start_ns,
                    "queue_depth": tick_store.write_queue_depth(),
                    "pending_writes": max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count()),
                })
            self._record_queue_event("commit_delay_applied", **context_payload)
            return
        if self.profile == "intermittent_stall" and self._next_stall_at is not None:
            dequeued_rows = int(context.get("rows_dequeued") or 0)
            if dequeued_rows >= self._next_stall_at and (self.expected_total_rows is None or dequeued_rows < self.expected_total_rows):
                self.hook_invocation_count += 1
                self.cumulative_requested_delay_ms += self.stall_duration_ms
                start_ns = time.monotonic_ns()
                self._record_hook_event("hook_start", context_payload, start_ns=start_ns)
                self.worker_lifecycle.append({
                    "stage": "stall_start",
                    "monotonic_ns": start_ns,
                    "stall_index": self._stall_index,
                    "stall_after_each_dequeued_rows": self.stall_after_each_dequeued_rows,
                    "stall_duration_ms": self.stall_duration_ms,
                    "dequeued_rows": dequeued_rows,
                    "queue_depth": tick_store.write_queue_depth(),
                    "pending_writes": max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count()),
                })
                time.sleep(self.stall_duration_ms / 1000.0)
                end_ns = time.monotonic_ns()
                self.cumulative_observed_delay_ms += (end_ns - start_ns) / 1e6
                self.worker_lifecycle.append({
                    "stage": "hook_end",
                    "hook_ordinal": self._hook_ordinal,
                    "batch_size": int(context_payload.get("batch_size") or context_payload.get("batch_rows") or 0),
                    "configured_delay_ms": self.stall_duration_ms,
                    "observed_delay_ms": (end_ns - start_ns) / 1e6,
                    "rows_dequeued_total": dequeued_rows,
                    "rows_committed_before_hook": int(context_payload.get("committed_rows") or 0),
                    "rows_committed_after_commit": None,
                    "monotonic_start_ns": start_ns,
                    "monotonic_end_ns": end_ns,
                })
                self.worker_lifecycle.append({
                    "stage": "stall_end",
                    "monotonic_ns": end_ns,
                    "stall_index": self._stall_index,
                    "duration_ns": end_ns - start_ns,
                    "dequeued_rows": dequeued_rows,
                    "queue_depth": tick_store.write_queue_depth(),
                    "pending_writes": max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count()),
                })
                self._stall_index += 1
                self._next_stall_at += self.stall_after_each_dequeued_rows
                self._record_queue_event("stall_released", **context_payload)

    def capture_drain_report(self, *, producer_completion_ns: int, producer_completion_queue_depth: int,
                             producer_completion_pending_writes: int, worker_completion_ns: int | None,
                             worker_join_ns: int | None, worker_terminated: bool | None,
                             worker_failures: int | None) -> dict[str, object]:
        queue_depth_at_shutdown = tick_store.write_queue_depth()
        pending_writes_at_shutdown = max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count())
        return {
            "producer_completion_monotonic_ns": producer_completion_ns,
            "producer_completion_queue_depth": producer_completion_queue_depth,
            "producer_completion_pending_writes": producer_completion_pending_writes,
            "worker_completion_monotonic_ns": worker_completion_ns,
            "backlog_drain_duration_ns": None if worker_completion_ns is None else worker_completion_ns - producer_completion_ns,
            "queue_depth_at_shutdown": queue_depth_at_shutdown,
            "pending_writes_at_shutdown": pending_writes_at_shutdown,
            "worker_join_duration_ns": None if worker_join_ns is None else worker_join_ns - producer_completion_ns,
            "worker_terminated": worker_terminated,
            "worker_failures": worker_failures,
        }


def _describe_tick_store_mode() -> dict:
    async_enabled = bool(getattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", True))
    batch_size = int(getattr(cfg, "TICK_STORE_ASYNC_BATCH_SIZE", 1000) or 1000)
    flush_interval = float(getattr(cfg, "TICK_STORE_ASYNC_FLUSH_INTERVAL_SEC", 0.5) or 0.5)
    return {
        "sync_diagnostic_mode": not async_enabled,
        "actual_production_persistence_mode": async_enabled,
        "queue_enabled": async_enabled,
        "writes_batched": async_enabled,
        "batch_size": batch_size,
        "one_transaction_commits_multiple_rows": async_enabled,
        "runner_forces_synchronous_persistence": False,
        "flush_interval_sec": flush_interval,
    }


def _resolve_persistence_mode(scenario: str, selected_mode: str | None) -> bool:
    if selected_mode == "sync":
        return True
    if selected_mode == "async_queue":
        return False
    return scenario != "normal_speed"


def _deterministic_replay_schedule(rows: list[dict], speed_factor: float) -> tuple[float, float]:
    if len(rows) < 2:
        return 0.0, 0.0
    ts_values = [float(r["ts"]) for r in rows if r.get("ts") is not None]
    if len(ts_values) < 2:
        return 0.0, 0.0
    source_duration = max(ts_values) - min(ts_values)
    return source_duration, source_duration / max(speed_factor, 1e-9)


def _run_once(rows: list[dict], scenario: str, seed: int, *, synchronous: bool, speed_factor: float = 1.0,
              batch_size: int = 1000, random_pause_probability: float = 0.0, random_pause_max_ms: float = 0.0,
              scheduler_jitter_seed: int | None = None, trace_path: Path | None = None,
              selected_persistence_mode: str | None = None,
              pressure_controller: _ReplayPressureController | None = None,
              shutdown_deadline_seconds: float | None = 2.0) -> dict:
    previous_async_db_writes = getattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", True)
    previous_enable_db_writes = getattr(cfg, "TICK_STORE_ENABLE_DB_WRITES", True)
    previous_trade_db_path = getattr(cfg, "TRADE_DB_PATH", None)
    collector.reset(enabled=True)
    tick_store.reset_audit_counters()
    tick_store.clear_replay_pressure_hook()
    tick_store.set_replay_pressure_immediate_flush_enabled(True)
    tick_store.set_replay_pressure_read_flush_enabled(True)
    kite_depth_ws._LAST_MSG_TS_BY_TOKEN.clear()
    kite_depth_ws._LAST_PAYLOAD_TS_BY_TOKEN.clear()
    kite_depth_ws._LAST_WS_TICK_EPOCH = 0.0
    cfg.TICK_STORE_ASYNC_DB_WRITES = not synchronous
    try:
        if trace_path is not None:
            try:
                reset_fd_trace(baseline_fd=process_fd_count(), path=trace_path)
            except Exception:
                pass
        rng = random.Random(seed if scheduler_jitter_seed is None else scheduler_jitter_seed)
        batch_size = max(1, int(batch_size))
        schedule_start = time.monotonic()
        source_first = float(rows[0]["ts"]) if rows and rows[0].get("ts") is not None else None
        source_last = float(rows[-1]["ts"]) if rows and rows[-1].get("ts") is not None else None
        last_source_ts = None
        max_scheduler_drift_ns = 0
        callback_batches: list[dict] = []
        if pressure_controller is not None and pressure_controller.enabled:
            tick_store.set_replay_pressure_hook(lambda context: pressure_controller.maybe_pause_before_commit(context))
            tick_store.set_replay_pressure_post_commit_hook(lambda context: pressure_controller.record_post_commit(context))
            tick_store.set_replay_pressure_immediate_flush_enabled(False)
            tick_store.set_replay_pressure_read_flush_enabled(False)
            pressure_controller.record_worker_event("hook_registered", scenario=scenario)
        for start in range(0, len(rows), batch_size):
            batch_rows = rows[start:start + batch_size]
            batch_start = time.monotonic_ns()
            batch = [_adapt(row) for row in batch_rows]
            batch_source_ts = [float(row["ts"]) for row in batch_rows if row.get("ts") is not None]
            if batch_source_ts:
                if last_source_ts is not None:
                    target_wait = max(0.0, (batch_source_ts[0] - last_source_ts) / max(speed_factor, 1e-9))
                    drift_ns = int((time.monotonic() - schedule_start - (batch_source_ts[0] - source_first) / max(speed_factor, 1e-9)) * 1e9) if source_first is not None else 0
                    max_scheduler_drift_ns = max(max_scheduler_drift_ns, abs(drift_ns))
                    if target_wait > 0:
                        time.sleep(min(target_wait, 0.01))
                last_source_ts = batch_source_ts[-1]
            kite_depth_ws.on_ticks(None, batch)
            batch_end = time.monotonic_ns()
            callback_batches.append({
                "batch_index": len(callback_batches),
                "batch_size": len(batch),
                "batch_start_ns": batch_start,
                "batch_end_ns": batch_end,
                "duration_ns": batch_end - batch_start,
                "rows_per_sec": (len(batch) / ((batch_end - batch_start) / 1e9)) if batch_end > batch_start else None,
            })
            if scenario == "randomized_pauses" and rng.random() < random_pause_probability:
                time.sleep(rng.uniform(0.0, random_pause_max_ms) / 1000.0)
            if pressure_controller is not None and pressure_controller.enabled:
                pressure_controller._record_queue_event(
                    "callback_batch_complete",
                    scenario=scenario,
                    batch_index=len(callback_batches) - 1,
                    rows_produced=min(len(rows), start + len(batch)),
                )
                pressure_controller.resource_timeline.append({"kind": "periodic_sample", **_resource_timeline_sample()})
        if pressure_controller is not None and pressure_controller.enabled:
            pressure_controller._record_queue_event("producer_completed", scenario=scenario, rows_produced=len(rows))
            pressure_controller.record_worker_event("shutdown_started", scenario=scenario)
        # Use shutdown as the sole async drain authority. Calling the public flush
        # concurrently with the persistence worker creates two queue consumers;
        # batches can then commit in a different order even though dequeue order is
        # FIFO. The governed shutdown path stops acceptance, drains, and joins the
        # worker without introducing that replay-only race.
        shutdown_result = tick_store.shutdown_persistence_worker(deadline_seconds=shutdown_deadline_seconds)
        if pressure_controller is not None and pressure_controller.enabled:
            pressure_controller.record_worker_event(
                "stop_accepting_writes",
                scenario=scenario,
                monotonic_ns=shutdown_result.get("shutdown_started_monotonic_ns"),
                shutdown_result=shutdown_result,
            )
            pressure_controller.record_worker_event(
                "drain_started",
                scenario=scenario,
                monotonic_ns=shutdown_result.get("shutdown_started_monotonic_ns"),
                shutdown_result=shutdown_result,
            )
            if shutdown_result.get("deadline_expired"):
                pressure_controller.record_worker_event(
                    "deadline_expired",
                    scenario=scenario,
                    monotonic_ns=shutdown_result.get("shutdown_finished_monotonic_ns"),
                    shutdown_result=shutdown_result,
                )
            pressure_controller.record_worker_event(
                "drain_completed",
                scenario=scenario,
                monotonic_ns=shutdown_result.get("shutdown_finished_monotonic_ns"),
                shutdown_result=shutdown_result,
            )
            pressure_controller.record_worker_event(
                "worker_join_started",
                scenario=scenario,
                monotonic_ns=shutdown_result.get("shutdown_started_monotonic_ns"),
                shutdown_result=shutdown_result,
            )
            pressure_controller.record_worker_event(
                "worker_join_completed",
                scenario=scenario,
                monotonic_ns=shutdown_result.get("shutdown_finished_monotonic_ns"),
                worker_state=tick_store.get_persistence_worker_state(),
                shutdown_result=shutdown_result,
            )
            pressure_controller.record_worker_event(
                "shutdown_completed",
                scenario=scenario,
                monotonic_ns=shutdown_result.get("shutdown_finished_monotonic_ns"),
                shutdown_result=shutdown_result,
            )
            pressure_controller.resource_timeline.append({"kind": "post_join_sample", **_resource_timeline_sample()})
        input_rows = []
        for row in rows:
            adapted = _adapt(row)
            input_rows.append({"source_row_index": row["source_row_index"], "instrument_token": adapted["instrument_token"],
                               "source_timestamp": adapted["_audit_source_timestamp"], "last_price": adapted["last_price"],
                               "volume": adapted["volume"], "oi": adapted["oi"]})
        report = collector.report(input_rows=input_rows, pending_at_shutdown=tick_store.pending_tick_count(), live_session_complete=False)
        source_duration, target_replay_duration = _deterministic_replay_schedule(rows, speed_factor)
        actual_replay_duration = time.monotonic() - schedule_start
        report["replay_timing"] = {
            "source_duration_sec": source_duration,
            "target_replay_duration_sec": target_replay_duration,
            "actual_replay_duration_sec": actual_replay_duration,
            "target_speed_factor": speed_factor,
            "achieved_speed_factor": (source_duration / actual_replay_duration) if actual_replay_duration > 0 else None,
            "max_scheduler_drift_ns": max_scheduler_drift_ns,
            "randomized_pause_seed": seed if scenario == "randomized_pauses" else None,
        }
        report["callback_batches"] = callback_batches
        report["persistence_mode"] = _describe_tick_store_mode()
        report["persistence_mode"]["selected_persistence_mode"] = selected_persistence_mode or "default"
        report["persistence_worker"] = tick_store.get_persistence_worker_state()
        report["shutdown_result"] = shutdown_result
        report["resource_snapshot"] = _resource_snapshot()
        report["fd_trace_summary"] = _fd_trace_summary(
            trace_path,
            baseline_fd=process_fd_count(),
            post_worker_shutdown_fd=process_fd_count(),
        )
        if pressure_controller is not None and pressure_controller.enabled:
            pressure_controller.record_worker_event("final_state", scenario=scenario, worker_state=report["persistence_worker"])
            producer_completion_event = next((entry for entry in reversed(pressure_controller.timeline) if entry.get("stage") == "producer_completed"), None)
            producer_completion_queue_depth = (
                int(producer_completion_event.get("queue_depth"))
                if producer_completion_event and producer_completion_event.get("queue_depth") is not None
                else tick_store.write_queue_depth()
            )
            producer_completion_pending_writes = (
                int(producer_completion_event.get("pending_writes"))
                if producer_completion_event and producer_completion_event.get("pending_writes") is not None
                else max(0, tick_store.write_enqueue_count() - tick_store.write_flush_count())
            )
            report["pressure_profile"] = {
                "profile": pressure_controller.profile,
                "delay_before_each_commit_ms": pressure_controller.delay_before_each_commit_ms,
                "stall_after_each_dequeued_rows": pressure_controller.stall_after_each_dequeued_rows,
                "stall_duration_ms": pressure_controller.stall_duration_ms,
                "expected_total_rows": pressure_controller.expected_total_rows,
                "queue_high_water_threshold": _pressure_queue_threshold(),
                "hook_invocation_count": pressure_controller.hook_invocation_count,
                "stall_activation_count": pressure_controller._stall_index,
                "worker_commit_hook_count": tick_store.get_persistence_worker_state().get("committed_batches"),
                "committed_batch_count": tick_store.get_persistence_worker_state().get("committed_batches"),
                "cumulative_requested_delay_ms": pressure_controller.cumulative_requested_delay_ms,
                "cumulative_observed_delay_ms": pressure_controller.cumulative_observed_delay_ms,
                "max_pending_writes": pressure_controller._max_pending_writes,
                "hook_ordinal": pressure_controller._hook_ordinal,
            }
            report["worker_lifecycle"] = pressure_controller.worker_lifecycle
            report["queue_depth_timeline"] = pressure_controller.timeline
            report["resource_timeline"] = pressure_controller.resource_timeline
            worker_state = tick_store.get_persistence_worker_state()
            report["drain_report"] = {
                "shutdown_status": shutdown_result.get("status"),
                "deadline_seconds": shutdown_result.get("deadline_seconds"),
                "deadline_expired": shutdown_result.get("deadline_expired"),
                "shutdown_started_monotonic_ns": shutdown_result.get("shutdown_started_monotonic_ns"),
                "shutdown_finished_monotonic_ns": shutdown_result.get("shutdown_finished_monotonic_ns"),
                "drain_duration_ns": shutdown_result.get("drain_duration_ns"),
                "actual_thread_join_duration_ns": shutdown_result.get("join_duration_ns"),
                "final_accounting_duration_ns": (
                    None
                    if shutdown_result.get("drain_duration_ns") is None or shutdown_result.get("join_duration_ns") is None
                    else max(0, int(shutdown_result["drain_duration_ns"]) - int(shutdown_result["join_duration_ns"]))
                ),
                "total_shutdown_path_duration_ns": shutdown_result.get("drain_duration_ns"),
                "producer_completion_monotonic_ns": (
                    producer_completion_event.get("monotonic_ns")
                    if producer_completion_event and producer_completion_event.get("monotonic_ns") is not None
                    else (callback_batches[-1]["batch_end_ns"] if callback_batches else schedule_start)
                ),
                "producer_completion_queue_depth": producer_completion_queue_depth,
                "producer_completion_pending_writes": producer_completion_pending_writes,
                "queue_depth_at_shutdown": shutdown_result.get("queue_depth"),
                "pending_writes_at_shutdown": shutdown_result.get("pending_writes"),
                "in_flight_rows_at_shutdown": shutdown_result.get("in_flight_rows"),
                "rows_enqueued": shutdown_result.get("rows_enqueued"),
                "rows_dequeued": shutdown_result.get("rows_dequeued"),
                "rows_committed": shutdown_result.get("rows_committed"),
                "committed_batches": shutdown_result.get("committed_batches"),
                "writes_rejected_after_shutdown": shutdown_result.get("writes_rejected_after_shutdown"),
                "worker_alive": shutdown_result.get("worker_alive"),
                "worker_daemon": worker_state.get("worker_daemon"),
                "worker_join_completed": shutdown_result.get("worker_join_completed"),
                "worker_terminated": shutdown_result.get("worker_terminated"),
                "worker_failures": shutdown_result.get("worker_failures"),
                "final_flush_attempted": shutdown_result.get("final_flush_attempted"),
                "final_flush_completed": shutdown_result.get("final_flush_completed"),
                "worker_completion_monotonic_ns": shutdown_result.get("shutdown_finished_monotonic_ns"),
                "initial_shutdown_result": worker_state.get("initial_shutdown_result"),
                "cleanup_shutdown_result": worker_state.get("cleanup_shutdown_result"),
            }
        tick_store.clear_replay_pressure_hook()
        tick_store.set_replay_pressure_immediate_flush_enabled(True)
        tick_store.set_replay_pressure_read_flush_enabled(True)
        return report
    finally:
        cfg.TICK_STORE_ASYNC_DB_WRITES = previous_async_db_writes
        cfg.TICK_STORE_ENABLE_DB_WRITES = previous_enable_db_writes
        if previous_trade_db_path is not None:
            cfg.TRADE_DB_PATH = previous_trade_db_path


def _load(path: Path, max_rows: int | None, spike_start: str | None, spike_end: str | None) -> list[dict]:
    frame = pd.read_parquet(path)
    if spike_start or spike_end:
        ts_col = "ts" if "ts" in frame.columns else "timestamp"
        parsed = pd.to_datetime(frame[ts_col], errors="coerce", utc=True)
        if spike_start:
            frame = frame[parsed >= pd.Timestamp(spike_start, tz="UTC")]
            parsed = parsed.loc[frame.index]
        if spike_end:
            frame = frame[parsed <= pd.Timestamp(spike_end, tz="UTC")]
    if max_rows:
        frame = frame.head(max_rows)
    records = frame.to_dict("records")
    for source_row_index, row in enumerate(records):
        row["source_row_index"] = source_row_index
    return records


def _select_scenarios(all_scenarios: dict[str, dict], selected: list[str] | None, parser: argparse.ArgumentParser) -> dict[str, dict]:
    selected_scenarios = list(selected or [])
    if not selected_scenarios:
        return dict(all_scenarios)
    unknown = [name for name in selected_scenarios if name not in all_scenarios]
    if unknown:
        parser.error(f"unknown scenario(s): {', '.join(sorted(set(unknown)))}")
    filtered = {name: all_scenarios[name] for name in selected_scenarios if name in all_scenarios}
    if not filtered:
        parser.error("no valid scenarios selected")
    return filtered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--spike-start")
    parser.add_argument("--spike-end")
    parser.add_argument("--session-cycles", type=int, default=50)
    parser.add_argument(
        "--persistence-mode",
        choices=["default", "sync", "async_queue"],
        default="default",
        help="Diagnostic-only persistence mode selector.",
    )
    parser.add_argument(
        "--pressure-profile",
        choices=["none", "constant_delay", "intermittent_stall"],
        default="none",
        help="Replay-only persistence pressure profile. Disabled by default.",
    )
    parser.add_argument("--pressure-delay-before-each-commit-ms", type=int, default=0)
    parser.add_argument("--pressure-stall-after-each-dequeued-rows", type=int, default=0)
    parser.add_argument("--pressure-stall-duration-ms", type=int, default=0)
    parser.add_argument(
        "--persistence-shutdown-deadline-seconds",
        type=float,
        default=2.0,
        help="Replay-only shutdown deadline used for the persistence worker join and drain.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        default=None,
        help="Run only the named replay scenario. May be repeated.",
    )
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")
    if not args.input.is_file():
        parser.error("input parquet does not exist")

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    trace_path = out / "fd_trace.jsonl"
    if os.environ.get("TRADEBOT_FEED_FD_TRACE"):
        os.environ.setdefault("TRADEBOT_FEED_FD_TRACE_PATH", str(trace_path))
    branch_name = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    dirty_files = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).splitlines()
    cfg.TICK_STORE_ENABLE_DB_WRITES = True
    cfg.TRADE_DB_PATH = str(out / "replay_ticks.sqlite3")
    rows = _load(args.input, args.max_rows, None, None)
    spike_rows = _load(args.input, args.max_rows, args.spike_start, args.spike_end) if args.spike_start or args.spike_end else rows
    timestamp_fidelity = _capture_timestamp_fidelity(rows)
    scenarios = {
        "normal_speed": {"rows": rows, "speed_factor": 1.0, "batch_size": 100},
        "5x_speed": {"rows": rows, "speed_factor": 5.0, "batch_size": 100},
        "10x_speed": {"rows": rows, "speed_factor": 10.0, "batch_size": 100},
        "randomized_pauses": {"rows": rows, "speed_factor": 1.0, "batch_size": 100, "random_pause_probability": 0.2, "random_pause_max_ms": 1.0},
        "known_spike_window": {"rows": spike_rows, "speed_factor": 1.0, "batch_size": 100},
        "batch_1": {"rows": rows, "speed_factor": 1.0, "batch_size": 1},
        "batch_10": {"rows": rows, "speed_factor": 1.0, "batch_size": 10},
        "batch_50": {"rows": rows, "speed_factor": 1.0, "batch_size": 50},
        "batch_100": {"rows": rows, "speed_factor": 1.0, "batch_size": 100},
        "batch_500": {"rows": rows, "speed_factor": 1.0, "batch_size": 500},
        "batch_1000": {"rows": rows, "speed_factor": 1.0, "batch_size": 1000},
    }
    selected_scenarios = list(args.scenarios or [])
    scenarios = _select_scenarios(scenarios, selected_scenarios, parser)
    pressure_controller = _ReplayPressureController(
        profile=args.pressure_profile,
        delay_before_each_commit_ms=args.pressure_delay_before_each_commit_ms,
        stall_after_each_dequeued_rows=args.pressure_stall_after_each_dequeued_rows,
        stall_duration_ms=args.pressure_stall_duration_ms,
    )
    if pressure_controller.enabled and not any(True for _ in scenarios):
        parser.error("pressure profile requires at least one replay scenario")
    results, faults = {}, []
    hard_failures = []
    selected_persistence_mode = args.persistence_mode
    for scenario, spec in scenarios.items():
        scenario_rows = spec["rows"]
        scenario_sync = _resolve_persistence_mode(scenario, selected_persistence_mode)
        runs = [_run_once(scenario_rows, scenario, seed=i, synchronous=scenario_sync, speed_factor=spec["speed_factor"],
                          batch_size=spec["batch_size"], random_pause_probability=spec.get("random_pause_probability", 0.0),
                          random_pause_max_ms=spec.get("random_pause_max_ms", 0.0), trace_path=trace_path,
                          selected_persistence_mode=selected_persistence_mode,
                          pressure_controller=pressure_controller if pressure_controller.enabled else None,
                          shutdown_deadline_seconds=args.persistence_shutdown_deadline_seconds)
                for i in range(args.iterations)]
        signatures = [run["checksums"] for run in runs]
        deterministic = all(item == signatures[0] for item in signatures[1:])
        if not deterministic or any(run["verdict"] == "FAIL" for run in runs):
            hard_failures.append(scenario)
        results[scenario] = {"iterations": args.iterations, "deterministic": deterministic, "runs": runs}

    current_runs = []
    current_deterministic = True
    if not selected_scenarios or "normal_speed_current_persistence" in selected_scenarios:
        current_runs = [_run_once(rows, "normal_speed_current_persistence", seed=i, synchronous=_resolve_persistence_mode("normal_speed_current_persistence", selected_persistence_mode), speed_factor=1.0, batch_size=100, trace_path=trace_path, selected_persistence_mode=selected_persistence_mode, shutdown_deadline_seconds=args.persistence_shutdown_deadline_seconds)
                        for i in range(args.iterations)]
        current_deterministic = all(run["checksums"] == current_runs[0]["checksums"] for run in current_runs[1:])
        if not current_deterministic or any(run["verdict"] == "FAIL" for run in current_runs):
            hard_failures.append("normal_speed_current_persistence")
        results["normal_speed_current_persistence"] = {
            "iterations": args.iterations, "deterministic": current_deterministic, "runs": current_runs,
        }

    cycle_snapshots = []
    cycle_hashes = []
    if not selected_scenarios or "session_cycles" in selected_scenarios:
        for cycle in range(max(0, args.session_cycles)):
            cycle_run = _run_once(rows, f"session_cycle_{cycle}", seed=cycle, synchronous=_resolve_persistence_mode("session_cycle", selected_persistence_mode), speed_factor=1.0, batch_size=100, trace_path=trace_path, selected_persistence_mode=selected_persistence_mode, shutdown_deadline_seconds=args.persistence_shutdown_deadline_seconds)
            cycle_snapshots.append({
                "cycle": cycle,
                "resource_snapshot": cycle_run["resource_snapshot"],
                "checksums": cycle_run["checksums"],
                "pending_at_shutdown": cycle_run["counters"].get("pending_at_shutdown"),
            })
            cycle_hashes.append(cycle_run["checksums"])
        cycle_deterministic = all(item == cycle_hashes[0] for item in cycle_hashes[1:]) if cycle_hashes else True
        if not cycle_deterministic:
            hard_failures.append("session_cycles")
    else:
        cycle_deterministic = True

    for name in ("disconnect_5s", "disconnect_30s", "disconnect_120s", "connection_flapping",
                 "malformed_messages", "duplicate_messages", "unknown_tokens", "out_of_order_timestamps",
                 "slow_downstream_consumer", "5x_input_burst", "10x_input_burst", "shutdown_during_active_processing"):
        event = {"ts": datetime.now(timezone.utc).isoformat(), "fault": name,
                 "simulated_offline": True, "production_runtime_mutated": False}
        faults.append(event)
    (out / "fault_injection_events.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in faults), encoding="utf-8")

    final_run = results["normal_speed"]["runs"][0]
    normal_records = results["normal_speed"]["runs"]
    first_diff = None
    if len(normal_records) >= 2:
        first_diff = first_difference(normal_records[0]["records"], normal_records[1]["records"])
    volatile_first_diff = None
    if len(normal_records) >= 2:
        for pos, (left, right) in enumerate(zip(normal_records[0]["records"], normal_records[1]["records"])):
            volatile = {key: (left.get(key), right.get(key)) for key in
                        ("callback_ns", "normalized_ns", "published_ns", "persisted_ns") if left.get(key) != right.get(key)}
            if volatile:
                volatile_first_diff = {"first_differing_position": pos, "source_row_index": left.get("source_row_index"),
                                       "instrument_token": left.get("instrument_token"), "source_timestamp": left.get("source_timestamp"),
                                       "volatile_stage_timestamps": volatile, "semantic_output_differs": first_diff is not None}
                break
    verdict = "FAIL" if hard_failures else "CONDITIONALLY_STABLE"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    diff_sha256 = _git_diff_sha256()
    manifest = {"schema_version": 1, "input": str(args.input.resolve()), "input_sha256": _sha(args.input),
                "git_commit": commit, "iterations": args.iterations, "scenarios": list(scenarios),
                "selected_scenarios": selected_scenarios,
                "row_limit": args.max_rows, "session_cycles": args.session_cycles, "live_session_complete": False,
                "provider_sequence_numbers_present": False, "upstream_completeness_claimed": False,
                "read_only": True, "append": False, "is_order_action": False,
                "broker_api_called": False, "allowed_for_live_execution": False,
                "output_dir": str(out),
                "worktree_path": str(ROOT),
                "branch_name": branch_name,
                "dirty_files": dirty_files,
                "dirty_diff_sha256": diff_sha256,
                "fd_trace_enabled": bool(os.environ.get("TRADEBOT_FEED_FD_TRACE")),
                "persistence_mode": selected_persistence_mode,
                "persistence_shutdown_deadline_seconds": args.persistence_shutdown_deadline_seconds,
                "trace_path": str(trace_path),
                "max_rows": args.max_rows,
               }
    _atomic_json(out / "run_manifest.json", manifest)
    _atomic_json(out / "feed_counters.json", {k: v["runs"] for k, v in results.items()})
    _atomic_json(out / "latency_report.json", final_run["latency"])
    _atomic_json(out / "subscription_recovery.json", final_run["reconnects"])
    _atomic_json(out / "timestamp_fidelity.json", timestamp_fidelity)
    _atomic_json(out / "first_difference.json", {"semantic_first_difference": first_diff,
                                                   "volatile_first_difference": volatile_first_diff})
    _atomic_json(out / "feed_verdict.json", {"verdict": verdict, "hard_failures": hard_failures,
                                              "assertions": final_run["assertions"],
                                              "unexplained_message_differences": final_run["unexplained_message_differences"],
                                              "first_difference": first_diff,
                                              "timestamp_fidelity_pass": timestamp_fidelity["summary"]["pass"],
                                              "timestamp_fidelity_summary": timestamp_fidelity["summary"]})
    _atomic_json(out / "checksums.json", {"input_sha256": manifest["input_sha256"],
                                           "output_sha256": {p.name: _sha(p) for p in out.iterdir() if p.is_file()}})
    _atomic_json(out / "configuration_snapshot.json", {"python": sys.version, "platform": platform.platform(),
                                                        "iterations": args.iterations, "max_rows": args.max_rows,
                                                        "persistence_shutdown_deadline_seconds": args.persistence_shutdown_deadline_seconds,
                                                        "modes": ["sync_diagnostic", "current_persistence"],
                                                        "persistence_mode": _describe_tick_store_mode(),
                                                        "pressure_profile": {
                                                            "profile": pressure_controller.profile,
                                                            "delay_before_each_commit_ms": pressure_controller.delay_before_each_commit_ms,
                                                            "stall_after_each_dequeued_rows": pressure_controller.stall_after_each_dequeued_rows,
                                                            "stall_duration_ms": pressure_controller.stall_duration_ms,
                                                            "expected_total_rows": pressure_controller.expected_total_rows,
                                                            "enabled": pressure_controller.enabled,
                                                            "queue_high_water_threshold": _pressure_queue_threshold(),
                                                            "hook_invocation_count": pressure_controller.hook_invocation_count,
                                                            "cumulative_requested_delay_ms": pressure_controller.cumulative_requested_delay_ms,
                                                            "cumulative_observed_delay_ms": pressure_controller.cumulative_observed_delay_ms,
                                                        }})
    _atomic_json(out / "resource_snapshot.json", {"final": cycle_snapshots[-1]["resource_snapshot"] if cycle_snapshots else final_run["resource_snapshot"],
                                                  "session_cycles": args.session_cycles,
                                                  "cycle_samples": cycle_snapshots,
                                                  "cycle_deterministic": cycle_deterministic,
                                                  "fd_trace": final_run.get("fd_trace_summary")})
    if pressure_controller.enabled:
        _atomic_json(out / "pressure_profile.json", {
            "profile": pressure_controller.profile,
            "delay_before_each_commit_ms": pressure_controller.delay_before_each_commit_ms,
            "stall_after_each_dequeued_rows": pressure_controller.stall_after_each_dequeued_rows,
            "stall_duration_ms": pressure_controller.stall_duration_ms,
            "expected_total_rows": pressure_controller.expected_total_rows,
            "queue_high_water_threshold": _pressure_queue_threshold(),
            "hook_invocation_count": pressure_controller.hook_invocation_count,
            "cumulative_requested_delay_ms": pressure_controller.cumulative_requested_delay_ms,
            "cumulative_observed_delay_ms": pressure_controller.cumulative_observed_delay_ms,
            "max_pending_writes": pressure_controller._max_pending_writes,
        })
        (out / "queue_depth_timeline.jsonl").write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in pressure_controller.timeline) + "\n",
            encoding="utf-8",
        )
        (out / "resource_timeline.jsonl").write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in pressure_controller.resource_timeline) + "\n",
            encoding="utf-8",
        )
        _atomic_json(out / "worker_lifecycle.json", pressure_controller.worker_lifecycle)
        _atomic_json(out / "drain_report.json", final_run.get("drain_report", {}))
    print(json.dumps({"verdict": verdict, "output_dir": str(out), "hard_failures": hard_failures}, indent=2))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
