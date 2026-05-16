# Stability to Execution Roadmap

## Purpose

This document explains why Tradebot is going through a structured stability, feed-truth, ranking, and execution-quality roadmap instead of immediately chasing more `EXECUTE` trades.

The short answer: a bot that is only "somewhat working" is not safe enough to optimize. If the feed is stale, contracts are wrong, quotes are untrusted, or ranking is opaque, then increasing executable trades only increases the speed of failure.

This roadmap turns the bot from:

```text
signals that sometimes appear useful
```

into:

```text
a measurable, explainable, evidence-driven trading system
```

## Why This Roadmap Exists

Tradebot has reached a point where isolated features work, tests are improving, and parts of the dashboard/runtime can produce useful output. That is progress, but it also exposed the real problem: the system was not failing because of one missing feature. It was failing because several layers were not yet trustworthy together.

The realization was this:

```text
A trading bot is not production-ready because it generates trades.
It is production-ready only when it can prove why a trade is valid, executable, ranked correctly, and safe to act on.
```

A somewhat working bot can still hide serious problems:

- market feed may be connected but option quotes may be stale
- candidate rows may exist but contracts may be unresolved
- confidence may look high while liquidity/spread quality is poor
- dashboard may show opportunities without explaining blockers
- backtest/replay behavior may not match live behavior
- executable count may be zero, but the reason may be unclear
- executable count may be non-zero, but the trades may be low quality

That is why the current roadmap focuses first on truth, then quality, then execution.

## Why We Are Building This Now

The project has already spent significant time trying to get the bot working. The mistake would be to keep adding features without fixing the foundation.

The current stage is the right time to formalize this roadmap because:

1. The codebase now has enough structure to be stabilized.
2. CI and local tests have exposed real compatibility and runtime-contract issues.
3. Depth subscription ownership and stale-prune behavior are now testable.
4. Full pytest stabilization exposed non-depth issues that also needed cleanup.
5. Market validation is still pending, so runtime decisions must remain evidence-driven.
6. The bot needs to move from "it runs" to "it proves what it is doing."

This is not a cosmetic documentation exercise. This is a control document for how the system should mature.

## North Star

Every PR after this point should support at least one of these goals:

```text
market feed stability
staleness control
quote truth
contract correctness
ranking quality
high-quality executable trades
risk-controlled live readiness
```

The goal is not to force more trades through the gate.

The goal is to make better trades naturally become executable because the underlying data, quote, contract, ranking, and risk evidence are strong.

## Current State

Recently completed cleanup chain:

```text
PR #39 — Depth subscription engine rewrite
PR #40 — Depth compatibility cleanup
PR #41 — Depth live validation checklist
PR #42 — Off-market depth validation plan
PR #43 — Depth ownership check script
PR #44 — Depth ownership cleanup fix
PR #45 — Local full pytest stabilization
PR #46 — Fix remaining local full pytest contracts
```

Current proven checkpoints:

```text
depth ownership check passes
depth subscription token tests pass
stale-prune hysteresis test passes
CI is green after PR #46
```

Important limitation:

```text
Live-market validation is still pending.
```

Until market-hours evidence is collected, the depth/feed work is not fully production-proven.

## Core Principle

Do not loosen gates to create executable trades.

Bad path:

```text
lower thresholds
ignore stale option LTP
allow unresolved contracts
rank wide-spread contracts highly
call more rows EXECUTE
```

Correct path:

```text
improve feed stability
prove quote freshness
validate contracts
penalize bad spread/liquidity
explain ranking
then allow only high-quality rows to become EXECUTE
```

## Scope 1: Current Cleanup Closeout

### PR #47 — Move Temporary Full-Pytest Shims Into Real Module Code

Purpose:

Move temporary stabilization behavior out of `core/full_pytest_contracts.py` and into real modules.

Target modules:

```text
core/market_data.py
core/review_queue.py
core/torture_test.py
```

Expected cleanup:

```text
remove or deactivate core/full_pytest_contracts.py
remove its installation from sitecustomize.py
keep tests green
```

Why this matters:

Temporary shims are useful to stabilize the suite quickly, but they should not become permanent architecture. Real behavior belongs in real modules.

### PR #48 — Feed/Staleness Observability Pack

Purpose:

Make feed and staleness state impossible to misunderstand.

Evidence to expose:

```text
feed_ok
ws_connected
subscribed_option_tokens_count
option_ltp_age
stale blockers
stale-prune events
candidate blocker reasons
executable blocker reasons
```

Why this matters:

If there are zero executable trades, the system must explain whether the cause is feed freshness, contract mapping, quote quality, ranking weakness, or strategy output.

### PR #49 — Live Market Validation Evidence

Purpose:

Validate depth/feed behavior during real market hours.

