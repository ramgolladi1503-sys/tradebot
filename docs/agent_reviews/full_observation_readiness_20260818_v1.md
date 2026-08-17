# Full Observation Readiness 2026-08-18 V1

## Agent Work Contract
Objective: establish the strongest defensible premarket repository/program readiness state for the 2026-08-18 TradeBot live observation session without changing or merging into the frozen live producer.

Frozen live producer authority: `f0f5b3d3659415ab36662291e91b8f57fd8d1e07`.

Allowed scope: additive validation/research-only tooling, exact-SHA contract rehearsal, post-close counterfactual analytics, tests, CI, and evidence documentation.

Prohibited scope: producer/feed/broker/order changes, secondary market-hours WebSocket ownership, live/paper/order authorization, historical-to-prospective promotion, missing-to-zero conversion, or structural-edge certification.

## Scope Guard
This branch starts exactly at the frozen producer SHA. It adds only a post-close advisory/rejected counterfactual analyzer, a full-program exact-SHA readiness validator, focused tests, this review document, and a focused workflow. It does not modify existing producer code.

## Grill Me Review
The principal false-positive risk is treating preparation as live readiness. The validator therefore emits `FULL_OBSERVATION_PROGRAM_READY=PASS` only with scope `PREMARKET_REPOSITORY_AND_POSTCLOSE_PROGRAM_READINESS_ONLY`, while explicitly keeping `LIVE_READY=false`, `LIVE_VERIFIED=false`, `PROSPECTIVE_SUPPORTED=false`, and `STRUCTURAL_EDGE_CERTIFIED=false`.

The frozen producer's pre-live gate is not treated as live tick proof because its current implementation derives `live_tick_proof_obtained` from market-open state. Actual advancing tick evidence remains mandatory after market open.

## Hermes Review
Cross-lane authorities are immutable 40-character SHAs. CI requires those commit objects to exist and the rehearsal reads exact files with `git show SHA:path`. Symbolic branch names are not accepted as evidence authority.

Aixion PR790 is constrained to `--once` post-close use. Its market-hours live-canary runbook is not authorized for this session because the session contract permits only one producer/feed owner.

## GSD Review
The implementation chooses the smallest high-information additions:

- reuse existing H1 exporter rather than rebuild it;
- reuse PR815 only as offline/read-only evidence machinery and preserve its missing live-attestation producer blocker;
- reuse T25's hardened offline evaluator;
- reuse PR838 kernel sealer/ingestor;
- reuse PR839 subscription reconciliation;
- reuse PR840 detached post-close orchestrator;
- reuse PR790's tested candidate-lineage and bid/ask outcome machinery post-close only;
- add only the missing advisory/rejected counterfactual target/stop analyzer.

No strategy logic or execution path is altered.

## QA / Safety Review
The advisory analyzer enforces:

- exact option instrument identity and expiry;
- observations strictly after the candidate signal timestamp;
- causal first-touch ordering;
- ambiguous same-timestamp target/stop classification;
- duplicate candidate IDs fail closed;
- missing required fields remain unavailable;
- rejected/advisory candidate is never represented as a trade;
- target/stop touch is never represented as realized P&L;
- write-once external output;
- all trading authorities false.

The full readiness validator verifies all referenced exact SHAs and controlled boundaries. CI separately asserts all trading/edge/live verdicts remain false.

## High-Risk Path Review
No broker client, WebSocket client, subscription mutator, order router, execution engine, or strategy generator is invoked by either new script. The full-program validator only executes local `git` reads and JSON output. The advisory analyzer only reads supplied JSONL evidence and writes one external JSON artifact.

## Acceptance Proof
Acceptance requires:

1. exact PR-head checkout;
2. focused compile pass;
3. focused tests pass;
4. all referenced exact commit objects resolve;
5. exact-SHA cross-lane rehearsal exits zero;
6. controlled verdict is `FULL_OBSERVATION_PROGRAM_READY=PASS` with live/prospective/edge claims false;
7. frozen-candidate read-only safety remains green where applicable.

## Runtime Proof Required After Merge
No merge is required or requested before the live session. Before launch, the operator must freshly prove local producer exact SHA/clean state, >=10 GiB free internal disk, credential/auth health, no competing producer/feed process, writable external runtime root, and all authority flags false. After market open, actual advancing live ticks must be observed from the frozen producer before any `LIVE_VERIFIED` claim.

## What This PR Does Not Prove
It does not prove current credentials, current disk space, current process isolation, live tick delivery, exchange completeness, PR815 live attestation, prospective support, execution viability, profitability, or structural edge.

## Human Approval
Human approval remains required for any change to producer authority, any merge into the live producer, any market-hours secondary observer, or any trading authorization. This validation branch itself grants none of those authorities.

## Controlled Verdict Boundary
If the focused workflow passes, the maximum allowed repository claim is:

`FULL_OBSERVATION_PROGRAM_READY=PASS`

with scope:

`PREMARKET_REPOSITORY_AND_POSTCLOSE_PROGRAM_READINESS_ONLY`

and simultaneously:

`LIVE_READY=false`
`LIVE_VERIFIED=false`
`PROSPECTIVE_SUPPORTED=false`
`STRUCTURAL_EDGE_CERTIFIED=false`
`broker_write_authority=false`
`order_authority=false`
`paper_authorized=false`
`live_authorized=false`
