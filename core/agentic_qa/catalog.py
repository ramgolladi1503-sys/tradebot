from __future__ import annotations

from .contracts import ControlDefinition, Severity


def _c(
    number: int,
    domain: str,
    title: str,
    description: str,
    severity: Severity,
    hard_fail: bool,
    rule: str,
    key: str,
    expected: object = True,
) -> ControlDefinition:
    return ControlDefinition(
        control_id=f"AQ-{number:02d}",
        domain=domain,
        title=title,
        description=description,
        severity=severity,
        hard_fail=hard_fail,
        rule=rule,
        key=key,
        expected=expected,
    )


CONTROL_CATALOG: tuple[ControlDefinition, ...] = (
    _c(1, "isolation_authority", "Isolated execution context", "Audit runs outside the live checkout and never on main.", Severity.CRITICAL, True, "is_true", "execution_context.isolated"),
    _c(2, "isolation_authority", "Read-only evidence access", "The auditor consumes frozen evidence without mutating source artifacts.", Severity.CRITICAL, True, "is_true", "authority.read_only"),
    _c(3, "isolation_authority", "No broker or order authority", "The agentic layer has no broker, order placement, cancellation, or modification capability.", Severity.CRITICAL, True, "is_true", "authority.no_broker_tools"),
    _c(4, "isolation_authority", "No live runtime mutation", "The package cannot alter feed, strategy, ranking, risk, execution, or broker modules.", Severity.CRITICAL, True, "is_true", "authority.no_live_runtime_mutation"),
    _c(5, "isolation_authority", "Deterministic verdict ownership", "Only deterministic policy code owns the final audit verdict.", Severity.CRITICAL, True, "equals", "authority.verdict_owner", "deterministic"),
    _c(6, "isolation_authority", "Agent advisory boundary", "LLM output may critique or explain but cannot promote or override.", Severity.CRITICAL, True, "is_true", "authority.agent_advisory_only"),
    _c(7, "isolation_authority", "Human approval boundary", "Promotion beyond research requires explicit human approval.", Severity.CRITICAL, True, "is_true", "governance.human_approval_required"),
    _c(8, "isolation_authority", "Least-privilege tool allowlist", "Agent tools are explicit, narrow, and deny-by-default.", Severity.HIGH, True, "is_true", "security.tool_allowlist_enforced"),
    _c(9, "isolation_authority", "Secret redaction", "Secrets are recursively removed from prompts, logs, and reports.", Severity.CRITICAL, True, "is_true", "security.secret_redaction_passed"),
    _c(10, "isolation_authority", "Immutable audit ledger", "State transitions and approvals are append-only and tamper-evident.", Severity.HIGH, True, "is_true", "governance.append_only_ledger"),
    _c(11, "evidence_integrity", "Manifest present", "A machine-readable run or bundle manifest exists.", Severity.CRITICAL, True, "is_true", "_derived.manifest_present"),
    _c(12, "evidence_integrity", "Manifest schema valid", "Required manifest identity and authority fields are present.", Severity.CRITICAL, True, "is_true", "_derived.manifest_schema_valid"),
    _c(13, "evidence_integrity", "Artifact paths contained", "Artifact paths are relative and cannot escape the evidence root.", Severity.CRITICAL, True, "is_true", "_derived.artifact_paths_safe"),
    _c(14, "evidence_integrity", "Required artifacts exist", "Every artifact declared by the manifest exists.", Severity.CRITICAL, True, "is_true", "_derived.artifacts_exist"),
    _c(15, "evidence_integrity", "Artifact hashes verified", "Observed SHA-256 values match the manifest.", Severity.CRITICAL, True, "is_true", "_derived.artifact_hashes_match"),
    _c(16, "evidence_integrity", "Repository commit captured", "The exact source commit is recorded.", Severity.HIGH, True, "nonempty", "repository_commit"),
    _c(17, "evidence_integrity", "Configuration digest captured", "The complete strategy and validation configuration is hashed.", Severity.HIGH, True, "nonempty", "provenance.config_sha256"),
    _c(18, "evidence_integrity", "Dataset digest captured", "Input data is identified by immutable checksum or manifest digest.", Severity.CRITICAL, True, "nonempty", "provenance.dataset_sha256"),
    _c(19, "evidence_integrity", "Command and environment captured", "Execution command, Python version, dependency lock, and random seed are recorded.", Severity.HIGH, True, "is_true", "provenance.execution_context_complete"),
    _c(20, "evidence_integrity", "Bundle digest reproducible", "Canonical bundle digest is computed from manifest and observed hashes.", Severity.HIGH, True, "is_true", "_derived.bundle_digest_reproducible"),
    _c(21, "temporal_data", "Timezone explicit", "All timestamps declare timezone and normalization rules.", Severity.HIGH, True, "is_true", "temporal.timezone_explicit"),
    _c(22, "temporal_data", "Signal precedes entry", "Every signal timestamp is strictly before its executable entry timestamp.", Severity.CRITICAL, True, "zero", "temporal.signal_after_entry_count", 0),
    _c(23, "temporal_data", "No same-event entry", "Same-bar or same-event fills are rejected unless explicitly modeled and delayed.", Severity.CRITICAL, True, "zero", "temporal.same_event_entry_count", 0),
    _c(24, "temporal_data", "No future feature access", "Feature windows and higher-timeframe joins cannot access future observations.", Severity.CRITICAL, True, "zero", "temporal.future_feature_access_count", 0),
    _c(25, "temporal_data", "Split boundaries valid", "Train, validation, and holdout windows are non-overlapping and ordered.", Severity.CRITICAL, True, "is_true", "validation.split_boundaries_valid"),
    _c(26, "temporal_data", "Preprocessing fit on train only", "Scalers, encoders, and selectors are fitted without holdout contamination.", Severity.CRITICAL, True, "is_true", "validation.preprocessing_train_only"),
    _c(27, "temporal_data", "Point-in-time universe", "Symbol selection avoids survivorship and future-membership bias.", Severity.HIGH, True, "is_true", "data.point_in_time_universe"),
    _c(28, "temporal_data", "Corporate actions handled", "Splits, dividends, symbol changes, and expiry adjustments are documented.", Severity.HIGH, True, "is_true", "data.corporate_actions_handled"),
    _c(29, "temporal_data", "Stale quote policy", "Stale quote counts are measured and fail closed above policy limits.", Severity.CRITICAL, True, "is_true", "data.stale_quote_policy_enforced"),
    _c(30, "temporal_data", "Sequence quality checks", "Missing, duplicate, and out-of-order observations are measured and bounded.", Severity.HIGH, True, "is_true", "data.sequence_quality_passed"),
    _c(31, "execution_risk", "Fees included", "Brokerage, exchange charges, taxes, and duties are included.", Severity.CRITICAL, True, "is_true", "execution.fees_included"),
    _c(32, "execution_risk", "Spread modeled", "Bid-ask spread is modeled using quote evidence or conservative assumptions.", Severity.CRITICAL, True, "is_true", "execution.spread_modeled"),
    _c(33, "execution_risk", "Slippage modeled", "Slippage is non-zero where applicable and stress-tested.", Severity.CRITICAL, True, "is_true", "execution.slippage_modeled"),
    _c(34, "execution_risk", "Latency modeled", "Signal-to-order and order-to-fill latency are represented.", Severity.HIGH, True, "is_true", "execution.latency_modeled"),
    _c(35, "execution_risk", "Partial fills modeled", "Fill quantity can be less than requested quantity.", Severity.HIGH, False, "is_true", "execution.partial_fills_modeled"),
    _c(36, "execution_risk", "Liquidity constraints", "Volume, open interest, depth, and participation limits are enforced.", Severity.CRITICAL, True, "is_true", "execution.liquidity_constraints_enforced"),
    _c(37, "execution_risk", "Position sizing deterministic", "Position size is reproducible and based on explicit risk inputs.", Severity.CRITICAL, True, "is_true", "risk.position_sizing_deterministic"),
    _c(38, "execution_risk", "Exposure limits", "Instrument, strategy, sector, and portfolio exposure limits are enforced.", Severity.CRITICAL, True, "is_true", "risk.exposure_limits_enforced"),
    _c(39, "execution_risk", "Loss limits and kill switch", "Daily loss, drawdown, stale-feed, and system-health halts fail closed.", Severity.CRITICAL, True, "is_true", "risk.kill_switch_tested"),
    _c(40, "execution_risk", "Rejected and missed orders", "Backtests account for rejected, stale, unfilled, and missed orders.", Severity.HIGH, False, "is_true", "execution.rejections_modeled"),
    _c(41, "robustness_validation", "Out-of-sample evidence", "Performance is measured on untouched data.", Severity.CRITICAL, True, "is_true", "validation.out_of_sample_present"),
    _c(42, "robustness_validation", "Walk-forward analysis", "Multiple chronological train-test folds are reported.", Severity.CRITICAL, True, "is_true", "validation.walk_forward_present"),
    _c(43, "robustness_validation", "Holdout reuse controlled", "Repeated holdout access is counted and bounded by policy.", Severity.CRITICAL, True, "zero", "validation.repeated_holdout_use_count", 0),
    _c(44, "robustness_validation", "Parameter perturbation", "Neighboring parameter values produce consistent behavior.", Severity.HIGH, True, "is_true", "robustness.parameter_perturbation_passed"),
    _c(45, "robustness_validation", "Cost stress", "Performance survives materially worse cost assumptions.", Severity.HIGH, True, "is_true", "robustness.cost_stress_passed"),
    _c(46, "robustness_validation", "Delayed-entry stress", "One or more execution delays do not destroy the result.", Severity.HIGH, True, "is_true", "robustness.delayed_entry_passed"),
    _c(47, "robustness_validation", "Regime segmentation", "Results are reported across trend, range, volatility, and crisis regimes.", Severity.HIGH, True, "is_true", "robustness.regime_segmentation_present"),
    _c(48, "robustness_validation", "Instrument generalization", "The thesis is tested across a justified instrument set.", Severity.MEDIUM, False, "is_true", "robustness.instrument_generalization_passed"),
    _c(49, "robustness_validation", "Best-trade dependence", "Removing top trades does not erase the entire result.", Severity.HIGH, True, "is_true", "robustness.best_trade_removal_passed"),
    _c(50, "robustness_validation", "Negative controls and resampling", "Placebo, shuffled, bootstrap, or equivalent controls are included.", Severity.HIGH, True, "is_true", "robustness.negative_controls_passed"),
    _c(51, "agent_quality_security", "Structured agent output", "Agent responses conform to a closed JSON schema.", Severity.HIGH, True, "is_true", "agent.structured_output_enforced"),
    _c(52, "agent_quality_security", "Evidence citation accuracy", "Every factual agent claim resolves to supplied evidence.", Severity.CRITICAL, True, "is_true", "agent.citations_resolve"),
    _c(53, "agent_quality_security", "No fabricated metrics", "The agent cannot introduce unsupported numbers.", Severity.CRITICAL, True, "zero", "agent.fabricated_metric_count", 0),
    _c(54, "agent_quality_security", "Verdict agreement", "Agent recommendation cannot contradict the deterministic verdict.", Severity.CRITICAL, True, "is_true", "agent.verdict_agreement"),
    _c(55, "agent_quality_security", "Uncertainty disclosure", "The agent labels missing evidence and uncertainty explicitly.", Severity.HIGH, False, "is_true", "agent.uncertainty_disclosed"),
    _c(56, "agent_quality_security", "Prompt-injection resistance", "Hostile instructions cannot bypass approval, tools, or verdict authority.", Severity.CRITICAL, True, "is_true", "agent.prompt_injection_tests_passed"),
    _c(57, "agent_quality_security", "Tool-call policy", "Every tool call is schema-validated, allowlisted, and logged.", Severity.CRITICAL, True, "is_true", "agent.tool_policy_passed"),
    _c(58, "agent_quality_security", "Model and prompt provenance", "Model ID, prompt version, temperature, and schema version are captured.", Severity.HIGH, True, "is_true", "agent.provenance_complete"),
    _c(59, "agent_quality_security", "Prompt regression suite", "Golden cases rerun after model, prompt, schema, or tool changes.", Severity.HIGH, True, "is_true", "agent.prompt_regression_passed"),
    _c(60, "agent_quality_security", "Agent scorecard thresholds", "Accuracy, unsafe-action, citation, and stability thresholds are enforced.", Severity.HIGH, True, "is_true", "agent.scorecard_passed"),
    _c(61, "governance_operations", "Run and trace identity", "Every report carries stable run and trace identifiers.", Severity.HIGH, True, "is_true", "_derived.identity_complete"),
    _c(62, "governance_operations", "Restart-safe checkpointing", "Interrupted orchestration resumes without repeating unsafe or expensive actions.", Severity.HIGH, False, "is_true", "governance.restart_safe_checkpointing"),
    _c(63, "governance_operations", "Manual promotion approval", "Paper or controlled deployment promotion requires named approval.", Severity.CRITICAL, True, "is_true", "governance.manual_promotion_approval"),
    _c(64, "governance_operations", "Role separation", "Author, reviewer, approver, and runtime operator roles are distinguishable.", Severity.HIGH, False, "is_true", "governance.role_separation"),
    _c(65, "governance_operations", "Policy version pinned", "The exact deterministic policy version is in the report.", Severity.HIGH, True, "nonempty", "policy_version"),
    _c(66, "governance_operations", "Failure taxonomy", "Failures use stable reason codes and remediation categories.", Severity.MEDIUM, False, "is_true", "governance.failure_taxonomy_present"),
    _c(67, "governance_operations", "Audit report completeness", "Report includes controls, evidence refs, blockers, warnings, score, and verdict.", Severity.HIGH, True, "is_true", "governance.report_schema_complete"),
    _c(68, "governance_operations", "CI enforcement", "Compilation, tests, deterministic evaluation, and authority-boundary gates run in CI.", Severity.HIGH, True, "is_true", "governance.ci_gate_present"),
    _c(69, "governance_operations", "Reproducible CLI and runbook", "A documented one-command audit path produces deterministic output.", Severity.MEDIUM, False, "is_true", "governance.reproducible_cli"),
    _c(70, "governance_operations", "Truthful non-claims", "Reports explicitly withhold profitability, live-readiness, and model-quality claims without evidence.", Severity.CRITICAL, True, "is_true", "governance.truthful_non_claims"),
)


def validate_catalog() -> None:
    if len(CONTROL_CATALOG) != 70:
        raise RuntimeError(f"expected 70 controls, found {len(CONTROL_CATALOG)}")
    ids = [item.control_id for item in CONTROL_CATALOG]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate control IDs")
    expected = [f"AQ-{number:02d}" for number in range(1, 71)]
    if ids != expected:
        raise RuntimeError("control IDs are not contiguous AQ-01..AQ-70")


validate_catalog()
