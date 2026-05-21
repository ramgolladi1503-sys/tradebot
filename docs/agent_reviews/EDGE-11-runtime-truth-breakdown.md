# EDGE-11 — Runtime Truth Breakdown

## Evidence Contract

mode: PAPER
candidate_id: EDGE-11-runtime-truth-breakdown
decision: ADD_RUNTIME_TRUTH_BREAKDOWN
reason: REST auth validation can pass while engine/feed runtime truth still reports feed/auth failure and zero subscriptions
timestamp: 2026-05-21T05:25:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-11-runtime-truth-breakdown.md

## Scope

Allowed:

- read existing runtime status files
- read existing feed status files
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

The PAPER session showed `run_live.sh --validate-only` could validate REST auth while the engine status still reported `AUTH_REQUIRED`, `feed_ok=false`, and zero option subscriptions. EDGE-10 correctly surfaced the failure but did not distinguish REST auth, feed runtime truth, stale file truth, and option subscription truth.

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

- detects REST auth OK while engine status reports auth required
- detects WebSocket/feed failure text in engine/log evidence
- detects stale feed runtime file when engine status is fresh
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

Use the report to decide whether the next fix belongs in feed auth, stale status publication, or option subscription setup.