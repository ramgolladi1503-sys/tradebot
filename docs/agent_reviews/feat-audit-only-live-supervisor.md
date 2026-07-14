# Agent Review: Audit-Only Live Supervisor

**Branch:** `feat/audit-only-live-supervisor`
**Author:** Tradebot Autonomous Agent (GSD)

- mode: PAPER
- candidate_id: PR-546
- decision: ACCEPT
- reason: Supervisor wrapper safely restarts crashed process
- timestamp: 2026-06-10
- is_order_action: false
- broker_api_called: false
- source: gsd_agent

## Agent Work Contract
This PR implements the process-level supervisor required by the Feed Module RCA (MOD-10) to safely restart the system after a fatal WS feed disconnect or Twisted ReactorNotRestartable failure. It preserves all safety gates.

## Scope Guard
- `scripts/run_live_supervised.sh` and `scripts/live_supervisor.py` added as independent execution wrappers.
- `tests/test_live_supervisor.py` added to verify logic.
- NO modifications to application logic, order flow, broker integrations, or strategy paths.
- `ALLOW_LIVE_ORDERS` and `MANUAL_APPROVAL_REQUIRED` remain intact and enforced.

## Grill Me Review
No new systemic risk introduced. The supervisor wrapper does not disable the orchestrator sleep or bypass feed verification, it merely restarts the Python process externally upon a fatal exit code.

## Hermes Review
The contract requires external supervisors to manage fatal reactor errors. Providing this script explicitly documents and provides a tested implementation for this system boundary.

## GSD Review
I implemented the supervisor exactly as specified in the RCA. I also included a Python equivalent for reliability, and a full unit test to ensure exit code parsing, restart counts, and wait seconds are fully respected.

## QA / Safety Review
* No runtime execution in LIVE or PAPER altered.
* Process restart count bounded explicitly by `LIVE_SUPERVISED_MAX_RESTARTS`.

## Acceptance Proof
`test_live_supervisor.py` confirms that the supervisor will:
1. Restart precisely X times when the script crashes (exit 1).
2. Cease restarts when the maximum is reached.
3. Cease restarts gracefully on a clean exit (exit 0).

## Runtime Proof Required After Merge
Once deployed, the supervisor should be observed returning the process to a healthy, recovered state (rather than sleeping forever) upon the first simulated or actual `ReactorNotRestartable` event in an offline market soak.

## What This PR Does Not Prove
This PR does not guarantee that the resumed session will have a connected WebSocket (e.g. if the Kite token is invalidated). It only proves the process reboots safely to attempt it.

## Human Approval
Requires explicit human review before merge, per standard project protocol.


## High-Risk Path Review

N/A