Minimum live run:

```text
15 to 30 minutes continuous runtime
```

Evidence to capture:

```text
.runtime/logs/feed_runtime_latest.json
.runtime/logs/runtime_health_latest.json
.runtime/logs/engine_cycle_status.json
.runtime/logs/suggestions_status.json
.runtime/logs/suggestions.jsonl
.runtime/logs/events.jsonl
```

Validation questions:

- Did websocket stay connected?
- Did option token subscription count remain healthy?
- Did stale option pruning preserve symbol floors?
- Did sticky/current trade tokens survive refresh?
- Did NIFTY/BANKNIFTY/SENSEX subscriptions remain stable?
- Were execution blockers truthful?

### PR #50 — Ranking Quality Diagnostics

Purpose:

Explain why each candidate ranks high or low.

Ranking evidence to expose:

```text
freshness_score
liquidity_score
spread_score
contract_score
confidence_components
risk_reward_score
final_rank_score
rank_explanation
```

Why this matters:

A high-confidence row is not automatically a high-quality trade. Ranking must consider freshness, spread, liquidity, contract validity, and execution realism.

### PR #51 — Executable Trade Quality Report

Purpose:

Show the full candidate-to-executable funnel.

Funnel:

```text
generated candidates
→ valid contracts
→ fresh quotes
→ liquid contracts
→ ranked opportunities
→ queue-only
→ executable
→ rejected
```

Required blocker distribution:

```text
UNRESOLVED_CONTRACT
STALE_OPTION_LTP
FEED_STALE
WIDE_SPREAD
PRICE_MISMATCH
LOW_CONFIDENCE
RISK_BLOCKED
ADVISORY_ONLY
QUEUE_ONLY
```

Why this matters:

Without a funnel, every failure becomes guesswork. With a funnel, the next bottleneck becomes obvious.

## Scope 2: Feed Resilience

### PR #52 — Feed Runtime Health Hardening

Purpose:

Strengthen runtime feed-health detection and reporting.

Examples:

- Detect option LTP staleness by symbol and age.
- Separate index feed health from option feed health.

### PR #53 — Broker Feed Reconnect and Recovery Evidence

Purpose:

Prove websocket reconnect does not lose critical subscriptions.

Examples:

- Reconnect should resubscribe underlying + option windows.
- Reconnect should preserve sticky/current trade tokens.

### PR #54 — Option LTP Freshness SLA Dashboard

Purpose:

Expose option quote freshness as a first-class runtime SLA.

Examples:

- Show stale option count by symbol.
- Show max/latest option LTP age.

## Scope 3: Quote Truth and Split-Brain Protection

### PR #55 — Bid/Ask/LTP Quote Consistency Gate

Purpose:

Block rows where LTP and bid/ask midpoint disagree too much.

Examples:

- LTP = 120, bid/ask midpoint = 82 → block as `PRICE_MISMATCH`.
- Bid/ask missing or stale → do not treat the row as fully executable.

### PR #56 — REST Fallback Quote Truth Audit

Purpose:

Ensure REST fallback quotes are clearly labeled, age-limited, and never confused with live websocket quotes.

Examples:

- `option_ltp_source=rest_fallback` must stay visible.
- stale REST fallback cannot silently become live truth.

### PR #57 — Spread/Liquidity Trust Score

Purpose:

Rank and gate based on actual tradability.

Examples:

- 18% spread should heavily penalize ranking.
- Low volume/open interest should block or downgrade execution readiness.

## Scope 4: Ranking Quality

### PR #58 — Ranking Score Decomposition

Purpose:

Break final rank into explainable components.

Required fields:

```text
momentum_score
confidence_score
freshness_score
liquidity_score
spread_score
contract_score
risk_reward_score
final_rank_score
```

### PR #59 — Liquidity-Aware Rank Penalty

Purpose:

Prevent illiquid contracts from ranking above tradable contracts.

Examples:

- Penalize low volume.
- Penalize weak depth/open interest.

### PR #60 — Freshness-Aware Rank Penalty

Purpose:

Prevent stale quotes from ranking highly.

Examples:

- Option LTP age > threshold lowers rank.
- Feed degraded state downgrades execution readiness.

### PR #61 — Contract-Quality-Aware Rank Penalty

Purpose:

Penalize weak or risky contract resolution.

Examples:

- Unresolved contract = hard block.
- Fallback-nearest contract = penalty unless explicitly safe.

## Scope 5: Executable Trade Funnel

### PR #62 — Executable Funnel Report

Purpose:

Create a structured report showing where candidates drop out.

### PR #63 — Blocker Distribution Dashboard

Purpose:

Display blocker counts by symbol, strategy, and time window.

### PR #64 — Executable Conversion Metrics

Purpose:

Track conversion rates from candidates to executable rows.

Examples:

```text
candidate_count=100
valid_contract_count=72
fresh_quote_count=48
liquid_contract_count=19
queue_only_count=6
executable_count=2
```

## Scope 6: Strategy Quality

### PR #65 — Strategy Performance Attribution

Purpose:

Show which strategies create useful candidates and which create noise.

### PR #66 — Strategy Regime Filter

Purpose:

Enable/disable strategies based on market regime.

Examples:

- Breakout strategy should not dominate dead sideways markets.
- Zero Hero should require volatility expansion.

### PR #67 — Strategy False-Positive Reduction

Purpose:

Reduce signals that repeatedly fail quality gates.

### PR #68 — Strategy-Specific Confidence Calibration

Purpose:

Calibrate confidence per strategy instead of using one generic confidence interpretation.

## Scope 7: Paper Execution and Fill Realism

### PR #69 — Paper Execution Lifecycle Evidence

Purpose:

Track paper entries, exits, stops, targets, and lifecycle events.

### PR #70 — Slippage Model

Purpose:

Estimate realistic fills based on spread and liquidity.

Examples:

- Signal entry = 120.
- Realistic fill = 123.5.
- P&L should use realistic fill, not fantasy entry.

### PR #71 — Entry/SL/Target Lifecycle Tracking

Purpose:

Track whether entries, stops, and targets are actually reachable in live quote terms.

### PR #72 — Missed-Fill and Bad-Fill Analysis

Purpose:

Differentiate theoretical trades from actually executable trades.

## Scope 8: Risk and Lifecycle Hardening

### PR #73 — Daily Loss Kill Switch

Purpose:

Stop new entries after daily loss exceeds a configured limit.

### PR #74 — Per-Symbol Exposure Cap

Purpose:

Limit concentration in one symbol.

### PR #75 — Consecutive-Loss Cooldown

Purpose:

Pause a symbol or strategy after repeated losses.

### PR #76 — Trade Lifecycle Reconciliation

Purpose:

Ensure internal state matches broker/paper execution state.

## Scope 9: Replay and Live Truth

### PR #77 — Replay/Live Parity Validator

Purpose:

Compare replay decisions against live runtime decisions.

### PR #78 — Truth Dataset Expansion

Purpose:

Build better historical datasets for validation.

### PR #79 — Historical Option Quote Replay

Purpose:

Replay actual option quote behavior, not just candle-level index movement.

### PR #80 — Replay-vs-Live Decision Diff

Purpose:

Explain why replay and live decisions differ.

## Scope 10: Control Tower

### PR #81 — Feed Health Panel

Purpose:

Show current feed health in the dashboard.

### PR #82 — Execution Blocker Panel

Purpose:

Show why rows are blocked.

### PR #83 — Ranking Explanation Panel

Purpose:

Show component-level ranking explanation.

### PR #84 — Live Run Evidence Export

Purpose:

Export live validation evidence as a reproducible artifact.

### PR #85 — Incident Timeline

Purpose:

Create timeline view of feed degradation, stale quotes, subscription changes, blockers, and recovery.

## Scope 11: Controlled Live Rollout

### PR #86 — Paper-Live Shadow Mode

Purpose:

Run live feed and paper execution side-by-side before real orders.

### PR #87 — One-Symbol Controlled Live Mode

Purpose:

Allow controlled live mode for one symbol only.

### PR #88 — One-Lot Capped Live Mode

Purpose:

Allow real orders only with strict one-lot cap.

### PR #89 — Live Postmortem Automation

Purpose:

Generate automatic postmortem reports after live sessions.

## Roadmap Rules

1. Do not weaken gates just to increase executable count.
2. Do not start strategy tuning until feed, quote, contract, and ranking truth are visible.
3. Do not treat off-market tests as proof of live-market behavior.
4. Do not clean multiple hook families in one PR.
5. Every PR must have a clear validation command or live evidence requirement.
6. Temporary compatibility/shim behavior must eventually move into real modules.
7. Ranking must become explainable before it becomes aggressively optimized.
8. Real-money execution must wait for paper/live shadow evidence.

## Definition of Done for This Roadmap

This roadmap is complete only when the bot can answer these questions with evidence:

```text
Is the feed connected and fresh?
Are option quotes fresh by symbol?
Are contracts resolved and tradable?
Is quote truth consistent across LTP/bid/ask/REST fallback?
Why did a candidate rank high?
Why did a candidate fail execution readiness?
How many candidates became executable and why?
What happened after paper/live execution?
Did replay and live behavior agree?
Was risk controlled across the session?
```

## Final Position

The bot should not aim to become aggressive first.

It should become truthful first.

Then stable.

Then explainable.

Then executable.

Then scalable.
