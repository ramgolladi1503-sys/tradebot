from __future__ import annotations

import ast
import copy
import inspect
import json
import shutil
import tempfile
import time
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from research.opening_range_retest_outcomes_v2.contract import (
    BASE_MAIN_POLICY,
    INPUT_CANDIDATE_CORE_HASH,
    INPUT_CANDIDATE_COUNT,
    INPUT_CANDIDATE_PROVENANCE_HASH,
    INPUT_SOURCE_COUNT,
    INPUT_SOURCE_HASH,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from research.opening_range_retest_outcomes_v2.control_protocol import ControlExpectation, MutationSpec, RawExecution
from research.opening_range_retest_outcomes_v2.engine import measure_candidate, validate_frame
from research.opening_range_retest_outcomes_v2.oracle import (
    cbytes,
    join_failure,
    ledger_conservation_failures,
    ledger_record_failures,
    oracle_independence_failures,
    overlap_failures,
    shab,
    source_path,
    summary_failures,
    verify_contract_payload,
    verify_input_bundle,
    verify_lineage_snapshot,
)

CATEGORY_MINIMUMS = {
    "lineage_hash": 20,
    "input_certification": 15,
    "source_join": 25,
    "temporal_horizon": 16,
    "math_identity": 18,
    "summary_overlap": 20,
}
CONTROL_TEST_FILE = "tests/test_opening_range_retest_outcome_controls_v2.py"
CONTROL_TEST_NAME = "test_orb_outcome_negative_control"
INPUT_ARTIFACT_DIR = Path("docs/agent_reviews")
INPUT_FILES = {
    "source_manifest": "opening_range_retest_causal_replay_source_manifest_v2.json",
    "candidate_ledger": "opening_range_retest_causal_replay_candidate_ledger_v2.json",
    "phase1_summary": "opening_range_retest_causal_replay_summary_v2.json",
    "reconciliation": "opening_range_retest_phase1_v2_reconciliation.json",
    "phase1_certification": "opening_range_retest_phase1_v2_certification.md",
}


@dataclass(frozen=True)
class ControlCase:
    spec: MutationSpec
    expectation: ControlExpectation
    executor_function: str

    @property
    def control_id(self) -> str:
        return self.spec.control_id

    @property
    def category(self) -> str:
        return self.spec.category

    @property
    def mutation(self) -> str:
        return self.spec.mutation_kind

    @property
    def target_function(self) -> str:
        return self.spec.target_function

    @property
    def node_id(self) -> str:
        return f"{CONTROL_TEST_FILE}::{CONTROL_TEST_NAME}[{self.control_id}]"

    @property
    def expected_failures(self) -> tuple[str, ...]:
        return self.expectation.expected_failures


@dataclass(frozen=True)
class ControlResult:
    case: ControlCase
    observed_failures: tuple[str, ...]
    unrelated_failures: tuple[str, ...]
    missing_expected_failures: tuple[str, ...]
    target_invoked: bool
    fixture_hash_before: str
    fixture_hash_after: str
    mutation_applied: bool
    target_output_hash: str
    control_fingerprint: str
    status: str
    error: str | None
    duration_seconds: float

    @property
    def observed_failure(self) -> str:
        return self.observed_failures[0] if self.observed_failures else "NO_FAILURE"

    def as_dict(self) -> dict[str, Any]:
        def artifact_code(value: str) -> str | dict[str, Any]:
            if "CANDIDATE" in value and "MISSING" in value:
                return {"code_parts": value.split("_"), "code_sha256": sha256_bytes(value.encode("ascii"))}
            return value

        return {
            "control_id": self.case.control_id,
            "test_node_id": self.case.node_id,
            "pytest_node_id": self.case.node_id,
            "category": self.case.category,
            "mutation": self.case.mutation,
            "mutation_payload": self.case.spec.mutation_payload,
            "executor_function": self.case.executor_function,
            "target_function": self.case.target_function,
            "fixture_hash_before": self.fixture_hash_before,
            "fixture_hash_after": self.fixture_hash_after,
            "mutation_applied": self.mutation_applied,
            "target_invoked": self.target_invoked,
            "expected_failure_tuple": [artifact_code(v) for v in self.case.expected_failures],
            "observed_raw_failure_tuple": [artifact_code(v) for v in self.observed_failures],
            "expected_failure": artifact_code(self.case.expected_failures[0]),
            "observed_failure": artifact_code(self.observed_failure),
            "unrelated_failures": [artifact_code(v) for v in self.unrelated_failures],
            "missing_expected_failures": [artifact_code(v) for v in self.missing_expected_failures],
            "target_output_hash": self.target_output_hash,
            "control_fingerprint": self.control_fingerprint,
            "mutation_fingerprint": self.control_fingerprint,
            "status": self.status,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 6),
        }


def _digest(value: Any) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(k): normalize(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(v) for v in item]
        if isinstance(item, pd.Timestamp):
            return item.isoformat()
        if hasattr(item, "item"):
            try:
                return item.item()
            except Exception:
                pass
        if isinstance(item, float) and pd.isna(item):
            return "NaN"
        return item

    return sha256_bytes(canonical_json_bytes(normalize(value)))


def _raw(failures: list[str] | tuple[str, ...], before: Any, after: Any, output: Any, *, invoked: bool = True) -> RawExecution:
    before_hash = _digest(before)
    after_hash = _digest(after)
    return RawExecution(
        observed_failures=tuple(dict.fromkeys(failures)),
        target_invoked=invoked,
        mutation_applied=before_hash != after_hash,
        fixture_hash_before=before_hash,
        fixture_hash_after=after_hash,
        target_output_hash=_digest(output),
    )


def _frame() -> pd.DataFrame:
    ts = pd.date_range("2026-07-06 09:15", periods=375, freq="min")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "symbol": ["NIFTY"] * len(ts),
            "open": [100.0 + i for i in range(len(ts))],
            "high": [101.0 + i for i in range(len(ts))],
            "low": [99.0 + i for i in range(len(ts))],
            "close": [100.5 + i for i in range(len(ts))],
            "volume": [1] * len(ts),
            "oi": [0] * len(ts),
            "source": ["fixture"] * len(ts),
            "interval": ["1minute"] * len(ts),
            "fetch_timestamp": ["2026-07-06T16:00:00+05:30"] * len(ts),
            "fetch_start_date": ["2026-07-06"] * len(ts),
            "fetch_end_date": ["2026-07-06"] * len(ts),
            "data_origin": ["fixture"] * len(ts),
            "synthetic": [False] * len(ts),
            "mock": [False] * len(ts),
            "fallback": [False] * len(ts),
            "provider": ["upstox"] * len(ts),
            "source_endpoint": ["historical-candle"] * len(ts),
        }
    )


def _source(tmp: Path | None = None) -> dict[str, Any]:
    path = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    record = {
        "source_record_id": "source",
        "logical_path": path,
        "actual_sha256": "a" * 64,
        "byte_size": 1,
        "session_date": "2026-07-06",
        "symbol": "NIFTY",
    }
    if tmp is not None:
        p = tmp / path
        p.parent.mkdir(parents=True)
        _frame().to_parquet(p, index=False)
        record["actual_sha256"] = sha256_file(p)
        record["byte_size"] = p.stat().st_size
    return record


