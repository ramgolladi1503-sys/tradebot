# Tradebot Reliable Trading Layer - Opportunity Engine V2 Product Bible

## 1. Purpose

Opportunity Engine V2 is the rebuild path for Tradebot's decision brain and reliability layer. It must convert raw market observations and strategy outputs into ranked, explainable, data-quality-safe trading opportunities while protecting the system from stale feeds, bad contracts, fallback quotes, weak execution decisions, poor sizing, and unreviewable behavior.

This is not a cosmetic dashboard rebuild. This is not a demo-piece refactor. This is the scope for making Tradebot a reliable real-time trading decision layer.

Before any trade is considered, the system must answer:

1. Is the market data real, fresh, and traceable?
2. Is the feed healthy enough to trust this decision?
3. Is the candidate structurally valid?
4. Is the contract real, tradable, and correctly resolved?
5. Why is this candidate ranked above others?
6. Is it safe to execute now?
7. What size is allowed?
8. What will stop this trade from becoming reckless?
9. Can the full decision be replayed after the session?
10. Can CI, replay, and live or paper validation prove the change did not weaken the system?

Tradebot remains a QA, SDET, and fintech reliability project. This document does not claim trading profitability. It defines the engineering standard required before Tradebot can be trusted as a serious trading layer.

## 2. North Star

Tradebot V2 must become a reliable trading decision layer, not a row-emitting dashboard.

Target flow:

```text
fresh market data
  -> validated contracts
  -> candidate discovery
  -> data-quality gate
  -> regime-aware scoring
  -> explainable ranking
  -> execution safety
  -> capital allocation
  -> broker and order lifecycle guard
  -> replay and audit
  -> cockpit dashboard
```

The system is successful only when it can clearly explain:

- what it saw;
- what it trusted;
- what it rejected;
- what it ranked;
- what it allowed;
- what it blocked;
- what it executed or would have executed;
- what happened after the decision.

## 3. Current Failure Pattern

The current system can produce rows, but rows are not opportunities.

The V1 failure pattern is:

- strategy output is emitted too directly into UI tables;
- weak and strong candidates look similar;
- fallback or recovered values can pollute decision logic;
- stale feed conditions can leak into display or execution paths;
- ranking is not clearly separated from execution eligibility;
- UI filtering hides weak data instead of improving decision quality;
- post-run review is hard because candidate, decision, order, and outcome snapshots are not first-class artifacts;
- CI can prove code compiles, but not yet prove trading-layer reliability;
- live-run validation is still too dependent on manual interpretation.

V2 must fix the product brain and reliability layer, not merely reorganize screens.

## 4. Product Positioning

Opportunity Engine V2 is a real-time options decision cockpit and safety layer for NIFTY, BANKNIFTY, SENSEX, and future stock-options workflows.

It should behave like:

- a candidate discovery system;
- a truth-first market-data validator;
- a feed freshness monitor;
- a contract-resolution guard;
- a scoring and ranking engine;
- an execution-safety gate;
- a capital-allocation guard;
- an order lifecycle monitor;
- a replayable decision audit system;
- a dashboard cockpit for human review;
- a CI-gated reliability project.

It should not behave like:

- a raw strategy-output table;
- a confidence-number generator;
- a fallback-data executor;
- a stale-feed amplifier;
- a dashboard-only project;
- a broker-click automation toy;
- a black-box signal bot.

## 5. Non-Negotiable Product Principles

### 5.1 Data truth before trade intelligence

No ranking, execution gate, or UI label is allowed to treat fake, stale, fallback, delayed, miss-ing, or untraceable market data as equivalent to a fresh broker quote.

Required data states:

```text
REALTIME
DELAYED
STALE
FALLBACK
MISSING
SUSPECT
DISCONNECTED
```

Execution rule:

- REALTIME may become executable.
- DELAYED, STALE, FALLBACK, SUSPECT, and DISCONNECTED may be advisory only or blocked.
- MISSING must be blocked.

