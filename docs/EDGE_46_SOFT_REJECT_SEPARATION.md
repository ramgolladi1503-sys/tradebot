# EDGE-46 — Soft Reject Separation

## Purpose

Separate candidate lifecycle states so logs, evidence, and future UI surfaces do not mix these meanings:

- hard reject
- soft reject
- advisory
- debug-only
- rankable
- executable

This fixes the roadmap bug where `no_signal`, `no_candidates_survived`, advisory-only, blocked, debug-only, and rankable states can be mixed in downstream reporting.

## Implementation

Added `core/candidate_state_contract.py`.

The contract exposes:

- `CandidateStateDecision`
- `classify_candidate_state(candidate)`
- stable state constants:
  - `hard_reject`
  - `soft_reject`
  - `advisory`
  - `debug_only`
  - `rankable`
  - `executable`

The classifier is pure and read-only. It inspects candidate fields and `source_flags`, then emits one canonical state plus boolean flags.

## Precedence

The classifier intentionally uses fail-closed precedence:

1. hard reject
2. soft reject
3. debug-only
4. advisory
5. executable
6. rankable
7. unclassified => soft reject

This prevents stale/fallback/unsafe evidence from being hidden by rankable or executable markers.

## Safety

Out of scope:

- no broker calls
- no live order behavior
- no order placement
- no modify/cancel/exit behavior
- no strategy tuning
- no dashboard changes
- no threshold loosening

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge46_candidate_state_contract.py
```

The tests prove:

- hard reject wins over executable/rankable markers
- no-signal and no-candidates-survived are soft rejects
- advisory-only is not rankable/executable
- debug-only is separate from advisory
- rankable and executable are separate states
- unclassified candidates fail to soft reject
