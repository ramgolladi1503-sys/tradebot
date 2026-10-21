# C1 Intraday 15m Impulse — Frozen Observation Contract V1

## Authority and purpose

- Repository: `ramgolladi1503-sys/tradebot`
- Base authority: `main@42aba05bd6597bb97d62d49d80b755e906b958d7`
- Candidate ID: `ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE`
- Strategy ID: `C1_INTRADAY_15M_IMPULSE`
- Status: `HISTORICAL_SIGNAL_SUPPORTED / PROSPECTIVE_REQUIRED / EXECUTION_VIABILITY_UNKNOWN`
- Structural-edge status: `STRUCTURAL_EDGE_CERTIFIED=false`

This document exists so C1 cannot be lost, silently redefined, or confused with other candidates. It freezes the strategy definition that must be observed prospectively and the evidence required before any promotion.

The repository implementation in `core/candidate_evaluators.py` is the source-code authority. If this document and the implementation ever disagree, the discrepancy must be treated as a blocking defect and resolved explicitly; it must never be silently normalized.

## Frozen strategy contract

### Signal instrument

`NIFTY 50 spot/index` one-minute market memory is the signal source.

### Signal window

`09:30:00 <= evaluation_time <= 14:45:00 Asia/Kolkata`.

### Signal measurement

`rolling_15m_return_bps = (close[t] / close[t-15] - 1) * 10,000`

Qualification requires:

`rolling_15m_return_bps > +50.0`

The operator is strictly `>`; exactly `+50.0 bps` is not a qualifying event unless repository authority is intentionally changed in a separately reviewed task.

### Market-memory readiness

C1 must not qualify from incomplete or stale memory.

Required evaluator states include:

- at least the required 15-bar history plus the current bar under repository semantics;
- positive/fresh memory watermark;
- no retrospective reconstruction promoted as a prospective signal.

Repository reason codes include:

- `C1_OUT_OF_WINDOW`
- `C1_MEMORY_NOT_READY`
- `C1_STALE_MEMORY`
- `C1_IMPULSE_BELOW_THRESHOLD`
- `C1_QUALIFIED`

### Entry reference

On qualification, the frozen historical/prospective reference is:

`Open[t+1] on NIFTY Futures`

This is a research/observation reference, not authority to place an order.

### Stop

Fixed stop:

`40 bps below entry futures open`

Equivalent formula:

`stop_price = entry_price * (1 - 0.0040)`

### Exit

Earlier of:

1. fixed 40 bps stop; or
2. `15:10:00 IST` futures close under the frozen historical engine semantics.

No overnight holding is allowed for C1.

### Position occupancy

The historical strategy contract is `MAX_1_POSITION_NO_CONCURRENCY` / one active position at a time. Raw rolling threshold hits are not automatically distinct strategy trades while a position is already active.

## Observation-only live contract

The live purpose is to collect trustworthy prospective evidence, not to trade.

