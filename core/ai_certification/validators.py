from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Callable

from .bundle import BundleError, CertificationBundle, sha256_file
from .contracts import EvidenceRef, GateResult, GateStatus, StrategyVerdict
from .policy import CertificationPolicy


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _ref(bundle: CertificationBundle, artifact: str, pointer: str = "") -> EvidenceRef:
    expected = bundle.artifacts.get(artifact)
    return EvidenceRef(artifact=artifact, pointer=pointer, sha256=expected)


def _pass(gate: str, reason: str, summary: str, *refs: EvidenceRef, mandatory: bool = True, details: dict[str, Any] | None = None) -> GateResult:
    return GateResult(gate, GateStatus.PASS, reason, summary, mandatory, tuple(refs), details or {})


def _fail(gate: str, reason: str, summary: str, *refs: EvidenceRef, mandatory: bool = True, details: dict[str, Any] | None = None) -> GateResult:
    return GateResult(gate, GateStatus.FAIL, reason, summary, mandatory, tuple(refs), details or {})


def _unevaluated(gate: str, reason: str, summary: str, *refs: EvidenceRef, mandatory: bool = True, details: dict[str, Any] | None = None) -> GateResult:
    return GateResult(gate, GateStatus.UNEVALUATED, reason, summary, mandatory, tuple(refs), details or {})