### 5.2 Feed health is a first-class trading input

Feed health is not a dashboard metric. It is part of execution eligibility.

A candidate cannot become executable when:

- websocket is disconnected;
- last tick is older than the configured freshness threshold;
- subscription coverage is incomplete;
- option quote is stale;
- underlying quote is stale;
- quote was recovered from fallback;
- quote age cannot be measured.

### 5.3 Candidates before trades

Strategies must produce candidates. They must not directly produce final executable trades.

A candidate is an observed market setup. A trade is only possible after data-quality validation, contract validation, scoring, ranking, lifecycle handling, execution gating, and risk sizing.

### 5.4 Ranking is not execution

A high-ranked candidate can still be non-executable.

Examples:

- high score plus wide spread means attractive but not executable;
- medium score plus fresh quote plus tight spread can be executable at smaller size.

### 5.5 Explain every decision

Every score, block, downgrade, and execution decision must have reason codes.

Required reason buckets:

- positive reasons;
- negative reasons;
- blocker reasons;
- downgrade reasons;
- feed-health reasons;
- contract-resolution reasons;
- execution reasons;
- sizing reasons;
- replay or outcome reasons.

### 5.6 Human cockpit, not table viewer

The dashboard must expose decision state, not merely rows.

The top-level UI must distinguish:

- top opportunities;
- ready but not approved;
- watchlist or near executable;
- blocked candidates;
- stale-feed candidates;
- contract-resolution failures;
- data-quality health;
- regime state;
- risk state;
- order state;
- decision timeline.

### 5.7 No silent degradation

The system must not quietly continue as if healthy when a critical layer is degraded.

If feed quality drops, broker connection fails, contract resolution breaks, or risk limits are exceeded, the system must downgrade, block, alert, and record the reason.

## 6. Reference Architecture Extraction

Tradebot V2 must not be designed in isolation. Before and during implementation, we must extract proven patterns from mature open-source trading systems and adapt only the parts that fit Tradebot's Indian index-options reality.

The purpose is not to copy code. The purpose is to extract architecture, failure handling, testing boundaries, and operational discipline.

Reference systems to study:

```text
QuantConnect LEAN
Freqtrade
Hummingbot
vn.py / VeighNa
FinRL or FinRL-X style research-to-deployment pipelines
Backtrader-style strategy and replay harnesses
```

Patterns to extract:

- LEAN: separation between universe selection, alpha generation, portfolio construction, risk management, and execution.
- LEAN: risk management as a layer that can override targets before execution.
- Freqtrade: cooldowns, stoploss guards, low-profit-pair locks, max-drawdown guards, and protection tests.
- Hummingbot: strategy, connector, executor, order candidate, and order-event separation.
- Hummingbot: executor lifecycle, retry limits, balance validation, start and stop behavior, and event registration.
- vn.py: event-driven engine architecture, gateway separation, paper account boundary, data recorder, risk manager, and RPC routing.
- FinRL-style pipelines: separation between data processing, research, backtesting, broker execution, and portfolio risk overlays.

Patterns not to copy blindly:

- crypto exchange assumptions into NSE options;
- portfolio-target models that ignore option liquidity and expiry;
- ML-first signal generation before feed and execution truth are fixed;
- code structure that conflicts with current Tradebot CI or runtime constraints;
- live-execution behavior without paper-mode parity and replay.

Required benchmark artifact:

```text
docs/reference_architecture/TRADEBOT_V2_REFERENCE_EXTRACTION.md
```

That artifact must include:

- reference system reviewed;
- pattern extracted;
- why it matters for Tradebot;
- what to adopt;
- what to reject;
- target Tradebot module impacted;
- acceptance test that proves the pattern is implemented safely.

Acceptance rule:

No major V2 runtime module should be built without checking whether a mature reference system already solved the same class of problem.

## 7. Target Architecture

