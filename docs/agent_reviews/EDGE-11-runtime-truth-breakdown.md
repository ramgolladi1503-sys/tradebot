# EDGE-11 — Runtime Truth Breakdown

## Evidence Contract

mode: PAPER
candidate_id: EDGE-11-runtime-truth-breakdown
decision: ADD_RUNTIME_TRUTH_BREAKDOWN
reason: REST validation can pass while engine/feed runtime truth still reports feed/auth failure and zero subscriptions
timestamp: 2026-05-21T05:25:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-11-runtime-truth-breakdown.md

## Scope

Allowed:

- read existing runtime files
- read existing feed files
- read existing auth health/events logs
- read latest paper log lines
- compare source freshness and truth conflicts
- add unit tests for contradictory runtime truth

Not included:

- strategy changes
- scoring changes
- ranking changes
- threshold changes
- feed reconnect changes
- broker/live behavior changes
- dashboard changes

## Why this PR exists

The PAPER session showed `run_live.sh --validate-only` could validate REST credentials while the engine runtime file still reported `AUTH_REQUIRED`, `feed_ok=false`, and zero option subscriptions. EDGE-10 correctly surfaced the failure but did not distinguish REST validation, feed runtime truth, stale file truth, and option subscription truth.

EDGE-11 makes that distinction explicit before another PAPER evidence run.

## Files Changed

- `core/runtime_truth_breakdown.py`
- `tests/test_runtime_truth_breakdown.py`
- `docs/agent_reviews/EDGE-11-runtime-truth-breakdown.md`

## Tests

```bash
python -m pytest tests/test_runtime_truth_breakdown.py
```

## Acceptance Proof

- detects REST validation success while engine runtime file reports auth required
- detects WebSocket/feed failure text in engine/log evidence
- detects stale feed runtime file when engine runtime file is fresh
- detects zero option subscriptions when truth is otherwise clean
- remains read-only and does not change runtime behavior

## Next

After merge, run:

```bash
python -m pytest tests/test_runtime_truth_breakdown.py
python - <<'PY'
import json
from core.runtime_truth_breakdown import build_runtime_truth_breakdown, save_runtime_truth_breakdown
report = build_runtime_truth_breakdown()
path = save_runtime_truth_breakdown(report)
print(path)
print(json.dumps(report['decision'], indent=2))
print(json.dumps(report['truth_conflicts'], indent=2))
PY
```

Use the report to decide whether the next fix belongs in feed auth, stale file publication, or option subscription setup.

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
