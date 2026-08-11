# Prospective Market Evidence Pipeline V1

Status: **IMPLEMENTATION CANDIDATE — NOT EDGE CERTIFICATION**

This sidecar turns completed TradeBot OHLC observations into immutable research evidence for NIFTY, BANKNIFTY and SENSEX. It does not make trading decisions and has no broker/order authority.

## Safety

`broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`.

A sidecar failure must never block or degrade trading. Historical seed, replay, fallback and recovered/synthetic bars cannot certify a live session. Missing index volume is represented as missing, never as observed zero.

## Independent live-attestation boundary

Bar metadata alone is not accepted as proof of live origin. A session can be sealed only when a separately produced live-session attestation is supplied and its HMAC-SHA256 verifies under a runtime-secret key that is not stored in the evidence artifact.

The attestation must bind:

- schema and attestation source;
- `VERIFIED_LIVE_SESSION` status;
- target session date;
- exact TradeBot code SHA;
- attestation timestamp after the session close;
- provider = `kite`;
- token domain = `kite_instrument_token`;
- one live feed session ID;
- exact NIFTY, BANKNIFTY and SENSEX instrument-token identities.

The finalizer then requires every one-minute bar to carry complete provenance (`source_type`, feed-session ID, provider, token domain, symbol and instrument token) and match the signed attestation exactly. Missing identity fields, a stable-but-wrong token, a mismatched provider/session/symbol, an unsigned attestation, a forged attestation or a wrong signing key fail closed.

The runtime wrapper does not manufacture this attestation. It requires `TRADEBOT_LIVE_SESSION_ATTESTATION_PATH`, `TRADEBOT_LIVE_SESSION_ATTESTATION_KEY` and `TRADEBOT_CODE_SHA`; if they are missing or invalid it returns `NOT_SEALED`. The actual trusted live-runtime attestation producer remains a separate wiring requirement before shadow-live validation.

## Session gate

A seal requires all three indices, 375 unique monotonic one-minute bars from 09:15 through 15:29 IST, valid finite OHLC geometry, one consistent attested live feed session identity and complete live-websocket provenance. Incomplete or conflicting evidence fails closed.

Artifacts are canonical JSON with a semantic SHA-256 covering the full audit payload, including `created_at_ist`. `created_at_ist` is derived from the signed attestation rather than wall-clock rerun time, so identical reruns remain deterministic while timestamp mutation is detected. An identical rerun is idempotent; a different artifact for the same session date is an immutable conflict.

## Global-context experiment boundary

This collector does not refit or reimplement the frozen Global Context Model V1. Model SHA-256 remains:

`d432566f5dc15b5f28d10c82879e0cb779ae306e102aab091d6251d9e167e17e`

The standalone frozen scorer remains authority for global inputs, prediction deadlines, prediction immutability and outcome binding. Adding GIFT Nifty, USDINR, crude, rates, Asian markets or any other variable is outside this frozen experiment.

## Certification ladder

`IMPLEMENTATION_VALID -> ADVERSARIAL_VALID -> REPLAY_VALID -> INDEPENDENTLY_VERIFIED -> OFFLINE_CERTIFIED -> SHADOW_LIVE_VALID`

None of those imply `PROSPECTIVE_SUPPORTED`, `STRUCTURAL_EDGE_CERTIFIED`, execution viability or profitability. Fresh genuine live-market evidence is required for `SHADOW_LIVE_VALID`; unit tests and replay cannot substitute for it.

## Current integration boundary

V1 deliberately lands the fail-closed finalizer and certification contract first. The finalizer now refuses to infer live truth from caller-declared bar provenance alone. Before automatic sealing can be enabled, a trusted live-runtime producer must generate the signed attestation from the authoritative subscription/feed seam for all three canonical indices.

The focused GitHub Actions workflow checks out and verifies the exact PR head SHA rather than relying on the synthetic PR merge ref.
