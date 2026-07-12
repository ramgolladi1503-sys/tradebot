# Replay context contract

## Verdict

`REPLAY_CONTEXT_BLOCKED`

The current replay-only runner can reconstruct a normalized snapshot and `StrategyContext` from a one-row option tick slice, but it cannot naturally regenerate persisted candidates because the persisted runtime candidate artifacts were produced with richer runtime context than raw option ticks provide.

The missing bridge is not the handoff/journal writer. The missing bridge is the replay input bundle that captures the runtime state needed by the strategy generators and candidate-pool layer to emit a candidate naturally.

## Purpose

Define the minimum replay input bundle required to regenerate:

`replay input → normalized snapshot → StrategyContext → strategy → candidate → ranking → handoff → journal`

without manually constructing intermediate objects and without inventing missing context.

## Current artifact inventory

### Existing replay/runtime artifacts

- `.runtime/runtime_candidate_handoff_latest.json`
- `.runtime/candidates/candidate_journal.jsonl`
- `.runtime/opportunities/ranked_pipeline_latest.json`
- `.runtime/market_data/ticks_*.jsonl`
- `.runtime/market_data/ticks_*.parquet`
- `.runtime/snapshots/market_snapshot_latest.json`
- `.runtime/feed_runtime_latest.json`
- `.runtime/feed_health_truth_latest.json`
- `.runtime/advisory_latest.json`
- `.runtime/candidate_handoff_latest.json`

### Persisted candidate artifacts

Persisted candidate artifacts are the strongest evidence that a candidate existed naturally in the runtime path, but they are not enough by themselves to regenerate the same candidate from replay input.

- candidate journal rows preserve candidate identity and some trade fields
- runtime handoff payload preserves the top executable candidate snapshot and runtime counters
- ranked pipeline payload preserves ranking outcomes and blockers
- market snapshot artifacts preserve normalized market-state evidence

The replay contract must tie these together for the same replay event. A candidate artifact alone is an endpoint, not a replay input bundle.

### What these artifacts already prove

- `runtime_candidate_handoff_latest.json` proves the handoff writer can persist a top executable candidate snapshot and runtime counters.
- `candidate_journal.jsonl` proves candidate journal persistence exists, but current historical rows predate the strict replay metadata fields.
- `ranked_pipeline_latest.json` proves ranked-opportunity persistence exists, but the current payload may be empty for executable/advisory lists in the latest snapshot.
- `market_data/*.jsonl` and `market_data/*.parquet` prove replay market ticks exist, but they do not by themselves reproduce the richer runtime context required for candidate emission.

## Required input files / artifacts

To regenerate a candidate naturally, the replay input bundle should contain all of the following classes of evidence:

1. replay market event(s)
2. normalized market snapshot
3. context fields used to build `StrategyContext`
4. regime and feed-health truth
5. option-chain / quote-truth evidence
6. candidate-pool state
7. ranked candidate evidence
8. handoff evidence
9. journal persistence evidence

The bundle can be split across files, but each class must be present in raw recorded form.

## Stage-to-field contract

The table below maps each stage to the minimum fields it consumes. The exact field names may differ across artifacts, but the replay bundle must provide equivalent recorded values without invention.

| Stage | Consumes | Required fields |
|---|---|---|
| Replay event selection | replay row identity | `event_id`, source file, source row index, `timestamp` / `timestamp_epoch`, `symbol`, source hash |
| Normalization | market row → snapshot | OHLCV, bid/ask, OI, quote timestamp, provenance, session marker, source file hash |
| `StrategyContext` creation | runtime market context | `symbol`, `timestamp`, `spot`, option LTPs, spread/depth, VWAP, day high/low, fallback indicators, feed freshness |
| Regime / feed-health gating | runtime truth | regime label, regime score, feed health, freshness, market-open/session flags, suppression reason |
| Strategy execution | strategy-specific context | setup/regime/OOS labels, global cues, option-chain summary, volatility/trend cues, prior candidate state, no-trade signals |
| Candidate generation | pool state + strategy output | generator counts, suppression reasons, candidate identity, expected side, strike/expiry, execution intent |
| Ranking | ranked candidate set | score, blocker reasons, executable/advisory split, top executable snapshot |
| Handoff | ranked top candidate | top executable candidate identity, counts, mismatch reasons, runtime provenance |
| Journal persistence | candidate record | candidate identity, timing provenance, OOS fields, cost fields, strict replay blockers |

