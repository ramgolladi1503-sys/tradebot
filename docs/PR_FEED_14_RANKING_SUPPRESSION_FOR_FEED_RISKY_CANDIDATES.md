# PR-FEED-14 — Ranking Suppression for Feed-Risky Candidates

## Purpose

PR-FEED-14 hardens the ranking layer so candidates carrying feed-risk evidence cannot remain executable or near-executable merely because their score is high.

This is a ranking-layer safety guard. It is not feed recovery, strategy tuning, dashboard work, or broker behavior.

## Problem

After PR-FEED-13, the candidate pipeline can be held when the whole canonical feed is unhealthy. That does not cover a mixed-feed case where the global feed is usable but an individual candidate carries unsafe quote/feed evidence such as:

- `NO_LIVE_OPTION_FEED`
- `SUBSCRIPTION_FAILED`
- `STALE_OPTION_LTP`
- `fallback_data`
- `rest_fallback`
- `recovered_fallback`
- `untrusted_quote_source`

Without PR-FEED-14, a high-scoring candidate with feed-risk evidence could still appear as executable or near-executable in ranking output.

## Scope

In scope:

- Add ranking-layer feed-risk suppression evidence.
- Suppress only `SCORE_ELIGIBLE` and `NEEDS_CONFIRMATION` records that carry feed-risk evidence.
- Keep advisory, already-suppressed, and no-trade records in their existing eligibility buckets.
- Preserve upstream `OpportunityScoreRecord` objects without mutation.
- Emit deterministic metadata: `feed_risk_suppression=enabled` and `feed_risk_suppressed_count`.
- Add negative tests for high-score feed-risk candidates.

Out of scope:

- No websocket reconnect changes.
- No subscription changes.
- No token-resolution changes.
- No strategy logic or threshold tuning.
- No dashboard UI changes.
- No broker calls.
- No order creation or execution behavior.

## Contract

If a ranked record is `SCORE_ELIGIBLE` or `NEEDS_CONFIRMATION` and contains feed-risk tokens in blockers, warnings, downgrade reasons, or safety flags:

- ranking output sets `score_eligibility=SUPPRESSED_BY_DOWNGRADE`.
- ranking output sets `bucket=SUPPRESSED_CANDIDATE`.
- ranking output sets `executable_candidate=false`.
- ranking output adds `ranking_feed_risk_suppression` to downgrade reasons.
- ranking output adds `ranking_feed_risk` to safety flags.
- ranking output includes `feed_risk_suppressed=true` in rank reason.

Source score records remain unchanged.

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_candidate_ranking.py
```

Required proof:

- High-score feed-risk executable candidate ranks below clean executable candidate.
- Feed-risk executable candidate no longer counts as executable.
- Feed-risk near-executable candidate is suppressed below advisory candidates.
- Ranking suppression does not mutate the source score record.
- Advisory feed-risk candidates remain advisory and are not double-suppressed.
- Ranking report remains read-only and JSON serializable.

## Runtime proof required after merge

In paper mode, inspect ranking evidence and confirm:

- feed-risk candidates are not top executable candidates.
- `feed_risk_suppressed_count` is present.
- no broker/order/live behavior is triggered by this read-only guard.

## Next PR

After PR-FEED-14 is merged and CI is green, continue only to PR-FEED-15 — Live/Paper Feed Policy Separation.