```text
broker websocket / broker REST / instruments / strategy scanners
        -> market_data_ingestion
        -> feed_health_monitor
        -> quote_freshness_gate
        -> contract_resolution_guard
        -> candidate_pool
        -> data_quality_gate
        -> regime_detector
        -> scoring_engine
        -> ranking_engine
        -> lifecycle_engine
        -> execution_gate
        -> capital_allocator
        -> order_intent_builder
        -> broker_execution_adapter
        -> order_lifecycle_monitor
        -> reconciliation_engine
        -> replay_store + audit_log + dashboard cockpit
```

The V2 engine must run side-by-side with existing V1 paths until it proves better through tests, replay, and live or paper validation.

No V1 path should be deleted until V2 can demonstrate equal or better behavior under replay and paper or live validation.

## 8. Required Modules

```text
core/opportunity/
    __init__.py
    candidate.py
    candidate_pool.py
    data_quality.py
    feed_health.py
    quote_freshness.py
    contract_guard.py
    regime.py
    scoring.py
    ranking.py
    reason_codes.py
    lifecycle.py
    execution_gate.py
    capital_allocator.py
    order_intent.py
    replay_store.py
    outcome_tracker.py
    selector.py

core/reliability/
    __init__.py
    heartbeat.py
    stale_feed_guard.py
    broker_connection_monitor.py
    subscription_audit.py
    kill_switch.py
    degradation_policy.py
    run_state.py

core/execution/
    order_lifecycle.py
    reconciliation.py
    paper_execution.py
    live_execution_guard.py

dashboard/ui/
    opportunity_table.py
    decision_timeline.py
    data_quality_panel.py
    feed_health_panel.py
    risk_panel.py
    regime_panel.py
    order_lifecycle_panel.py
    replay_panel.py

tests/opportunity/
    test_candidate.py
    test_data_quality.py
    test_quote_freshness.py
    test_feed_health.py
    test_contract_guard.py
    test_reason_codes.py
    test_scoring.py
    test_ranking.py
    test_lifecycle.py
    test_execution_gate.py
    test_capital_allocator.py
    test_replay_store.py

tests/reliability/
    test_stale_feed_guard.py
    test_broker_connection_monitor.py
    test_subscription_audit.py
    test_kill_switch.py
    test_degradation_policy.py

tests/execution/
    test_order_lifecycle.py
    test_reconciliation.py
    test_live_execution_guard.py
```

## 9. Feed Staleness and Market Data Freshness Contract

Staleness is one of the main product problems. It must be handled as a core safety contract, not a UI warning.

Required freshness fields:

```text
feed_source
feed_connected
websocket_connected
subscription_active
instrument_token
last_tick_at
last_quote_at
last_underlying_tick_at
last_option_tick_at
feed_age_ms
quote_age_ms
underlying_quote_age_ms
option_quote_age_ms
max_allowed_quote_age_ms
quote_freshness_status
rest_fallback_used
recovered_fallback_used
stale_transition_reason
feed_recovery_status
last_reconnect_at
reconnect_count
heartbeat_age_ms
```

Freshness states:

```text
FRESH
AGING
STALE
RECOVERING
DISCONNECTED
UNKNOWN
```

Required rules:

- If option quote age is greater than the configured threshold, candidate gets STALE_OPTION_LTP.
- If underlying quote age is greater than the configured threshold, candidate gets STALE_UNDERLYING_LTP.
- If websocket disconnects, affected candidates must become ADVISORY_ONLY or BLOCKED.
- If REST fallback is used, candidate must not become executable.
- If recovered fallback is used, candidate must not become executable.
- If quote recovers after stale state, candidate must be revalidated before becoming READY.
- If quote age cannot be measured, candidate must be treated as UNKNOWN and blocked from execution.
- Freshness thresholds must be configurable and test-covered, not hardcoded in dashboard code.

Required blockers:

