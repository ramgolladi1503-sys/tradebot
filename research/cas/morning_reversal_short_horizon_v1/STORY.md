# CAS Morning-Reversal Short-Horizon Research Story

## Research question

The broader CAS work searched for causal pre-15:14 information that could predict short post-15:14 movement. No structural edge was certified.

## What failed

The late `15:11→15:13` continuation pattern looked strong in DEV (`72.2%`, `72.2%`, `80.6%` at 15:20/15:25/15:30) but failed frozen validation (`33.3%`, `33.3%`, `25.0%`). It is `FALSE_POSITIVE_IN_SAMPLE` and `REJECTED_AT_FROZEN_VALIDATION`.

The `09:15→10:00` reversal then showed DEV balanced accuracy of `63.9%`, `63.9%`, `55.6%` and validation balanced accuracy of `75.0%`, `75.0%`, `83.3%`. This created a frozen candidate, not an edge claim.

Its original four-session holdout was `66.7%`, `66.7%`, `41.7%`, combined `58.3%`, with session hit rates `22.2%`, `66.7%`, `44.4%`, `100%`. Verdict: `FAILED_ALL_HORIZON_STABILITY`.

Symbol diagnostics did not rescue it: NIFTY validation `100/100/100`, holdout `50/50/50`; BANKNIFTY validation `75/75/50`, holdout `100/100/25`; SENSEX validation `50/50/100`, holdout `50/50/50`. There was no symbol-specific promotion.

## Successor hypothesis

The failed 15:30 result suggested a materially different, short-lived reversal hypothesis: the signal may decay before 15:30. The successor is:

`CAS_MORNING_REVERSAL_SHORT_HORIZON_V1`

Feature: `09:15→10:00` underlying return. Signal: opposite direction. Primary exit: `15:20`; secondary exit: `15:25`; `15:30` is diagnostic decay only. The prior holdout is diagnostic-only and was not reused for confirmation.

## Authority and protocol

No clean untouched historical evaluation surface was proven; prospective testing is required. The operational amendment freezes exact-zero return as `NO_SIGNAL`, timezone `Asia/Kolkata`, best-ask option entry, best-bid option exit, and zero additional slippage with `SLIPPAGE_EVIDENCE=UNPROVEN`. Economic signal, outcome horizons, and selection logic were unchanged.

Entry uses the first authoritative observation at or after `15:14:00 IST`, with a `2000 ms` tolerance from the repository underlying-tick freshness authority (`core/runtime_feed_truth_snapshot.py:83-88`, `config/config.py:L370`). Exchange timestamp is preferred; governed receive timestamp is allowed only when explicitly available. Future-leak audit passed.

## Current state

The prospective collection is armed for exactly 20 newly admitted sessions. Current count is `0/20`; aggregate outcome analysis is locked and the old holdout is not reused. Option execution remains `UNKNOWN`; underlying predictive evidence must not be promoted to option profitability or structural certification.

Safety remains: `broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`; all broker/order counts are zero.

## Falsification and success

The successor is falsified by failure across 20 admitted sessions, indistinguishability from benchmarks or controls, concentration in too few sessions/symbols, cost failure for any option execution hypothesis, causal/persistence failure, or sensitivity to arbitrary rule changes. Even prospective support would not automatically establish option execution viability or structural certification.

Next action: collect exactly 20 newly admitted prospective sessions and do not inspect aggregate performance before session 20.
