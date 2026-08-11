# PR #815 — Prospective Market Evidence V1 Review Evidence

## Agent Work Contract

Objective: implement and harden a read-only, fail-closed NIFTY/BANKNIFTY/SENSEX prospective evidence finalizer without changing trading decisions or granting execution authority. Scope is limited to the sidecar module, focused tests, its focused workflow, research documentation, and this review artifact.

Repository authority at review start: `main` = `694c2b106416c2b4bbb1093bbbffed28262a0ce9`. PR #815 base is that exact SHA. The PR remains research/evidence-only.

## Scope Guard

In scope:
- three-index completed-session evidence validation;
- live provenance and source/session identity validation;
- immutable SHA-bound artifact sealing;
- idempotent identical reruns;
- MISSING-not-ZERO index volume semantics;
- replay/adversarial tests;
- CI evidence for this sidecar.

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

Assumption attacked: "375 rows means a complete session." The implementation now requires the exact 09:15 through 15:29 IST minute sequence, monotonicity, uniqueness, no gaps, and exact count. A shifted or missing minute cannot pass merely by preserving row count.

Assumption attacked: "matching stored semantic hash means an existing artifact is unchanged." The implementation now recomputes the existing semantic hash and compares the full semantic payload. A tampered artifact retaining the old claimed hash is rejected as an immutable conflict.

Assumption attacked: "filtering to the target date safely ignores extra bars." Future-day bars in the supplied evidence are now rejected rather than silently discarded.

Assumption attacked: "source type plus a session id is enough provenance." Present provider/token/symbol/instrument identity fields must remain stable; mismatched declared symbols, within-symbol identity changes, cross-symbol provider changes, and cross-symbol feed-session changes are rejected.

## Hermes Review

The sidecar imports only completed OHLC state and writes a research artifact. It does not call broker or execution boundaries. Its best-effort runtime wrapper catches all sidecar exceptions and returns `NOT_SEALED` with explicit false authority fields.

The focused workflow previously contained restricted action-marker text inside a self-authored scan, causing the repository Cerberus gate to block the workflow file itself. That redundant scan was removed. Safety is still enforced by repository Cerberus plus the focused runtime-module boundary test; no safety gate was weakened or bypassed.

## GSD Review

Files changed for the hardened candidate:
- `core/prospective_market_evidence.py`
- `tests/test_prospective_market_evidence.py`
- `.github/workflows/prospective-market-evidence-v1.yml`
- `docs/research/prospective_market_evidence_pipeline_v1.md`
- `docs/agent_reviews/pr815_prospective_market_evidence_v1.md`

Evidence required before any offline-certification claim:
- focused compile passes;
- focused adversarial/replay suite passes on exact HEAD;
- repo-forensics gate passes;
- Code Excellence gates pass;
- Agent Review Evidence gate passes;
- relevant repository CI remains green;
- exact-SHA independent verification remains separately required.

Current controlled status at artifact creation: implementation hardened; CI and exact-SHA independent verification are pending. No live or structural-edge claim is made.

## QA / Safety Review

Adversarial cases covered include:
- feed ending at 14:00;
- each required index independently missing;
- duplicate and non-monotonic bars;
- preserved-count minute gaps;
- invalid and non-finite OHLC;
- future timestamps;
- replay, historical seed, fallback, and synthetic provenance;
- within-symbol source identity mismatch;
- cross-symbol provider/session mismatch;
- declared symbol mismatch;
- immutable artifact tampering;
- non-idempotent rerun caused by code-SHA change;
- sidecar exception containment;
- runtime module restricted-boundary call absence;
- OhlcBuffer integration/replay-style assembly preserving provenance.

The tests explicitly assert false broker/order/paper/live authority fields. No unit or replay test is treated as live evidence.

## Acceptance Proof

Acceptance for T01-T03 requires exact-HEAD CI evidence, not this document alone. The focused workflow is designed to compile the sidecar and execute the full adversarial/replay test file. Repository-wide CI/check results must be inspected after the new commits land.

The correct interim labels are:
- `IMPLEMENTATION_VALID` only after exact-HEAD focused evidence passes;
- `ADVERSARIAL_VALID` only after all declared attacks pass;
- `REPLAY_VALID` only after the OhlcBuffer integration path passes;
- `INDEPENDENTLY_VERIFIED` remains unavailable until a genuinely independent exact-SHA reviewer verifies the candidate.

## Runtime Proof Required After Merge

Fresh genuine market-session evidence is required later to establish `SHADOW_LIVE_VALID`. Unit tests, synthetic fixtures, replay-style buffer construction, historical sessions, or prior live sessions cannot substitute for a fresh live session on the exact offline-certified SHA.

The runtime seam must also demonstrate all three canonical index keys are populated with live provenance throughout the full session. If the current live feed does not supply the required source identity/provenance, the correct outcome is `BLOCKED`/`NOT_SEALED`, not a relaxed validator.

## What This PR Does Not Prove

This PR does not prove profitability, prediction skill, structural edge, execution viability, prospective support, or live readiness. It does not certify the frozen NIFTY model, discover BANKNIFTY/SENSEX models, collect global evidence, or automate the full pre-open lifecycle.

It also does not prove fresh live operation until genuine market evidence is captured on the exact candidate SHA.

## Human Approval

No human approval is asserted by this review artifact. Merge and any later live-session operation remain subject to repository branch protection and the user's explicit workflow. This artifact records engineering evidence only and grants no trading authority.