```text
STALE_OPTION_LTP
STALE_UNDERLYING_LTP
QUOTE_AGE_UNKNOWN
FEED_DISCONNECTED
SUBSCRIPTION_MISSING
HEARTBEAT_TIMEOUT
REST_FALLBACK_USED
RECOVERED_FALLBACK_USED
QUOTE_RECOVERY_PENDING_REVALIDATION
```

Acceptance tests must prove:

- stale option quotes cannot become executable;
- stale underlying quotes cannot become executable;
- disconnected feed blocks execution;
- fallback quote blocks execution;
- recovered quote requires revalidation;
- unknown quote age blocks execution;
- freshness status is visible in candidate serialization;
- UI receives freshness fields without recomputing them incorrectly.

## 10. Candidate Contract

Every candidate must carry enough information to reconstruct why it existed and how it was judged.

Minimum fields:

```text
candidate_id
created_at
updated_at
symbol
underlying
option_type
strike
expiry
direction
source_strategy
setup_type
market_regime
data_quality_status
quote_freshness_status
feed_health_status
quote_source
underlying_ltp
option_ltp
bid
ask
spread
volume
open_interest
instrument_token
contract_symbol
contract_valid
contract_resolution_method
raw_features
score_components
final_score
rank
lifecycle_status
execution_status
position_size
positive_reasons
negative_reasons
blockers
downgrades
decision_snapshot_id
```

A missing field must be explicit. Silent defaults are not allowed for decision-critical fields.

## 11. Contract Resolution Guard

Contract resolution is a hard safety layer.

The system must prove that a candidate maps to a real, current, broker-tradable instrument before execution eligibility.

Required fields:

```text
instrument_token
tradingsymbol
exchange
segment
expiry
strike
lot_size
tick_size
contract_valid
resolution_method
resolution_confidence
resolution_reason
```

Allowed resolution methods:

```text
EXACT_MATCH
NEAREST_SAFE_FALLBACK
REJECTED_NO_MATCH
REJECTED_EXPIRED
REJECTED_WRONG_EXPIRY
REJECTED_STRIKE_TOO_FAR
```

Rules:

- exact match is preferred;
- nearest fallback must be bounded and reason-coded;
- unsafe fallback must be rejected;
- expired contracts must be rejected;
- contract resolution failures must be visible in UI and replay;
- no order intent may be created without a valid contract.

## 12. Lifecycle Model

Allowed candidate lifecycle states:

```text
DISCOVERED
VALIDATING
WATCHLIST
READY
APPROVED
ORDER_INTENT_CREATED
SUBMITTED
EXECUTED
REJECTED
EXPIRED
CANCELLED
```

Lifecycle rules:

- A candidate starts as DISCOVERED.
- A candidate becomes VALIDATING only after minimum structural fields exist.
- A candidate becomes WATCHLIST when setup is interesting but not executable.
- A candidate becomes READY when score, data quality, feed health, contract validity, and execution conditions are aligned.
- A candidate becomes APPROVED only after approval policy passes.
- A candidate becomes ORDER_INTENT_CREATED only after risk sizing and execution checks pass.
- A candidate becomes SUBMITTED only after broker adapter accepts the order request.
- A candidate becomes EXECUTED only after broker or execution confirmation.
- A candidate becomes REJECTED when hard blockers exist.
- A candidate becomes EXPIRED when its opportunity window is no longer valid.
- A candidate becomes CANCELLED when user or system cancels an active intent or order.

Invalid transitions must fail loudly and be tested.

## 13. Data-Quality Gate

The data-quality gate is a hard safety layer, not a scoring suggestion.

Hard blockers:

```text
MISSING_OPTION_LTP
MISSING_UNDERLYING_LTP
STALE_OPTION_LTP
STALE_UNDERLYING_LTP
QUOTE_AGE_UNKNOWN
FALLBACK_QUOTE
RECOVERED_FALLBACK_QUOTE
WIDE_SPREAD
INVALID_CONTRACT
ZERO_VOLUME_WHEN_VOLUME_REQUIRED
BROKER_FEED_DISCONNECTED
SUBSCRIPTION_MISSING
HEARTBEAT_TIMEOUT
```