## Required fields per artifact

### 1. Replay market event

File class:

- `.runtime/market_data/ticks_*.jsonl`
- or equivalent replay event source

Required fields:

- `ts` or `ts_epoch`
- `symbol`
- `ltp`
- `bid`
- `ask`
- `vol`
- `oi`
- `depth` if available
- `last_trade_time` / quote timestamp if available
- source provenance fields

Consumed by:

- replay row selection
- VWAP reconstruction
- raw-to-snapshot normalization

Currently available:

- yes, at least in the real JSONL replay files

Missing:

- a replay bundle that includes the broader runtime context for the candidate-pool layer

Can be recorded in future runs:

- yes

### 2. Normalized market snapshot

File class:

- replay-snapshot artifact or a replay runner output

Required fields:

- `spot`
- `ltp`
- `ohlc`
- `vwap`
- `regime`
- `option_chain_summary`
- `feed_health`
- `quote_truth`
- `metadata` / provenance

Consumed by:

- `_strategy_context_from_market_symbol(...)`
- strategy generators

Currently available:

- partially, through runtime snapshot artifacts and live snapshot production helpers

Missing:

- a replay-ready snapshot artifact that preserves all fields needed by candidate generation without synthesizing missing values

Can be recorded in future runs:

- yes, via a replay snapshot recorder that writes the exact snapshot payload used by the runtime

### 3. `StrategyContext`

File class:

- replay runner internal object, derived from normalized snapshot

Required fields that materially affect candidate generation:

- `symbol`
- `ts_epoch`
- `spot_ltp`
- `open_price`
- `vwap`
- `day_high`
- `day_low`
- `regime_hint`
- `regime_scores`
- `option_ce_ltp`
- `option_pe_ltp`
- `ce_spread_pct`
- `pe_spread_pct`
- `ce_depth`
- `pe_depth`
- `quote_source`
- `fallback_used`
- `option_ltp_age_sec`
- evidence / metadata / lineage
- global cue fields where applicable
- strategy-specific cue fields where applicable

Consumed by:

- candidate generators
- option-pressure assessment
- regime classification
- no-trade assessment

Currently available:

- partially, from `_strategy_context_from_market_symbol(...)`

Missing:

- some strategy-critical inputs are not present in the current one-row replay slices, especially those that the live runtime derives from broader market state, feed-health, option-chain context, and candidate-pool history

Can be recorded in future runs:

- yes, if the replay runner records the exact normalized snapshot and the exact input fields used to build the context

### 4. Regime / feed-health truth

File class:

- `.runtime/feed_health_truth_latest.json`
- `.runtime/feed_runtime_latest.json`
- `.runtime/market_snapshot_latest.json`
- ranked-pipeline snapshot payload

Required fields:

- `feed_truth_state`
- `feed_truth_reason_code`
- `feed_ok`
- `market_open`
- `regime` / `regime_hint`
- regime scores / instability reasons
- freshness / quote-source blockers
- session boundary flags
- any runtime suppression flags emitted by the feed/runtime gate

Consumed by:

- ranking hold logic
- candidate suppression
- feed-risk suppression

Currently available:

- yes in live runtime artifacts

Missing:

- replay slices do not currently bundle the exact feed/regime truth that produced the persisted candidate

Can be recorded in future runs:

- yes

### 5. Option chain / quote truth

File class:

- market snapshot payload
- candidate journal row
- handoff snapshot

Required fields:

