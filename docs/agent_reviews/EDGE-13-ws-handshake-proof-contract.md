# EDGE-13 — WebSocket Handshake Credential Proof Contract

## Evidence Contract

mode: PAPER
candidate_id: EDGE-13-ws-handshake-proof-contract
decision: ADD_WS_HANDSHAKE_CREDENTIAL_PROOF_CONTRACT
reason: WebSocket failure needs safe proof of credential tail markers before changing feed startup behavior
timestamp: 2026-05-21T06:15:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-13-ws-handshake-proof-contract.md

## Scope

Allowed:

- add a pure proof payload builder
- include safe public key tail and access token tail only
- include stripped access token length
- include internal whitespace flag
- include WebSocket failure proof payload
- include log-line extraction helpers
- add unit tests for proof payload shape and secret safety

Not included:

- strategy changes
- scoring changes
- ranking changes
- threshold changes
- reconnect behavior changes
- feed startup behavior changes
- broker behavior changes
- live order behavior changes
- dashboard changes

## Why this PR exists

EDGE-12 proved the current blocker is WebSocket rejection after REST validation. The current logs do not prove which safe credential tail markers were passed to the WebSocket constructor before rejection.

This PR defines the exact proof payloads needed before wiring into `core/kite_depth_ws.py`. Directly rewriting that large file through the connector is risky, so this PR locks the proof contract first.

## Files Changed

- `core/ws_handshake_credential_proof.py`
- `tests/test_ws_handshake_credential_proof.py`
- `docs/agent_reviews/EDGE-13-ws-handshake-proof-contract.md`

## Tests

```bash
python -m pytest tests/test_ws_handshake_credential_proof.py
```

## Acceptance Proof

- builds handshake attempt proof with safe tail markers only
- builds auth failure proof with safe tail markers only
- detects internal whitespace in stripped access token
- extracts latest proof payload from JSON log lines
- supports fallback extraction from key-value log lines
- does not expose full secrets in proof payload string
- remains read-only and does not change runtime behavior

## Next

After merge, wire the proof contract into `core/kite_depth_ws.py` near WebSocket construction and auth failure callbacks. That later PR should log:

- `FEED_WS_HANDSHAKE_CREDENTIAL_PROOF`
- `FEED_WS_AUTH_FAILURE_PROOF`

No feed behavior should change in that wiring PR.