Rules:

- fallback-based candidates must not become executable;
- stale LTP must not become executable;
- invalid contract resolution must block execution;
- spread must be measured from bid and ask where available;
- derived or recovered quote values must be labeled as such;
- UI must not recompute truth fields differently from the engine;
- missing critical fields must create explicit blockers, not defaults.

## 14. Scoring and Ranking

confidence_raw alone is not enough.

V2 scoring must be component-based:

```text
final_score =
    trend_score
  + momentum_score
  + volume_score
  + liquidity_score
  + regime_alignment_score
  + setup_quality_score
  + contract_quality_score
  + feed_quality_score
  - spread_penalty
  - stale_data_penalty
  - fallback_penalty
  - expiry_risk_penalty
  - volatility_noise_penalty
  - execution_risk_penalty
```

Score requirements:

- final score must be deterministic for the same input snapshot;
- each score component must have bounded ranges;
- score output must include reason codes;
- score alone must not grant execution permission;
- stale and fallback penalties must be strong enough that bad data cannot dominate rankings;
- hard blockers must override score.

Ranking requirements:

- sort candidates by final score after hard-block handling;
- separate executable, watchlist, advisory, stale, and blocked candidates;
- preserve blocked candidates for debugging;
- show rank movement over time where available;
- prevent fallback candidates from outranking real-quote executable candidates solely due to synthetic values;
- prevent stale candidates from appearing as ready opportunities;
- show primary reason and primary blocker.

## 15. Market Regime Model

Required regimes:

```text
TRENDING_UP
TRENDING_DOWN
RANGE_BOUND
HIGH_VOLATILITY
LOW_VOLATILITY
EXPIRY_NOISE
OPENING_SPIKE
CLOSING_DECAY
NEWS_SHOCK
UNKNOWN
```

Rules:

- unknown regime must reduce confidence, not inflate it;
- opening-spike setups must have shorter validity windows;
- expiry-noise regimes must increase risk penalties;
- range-bound regimes must penalize late breakout chasing;
- high-volatility regimes must tighten sizing and spread limits;
- regime must be captured in replay snapshots.

## 16. Execution Gate

Execution statuses:

```text
EXECUTABLE
READY_NOT_APPROVED
WATCHLIST_ONLY
ADVISORY_ONLY
STALE_ONLY
BLOCKED
```

A candidate cannot be EXECUTABLE unless:

- data quality is REALTIME;
- feed health is valid;
- option quote is fresh;
- underlying quote is fresh;
- contract is valid;
- spread is acceptable;
- risk limits allow it;
- lifecycle state is READY or stronger;
- blocker list is empty;
- sizing decision exists;
- order intent can be created safely.

## 17. Capital Allocation and Risk Guard

Required controls:

```text
risk_per_trade
max_daily_risk
max_open_positions
symbol_exposure_limit
strategy_exposure_limit
underlying_exposure_limit
confidence_to_size_mapping
volatility_size_adjustment
spread_size_adjustment
loss_streak_throttle
max_orders_per_minute
max_trades_per_session
cooldown_after_loss
cooldown_after_feed_recovery
```

Sizing output must include:

```text
allowed_lots
max_risk_amount
size_reason
size_blockers
risk_state
```

No candidate may be labeled executable without a valid size decision.

Risk must be able to block execution even when scoring is strong.

## 18. Order Intent and Execution Safety

The system must separate a candidate from an order intent.

Required order-intent fields:

```text
order_intent_id
candidate_id
created_at
tradingsymbol
exchange
transaction_type
order_type
product
quantity
price
trigger_price
validity
risk_snapshot_id
execution_gate_snapshot_id
approval_state
```

Rules:

- no order intent without valid candidate;
- no order intent without valid contract;
- no order intent without risk snapshot;
- no live order without explicit live-mode guard;
- paper mode and live mode must be impossible to confuse;
- duplicate order intents must be prevented through idempotency keys;
- order submission must be auditable.