Mandatory safety state:

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
ORDERS_PLACED=0
ORDERS_MODIFIED=0
ORDERS_CANCELLED=0
```

A live observer must evaluate C1 continuously during the frozen window and persist every evaluation outcome with an immutable trace lineage.

Minimum per-evaluation record:

```text
session_id
trace_id
source_sha
candidate_id
strategy_id
evaluation_timestamp_ist
memory_as_of_timestamp
memory_freshness_watermark
rolling_1m_bars_count
rolling_15m_return_bps
threshold_bps
operator
window_state
decision
reason_code
qualified
signal_timestamp
entry_reference_timestamp
entry_reference_price
stop_reference_price
planned_exit_boundary
created_at_ist
record_sha256
```

Missing must remain missing. Never convert missing values to zero.

## Pipeline checkpoints

For every live session, C1 observation must carry the same trace/correlation lineage through:

```text
BROKER_AUTH
→ MARKET_FEED
→ WEBSOCKET
→ RAW_TICK/QUOTE
→ PERSISTENCE
→ BAR_MEMORY
→ 1M_AGGREGATION
→ 15M_ROLLING_FEATURE
→ C1_EVALUATOR
→ CANDIDATE_EMISSION / NO_SIGNAL
→ RISK / RANKING OBSERVABILITY
→ PROSPECTIVE_LEDGER
```

Each checkpoint must expose:

- intended state;
- actual state;
- `PASS | FAIL | UNKNOWN | DEGRADED`;
- reason code;
- input/output count;
- latest event timestamp;
- freshness;
- exception/root-cause field.

The observer must distinguish:

`NO_SIGNAL_BECAUSE_THRESHOLD_NOT_MET`

from:

`NO_SIGNAL_BECAUSE_PIPELINE_OR_DATA_FAILED`.

## Prospective admission law

A session/trade can be admitted as prospective C1 evidence only if the candidate decision was created and durably recorded before the outcome became known.

Historical replay, post-close reconstruction, repaired files created later, or broker historical-data downloads can never retroactively create prospective evidence.

Required pre-outcome proof for each qualifying observation:

- immutable candidate record existed at signal time;
- source SHA and strategy/spec identity are recorded;
- entry reference is captured causally;
- stop/exit rules were frozen before outcome;
- no parameter change or discretionary override occurred;
- observer/process liveness is evidenced for the relevant interval.

## Evidence status at PR creation

The current controlled interpretation is:

```text
IMPLEMENTATION_PRESENT=true
HISTORICAL_SIGNAL_EVIDENCE=SUPPORTED
HISTORICAL_REGIME_ROBUSTNESS=SUPPORTIVE
NEGATIVE_CONTROLS=SUPPORTIVE
MULTIPLE_TESTING_AT_DOCUMENTED_SEARCH_PRESSURE=SUPPORTIVE_BUT_SELECTION_PRESSURE_NOT_FULLY_ELIMINATED
FUTURES_GROSS_TRANSLATION=SUPPORTED
OUT_OF_SAMPLE_SUPPORTED=false
PROSPECTIVE_SUPPORTED=false
EXECUTION_VIABILITY=UNKNOWN
STRUCTURAL_EDGE_CERTIFIED=false
```

Do not use the label `PARTIAL structural certification`.

## Current execution-cost warning

The current NSE Securities Transaction Tax schedule must be used for any future net-cost analysis. NSE states that sale of securities futures is subject to STT of `0.05%` from `2026-04-01` (seller side), replacing the older `0.02%` rate.

Primary references:

- https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax
- https://nsearchives.nseindia.com/content/circulars/FATAX73524.pdf

Therefore any C1 analysis using the old 0.02% futures STT assumption is stale for 2026 execution economics.

Real spread, slippage, impact, latency and fill quality remain `UNKNOWN` until directly observed. A positive gross futures translation must not be called a tradable/net edge.

## What must be observed

For every qualifying C1 event prospectively capture at minimum:

- signal timestamp and rolling 15m return;
- exact NIFTY spot inputs used to form the signal;
- selected active NIFTY futures contract and contract identity;
- causal next-bar futures reference/open;
- contemporaneous best bid/ask if available;
- spread at arrival;
- depth/liquidity fields if available;
- stop level;
- first stop touch, if any;
- 15:10 reference close;
- theoretical gross outcome under frozen rules;
- observed arrival-to-fill slippage only if future paper/live execution is separately authorized;
- full pipeline checkpoint health.

The observation layer may record shadow/theoretical fills. It must label them as theoretical and must never call them broker fills.

## Observation milestones

No fixed number of days can certify the strategy by itself. Record evidence continuously and evaluate only under a frozen review policy.

Recommended governance milestones:

- session-level integrity review: every session;
- candidate-event integrity review: every qualifying event;
- statistical review checkpoints: pre-registered batches (for example 10/20/30 admitted events) without parameter tuning;
- execution review: only after authoritative spread/slippage/fill data exists;
- certification review: only when historical, selection-aware, prospective and execution evidence all satisfy their respective gates.

If a batch is weak, preserve the result. Do not retune C1 inside this observation campaign.

## Promotion gates

C1 may not be called structurally certified unless all required gates are independently supported:

```text
IMPLEMENTATION_VALID
HISTORICAL_EDGE_SUPPORTED
SELECTION_AWARE_VALIDATION_SUPPORTED
OUT_OF_SAMPLE_OR_PROSPECTIVE_SUPPORTED
EXECUTION_VIABLE
REGIME_AND_PARAMETER_ROBUSTNESS_SUPPORTED
INDEPENDENT_VERIFICATION_SUPPORTED
STRUCTURAL_EDGE_CERTIFIED
```

`STRUCTURAL_EDGE_CERTIFIED` is boolean. Until all required gates pass, it remains `false`.

## Failure / stop conditions

Observation must fail closed if any of the following occurs:

- source SHA/spec mismatch;
- stale or incomplete market memory;
- missing 15m history;
- futures contract identity ambiguity;
- candidate generated retrospectively;
- prospective ledger write failure;
- trace lineage break;
- missing timestamp provenance;
- authority state changes from read-only;
- any order placement/modification/cancellation;
- strategy parameter mutation.

A failed session is evidence of an operational problem, not a zero-return strategy observation.

## Explicit non-goals

This PR does not:

- certify C1;
- authorize paper or live trading;
- place orders;
- modify strategy thresholds;
- optimize stops or exit times;
- redefine C2;
- claim options profitability;
- claim realistic execution viability.

## Durable next action

Keep C1 enabled only as a governed read-only/prospective observer under this frozen contract. Accumulate admissible prospective evidence and real market-friction observations. Revisit promotion only after those records exist and survive independent review.
