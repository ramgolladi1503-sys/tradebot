# Structural Pattern Suite Final Decision

## Scope

This document finalizes PR #699 as a rejection study for exactly three frozen strategies:

- `GAP_GO_LEADER_V1`
- `PRIOR_RANGE_LEADER_V1`
- `LATE_DAY_PERSISTENCE_V1`

No new strategies were discovered in this campaign. No thresholds were changed to rescue a losing result. No production strategy registration, broker wiring, order path, risk gate, feed gate, credential, dashboard, Telegram, or deployment path was modified.

## Frozen Rules

The frozen rules are the PR #699 contracts:

- `GAP_GO_LEADER_V1`: opening gap direction, minimum normalized gap `0.33`, same-direction opening return at least `5` bps, and directed leader spread at least `20` bps.
- `PRIOR_RANGE_LEADER_V1`: opening decision close outside the previous session range, with directed leader spread at least `20` bps.
- `LATE_DAY_PERSISTENCE_V1`: 14:00 displacement at least `0.50` of previous range, with close location at least `0.80` for long or at most `0.20` for short.

The primary horizon is the current TradeBot objective: 30 minutes from legal next-open entry.

## Source Authority

Kite recent corpus:

- Path: `/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip`
- SHA-256: `f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d`
- Accepted underlying files: `1473`
- Accepted sessions: `491`
- Rejected archive entries: `3615`

Aeron7 older corpus:

- Cache: `/Users/madhuram/tradebot-ml-evidence/source-cache/aeron7-nifty-banknifty-intraday-data`
- Pinned commit: `906fc2378b82e50de78f62844a3ecb3f9306a85d`
- Status: inventoried only, not used to rescue these frozen strategies.
- Reason: conflict-safe one-minute duplicate reconciliation was not authoritative in this PR.

## Legal Entry Contract

For the corrected Kite bar-start interpretation:

- Opening decision information uses the completed `09:40-09:45` bar.
- Canonical next-open entry is the bar whose `interval_start == 09:45`.
- Conservative one-full-bar delay is reported separately as `interval_start > 09:45`.
- Late-day decision information uses the completed `13:55-14:00` bar.
- Canonical next-open entry is the bar whose `interval_start == 14:00`.

## Candidate Counts and Occurrence

Accepted Kite sessions: `491`.

| Strategy | Candidate rows | Candidate sessions | Session occurrence |
|---|---:|---:|---:|
| `GAP_GO_LEADER_V1` | 39 | 39 | 0.07943 |
| `PRIOR_RANGE_LEADER_V1` | 113 | 111 | 0.22607 |
| `LATE_DAY_PERSISTENCE_V1` | 296 | 208 | 0.42363 |

## Canonical Results

Session-equal net mean after a 5 bps underlying sensitivity deduction:

| Strategy | 15m | 30m | 60m | Close |
|---|---:|---:|---:|---:|
| `GAP_GO_LEADER_V1` | -0.359 bps | -0.783 bps | +0.200 bps | +3.987 bps |
| `PRIOR_RANGE_LEADER_V1` | -3.917 bps | -4.254 bps | -0.209 bps | +4.763 bps |
| `LATE_DAY_PERSISTENCE_V1` | -2.953 bps | -2.312 bps | -3.774 bps | -3.443 bps |

## Current-Objective Verdict

| Strategy | Final decision |
|---|---|
| `GAP_GO_LEADER_V1` | `REJECT_FROZEN_STRATEGY_FOR_30M_OBJECTIVE` |
| `PRIOR_RANGE_LEADER_V1` | `REJECT_FROZEN_STRATEGY_FOR_30M_OBJECTIVE`; `ARCHIVE_DESCRIPTIVE_CLOSE_HORIZON_BEHAVIOR` |
| `LATE_DAY_PERSISTENCE_V1` | `REJECT_FROZEN_STRATEGY_FOR_30M_OBJECTIVE` |

Suite verdict:

`NO_EDGE_FOR_CURRENT_30M_OBJECTIVE`

This is not a claim that the market patterns never existed. It means that after causal confirmation, at legal next-open entry, at the frozen 30-minute horizon, and after a 5 bps underlying sensitivity deduction, these exact strategy definitions do not retain sufficient edge for the current TradeBot objective.

## Why Close-Horizon Behavior Is Not a 30-Minute Strategy

`PRIOR_RANGE_LEADER_V1` has positive descriptive behavior at the session-close horizon, but the frozen primary objective is 30 minutes. Substituting close-horizon behavior would be a risk-policy and holding-period change, not confirmation of the frozen 30-minute strategy.

## Why Aeron7 Is Not Required for Rejection

A positive certification requires complete proof: source parsing, exact candidate reconstruction, real matched controls, negative controls, independent oracle reconciliation, option executability, and prospective shadow evidence.

A negative primary economic result is sufficient to reject a frozen strategy for the current objective. Older Aeron7 recurrence could explain historical behavior, but it cannot convert a currently negative or tail-dependent 30-minute result into production readiness without changing the evidence question.

## Lessons for Future Discovery

- Start from structural states and distribution shifts, not named strategy templates.
- Freeze decision timestamps, feature library, split policy, hypothesis budget, and primary horizon before viewing validation or holdout outcomes.
- Use all accepted sessions as the denominator, not only candidate sessions.
- Treat close-horizon behavior as a separate hypothesis when the production objective is 30 minutes.
- Do not use option replay or production integration until the underlying 30-minute state effect survives real controls and chronological validation.

## Final Safety Status

- `execution_eligibility=false`
- `research_only=true`
- `allowed_for_live_execution=false`
- `broker_api_called=false`
- `is_order_action=false`

Production integration is prohibited for these three frozen strategies.