## 19. Order Lifecycle and Reconciliation

Required order states:

```text
INTENT_CREATED
SUBMITTING
SUBMITTED
ACKNOWLEDGED
PARTIALLY_FILLED
FILLED
REJECTED
CANCEL_REQUESTED
CANCELLED
EXPIRED
UNKNOWN
```

Required reconciliation checks:

- local order state vs broker orderbook;
- local position state vs broker positions;
- expected quantity vs filled quantity;
- duplicate order detection;
- orphan order detection;
- rejected order reason capture;
- stale order state detection;
- paper or live mode mismatch detection.

Reconciliation failures must be visible in the dashboard and replay store.

## 20. Kill Switch and Degradation Policy

Kill-switch triggers:

```text
BROKER_DISCONNECTED
FEED_DISCONNECTED
QUOTE_STALENESS_BREACH
MAX_DAILY_LOSS_REACHED
MAX_ORDER_REJECTIONS_REACHED
RECONCILIATION_MISMATCH
UNKNOWN_POSITION_STATE
CONFIG_VALIDATION_FAILURE
```

Degradation levels:

```text
NORMAL
DEGRADED_DATA
ADVISORY_ONLY
PAPER_ONLY
HALTED
```

Rules:

- degraded data must downgrade execution;
- advisory-only mode must block live orders;
- halted mode must block all new order intents;
- recovery from degraded state requires revalidation;
- kill-switch events must be persisted and shown in UI.

## 21. Replay, Learning, and Run Health

Required snapshots:

```text
candidate_snapshot
data_quality_snapshot
feed_health_snapshot
quote_freshness_snapshot
contract_resolution_snapshot
score_snapshot
rank_snapshot
execution_gate_snapshot
risk_snapshot
order_intent_snapshot
order_lifecycle_snapshot
reconciliation_snapshot
entry_snapshot
exit_snapshot
outcome_snapshot
```

Replay must support:

- why a candidate was blocked;
- why a candidate was ranked highly;
- whether a rejected candidate later moved favorably;
- whether an executed candidate failed due to bad scoring, bad data, bad timing, bad execution, or bad risk sizing;
- whether stale feed caused false opportunity display;
- whether contract fallback caused unsafe output;
- whether execution state matched broker truth.

Required run-health metrics:

```text
feed_connected
websocket_uptime_seconds
last_tick_age_ms
option_quote_stale_count
underlying_quote_stale_count
fallback_quote_count
candidate_count
ready_count
executable_count
blocked_count
order_intent_count
submitted_order_count
rejected_order_count
reconciliation_mismatch_count
kill_switch_state
current_degradation_level
```

Required artifacts:

```text
runtime/analytics/events/
runtime/analytics/outcomes/
runtime/reports/session_summary.json
runtime/reports/feed_health.json
runtime/reports/decision_audit.json
runtime/reports/reconciliation_report.json
```

## 22. Dashboard Cockpit Requirements

Required panels:

1. Top Opportunities
2. Ready but Not Approved
3. Watchlist or Near Executable
4. Stale or Feed-Degraded Candidates
5. Blocked Candidates
6. Contract Resolution Failures
7. Data Quality Health
8. Feed Health
9. Regime Panel
10. Risk Panel
11. Order Lifecycle
12. Reconciliation
13. Decision Timeline
14. Replay or Outcome Review
15. Kill Switch or Degradation Status

Table rows must include:

```text
rank
symbol
contract
setup_type
final_score
execution_status
data_quality_status
quote_freshness_status
feed_health_status
spread
freshness_seconds
allowed_lots
primary_reason
primary_blocker
last_tick_at
last_updated
```

UI rules:

- UI must not hide stale candidates without preserving a debug view;
- UI must not recompute engine truth fields incorrectly;
- UI must show why a candidate is blocked;
- UI must show quote age and feed state near execution labels;
- UI must clearly distinguish advisory, paper, and live states.

