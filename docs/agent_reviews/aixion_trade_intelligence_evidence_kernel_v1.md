# Agent Review — Aixion Trade Intelligence Evidence Kernel V1

mode: PAPER_AND_OFFLINE_EVIDENCE
candidate_id: aixion_trade_intelligence_evidence_kernel_v1
decision: OFFLINE_CERTIFIED_LIVE_CANARY_REQUIRED
reason: Adds a read-only canonical evidence, deterministic replay, candidate-lineage, causal outcome, and reporting lane without changing trading authority.
timestamp: 2026-08-04T18:30:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
strategy_logic_changed: false
execution_logic_changed: false
risk_logic_changed: false

## Objective

Create the smallest complete evidence kernel needed to observe TradeBot candidates, attach exact market evidence, calculate causal outcomes, and fail closed when data or contracts are incomplete.

## Agent Work Contract

- Repository: `ramgolladi1503-sys/tradebot`
- Base commit: `422a4ccd639fc8c2f594506374cd0d2a39fc2d1a`
- Branch: `agent/aixion-trade-intelligence-evidence-kernel-v1`
- Draft PR: `#790`
- Authority: read-only analytics and evidence only.
- Required result: deterministic offline evidence certification plus a separate read-only market-session canary.
- Forbidden result: profitability, strategy-edge, paper/live promotion, or broker-execution claim.

Allowed paths:

- `aixion_trade_intelligence/`
- `.github/workflows/aixion-trade-intelligence-v1.yml`
- `scripts/build_trade_intelligence_session_contract.py`
- `scripts/generate_offline_fixture.py`
- `scripts/run_tradebot_intelligence_observer.py`
- `scripts/import_upstox_parquet.py`
- `scripts/finalize_trade_intelligence_session.py`
- `tests/test_aixion_*`
- `docs/architecture/aixion_trade_intelligence_v1.md`
- `docs/runbooks/aixion_trade_intelligence_live_canary.md`
- this review document;
- `research/aixion_trade_intelligence_v1/`.

Forbidden paths and behavior:

- no `strategies/` changes;
- no TradeBuilder, ranking, risk, broker, order, orchestrator, execution configuration, or dashboard changes;
- no inferred bid, ask, strike, expiry, fill, or missing instrument identity;
- no embedded generic trading horizon or profitability threshold;
- no live broker call;
- no merge before human review and separate live-canary review.

## Scope Guard

Verdict: PASS

The reviewed commit changes 45 files only in the allowed package, scripts, focused tests, documentation, research evidence, and focused CI workflow. The GitHub compare result shows no strategy, TradeBuilder, ranking, risk, broker/order, orchestrator, production configuration, or dashboard path.

The focused workflow also contains an explicit forbidden-production-surface guard. It passed against the exact published commit.

## Grill Me Review

Verdict: PASS_WITH_LIVE_GAP

Questions challenged:

1. Can a missing bid or ask become an executable option outcome?
   - No. LTP-only evidence remains `LTP_ONLY`; incomplete ask/bid evidence fails `OUTCOME_EVIDENCE_COMPLETE`.
2. Can a candidate receive a default outcome horizon?
   - No. Horizons and delay scenarios must come from the candidate outcome contract.
3. Can a future feature or quote be treated as decision-time evidence?
   - No. Feature availability is checked against decision event time; quote selection uses the first quote available at or after the causal time.
4. Can duplicate or rewritten source evidence silently double-count?
   - No. Identical event IDs are idempotently deduplicated; conflicting duplicates reject replay; the tailer fingerprints checkpoints and detects source rewrites/truncation.
5. Can finalization create duplicate terminal records after interruption?
   - No. Finalization is idempotent once `SESSION_ENDED` exists.
6. Can the quote importer silently ingest the whole market when identities are unresolved?
   - No. It requires exact explicit or derived instruments unless `--all-instruments` is consciously supplied.
7. Can the certification be mistaken for a trading-edge certification?
   - No. The successful verdict is `PIPELINE_OFFLINE_CERTIFIED`, while `strategy_edge_certified` is always false in V1.

Residual gap: offline testing cannot prove tomorrow’s exact callback, filesystem, timing, capture completion, or operator lifecycle.

## Hermes Review

Verdict: PASS

Architecture consistency:

