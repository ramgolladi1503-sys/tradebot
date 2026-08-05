# PSILOR V1 Upstox Fetcher — Agent Review Evidence

## Evidence Contract

mode: RESEARCH_ONLY  
candidate_id: psilor-v1-upstox-fetch-v2  
decision: HARDEN_DATA_ACQUISITION_AND_ADMISSION  
is_order_action: false  
broker_api_called: false  
source: docs/agent_reviews/psilor_v1_upstox_fetcher.md

## Agent Work Contract

Implement and validate a read-only historical-data acquisition lane for PSILOR V1. The lane must fail closed on provider, schema, reconciliation, authority, and coverage defects. It may authorize only data extraction or proxy research; it cannot authorize live execution.

## Scope Guard

Allowed:

- Upstox historical index, VIX, expired-future, expired-option, and constituent acquisition
- immutable manifests, hashes, session ledgers, and admission verdicts
- bounded authenticated smoke testing
- PR #719 corpus inventory and reuse planning
- focused tests and CI

Forbidden:

- strategy, ranking, risk, execution, broker-order, or UI changes
- placing, modifying, or cancelling orders
- edge or profitability claims
- merging this PR
- committing tokens or raw environment files

## Grill Me Review

The strongest failure modes are stale smoke artifacts, metadata-only success, empty contracts counted as reconciled, CE/PE metrics omitted, disjoint session counts, current constituents used historically, and Git LFS pointers counted as market data. The implementation must explicitly reject each case.

## Hermes Review

The public contract is:

- source candles may contain zero volume or OI
- proxy entry eligibility requires positive volume
- every request chunk receives a terminal status
- every admitted file is tied to a run ID, request, contract, date interval, row count, and SHA-256
- DORL can pass without constituent authority; PSILOR cannot
- no provider or data blocker may be overwritten by a weaker verdict

## GSD Review

The branch is stacked on `research/psilor-v1-recertification` and limited to the fetcher, bounded smoke, focused tests, CI, reuse matrix, and this evidence file. Formal extraction remains a separate action after a clean smoke and completed checks.

## QA / Safety Review

Focused behavioral tests cover finite positive OHLC, non-negative volume/OI, duplicate semantics, India session dates, provider error taxonomy, CE/PE chunk accounting, empty-contract reconciliation, exact DORL overlap, PSILOR constituent authority, transparent user-agent identity, secret exclusion, and LFS pointer rejection.

## Acceptance Proof

Required before formal extraction:

- focused tests pass
- compilation passes
- Agent Review Evidence Gate passes
- bounded smoke uses a new empty run directory
- exactly five current-run Parquet files exist
- all five files contain the same two completed sessions
- all files parse and have positive row counts
- SHA256SUMS is written and read back successfully
- no unexpected Parquet files exist
- no secrets appear in committed evidence

Required before DORL or PSILOR validation:

- at least 30 exact DORL sessions
- PSILOR additionally requires point-in-time authority and at least 45 covered constituents per admitted session

## High-Risk Path Review

No production or live trading path is changed. Network calls are read-only historical endpoints. The most sensitive value is the bearer token; it is used only in memory and is excluded from URLs, logs, manifests, evidence, and tests.

## Runtime Proof Required After Merge

This PR must not be merged as part of this task. If a human later merges it, run a fresh bounded authenticated smoke from an empty run directory and retain only sanitized manifests, hashes, counts, and verdicts.

## What This PR Does Not Prove

- that PR #719 binaries are currently materialized or reusable
- that 30 overlapping DORL or PSILOR sessions exist
- that PSILOR has predictive or profitable edge
- that OHLC-only evidence is executable without bid/ask confirmation
- that production integration is safe
- that the provider will not change schema, entitlement, or rate limits

## Human Approval

Required for merge, formal extraction, and any later transition from data acquisition to strategy evaluation. Current status: not approved for merge.