## 23. Configuration and Safety Defaults

All thresholds must be centralized and testable.

Required config groups:

```text
feed_freshness_thresholds
spread_thresholds
risk_limits
execution_mode
broker_session_config
contract_resolution_limits
reconnect_policy
kill_switch_policy
replay_policy
```

Rules:

- unsafe missing config must fail closed;
- live mode must require explicit config;
- paper mode must be default for development;
- secrets must not be committed;
- runtime config must be visible in session summary without exposing secrets.

## 24. MVP Scope

The first V2 MVP must be serious but controlled.

MVP includes:

- candidate model;
- reason-code system;
- feed-health contract;
- quote-freshness contract;
- data-quality gate;
- contract-resolution guard contract;
- component scoring;
- ranking buckets;
- lifecycle states;
- execution gate;
- capital-allocation shell;
- order-intent contract;
- replay snapshot schema;
- run-health metrics contract;
- reference architecture extraction document;
- focused unit tests;
- UI cockpit contract documentation.

MVP excludes:

- broker auto-execution changes;
- new strategy families;
- major dashboard redesign;
- machine-learning optimization;
- profitability claims;
- live-money automation changes;
- deletion of V1 paths before V2 validation.

## 25. PR Plan

### PR 1 - Product Bible

Scope:

- add this Product Bible;
- no runtime code;
- no behavior changes.

Acceptance:

- documentation renders cleanly;
- CI remains green;
- Portfolio CI remains green.

### PR 2 - Reference Architecture Extraction

Scope:

- add docs/reference_architecture/TRADEBOT_V2_REFERENCE_EXTRACTION.md;
- compare LEAN, Freqtrade, Hummingbot, vn.py, and FinRL-style patterns;
- map extracted patterns to Tradebot modules and tests.

Acceptance:

- each adopted pattern has a Tradebot module target;
- each rejected pattern has a reason;
- extraction does not copy proprietary or incompatible behavior;
- CI remains green.

### PR 3 - Candidate and Reason-Code Contracts

Scope:

- add candidate dataclasses or typed contracts;
- add reason-code enums or constants;
- add serialization tests.

Acceptance:

- deterministic candidate serialization;
- no hidden defaults for decision-critical fields;
- stale, feed, contract, and risk reason codes exist;
- tests green.

### PR 4 - Feed Health and Quote Freshness Contracts

Scope:

- implement feed-health model;
- implement quote-freshness classification;
- add stale, fallback, and disconnected tests.

Acceptance:

- stale option quote cannot become executable;
- stale underlying quote cannot become executable;
- disconnected feed blocks execution;
- recovered fallback requires revalidation;
- tests green.

### PR 5 - Data-Quality Gate and Contract Guard

Scope:

- implement data-quality classification;
- enforce fallback, stale, and missing execution blocks;
- add contract guard model and tests.

Acceptance:

- fallback cannot become executable;
- stale quotes cannot become executable;
- missing LTP is blocked;
- invalid contracts are blocked;
- tests green.

### PR 6 - Scoring and Ranking

Scope:

- component score model;
- bounded score outputs;
- ranking buckets.

Acceptance:

- deterministic scores;
- blocked, advisory, and stale candidates are preserved but separated;
- ranking tests green.

### PR 7 - Lifecycle and Execution Gate

Scope:

- lifecycle transitions;
- execution eligibility rules;
- blocker propagation.

Acceptance:

- invalid transitions fail;
- execution requires realtime data, fresh quote, valid contract, sizing, and no blockers;
- tests green.

### PR 8 - Capital Allocation and Risk Guard

Scope:

- position-size decision contract;
- risk limit checks;
- lot sizing outputs;
- risk-block tests.

Acceptance:

- no executable candidate without sizing;
- risk-blocked candidates are not executable;
- loss, session, and exposure controls are represented.

### PR 9 - Order Intent and Paper Execution Guard

