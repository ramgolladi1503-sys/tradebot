# Tradebot EDGE Bug Solution Roadmap

This document turns the 2026-05-22 runtime diagnosis into a concrete bug-reduction roadmap.

It is not a feature roadmap. It is the operating plan for reducing recurring runtime bugs before strategy tuning, ML scoring, capital allocation, dashboard polish, or live-order work.

## Source diagnosis

The runtime evidence pack showed this failure chain:

```text
feed_ok=false
+ effective_ws_connected=false
+ websocket close 1006
+ quote_exceeds_threshold dominating freshness decisions
+ max quote age around 602k seconds
+ fallback / stale / mismatch quote sources entering candidate paths
+ no_signal and no_candidates_survived soft rejects
+ advisory_only candidates
+ terminal confidence flattened
+ execution-feasibility labels that look executable while execution_allowed=false
+ repeated broker_api_unavailable reconciliation noise
= NO_EXECUTABLE_OPPORTUNITY
```

The correct response is not to make stale thresholds looser or add strategy tuning. The correct response is to make market truth, quote truth, candidate truth, and execution truth impossible to confuse.

## Code surfaces inspected before locking this roadmap

The roadmap is grounded in existing code surfaces, including:

```text
core/candidate_quote_freshness.py
core/quote_age_truth.py
core/option_token_resolver.py
core/advisory_schema.py
docs/EDGE_TODO.md
```

The inspected code already contains important pieces:

- `classify_candidate_quote_freshness()` validates executable candidate freshness.
- `classify_quote_age_truth()` compares reported quote age with timestamp-derived age.
- `resolve_option_token()` already rejects expired requested contracts and marks sa-fe fallback token resolution as `execution_grade=false` and `advisory_only=true`.
- `advisory_schema.py` derives candidate status, readiness, execution status, and quote source, but runtime evidence showed these semantics still need cleanup across the pipeline.

## Roadmap principles

1. Fix market truth before strategy truth.
2. Bad feed must block early, not produce noisy downstream artifacts.
3. Fallback data may support diagnostics/advisory only, never rankable/executable decisions.
4. Price feasibility is not execution permission.
5. `NO_TRADE` must include evidence-backed reasons.
6. Every PR must be narrow, test-backed, and evidence-backed.
7. Every PR must preserve broker/order/live safety boundaries.

## Final implementation order

### EDGE-41 - Fallback Execution Firewall

Bug solved:

```text
Fallback, stale, subscription-failed, or price-mismatch data can still look trade-like in advisory/ranking paths.
```

Required outcome:

```text
rest_fallback
fallback_estimated
subscription_failed
STALE_OPTION_LTP
PRICE_MISMATCH
stale_quote
old_session_quote
```

must remain debug/advisory only and cannot become rankable or executable.

Likely code areas:

```text
core/advisory_schema.py
core/candidate_quote_freshness.py
core/quote_age_truth.py
core/option_token_resolver.py
core/opportunity_engine.py
core/evidence_replay_report.py
tests/observability/test_fallback_execution_block.py
```

Acceptance proof:

```text
fallback candidate is never rankable
fallback candidate is never executable
PRICE_MISMATCH candidate is blocked from execution
STALE_OPTION_LTP candidate is blocked from execution
fallback_estimated RR cannot produce execution-grade opportunity
selector report counts fallback-blocked candidates
```

### EDGE-44 - Feed Recovery Runtime Wiring

Bug solved:

```text
Websocket/feed degradation does not consistently stop downstream candidate flow early enough.
```

Required outcome:

```text
DISCONNECTED -> RECONNECTING -> WARMING_UP -> FRESH
```

or degraded/stale states must be explicit. No symbol should produce rankable candidates until it has fresh current-session ticks after reconnect.

Likely code areas:

```text
core/kite_depth_ws.py
core/market_data.py
core/candidate_quote_freshness.py
core/observability/feed_state.py
core/observability/runtime_cycle.py
```

Acceptance proof:

```text
websocket disconnected sets feed degraded
feed degraded blocks rankable candidates
reconnect without fresh ticks stays WARMING_UP
fresh current-session ticks restore symbol to FRESH
partial recovery enables only recovered symbols
```

### EDGE-38 - Runtime Evidence Capture Guard

Bug solved:

```text
Runtime diagnosis is still too manual and depends on terminal/pasted evidence.
```

