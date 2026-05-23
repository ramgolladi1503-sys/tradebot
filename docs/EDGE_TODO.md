# Tradebot EDGE TODO

This file is the living TODO list for the EDGE 37-56 remediation roadmap.

Rule: when an EDGE PR is completed and merged, remove that item from this list in the next PR branch. The list should only show remaining work.

## Current bug-solution focus

The next EDGE work is a bug-reduction roadmap driven by the 2026-05-22 runtime evidence diagnosis, not a feature-expansion roadmap.

The observed runtime failure pattern was:

```text
feed unhealthy / websocket degraded
+ stale quote and old-session quote evidence
+ fallback and price-mismatch data entering advisory paths
+ no rankable candidates
+ misleading execution-feasibility wording
+ flattened terminal scores
+ repeated broker reconciliation noise
= NO_EXECUTABLE_OPPORTUNITY with noisy downstream artifacts
```

Do not start strategy tuning, ML scoring, capital allocation, dashboard polish, or live-order work before the market-truth and candidate-truth bugs below are fixed.

## Remaining EDGE PRs

### Phase 1 - Stop bad market data from becoming trade-like output

- [ ] EDGE-41 - Fallback Execution Firewall
  - Bug solved: fallback/stale/mismatch data can still appear as trade-like advisory output.
  - Required outcome: fallback, stale, subscription-failed, and price-mismatch inputs remain debug/advisory only and cannot become rankable or executable.
  - Evidence link: runtime diagnosis showed `rest_fallback`, `fallback_estimated`, `STALE_OPTION_LTP`, and `PRICE_MISMATCH` in candidate/advisory paths.

- [ ] EDGE-44 - Feed Recovery Runtime Wiring
  - Bug solved: websocket/feed degradation does not consistently stop downstream candidate flow early enough.
  - Required outcome: disconnected/reconnecting feed causes degraded feed state, symbol warmup, and no rankable candidates until fresh current-session ticks return.
  - Evidence link: runtime diagnosis showed `feed_ok=false`, `effective_ws_connected=false`, websocket close `1006`, and final `NO_EXECUTABLE_OPPORTUNITY`.

- [ ] EDGE-38 - Runtime Evidence Capture Guard
  - Bug solved: runtime diagnosis is still too manual and depends on pasted terminal output.
  - Required outcome: every `runtime/evidence/live_diag_*` pack can produce a deterministic diagnosis report covering feed, freshness, fallback, candidate funnel, score flattening, and final no-trade reasons.
  - Evidence link: the manual analyzer proved the diagnosis; this PR makes that repeatable.

- [ ] EDGE-42 - Quote Truth Single Source of Truth
  - Bug solved: quote source, option LTP source, quote validation, reported age, and timestamp age can disagree across modules.
  - Required outcome: one quote-truth contract owns quote source trust, freshness, validation status, and rank/execution eligibility.
  - Evidence link: runtime diagnosis showed `quote_source` as `unknown`, `rest_fallback`, `tick_store`, and `live`; `option_ltp_source` as `rest_fallback`, `subscription_failed`, and `tick_store`; and validation as `STALE_OPTION_LTP`, `PRICE_MISMATCH`, and `OK`.

- [ ] EDGE-43 - Feed Health Split-Brain Fix
  - Bug solved: global feed health, symbol health, and option feed block reasons can disagree.
  - Required outcome: global feed state, per-symbol feed state, option quote health, and candidate eligibility must report one consistent truth.
  - Evidence link: runtime diagnosis showed `feed_ok=false` and `effective_ws_connected=false` while some per-symbol option block reasons were `OK` and stale quote ages were huge.

### Phase 2 - Stop noisy candidates and misleading execution labels

- [ ] EDGE-45 - Symbol-Level Execution Safety Gate
  - Bug solved: one symbol can look healthy while another symbol is stale/degraded, and candidate paths do not always isolate that risk clearly.
  - Required outcome: each symbol must prove fresh current-session data before producing rankable candidates.

- [ ] EDGE-46 - Soft Reject Separation
  - Bug solved: `no_signal`, `no_candidates_survived`, advisory-only, blocked, debug-only, and rankable states are mixed in logs/UI.
  - Required outcome: hard reject, soft reject, advisory, debug-only, rankable, and executable states are separate and test-backed.

- [ ] EDGE-47 - Candidate Status Contract Cleanup
  - Bug solved: `execution_feasibility.status=executable` can be confused with `execution_allowed=true`.
  - Required outcome: price feasibility/entry derivation must be separated from execution permission.
  - Evidence link: runtime trace showed readiness `advisory_only`, execution feasibility `executable`, `execution_allowed=false`, and freshness `quote_exceeds_threshold` for the same trade path.

