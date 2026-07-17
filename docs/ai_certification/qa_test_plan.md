# TradeBot AI Certification — QA Test Plan

## 1. Objective

Validate that the AI certification module behaves correctly as a read-only, fail-closed evidence authority without changing TradeBot's live feed, strategy, ranking, risk, execution, broker, option-backtest, or WFA behavior.

The QA suite verifies two independent outputs:

1. **Evidence certification** — whether the experiment is trustworthy.
2. **Strategy verdict** — what the trustworthy experiment concludes.

A negative trading result may be valid evidence. A profitable-looking result may still be rejected when the evidence is invalid.

## 2. Test Scope

### In scope

- Functional behavior
- Business-verdict mapping
- Positive and happy paths
- Negative paths
- Fail-closed behavior
- Source and derived evidence consistency
- Bundle integrity and filesystem boundaries
- MCP tool integration
- Exporter-to-certifier integration
- Report persistence
- Prompt-injection resistance as data handling
- Ad-hoc misuse and hostile inputs
- Determinism and auditability

### Out of scope

- Live order placement
- Broker API execution
- Strategy optimization
- Live feed readiness
- Production MCP hosting
- Cryptographic signing of the bundle manifest
- Performance/load testing beyond deterministic correctness

## 3. Test Approach

Every QA scenario begins from one shared known-good strict option-replay bundle. A test changes only one authority condition unless the purpose is mixed-failure precedence. This isolates the root cause and prevents invalid test fixtures from creating false positives.

The suite uses the following levels:

| Level | Purpose |
|---|---|
| Unit | Validate individual deterministic gates and helpers. |
| Functional | Validate externally visible certification and strategy outcomes. |
| Behavioral | Validate precedence, warnings, blockers, and deterministic repetition. |
| Integration | Validate exporter, bundle, MCP gate, final certification, and report flow. |
| Security boundary | Validate traversal, symlink, hostile identifiers, and inert untrusted text. |
| Ad-hoc | Validate unexpected but realistic misuse and forward-compatibility behavior. |

## 4. Entry Criteria

- Branch is isolated from `main`.
- No existing TradeBot production file is modified.
- Strict option-replay authority names and policy version are frozen.
- The known-good bundle passes all 12 deterministic gates.
- Test data contains no live credentials, broker tokens, or production secrets.

## 5. Exit Criteria

- All focused tests under `tests/ai_certification` pass.
- Repository CI, CodeQL, Code Excellence, Agent Review Evidence, Repo Forensics, Portfolio CI, and strategy-registry checks pass on the final commit.
- No test introduces broker, order, shell, database-write, Git-write, or risk-override capability.
- Every mandatory failure produces `REJECTED`, `INSUFFICIENT_EVIDENCE`, or `AGENT_ERROR`; it must never silently produce `CERTIFIED`.
- Evidence and strategy outcomes remain separate.

## 6. Automated Test Inventory

Current inventory: **43 automated test functions**.

| Category | File | Coverage |
|---|---|---|
| Core certification | `tests/ai_certification/test_certifier.py` | Hashes, timing, proxy paths, missing evidence, source identity, strategy result. |
| Export integration | `tests/ai_certification/test_exporter.py` | Real WFA output to frozen certifiable bundle. |
| MCP boundary | `tests/ai_certification/test_mcp_boundary.py` | Allowlisted paths, gate dispatch, curated retrieval. |
| Functional and behavioral | `tests/ai_certification/test_qa_functional_behavior.py` | Happy path, positive result, insufficient trades, warnings, deterministic output. |
| Negative and fail closed | `tests/ai_certification/test_qa_negative_fail_closed.py` | Corruption, missing evidence, fallback fills, WFA reuse, controls, tests, validator crash. |
| Integration and ad-hoc | `tests/ai_certification/test_qa_integration_adhoc.py` | MCP flow, raw/derived mismatch, hostile IDs, symlinks, prompt injection, exporter misuse. |

## 7. Functional Test Cases

### QA-FUNC-001 — Valid methodology with negative edge

- **Precondition:** All 12 evidence gates pass; after-cost metrics are negative.
- **Steps:** Certify the frozen bundle.
- **Expected:** `evidence_certification=CERTIFIED`; `strategy_verdict=NO_STRUCTURAL_EDGE`; no blockers or warnings.
- **Severity if failed:** Critical.
- **Automation:** `test_qa_func_001_happy_path_valid_negative_edge_is_certified`.

### QA-FUNC-002 — Valid methodology with supported edge

