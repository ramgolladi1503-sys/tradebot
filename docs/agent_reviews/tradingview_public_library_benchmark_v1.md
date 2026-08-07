# Agent Review Evidence — TradingView Public Library Benchmark V1

## Agent Work Contract

Research-only external-hypothesis benchmark. Enumerate every listing exposed by TradingView's 42-page public scripts index at campaign start, freeze the inventory before any benchmark outcomes are calculated, classify every listing for mechanical reproducibility and evidence compatibility, and benchmark only rules that can be reproduced causally from authorized data. No result may be promoted to a structural-edge claim from the already exhausted historical corpus.

## Scope Guard

In scope: public-page inventory, provenance, description-derived mechanical classification, data-compatibility classification, causal benchmark adapters, global multiplicity accounting for tested hypotheses, chronological development benchmarking, and explicit untestable reasons.

Out of scope: reverse engineering protected/invite-only source, bypassing TradingView access controls, broker calls, strategy registry changes, ranking/risk/execution changes, paper/live/order behavior, opening the shared sealed tail without separate authority, and claiming a certified structural edge from the exhausted same corpus.

## Grill Me Review

- Are all 42 pages attempted before benchmark outcomes? They must be.
- Is every unique listing represented by a manifest row? It must be.
- Are protected/invite-only scripts reverse engineered? They must not be.
- Are ambiguous visual indicators silently converted into trading rules? They must not be.
- Are data-incompatible scripts falsely simulated with proxies? They must not be.
- Are benchmark parameters changed after seeing outcomes? They must not be.
- Is the unopened tail accessed in the inventory/benchmark phase? It must not be.
- Does a positive same-corpus benchmark result count as structural-edge certification? It must not.

## Hermes Review

TradingView listing URLs, page numbers, titles, descriptions, detected visibility, required data primitives, classification status, and description hashes are persisted. The already governed NIFTY constituent/index evidence is used only as a non-certifying benchmark corpus unless materially independent history is separately authorized. Public TradingView source access controls are respected.

## GSD Review

The campaign extends existing research machinery rather than creating another production architecture. Inventory and classification live under `research/tradingview_public_library_benchmark_v1/`; execution is isolated to research scripts/workflows. Existing runtime, broker, strategies, ranking, and risk modules are untouched.

## QA / Safety Review

Tests and CI must prove 42-page attempt coverage, deterministic deduplication, inventory freeze-before-outcomes, explicit classification for every listing, no sealed-tail access, no production authority, and fail-closed handling for fetch failures, opaque logic, and missing data primitives.

## Acceptance Proof

Acceptance requires a physically executed GitHub Actions artifact containing the frozen inventory, evidence schema, classification counts, and later benchmark outputs. Counts must reconcile: tested + opaque + incompatible + fetch-failed + non-signal must equal unique inventory rows. Any benchmark survivor remains non-certifying until independent-history validation.

## Runtime Proof Required After Merge

This PR is research-only and marked DO NOT MERGE. No production runtime proof is applicable. If any code is ever proposed for production reuse, a separate PR must provide runtime proof under the relevant production safety gates.

## What This PR Does Not Prove

It does not prove that TradingView community scripts contain an edge. It does not prove that descriptions perfectly reproduce protected source code. It does not certify any strategy for options, shadow, paper, live, or order use. It does not invalidate scripts that require unavailable markets, timeframes, fundamentals, options data, or microstructure.

## Human Approval

The user explicitly requested exhaustive testing of the 42 TradingView script pages. That is approval to execute this research benchmark only. There is no human approval to merge, trade, open the sealed tail, or promote any result to live authority.
