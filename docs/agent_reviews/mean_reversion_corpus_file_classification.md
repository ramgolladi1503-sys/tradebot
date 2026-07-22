# Mean Reversion Corpus File Classification Review

mode: RESEARCH_BACKTEST_PRODUCTION_REPAIR
candidate_id: MEAN_REVERSION_CORPUS_FILE_CLASSIFICATION_V1
decision: DRAFT_REVIEW_REQUIRED
reason: The immutable corpus census proved that date-level underlying directories contain 1,547 OHLC candle files and 129 option quote/depth parquets; the generator previously attempted to load every parquet as a candle and truncated symbols containing underscores.
timestamp: 2026-07-22T14:00:00+05:30
is_order_action: false
broker_api_called: false
source: Frozen corpus schema report and post-merge regeneration failures

## Agent Work Contract

Repair only corpus file classification, deterministic candle normalization, and authoritative symbol resolution in the mean-reversion research path. Preserve strategy logic, thresholds, accounting, WFA, broker, feed, risk, dashboard, configuration, and order permissions.

## Scope Guard

In scope: classify canonical OHLC candles, explicitly skip the proven quote/depth schema, reject partial or unknown schemas, reject duplicate timestamps, preserve underscore-containing symbols, expose skipped-file telemetry, and add focused regressions.

Out of scope: changing market data, accepting arbitrary timestamp aliases, converting quote ticks into candles, changing strategy formulas, retuning parameters, or authorizing execution.

## Grill Me Review

1. Can a quote file silently become a candle? No; only the complete timestamp/OHLC schema is accepted.
2. Can a damaged candle silently be skipped? No; any partial OHLC schema raises an error.
3. Can an unknown parquet silently disappear? No; only the fully proven quote/depth schema is skippable.
4. Can duplicate timestamps alter bar ordering? No; duplicates fail closed.
5. Can BSE_INDEX|SENSEX be truncated to BSE? No; the authoritative symbol column is preferred and the fallback right-splits the date suffix.
6. Can skipped quote files inflate capacity denominators? No; candle symbol-day counting occurs only after candle classification.

## Hermes Review

The existing generator command and output schema remain compatible. Reconciliation receives additive non-candle counters. Existing canonical candle frames remain timestamp-sorted and retain start-labelled semantics. The helper is shared and independently testable.

## GSD Review

The repair is separated into one shared classification/normalization contract, one guarded generator integration, and focused positive/negative tests. No unrelated refactor is included.

## QA / Safety Review

Tests cover canonical candles, known quote files, partial OHLC corruption, unknown schemas, duplicate timestamps, deterministic sorting, and underscore-preserving symbol resolution. No broker or order path is imported or called.

## Acceptance Proof

Acceptance requires focused tests, neighboring ledger/audit tests, full repository tests, Code Excellence, CodeQL, Portfolio, Forensics, review evidence, and registry verification on one immutable head. A post-merge corpus regeneration must then verify exactly 1,547 candle files and 129 explicitly skipped quote/depth files before Phase 4 evidence is trusted.

## Runtime Proof Required After Merge

Rerun the immutable corpus workflow from its fixed SHA. Confirm archive and parquet hashes, file classification counts, Phase 4 two-run semantic determinism, full-grid output, shared WFA determinism, and read-only evidence publication.

## What This PR Does Not Prove

It does not prove structural edge, profitability, executable option economics, or correctness of unrelated engines. It does not reverse any historical strategy verdict without regeneration.

## Human Approval

Human review is required before merge. The PR must remain draft until all gates pass and the exact corpus-derived classification contract is accepted.
