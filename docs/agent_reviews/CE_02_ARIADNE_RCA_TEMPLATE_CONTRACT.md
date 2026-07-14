# CE-02 — Ariadne RCA Template and Contract

## Agent Work Contract

### Scope

Add Ariadne root-cause analysis templates and contract documents.

This PR defines how TradeBot issues should be analyzed before remediation planning begins.

### Files Changed

- `docs/code_excellence/ariadne/RCA_TEMPLATE.md`
- `docs/code_excellence/ariadne/RCA_CONTRACT.md`
- `docs/code_excellence/ariadne/MAPPING_RULES.md`
- `docs/code_excellence/ariadne/examples/FALLBACK_CONTRACT_EXECUTABLE_LEAK_RCA.md`
- `docs/agent_reviews/CE_02_ARIADNE_RCA_TEMPLATE_CONTRACT.md`

### Hard Boundaries

- No product code changes.
- No RCA engine implementation.
- No remediation planner implementation.
- No scanner behavior changes.
- No trading logic changes.
- No broker behavior changes.
- No live runtime execution.
- No auto-fix.
- No auto-PR.
- No baseline debt cleanup.
- No test weakening.

## Deliverables

This PR adds:

- RCA record template
- RCA contract
- symptom/finding/source mapping rules
- root-cause family taxonomy
- example RCA for fallback contract executable leak

## Gate 1 — Scope and Intent

PASS.

This is documentation/contract work only. It defines RCA standards before implementation work begins.

## Gate 2 — Truth and Root-Cause

PASS.

This PR does not claim to fix a production bug. It defines how future root-cause analysis must be recorded. The example RCA is explicitly marked as an example and is based on already documented TradeBot PR evidence.

## Gate 3 — Hardening and Proof

PASS pending CI.

Docs-only PR. The required repo-forensics PR gate must pass.

## Grill Me Review

### Challenge

RCA templates can become paperwork if they do not change remediation quality.

### Findings

- Good: template requires concrete evidence, hypotheses, selected root cause, unknowns, and remediation requirements.
- Good: mapping rules prevent treating isolated symptoms as root cause.
- Good: example RCA uses a real TradeBot safety issue.
- Risk: future PRs must actually use this template before meaningful fixes, otherwise CE becomes decorative.

### Verdict

PASS.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No scanner implementation added.
- [x] No broker behavior changed.
- [x] No live behavior changed.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] RCA template added.
- [x] RCA contract added.
- [x] Mapping rules added.
- [x] Example RCA added.
- [x] Agent evidence added.
- [x] Next action is clear: CE-03 — Finding Normalization Contract.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Ariadne RCA template.
- Ariadne RCA contract.
- Mapping rules.
- Example RCA.
- Agent evidence file.

### Out of Scope

- RCA engine.
- Finding normalization implementation.
- Remediation planning.
- Product fixes.
- Runtime execution.

## Test Plan

No runtime tests required for documentation-only PR.

Required CI:

```text
repo-forensics-pr-gate
```

## Final Verdict

PASS pending CI.

## Next PR

CE-03 — Finding Normalization Contract

Expected deliverables:

- normalized finding schema
- severity mapping
- source mapping
- deduplication rules
- examples for repo-forensics, CI, runtime logs, and product reality findings


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
