# Example Ariadne RCA — Fallback Contract Executable Leak

## RCA Metadata

```yaml
rca_id: CE-RCA-2026-001
status: example
source_pr: PR-102
related_prs:
  - PR-101
  - PR-102
  - PR-103
  - PR-104
```

## Symptom

A candidate involving fallback contract resolution reached an executable-looking trace.

Fallback contract resolution should not create executable candidates. It should force advisory/queue-only truth until contract tradability is proven.

## Observed In

- live read-only validation
- runtime evidence review
- regression tests added after the issue

## Source Evidence

### PR Evidence

- PR #102 identified `fallback_contract_reached_executable_trace` after PR #101.
- PR #102 added a propagation gate to force fallback-resolved contracts to queue-only/non-executable truth.

### Expected Safety Contract

When contract resolution fallback occurs:

```text
execution_allowed=false
selected_for_execution=false
tradable=false
permission=QUEUE_ONLY
final_action=QUEUE_ONLY
readiness=QUEUE_ONLY
execution_status=queue_only
candidate_status=advisory_only
execution_entry=None
execution_entry_status=blocked_contract
source_flags.contract_resolution_fallback_used=true
```

## Impact

### Product Risk

Executable candidate truth becomes unreliable.

### Safety Risk

A fallback-resolved contract may appear more actionable than it should.

### Evidence Risk

Operators and validators cannot trust candidate-readiness evidence.

### Operator Risk

A misleading executable-looking signal could drive the wrong manual decision.

## Scope Boundary

### In Scope

- fallback contract truth propagation
- candidate finalization truth
- readiness/actionability fields
- regression tests proving fallback stays non-executable

### Out of Scope

- broker execution
- strategy scoring
- dashboard UI
- profitability optimization
- feed subscription changes

### Must Not Change

- order routing behavior
- live order behavior
- broker adapter behavior
- strategy entry logic

## Related Modules

### Production

- contract resolution path
- candidate finalization path
- review/queue readiness path

### Tests

- fallback contract firewall tests
- fallback propagation gate tests
- live evidence validator tests

### Evidence

- live validation evidence
- PR #102 agent evidence
- runtime truth diagnostics added by later PRs

## Finding Map

### Normalized Finding

```yaml
finding_type: SAFETY_BOUNDARY_GAP
symptom: fallback contract reached executable-looking trace
severity: critical
root_cause_family: PROPAGATION_GAP
```

### Related Findings

- queue-only/executable contradiction
- final emit truth contradiction
- runtime truth consistency gap

### Ruled Out Findings

- pure test failure only
- dashboard rendering issue
- profitability strategy issue

## Root-Cause Hypotheses

### H1 — Fallback resolution was detected but not propagated into candidate finalization

Supporting evidence:

- fallback contract resolution appeared in validation
- executable-looking candidate trace still appeared
- PR #102 fixed propagation into execution/actionability fields

Contradicting evidence:

- none strong enough in the example record

Confidence: high

### H2 — Validator incorrectly classified queue-only traces as executable

Supporting evidence:

- validator reported executable-looking trace

Contradicting evidence:

- PR #102 changed product truth propagation, not just validator behavior
- follow-up tests focused on propagation contract

Confidence: low

### H3 — Final emit logging used misleading wording while internal state was correct

Supporting evidence:

- later PR #104 addressed final emit truth wording

Contradicting evidence:

- PR #102 symptom existed before final emit wording was the only issue

Confidence: medium

## Selected Root Cause

```yaml
hypothesis_id: H1
cause: Fallback contract resolution was not consistently propagated into final candidate actionability fields.
```

## Why This Is Root Cause, Not Just Symptom

The symptom was an executable-looking trace.

The root cause was that fallback truth did not dominate all downstream readiness/actionability fields.

Fixing only the validator or log text would not guarantee the candidate remained non-executable. The propagation contract had to be enforced where candidate truth is finalized.

## Unknowns

- Whether all future fallback-like resolution paths share the same safety contract.
- Whether dashboard views could still display old executable wording from cached or stale evidence.

## Deferred Questions

### Question

Should every resolution fallback type be modeled under one common safety contract?

### Reason Deferred

That is broader than the targeted PR #102 fix.

### Required Future Evidence

- inventory of fallback resolution types
- contract test for each fallback type
- evidence audit proving all fallback types include actionability fields

## Remediation Requirements

Any remediation must prove:

- fallback-resolved contract cannot be selected for execution
- fallback-resolved contract cannot have execution_allowed=true
- fallback-resolved contract cannot emit executable final action
- fallback-resolved contract has explicit blocked reason
- evidence records fallback flag and actionability status

## Forbidden Shortcuts

- changing validator only
- changing log wording only
- suppressing fallback warning
- removing fallback evidence
- allowing fallback to pass based on score quality

## Ariadne Verdict

```yaml
result: pass
reason: Evidence supports a propagation gap root cause and defines bounded remediation requirements.
```