- [ ] EDGE-48 - Scoring Truth Hardening
  - Bug solved: internal score diversity is flattened into terminal confidence/opportunity values without enough explanation.
  - Required outcome: raw score, score-breakdown score, terminal score, flattening reason, fallback penalty, and no-signal penalty must be visible and deterministic.
  - Evidence link: runtime diagnosis showed `confidence_raw` flattened to `0.18` and terminal opportunity score flattened to `0.32` while score-breakdown confidence ranged roughly `0.41932` to `0.600494`.

- [ ] EDGE-49 - Opportunity Selector Evidence Upgrade
  - Bug solved: selector can report `no_rankable_candidates` without detailed blocker counts.
  - Required outcome: selector must explain no-trade using counts for feed unhealthy, stale quote, fallback, no-signal, price mismatch, token issues, and rankability blockers.

- [ ] EDGE-50 - Latest Artifact Freshness Guard
  - Bug solved: `*_latest.json` artifacts can be stale or from a different session and still influence diagnosis/debugging.
  - Required outcome: latest artifacts must expose generated time, session date, market date, age, producer, and stale/not-stale status.

### Phase 3 - Reporting only after truth contracts are stable

- [ ] EDGE-51 - Runtime Evidence Dashboard Contract
  - Bug solved: dashboard can read misleading raw fields instead of diagnosis/truth contracts.
  - Required outcome: dashboard reads the evidence diagnosis contract after EDGE-38/42/43/49/50 are stable.

### Phase 4 - Strategy validation after market truth is fixed

- [ ] EDGE-52 - Strategy Outcome Journal
  - Bug solved: no durable journal connects candidate decisions to later outcomes.
  - Required outcome: record candidate appeared, blocked/advisory/rankable state, later movement, would-have-worked, and would-have-failed evidence.

- [ ] EDGE-53 - Replay-Based Strategy Validation
  - Bug solved: strategy quality cannot be trusted from live UI rows alone.
  - Required outcome: replay validates historical candidate decisions without live orders, broker calls, or strategy tuning shortcuts.

- [ ] EDGE-54 - Strategy Family Kill/Keep Report
  - Bug solved: weak/noisy strategy families can survive because there is no evidence-backed kill/keep report.
  - Required outcome: each strategy family gets keep/kill evidence from replay and outcome journal data.

### Phase 5 - Trade quality and paper truth

- [ ] EDGE-55 - Executable Trade Quality Gate
  - Bug solved: high-quality executable trade criteria are not enforced as one final contract.
  - Required outcome: executable requires fresh feed, trusted quote, valid token, non-fallback RR, valid signal, acceptable spread, risk okay, and no stale blockers.

- [ ] EDGE-56 - Paper Trading Truth Acceptance Gate
  - Bug solved: live-readiness cannot be claimed without paper-truth evidence.
  - Required outcome: paper trades prove why selected, why sized, why entered, what happened, what would have failed, and whether strategy has evidence of edge.

## Non-negotiable sequencing

Do not start strategy tuning before market truth is fixed.

Immediate priority order:

1. EDGE-41 - Fallback Execution Firewall
2. EDGE-44 - Feed Recovery Runtime Wiring
3. EDGE-38 - Runtime Evidence Capture Guard
4. EDGE-42 - Quote Truth Single Source of Truth
5. EDGE-43 - Feed Health Split-Brain Fix
6. EDGE-45 - Symbol-Level Execution Safety Gate
7. EDGE-46 - Soft Reject Separation
8. EDGE-47 - Candidate Status Contract Cleanup
9. EDGE-48 - Scoring Truth Hardening
10. EDGE-49 - Opportunity Selector Evidence Upgrade
11. EDGE-50 - Latest Artifact Freshness Guard
12. EDGE-51 - Runtime Evidence Dashboard Contract
13. EDGE-52 - Strategy Outcome Journal
14. EDGE-53 - Replay-Based Strategy Validation
15. EDGE-54 - Strategy Family Kill/Keep Report
16. EDGE-55 - Executable Trade Quality Gate
17. EDGE-56 - Paper Trading Truth Acceptance Gate

## Scope guard

- Keep remediation PRs narrow and evidence-backed.
- Do not add unrelated dashboard polish before truth/reporting fixes.
- Do not rewrite strategies before evidence replay and quote/token truth guards.
- Do not weaken stale/fallback safety to make the UI look better.
- Do not increase stale thresholds to hide feed problems.
- Do not allow fallback, stale quote, or price mismatch data to become rankable/executable.
- Every PR must include tests and acceptance proof.
- Every PR must include agent-review evidence under `docs/agent_reviews/`.

## Todays operating rule

Follow the roadmap above one PR at a time. Start with EDGE-41. Do not skip to strategy, ranking, dashboard, or live-order work until the market-truth bugs are fixed.
