# EDGE-07 — Setup Hypothesis Identity

## Evidence Contract

mode: PAPER
candidate_id: EDGE-07-setup-hypothesis-identity
decision: ADD_SETUP_HYPOTHESIS_IDENTITY_CONTRACT
reason: Outcome records need setup identity before setup-level expectancy reporting can be trusted.
timestamp: 2026-05-20T21:05:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/EDGE-07-setup-hypothesis-identity.md

## Agent Work Contract

### Purpose
Add a fail-closed identity contract for edge hypotheses so future outcome rows can be grouped by the exact setup, regime, entry rule, exit rule, cost model, and score bucket.

### Scope

- Require setup identity fields.
- Normalize setup and rule identifiers.
- Derive score buckets from final score.
- Enrich records without changing runtime behavior.
- Add focused tests for identity validation and enrichment.

### Explicit non-scope

- No strategy changes.
- No scoring changes.
- No ranking changes.
- No dashboard changes.
- No broker calls.
- No live execution behavior.
- No runtime candidate wiring yet.
- No expectancy reporting yet.

## Grill Me Review

### Hard question
Does this prove which setup has edge?

### Answer
No. It only creates the identity contract required before setup expectancy reports can be meaningful.

### Hard question
Why not force every journal write to require setup identity now?

### Answer
That would break existing PAPER journal paths before the candidate pipeline supplies setup identity consistently. This PR adds the contract first; runtime adoption should be a separate PR.

### Hard question
What can still silently kill reporting?

### Answer
If runtime does not populate setup fields, reports will still collapse into family-level truth instead of setup-level truth.

## Hermes Review

### Boundary status

- PAPER evidence identity only.
- Broker boundary untouched.
- Live boundary untouched.
- Dashboard untouched.
- Strategy/scoring/ranking untouched.

## GSD Plan / Review

### Files changed

- `core/edge_setup_identity.py`
- `tests/test_edge_setup_identity.py`
- `docs/agent_reviews/EDGE-07-setup-hypothesis-identity.md`

### Tests

```bash
python -m pytest tests/test_edge_setup_identity.py tests/test_paper_exit_outcome.py tests/test_edge_baseline_audit.py
```

### Proof added

- Score bucket derives from normalized score.
- Required identity fields fail closed.
- Explicit valid score bucket is accepted when final score is absent.
- Invalid score bucket is rejected.
- Enrichment preserves existing metadata.

## Scope Guard

Allowed:

- Setup identity contract.
- Score bucket derivation.
- Record enrichment helper.
- Tests and evidence documentation.

Blocked:

- Runtime adoption.
- Strategy/scoring/ranking changes.
- Dashboard display.
- Broker/live behavior.
- Fake seeded production records.

## Approval + Evidence

### Acceptance checks

- `setup_id` is required.
- `entry_rule_id` is required.
- `exit_rule_id` is required.
- `cost_model_version` is required.
- `score_bucket` is derived or explicitly validated.
- Existing record metadata is preserved.

### Next PR
EDGE-08 should begin runtime/candidate adoption of setup identity, or add the outcome reducer if setup identity is already present in candidate payloads.
