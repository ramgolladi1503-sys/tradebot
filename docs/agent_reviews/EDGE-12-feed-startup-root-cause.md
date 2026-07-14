# EDGE-12 — Feed Startup Root Cause Report

## Evidence Contract

mode: PAPER
candidate_id: EDGE-12-feed-startup-root-cause
decision: ADD_FEED_STARTUP_ROOT_CAUSE_REPORT
reason: PAPER evidence cannot be produced until feed startup explains credential source, WebSocket rejection, latch state, and subscription state
timestamp: 2026-05-21T05:55:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-12-feed-startup-root-cause.md

## Scope

Allowed:

- read local credential metadata without printing secrets
- read existing runtime files
- read existing feed runtime files
- read existing auth health logs
- read existing WebSocket event logs when present
- read latest paper log lines
- compare safe credential tail markers
- report root cause and next action
- add unit tests for feed startup diagnosis

Not included:

- strategy changes
- scoring changes
- ranking changes
- threshold changes
- reconnect behavior changes
- broker behavior changes
- live order behavior changes
- dashboard changes

## Why this PR exists

EDGE-11 proved the current blocker is feed startup truth: REST validation can succeed while the engine/feed path reports `AUTH_REQUIRED`, `feed_ok=false`, zero option subscriptions, and a WebSocket 403 failure.

EDGE-12 narrows that down further by comparing safe tail markers and latch evidence. It answers whether the feed startup used the same credential tail as the local credential file, whether env drift exists, whether a latch blocked restart, and whether subscriptions were attempted after startup.

## Files Changed

- `core/feed_startup_root_cause_report.py`
- `tests/test_feed_startup_root_cause_report.py`
- `docs/agent_reviews/EDGE-12-feed-startup-root-cause.md`

## Tests

```bash
python -m pytest tests/test_feed_startup_root_cause_report.py
```

## Acceptance Proof

- detects WebSocket rejection when the feed credential tail matches the local credential file tail
- detects feed credential mismatch when the feed credential tail differs from the local credential file tail
- detects restart blocked by auth-required latch evidence
- report is read-only
- report does not expose full secrets
- report does not change runtime behavior

## Next

After merge, run:

```bash
python -m pytest tests/test_feed_startup_root_cause_report.py
python - <<'PY'
import json
from core.feed_startup_root_cause_report import build_feed_startup_root_cause_report, save_feed_startup_root_cause_report
report = build_feed_startup_root_cause_report()
path = save_feed_startup_root_cause_report(report)
print(path)
print(json.dumps(report['decision'], indent=2))
print(json.dumps(report['credential_sources'], indent=2))
print(json.dumps(report['websocket_failure'], indent=2))
PY
```

Only after this report is understood should the next PR touch feed startup behavior.

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
