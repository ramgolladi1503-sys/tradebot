# Opening Range Retest Outcome Audit

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Audit corrected ORB underlying outcome certification
- scope: Research-only audit evidence for PR #674 corrected outcome certification attempt.
- requested_paths: `docs/agent_reviews/opening_range_retest_outcome_audit.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: corrected generator smoke, independent audit smoke, focused tests, py_compile, evidence validation
- acceptance_proof: `AUDIT_INVALID`

## Scope Guard

This audit is read-only with respect to source market data and production code. It records why corrected certification cannot proceed.

## Repository Evidence Fields

- mode: RESEARCH_UNDERLYING_OUTCOME_AUDIT
- candidate_id: opening_range_retest_outcome_audit
- decision: AUDIT_INVALID
- reason: Corrected source verifier rejected a certified source record whose manifest symbol is NIFTY while the parquet source symbol is BANKNIFTY.
- timestamp: 2026-07-19T05:30:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/opening_range_retest_outcome_audit.md

## Grill Me Review

The previous `ORB_OUTCOMES_MEASURED` claim is invalid because it used challenged horizon semantics, shallow source checks, duplicate-only exposure reporting, and a non-independent audit. Corrected source verification now fails closed before any new certification can be issued.

## Hermes Review

Corrected contract direction:

- Source timestamps are one-minute bar starts.
- `proposal_ready_at` is a completed bar-end readiness timestamp.
- Legal entry is the first bar start strictly after `proposal_ready_at`.
- A 1-minute horizon uses the legal entry bar close.
- Horizon selection uses elapsed market time and exact expected timestamps, not positional `entry_index + horizon`.
- Source files must match manifest SHA-256, byte size, row count, schema, session, timestamp order, and symbol identity before measurement.

## GSD Review

Implemented repairs in this attempt add strict source verification, elapsed-time horizon selection, source-prefix hashing, richer terminal records, interval overlap fields, and a self-contained independent auditor. The corrected full-corpus smoke stops at source verification.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Corrected generator failed closed with:

`INVALID_SOURCE_HISTORY:symbol_mismatch`

Blocking source:

`runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet`

Observed contradiction:

- manifest symbol: `NIFTY`
- parquet source symbol after normalization: `BANKNIFTY`

## Runtime Proof Required After Merge

Do not merge this as measured outcome certification. A future certification attempt must repair or supersede the certified source manifest under an explicitly authorized scope, then rerun two fresh full-corpus executions and independent audits from a new frozen clean commit.

## What This PR Does Not Prove

This PR does not certify `ORB_OUTCOMES_MEASURED`, structural edge, profitability, exact option P&L, option fills, spread realization, slippage, latency, paper readiness, live readiness, execution readiness, capital allocation readiness, broker correctness, or production promotion.

## Human Approval

Human review is required. Codex must not merge this PR or enable auto-merge.
