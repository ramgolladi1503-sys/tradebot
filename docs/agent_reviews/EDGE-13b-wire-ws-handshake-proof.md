# EDGE-13b — Wire WebSocket Handshake Proof into kite_depth_ws

## Evidence Contract

mode: PAPER
candidate_id: EDGE-13b-wire-ws-handshake-proof
decision: WIRE_WS_HANDSHAKE_CREDENTIAL_PROOF
reason: WebSocket 403 failure needs proof of safe credential tail markers at the actual KiteTicker creation and auth-failure points
timestamp: 2026-05-21T06:35:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-13b-wire-ws-handshake-proof.md

## Scope

Allowed:

- import EDGE-13 proof builders
- log `FEED_WS_HANDSHAKE_CREDENTIAL_PROOF` before KiteTicker creation
- log `FEED_WS_AUTH_FAILURE_PROOF` on WebSocket auth failure
- log safe tail markers only
- add static wiring tests

Not included:

- strategy changes
- scoring changes
- ranking changes
- threshold changes
- reconnect behavior changes
- broker behavior changes
- live order behavior changes
- dashboard changes

## Tests

```bash
python -m pytest \
  tests/test_ws_handshake_credential_proof.py \
  tests/test_kite_depth_ws_handshake_proof_wiring.py
```

## Acceptance Proof

- handshake proof is emitted before WebSocket constructor usage
- auth failure proof is emitted before auth-required latch handling
- proof contains only safe tail markers, token length, and whitespace flag
- no full secret is logged
- runtime behavior is unchanged


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