- Existing TradeBot candidate lineage, feed truth, execution truth, Upstox capture, replay, RAG, risk, and broker owners remain authoritative.
- The new package adapts and joins evidence instead of replacing those owners.
- The hot path is read-only and file-backed; post-session analysis is separated from execution authority.
- JSONL is the immutable source; Parquet is optional derived output.
- Analytics dependencies are declared in the session contract. Missing futures, constituent weights, two-sided quotes, or pairing authority produce unavailable metrics rather than fabricated values.
- A separate repository or distributed event stack is deferred until the contract and canary justify it.

## GSD Review

Verdict: PASS

Execution completed:

1. Built the canonical event, storage, replay, quality, lineage, outcome, analytics, certification, and report kernel.
2. Added existing candidate-ledger and Upstox evidence adapters.
3. Added a checkpointed read-only observer.
4. Added exact-instrument Parquet import and deferred idempotent finalization.
5. Added a point-in-time session-contract builder tied to instrument-master hashes.
6. Added 45 focused tests and negative controls.
7. Certified the deterministic fixture.
8. Certified a real August 3 corpus of 18,014 canonical events.
9. Preserved the real negative result `UNDERLYING_WRONG x2` rather than tuning it away.
10. Published one isolated commit and opened draft PR #790.
11. Passed the dedicated GitHub workflow on the exact published commit.

## QA / Safety Review

Verdict: PASS_WITH_LIVE_GAP

Focused coverage includes:

- schema and timezone validation;
- payload hash verification;
- non-finite value rejection;
- process-safe append and batch append;
- deterministic replay and duplicate conflict handling;
- expected instrument/event and producer reconciliation;
- look-ahead detection;
- producer sequence gaps;
- candidate lineage, approvals, orders, and fills;
- causal option ask-entry and bid-exit outcomes;
- malformed/missing outcome contracts;
- incomplete executable evidence;
- analytics dependency contracts;
- session-contract index/future resolution;
- observer deferred lifecycle;
- idempotent finalization;
- JSONL rotation, rewrite, truncation, partial-line, and malformed-source behavior;
- Upstox epoch units and LTP-only preservation.

Safety controls:

- tests perform no network or broker action;
- no order router is imported;
- analytics output defaults under runtime evidence paths;
- observer and importer failures return nonzero and leave TradeBot authority unchanged;
- unsuccessful gates cannot be manually relabeled by the certification code.

## Acceptance Proof

Published commit: `ea2bfa43e253035d061f2e9e49ea9101b0606867`

Dedicated GitHub workflow:

- workflow: `Aixion Trade Intelligence Evidence Kernel`
- run: `30944072913`
- result: success
- checkout: success
- compile: success
- 45 focused tests: success
- deterministic fixture certification: success
- forbidden production-surface guard: success
- offline proof upload: success

Offline proof:

```text
fixture pipeline: PIPELINE_OFFLINE_CERTIFIED
real August 3 corpus: PIPELINE_OFFLINE_CERTIFIED
real event count: 18,014
real quote events: 18,009
real look-ahead violations: 0
real outcome classifications: UNDERLYING_WRONG x2
strategy edge certified: false
```

## Runtime Proof Required After Merge

The code should remain draft/unmerged for the first read-only canary. If a later human merge decision is made, the same proof remains mandatory for the merged revision.

The canary must publish and review:

1. exactly one `SESSION_STARTED`, one `OBSERVER_STOPPED`, and one final `SESSION_ENDED`;
2. checkpoint progression without source rewrite/truncation incidents;
3. exact candidate-ledger row count;
4. exact imported market-event count;
5. producer reconciliation with no sequence gaps;
6. point-in-time instrument-master hash and exact index/option identities;
7. no look-ahead or timestamp-order violation;
8. complete two-sided option evidence for every declared outcome horizon;
9. zero analysis errors;
10. generated certification and session reports;
11. no impact on TradeBot strategy, risk, broker, order, exit, or runtime authority.

A failed canary stays failed. It must not be relabeled valid manually.

## What This PR Does Not Prove

- It does not prove a profitable strategy or structural edge.
- It does not certify any candidate for live trading.
- It does not calibrate queue position or fill probability.
- It does not prove capacity, market impact, or risk of ruin.
- It does not prove holdout or walk-forward profitability.
- It does not prove CAS directional edge.
- It does not implement autonomous strategy mutation, model promotion, agent trading, or LLM order authority.
- It does not prove tomorrow’s live filesystem/callback lifecycle until the canary is completed.

## Human Approval

Status: PENDING

- PR #790 remains draft and unmerged.
- A human must review the diff and repository-wide CI.
- A human must review the separate read-only live-canary evidence.
- Human approval of this evidence kernel does not approve any strategy, trade, paper/live promotion, broker action, or autonomous agent authority.
