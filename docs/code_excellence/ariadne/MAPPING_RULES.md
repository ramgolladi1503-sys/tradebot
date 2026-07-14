# Ariadne Symptom/Finding/Source Mapping Rules

## Purpose

Mapping rules prevent Ariadne from treating isolated failures as unrelated noise.

A symptom must be mapped to findings, evidence sources, modules, and likely root-cause families before remediation planning begins.

## Mapping Layers

Ariadne maps every issue through five layers:

```text
Symptom
→ Evidence source
→ Related finding
→ Affected module/contract
→ Root-cause family
```

## Source Types

### CI Failure

Examples:

- failed unit test
- failed required status check
- failed repo-forensics PR gate
- failed lint/static check

Required mapping:

- workflow name
- job name
- failed step
- failing test or command
- changed files in the PR

### Runtime Log Symptom

Examples:

- final emit contradiction
- stale feed blocker
- fallback contract warning
- queue-only candidate marked executable

Required mapping:

- log file
- event name
- candidate or symbol if available
- timestamp if available
- fields proving contradiction

### Repo-Forensics Finding

Examples:

- missing caller proof
- safety boundary finding
- evidence high finding
- architecture drift
- product reality unproven capability

Required mapping:

- report path
- finding type
- severity
- affected path
- baseline delta if available

### Test Failure

Examples:

- assertion failure
- import failure
- fixture mismatch
- snapshot mismatch

Required mapping:

- test file
- test name
- expected behavior
- observed behavior
- whether the test is contract/regression/negative/fake-confidence

### Manual Review Finding

Examples:

- duplicated logic
- unsafe default
- silent fallback
- hidden global state

Required mapping:

- file/function
- exact behavior risk
- evidence that risk is reachable
- related tests or missing tests

## Root-Cause Families

Use these families for initial clustering:

### CONTRACT_VIOLATION

A documented or expected contract is violated.

Examples:

- queue-only candidate appears executable
- fallback contract appears tradable
- blocked candidate emits actionable wording

### PROPAGATION_GAP

Truth is detected in one layer but not carried into another.

Examples:

- fallback resolution detected but not propagated to candidate finalization
- feed freshness blocker exists but not reflected in readiness

### EVIDENCE_GAP

Runtime behavior may be correct, but evidence is incomplete or ambiguous.

Examples:

- status-only logs
- miss_ing reason field
- miss_ing b-roker_api_called flag

### TEST_REALITY_GAP

Tests do not prove real behavior.

Examples:

- mock-only test
- shape-only assertion
- missing negative test

### SAFETY_BOUNDARY_GAP

A read-only/paper/live/broker boundary is unclear or unsafe.

Examples:

- order-like field in read-only path
- broker import in static/paper-only module

### ARCHITECTURE_DRIFT

Multiple old/new paths create ambiguity.

Examples:

- duplicate module names
- legacy and current pipelines both present
- dashboard reads evidence from stale path

### DATA_QUALITY_GAP

Input data quality is insufficient or unproven.

Examples:

- stale feed
- missing token mapping
- fallback instrument resolution

### OPERATIONAL_GAP

The system behavior depends on manual process or missing runbook discipline.

Examples:

- validation not run after merge
- evidence not archived
- baseline not updated when intended

## Mapping Rules

### Rule 1 — Do Not Map By Filename Alone

A file name is a clue, not proof.

Bad:

```text
core/risk.py changed, so root cause is risk management.
```

Good:

```text
core/risk.py changed, and test X proves rejected candidates no longer carry rejection reason into evidence.
```

### Rule 2 — Separate Symptom From Cause

Bad:

```text
The test failed because the assertion failed.
```

Good:

```text
The assertion failed because candidate finalization did not preserve fallback-resolution truth into final readiness fields.
```

### Rule 3 — Prefer Contract Breach Over Broad Blame

Bad:

```text
The architecture is messy.
```

Good:

```text
Two readiness contracts disagree: candidate_status says advisory_only while final emit says executable.
```

### Rule 4 — Attach Missing Proof As A Finding

If behavior might be correct but evidence is missing, classify it as EVIDENCE_GAP instead of pretending the product is broken.

### Rule 5 — Escalate Safety Unknowns

If the finding touches broker/live/order boundaries and proof is miss-ing, classify safety risk as high until proven otherwise.

## RCA Readiness Checklist

Before Daedalus remediation planning, Ariadne must have:

- [ ] symptom mapped
- [ ] evidence source listed
- [ ] related findings grouped
- [ ] affected modules identified
- [ ] root-cause family assigned
- [ ] selected root-cause hypothesis documented
- [ ] remediation requirements stated
- [ ] unknowns documented

If this checklist is incomplete, the RCA verdict should be `NEEDS_MORE_EVIDENCE` or `BLOCKED`.
