# Hermes Stage 1 — captured replay health authority

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Keep unavailable health truth unknown in historical replay
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Evidence and defect

The Oct. 1 stitched capture has schema `ts, token, symbol, ltp, bid, ask, vol, oi, depth`; it has no receive-time, websocket, subscription-transition, or health fields. Its exact SHA-256 and bounded replay result are recorded in `artifacts/issues_7_11/CAPTURE_REPLAY_20261001.md`. `UpstoxTickReplaySource` currently emits `feed_ok=True`, `websocket_ok=True`, `session_health=NORMAL` when these authorities are absent. The `ParquetBarReplaySource` also supplies those flags and a fixed `option_last_tick_age_sec=0.05` from OHLCV rows. Those values are replay defaults, not source evidence, and may make offline observations appear healthy without a recorded basis.

## Contract

For historical parquet sources:

- Transport/feed health and websocket connectivity are `UNKNOWN` unless the source artifact has explicit, schema-recognized health fields with strict boolean values. Absence, malformed fields, or non-boolean values must remain unknown/fail-closed; never infer health from the presence of ticks or bars.
- Session health is `UNKNOWN` unless the source records an explicit governed session-health value. The replay engine remains read-only.
- Tick freshness/receipt latency is available only when an explicit valid receive timestamp exists. Without it, keep receipt authority unavailable and age unknown. A timestamped bar is not an option quote and must not get a fabricated option tick age.
- Preserve causal event/availability ordering and the existing `ReplayEvent` behavior for deliberately constructed fixtures. Do not alter live feed producers, runtime health gates, candidate/execution safety, strategy rules, order/broker authority, or token-universe policy.

## Authorized GSD scope

Allowed paths:
- `core/replay/governed_market_replay.py`
- `tests/replay/test_replay_fidelity_hardening.py`
- `tests/replay/test_governed_market_replay.py` only if compatibility coverage requires it
- `artifacts/issues_7_11/` replay evidence and ledgers

Forbidden paths include live feed producers, candidate/feed safety, strategy evaluation or thresholds, execution/risk/broker code, credentials, runtime wiring, and configured token-universe files.

## Acceptance gates

1. Capture rows without receive or health fields produce unknown feed/websocket/session health and unknown option age.
2. A valid explicit receipt timestamp remains usable for event availability/latency but does not imply websocket or global feed health.
3. Malformed timestamps/health values do not become healthy defaults.
4. OHLCV bars do not imply option quote freshness or transport health.
5. Hand-constructed replay fixtures retain their existing explicit/default behavior unless tests show that behavior itself is part of a separate defect.
6. Focused replay tests pass; the real Oct. 1 capture probe remains read-only and reports authority flags closed.

**Hermes verdict:** narrow offline replay-source repair authorized. No live behavior or execution authority is changed. The capture cannot establish Issues 7/8 source authority or Issue 11 live latch cause.

## Agent Work Contract

Campaign issue contract; see `issues_7_11_campaign_review.md` for the PR-level Hermes/GSD scope and actions.

## Scope Guard

Issue-level design boundary and restrictions are defined above; the consolidated review records the full campaign boundary.

## Grill Me Review

Campaign risk critique and unresolved proof limits are recorded in `issues_7_11_campaign_review.md`.

## Hermes Review

This file is the issue-specific Hermes contract. The consolidated review records the cross-issue architecture review.

## GSD Review

Execution evidence and test limits are recorded in `issues_7_11_campaign_review.md`; this contract alone is not implementation proof.

## QA / Safety Review

Safety boundary and verification limits are recorded in `issues_7_11_campaign_review.md`.

## High-Risk Path Review

See `issues_7_11_campaign_review.md` for the cross-cutting review of feed and orchestrator high-risk paths. This issue contract does not authorize runtime or broker actions.

## Acceptance Proof

Issue-specific acceptance criteria are defined above. Cross-issue executed proof and its limitations are recorded in `issues_7_11_campaign_review.md`.

## Runtime Proof Required After Merge

Runtime proof requirements are recorded in `issues_7_11_campaign_review.md`; offline contract text does not establish runtime parity.

## What This PR Does Not Prove

See the consolidated review for campaign-level limitations. This issue contract does not independently claim live verification.

## Human Approval

This design contract does not represent human approval. The PR remains subject to human review as described in `issues_7_11_campaign_review.md`.