- `option_type`
- `strike`
- `expiry`
- `entry`
- `execution_entry`
- `stop_loss`
- `target`
- `bid`
- `ask`
- `ltp`
- `quote_age_sec`
- `quote_source`
- `execution_truth_state`
- `execution_truth_blockers`
- `execution_allowed`
- `reportable_executable`
- quote source / quote timestamp provenance
- bid/ask quantities when available
- quote-side evidence used by executable fills

Consumed by:

- candidate generation
- ranking
- handoff
- journal

Currently available:

- partially, in the persisted runtime handoff snapshot and some candidate journal rows

Missing:

- replay market rows do not yet carry the exact execution-truth and option-truth fields needed to recreate the persisted runtime candidate naturally

Can be recorded in future runs:

- yes

### 6. Candidate-pool state

File class:

- candidate-pool report
- ranked-opportunity report
- live runtime evidence

Required fields:

- `candidate_count`
- `movement_candidate_count`
- `no_trade_candidate_count`
- `validated_candidate_count`
- `blocked_candidate_count`
- `eligible_candidate_count_before_suppression`
- `report_executable_eligible_count`
- generator counts / failures
- candidate blockers / warnings
- option confirmations
- no-trade assessment
- prior selection / dedupe state if the runtime uses it
- suppression / ranking gate outcomes

Consumed by:

- ranking
- handoff evidence
- replay proof

Currently available:

- yes in the ranking pipeline reports

Missing:

- the replay runner does not yet have a bundle that preserves the same candidate-pool context for the same replay event

Can be recorded in future runs:

- yes

### 7. Ranked candidate evidence

File class:

- `.runtime/opportunities/ranked_pipeline_latest.json`
- replay runner audit artifact

Required fields:

- `top_reportable_executable`
- `top_reportable_executable_snapshot`
- `ranked_candidate_count`
- `executable_rank_count`
- `top_rank_strategy_id`
- `top_rank_score`
- blocker counts
- advisory/executable split
- rank rejection reason(s)

Consumed by:

- handoff writer
- candidate journal writer
- replay audit

Currently available:

- yes in the live runtime ranked-pipeline artifact

Missing:

- current replay slices do not reproduce a ranked candidate for the sampled real rows

Can be recorded in future runs:

- yes

### 8. Handoff evidence

File class:

- `.runtime/runtime_candidate_handoff_latest.json`

Required fields:

- `symbol`
- `generated_epoch`
- `trade_builder_raw_count`
- `post_scan_survivor_count`
- `post_soft_reject_count`
- `post_real_filter_count`
- `post_executable_filter_count`
- `ranked_total_count`
- `ranked_executable_count`
- `phase2_input_count`
- `top_opportunities_source_candidate_count`
- `top_opportunities_executable_count`
- `top_opportunities_phase2_state`
- `top_opportunities_selector_outcome`
- `top_reportable_executable`
- `top_reportable_executable_trade_id`
- `top_reportable_executable_snapshot`
- `handoff_mismatch`
- `mismatch_reason`
- source evidence hash or pointer to the replay bundle
- output isolation marker for replay-only runs

Consumed by:

- persistence evidence
- live truth alignment
- replay proof

Currently available:

- yes

Missing:

- a replay path that naturally produces this handoff evidence from replay input alone

Can be recorded in future runs:

- yes

### 9. Candidate journal evidence

File class:

- `.runtime/candidates/candidate_journal.jsonl`

Required strict replay fields:

- `feature_cutoff_ts`
- `signal_ts`
- `earliest_entry_ts`
- `is_oos`
- `oos_label`
- `strict_replay_export_ready`
- `strict_replay_export_blockers`
- `feature_cutoff_ts_source`
- `signal_ts_source`
- `earliest_entry_ts_source`
- `oos_source`

Consumed by:

- strict option replay export
- strict WFA readiness

Currently available:

- only on newly written journal rows after the journal writer hardening

Missing:

- older persisted journal rows still lack the strict replay metadata

Can be recorded in future runs:

- yes

## Which fields are currently available vs missing

### Currently available in some form

- replay market ticks
- market snapshot normalization
- `StrategyContext` construction
- regime / feed-health artifacts
- option chain / quote truth artifacts
- candidate-pool evidence
- ranked-pipeline evidence
- runtime handoff evidence
- candidate journal persistence
- some strategy-specific cue fields through the live runtime, depending on the strategy

### Missing for natural candidate regeneration from replay rows alone

- replay bundle carrying the same candidate-pool context as the live/runtime handoff
- replay-ready market slice with the specific upstream state that the strategy generators need to emit a candidate
- preserved strict replay metadata on older journal rows
- an explicit record of which strategy-specific cues were available at candidate emission time
- an explicit replay/event bundle identifier that links replay row, snapshot, context, ranking, and handoff together

## Missing fields and whether they can be recorded later

| Missing field/class | Can be recorded in future live/replay runs? | Minimal recorder change |
|---|---:|---|
| exact candidate-pool context for a replay event | yes | write a replay bundle artifact that captures the exact candidate-pool inputs and counts used by the runtime |
| exact regime/feed-health truth paired to the replay row | yes | persist the exact regime/feed-health snapshot alongside the replay event |
| exact option-chain truth used by the strategy generators | yes | record the normalized option-chain summary that fed `StrategyContext` |
| strict replay metadata on older journal rows | yes | continue writing `feature_cutoff_ts`, `signal_ts`, `earliest_entry_ts`, `is_oos`, `oos_label`, and blocker fields in the journal writer |
| replay row provenance tying event id to runtime candidate handoff | yes | add a replay bundle identifier and source hash to the replay runner output |
| strategy-specific cue bundle | yes | record the exact cue payload passed into the strategy at runtime |
| ranking rejection reasons and split counts | yes | persist the ranking decision payload alongside the replay bundle |

## Minimal recorder changes needed

The replay contract does not require new strategy logic. It requires recording the real runtime bundle that already exists across these layers:

1. replay source event id / row index / source file hash
2. normalized snapshot payload
3. `StrategyContext` input payload
4. regime and feed-health truth used for the run
5. option-chain summary and quote-truth evidence
6. candidate-pool counts and blockers
7. ranked report snapshot
8. runtime handoff payload
9. candidate journal payload
10. strategy-specific cue payload
11. replay bundle identifier and source hash

This can be done by a replay-only recorder that writes a single replay bundle artifact plus the existing runtime-style latest files inside an isolated directory.

## What must not be synthesized

The replay recorder must not invent the following:

- feature cutoff time
- signal time
- earliest eligible entry time
- OOS status
- regime label
- feed health
- option-chain truth
- candidate count / ranking counts
- trade identity
- journal timing or cost fields

If a value cannot be sourced from runtime evidence, it must remain null or blocked.

## How to avoid synthesizing missing context

Rules:

- never fabricate `StrategyContext` fields from unrelated data
- never convert a raw option tick into a candidate-pool state if the strategy generator did not naturally emit it
- never fill missing regime/feed-health with defaults that make the candidate look better
- never promote `NO_CANDIDATE` to success
- never derive OOS from current runtime unless the runtime partition context is explicit
- never overwrite production `latest` files during replay proof runs

If a field is missing, the replay bundle must record it as missing and fail closed.

## What the bounded scans showed

The isolated replay candidate handoff runner could:

- build a normalized snapshot
- build `StrategyContext`
- fail closed with `BLOCKED_NO_CANDIDATE`

But the sampled replay rows still did not produce a candidate naturally.

This means the current replay input bundle is still incomplete for natural candidate regeneration.

## Verdict

`REPLAY_CONTEXT_BLOCKED`

The replay-only runner is valid, but the minimum replay context bundle required to regenerate persisted candidates naturally is not yet fully captured by the current replay market-data artifacts.
