# Prospective Market Evidence Pipeline V1

Status: **IMPLEMENTATION CANDIDATE — NOT EDGE CERTIFICATION**

This sidecar turns existing completed TradeBot live OHLC observations into immutable research evidence for NIFTY, BANKNIFTY and SENSEX. It does not make trading decisions and has no broker/order authority.

## Safety

`broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`.

A sidecar failure must never block or degrade trading. Historical seed, replay, fallback and recovered/synthetic bars cannot certify a live session. Missing index volume is represented as missing, never as observed zero.

## Session gate

A seal requires all three indices, 375 unique monotonic one-minute bars from 09:15 through 15:29 IST, valid OHLC geometry, one consistent live feed session identity and live-websocket provenance. Incomplete or conflicting evidence fails closed.

Artifacts are canonical JSON with a semantic SHA-256. An identical rerun is idempotent; a different artifact for the same session date is an immutable conflict.

## Global-context experiment boundary

This collector does not refit or reimplement the frozen Global Context Model V1. Model SHA-256 remains:

`d432566f5dc15b5f28d10c82879e0cb779ae306e102aab091d6251d9e167e17e`

The standalone frozen scorer remains authority for global inputs, prediction deadlines, prediction immutability and outcome binding. Adding GIFT Nifty, USDINR, crude, rates, Asian markets or any other variable is outside this frozen experiment.

## Certification ladder

`IMPLEMENTATION_VALID -> REPLAY_VALID -> SHADOW_LIVE_VALID -> MERGEABLE`

None of those imply `PROSPECTIVE_SUPPORTED`, `STRUCTURAL_EDGE_CERTIFIED`, execution viability or profitability. Fresh live-market evidence is required for `SHADOW_LIVE_VALID`; unit tests and replay cannot substitute for it.

## Current integration boundary

V1 deliberately lands the fail-closed finalizer and certification contract first. Runtime wiring must be reviewed against the exact live OHLC provenance actually emitted by `main` before enabling automatic sealing. Do not silently wire to a buffer that includes historical warm seed or lacks SENSEX live coverage.
