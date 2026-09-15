#!/usr/bin/env python3
"""Primitive-first proof generator for PR #905.

This generator does not certify itself. It runs the real canonical coordinator
with frozen replay inputs, spies the exact TradeBuilder call arguments/results,
and persists raw primitives for an independent verifier.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.canonical_cycle_coordinator import CanonicalCycleCoordinator
from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot
from core.runtime_authority_contract import AuthorityKind, build_runtime_authority_map
import core.runtime_snapshot_producer as producer
import core.runtime_snapshot_store as store
from core.trade_truth.decision_hash import compute_deterministic_hash
from core.trade_truth.prospective_capture_engine import (
    CALL_COUNTS,
    arm_broker_write_guards,
    reset_broker_write_guards,
)
from core.trade_truth.trade_builder_input_contract import parse_iso_or_epoch_seconds
from strategies.trade_builder import TradeBuilder


BASE_SHA = "87190fd9119327456ec38d0390500a5a2ff70d60"
PROOF_TYPE = "CANONICAL_COORDINATOR_REPLAY"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(REPO_ROOT), text=True).strip()


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalize_trace(value: Any) -> dict[str, Any]:
    raw = _jsonable(value) or {}
    if not isinstance(raw, dict):
        return {"value": raw}
    return {k: v for k, v in raw.items() if k not in {"ts", "run_id"}}


def _normalize_trade_for_runtime_hash(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if isinstance(value, Mapping):
        return _jsonable(dict(value))
    return str(value)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(dict(row), sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )


def _parse_timestamp(value: Any) -> float | None:
    try:
        parsed = parse_iso_or_epoch_seconds(value)
    except Exception:
        return None
    try:
        return None if parsed is None else float(parsed)
    except (TypeError, ValueError):
        return None


def generate_proof(output_dir: Path | None = None) -> Path:
    full_sha = _git("rev-parse", "HEAD")
    short_sha = _git("rev-parse", "--short", "HEAD")
    if output_dir is None:
        output_dir = Path(f"/Volumes/TradeBotData/pr905-tradebuilder-canonical-proof-{short_sha}")
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    session_id = f"pr905_canonical_{short_sha}"
    session_date = "2026-09-15"
    cutoff_iso = "2026-09-15T09:20:00+00:00"
    quote_event_ts = "2026-09-15T09:19:59+00:00"

    runtime_root = output_dir / "runtime"
    logs_root = output_dir / "logs"
    runtime_root.mkdir()
    logs_root.mkdir()

    orig_logs_dir = producer.logs_dir
    orig_runtime_dir = producer.runtime_dir
    orig_read_market_snapshot = producer.read_market_snapshot
    orig_ranked_builder = producer._build_and_write_canonical_ranked_snapshot
    orig_ranked_path = store.RANKED_PIPELINE_LATEST_PATH
    orig_ranked_legacy_path = store.RANKED_VS_LEGACY_LATEST_PATH

    from core.execution_router import ExecutionRouter

    orig_router_execute = ExecutionRouter.execute
    orig_tb_build = TradeBuilder.build_with_trace
    router_calls = [0]
    capture_run = ["run1"]
    captured_calls: list[dict[str, Any]] = []

    def _router_guard(self, *args, **kwargs):
        router_calls[0] += 1
        raise RuntimeError("EXECUTION_ROUTER_CALLED_IN_READ_ONLY_PROOF")

    def _tb_spy(self, market_data, *args, **kwargs):
        input_copy = copy.deepcopy(dict(market_data))
        try:
            trade, trace = orig_tb_build(self, market_data, *args, **kwargs)
        except Exception as exc:
            captured_calls.append(
                {
                    "run": capture_run[0],
                    "input": _jsonable(input_copy),
                    "trade": None,
                    "trace": None,
                    "reject_reason": getattr(self, "_reject_reason", None),
                    "exception": f"{type(exc).__name__}:{exc}",
                }
            )
            raise
        captured_calls.append(
            {
                "run": capture_run[0],
                "input": _jsonable(input_copy),
                "trade": _normalize_trade_for_runtime_hash(trade),
                "trace": _normalize_trace(trace),
                "reject_reason": (
                    str(getattr(self, "_reject_reason", None) or "REJECTED_BY_TRADE_BUILDER")
                    if trade is None
                    else None
                ),
                "exception": None,
            }
        )
        return trade, trace

    reset_broker_write_guards()
    arm_broker_write_guards()
    ExecutionRouter.execute = _router_guard
    TradeBuilder.build_with_trace = _tb_spy

    try:
        (logs_root / "feed_runtime_latest.json").write_text(
            json.dumps(
                {
                    "ws_connected": True,
                    "effective_ws_connected": True,
                    "runtime_state": "RUNNING",
                    "feed_runtime_state": "LIVE",
                }
            ),
            encoding="utf-8",
        )
        (logs_root / "token_resolution.json").write_text(
            json.dumps({"NIFTY": {"instrument_token": 1}}),
            encoding="utf-8",
        )

        producer.logs_dir = lambda: logs_root
        producer.runtime_dir = lambda: runtime_root
        store.RANKED_PIPELINE_LATEST_PATH = runtime_root / "ranked_pipeline_latest.json"
        store.RANKED_VS_LEGACY_LATEST_PATH = runtime_root / "ranked_vs_legacy_latest.json"

        market_snapshot = build_market_snapshot(
            generated_at="2026-09-15T09:19:59.500000+00:00",
            market_open=True,
            symbols_payload={
                "NIFTY": build_symbol_market_snapshot(
                    spot=24500.0,
                    ltp=24500.0,
                    regime={"primary_regime": "TRENDING"},
                    quote_truth={
                        "symbol": "NIFTY",
                        "ltp": 24500.0,
                        "last_tick_ts": quote_event_ts,
                        "is_fresh": True,
                        "source": "PR905_FROZEN_REPLAY_FIXTURE",
                    },
                )
            },
            warnings=[],
            compute_ms=1.0,
            loop_id=session_id,
        )
        producer.read_market_snapshot = lambda _: copy.deepcopy(market_snapshot)

        cutoff_dt = datetime.fromisoformat(cutoff_iso)
        coord1 = CanonicalCycleCoordinator(
            output_root=output_dir / "coordinator_run1",
            session_id=session_id,
            source_sha=full_sha,
        )
        req1 = coord1.request("MARKET_OPEN_INITIAL", cutoff=cutoff_dt)

        candidate = {
            "candidate_id": "c_nifty_orb_01",
            "strategy_id": "s_nifty_orb",
            "spec_sha": full_sha,
            "timestamp": quote_event_ts,
            "underlying": "NIFTY",
            "direction": "UP",
            "candidate_type": "INTRADAY",
            "confidence_raw": 0.88,
            "regime": "TRENDING",
            "reason": "orb_breakout",
            "data_cutoff": quote_event_ts,
            "execution_status": "advisory_only",
            "ltp": 11111.0,
            "entry": 11111.0,
        }
        pipeline1 = {
            "cycle_provenance": {
                "cycle_id": req1.cycle_id,
                "session_id": session_id,
                "source_sha": full_sha,
                "session_date": session_date,
            },
            "reports": [
                {
                    "candidate_pool": {
                        "regime": {"primary_regime": "TRENDING"},
                        "candidates": [candidate],
                    }
                }
            ],
        }
        producer._build_and_write_canonical_ranked_snapshot = lambda *args, **kwargs: copy.deepcopy(pipeline1)
        (runtime_root / "ranked_pipeline_latest.json").write_text(json.dumps(pipeline1), encoding="utf-8")

        capture_run[0] = "run1"
        result1 = coord1.run(req1)

        pulse1_path = output_dir / "coordinator_run1" / "truth_feed" / "CHECKPOINT_PULSE.jsonl"
        pulse1 = [json.loads(line) for line in pulse1_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        coord2 = CanonicalCycleCoordinator(
            output_root=output_dir / "coordinator_run2",
            session_id=session_id,
            source_sha=full_sha,
        )
        req2 = coord2.request("MARKET_OPEN_INITIAL", cutoff=cutoff_dt)
        pipeline2 = copy.deepcopy(pipeline1)
        pipeline2["cycle_provenance"]["cycle_id"] = req2.cycle_id
        producer._build_and_write_canonical_ranked_snapshot = lambda *args, **kwargs: copy.deepcopy(pipeline2)
        (runtime_root / "ranked_pipeline_latest.json").write_text(json.dumps(pipeline2), encoding="utf-8")

        capture_run[0] = "run2"
        result2 = coord2.run(req2)
        pulse2_path = output_dir / "coordinator_run2" / "truth_feed" / "CHECKPOINT_PULSE.jsonl"
        pulse2 = [json.loads(line) for line in pulse2_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    finally:
        TradeBuilder.build_with_trace = orig_tb_build
        ExecutionRouter.execute = orig_router_execute
        producer.logs_dir = orig_logs_dir
        producer.runtime_dir = orig_runtime_dir
        producer.read_market_snapshot = orig_read_market_snapshot
        producer._build_and_write_canonical_ranked_snapshot = orig_ranked_builder
        store.RANKED_PIPELINE_LATEST_PATH = orig_ranked_path
        store.RANKED_VS_LEGACY_LATEST_PATH = orig_ranked_legacy_path

    run1_calls = [c for c in captured_calls if c["run"] == "run1"]
    run2_calls = [c for c in captured_calls if c["run"] == "run2"]
    if len(run1_calls) != 1 or len(run2_calls) != 1:
        raise RuntimeError(
            f"EXPECTED_EXACTLY_ONE_TRADEBUILDER_CALL_PER_RUN:run1={len(run1_calls)}:run2={len(run2_calls)}"
        )

    cp1 = [s for s in pulse1 if s.get("stage_name") == "CANDIDATE_POOL"]
    tb1 = [s for s in pulse1 if s.get("stage_name") == "TRADE_BUILDER"]
    if len(cp1) != 1 or len(tb1) != 1:
        raise RuntimeError(f"EXPECTED_SINGLE_LINEAGE_SPANS:cp={len(cp1)}:tb={len(tb1)}")

    consumer_path = output_dir / "coordinator_run1" / "consumer_cycle_latest.json"
    consumer = json.loads(consumer_path.read_text(encoding="utf-8"))
    tb_state = dict((consumer.get("consumers") or {}).get("trade_builder") or {})

    captured_inputs = [copy.deepcopy(c["input"]) for c in run1_calls]
    recomputed_input_hash = compute_deterministic_hash(
        {
            "cycle_id": req1.cycle_id,
            "session_id": session_id,
            "source_sha": full_sha,
            "items": captured_inputs,
        }
    )

    runtime_trades = [c["trade"] for c in run1_calls if c["trade"] is not None]
    runtime_traces = [c["trace"] for c in run1_calls if c["trace"]]
    reject_reasons = [c["reject_reason"] for c in run1_calls if c["reject_reason"]]
    recomputed_output_hash = compute_deterministic_hash(
        {
            "trades": runtime_trades,
            "traces": runtime_traces,
            "result_status": tb_state.get("result_status"),
            "reject_reasons": reject_reasons,
            "cycle_id": req1.cycle_id,
            "session_id": session_id,
            "source_sha": full_sha,
        }
    )

    _write_jsonl(output_dir / "CHECKPOINT_PULSE_RUN1.jsonl", pulse1)
    _write_jsonl(output_dir / "CHECKPOINT_PULSE_RUN2.jsonl", pulse2)

    _write_json(
        output_dir / "TRADEBUILDER_CAPTURED_CALLS.json",
        {
            "candidate_sha": full_sha,
            "base_sha": BASE_SHA,
            "proof_type": PROOF_TYPE,
            "session_id": session_id,
            "causal_data_cutoff": cutoff_iso,
            "run1_cycle_id": req1.cycle_id,
            "run2_cycle_id": req2.cycle_id,
            "calls": captured_calls,
            "run1_consumer_tradebuilder_state": tb_state,
        },
    )
    _write_json(
        output_dir / "TRADEBUILDER_INPUT_HASHES.json",
        {
            "candidate_sha": full_sha,
            "proof_type": PROOF_TYPE,
            "checkpoint_input_hash": tb1[0]["input_hash"],
            "recomputed_from_exact_captured_arguments": recomputed_input_hash,
            "captured_inputs": captured_inputs,
        },
    )
    _write_json(
        output_dir / "TRADEBUILDER_OUTPUT_HASHES.json",
        {
            "candidate_sha": full_sha,
            "proof_type": PROOF_TYPE,
            "checkpoint_output_hash": tb1[0]["output_hash"],
            "recomputed_from_exact_captured_results": recomputed_output_hash,
            "captured_native_trades": runtime_trades,
            "captured_traces": runtime_traces,
            "captured_reject_reasons": reject_reasons,
            "result_status": tb_state.get("result_status"),
        },
    )
    _write_json(
        output_dir / "TRACE_LINEAGE.json",
        {
            "candidate_sha": full_sha,
            "proof_type": PROOF_TYPE,
            "candidate_pool_span": cp1[0],
            "trade_builder_span": tb1[0],
        },
    )

    broker_counts = {str(k): int(v) for k, v in CALL_COUNTS.items()}
    placed = sum(v for k, v in broker_counts.items() if "place_order" in k or "submit_order" in k)
    cancelled = sum(v for k, v in broker_counts.items() if "cancel_order" in k)
    modified = sum(v for k, v in broker_counts.items() if "modify_order" in k)
    _write_json(
        output_dir / "BROKER_WRITE_AUDIT.json",
        {
            "candidate_sha": full_sha,
            "proof_type": PROOF_TYPE,
            "execution_router_call_count": int(router_calls[0]),
            "call_counts": broker_counts,
            "orders_placed": int(placed),
            "orders_modified": int(modified),
            "orders_cancelled": int(cancelled),
        },
    )

    authorities = [
        {
            "stage": s.stage,
            "owner_module": s.owner_module,
            "callable_name": s.callable_name,
            "authority": s.authority.value if hasattr(s.authority, "value") else str(s.authority),
        }
        for s in build_runtime_authority_map()
        if s.authority == AuthorityKind.CANDIDATE_SELECTION
    ]
    _write_json(
        output_dir / "CANDIDATE_SELECTION_AUTHORITY_AUDIT.json",
        {
            "candidate_sha": full_sha,
            "proof_type": PROOF_TYPE,
            "authorities": authorities,
        },
    )

    event_seconds = [_parse_timestamp(c["input"].get("event_timestamp")) for c in run1_calls]
    cutoff_seconds = _parse_timestamp(cutoff_iso)
    known_events = [v for v in event_seconds if v is not None]
    future_status = "UNKNOWN"
    max_event = None
    if cutoff_seconds is not None and len(known_events) == len(run1_calls) and known_events:
        max_event = max(known_events)
        future_status = "FAIL" if max_event > cutoff_seconds else "PASS"
    _write_json(
        output_dir / "FUTURE_LEAK_AUDIT.json",
        {
            "candidate_sha": full_sha,
            "proof_type": PROOF_TYPE,
            "captured_event_timestamps": [c["input"].get("event_timestamp") for c in run1_calls],
            "max_input_event_timestamp_epoch": max_event,
            "causal_data_cutoff": cutoff_iso,
            "causal_data_cutoff_epoch": cutoff_seconds,
            "status": future_status,
        },
    )

    _write_json(
        output_dir / "DETERMINISM_REPORT.json",
        {
            "candidate_sha": full_sha,
            "proof_type": PROOF_TYPE,
            "run1_input": run1_calls[0]["input"],
            "run2_input": run2_calls[0]["input"],
            "note": "Verifier performs independent same-input replay; this artifact is primitive context only.",
        },
    )

    observed_stages = [
        {
            "stage_name": s.get("stage_name"),
            "span_id": s.get("span_id"),
            "trace_id": s.get("trace_id"),
            "parent_span_id": s.get("parent_span_id"),
            "input_hash": s.get("input_hash"),
            "output_hash": s.get("output_hash"),
            "status": s.get("status"),
        }
        for s in pulse1
    ]
    _write_json(
        output_dir / "CANONICAL_RUNTIME_CALL_LEDGER.json",
        {
            "candidate_sha": full_sha,
            "base_sha": BASE_SHA,
            "proof_type": PROOF_TYPE,
            "live_verified": False,
            "entrypoint": "core.canonical_cycle_coordinator.CanonicalCycleCoordinator.run",
            "session_id": session_id,
            "cycle_id": req1.cycle_id,
            "observed_tradebuilder_call_count": len(run1_calls),
            "observed_stages": observed_stages,
            "full_20_stage_runtime_observation": "NOT_CLAIMED",
            "coordinator_result": result1,
        },
    )

    stale_self_cert = output_dir / "PR905_IMPLEMENTATION_VERIFICATION.json"
    if stale_self_cert.exists():
        stale_self_cert.unlink()

    print(f"Generated primitive PR #905 proof package: {output_dir}")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    generate_proof(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
