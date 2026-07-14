# EDGE-09 — Runtime Setup Identity Adoption Helper

## Evidence Contract

mode: PAPER
candidate_id: EDGE-09-runtime-setup-identity-adoption
decision: ADD_RUNTIME_SETUP_IDENTITY_HELPER
reason: provide a safe helper for copying supplied setup identity from trade objects into paper journal payloads
timestamp: 2026-05-21T02:40:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-09-runtime-setup-identity-adoption.md

## Scope

Allowed:

- extract setup identity fields from trade objects
- attach supplied setup identity to paper journal payloads
- avoid fabricating missing setup identity
- add focused tests

Not included:

- strategy changes
- scoring changes
- ranking changes
- dashboard work
- expectancy report
- direct execution-router patch in this PR

## Review Notes

This PR is intentionally conservative. It does not invent setup identity from strategy family or regime alone.

The direct execution-router file update was not included in this connector patch because that file is live-adjacent and the update was blocked. The next local patch should import `attach_runtime_setup_identity` and wrap the paper outcome payload before calling `record_paper_outcome`.

## Files Changed

- `core/paper_runtime_setup_identity.py`
- `tests/test_paper_runtime_setup_identity.py`
- `docs/agent_reviews/EDGE-09-runtime-setup-identity-adoption.md`

## Tests

```bash
python -m pytest tests/test_paper_runtime_setup_identity.py tests/test_paper_outcome_journal.py tests/test_edge_setup_identity.py
```

## Acceptance Proof

- supplied setup identity fields are extracted from trade objects
- missing setup identity is not fabricated
- blank fields are skipped
- existing journal payload values are preserved when identity is attached

## Next

Patch the actual paper execution outcome call site to use `attach_runtime_setup_identity(payload, trade)` before journal write.

## Agent Work Contract

N/A

## Scope Guard

N/A

## Grill Me Review

N/A

## Hermes Review

N/A

## GSD Review

N/A

## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A
