#!/usr/bin/env python3
"""Independent primitive verifier for PR #905.

The verifier deliberately ignores generator-authored PASS booleans. It
recomputes lineage, hashes, cutoff compliance, authority count, determinism,
and zero-execution bounds from raw primitives plus the candidate codebase.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_authority_contract import AuthorityKind, build_runtime_authority_map
from core.trade_truth.decision_hash import compute_deterministic_hash
from core.trade_truth.trade_builder_input_contract import parse_iso_or_epoch_seconds
from strategies.trade_builder import TradeBuilder

PROOF_TYPE = "CANONICAL_COORDINATOR_REPLAY"


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=str(cwd), text=True).strip()


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


def _normalize_trade(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if isinstance(value, Mapping):
        return _jsonable(dict(value))
    return str(value)


def _parse_timestamp(value: Any) -> float | None:
    try:
        parsed = parse_iso_or_epoch_seconds(value)
    except Exception:
        return None
    try:
        return None if parsed is None else float(parsed)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"NOT_OBJECT:{path.name}")
    return raw


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"NOT_OBJECT_ROW:{path.name}")
        rows.append(row)
    return rows


def verify_pr905_codebase(repo_root: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []

    orch = (repo_root / "core" / "orchestrator.py").read_text(encoding="utf-8")
    if "build_canonical_tradebuilder_input(" not in orch:
        errors.append("CODE:PRODUCTION_SHARED_INPUT_CONTRACT_MISSING")
    if "builder_input = market_data" in orch:
        errors.append("CODE:RAW_MARKET_DATA_BYPASS_PRESENT")
    for bad in ('or "live_cycle"', 'or "production_live"'):
        if bad in orch:
            errors.append(f"CODE:SYNTHETIC_LINEAGE_DEFAULT_PRESENT:{bad}")
    if re.search(r"real_session_id\s*=.*\bor\s+[\"']DEFAULT[\"']", orch):
        errors.append("CODE:SYNTHETIC_SESSION_DEFAULT_PRESENT")
    if "except ValueError as input_contract_exc:" not in orch:
        errors.append("CODE:EXPECTED_INPUT_VALIDATION_FAIL_CLOSED_MISSING")
    if not re.search(
        r"except ValueError as input_contract_exc:.*?continue\s+except Exception:\s+.*?raise",
        orch,
        re.DOTALL,
    ):
        errors.append("CODE:UNEXPECTED_INPUT_EXCEPTION_NOT_RERAISED")

    consumer = (repo_root / "core" / "read_only_consumer_cycle.py").read_text(encoding="utf-8")
    if "build_canonical_tradebuilder_input(" not in consumer:
        errors.append("CODE:OBSERVER_SHARED_INPUT_CONTRACT_MISSING")
    if 'upstream_span_id = candidate_pool_span.span_id' not in consumer:
        errors.append("CODE:REAL_PARENT_SPAN_NOT_PROPAGATED")
    if 'stage_name="CANDIDATE_POOL"' not in consumer or 'stage_name="TRADE_BUILDER"' not in consumer:
        errors.append("CODE:REQUIRED_CHECKPOINTS_NOT_EMITTED")
    if 'parent_span_id=upstream_span_id' not in consumer:
        errors.append("CODE:TRADEBUILDER_PARENT_NOT_BOUND_TO_EMITTED_SPAN")

    if "ltp=spot_px" not in consumer:
        errors.append("CODE:TRADEBUILDER_NOT_USING_MARKET_SNAPSHOT_PRICE")
    builder_region_match = re.search(
        r"# Determine symbols/candidates to evaluate for TradeBuilder(.*?)eligibility_rows =",
        consumer,
        re.DOTALL,
    )
    builder_region = builder_region_match.group(1) if builder_region_match else consumer
    if re.search(r"spot_px\s*=\s*float\([^)]*(?:entry|valid_candidates.*ltp)", builder_region):
        errors.append("CODE:CANDIDATE_PRICE_USED_AS_MARKET_TRUTH")
    if "ranked_candidates" in builder_region or re.search(r"for\s+\w+\s+in\s+ranked\b", builder_region):
        errors.append("CODE:UI_RANKING_USED_CAUSALLY")

    if "snapshot_gen_at" in builder_region:
        errors.append("CODE:SNAPSHOT_GENERATION_TIME_USED_AS_EVENT_FALLBACK")
    if re.search(r"event_ts\s*=.*causal_cutoff", builder_region):
        errors.append("CODE:CAUSAL_CUTOFF_USED_AS_EVENT_TIMESTAMP_FALLBACK")
    if re.search(
        r"event_ts\s*=.*?(?:timestamp|quote_timestamp).*?or\s+snapshot_gen_at",
        builder_region,
        re.DOTALL,
    ):
        errors.append("CODE:EVENT_TIMESTAMP_HAS_NONMARKET_FALLBACK")
    if re.search(
        r"parse_iso_or_epoch_seconds\(event_ts\).*?except Exception:\s+pass",
        builder_region,
        re.DOTALL,
    ):
        errors.append("CODE:TIMESTAMP_PARSE_FAILURE_SWALLOWED")
    if "EVENT_TIMESTAMP_MISSING" not in builder_region and "EVENT_TIMESTAMP_INVALID" not in builder_region:
        errors.append("CODE:MISSING_TIMESTAMP_NOT_EXPLICITLY_BLOCKED")

    if 'trade["read_only"] = True' in consumer or 'market_data["read_only"] = True' in consumer:
        errors.append("CODE:POST_HOC_READ_ONLY_REWRITE_PRESENT")
    if "ExecutionRouter" in consumer or "place_order(" in consumer:
        errors.append("CODE:EXECUTION_PATH_PRESENT_IN_OBSERVER")
    if re.search(
        r'result\["consumers"\]\["trade_builder"\].*?isinstance\s*\(\s*ranked_pipeline',
        consumer,
        re.DOTALL,
    ):
        errors.append("CODE:TRADEBUILDER_TAUTOLOGICAL_PASS_PRESENT")

    hook = (repo_root / "core" / "trade_truth" / "truth_feed_runtime_hook.py").read_text(encoding="utf-8")
    if not re.search(r"class CheckpointSpan:.*?\n\s+span_id:\s*str", hook, re.DOTALL):
        errors.append("CODE:CHECKPOINT_SPAN_ID_MISSING")

    stages = build_runtime_authority_map()
    selection = [s for s in stages if s.authority == AuthorityKind.CANDIDATE_SELECTION]
    if len(selection) != 1:
        errors.append(f"CODE:CANDIDATE_SELECTION_AUTHORITY_COUNT:{len(selection)}")
    elif (
        selection[0].owner_module != "core.opportunity_engine"
        or selection[0].callable_name != "select_best_opportunity"
    ):
        errors.append("CODE:CANDIDATE_SELECTION_AUTHORITY_WRONG")

    return not errors, errors


def verify_pr905_evidence(evidence_root: Path, repo_root: Path = REPO_ROOT) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []
    report: dict[str, Any] = {
        "evidence_root": str(evidence_root),
        "status": "FAIL",
        "derived": {},
    }

    required = [
        "CHECKPOINT_PULSE_RUN1.jsonl",
        "CHECKPOINT_PULSE_RUN2.jsonl",
        "TRADEBUILDER_CAPTURED_CALLS.json",
        "TRADEBUILDER_INPUT_HASHES.json",
        "TRADEBUILDER_OUTPUT_HASHES.json",
        "TRACE_LINEAGE.json",
        "BROKER_WRITE_AUDIT.json",
        "CANDIDATE_SELECTION_AUTHORITY_AUDIT.json",
        "DETERMINISM_REPORT.json",
        "FUTURE_LEAK_AUDIT.json",
        "CANONICAL_RUNTIME_CALL_LEDGER.json",
    ]
    missing = [name for name in required if not (evidence_root / name).exists()]
    if missing:
        return False, [f"EVIDENCE:MISSING:{name}" for name in missing], report
    if (evidence_root / "PR905_IMPLEMENTATION_VERIFICATION.json").exists():
        errors.append("EVIDENCE:GENERATOR_SELF_CERTIFICATION_ARTIFACT_PRESENT")

    pulse1 = _load_jsonl(evidence_root / "CHECKPOINT_PULSE_RUN1.jsonl")
    pulse2 = _load_jsonl(evidence_root / "CHECKPOINT_PULSE_RUN2.jsonl")
    captured = _load_json(evidence_root / "TRADEBUILDER_CAPTURED_CALLS.json")
    input_art = _load_json(evidence_root / "TRADEBUILDER_INPUT_HASHES.json")
    output_art = _load_json(evidence_root / "TRADEBUILDER_OUTPUT_HASHES.json")
    lineage_art = _load_json(evidence_root / "TRACE_LINEAGE.json")
    broker = _load_json(evidence_root / "BROKER_WRITE_AUDIT.json")
    authority_art = _load_json(evidence_root / "CANDIDATE_SELECTION_AUTHORITY_AUDIT.json")
    future_art = _load_json(evidence_root / "FUTURE_LEAK_AUDIT.json")
    ledger = _load_json(evidence_root / "CANONICAL_RUNTIME_CALL_LEDGER.json")

    current_sha = _git("rev-parse", "HEAD", cwd=repo_root)
    for name, art in [
        ("captured", captured),
        ("input", input_art),
        ("output", output_art),
        ("lineage", lineage_art),
        ("broker", broker),
        ("authority", authority_art),
        ("future", future_art),
        ("ledger", ledger),
    ]:
        if art.get("candidate_sha") != current_sha:
            errors.append(f"EVIDENCE:SHA_MISMATCH:{name}:{art.get('candidate_sha')}:{current_sha}")
        if art.get("proof_type") != PROOF_TYPE:
            errors.append(f"EVIDENCE:PROOF_TYPE_INVALID:{name}:{art.get('proof_type')}")

    if ledger.get("live_verified") is not False:
        errors.append("EVIDENCE:LIVE_VERIFIED_MUST_BE_FALSE")
    if ledger.get("full_20_stage_runtime_observation") != "NOT_CLAIMED":
        errors.append("EVIDENCE:FULL_20_STAGE_CLAIM_NOT_ALLOWED")

    run1_cycle = str(captured.get("run1_cycle_id") or "")
    session_id = str(captured.get("session_id") or "")
    cutoff = captured.get("causal_data_cutoff")
    calls = list(captured.get("calls") or [])
    run1_calls = [c for c in calls if c.get("run") == "run1"]
    run2_calls = [c for c in calls if c.get("run") == "run2"]
    if len(run1_calls) != 1:
        errors.append(f"EVIDENCE:RUN1_TRADEBUILDER_CALL_COUNT:{len(run1_calls)}")
    if len(run2_calls) != 1:
        errors.append(f"EVIDENCE:RUN2_TRADEBUILDER_CALL_COUNT:{len(run2_calls)}")
    if ledger.get("observed_tradebuilder_call_count") != len(run1_calls):
        errors.append("EVIDENCE:LEDGER_CALL_COUNT_NOT_DERIVED_FROM_CAPTURE")

    cp_spans = [s for s in pulse1 if s.get("stage_name") == "CANDIDATE_POOL"]
    tb_spans = [s for s in pulse1 if s.get("stage_name") == "TRADE_BUILDER"]
    if len(cp_spans) != 1 or len(tb_spans) != 1:
        errors.append(f"EVIDENCE:LINEAGE_SPAN_COUNTS:cp={len(cp_spans)}:tb={len(tb_spans)}")
    else:
        cp = cp_spans[0]
        tb = tb_spans[0]
        if not cp.get("span_id") or not tb.get("span_id"):
            errors.append("EVIDENCE:SPAN_ID_MISSING")
        if tb.get("parent_span_id") != cp.get("span_id"):
            errors.append("EVIDENCE:PARENT_SPAN_NOT_ACTUAL_CANDIDATE_POOL_SPAN")
        if tb.get("trace_id") != cp.get("trace_id") or tb.get("trace_id") != run1_cycle:
            errors.append("EVIDENCE:TRACE_ID_NOT_CORRELATED")
        try:
            if float(cp.get("exited_at")) > float(tb.get("entered_at")):
                errors.append("EVIDENCE:PARENT_SPAN_ORDER_INVALID")
        except (TypeError, ValueError):
            errors.append("EVIDENCE:SPAN_TIMESTAMPS_INVALID")

        if lineage_art.get("candidate_pool_span") != cp:
            errors.append("EVIDENCE:LINEAGE_ARTIFACT_PARENT_NOT_RAW_PULSE")
        if lineage_art.get("trade_builder_span") != tb:
            errors.append("EVIDENCE:LINEAGE_ARTIFACT_TB_NOT_RAW_PULSE")

        if run1_calls:
            exact_inputs = [copy.deepcopy(c.get("input")) for c in run1_calls]
            expected_input_hash = compute_deterministic_hash(
                {
                    "cycle_id": run1_cycle,
                    "session_id": session_id,
                    "source_sha": current_sha,
                    "items": exact_inputs,
                }
            )
            report["derived"]["input_hash"] = expected_input_hash
            if tb.get("input_hash") != expected_input_hash:
                errors.append("EVIDENCE:CHECKPOINT_INPUT_HASH_MISMATCH")
            if input_art.get("recomputed_from_exact_captured_arguments") != expected_input_hash:
                errors.append("EVIDENCE:INPUT_ARTIFACT_HASH_MISMATCH")
            if input_art.get("captured_inputs") != exact_inputs:
                errors.append("EVIDENCE:INPUT_ARTIFACT_NOT_EXACT_CAPTURE")

            for item in exact_inputs:
                try:
                    if float(item.get("ltp")) != 24500.0:
                        errors.append(f"EVIDENCE:NONCANONICAL_MARKET_PRICE:{item.get('ltp')}")
                except (TypeError, ValueError):
                    errors.append("EVIDENCE:CAPTURED_LTP_INVALID")

            tb_state = dict(captured.get("run1_consumer_tradebuilder_state") or {})
            trades = [c.get("trade") for c in run1_calls if c.get("trade") is not None]
            traces = [c.get("trace") for c in run1_calls if c.get("trace")]
            reject_reasons = [c.get("reject_reason") for c in run1_calls if c.get("reject_reason")]
            expected_output_hash = compute_deterministic_hash(
                {
                    "trades": trades,
                    "traces": traces,
                    "result_status": tb_state.get("result_status"),
                    "reject_reasons": reject_reasons,
                    "cycle_id": run1_cycle,
                    "session_id": session_id,
                    "source_sha": current_sha,
                }
            )
            report["derived"]["output_hash"] = expected_output_hash
            if tb.get("output_hash") != expected_output_hash:
                errors.append("EVIDENCE:CHECKPOINT_OUTPUT_HASH_MISMATCH")
            if output_art.get("recomputed_from_exact_captured_results") != expected_output_hash:
                errors.append("EVIDENCE:OUTPUT_ARTIFACT_HASH_MISMATCH")
            if output_art.get("captured_native_trades") != trades:
                errors.append("EVIDENCE:OUTPUT_ARTIFACT_TRADES_NOT_EXACT_CAPTURE")
            if output_art.get("captured_traces") != traces:
                errors.append("EVIDENCE:OUTPUT_ARTIFACT_TRACES_NOT_EXACT_CAPTURE")

    expected_ledger_stages = [
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
    if ledger.get("observed_stages") != expected_ledger_stages:
        errors.append("EVIDENCE:LEDGER_CONTAINS_UNOBSERVED_OR_MUTATED_STAGE")

    cutoff_sec = _parse_timestamp(cutoff)
    event_values = [c.get("input", {}).get("event_timestamp") for c in run1_calls]
    event_secs = [_parse_timestamp(v) for v in event_values]
    if cutoff_sec is None or not event_secs or any(v is None for v in event_secs):
        derived_future = "UNKNOWN"
        errors.append("EVIDENCE:FUTURE_LEAK_NOT_DERIVABLE_FROM_CAPTURED_INPUT")
    else:
        derived_future = "FAIL" if max(float(v) for v in event_secs if v is not None) > cutoff_sec else "PASS"
        if derived_future != "PASS":
            errors.append("EVIDENCE:FUTURE_INPUT_AFTER_CAUSAL_CUTOFF")
    report["derived"]["future_leak_status"] = derived_future
    if future_art.get("status") != derived_future:
        errors.append("EVIDENCE:FUTURE_AUDIT_NOT_DERIVED_FROM_CAPTURED_INPUT")
    if future_art.get("captured_event_timestamps") != event_values:
        errors.append("EVIDENCE:FUTURE_AUDIT_TIMESTAMPS_NOT_EXACT_CAPTURE")

    call_counts = broker.get("call_counts")
    if not isinstance(call_counts, dict):
        errors.append("EVIDENCE:BROKER_CALL_COUNTS_MISSING")
        call_counts = {}
    try:
        broker_sum = sum(int(v) for v in call_counts.values())
    except Exception:
        broker_sum = -1
        errors.append("EVIDENCE:BROKER_CALL_COUNTS_INVALID")
    router_count = broker.get("execution_router_call_count")
    report["derived"]["broker_write_calls_total"] = broker_sum
    report["derived"]["execution_router_call_count"] = router_count
    if broker_sum != 0:
        errors.append(f"EVIDENCE:BROKER_WRITE_CALLS_NONZERO:{broker_sum}")
    if router_count != 0:
        errors.append(f"EVIDENCE:EXECUTION_ROUTER_CALLS_NONZERO:{router_count}")
    placed = sum(int(v) for k, v in call_counts.items() if "place_order" in k or "submit_order" in k)
    cancelled = sum(int(v) for k, v in call_counts.items() if "cancel_order" in k)
    modified = sum(int(v) for k, v in call_counts.items() if "modify_order" in k)
    if broker.get("orders_placed") != placed or broker.get("orders_cancelled") != cancelled or broker.get("orders_modified") != modified:
        errors.append("EVIDENCE:ORDER_COUNTERS_NOT_DERIVED_FROM_CALL_COUNTS")

    selection = [s for s in build_runtime_authority_map() if s.authority == AuthorityKind.CANDIDATE_SELECTION]
    report["derived"]["candidate_selection_authority_count"] = len(selection)
    if len(selection) != 1:
        errors.append(f"EVIDENCE:CANDIDATE_SELECTION_AUTHORITY_COUNT:{len(selection)}")
    artifact_authorities = list(authority_art.get("authorities") or [])
    if len(artifact_authorities) != len(selection):
        errors.append("EVIDENCE:AUTHORITY_ARTIFACT_COUNT_MISMATCH")

    if run1_calls:
        frozen_input = copy.deepcopy(run1_calls[0].get("input"))
        tb_a = TradeBuilder()
        ta, tra = tb_a.build_with_trace(copy.deepcopy(frozen_input), quick_mode=False, allow_fallbacks=False, allow_baseline=False)
        tb_b = TradeBuilder()
        tb, trb = tb_b.build_with_trace(copy.deepcopy(frozen_input), quick_mode=False, allow_fallbacks=False, allow_baseline=False)
        if _normalize_trade(ta) != _normalize_trade(tb) or _normalize_trace(tra) != _normalize_trace(trb):
            errors.append("EVIDENCE:INDEPENDENT_DETERMINISM_REPLAY_FAILED")

    report["status"] = "PASS" if not errors else "FAIL"
    return not errors, errors, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=None)
    args = parser.parse_args()

    short_sha = _git("rev-parse", "--short", "HEAD", cwd=args.repo_root)
    evidence_root = args.evidence_root or Path(
        f"/Volumes/TradeBotData/pr905-tradebuilder-canonical-proof-{short_sha}"
    )

    code_ok, code_errors = verify_pr905_codebase(args.repo_root)
    evidence_ok, evidence_errors, report = verify_pr905_evidence(evidence_root, args.repo_root)
    errors = code_errors + evidence_errors
    payload = {
        "overall_status": "PASS" if code_ok and evidence_ok else "FAIL",
        "codebase_verified": code_ok,
        "evidence_verified": evidence_ok,
        "evidence_report": report,
        "errors": errors,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if errors:
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
