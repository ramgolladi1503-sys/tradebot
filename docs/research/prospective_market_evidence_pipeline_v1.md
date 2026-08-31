# Prospective Market Evidence Pipeline V1

Status: **IMPLEMENTATION CANDIDATE — NOT EDGE CERTIFICATION**

This sidecar turns completed TradeBot OHLC observations into immutable research evidence for NIFTY, BANKNIFTY and SENSEX. It does not make trading decisions and has no broker/order authority.

## Safety

`broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`.

A sidecar failure must never block or degrade trading. Historical seed, replay, fallback and recovered/synthetic bars cannot certify a live session. Missing index volume is represented as missing, never as observed zero.

## Independent live-attestation boundary

Bar metadata alone is not accepted as proof of live origin. A session can be sealed only when a separately produced live-session attestation is supplied and its HMAC-SHA256 verifies under the trusted runtime verification key in `TRADEBOT_LIVE_SESSION_ATTESTATION_KEY`.

`finalize_session()` does **not** accept a verification-key argument. This prevents the caller supplying the attestation from also selecting the key against which that attestation is trusted. An attacker-selected key can sign a syntactically valid attestation, but that signature is rejected unless it verifies under the separately configured trusted runtime key.

The attestation must bind:

- schema and attestation source;
- `VERIFIED_LIVE_SESSION` status;
- target session date;
- exact TradeBot code SHA;
- attestation timestamp on the exact target session date, at or after 15:30 IST, and not in the future beyond the bounded clock-skew allowance;
- provider = `kite`;
- token domain = `kite_instrument_token`;
- one live feed session ID;
- exact NIFTY, BANKNIFTY and SENSEX instrument-token identities.

The accepted canonical index identities are repository-pinned at this evidence boundary: NIFTY `256265`, BANKNIFTY `260105`, and SENSEX `265`. Agreement between bars and an attestation is therefore insufficient by itself: a consistently wrong positive token in both bars and attestation is rejected. Any legitimate future token migration requires a reviewed code change to this trust policy.

The finalizer then requires every one-minute bar to carry complete provenance (`source_type`, feed-session ID, provider, token domain, symbol and instrument token) and match the verified attestation exactly. Missing identity fields, mismatched provider/session/symbol, unsigned or modified attestations, attacker-key signatures, wrong canonical identities and future-dated attestation chronology fail closed.

The runtime wrapper does not manufacture this attestation. It requires `TRADEBOT_LIVE_SESSION_ATTESTATION_PATH`, `TRADEBOT_LIVE_SESSION_ATTESTATION_KEY` and `TRADEBOT_CODE_SHA`; if they are missing or invalid it returns `NOT_SEALED`. The trusted producer is implemented as a dormant prerequisite in this reconstruction, but remains unwired until a separately authorized read-only session.

## Session gate

A seal requires all three indices, 375 unique monotonic one-minute bars from 09:15 through 15:29 IST, valid finite OHLC geometry, one consistent attested live feed session identity and complete live-websocket provenance. Incomplete or conflicting evidence fails closed.

Artifacts are canonical JSON with a semantic SHA-256 covering the full audit payload, including `created_at_ist`. `created_at_ist` is derived from the verified attestation rather than wall-clock rerun time, so identical reruns remain deterministic while timestamp mutation is detected. An identical rerun is idempotent; a different artifact for the same session date is an immutable conflict.

## Global-context experiment boundary

This collector does not refit or reimplement the frozen Global Context Model V1. Model SHA-256 remains:

`d432566f5dc15b5f28d10c82879e0cb779ae306e102aab091d6251d9e167e17e`

The standalone frozen scorer remains authority for global inputs, prediction deadlines, prediction immutability and outcome binding. Adding GIFT Nifty, USDINR, crude, rates, Asian markets or any other variable is outside this frozen experiment.

## Certification ladder

`IMPLEMENTATION_VALID -> ADVERSARIAL_VALID -> REPLAY_VALID -> INDEPENDENTLY_VERIFIED -> OFFLINE_CERTIFIED -> SHADOW_LIVE_VALID`

None of those imply `PROSPECTIVE_SUPPORTED`, `STRUCTURAL_EDGE_CERTIFIED`, execution viability or profitability. Fresh genuine live-market evidence is required for `SHADOW_LIVE_VALID`; unit tests and replay cannot substitute for it.

## Current integration boundary

V1 deliberately lands the fail-closed finalizer and certification contract first. The finalizer refuses to infer live truth from caller-declared bar provenance alone and now also refuses caller-selected verification keys, non-canonical index identities and impossible future attestation chronology.

Before automatic sealing can be enabled, the trusted producer must be wired into a separately authorized read-only session and generate the signed attestation from the authoritative subscription/feed seam for all three canonical indices. This implementation does not provide that live wiring or evidence; the absence of a fresh session remains a live-integration blocker.

The focused GitHub Actions workflow checks out and verifies the exact PR head SHA rather than relying on the synthetic PR merge ref.
