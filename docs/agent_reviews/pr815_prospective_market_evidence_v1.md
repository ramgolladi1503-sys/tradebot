# PR #815 — Prospective Market Evidence V1 Review Evidence

mode: RESEARCH_READ_ONLY
candidate_id: PR815_PROSPECTIVE_MARKET_EVIDENCE_V1
decision: REPAIR_IMPLEMENTED_PENDING_EXACT_HEAD_CI_AND_INDEPENDENT_REVIEW
reason: Read-only three-index evidence hardening now requires signed independent live-session attestation, complete identity binding, and full immutable audit hashing; no trading authority granted.
timestamp: 2026-08-11T18:45:00Z
is_order_action: false
broker_api_called: false
source: GITHUB_PR_815_REPOSITORY_EVIDENCE

## Agent Work Contract

Objective: implement and harden a read-only, fail-closed NIFTY/BANKNIFTY/SENSEX prospective evidence finalizer without changing trading decisions or granting execution authority. Scope is limited to the sidecar module, focused tests, its focused workflow, research documentation, and this review artifact.

Repository authority at review start: `main` = `694c2b106416c2b4bbb1093bbbffed28262a0ce9`. PR #815 base remains that exact SHA. The PR remains research/evidence-only.

## Scope Guard

In scope:
- three-index completed-session evidence validation;
- independently attested live provenance;
- complete source/session/instrument identity validation;
- immutable SHA-bound artifact sealing;
- idempotent identical reruns;
- MISSING-not-ZERO index volume semantics;
- replay/adversarial tests;
- exact-head focused CI evidence.

Explicitly out of scope and not modified:
- TradeBuilder, strategy selection, ranking, risk limits, approvals;
- broker clients, positions, order handling, execution engine;
- paper/live authority or runtime mode policy;
- frozen NIFTY model economics;
- BANKNIFTY/SENSEX model discovery;
- global-context model refitting.

Safety contract remains:
- `broker_write_authority=false`
- `order_authority=false`
- `paper_authorized=false`
- `live_authorized=false`

## Grill Me Review

The prior independent exact-SHA review of `1cb1b17a12772b840a92fcb23ddef7fd4b875cca` identified three MAJOR evidence-integrity defects and one MINOR CI-binding defect. The repair attacks each root cause rather than relaxing a validator.

1. Bar metadata can no longer self-certify live origin. `finalize_session` now requires a separately supplied HMAC-SHA256 live-session attestation. The runtime-secret signing key is not written to the output artifact. Self-declared `source_type=live_websocket` plus a feed-session ID is insufficient by itself.

2. Source identity is no longer "populated values must agree." Every bar must carry source type, feed-session ID, provider, token domain, symbol and instrument token. Each value must match the signed attestation for the exact NIFTY/BANKNIFTY/SENSEX identity. A missing identity field or a stable-but-wrong token fails closed.

3. `created_at_ist` is no longer excluded from the semantic hash. It is derived from the signed attestation and included in the immutable semantic payload. This preserves deterministic idempotency while detecting timestamp mutation.

4. The focused GitHub Actions workflow now checks out `${{ github.event.pull_request.head.sha || github.sha }}` and explicitly compares `git rev-parse HEAD` to the expected exact head SHA.

Existing attacks remain in place for exact session completeness, preserved-count gaps, future bars, non-finite OHLC, declared replay/fallback/synthetic/history, code-SHA mutation, artifact mutation, and research-sidecar exception containment.

## Hermes Review

The sidecar still does not import or call broker/order/execution boundaries. The new HMAC attestation mechanism is evidence-only and uses Python standard-library cryptography primitives. No execution authority is introduced.

`safe_finalize_live_session` now fails closed unless the runtime provides all three of:
- `TRADEBOT_LIVE_SESSION_ATTESTATION_PATH`;
- `TRADEBOT_LIVE_SESSION_ATTESTATION_KEY`;
- `TRADEBOT_CODE_SHA`.