- **Precondition:** Minimum trades met, positive expectancy, profit factor above policy.
- **Steps:** Certify the frozen bundle.
- **Expected:** `CERTIFIED` plus `STRUCTURAL_EDGE_SUPPORTED`.
- **Severity if failed:** Critical.
- **Automation:** `test_qa_func_002_happy_path_positive_edge_is_supported`.

### QA-FUNC-003 — Insufficient sample size

- **Precondition:** Methodology is valid; trade count is below policy minimum.
- **Expected:** Evidence remains `CERTIFIED`; strategy verdict becomes `INSUFFICIENT_TRADES`.
- **Severity if failed:** High.
- **Automation:** `test_qa_func_003_insufficient_trades_is_business_outcome_not_invalid_evidence`.

### QA-FUNC-004 — Conditional strategy result

- **Precondition:** Methodology is valid and result is declared conditionally supported.
- **Expected:** `CERTIFIED` plus `CONDITIONALLY_SUPPORTED`.
- **Severity if failed:** Medium.
- **Automation:** `test_qa_func_004_conditionally_supported_verdict_is_preserved`.

## 8. Behavioral Test Cases

### QA-BEH-001 — Optional strategy contradiction

- **Input:** Declared structural edge with negative expectancy and sub-policy profit factor.
- **Expected:** Evidence remains `CERTIFIED`; strategy claim is `WITHHELD`; warning is emitted.
- **Automation:** `test_qa_behavior_001_optional_strategy_contradiction_withholds_only_strategy_claim`.

### QA-BEH-002 — Gate audit contract

- **Expected:** All gates provide status, reason code, summary, details, and evidence references.
- **Automation:** `test_qa_behavior_002_all_gate_results_have_auditable_contract`.

### QA-BEH-003 — Determinism

- **Steps:** Certify the same immutable bundle twice.
- **Expected:** Identical report payload, trace ID, and bundle digest.
- **Automation:** `test_qa_behavior_003_repeated_certification_is_bitwise_deterministic`.

### QA-BEH-004 — Unknown strategy verdict

- **Expected:** No fake methodology failure; evidence remains certified, strategy is withheld, warning is emitted.
- **Automation:** `test_qa_behavior_004_unknown_strategy_verdict_is_warning_not_fake_methodology_failure`.

## 9. Positive and Happy-Path Tests

| ID | Scenario | Expected result | Automation |
|---|---|---|---|
| QA-POS-001 | Valid negative result | `CERTIFIED / NO_STRUCTURAL_EDGE` | QA-FUNC-001 |
| QA-POS-002 | Valid positive result | `CERTIFIED / STRUCTURAL_EDGE_SUPPORTED` | QA-FUNC-002 |
| QA-POS-003 | MCP inspect → targeted gate → final certification | Reports persisted; all identities match | `test_qa_integration_001_mcp_inspect_gate_and_final_report_flow` |
| QA-POS-004 | Unknown harmless extra artifact | Certification remains valid | `test_qa_adhoc_003_unknown_harmless_artifact_is_forward_compatible` |

## 10. Negative-Path Tests

| ID | Scenario | Expected result | Automation |
|---|---|---|---|
| QA-NEG-001 | Missing provider identity | `INSUFFICIENT_EVIDENCE / WITHHELD` | `test_qa_negative_001_missing_dataset_identity_is_not_assumed` |
| QA-NEG-002 | Stale quote rows | `REJECTED / INVALID_DUE_TO_DATA` | `test_qa_negative_002_stale_quotes_reject_data_certification` |
| QA-NEG-003 | Fallback liquidity fill | `REJECTED / INVALID_DUE_TO_DATA` | `test_qa_negative_003_fallback_fill_rejects_execution_realism` |
| QA-NEG-004 | Gross/cost/net mismatch | `REJECTED / WITHHELD` | `test_qa_negative_004_financial_mismatch_blocks_certification` |
| QA-NEG-005 | Repeated holdout use | `REJECTED / WITHHELD` | `test_qa_negative_005_repeated_holdout_use_blocks_certification` |
| QA-NEG-006 | Failed negative control | `REJECTED / WITHHELD` | `test_qa_negative_006_failed_negative_control_blocks_certification` |
| QA-NEG-007 | Failed test run | `REJECTED / WITHHELD` | `test_qa_negative_007_failed_test_run_blocks_certification` |
| QA-NEG-008 | Policy version mismatch | `REJECTED / INVALID_DUE_TO_DATA` | `test_qa_negative_008_policy_version_mismatch_rejects_bundle` |