def validate_manifest(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    gate = "bundle_manifest"
    required_fields = (
        "bundle_schema_version",
        "run_id",
        "strategy_id",
        "repository_commit",
        "created_at",
        "policy_version",
        "artifacts",
    )
    missing = [field for field in required_fields if not bundle.manifest.get(field)]
    if missing:
        return _unevaluated(gate, "MANIFEST_FIELDS_MISSING", "Bundle manifest is incomplete.", EvidenceRef("bundle_manifest.json"), details={"missing": missing})
    if str(bundle.manifest.get("bundle_schema_version")) != policy.required_bundle_schema:
        return _fail(gate, "UNSUPPORTED_BUNDLE_SCHEMA", "Bundle schema is not allowed by the active policy.", EvidenceRef("bundle_manifest.json", "/bundle_schema_version"), details={"expected": policy.required_bundle_schema, "actual": bundle.manifest.get("bundle_schema_version")})
    if str(bundle.manifest.get("policy_version")) != policy.version:
        return _fail(gate, "POLICY_VERSION_MISMATCH", "Bundle was not produced for the active certification policy.", EvidenceRef("bundle_manifest.json", "/policy_version"), details={"expected": policy.version, "actual": bundle.manifest.get("policy_version")})
    artifacts = bundle.artifacts
    missing_artifacts = [name for name in policy.required_artifacts if name not in artifacts or not bundle.artifact_path(name).is_file()]
    if missing_artifacts:
        return _unevaluated(gate, "REQUIRED_ARTIFACTS_MISSING", "One or more mandatory evidence artifacts are unavailable.", EvidenceRef("bundle_manifest.json", "/artifacts"), details={"missing": missing_artifacts})
    invalid_paths: list[str] = []
    for name in artifacts:
        try:
            bundle.artifact_path(name)
        except BundleError:
            invalid_paths.append(name)
    if invalid_paths:
        return _fail(gate, "UNSAFE_ARTIFACT_PATH", "Manifest contains artifact paths outside the bundle root.", EvidenceRef("bundle_manifest.json", "/artifacts"), details={"paths": invalid_paths})
    return _pass(gate, "MANIFEST_VALID", "Bundle manifest and mandatory artifact inventory are valid.", EvidenceRef("bundle_manifest.json"))


def validate_hashes(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    del policy
    gate = "artifact_hashes"
    mismatches: list[dict[str, str]] = []
    invalid_hashes: list[str] = []
    missing: list[str] = []
    unsafe_paths: list[str] = []
    for name, expected in sorted(bundle.artifacts.items()):
        if not isinstance(expected, str) or not _SHA256_RE.fullmatch(expected):
            invalid_hashes.append(name)
            continue
        try:
            path = bundle.artifact_path(name)
        except BundleError:
            unsafe_paths.append(name)
            continue
        if not path.is_file():
            missing.append(name)
            continue
        observed = sha256_file(path)
        if observed != expected:
            mismatches.append({"artifact": name, "expected": expected, "observed": observed})
    if unsafe_paths:
        return _fail(gate, "UNSAFE_ARTIFACT_PATH", "Manifest contains artifact paths outside the bundle root.", EvidenceRef("bundle_manifest.json", "/artifacts"), details={"paths": unsafe_paths})
    if missing:
        return _unevaluated(gate, "HASHED_ARTIFACT_MISSING", "A hashed artifact is missing.", EvidenceRef("bundle_manifest.json", "/artifacts"), details={"missing": missing})
    if invalid_hashes:
        return _fail(gate, "INVALID_SHA256", "Manifest contains invalid SHA-256 values.", EvidenceRef("bundle_manifest.json", "/artifacts"), details={"artifacts": invalid_hashes})
    if mismatches:
        return _fail(gate, "ARTIFACT_HASH_MISMATCH", "One or more evidence artifacts changed after the bundle was frozen.", EvidenceRef("bundle_manifest.json", "/artifacts"), details={"mismatches": mismatches})
    return _pass(gate, "ARTIFACT_HASHES_VERIFIED", "All frozen evidence artifact hashes match.", EvidenceRef("bundle_manifest.json", "/artifacts"))


def validate_source_authority(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    gate = "source_authority"
    try:
        identity = bundle.read_json("engine_identity.json")
        config = bundle.read_json("run_configuration.json")
    except BundleError as exc:
        return _unevaluated(gate, "SOURCE_IDENTITY_UNAVAILABLE", str(exc), _ref(bundle, "engine_identity.json"), _ref(bundle, "run_configuration.json"))
    actual_engine = str(identity.get("engine_module", ""))
    actual_wfa = str(identity.get("wfa_engine_module", ""))
    mode = str(config.get("execution_mode", ""))
    forbidden = bool(identity.get("legacy_or_proxy_path_used", False)) or bool(identity.get("hardcoded_metrics_used", False))
    problems: list[str] = []
    if actual_engine != policy.allowed_engine:
        problems.append("ENGINE_NOT_CERTIFYING")
    if actual_wfa != policy.allowed_wfa_engine:
        problems.append("WFA_NOT_CERTIFYING")
    if mode != policy.required_execution_mode:
        problems.append("EXECUTION_MODE_NOT_STRICT")
    if forbidden:
        problems.append("FORBIDDEN_EVIDENCE_PRODUCER")
    if problems:
        return _fail(gate, problems[0], "Evidence was not produced exclusively by the certifying strict option-replay path.", _ref(bundle, "engine_identity.json"), _ref(bundle, "run_configuration.json"), details={"problems": problems, "engine": actual_engine, "wfa_engine": actual_wfa, "execution_mode": mode})
    return _pass(gate, "CERTIFYING_SOURCE_CONFIRMED", "Engine, WFA path, and execution mode match the certifying authority.", _ref(bundle, "engine_identity.json"), _ref(bundle, "run_configuration.json"))


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_data_provenance(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    del policy
    gate = "data_provenance"
    try:
        data = bundle.read_json("dataset_manifest.json")
    except BundleError as exc:
        return _unevaluated(gate, "DATASET_MANIFEST_UNAVAILABLE", str(exc), _ref(bundle, "dataset_manifest.json"))
    required = ("dataset_sha256", "row_count", "time_start", "time_end", "provider", "symbol", "expiry")
    missing = [field for field in required if data.get(field) in (None, "")]
    if missing:
        return _unevaluated(gate, "DATASET_PROVENANCE_INCOMPLETE", "Dataset provenance is missing mandatory fields.", _ref(bundle, "dataset_manifest.json"), details={"missing": missing})
    problems: list[str] = []
    if not _SHA256_RE.fullmatch(str(data.get("dataset_sha256", ""))):
        problems.append("INVALID_DATASET_HASH")
    if int(data.get("row_count", 0) or 0) <= 0:
        problems.append("EMPTY_DATASET")
    start, end = _parse_iso(data.get("time_start")), _parse_iso(data.get("time_end"))
    if start is None or end is None or start >= end:
        problems.append("INVALID_DATASET_TIME_RANGE")
    zero_required = (
        "duplicate_timestamp_count",
        "missing_timestamp_count",
        "malformed_timestamp_count",
        "stale_quote_count",
        "post_expiry_row_count",
        "invalid_ohlc_count",
    )
    for field in zero_required:
        if int(data.get(field, 0) or 0) != 0:
            problems.append(field.upper())
    if not bool(data.get("quote_columns_complete", False)):
        problems.append("QUOTE_COLUMNS_INCOMPLETE")
    if not bool(data.get("contract_metadata_complete", False)):
        problems.append("CONTRACT_METADATA_INCOMPLETE")
    if problems:
        return _fail(gate, problems[0], "Dataset provenance or strict replay eligibility failed.", _ref(bundle, "dataset_manifest.json"), details={"problems": problems})
    return _pass(gate, "DATASET_PROVENANCE_VALID", "Dataset identity, chronology, quote completeness, and contract metadata are valid.", _ref(bundle, "dataset_manifest.json"))


def validate_temporal_causality(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    del policy
    gate = "temporal_causality"
    try:
        data = bundle.read_json("timing_evidence.json")
    except BundleError as exc:
        return _unevaluated(gate, "TIMING_EVIDENCE_UNAVAILABLE", str(exc), _ref(bundle, "timing_evidence.json"))
    required = ("signals_checked", "future_mutation_stable", "elapsed_hold_verified")
    missing = [field for field in required if field not in data]
    if missing:
        return _unevaluated(gate, "TIMING_EVIDENCE_INCOMPLETE", "Temporal evidence is incomplete.", _ref(bundle, "timing_evidence.json"), details={"missing": missing})
    problems: list[str] = []
    if int(data.get("signals_checked", 0) or 0) <= 0:
        problems.append("NO_SIGNALS_CHECKED")
    count_fields = (
        "same_event_entry_count",
        "chronology_violation_count",
        "missing_timing_provenance_count",
        "future_data_dependency_count",
    )
    for field in count_fields:
        if int(data.get(field, 0) or 0) != 0:
            problems.append(field.upper())
    if not bool(data.get("future_mutation_stable", False)):
        problems.append("FUTURE_MUTATION_UNSTABLE")
    if not bool(data.get("elapsed_hold_verified", False)):
        problems.append("ELAPSED_HOLD_NOT_VERIFIED")
    if problems:
        return _fail(gate, problems[0], "Signal, entry, exit, or future-mutation causality failed.", _ref(bundle, "timing_evidence.json"), details={"problems": problems})
    return _pass(gate, "TEMPORAL_CAUSALITY_VALID", "Signal timing, legal entry chronology, future-mutation stability, and elapsed-time holds are valid.", _ref(bundle, "timing_evidence.json"))


def validate_execution_realism(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    del policy
    gate = "execution_realism"
    try:
        data = bundle.read_json("fill_evidence.json")
    except BundleError as exc:
        return _unevaluated(gate, "FILL_EVIDENCE_UNAVAILABLE", str(exc), _ref(bundle, "fill_evidence.json"))
    required = ("entries_use_executable_side", "exits_use_executable_side", "strict_liquidity_mode", "cost_monotonicity_verified")
    missing = [field for field in required if field not in data]
    if missing:
        return _unevaluated(gate, "FILL_EVIDENCE_INCOMPLETE", "Execution evidence is incomplete.", _ref(bundle, "fill_evidence.json"), details={"missing": missing})
    problems: list[str] = []
    for field in required:
        if not bool(data.get(field, False)):
            problems.append(field.upper())
    count_fields = (
        "fallback_liquidity_fill_count",
        "proxy_exit_mark_count",
        "missing_bid_ask_accepted_count",
        "synthetic_liquidity_fill_count",
    )
    for field in count_fields:
        if int(data.get(field, 0) or 0) != 0:
            problems.append(field.upper())
    if problems:
        return _fail(gate, problems[0], "Executable-side fill or strict liquidity evidence failed.", _ref(bundle, "fill_evidence.json"), details={"problems": problems})
    return _pass(gate, "EXECUTION_REALISM_VALID", "Entries, exits, liquidity, and adverse cost behavior satisfy strict execution evidence.", _ref(bundle, "fill_evidence.json"))


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_financial_reconciliation(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    del policy
    gate = "financial_reconciliation"
    try:
        data = bundle.read_json("cost_reconciliation.json")
    except BundleError as exc:
        return _unevaluated(gate, "RECONCILIATION_UNAVAILABLE", str(exc), _ref(bundle, "cost_reconciliation.json"))
    numeric_fields = ("gross_pnl", "total_costs", "net_pnl", "trade_net_pnl_sum")
    numbers = {field: _finite_number(data.get(field)) for field in numeric_fields}
    if any(value is None for value in numbers.values()):
        return _unevaluated(gate, "RECONCILIATION_FIELDS_MISSING", "Financial reconciliation lacks finite numeric values.", _ref(bundle, "cost_reconciliation.json"), details={"fields": numbers})
    tolerance = float(data.get("tolerance", 1e-8) or 1e-8)
    problems: list[str] = []
    if abs((numbers["gross_pnl"] - numbers["total_costs"]) - numbers["net_pnl"]) > tolerance:
        problems.append("GROSS_COST_NET_MISMATCH")
    if abs(numbers["trade_net_pnl_sum"] - numbers["net_pnl"]) > tolerance:
        problems.append("TRADE_NET_SUM_MISMATCH")
    trades = int(data.get("total_trades", -1) or 0)
    components = sum(int(data.get(field, 0) or 0) for field in ("winning_trades", "losing_trades", "flat_trades"))
    if trades < 0 or components != trades:
        problems.append("TRADE_COUNT_MISMATCH")
    if int(data.get("ambiguity_count", 0) or 0) != 0:
        problems.append("AMBIGUITY_PRESENT")
    if problems:
        return _fail(gate, problems[0], "Gross P&L, costs, net P&L, or trade counts do not reconcile.", _ref(bundle, "cost_reconciliation.json"), details={"problems": problems})
    return _pass(gate, "FINANCIALS_RECONCILE", "Gross P&L, explicit costs, net P&L, and trade counts reconcile.", _ref(bundle, "cost_reconciliation.json"))


def validate_wfa_integrity(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    gate = "walk_forward_integrity"
    try:
        plan = bundle.read_json("wfa_partition_plan.json")
        result = bundle.read_json("wfa_results.json")
    except BundleError as exc:
        return _unevaluated(gate, "WFA_EVIDENCE_UNAVAILABLE", str(exc), _ref(bundle, "wfa_partition_plan.json"), _ref(bundle, "wfa_results.json"))
    bool_fields = (
        "chronological",
        "non_overlapping",
        "purge_embargo_applied",
        "validation_before_holdout",
        "holdout_isolated_from_selection",
    )
    missing = [field for field in bool_fields if field not in plan]
    if missing:
        return _unevaluated(gate, "WFA_PLAN_INCOMPLETE", "Walk-forward partition evidence is incomplete.", _ref(bundle, "wfa_partition_plan.json"), details={"missing": missing})
    problems: list[str] = []
    for field in bool_fields:
        if not bool(plan.get(field, False)):
            problems.append(field.upper())
    if int(result.get("repeated_holdout_run_count", 0) or 0) > 1:
        problems.append("REPEATED_HOLDOUT_USE")
    if int(result.get("contamination_count", 0) or 0) > policy.maximum_contamination_count:
        problems.append("WFA_CONTAMINATION")
    if not bool(result.get("known_setup_regime_oos", False)):
        problems.append("UNKNOWN_SETUP_REGIME_OOS")
    holdout_fraction = _finite_number(result.get("holdout_fraction"))
    if holdout_fraction is None or holdout_fraction < policy.minimum_holdout_fraction:
        problems.append("INSUFFICIENT_HOLDOUT_FRACTION")
    if problems:
        return _fail(gate, problems[0], "Walk-forward chronology, isolation, metadata, or contamination gates failed.", _ref(bundle, "wfa_partition_plan.json"), _ref(bundle, "wfa_results.json"), details={"problems": problems})
    return _pass(gate, "WFA_INTEGRITY_VALID", "Walk-forward partitions are chronological, buffered, isolated, and uncontaminated.", _ref(bundle, "wfa_partition_plan.json"), _ref(bundle, "wfa_results.json"))


def validate_negative_controls(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    gate = "negative_controls"
    try:
        data = bundle.read_json("negative_controls.json")
    except BundleError as exc:
        return _unevaluated(gate, "NEGATIVE_CONTROLS_UNAVAILABLE", str(exc), _ref(bundle, "negative_controls.json"))
    controls = data.get("controls")
    if not isinstance(controls, dict):
        return _unevaluated(gate, "NEGATIVE_CONTROLS_INCOMPLETE", "Negative-control artifact has no controls map.", _ref(bundle, "negative_controls.json"))
    missing = [name for name in policy.required_negative_controls if name not in controls]
    failed = [name for name in policy.required_negative_controls if name in controls and controls.get(name) is not True]
    if missing:
        return _unevaluated(gate, "NEGATIVE_CONTROLS_MISSING", "Mandatory negative controls are absent.", _ref(bundle, "negative_controls.json", "/controls"), details={"missing": missing})
    if failed:
        return _fail(gate, "NEGATIVE_CONTROL_FAILED", "One or more controls failed to invalidate broken causality or adverse assumptions.", _ref(bundle, "negative_controls.json", "/controls"), details={"failed": failed})
    return _pass(gate, "NEGATIVE_CONTROLS_PASS", "Future mutation, timing shift, and cost sensitivity controls passed.", _ref(bundle, "negative_controls.json", "/controls"))


def validate_test_evidence(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    del policy
    gate = "test_evidence"
    try:
        data = bundle.read_json("test_results.json")
    except BundleError as exc:
        return _unevaluated(gate, "TEST_EVIDENCE_UNAVAILABLE", str(exc), _ref(bundle, "test_results.json"))
    if int(data.get("collected", 0) or 0) <= 0:
        return _unevaluated(gate, "NO_TESTS_COLLECTED", "No test execution evidence was collected.", _ref(bundle, "test_results.json"))
    if int(data.get("failed", 0) or 0) != 0 or int(data.get("errors", 0) or 0) != 0:
        return _fail(gate, "TESTS_NOT_GREEN", "Focused certification tests contain failures or errors.", _ref(bundle, "test_results.json"), details={"failed": data.get("failed"), "errors": data.get("errors")})
    if not bool(data.get("commit_matches_bundle", False)):
        return _fail(gate, "TEST_COMMIT_MISMATCH", "Test results do not belong to the bundle repository commit.", _ref(bundle, "test_results.json"))
    return _pass(gate, "TEST_EVIDENCE_VALID", "Focused tests passed on the repository commit recorded by the bundle.", _ref(bundle, "test_results.json"))


def validate_strategy_result(bundle: CertificationBundle, policy: CertificationPolicy) -> GateResult:
    gate = "strategy_result_consistency"
    try:
        data = bundle.read_json("strategy_result.json")
    except BundleError as exc:
        return _unevaluated(gate, "STRATEGY_RESULT_UNAVAILABLE", str(exc), _ref(bundle, "strategy_result.json"), mandatory=False)
    declared = str(data.get("verdict", ""))
    allowed = {item.value for item in StrategyVerdict if item not in (StrategyVerdict.INVALID_DUE_TO_DATA, StrategyVerdict.INVALID_DUE_TO_LEAKAGE, StrategyVerdict.WITHHELD)}
    if declared not in allowed:
        return _fail(gate, "UNKNOWN_STRATEGY_VERDICT", "Strategy result uses an unsupported verdict.", _ref(bundle, "strategy_result.json", "/verdict"), mandatory=False, details={"declared": declared})
    trades = int(data.get("trades", 0) or 0)
    expectancy = _finite_number(data.get("after_cost_expectancy"))
    profit_factor = _finite_number(data.get("profit_factor"))
    problems: list[str] = []
    computed = declared
    if trades < policy.minimum_trades:
        computed = StrategyVerdict.INSUFFICIENT_TRADES.value
    elif declared == StrategyVerdict.STRUCTURAL_EDGE_SUPPORTED.value:
        if expectancy is None or expectancy <= 0:
            problems.append("NON_POSITIVE_EXPECTANCY")
        if profit_factor is None or profit_factor < policy.minimum_profit_factor:
            problems.append("PROFIT_FACTOR_BELOW_POLICY")
    elif declared == StrategyVerdict.NO_STRUCTURAL_EDGE.value and expectancy is not None and expectancy > 0 and profit_factor is not None and profit_factor >= policy.minimum_profit_factor:
        problems.append("NEGATIVE_VERDICT_CONTRADICTS_METRICS")
    if problems:
        return _fail(gate, problems[0], "Declared strategy conclusion conflicts with policy-controlled metrics.", _ref(bundle, "strategy_result.json"), mandatory=False, details={"problems": problems, "computed_verdict": computed})
    return _pass(gate, "STRATEGY_RESULT_CONSISTENT", "Strategy conclusion is consistent with the recorded metrics and policy thresholds.", _ref(bundle, "strategy_result.json"), mandatory=False, details={"computed_verdict": computed})


Validator = Callable[[CertificationBundle, CertificationPolicy], GateResult]


DEFAULT_VALIDATORS: tuple[Validator, ...] = (
    validate_manifest,
    validate_hashes,
    validate_source_authority,
    validate_data_provenance,
    validate_temporal_causality,
    validate_execution_realism,
    validate_financial_reconciliation,
    validate_wfa_integrity,
    validate_negative_controls,
    validate_test_evidence,
    validate_strategy_result,
)