Missing/invalid attestation evidence produces `NOT_SEALED`; it never causes the finalizer to infer live truth from OHLC-buffer labels.

The actual trusted producer of the signed live-session attestation is intentionally not fabricated in this PR. That producer must later bind to the authoritative live subscription/feed seam before any shadow-live claim is possible.

## GSD Review

Files changed for this candidate remain limited to:
- `core/prospective_market_evidence.py`
- `tests/test_prospective_market_evidence.py`
- `.github/workflows/prospective-market-evidence-v1.yml`
- `docs/research/prospective_market_evidence_pipeline_v1.md`
- `docs/agent_reviews/pr815_prospective_market_evidence_v1.md`

Evidence required before any offline-certification claim:
- focused compile passes on exact HEAD;
- focused adversarial/replay suite passes on exact HEAD;
- repo-forensics gate passes;
- Code Excellence gates pass;
- Agent Review Evidence gate passes;
- relevant repository CI remains green;
- genuinely independent exact-SHA verification returns no MAJOR/CRITICAL finding and no mandatory UNKNOWN.

No live or structural-edge claim is made by this artifact.

## QA / Safety Review

Adversarial coverage includes:
- feed ending at 14:00;
- NIFTY missing;
- BANKNIFTY missing;
- SENSEX missing;
- duplicate/non-monotonic bars;
- preserved-count one-minute gaps;
- invalid and non-finite OHLC;
- future timestamps;
- declared replay, historical seed, fallback and synthetic provenance;
- replay/historical/synthetic data relabelled as live but lacking a valid independent attestation;
- forged/tampered attestation signature;
- wrong attestation signing key;
- one-bar missing instrument identity;
- stable-but-wrong instrument token;
- source/provider/session/symbol mismatch versus attestation;
- immutable artifact payload tampering;
- immutable `created_at_ist` tampering;
- non-idempotent rerun caused by code-SHA change;
- sidecar exception containment;
- runtime module restricted-boundary call absence;
- OhlcBuffer integration proving buffer provenance alone still cannot seal without independent attestation.

Tests explicitly assert false broker/order/paper/live authority fields. No unit or replay test is treated as live evidence.

## Acceptance Proof

The focused workflow is configured to execute the exact PR head, print the exact checkout SHA, compile the sidecar, and run the complete adversarial/replay test file. Repository-wide CI/check results must be inspected after the repair commits land.

Controlled labels remain evidence-dependent:
- `IMPLEMENTATION_VALID` only after exact-head focused evidence passes;
- `ADVERSARIAL_VALID` only after all declared attacks pass;
- `REPLAY_VALID` only after the OhlcBuffer integration path passes;
- `INDEPENDENTLY_VERIFIED` only after a genuinely independent exact-SHA reviewer verifies the repaired candidate;
- `OFFLINE_CERTIFIED` only after all required gates above are satisfied.

## Runtime Proof Required After Merge

Fresh genuine market-session evidence is required later to establish `SHADOW_LIVE_VALID`. Unit tests, synthetic fixtures, replay-style buffer construction, historical sessions, or prior live sessions cannot substitute for a fresh live session on the exact offline-certified SHA.

The future trusted attestation producer must itself derive identity/session truth from the authoritative Kite live subscription/feed seam. A manually fabricated attestation or test signing key is not live proof.

## What This PR Does Not Prove

This PR does not prove profitability, prediction skill, structural edge, execution viability, prospective support or live readiness. It does not certify the frozen NIFTY model, discover BANKNIFTY/SENSEX models, collect global evidence, or automate the full pre-open lifecycle.

It does not prove fresh live operation until genuine market evidence and the independent live attestation are captured on the exact candidate SHA.

## Human Approval

No human approval is asserted by this review artifact. Merge and any later live-session operation remain subject to repository branch protection and the user's explicit workflow. This artifact records engineering evidence only and grants no trading authority.
