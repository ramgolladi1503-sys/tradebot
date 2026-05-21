# EDGE-08 — Adopt Setup Identity In Paper Outcome Journal

## Evidence Contract

mode: PAPER
candidate_id: EDGE-08-adopt-setup-identity-in-paper-outcomes
decision: ADOPT_SETUP_IDENTITY_IN_PAPER_OUTCOME_JOURNAL
reason: preserve setup identity in journal rows when supplied
timestamp: 2026-05-20T21:10:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-08-adopt-setup-identity-in-paper-outcomes.md

## Scope

Allowed:

- preserve complete setup identity in paper journal records
- keep old journal records working when setup fields are absent
- reject partial setup identity
- add focused tests

Not included:

- strategy changes
- scoring changes
- ranking changes
- dashboard work
- expectancy report

## Review Notes

This PR does not fabricate setup identity. It only preserves identity supplied by upstream records.

It is intentionally backward compatible. Forcing setup identity on every existing paper row would break older paths before upstream payloads are ready.

## Files Changed

- `core/paper_outcome_journal.py`
- `tests/test_paper_outcome_journal.py`
- `docs/agent_reviews/EDGE-08-adopt-setup-identity-in-paper-outcomes.md`

## Tests

```bash
python -m pytest tests/test_paper_outcome_journal.py tests/test_edge_setup_identity.py tests/test_paper_exit_outcome.py tests/test_edge_baseline_audit.py
```

## Acceptance Proof

- existing paper outcome record still writes without setup fields
- complete setup fields reach the normalized journal record
- partial setup fields are rejected
- score bucket is derived from final score
- setup identity metadata is retained

## Next

Adopt setup identity in actual candidate payloads so real paper records include setup and rule identifiers.