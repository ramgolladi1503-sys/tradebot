from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode()).hexdigest()


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    rows = sorted(values); rank = (len(rows) - 1) * q; lo = math.floor(rank); hi = math.ceil(rank)
    return rows[lo] if lo == hi else rows[lo] + (rows[hi] - rows[lo]) * (rank - lo)


def latency_summary(values: Iterable[float], sla_ms: float | None = None) -> dict[str, Any]:
    rows = [float(v) for v in values if math.isfinite(float(v)) and float(v) >= 0]
    return {"count": len(rows), "p50_ms": _pct(rows, .5), "p95_ms": _pct(rows, .95),
            "p99_ms": _pct(rows, .99), "p99_9_ms": _pct(rows, .999),
            "max_ms": max(rows) if rows else None, "sla_ms": sla_ms,
            "sla_breach_count": sum(sla_ms is not None and v > sla_ms for v in rows)}


def canonical_semantic(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keys = ("instrument_token", "source_timestamp", "last_price", "volume", "oi")
    return sorted(({k: row.get(k) for k in keys} for row in rows), key=lambda r: tuple(str(r[k]) for k in keys))


def final_token_state(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    # Existing callback policy is arrival/source order: for equal token/timestamp, later source row wins.
    state: dict[int, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: int(r["source_row_index"])):
        state[int(row["instrument_token"])] = {k: row.get(k) for k in
            ("source_row_index", "instrument_token", "source_timestamp", "last_price", "volume", "oi")}
    return [state[token] for token in sorted(state)]


def first_difference(left: list[Mapping[str, Any]], right: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    comparison_keys = ("source_row_index", "instrument_token", "source_timestamp", "callback_sequence",
                       "normalization_sequence", "persistence_sequence", "last_price", "volume", "oi")
    for pos in range(max(len(left), len(right))):
        a = ({k: left[pos].get(k) for k in comparison_keys} if pos < len(left) else None)
        b = ({k: right[pos].get(k) for k in comparison_keys} if pos < len(right) else None)
        if a != b:
            return {"first_differing_position": pos, "left": a, "right": b,
                    "source_row_index": (a or b or {}).get("source_row_index"),
                    "instrument_token": (a or b or {}).get("instrument_token"),
                    "source_timestamp": (a or b or {}).get("source_timestamp"),
                    "final_per_token_state_differs": _hash(final_token_state(left)) != _hash(final_token_state(right))}
    return None


@dataclass
class FeedEvidenceCollector:
    enabled: bool = False
    progress_stall_sec: float = 5.0
    latency_sla_ms: float | None = None
    counters: Counter = field(default_factory=Counter)
    rejection_reasons: Counter = field(default_factory=Counter)
    drop_reasons: Counter = field(default_factory=Counter)
    records: dict[int, dict[str, Any]] = field(default_factory=dict)
    callback_order: list[int] = field(default_factory=list)
    normalization_order: list[int] = field(default_factory=list)
    persistence_order: list[int] = field(default_factory=list)
    pending_by_key: dict[tuple, deque[int]] = field(default_factory=lambda: defaultdict(deque))
    reconnects: list[dict[str, Any]] = field(default_factory=list)
    last_callback_monotonic_ns: int | None = None
    last_progress_monotonic_ns: int | None = None
    longest_stall_ns: int = 0
    _callback_sequence: int = 0
    _normalization_sequence: int = 0
    _persistence_sequence: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def reset(self, *, enabled: bool | None = None) -> None:
        replacement = FeedEvidenceCollector(self.enabled if enabled is None else enabled, self.progress_stall_sec, self.latency_sla_ms)
        with self._lock:
            for name in self.__dataclass_fields__:
                if name != "_lock": setattr(self, name, getattr(replacement, name))

    def callback(self, count: int, callback_epoch: float | None = None, *, rows: Iterable[Mapping[str, Any]] | None = None) -> None:
        if not self.enabled: return
        now_ns = time.monotonic_ns()
        with self._lock:
            self.counters["websocket_messages_received"] += 1; self.counters["decoded"] += int(count)
            self.last_callback_monotonic_ns = now_ns
            if self.last_progress_monotonic_ns is None: self.last_progress_monotonic_ns = now_ns
            for row in rows or ():
                idx = int(row["source_row_index"]); self._callback_sequence += 1; self.callback_order.append(idx)
                self.records[idx] = {"source_row_index": idx, "instrument_token": int(row["instrument_token"]),
                    "source_timestamp": row.get("source_timestamp"), "last_price": row.get("last_price"),
                    "volume": row.get("volume"), "oi": row.get("oi"), "callback_sequence": self._callback_sequence,
                    "callback_ns": now_ns}

    def inc(self, boundary: str, count: int = 1, *, reason: str | None = None) -> None:
        if not self.enabled: return
        with self._lock:
            self.counters[boundary] += count
            if boundary == "rejected" and reason: self.rejection_reasons[reason] += count
            if boundary == "explicitly_dropped" and reason: self.drop_reasons[reason] += count

    def normalized(self, source_row_index: int, token: int, source_timestamp: Any, last_price: Any,
                   volume: Any, oi: Any) -> None:
        if not self.enabled: return
        now_ns = time.monotonic_ns(); idx = int(source_row_index)
        with self._lock:
            self.counters["normalized"] += 1; self._normalization_sequence += 1; self.normalization_order.append(idx)
            row = self.records.setdefault(idx, {"source_row_index": idx})
            row.update(instrument_token=int(token), source_timestamp=source_timestamp, last_price=last_price,
                       volume=volume, oi=oi, normalization_sequence=self._normalization_sequence, normalized_ns=now_ns)
            if self.last_progress_monotonic_ns is not None: self.longest_stall_ns = max(self.longest_stall_ns, now_ns-self.last_progress_monotonic_ns)
            self.last_progress_monotonic_ns = now_ns

    @staticmethod
    def key(token: Any, ts: Any, price: Any, volume: Any, oi: Any) -> tuple:
        return (int(token), float(ts), None if price is None else float(price),
                None if volume is None else float(volume), None if oi is None else float(oi))

    def published(self, source_row_index: int, token: Any, ts: Any, price: Any, volume: Any, oi: Any) -> None:
        if not self.enabled: return
        now_ns = time.monotonic_ns(); idx = int(source_row_index)
        with self._lock:
            self.counters["published"] += 1; self.records[idx]["published_ns"] = now_ns
            self.pending_by_key[self.key(token, ts, price, volume, oi)].append(idx)

    def publication_failed(self, source_row_index: int, token: Any, ts: Any, price: Any, volume: Any, oi: Any,
                           reason: str) -> None:
        if not self.enabled: return
        idx = int(source_row_index); key = self.key(token, ts, price, volume, oi)
        with self._lock:
            self.counters["published"] -= 1; self.counters["explicitly_dropped"] += 1; self.drop_reasons[reason] += 1
            pending = self.pending_by_key.get(key)
            if pending:
                try: pending.remove(idx)
                except ValueError: pass
            self.records[idx].pop("published_ns", None)

    def persisted_row(self, token: Any, ts: Any, price: Any, volume: Any, oi: Any) -> None:
        if not self.enabled: return
        now_ns = time.monotonic_ns(); key = self.key(token, ts, price, volume, oi)
        with self._lock:
            pending = self.pending_by_key.get(key)
            if not pending: self.counters["uncorrelated_persisted"] += 1; return
            idx = pending.popleft(); self._persistence_sequence += 1; self.persistence_order.append(idx)
            self.records[idx].update(persistence_sequence=self._persistence_sequence, persisted_ns=now_ns)
            self.counters["persisted"] += 1

    def record_reconnect(self, expected: Iterable[int], restored: Iterable[int], **values: Any) -> None:
        exp, restored_list = set(map(int, expected)), list(map(int, restored)); got = set(restored_list)
        self.reconnects.append({"stale_state_exposed": bool(values.get("stale_exposed")),
            "reconnect_completed": bool(values.get("completed")), "expected_tokens": sorted(exp), "restored_tokens": sorted(got),
            "missing_tokens": sorted(exp-got), "unexpected_tokens": sorted(got-exp),
            "duplicate_subscription_count": len(restored_list)-len(got),
            "time_to_first_valid_post_reconnect_tick_ms": values.get("first_valid_tick_ms")})

    def report(self, *, input_rows: Iterable[Mapping[str, Any]] = (), pending_at_shutdown: int = 0,
               live_session_complete: bool = False, report_generated_at: Any = None) -> dict[str, Any]:
        with self._lock:
            rows = [dict(self.records[i]) for i in sorted(self.records)]
            semantic_rows = canonical_semantic(rows); final_rows = final_token_state(rows)
            input_material = [{k: r.get(k) for k in ("source_row_index", "instrument_token", "source_timestamp", "last_price", "volume", "oi")} for r in input_rows]
            def stage_material(order: list[int]) -> list[dict[str, Any]]:
                return [{k: self.records[i].get(k) for k in ("source_row_index", "instrument_token", "source_timestamp", "last_price", "volume", "oi")} for i in order]
            stage_ok, latency = True, {"callback_to_normalization": [], "normalization_to_publication": [],
                                      "publication_to_persistence": [], "callback_to_persistence": [], "additivity_error_ns": []}
            for row in rows:
                if not all(k in row for k in ("callback_ns", "normalized_ns", "published_ns", "persisted_ns")): continue
                c,n,p,s = (int(row[k]) for k in ("callback_ns","normalized_ns","published_ns","persisted_ns"))
                stage_ok &= c <= n <= p <= s
                latency["callback_to_normalization"].append((n-c)/1e6); latency["normalization_to_publication"].append((p-n)/1e6)
                latency["publication_to_persistence"].append((s-p)/1e6); latency["callback_to_persistence"].append((s-c)/1e6)
                latency["additivity_error_ns"].append((s-c)-((n-c)+(p-n)+(s-p)))
            latency_report = {k: (latency_summary(v, self.latency_sla_ms) if k != "additivity_error_ns" else
                               {"count": len(v), "max_abs_ns": max(map(abs,v), default=0)}) for k,v in latency.items()}
            c = Counter(self.counters); c["pending_at_shutdown"] = pending_at_shutdown
            assertions = {"decoded_equals_normalized_plus_rejected": c["decoded"] == c["normalized"]+c["rejected"],
                "normalized_equals_published_plus_explicitly_dropped": c["normalized"] == c["published"]+c["explicitly_dropped"],
                "published_equals_persisted_plus_pending_at_shutdown": c["published"] == c["persisted"]+pending_at_shutdown,
                "latency_stage_order_valid": stage_ok, "latency_additivity_valid": latency_report["additivity_error_ns"]["max_abs_ns"] == 0}
            unexplained = {"decoded": c["decoded"]-c["normalized"]-c["rejected"],
                "normalized": c["normalized"]-c["published"]-c["explicitly_dropped"],
                "published": c["published"]-c["persisted"]-pending_at_shutdown}
            hashes = {"input_source_order_sha256": _hash(input_material), "callback_order_sha256": _hash(stage_material(self.callback_order)),
                "normalization_order_sha256": _hash(stage_material(self.normalization_order)), "persistence_order_sha256": _hash(stage_material(self.persistence_order)),
                "canonical_semantic_output_sha256": _hash(semantic_rows), "final_per_token_state_sha256": _hash(final_rows)}
            verdict = "CONDITIONALLY_STABLE" if all(assertions.values()) and not any(unexplained.values()) else "FAIL"
            return {"counters": dict(c), "records": rows, "checksums": hashes, "assertions": assertions,
                "unexplained_message_differences": unexplained, "latency": latency_report, "verdict": verdict,
                "reconnects": list(self.reconnects),
                "report_generated_at": report_generated_at, "read_only": True, "append": False,
                "is_order_action": False, "broker_api_called": False, "allowed_for_live_execution": False,
                "upstream_completeness_claimed": False}


collector = FeedEvidenceCollector()