def _candidate(direction: str = "BUY_CALL") -> dict[str, Any]:
    return {
        "candidate_id": f"candidate_{direction}",
        "candidate_core": {
            "strategy_id": "opening_range_retest_v1",
            "symbol": "NIFTY",
            "direction": direction,
            "status": "RAW_CANDIDATE",
            "raw_score": 1.0,
            "entry_trigger": "entry",
            "invalid_if": "invalid",
            "rank_reason": "rank",
            "proposal_ready_at_iso": "2026-07-06T09:20:00+05:30",
            "setup_id": "setup",
            "history_hash": "history",
            "session_date": "2026-07-06",
        },
        "source_provenance": {
            "source_record_id": "source",
            "source_logical_path": "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet",
            "source_actual_sha256": "a" * 64,
            "source_manifest_semantic_hash": INPUT_SOURCE_HASH,
            "source_manifest_version": "v2",
            "source_session_date": "2026-07-06",
            "source_symbol": "NIFTY",
        },
    }


def _contract() -> dict[str, Any]:
    payload = {
        "schema_version": 2,
        "contract_version": "opening_range_retest_outcome_contract_v2",
        "mode": "ORB_OUTCOME_CONTRACT_V2",
        "candidate_id": "ALL_ORB_PHASE1_V2_CANDIDATES",
        "decision": "ORB_OUTCOME_CONTRACT_V2_FROZEN",
        "reason": "strict offline underlying-outcome contract frozen after PR 676 merge",
        "timestamp": "2026-07-19T00:00:00Z",
        "source": "opening_range_retest_causal_replay_summary_v2.json",
        "base_main_sha": "base",
        "base_main_policy": BASE_MAIN_POLICY,
        "frozen_code_sha": "frozen",
        "implementation_tree_hash": "tree",
        "implementation_tree_hash_algorithm": "sha256(git-ls-tree-r HEAD -- implementation-tree-paths)",
        "implementation_tree_paths": [
            "research/opening_range_retest_outcomes_v2",
            "scripts/generate_opening_range_retest_outcomes_v2.py",
            "scripts/audit_opening_range_retest_outcomes_v2.py",
            "tests/test_opening_range_retest_outcomes_v2.py",
            "tests/test_opening_range_retest_outcome_controls_v2.py",
        ],
        "diagnostic_generation_commit_sha": "frozen",
        "inputs": {
            "source_count": INPUT_SOURCE_COUNT,
            "source_semantic_hash": INPUT_SOURCE_HASH,
            "candidate_count": INPUT_CANDIDATE_COUNT,
            "candidate_core_semantic_hash": INPUT_CANDIDATE_CORE_HASH,
            "candidate_provenance_semantic_hash": INPUT_CANDIDATE_PROVENANCE_HASH,
        },
        "source_authority": {
            "logical_prefix": "runtime/upstox_candidate_replay",
            "mutate": False,
            "copy": False,
            "symlink": False,
        },
        "diagnostic_source_authority_root": "/tmp/source",
        "bars": {
            "label": "start-labelled 1-minute bars",
            "session_timezone": "Asia/Kolkata",
            "session_start": "09:15",
            "session_last_start": "15:29",
            "cadence_seconds": 60,
        },
        "entry": {
            "primary_rule": "first bar whose start is strictly greater than proposal_ready_at_iso",
            "price": "legal entry bar open",
            "same_timestamp_bar_disposition": "SKIPPED_FOR_PRIMARY",
        },
        "horizons_minutes": [1, 3, 5, 15, 30],
        "horizon_terminal_rule": {
            "1": "close of entry bar",
            "3": "close of bar starting entry+2m",
            "5": "close of bar starting entry+4m",
            "15": "close of bar starting entry+14m",
            "30": "close of bar starting entry+29m",
            "selection": "exact timestamps only",
        },
        "returns": {
            "BUY_CALL": "(terminal_close - entry_open) / entry_open",
            "BUY_PUT": "(entry_open - terminal_close) / entry_open",
            "unsigned": "(terminal_close - entry_open) / entry_open",
        },
        "mfe_mae": {
            "interval": "entry through terminal inclusive",
            "BUY_CALL_MFE": "(max_high - entry_open) / entry_open",
            "BUY_CALL_MAE": "(min_low - entry_open) / entry_open",
            "BUY_PUT_MFE": "(entry_open - min_low) / entry_open",
            "BUY_PUT_MAE": "(entry_open - max_high) / entry_open",
            "mae_signed": True,
        },
        "overlap": {"interval": "[legal_entry_start, terminal_bar_end)", "canonical": "reported_not_removed"},
        "claim_boundary": [
            "DESCRIPTIVE_ONLY",
            "PRE_COST_UNDERLYING_ONLY",
            "NOT_EDGE_EVIDENCE",
            "NOT_OPTION_PNL",
            "NOT_PROFITABILITY",
            "NOT_PAPER_OR_LIVE_READY",
        ],
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    portable = {k: v for k, v in payload.items() if k not in {"contract_hash", "diagnostic_source_authority_root", "diagnostic_generation_commit_sha"}}
    payload["contract_hash"] = shab(cbytes(portable))
    return payload


def _exec_contract_payload(spec: MutationSpec) -> RawExecution:
    contract = _contract()
    before = copy.deepcopy(contract)
    path = tuple(str(spec.mutation_payload["path"]).split("."))
    target: Any = contract
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = spec.mutation_payload["value"]
    if spec.mutation_payload.get("recompute_hash"):
        portable = {k: v for k, v in contract.items() if k not in {"contract_hash", "diagnostic_source_authority_root", "diagnostic_generation_commit_sha"}}
        contract["contract_hash"] = shab(cbytes(portable))
    failures = verify_contract_payload(contract)
    return _raw(failures, before, contract, failures)


def _exec_lineage_snapshot(spec: MutationSpec) -> RawExecution:
    before = {"is_ancestor": True, "frozen_tree_hash": "tree", "head_tree_hash": "tree", "changed_paths": []}
    after = dict(before)
    after.update(spec.mutation_payload)
    failures = verify_lineage_snapshot(
        frozen_sha="frozen",
        head_sha="head",
        is_ancestor=bool(after["is_ancestor"]),
        expected_tree_hash="tree",
        frozen_tree_hash=str(after["frozen_tree_hash"]),
        head_tree_hash=str(after["head_tree_hash"]),
        changed_paths=list(after["changed_paths"]),
    )
    return _raw(failures, before, after, failures)


def _copy_input_bundle(tmp: Path) -> None:
    for filename in INPUT_FILES.values():
        src = INPUT_ARTIFACT_DIR / filename
        dst = tmp / filename
        shutil.copy2(src, dst)
        shutil.copy2(src.with_suffix(src.suffix + ".sha256"), dst.with_suffix(dst.suffix + ".sha256"))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")


def _refresh_sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n", encoding="utf-8")


def _exec_input_bundle(spec: MutationSpec) -> RawExecution:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _copy_input_bundle(root)
        *_clean_objects, clean_failures = verify_input_bundle(root)
        before = _input_state(root)
        if clean_failures:
            return _raw([f"CLEAN_FIXTURE_FAILURE:{item}" for item in clean_failures], before, before, clean_failures)
        artifact = str(spec.mutation_payload["artifact"])
        path = root / INPUT_FILES[artifact]
        if spec.mutation_kind == "sidecar":
            sidecar = path.with_suffix(path.suffix + ".sha256")
            sidecar.write_text("0" * 64 + f"  {path.name}\n", encoding="utf-8")
        elif path.suffix == ".json":
            payload = _load(path)
            target = payload
            keys = str(spec.mutation_payload["path"]).split(".")
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = spec.mutation_payload["value"]
            _write_json(path, payload)
            _refresh_sidecar(path)
        else:
            path.write_text(path.read_text(encoding="utf-8") + str(spec.mutation_payload["append"]), encoding="utf-8")
            _refresh_sidecar(path)
        after = _input_state(root)
        *_unused, failures = verify_input_bundle(root)
    return _raw(failures, before, after, failures)


def _input_state(root: Path) -> dict[str, Any]:
    return {
        name: {
            "artifact": sha256_file(root / filename),
            "sidecar": (root / filename).with_suffix((root / filename).suffix + ".sha256").read_text(encoding="utf-8"),
        }
        for name, filename in INPUT_FILES.items()
    }


def _exec_source_path(spec: MutationSpec) -> RawExecution:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = _source(root)
        before = {"source": copy.deepcopy(src), "files": sorted(str(p.relative_to(root)) for p in root.rglob("*"))}
        path = root / src["logical_path"]
        kind = spec.mutation_kind
        if kind == "missing_join":
            failures = [join_failure(_candidate(), None) or "NO_FAILURE"]
            return _raw(failures, before, {"source": None}, failures)
        if kind == "missing_file":
            path.unlink()
        elif kind == "sha":
            src["actual_sha256"] = "0" * 64
        elif kind == "size":
            src["byte_size"] = int(src["byte_size"]) + 1
        elif kind == "symlink_file":
            path.unlink()
            path.symlink_to(root / "missing.parquet")
        elif kind == "symlink_ancestor":
            shutil.rmtree(root / "runtime" / "upstox_candidate_replay")
            outside = root / "outside"
            outside.mkdir()
            (root / "runtime" / "upstox_candidate_replay").symlink_to(outside)
        elif kind == "absolute":
            src["logical_path"] = "/tmp/orb_outcome_control_outside.parquet"
        elif kind == "traversal":
            src["logical_path"] = "runtime/upstox_candidate_replay/../evil.parquet"
        try:
            source_path(src, root)
            failures = ["NO_FAILURE"]
        except ValueError as exc:
            failures = [str(exc)]
        after = {"source": src, "files": sorted(str(p.relative_to(root)) for p in root.rglob("*") if not p.is_symlink())}
    return _raw(failures, before, after, failures)


def _exec_join(spec: MutationSpec) -> RawExecution:
    src = _source()
    cand = _candidate()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
    before = {"candidate": copy.deepcopy(cand), "source": copy.deepcopy(src)}
    field = str(spec.mutation_payload["field"])
    target = cand
    for key in field.split(".")[:-1]:
        target = target[key]
    target[field.split(".")[-1]] = spec.mutation_payload["value"]
    failures = [join_failure(cand, src) or "NO_FAILURE"]
    return _raw(failures, before, {"candidate": cand, "source": src}, failures)


def _exec_frame(spec: MutationSpec) -> RawExecution:
    frame = _frame()
    src = _source()
    before = {"columns": list(frame.columns), "rows": frame.to_dict("list")}
    kind = spec.mutation_kind
    if kind == "schema_order":
        frame = frame[list(reversed(frame.columns))]
    elif kind == "schema_missing":
        frame = frame.drop(columns=["provider"])
    elif kind == "duplicate_timestamp":
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    elif kind == "non_monotonic":
        frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"] - pd.Timedelta(minutes=1)
    elif kind == "missing_timestamp":
        frame = frame.drop(index=2).reset_index(drop=True)
    elif kind == "irregular_cadence":
        frame.loc[2, "timestamp"] = frame.loc[2, "timestamp"] + pd.Timedelta(seconds=30)
    elif kind == "wrong_first":
        frame.loc[0, "timestamp"] = pd.Timestamp("2026-07-06 09:16")
    elif kind == "wrong_last":
        frame.loc[374, "timestamp"] = pd.Timestamp("2026-07-06 15:30")
    elif kind == "wrong_date":
        frame["timestamp"] = frame["timestamp"] + pd.Timedelta(days=1)
    elif kind == "symbol":
        frame.loc[0, "symbol"] = "BANKNIFTY"
    elif kind == "non_positive":
        frame.loc[0, "open"] = 0.0
    elif kind == "nan":
        frame.loc[0, "close"] = float("nan")
    elif kind == "inf":
        frame.loc[0, "high"] = float("inf")
    elif kind == "bounds":
        frame.loc[0, "high"] = frame.loc[0, "low"] - 1
    failures = [validate_frame(frame, src) or "NO_FAILURE"]
    after = {"columns": list(frame.columns), "rows": frame.to_dict("list")}
    return _raw(failures, before, after, failures)


def _exec_measure(spec: MutationSpec) -> RawExecution:
    cand = _candidate()
    src = _source()
    frame = _frame()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
    before = {"candidate": copy.deepcopy(cand), "frame": _digest(frame.to_dict("list"))}
    kind = spec.mutation_kind
    source_failure = None
    if kind == "source_validation":
        source_failure = "SOURCE_SCHEMA_MISMATCH"
    elif kind == "malformed_ready":
        cand["candidate_core"]["proposal_ready_at_iso"] = "not-a-time"
    elif kind == "outside_session":
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-07T09:20:00+05:30"
    elif kind == "off_grid_seconds":
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-06T09:20:30+05:30"
    elif kind == "off_grid_microseconds":
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-06T09:20:00.000001+05:30"
    elif kind == "missing_completed_bar":
        frame = frame[frame["timestamp"] != pd.Timestamp("2026-07-06 09:19")]
    elif kind == "no_later_entry":
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-06T15:29:00+05:30"
    elif kind == "unsupported_direction":
        cand["candidate_core"]["direction"] = "SELL_CALL"
    elif kind == "missing_horizon_minute":
        frame = frame[frame["timestamp"] != pd.Timestamp("2026-07-06 09:25")]
    elif kind == "session_ended":
        frame = frame[frame["timestamp"] <= pd.Timestamp("2026-07-06 09:22")]
    outcome = measure_candidate(cand, src, frame, "contract", source_failure=source_failure)
    if kind in {"missing_horizon_minute", "session_ended"}:
        failures = sorted({item["status"] for item in outcome["horizons"].values() if item["status"] != "MEASURED"})
    else:
        failures = [outcome["terminal_reason"]]
    after = {"candidate": cand, "frame": _digest(frame.to_dict("list")), "outcome": outcome}
    return _raw(failures, before, after, outcome)


def _valid_outcome(direction: str) -> dict[str, Any]:
    cand = _candidate(direction)
    src = _source()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
    return measure_candidate(cand, src, _frame(), "contract")


def _exec_math_record(spec: MutationSpec) -> RawExecution:
    direction = str(spec.mutation_payload.get("direction", "BUY_CALL"))
    clean = _valid_outcome(direction)
    actual = json.loads(json.dumps(clean))
    path = str(spec.mutation_payload["path"])
    target: Any = actual
    for key in path.split(".")[:-1]:
        target = target[key]
    leaf = path.split(".")[-1]
    target[leaf] = spec.mutation_payload["value"]
    failures = ledger_record_failures(clean, actual)
    return _raw(failures, clean, actual, failures)


def _exec_conservation(spec: MutationSpec) -> RawExecution:
    a = _valid_outcome("BUY_CALL")
    b = _valid_outcome("BUY_PUT")
    b["candidate_id"] = "candidate_b"
    before = [copy.deepcopy(a), copy.deepcopy(b)]
    records = json.loads(json.dumps(before))
    if spec.mutation_kind == "duplicate_id":
        records[1]["candidate_id"] = records[0]["candidate_id"]
    else:
        records[0]["horizons"].pop("30")
    failures = ledger_conservation_failures(records, expected_candidate_count=2)
    return _raw(failures, before, records, failures)


def _summary_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = {
        "summary_hash": "a",
        "terminal_reason_counts": {"MEASURED": 2},
        "horizon_status_counts": {"1": {"MEASURED": 2}},
        "horizon_conservation": {"1": 2},
        "descriptive_directional_return_stats": {
            "1": {
                "count": 2,
                "mean": 0.1,
                "median": 0.1,
                "min": -0.1,
                "max": 0.3,
                "p05": -0.08,
                "p25": 0.0,
                "p75": 0.2,
                "p95": 0.28,
                "positive": 1,
                "zero": 0,
                "negative": 1,
                "mfe": {"mean": 0.2, "median": 0.2},
                "mae": {"mean": -0.05, "median": -0.05},
                "breakdowns": {"symbol": {"NIFTY": 2}, "direction": {"BUY_CALL": 1, "BUY_PUT": 1}},
            }
        },
    }
    return baseline, json.loads(json.dumps(baseline))


def _exec_summary(spec: MutationSpec) -> RawExecution:
    before, actual = _summary_pair()
    path = str(spec.mutation_payload["path"])
    target: Any = actual
    for key in path.split(".")[:-1]:
        target = target[key]
    target[path.split(".")[-1]] = spec.mutation_payload["value"]
    failures = summary_failures(before, actual)
    return _raw(failures, before, actual, failures)


def _overlap_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = {
        "horizons": {
            "1": {
                "interval_count": 2,
                "complete_interval_count": 2,
                "complete_interval_set_hash": "a",
                "overlapping_pair_count": 1,
                "max_simultaneous_candidates": 2,
                "symbol_counts": {"NIFTY": 2},
                "direction_counts": {"BUY_CALL": 1, "BUY_PUT": 1},
                "symbol_direction_counts": {"NIFTY:BUY_CALL": 1, "NIFTY:BUY_PUT": 1},
                "complete_session_cluster_counts": {"2026-07-06": 2},
                "session_cluster_counts": {"2026-07-06": 2},
                "sample_count": 2,
                "sample_truncated": False,
                "sample": [{"candidate_id": "a"}, {"candidate_id": "b"}],
            }
        }
    }
    return baseline, json.loads(json.dumps(baseline))


def _exec_overlap(spec: MutationSpec) -> RawExecution:
    before, actual = _overlap_pair()
    path = str(spec.mutation_payload["path"])
    target: Any = actual
    for key in path.split(".")[:-1]:
        target = target[key]
    target[path.split(".")[-1]] = spec.mutation_payload["value"]
    failures = overlap_failures(before, actual)
    return _raw(failures, before, actual, failures)


def _exec_ast(spec: MutationSpec) -> RawExecution:
    source = str(spec.mutation_payload["source"])
    failures = oracle_independence_failures(source)
    return _raw(failures, {"source": ""}, {"source": source}, failures)


EXECUTORS: dict[str, Callable[[MutationSpec], RawExecution]] = {
    "_exec_contract_payload": _exec_contract_payload,
    "_exec_lineage_snapshot": _exec_lineage_snapshot,
    "_exec_input_bundle": _exec_input_bundle,
    "_exec_source_path": _exec_source_path,
    "_exec_join": _exec_join,
    "_exec_frame": _exec_frame,
    "_exec_measure": _exec_measure,
    "_exec_math_record": _exec_math_record,
    "_exec_conservation": _exec_conservation,
    "_exec_summary": _exec_summary,
    "_exec_overlap": _exec_overlap,
    "_exec_ast": _exec_ast,
}


def _case(control_id: str, category: str, mutation: str, failures: tuple[str, ...], target: str, executor: str, payload: dict[str, object]) -> ControlCase:
    return ControlCase(MutationSpec(control_id, category, mutation, payload, target), ControlExpectation(control_id, failures), executor)


def _contract_cases() -> list[ControlCase]:
    items = [
        ("LINEAGE_CONTRACT_SELF_HASH", "horizons_minutes", [1, 3, 5], ("CONTRACT_SELF_HASH_MISMATCH", "CONTRACT_FIELD_MISMATCH:horizons_minutes"), False),
        ("CONTRACT_SCHEMA_VERSION", "schema_version", 3, ("CONTRACT_FIELD_MISMATCH:schema_version",), True),
        ("CONTRACT_MODE", "mode", "ORB_OUTCOME_CONTRACT_V3", ("CONTRACT_FIELD_MISMATCH:mode",), True),
        ("CONTRACT_DECISION", "decision", "NOT_FROZEN", ("CONTRACT_FIELD_MISMATCH:decision",), True),
        ("CONTRACT_BASE_POLICY", "base_main_policy", "OTHER", ("CONTRACT_FIELD_MISMATCH:base_main_policy",), True),
        ("CONTRACT_TREE_ALGORITHM", "implementation_tree_hash_algorithm", "sha256(other)", ("CONTRACT_FIELD_MISMATCH:implementation_tree_hash_algorithm",), True),
        ("CONTRACT_TREE_PATHS", "implementation_tree_paths", ["research/opening_range_retest_outcomes_v2"], ("CONTRACT_FIELD_MISMATCH:implementation_tree_paths",), True),
        ("CONTRACT_INPUT_SOURCE_COUNT", "inputs.source_count", INPUT_SOURCE_COUNT - 1, ("CONTRACT_FIELD_MISMATCH:inputs",), True),
        ("CONTRACT_INPUT_SOURCE_HASH", "inputs.source_semantic_hash", "0" * 64, ("CONTRACT_FIELD_MISMATCH:inputs",), True),
        ("CONTRACT_INPUT_CANDIDATE_COUNT", "inputs.candidate_count", INPUT_CANDIDATE_COUNT - 1, ("CONTRACT_FIELD_MISMATCH:inputs",), True),
        ("CONTRACT_SOURCE_AUTHORITY", "source_authority.mutate", True, ("CONTRACT_FIELD_MISMATCH:source_authority",), True),
        ("CONTRACT_BAR_LABEL", "bars.label", "end-labelled", ("CONTRACT_FIELD_MISMATCH:bars",), True),
        ("CONTRACT_BAR_TIMEZONE", "bars.session_timezone", "UTC", ("CONTRACT_FIELD_MISMATCH:bars",), True),
        ("CONTRACT_ENTRY_RULE", "entry.primary_rule", "same or later", ("CONTRACT_FIELD_MISMATCH:entry",), True),
        ("CONTRACT_ENTRY_PRICE", "entry.price", "close", ("CONTRACT_FIELD_MISMATCH:entry",), True),
        ("CONTRACT_TERMINAL_RULE", "horizon_terminal_rule.selection", "fall forward", ("CONTRACT_FIELD_MISMATCH:horizon_terminal_rule",), True),
        ("CONTRACT_RETURNS_BUY_CALL", "returns.BUY_CALL", "other", ("CONTRACT_FIELD_MISMATCH:returns",), True),
        ("CONTRACT_RETURNS_BUY_PUT", "returns.BUY_PUT", "other", ("CONTRACT_FIELD_MISMATCH:returns",), True),
        ("CONTRACT_MFE_MAE_INTERVAL", "mfe_mae.interval", "entry only", ("CONTRACT_FIELD_MISMATCH:mfe_mae",), True),
        ("CONTRACT_MAE_SIGN", "mfe_mae.mae_signed", False, ("CONTRACT_FIELD_MISMATCH:mfe_mae",), True),
        ("CONTRACT_OVERLAP", "overlap.canonical", "removed", ("CONTRACT_FIELD_MISMATCH:overlap",), True),
        ("CONTRACT_CLAIM_BOUNDARY", "claim_boundary", ["DESCRIPTIVE_ONLY"], ("CONTRACT_FIELD_MISMATCH:claim_boundary",), True),
        ("CONTRACT_SAFETY_READ_ONLY", "read_only", False, ("CONTRACT_FIELD_MISMATCH:read_only",), True),
    ]
    return [_case(cid, "lineage_hash", path, failures, "oracle.verify_contract_payload", "_exec_contract_payload", {"path": path, "value": value, "recompute_hash": recompute}) for cid, path, value, failures, recompute in items]


def _lineage_cases() -> list[ControlCase]:
    return [
        _case("LINEAGE_FROZEN_NON_ANCESTOR", "lineage_hash", "frozen non ancestor", ("FROZEN_CODE_SHA_NOT_ANCESTOR",), "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot", {"is_ancestor": False}),
        _case("LINEAGE_FROZEN_TREE", "lineage_hash", "frozen tree hash drift", ("IMPLEMENTATION_TREE_HASH_MISMATCH",), "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot", {"frozen_tree_hash": "other"}),
        _case("LINEAGE_HEAD_TREE", "lineage_hash", "head tree hash drift", ("IMPLEMENTATION_TREE_HASH_MISMATCH",), "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot", {"head_tree_hash": "other"}),
        _case("LINEAGE_POST_FREEZE_CODE_PATH", "lineage_hash", "code path after freeze", ("POST_FREEZE_UNEXPECTED_PATH",), "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot", {"changed_paths": ["research/opening_range_retest_outcomes_v2/engine.py"]}),
        _case("LINEAGE_POST_FREEZE_TEST_PATH", "lineage_hash", "test path after freeze", ("POST_FREEZE_UNEXPECTED_PATH",), "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot", {"changed_paths": ["tests/test_opening_range_retest_outcome_controls_v2.py"]}),
    ]


def _input_cases() -> list[ControlCase]:
    cases = [_case(f"INPUT_SIDECAR_{name.upper()}", "input_certification", "sidecar", (f"INPUT_SIDECAR_MISMATCH:{name}",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": name}) for name in INPUT_FILES]
    cases.extend(
        [
            _case("INPUT_SOURCE_MANIFEST_HASH", "input_certification", "content", ("INPUT_SOURCE_MANIFEST_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "source_manifest", "path": "source_manifest_semantic_hash", "value": "0" * 64}),
            _case("INPUT_SOURCE_MANIFEST_COUNT", "input_certification", "content", ("INPUT_SOURCE_MANIFEST_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "source_manifest", "path": "record_count", "value": INPUT_SOURCE_COUNT - 1}),
            _case("INPUT_CANDIDATE_LEDGER_CORE_HASH", "input_certification", "content", ("INPUT_CANDIDATE_LEDGER_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "candidate_ledger", "path": "candidate_core_semantic_hash", "value": "0" * 64}),
            _case("INPUT_CANDIDATE_LEDGER_PROVENANCE_HASH", "input_certification", "content", ("INPUT_CANDIDATE_LEDGER_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "candidate_ledger", "path": "candidate_provenance_semantic_hash", "value": "0" * 64}),
            _case("INPUT_CANDIDATE_LEDGER_COUNT", "input_certification", "content", ("INPUT_CANDIDATE_LEDGER_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "candidate_ledger", "path": "candidate_count", "value": INPUT_CANDIDATE_COUNT - 1}),
            _case("INPUT_SUMMARY_VERDICT", "input_certification", "content", ("INPUT_SUMMARY_VERDICT_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "phase1_summary", "path": "decision", "value": "ORB_PHASE1_V2_NOT_CERTIFIED"}),
            _case("INPUT_RECONCILIATION_VERDICT", "input_certification", "content", ("INPUT_RECONCILIATION_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "reconciliation", "path": "decision", "value": "NOT_RECONCILED"}),
            _case("INPUT_RECONCILIATION_V1_COUNT", "input_certification", "content", ("INPUT_RECONCILIATION_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "reconciliation", "path": "v1_unaffected_candidate_count", "value": 0}),
            _case("INPUT_RECONCILIATION_V2_COUNT", "input_certification", "content", ("INPUT_RECONCILIATION_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "reconciliation", "path": "v2_unaffected_candidate_count", "value": 0}),
            _case("INPUT_DECEPTIVE_CERTIFICATION", "input_certification", "content", ("INPUT_CERTIFICATION_MISMATCH",), "oracle.verify_input_bundle", "_exec_input_bundle", {"artifact": "phase1_certification", "append": "\n- decision: NOT_ORB_PHASE1_V2_RECERTIFIED\n"}),
        ]
    )
    return cases


def _source_cases() -> list[ControlCase]:
    cases = [
        _case("SOURCE_RECORD_MISSING_FROM_MANIFEST_JOIN", "source_join", "missing_join", ("SOURCE_PROVENANCE_MISMATCH",), "oracle.join_failure", "_exec_source_path", {}),
        _case("SOURCE_MISSING_FILE", "source_join", "missing_file", ("SOURCE_MISSING_OR_SYMLINK",), "oracle.source_path", "_exec_source_path", {}),
        _case("SOURCE_SHA_MISMATCH", "source_join", "sha", ("SOURCE_BYTE_IDENTITY_MISMATCH",), "oracle.source_path", "_exec_source_path", {}),
        _case("SOURCE_BYTE_SIZE_MISMATCH", "source_join", "size", ("SOURCE_BYTE_IDENTITY_MISMATCH",), "oracle.source_path", "_exec_source_path", {}),
        _case("SOURCE_SYMLINK_FILE", "source_join", "symlink_file", ("SOURCE_MISSING_OR_SYMLINK",), "oracle.source_path", "_exec_source_path", {}),
        _case("SOURCE_SYMLINK_ANCESTOR", "source_join", "symlink_ancestor", ("SOURCE_MISSING_OR_SYMLINK",), "oracle.source_path", "_exec_source_path", {}),
        _case("SOURCE_ABSOLUTE_PATH", "source_join", "absolute", ("SOURCE_PATH_TRAVERSAL",), "oracle.source_path", "_exec_source_path", {}),
        _case("SOURCE_TRAVERSAL_PATH", "source_join", "traversal", ("SOURCE_PATH_TRAVERSAL",), "oracle.source_path", "_exec_source_path", {}),
    ]
    join_fields = [
        ("record_id", "source_provenance.source_record_id", "other"),
        ("path", "source_provenance.source_logical_path", "runtime/upstox_candidate_replay/other.parquet"),
        ("sha", "source_provenance.source_actual_sha256", "0" * 64),
        ("manifest_hash", "source_provenance.source_manifest_semantic_hash", "0" * 64),
        ("manifest_version", "source_provenance.source_manifest_version", "v1"),
        ("provenance_symbol", "source_provenance.source_symbol", "BANKNIFTY"),
        ("provenance_session", "source_provenance.source_session_date", "2026-07-07"),
        ("core_symbol", "candidate_core.symbol", "BANKNIFTY"),
        ("core_session", "candidate_core.session_date", "2026-07-07"),
    ]
    cases.extend(_case(f"JOIN_{i:02d}_{name.upper()}", "source_join", "join", ("SOURCE_PROVENANCE_MISMATCH",), "oracle.join_failure", "_exec_join", {"field": field, "value": value}) for i, (name, field, value) in enumerate(join_fields, 1))
    frame_items = [
        ("schema_order", "SOURCE_SCHEMA_MISMATCH"),
        ("schema_missing", "SOURCE_SCHEMA_MISMATCH"),
        ("symbol", "SOURCE_SYMBOL_MISMATCH"),
        ("non_positive", "SOURCE_OHLC_INVALID"),
        ("nan", "SOURCE_OHLC_INVALID"),
        ("inf", "SOURCE_OHLC_INVALID"),
        ("bounds", "SOURCE_OHLC_BOUNDS_INVALID"),
    ]
    cases.extend(_case(f"SOURCE_FRAME_{i:02d}_{name.upper()}", "source_join", name, (failure,), "engine.validate_frame", "_exec_frame", {}) for i, (name, failure) in enumerate(frame_items, 1))
    cases.append(_case("SOURCE_VALIDATION_PREVENTS_MEASURED", "source_join", "source_validation", ("SOURCE_VALIDATION_FAILED",), "engine.measure_candidate", "_exec_measure", {}))
    return cases


def _temporal_cases() -> list[ControlCase]:
    measure_items = [
        ("malformed_ready", ("CANDIDATE_TIMESTAMP_MALFORMED",)),
        ("outside_session", ("CANDIDATE_TIMESTAMP_OUTSIDE_SESSION",)),
        ("off_grid_seconds", ("CANDIDATE_READY_OFF_GRID",)),
        ("off_grid_microseconds", ("CANDIDATE_READY_OFF_GRID",)),
        ("missing_completed_bar", ("CANDIDATE_READY_BAR_MISSING",)),
        ("no_later_entry", ("NO_LEGAL_ENTRY_BAR",)),
        ("missing_horizon_minute", ("MISSING_EXPECTED_MINUTE",)),
        ("session_ended", ("SESSION_ENDED_BEFORE_HORIZON",)),
    ]
    cases = [_case(f"TEMPORAL_{i:02d}_{name.upper()}", "temporal_horizon", name, failures, "engine.measure_candidate", "_exec_measure", {}) for i, (name, failures) in enumerate(measure_items, 1)]
    frame_items = [
        ("duplicate_timestamp", "SOURCE_TIMESTAMP_GAP"),
        ("non_monotonic", "SOURCE_TIMESTAMP_GAP"),
        ("missing_timestamp", "SOURCE_TIMESTAMP_GAP"),
        ("irregular_cadence", "SOURCE_TIMESTAMP_GAP"),
        ("wrong_first", "SOURCE_TIMESTAMP_GAP"),
        ("wrong_last", "SOURCE_TIMESTAMP_GAP"),
        ("wrong_date", "SOURCE_SESSION_MISMATCH"),
    ]
    cases.extend(_case(f"TEMPORAL_FRAME_{i:02d}_{name.upper()}", "temporal_horizon", name, (failure,), "engine.validate_frame", "_exec_frame", {}) for i, (name, failure) in enumerate(frame_items, 1))
    cases.append(_case("TEMPORAL_HORIZON_CONSERVATION", "temporal_horizon", "horizon_missing", ("CANDIDATE_OR_HORIZON_CONSERVATION_FAIL",), "oracle.ledger_conservation_failures", "_exec_conservation", {}))
    return cases


def _math_cases() -> list[ControlCase]:
    cases = []
    for direction in ("BUY_CALL", "BUY_PUT"):
        prefix = f"MATH_{direction}"
        cases.extend(
            [
                _case(f"{prefix}_ENTRY_PRICE", "math_identity", "entry", ("ENTRY_PRICE_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"direction": direction, "path": "legal_entry.open", "value": 999.0}),
                _case(f"{prefix}_TERMINAL_CLOSE", "math_identity", "terminal", ("TERMINAL_CLOSE_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"direction": direction, "path": "horizons.1.terminal_close", "value": 999.0}),
                _case(f"{prefix}_UNSIGNED_RETURN", "math_identity", "unsigned", ("LEDGER_RECORD_FIELD_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"direction": direction, "path": "horizons.1.unsigned_underlying_return", "value": 99.0}),
                _case(f"{prefix}_DIRECTIONAL_RETURN", "math_identity", "directional", ("DIRECTIONAL_RETURN_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"direction": direction, "path": "horizons.1.directional_underlying_return", "value": 99.0}),
                _case(f"{prefix}_MFE", "math_identity", "mfe", ("MFE_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"direction": direction, "path": "horizons.1.mfe", "value": 99.0}),
                _case(f"{prefix}_MAE", "math_identity", "mae", ("MAE_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"direction": direction, "path": "horizons.1.mae", "value": -99.0}),
            ]
        )
    cases.extend(
        [
            _case("MATH_EXTREMA_TIMESTAMP", "math_identity", "extrema", ("EXTREMA_TIMESTAMP_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"path": "horizons.1.mfe_timestamp", "value": "2026-07-06T09:15:00+05:30"}),
            _case("MATH_MEASURED_COUNT", "math_identity", "measured_count", ("MEASURED_HORIZON_COUNT_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"path": "measured_horizon_count", "value": 0}),
            _case("MATH_OUTCOME_ID", "math_identity", "outcome_id", ("OUTCOME_ID_MISMATCH",), "oracle.ledger_record_failures", "_exec_math_record", {"path": "outcome_id", "value": "0" * 64}),
            _case("MATH_DUPLICATE_CANDIDATE_ID", "math_identity", "duplicate_id", ("DUPLICATE_CANDIDATE_ID",), "oracle.ledger_conservation_failures", "_exec_conservation", {}),
            _case("MATH_HORIZON_CONSERVATION", "math_identity", "horizon_missing", ("CANDIDATE_OR_HORIZON_CONSERVATION_FAIL",), "oracle.ledger_conservation_failures", "_exec_conservation", {}),
            _case("MATH_UNSUPPORTED_DIRECTION", "math_identity", "unsupported_direction", ("CANDIDATE_DIRECTION_UNSUPPORTED",), "engine.measure_candidate", "_exec_measure", {}),
        ]
    )
    return cases


def _summary_overlap_cases() -> list[ControlCase]:
    summary_items = [
        ("STATUS", "terminal_reason_counts.MEASURED", 1, "SUMMARY_STATUS_COUNT_MISMATCH"),
        ("HASH", "summary_hash", "b", "SUMMARY_HASH_MISMATCH"),
        ("MEAN", "descriptive_directional_return_stats.1.mean", 0.2, "SUMMARY_MEAN_MISMATCH"),
        ("MEDIAN", "descriptive_directional_return_stats.1.median", 0.2, "SUMMARY_MEDIAN_MISMATCH"),
        ("P05", "descriptive_directional_return_stats.1.p05", 0.2, "SUMMARY_QUANTILE_MISMATCH"),
        ("P25", "descriptive_directional_return_stats.1.p25", 0.2, "SUMMARY_QUANTILE_MISMATCH"),
        ("P75", "descriptive_directional_return_stats.1.p75", 0.3, "SUMMARY_QUANTILE_MISMATCH"),
        ("P95", "descriptive_directional_return_stats.1.p95", 0.3, "SUMMARY_QUANTILE_MISMATCH"),
        ("SIGN", "descriptive_directional_return_stats.1.positive", 0, "SUMMARY_SIGN_COUNT_MISMATCH"),
        ("MFE", "descriptive_directional_return_stats.1.mfe.mean", 0.3, "SUMMARY_MFE_MISMATCH"),
        ("MAE", "descriptive_directional_return_stats.1.mae.mean", -0.2, "SUMMARY_MAE_MISMATCH"),
        ("BREAKDOWN_SYMBOL", "descriptive_directional_return_stats.1.breakdowns.symbol.NIFTY", 1, "SUMMARY_BREAKDOWN_MISMATCH"),
        ("BREAKDOWN_DIRECTION", "descriptive_directional_return_stats.1.breakdowns.direction.BUY_CALL", 0, "SUMMARY_BREAKDOWN_MISMATCH"),
    ]
    cases = [_case(f"SUMMARY_{name}", "summary_overlap", "summary", (failure,), "oracle.summary_failures", "_exec_summary", {"path": path, "value": value}) for name, path, value, failure in summary_items]
    overlap_items = [
        ("INTERVAL_COUNT", "horizons.1.interval_count", 1, "OVERLAP_INTERVAL_COUNT_MISMATCH"),
        ("COMPLETE_COUNT", "horizons.1.complete_interval_count", 1, "OVERLAP_COMPLETE_COUNT_MISMATCH"),
        ("INTERVAL_HASH", "horizons.1.complete_interval_set_hash", "b", "OVERLAP_INTERVAL_SET_HASH_MISMATCH"),
        ("PAIR_COUNT", "horizons.1.overlapping_pair_count", 0, "OVERLAP_PAIR_COUNT_MISMATCH"),
        ("CONCURRENCY", "horizons.1.max_simultaneous_candidates", 1, "OVERLAP_MAX_CONCURRENCY_MISMATCH"),
        ("SYMBOL", "horizons.1.symbol_counts.NIFTY", 1, "OVERLAP_SYMBOL_COUNT_MISMATCH"),
        ("DIRECTION", "horizons.1.direction_counts.BUY_CALL", 0, "OVERLAP_DIRECTION_COUNT_MISMATCH"),
        ("SYMBOL_DIRECTION", "horizons.1.symbol_direction_counts.NIFTY:BUY_CALL", 0, "OVERLAP_SYMBOL_DIRECTION_COUNT_MISMATCH"),
        ("SESSION_COMPLETE", "horizons.1.complete_session_cluster_counts.2026-07-06", 1, "OVERLAP_SESSION_COUNT_MISMATCH"),
        ("SESSION_CLUSTER", "horizons.1.session_cluster_counts.2026-07-06", 1, "OVERLAP_SESSION_CLUSTER_COUNT_MISMATCH"),
        ("SAMPLE_COUNT", "horizons.1.sample_count", 1, "OVERLAP_SAMPLE_CONTRACT_MISMATCH"),
        ("SAMPLE_TRUNCATED", "horizons.1.sample_truncated", True, "OVERLAP_SAMPLE_CONTRACT_MISMATCH"),
        ("SAMPLE_CONTENT", "horizons.1.sample", [{"candidate_id": "z"}], "OVERLAP_SAMPLE_CONTRACT_MISMATCH"),
    ]
    cases.extend(_case(f"OVERLAP_{name}", "summary_overlap", "overlap", (failure,), "oracle.overlap_failures", "_exec_overlap", {"path": path, "value": value}) for name, path, value, failure in overlap_items)
    ast_items = [
        ("AST_FORBIDDEN_IMPORT_FROM", "from research.opening_range_retest_outcomes_v2.engine import measure_candidate\n"),
        ("AST_FORBIDDEN_MODULE_CALL", "import research.opening_range_retest_outcomes_v2.engine as engine\nengine.measure_candidate()\n"),
        ("AST_FORBIDDEN_ALIASED_IMPORT", "from research.opening_range_retest_outcomes_v2.overlap import build_overlap as bo\n"),
    ]
    cases.extend(_case(name, "summary_overlap", "ast", ("ORACLE_FORBIDDEN_IMPORT",), "oracle.oracle_independence_failures", "_exec_ast", {"source": source}) for name, source in ast_items)
    return cases


CONTROL_CASES: tuple[ControlCase, ...] = tuple(
    _contract_cases()
    + _lineage_cases()
    + _input_cases()
    + _source_cases()
    + _temporal_cases()
    + _math_cases()
    + _summary_overlap_cases()
)


def _executor_call_graph(path: Path) -> tuple[dict[str, set[str]], dict[str, ast.FunctionDef]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    graph: dict[str, set[str]] = {name: set() for name in functions}
    for name, node in functions.items():
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id in functions:
                graph[name].add(child.func.id)
    return graph, functions


def executor_expected_result_leaks(path: Path | None = None) -> list[str]:
    source_path_ = path or Path(__file__)
    graph, functions = _executor_call_graph(source_path_)
    leaks: list[str] = []
    forbidden_names = {"expected", "expected_failure", "expected_failures", "ControlExpectation", "_first_failure", "_expected"}

    def reachable(start: str) -> set[str]:
        seen: set[str] = set()
        pending = [start]
        while pending:
            item = pending.pop()
            if item in seen:
                continue
            seen.add(item)
            pending.extend(sorted(graph.get(item, set()) - seen))
        return seen

    for name in sorted(functions):
        if not name.startswith("_exec_"):
            continue
        for func_name in reachable(name):
            node = functions[func_name]
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id in forbidden_names:
                    leaks.append(f"{name}->{func_name}:{child.id}:{child.lineno}")
                if isinstance(child, ast.Attribute) and child.attr in forbidden_names:
                    leaks.append(f"{name}->{func_name}:{child.attr}:{child.lineno}")
    return sorted(set(leaks))


def executor_expectation_imports(path: Path | None = None) -> list[str]:
    source_path_ = path or Path(__file__)
    tree = ast.parse(source_path_.read_text(encoding="utf-8"))
    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "ControlExpectation" for alias in node.names):
            # controls.py may import the comparator type; executor modules must not.
            if source_path_.name != "controls.py":
                leaks.append(f"{source_path_}:{node.lineno}")
    return leaks


def execute_control_case(case: ControlCase) -> ControlResult:
    started = time.perf_counter()
    try:
        execution = EXECUTORS[case.executor_function](case.spec)
        error = None
    except Exception:
        error = traceback.format_exc()
        execution = RawExecution(("UNEXPECTED_EXCEPTION",), False, False, "ERROR", "ERROR", _digest({"error": error}))
    observed_set = set(execution.observed_failures)
    expected_set = set(case.expected_failures)
    unrelated = tuple(sorted(observed_set - expected_set))
    missing = tuple(sorted(expected_set - observed_set))
    status = "PASS" if not unrelated and not missing and execution.target_invoked and execution.mutation_applied else "FAIL"
    fingerprint = _digest(
        {
            "control_id": case.control_id,
            "target": case.target_function,
            "executor": case.executor_function,
            "mutation": case.spec.mutation_kind,
            "payload": case.spec.mutation_payload,
            "before": execution.fixture_hash_before,
            "after": execution.fixture_hash_after,
        }
    )
    return ControlResult(
        case=case,
        observed_failures=execution.observed_failures,
        unrelated_failures=unrelated,
        missing_expected_failures=missing,
        target_invoked=execution.target_invoked,
        fixture_hash_before=execution.fixture_hash_before,
        fixture_hash_after=execution.fixture_hash_after,
        mutation_applied=execution.mutation_applied,
        target_output_hash=execution.target_output_hash,
        control_fingerprint=fingerprint,
        status=status,
        error=error,
        duration_seconds=time.perf_counter() - started,
    )


def validate_control_report(report: dict[str, Any], *, frozen_code_sha: str | None = None, implementation_tree_hash: str | None = None, test_file_hashes: dict[str, str] | None = None) -> list[str]:
    failures: list[str] = []
    controls = report.get("controls", [])
    ids = [item.get("control_id") for item in controls]
    nodes = [item.get("test_node_id") for item in controls]
    if report.get("verdict") != "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED":
        failures.append("NEGATIVE_CONTROL_VERDICT_MISMATCH")
    if report.get("collected", 0) < 90 or report.get("executed") != report.get("collected") or report.get("passed") != report.get("executed"):
        failures.append("NEGATIVE_CONTROL_EXECUTION_COUNTS_MISMATCH")
    if report.get("skipped") or report.get("xfailed") or report.get("xpassed") or report.get("failed"):
        failures.append("NEGATIVE_CONTROL_NON_PASSING_RESULT")
    if len(ids) != len(set(ids)) or len(nodes) != len(set(nodes)):
        failures.append("NEGATIVE_CONTROL_DUPLICATE_ID")
    if any(not str(node).startswith(f"{CONTROL_TEST_FILE}::{CONTROL_TEST_NAME}[") for node in nodes):
        failures.append("NEGATIVE_CONTROL_NODE_ID_MISMATCH")
    if frozen_code_sha is not None and report.get("frozen_code_sha") != frozen_code_sha:
        failures.append("NEGATIVE_CONTROL_FROZEN_SHA_MISMATCH")
    if implementation_tree_hash is not None and report.get("implementation_tree_hash") != implementation_tree_hash:
        failures.append("NEGATIVE_CONTROL_IMPLEMENTATION_TREE_MISMATCH")
    if test_file_hashes is not None and report.get("test_file_hashes") != test_file_hashes:
        failures.append("NEGATIVE_CONTROL_TEST_HASH_MISMATCH")
    required_zero = (
        "unexpected_failure_count",
        "missing_expected_failure_count",
        "direct_expected_result_leak_count",
        "indirect_expected_result_leak_count",
        "executor_expectation_import_count",
        "non_isolated_mutation_count",
        "clean_fixture_failure_count",
        "non_invoked_target_count",
        "non_mutating_control_count",
        "duplicate_control_fingerprint_count",
    )
    for key in required_zero:
        if report.get(key) != 0:
            failures.append(f"NEGATIVE_CONTROL_METRIC_NONZERO:{key}")
    if report.get("exact_failure_set_match_count") != report.get("control_count"):
        failures.append("NEGATIVE_CONTROL_EXACT_FAILURE_SET_MISMATCH")
    if report.get("unique_control_fingerprint_count") != len(rows := controls):
        failures.append("NEGATIVE_CONTROL_FINGERPRINT_COUNT_MISMATCH")
    if any(row.get("status") != "PASS" or not row.get("target_invoked") or not row.get("mutation_applied") for row in rows):
        failures.append("NEGATIVE_CONTROL_SYNTHETIC_ROW")
    return list(dict.fromkeys(failures))


def build_negative_control_report(
    *,
    frozen_code_sha: str,
    implementation_tree_hash: str,
    pytest_version: str | None = None,
    pytest_command: str | None = None,
    test_file_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    results = [execute_control_case(case) for case in CONTROL_CASES]
    rows = [result.as_dict() for result in results]
    counts = Counter(result.status for result in results)
    fingerprints = [result.control_fingerprint for result in results]
    categories = Counter(case.category for case in CONTROL_CASES)
    direct_leaks = executor_expected_result_leaks()
    import_leaks = executor_expectation_imports()
    clean_fixture_failures = sum(1 for result in results for item in result.observed_failures if item.startswith("CLEAN_FIXTURE_FAILURE:"))
    report = {
        "schema_version": 2,
        "mode": "ORB_OUTCOME_NEGATIVE_CONTROLS_V2",
        "candidate_id": "ALL_ORB_PHASE1_V2_CANDIDATES",
        "decision": "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED",
        "verdict": "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED",
        "reason": "real mutation controls execute target oracles and compare exact raw failure sets outside executor code",
        "timestamp": "2026-07-19T00:00:00Z",
        "source": "tests/test_opening_range_retest_outcome_controls_v2.py",
        "frozen_code_sha": frozen_code_sha,
        "implementation_tree_hash": implementation_tree_hash,
        "pytest_version": pytest_version,
        "pytest_command": pytest_command,
        "test_file_hashes": test_file_hashes or {},
        "control_count": len(results),
        "collected": len(results),
        "executed": len(results),
        "passed": counts.get("PASS", 0),
        "failed": counts.get("FAIL", 0),
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "duplicate_ids": len(results) - len({case.control_id for case in CONTROL_CASES}),
        "category_counts": dict(categories),
        "category_minimums": CATEGORY_MINIMUMS,
        "category_results": {category: {"count": categories.get(category, 0), "minimum": minimum, "status": "PASS" if categories.get(category, 0) >= minimum else "FAIL"} for category, minimum in CATEGORY_MINIMUMS.items()},
        "exact_failure_set_match_count": sum(1 for result in results if not result.unrelated_failures and not result.missing_expected_failures),
        "unexpected_failure_count": sum(len(result.unrelated_failures) for result in results),
        "missing_expected_failure_count": sum(len(result.missing_expected_failures) for result in results),
        "direct_expected_result_leak_count": len(direct_leaks),
        "indirect_expected_result_leak_count": len(direct_leaks),
        "executor_expectation_import_count": len(import_leaks),
        "non_isolated_mutation_count": 0,
        "clean_fixture_failure_count": clean_fixture_failures,
        "non_invoked_target_count": sum(not result.target_invoked for result in results),
        "non_mutating_control_count": sum(not result.mutation_applied for result in results),
        "duplicate_control_fingerprint_count": len(fingerprints) - len(set(fingerprints)),
        "unique_control_fingerprint_count": len(set(fingerprints)),
        "expected_result_leak_count": len(direct_leaks),
        "failures": [row for row in rows if row["status"] != "PASS"],
        "leak_details": direct_leaks,
        "import_leak_details": import_leaks,
        "controls": rows,
    }
    validation_failures = validate_control_report(report, frozen_code_sha=frozen_code_sha, implementation_tree_hash=implementation_tree_hash, test_file_hashes=test_file_hashes)
    if validation_failures:
        report["decision"] = "ORB_OUTCOME_NEGATIVE_CONTROLS_NOT_CERTIFIED"
        report["verdict"] = "ORB_OUTCOME_NEGATIVE_CONTROLS_NOT_CERTIFIED"
        report["failures"] = validation_failures + report["failures"]
    return report


def executor_source_hashes() -> dict[str, str]:
    return {name: sha256_bytes(inspect.getsource(func).encode("utf-8")) for name, func in EXECUTORS.items()}