## 11. Fail-Closed Test Cases

### QA-FC-001 — Mixed invalid and missing evidence

- **Input:** Dataset contains stale quotes while a separate required artifact is absent.
- **Expected:** The explicit failure takes precedence; status remains `REJECTED`, not downgraded to `INSUFFICIENT_EVIDENCE`.
- **Automation:** `test_qa_fail_closed_001_failure_is_not_downgraded_by_missing_evidence`.

### QA-FC-002 — Malformed JSON with valid file hash

- **Expected:** Artifact hash passes, semantic evaluation is impossible, status is `INSUFFICIENT_EVIDENCE`.
- **Automation:** `test_qa_fail_closed_002_malformed_artifact_with_valid_hash_is_insufficient`.

### QA-FC-003 — Validator exception

- **Expected:** `AGENT_ERROR / WITHHELD`; exception must not produce certification.
- **Automation:** `test_qa_fail_closed_003_validator_exception_returns_agent_error`.

### QA-FC-004 — Raw WFA and generated authority mismatch

- **Expected:** `REJECTED / INVALID_DUE_TO_DATA`.
- **Automation:** `test_qa_integration_002_raw_wfa_engine_mismatch_rejects_generated_identity`.

### QA-FC-005 — Raw WFA action boundary violation

- **Expected:** Any broker-action marker in raw WFA evidence rejects the bundle.
- **Automation:** `test_qa_integration_003_raw_wfa_action_boundary_violation_is_rejected`.

## 12. Integration Test Cases

### QA-INT-001 — WFA artifacts to bundle

- **Steps:** Read an existing strict WFA output directory, copy raw reports and partition evidence, generate normalized artifacts, freeze hashes, and certify.
- **Expected:** Raw files remain byte-for-byte identical; valid negative strategy result is certified.
- **Automation:** `test_exported_wfa_bundle_certifies_without_modifying_engine_outputs`.

### QA-INT-002 — MCP end-to-end

- **Steps:** Inspect bundle, run source gate, run final certification, write JSON and Markdown reports.
- **Expected:** Same run ID, bundle digest, trace ID, and persisted report payload.
- **Automation:** `test_qa_integration_001_mcp_inspect_gate_and_final_report_flow`.

## 13. Ad-Hoc and Misuse Test Cases

| ID | Scenario | Expected result | Automation |
|---|---|---|---|
| QA-ADHOC-001 | Run ID contains traversal characters | Safe deterministic filename under report root | `test_qa_adhoc_001_hostile_run_id_uses_safe_deterministic_report_name` |
| QA-ADHOC-002 | Run ID is extremely long | Filename is bounded to 96 characters | `test_qa_adhoc_002_extreme_run_id_is_bounded_in_filename` |
| QA-ADHOC-003 | Harmless unknown artifact | Forward-compatible certification | `test_qa_adhoc_003_unknown_harmless_artifact_is_forward_compatible` |
| QA-ADHOC-004 | Prompt injection embedded in evidence text | Text remains inert and cannot alter verdict | `test_qa_adhoc_004_prompt_injection_text_is_inert_evidence_data` |
| QA-ADHOC-005 | Symlink points outside allowed root | Path resolution rejects escape | `test_qa_adhoc_005_symlink_escape_is_blocked` |
| QA-ADHOC-006 | Export target is nonempty | Export refuses overwrite before reading sources | `test_qa_adhoc_006_exporter_refuses_nonempty_output_before_source_read` |
| QA-ADHOC-007 | Bundle manifest is a JSON array | Loader rejects non-object manifest | `test_qa_adhoc_007_non_object_manifest_is_rejected` |

## 14. Defect Severity

| Severity | Definition | Examples |
|---|---|---|
| Critical | Can falsely certify invalid evidence or cross the broker/order boundary. | Temporal leakage accepted; proxy engine certified; broker action evidence ignored. |
| High | Produces wrong evidence status, strategy verdict, or non-deterministic audit result. | Rejection downgraded to insufficient; repeated holdout accepted. |
| Medium | Incorrect warning, report persistence, or compatibility behavior. | Optional strategy contradiction treated as mandatory failure. |
| Low | Documentation, message clarity, or non-authoritative formatting issue. | Incomplete reason wording with correct status. |

## 15. Regression Rule

Every defect found in certification logic must add a deterministic regression test before the fix is accepted. A test must assert both the top-level result and the specific gate reason code. Fixing only the visible output without protecting the authority boundary is not acceptable.