Scope:

- order-intent model;
- paper execution adapter boundary;
- live execution guard contract.

Acceptance:

- no order intent without candidate, contract, risk, and execution snapshots;
- paper and live mode cannot be confused;
- duplicate intents are blocked.

### PR 10 - Replay Store and Run Health Artifacts

Scope:

- snapshot schema;
- local replay artifact writer;
- run-health summary writer;
- outcome-ready schema.

Acceptance:

- every decision can be serialized;
- feed health and stale decisions are replayable;
- replay tests green.

### PR 11 - Dashboard Cockpit Integration

Scope:

- V2 panels behind feature flag;
- no removal of V1 UI until V2 is validated.

Acceptance:

- V1 dashboard still works;
- V2 cockpit displays ranked opportunities, stale candidates, watchlist, blocked candidates, contract failures, risk, feed health, and data-quality health.

### PR 12 - Reconciliation and Kill Switch

Scope:

- reconciliation state model;
- kill-switch policy;
- degradation mode handling.

Acceptance:

- broker and local mismatches create explicit health events;
- kill-switch blocks new order intents;
- recovery requires revalidation.

### PR 13 - Live and Paper Validation Harness

Scope:

- paper and live validation checklist;
- session report expectations;
- replay comparison between V1 and V2.

Acceptance:

- session summary proves candidate counts, blocked counts, stale counts, executable counts, and outcomes;
- live or paper validation can be reviewed without guessing from UI screenshots.

## 26. CI and Release Gates

Every PR must be small enough to review and safe enough to revert.

Documentation PRs:

- markdown renders;
- no runtime behavior changes;
- CI and Portfolio CI green.

Contract and model PRs:

- unit tests for serialization and invalid states;
- no dashboard dependency;
- no broker dependency.

Runtime logic PRs:

- unit tests;
- regression tests;
- no live broker dependency;
- paper and offline-safe tests;
- focused replay fixture where possible.

Dashboard PRs:

- V1 dashboard remains intact;
- V2 behind feature flag;
- UI uses engine-provided truth fields;
- stale and fallback states visible.

Execution-related PRs:

- paper mode default;
- live mode guarded;
- no live order path enabled by default;
- reconciliation and kill-switch implications documented.

## 27. Acceptance Gates

A V2 candidate can be considered production-safe only when:

- all candidate fields are explicit;
- feed health is known;
- quote age is known;
- fallback data never executes;
- stale quotes never execute;
- disconnected feed blocks execution;
- invalid contracts never produce order intents;
- ranking separates executable, watchlist, advisory, stale, and blocked candidates;
- execution status is explainable through reason codes;
- capital allocation produces a size or a block reason;
- order intent is separated from candidate;
- replay snapshots exist for decisions;
- reconciliation can detect state mismatches;
- kill switch can halt unsafe behavior;
- CI and Portfolio CI are green;
- paper or live validation confirms the decision stream behaves as expected.

## 28. Definition of Done

Opportunity Engine V2 is done only when Tradebot can show, for each trading session:

- feed health;
- quote freshness;
- what candidates were discovered;
- which contracts resolved correctly;
- which contracts failed and why;
- which candidates were rejected and why;
- which were watchlisted and why;
- which were stale and why;
- which became executable and why;
- what size was allowed;
- whether an order intent was created;
- what happened to the order lifecycle;
- whether broker and local state reconciled;
- what changed over time;
- what happened after the decision;
- whether the decision logic should be improved.

If the system cannot explain these, it is not a reliable trading layer. It is still a table viewer.

## 29. Hard Truth

A reliable Tradebot is not created by adding more strategy output, more dashboard columns, or more confidence numbers.

It is created by enforcing truth at every layer:

```text
fresh data
valid contract
explainable candidate
bounded score
safe execution gate
risk-aware sizing
auditable order state
replayable outcome
CI-gated change
```

Any feature that bypasses this chain is not an improvement. It is a liability.