Required outcome:

Every evidence pack can produce:

```text
runtime_diagnosis_report.json
```

covering:

```text
feed health
freshness blockers
max quote age
expired token/contract risk
candidate rejection funnel
fallback usage
score flattening
price-feasibility vs execution-permission mismatches
final NO_TRADE reason
broker reconciliation noise
```

Likely code areas:

```text
scripts/analyze_live_diag_evidence.py
scripts/build_observability_evidence.py
core/evidence_replay_report.py
core/observability/evidence_bundle.py
```

Acceptance proof:

```text
analyzer reads runtime/evidence/live_diag_* pack
report detects feed_ok=false
report detects stale quote max age
report detects fallback usage
report detects no rankable candidates
report detects execution-feasibility naming mismatch
report is deterministic
```

### EDGE-42 - Quote Truth Single Source of Truth

Bug solved:

```text
Quote source, option LTP source, validation status, reported age, timestamp-derived age, and trust can disagree across modules.
```

Required outcome:

One quote-truth contract decides:

```text
quote_source
option_ltp_source
quote_validation_status
reported_age_sec
timestamp_age_sec
effective_age_sec
quote_trust
rankable_allowed
execution_allowed
```

Likely code areas:

```text
core/quote_age_truth.py
core/candidate_quote_freshness.py
core/advisory_schema.py
core/quote_age_truth.py
```

Acceptance proof:

```text
reported quote age mismatch is detected
old timestamp cannot be hidden by low reported age
unknown quote source is untrusted
rest_fallback is not execution-grade
quote trust is included in candidate/debug output
```

### EDGE-43 - Feed Health Split-Brain Fix

Bug solved:

```text
Global feed health, per-symbol feed health, option feed block reason, and candidate eligibility can disagree.
```

Required outcome:

One consistent feed truth across:

```text
global feed state
symbol feed state
option quote health
underlying quote health
candidate eligibility
selector outcome
```

Likely code areas:

```text
core/observability/feed_state.py
core/candidate_quote_freshness.py
core/market_data.py
core/option_token_resolver.py
```

Acceptance proof:

```text
feed_ok=false cannot coexist with rankable=true
symbol stale state blocks that symbol only
option feed reason OK cannot override stale quote age
feed split-brain appears in diagnosis report
```

### EDGE-45 - Symbol-Level Execution Safety Gate

Bug solved:

```text
One symbol can be stale/degraded while another is fresh, and the pipeline does not isolate symbol-level safety clearly enough.
```

Required outcome:

Each symbol must carry execution safety state:

```text
symbol
feed_state
freshness_state
quote_trust
execution_safety_allowed
block_reason
```

Acceptance proof:

```text
stale BANKNIFTY blocks only BANKNIFTY
fresh NIFTY remains eligible if all other gates pass
mixed-symbol evidence produces symbol-level blockers
```

### EDGE-46 - Soft Reject Separation

Bug solved:

```text
no_signal, no_candidates_survived, advisory-only, blocked, debug-only, rankable, and executable states are mixed in logs/UI.
```

Required outcome:

Separate states:

```text
hard_reject
soft_reject
advisory_only
debug_only
rankable
executable
```

Acceptance proof:

```text
no_signal is soft reject, not feed failure
feed failure is feed_blocked, not no_signal
no_candidates_survived stays separate from stale feed
soft rejected candidates cannot enter top executable opportunities
```

### EDGE-47 - Candidate Status Contract Cleanup

Bug solved:

```text
execution_feasibility.status=executable can be confused with execution_allowed=true.
```

Required outcome:

Rename/clarify semantics:

```text
price_feasible
entry_derivable
execution_allowed
rankable
selected_for_execution
```

Acceptance proof:

```text
entry_derivable does not imply execution_allowed
advisory_only plus entry_derivable remains non-executable
UI/debug rows cannot label blocked candidate as executable
lifecycle evidence separates price feasibility from execution permission
```

### EDGE-48 - Scoring Truth Hardening

Bug solved:

```text
Internal score diversity is flattened into terminal confidence/opportunity values without enough explanation.
```

Required outcome:

Expose:

```text
raw_score
score_breakdown_confidence
penalty_adjusted_score
terminal_score
terminal_score_reason
flattened_by_reason
fallback_penalty_reason
no_signal_penalty_reason
```

Acceptance proof:

```text
terminal confidence cannot overwrite raw score without trace
flattening reason is mandatory
fallback_estimated RR applies explicit penalty
no_signal flattening includes explicit reason
UI receives both raw and terminal score fields
```

### EDGE-49 - Opportunity Selector Evidence Upgrade

Bug solved:

```text
Selector can report no_rankable_candidates without detailed blocker counts.
```

Required outcome:

`NO_TRADE` evidence must include counts for:

```text
feed_unhealthy
stale_quote
fallback
no_signal
price_mismatch
expired_contract
soft_reject
rankability_blocker
```

Acceptance proof:

```text
NO_EXECUTABLE_OPPORTUNITY includes blocker counts
no_rankable_candidates includes top reasons
selector evidence is deterministic
selector report does not imply strategy edge when candidates are feed-blocked
```

### EDGE-50 - Latest Artifact Freshness Guard

Bug solved:

```text
*_latest.json artifacts can be stale or from a different session and still influence diagnosis/debugging.
```

Required outcome:

Every latest artifact exposes and validates:

```text
generated_at
session_date
market_date
age_sec
producer
stale flag
```

Acceptance proof:

```text
old latest artifact is marked stale
missing generated_at is unsafe
cross-session latest artifact cannot be trusted as current evidence
```

### EDGE-51 - Runtime Evidence Dashboard Contract

Bug solved:

```text
Dashboard can read misleading raw fields instead of diagnosis/truth contracts.
```

Required outcome:

Dashboard reads diagnosis outputs only after truth contracts are stable.

Acceptance proof:

```text
dashboard shows feed unhealthy from diagnosis contract
dashboard shows no-trade reason from selector evidence
dashboard does not infer executable from price feasibility
```

### EDGE-52 - Strategy Outcome Journal

Bug solved:

```text
No durable journal connects candidate decisions to later outcomes.
```

Required outcome:

Journal records:

```text
candidate appeared
blocked/advisory/rankable/executable state
later price movement
would_have_worked
would_have_failed
saved_loss
missed_win
```

Acceptance proof:

```text
journal entry is append-only
journal does not call broker
journal supports replay lookup by candidate/trade id
```

### EDGE-53 - Replay-Based Strategy Validation

Bug solved:

```text
Strategy quality cannot be trusted from live UI rows alone.
```

Required outcome:

Replay strategy decisions against historical evidence without broker calls or live orders.

Acceptance proof:

```text
replay proves candidate path
replay produces deterministic outcome report
replay separates feed-blocked candidates from true strategy rejects
```

### EDGE-54 - Strategy Family Kill/Keep Report

Bug solved:

```text
Weak/noisy strategy families can survive because there is no evidence-backed kill/keep report.
```

Required outcome:

Each strategy family gets:

```text
keep
kill
needs_more_data
```

based on replay/outcome evidence.

Acceptance proof:

```text
kill/keep report is deterministic
report includes evidence counts
report cannot promote family without enough proof
```

### EDGE-55 - Executable Trade Quality Gate

Bug solved:

```text
High-quality executable trade criteria are not enforced as one final contract.
```

Required outcome:

Executable requires:

```text
fresh feed
trusted quote
valid token
non-fallback RR
valid signal
acceptable spread
risk ok
no stale blockers
explicit selector approval
```

Acceptance proof:

```text
only quality-gated candidate can be executable
fallback candidate fails quality gate
stale candidate fails quality gate
no_signal candidate fails quality gate
```

### EDGE-56 - Paper Trading Truth Acceptance Gate

Bug solved:

```text
Live-readiness cannot be claimed without paper-truth evidence.
```

Required outcome:

Paper truth proves:

```text
why selected
why sized
why entered
what happened
what would have failed
whether strategy has evidence of edge
```

Acceptance proof:

```text
paper acceptance report exists
paper report includes selected and rejected candidates
paper report proves no live broker calls
paper report blocks live-readiness if evidence is weak
```

## Work that is explicitly postponed

Do not start these until the EDGE market-truth roadmap reaches the correct phase:

```text
new strategy writing
strategy tuning
ML scoring
capital allocation
more dashboard polish
Pyroscope profiling
live broker/order work
auto remediation
```

## Daily execution rule

Work one EDGE PR at a time.

For each PR, first produce:

```text
files to change
design approach
risks
test plan
what not to touch
```

Then implement only that scope with tests, docs, and agent-review evidence.
