# EDGE-14 — Status Provenance Report

## Evidence Contract

mode: PAPER
candidate_id: EDGE-14-status-provenance
decision: ADD_STATUS_PROVENANCE_REPORT
reason: runtime status can report a WebSocket 403 while fresh process logs show no WebSocket startup proof
timestamp: 2026-05-21T07:10:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-14-status-provenance.md

## Scope

Allowed:

- read runtime status files
- read suggestions status file
- read runtime health file
- read feed runtime file
- read auth health and auth events logs
- read depth watchdog log
- read latest paper proof log
- classify whether status failure is fresh or reused
- add unit tests for provenance classification

Not included:

- strategy changes
- scoring changes
- ranking changes
- threshold changes
- credential handling changes
- reconnect behavior changes
- broker behavior changes
- live order behavior changes
- dashboard changes

## Why this PR exists

EDGE-13b added proof events to the actual WebSocket startup path. The next controlled PAPER run still produced status files with a WebSocket 403 reason, but the fresh process log did not contain proof events, credential stats, or ticker creation lines.

That means the system must prove whether the status reason came from a fresh WebSocket attempt or from copied / reused runtime truth.

## Files Changed

- `core/ws_status_provenance_report.py`
- `tests/test_ws_status_provenance_report.py`
- `docs/agent_reviews/EDGE-14-status-provenance.md`

## Tests

```bash
python -m pytest tests/test_ws_status_provenance_report.py
```

## Acceptance Proof

- detects fresh WebSocket failure when proof and failure lines exist
- detects status written without fresh WebSocket startup proof
- detects stale status reuse when current proof logs are old
- report is read-only
- report does not change runtime behavior

## Next

After merge, run:

```bash
python -m pytest tests/test_ws_status_provenance_report.py
python - <<'PY'
import json
from core.ws_status_provenance_report import build_ws_status_provenance_report, save_ws_status_provenance_report
report = build_ws_status_provenance_report()
path = save_ws_status_provenance_report(report)
print(path)
print(json.dumps(report['decision'], indent=2))
print(json.dumps(report['observed_runtime_path'], indent=2))
print(json.dumps(report['status_truth'], indent=2))
PY
```

Only if the report says `fresh_ws_attempt_failed` should the next work inspect provider handshake behavior. If it says status was written without fresh startup proof, the next work must trace the status writer input.