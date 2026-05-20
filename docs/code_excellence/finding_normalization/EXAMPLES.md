# Finding Normalization Examples

## Purpose

These examples show how raw TradeBot signals should become normalized findings before Ariadne RCA or Daedalus remediation planning.

## Example 1 — Repo Forensics Finding

### Raw Signal

```text
repo-forensics baseline: hard_failures=113
```

### Normalized Finding

```yaml
finding_id: CE-FINDING-2026-001
schema_version: 1
status: open
source:
  source_type: repo_forensics
  source_name: baseline_latest.md
  source_path: docs/repo_forensics/reports/baseline_latest.md
classification:
  finding_type: unknown
  severity: high
  confidence: medium
  root_cause_family: baseline_debt
summary:
  title: Repo-forensics baseline contains hard failures
  observed_behavior: Baseline reports hard failures.
  expected_behavior: Future PRs should not increase hard failures, and debt should be reduced by targeted CE work.
impact:
  product_risk: Unknown until hard failures are clustered.
  safety_risk: Unknown until safety-related failures are separated.
  evidence_risk: High because baseline debt can hide new issues if not compared carefully.
  operator_risk: Medium.
rca:
  required: true
  ariadne_status: not_started
remediation:
  required: true
  daedalus_status: not_started
proof:
  acceptance_criteria:
    - Baseline hard failures are grouped into root-cause clusters.
    - Future PR gate continues blocking new hard failures.
```

## Example 2 — Runtime Log Contradiction

### Raw Signal

```text
FINAL EMIT shows executable wording for queue-only candidate.
```

### Normalized Finding

```yaml
finding_id: CE-FINDING-2026-002
schema_version: 1
status: accepted
source:
  source_type: runtime_log
  source_name: final emit log
classification:
  finding_type: contract_violation
  severity: critical
  confidence: high
  root_cause_family: final_emit_truth_contract
summary:
  title: Queue-only candidate appears executable in final emit output
  observed_behavior: Final emit text uses executable wording for non-executable candidate.
  expected_behavior: Queue-only candidates must emit FINAL_EMIT_QUEUE_ONLY or equivalent non-executable truth.
impact:
  product_risk: Runtime actionability truth is unreliable.
  safety_risk: Operator may misread candidate as actionable.
  evidence_risk: Evidence contradicts candidate state.
  operator_risk: High.
relationships:
  related_prs:
    - PR-104
rca:
  required: true
  ariadne_status: pass
remediation:
  required: true
  daedalus_status: complete
proof:
  required_tests:
    - final emit queue-only regression test
  acceptance_criteria:
    - Queue-only candidates never emit executable final truth.
    - Aborted candidates emit aborted final truth.
```

## Example 3 — Test Reality Gap

### Raw Signal

```text
A test proves only that a dictionary contains expected keys.
```

### Normalized Finding

```yaml
finding_id: CE-FINDING-2026-003
schema_version: 1
status: open
source:
  source_type: test_failure
  source_name: pytest/manual review
classification:
  finding_type: test_reality_gap
  severity: medium
  confidence: medium
  root_cause_family: weak_test_proof
summary:
  title: Shape-only test does not prove behavior
  observed_behavior: Test asserts fields exist but does not prove safety or runtime contract.
  expected_behavior: Test should prove meaningful behavior, including negative paths when relevant.
impact:
  product_risk: False confidence in runtime behavior.
  safety_risk: Depends on tested module.
  evidence_risk: High if evidence contract is only shape-tested.
  operator_risk: Medium.
rca:
  required: false
  ariadne_status: not_started
remediation:
  required: true
  daedalus_status: not_started
proof:
  acceptance_criteria:
    - Replace or extend shape-only test with behavioral assertions.
    - Add negative or regression case if safety-related.
```

## Example 4 — Product Reality Finding

### Raw Signal

```text
Product Reality Audit classifies live broker execution boundary as UNPROVEN.
```

### Normalized Finding

```yaml
finding_id: CE-FINDING-2026-004
schema_version: 1
status: open
source:
  source_type: product_reality
  source_name: product_reality_latest.md
classification:
  finding_type: safety_boundary_gap
  severity: high
  confidence: medium
  root_cause_family: unproven_live_boundary
summary:
  title: Live broker execution boundary lacks sufficient proof
  observed_behavior: Product reality audit does not find enough source/test/evidence proof for live broker boundary.
  expected_behavior: Live broker boundary should be explicitly guarded and proven by tests/evidence before live behavior is enabled.
impact:
  product_risk: Live readiness cannot be claimed.
  safety_risk: High until boundary proof exists.
  evidence_risk: High.
  operator_risk: High.
rca:
  required: true
  ariadne_status: not_started
remediation:
  required: true
  daedalus_status: not_started
proof:
  acceptance_criteria:
    - Boundary tests prove no accidental live order action.
    - Evidence fields prove broker_api_called and is_order_action remain false in read-only paths.
```

## Example 5 — Architecture Drift Finding

### Raw Signal

```text
Architecture drift detector finds old/new ranking paths.
```

### Normalized Finding

```yaml
finding_id: CE-FINDING-2026-005
schema_version: 1
status: open
source:
  source_type: repo_forensics
  source_name: architecture_drift
classification:
  finding_type: architecture_drift
  severity: medium
  confidence: medium
  root_cause_family: duplicate_runtime_ownership
summary:
  title: Ranking ownership is ambiguous
  observed_behavior: Multiple ranking-like modules exist with old/new naming signals.
  expected_behavior: Ranking ownership should be clear enough that runtime and dashboard paths cannot disagree.
impact:
  product_risk: Fixes may target the wrong path.
  safety_risk: Low to medium unless ranking affects actionability.
  evidence_risk: Medium.
  operator_risk: Medium.
rca:
  required: true
  ariadne_status: not_started
remediation:
  required: true
  daedalus_status: not_started
proof:
  acceptance_criteria:
    - Runtime owner path is identified.
    - Stale path is marked inactive, removed, or documented.
    - Tests prove runtime uses canonical path.
```
