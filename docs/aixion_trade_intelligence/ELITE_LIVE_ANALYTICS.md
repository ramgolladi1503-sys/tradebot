# Aixion Elite Live Analytics

## Purpose

Aixion Elite Live Analytics is a read-only decision-quality and evidence-observation layer for TradeBot.

It answers four different questions without collapsing them into one confidence score:

1. **Observation authority** — is the evidence stream complete, fresh, causal and internally consistent enough to observe?
2. **Diagnosis authority** — are candidate outcomes and ranking evidence complete enough to diagnose strategy behaviour?
3. **Strategy-change authority** — is there sufficient evidence for a human to review a proposed strategy or ranking change?
4. **Profitability-claim authority** — has the full strategy-certification contract passed?

These authorities are intentionally separate. A healthy feed does not prove edge. A valid session does not prove profitability. A ranking anomaly does not authorize automatic parameter changes.

```text
NO LIVE ORDER AUTHORITY
NO AUTOMATIC STRATEGY MUTATION
NO AUTOMATIC RANKING MUTATION
NO RISK OVERRIDE
NO AUTOMATIC PROMOTION
```

## New elite analytics

### Ranking decision quality

For every scored candidate cycle:

- full score distribution;
- P10/P25/median/P75/P90;
- score range and interquartile range;
- top-one versus top-two separation;
- top-one versus median separation;
- tie rate;
- executable rate;
- fallback/recovered-fallback contamination;
- stale-quote rate;
- directional distribution;
- winner share and score-concentration HHI;
- score versus realized-outcome pairwise concordance;
- candidate retention across cycles;
- top-k overlap;
- Kendall tau-b rank stability.

The implementation uses the latest scored lifecycle state for each candidate in each cycle. It does not count the same candidate multiple times merely because the candidate passed through several pipeline stages.

### Empirical baseline

Ranking behaviour is compared with a provenance-hashed baseline generated from historical candidate-lineage files.

The baseline records:

- source paths;
- source SHA-256 hashes;
- source row counts;
- cycle counts;
- per-cycle metric values;
- a canonical baseline ID.

The baseline builder reads metric names from the live policy. It does not contain universal score, spread or confidence thresholds.

### Evidence continuity guardian

For each authoritative source or filtered component view:

- file SHA-256 and byte size;
- complete-row count;
- duplicate identities;
- malformed records;
- ignored unfinished final line;
- producer-sequence gaps;
- unique event coverage;
- required event-type coverage;
- latest source, receive and persist timestamps;
- source age;
- source-to-receive latency;
- receive-to-persist latency.

A single canonical event log can be split into component views using explicit field filters. This supports separate feed, runtime, risk, candidate and incident freshness checks without copying the evidence.

### Safe in-session snapshot

During an active session, `SESSION_ENDED` is expected to be absent. The live snapshot therefore permits exactly one incomplete lifecycle condition:

```text
SESSION_ENDED_COUNT=0
```

It still blocks monitoring for:

- missing or duplicate session start;
- multiple sessions;
- event-log verification failure;
- payload-contract failure;
- sequence gaps or duplicates;
- invalid, stale, partial or fallback quality evidence;
- any other lifecycle defect.

An active session can receive `LIVE_MONITORING_HEALTHY`, but it cannot receive a final valid-session verdict until the end event is written and post-close replay passes.

## Configuration inputs

### 1. Canary readiness configuration

Use the existing readiness checker. Storage size must come from a measured prior capture. Point-in-time files must be real, non-empty artifacts.

```bash
python scripts/check_aixion_trade_intelligence_canary.py \
  --config /absolute/path/aixion_canary.json \
  --output runtime/aixion_trade_intelligence/canary_readiness.json
```

Required premarket verdict:

```text
READY_FOR_READ_ONLY_CANARY
```

### 2. Ranking policy

Example shape only:

```json
{
  "freshness_limits_seconds": {
    "feed_truth": "DERIVE_FROM_FEED_SLO_OR_STABLE_CAPTURE",
    "candidate_lineage": "DERIVE_FROM_CYCLE_CADENCE",
    "runtime_health": "DERIVE_FROM_RUNTIME_HEARTBEAT_CADENCE"
  },
  "ranking_stability_top_k": "EXPLICIT_OPERATOR_SELECTION_SET_SIZE",
  "score_policy": {
    "minimum_reference_sessions": "EXPLICIT_RESEARCH_REQUIREMENT",
    "metrics": {
      "score_range": {
        "lower_quantile": "EXPLICIT_BASELINE_QUANTILE",
        "upper_quantile": "EXPLICIT_BASELINE_QUANTILE"
      },
      "top1_minus_top2": {
        "lower_quantile": "EXPLICIT_BASELINE_QUANTILE"
      },
      "fallback_contamination_rate": {
        "upper_quantile": "EXPLICIT_BASELINE_QUANTILE"
      },
      "stale_quote_rate": {
        "upper_quantile": "EXPLICIT_BASELINE_QUANTILE"
      },
      "executable_rate": {
        "lower_quantile": "EXPLICIT_BASELINE_QUANTILE"
      }
    }
  }
}
```

Do not replace the placeholders with generic market folklore. Use existing authoritative TradeBot SLOs where available. Otherwise derive the policy from frozen historical captures and document the derivation.

### 3. Source checkpoint configuration

Example canonical-event-log component views:

```json
{
  "sources": [
    {
      "source_name": "feed_truth",
      "path": "runtime/aixion_trade_intelligence/evidence/<SESSION_ID>/events.jsonl",
      "identity_fields": ["event_id"],
      "event_type_field": "event_type",
      "source_time_field": "source_time",
      "receive_time_field": "receive_time",
      "persist_time_field": "persist_time",
      "sequence_field": "producer_sequence",
      "required_event_types": ["FEED_TRUTH_UPDATED"],
      "filters": {
        "source_component": ["AUTHORITATIVE_FEED_COMPONENT"]
      }
    },
    {
      "source_name": "candidate_lineage",
      "path": "runtime/aixion_trade_intelligence/evidence/<SESSION_ID>/events.jsonl",
      "identity_fields": ["event_id"],
      "event_type_field": "event_type",
      "source_time_field": "source_time",
      "receive_time_field": "receive_time",
      "persist_time_field": "persist_time",
      "sequence_field": "producer_sequence",
      "required_event_types": ["CANDIDATE_CREATED", "CANDIDATE_RANKED"],
      "filters": {
        "source_component": ["core.candidate_lineage_ledger"]
      }
    }
  ]
}
```

Only use `producer_sequence` when it is monotonic within the filtered source view. Omit `sequence_field` when the source does not provide a valid source-local sequence.

## Premarket procedure

### Step 1 — Freeze the branch and inspect CI

Do not run the live sidecar from a moving branch. Record the exact commit SHA used for the session.

### Step 2 — Build the empirical ranking baseline

Use historical candidate-lineage JSONL files that are causally trustworthy and representative of the current ranking version.

```bash
python scripts/build_aixion_ranking_baseline.py \
  /path/to/historical_candidate_lineage_1.jsonl \
  /path/to/historical_candidate_lineage_2.jsonl \
  --policy /path/to/elite_policy.json \
  --output runtime/aixion_trade_intelligence/ranking_baseline.json
```

Persist the emitted `baseline_id` with the session metadata.

If the available history is below `minimum_reference_sessions`, the diagnosis gate remains blocked. Do not lower the minimum merely to obtain a green result.

### Step 3 — Start the read-only sidecar

```bash
EXECUTION_MODE=SHADOW \
python scripts/run_aixion_trade_intelligence_sidecar.py \
  --config /absolute/path/sidecar.json \
  --evidence-root runtime/aixion_trade_intelligence/evidence
```

### Step 4 — Start the continuous elite monitor

The monitor interval is an explicit operating parameter. Set it from the observation need and local-machine resource budget.

```bash
python scripts/run_aixion_elite_monitor.py \
  --event-log runtime/aixion_trade_intelligence/evidence/<SESSION_ID>/events.jsonl \
  --candidate-lineage runtime/candidate_lineage/candidate_funnel_<YYYYMMDD>.jsonl \
  --source-config /absolute/path/source_checkpoints.json \
  --canary-readiness runtime/aixion_trade_intelligence/canary_readiness.json \
  --policy /absolute/path/elite_policy.json \
  --baseline runtime/aixion_trade_intelligence/ranking_baseline.json \
  --certification /absolute/path/current_certification.json \
  --output-dir runtime/aixion_trade_intelligence/elite_live \
  --history-jsonl runtime/aixion_trade_intelligence/elite_live/history.jsonl \
  --interval-seconds <EXPLICIT_INTERVAL> \
  --iterations 0
```

The monitor atomically refreshes:

```text
elite_monitor_latest.json
elite_cockpit_latest.json
live_snapshot_latest.json
source_checkpoints_latest.json
```

It also appends an fsync-backed history journal when `--history-jsonl` is supplied.

The monitor safely ignores only an unfinished final JSONL line. A malformed complete line is an error and is not hidden.

### Step 5 — Open the read-only dashboard

```bash
streamlit run scripts/run_aixion_trade_intelligence_dashboard.py -- \
  --session-report runtime/aixion_trade_intelligence/elite_live/live_snapshot_latest.json \
  --elite-cockpit runtime/aixion_trade_intelligence/elite_live/elite_cockpit_latest.json
```

The dashboard exposes the four authority gates, score separation, ranking stability, empirical baseline results and evidence continuity.

## In-session interpretation

### Observation gate

A green observation gate means only that the configured evidence sources are present, fresh enough under the supplied policy, causally ordered and internally consistent.

### Diagnosis gate

During the live session this normally remains blocked because the session is incomplete and future outcome labels are not yet available. This is intentional.

### Strategy-change gate

No code, threshold, ranking or strategy mutation should be performed during the session from a transient anomaly. Review changes only after post-close outcome joining and multi-session evidence.

### Profitability gate

This must remain blocked until the full certification contract passes. Neither an attractive score distribution nor a successful live monitor is profitability evidence.

## Post-close procedure

### Step 1 — Stop the sidecar cleanly

Confirm that `SESSION_ENDED` was written.

### Step 2 — Run final event-log replay

```bash
python scripts/run_aixion_trade_intelligence_offline.py \
  --event-log runtime/aixion_trade_intelligence/evidence/<SESSION_ID>/events.jsonl \
  --output-dir runtime/aixion_trade_intelligence/reports/<SESSION_ID>
```

The final session must no longer be `INCOMPLETE_SESSION`.

### Step 3 — Rebuild final source checkpoints

```bash
python scripts/build_aixion_source_checkpoints.py \
  --config /absolute/path/source_checkpoints.json \
  --output runtime/aixion_trade_intelligence/reports/<SESSION_ID>/source_checkpoints.json
```

### Step 4 — Build the final elite cockpit

```bash
python scripts/build_aixion_elite_cockpit.py \
  --canary-readiness runtime/aixion_trade_intelligence/canary_readiness.json \
  --session-analysis runtime/aixion_trade_intelligence/reports/<SESSION_ID>/session_analysis.json \
  --candidate-lineage runtime/candidate_lineage/candidate_funnel_<YYYYMMDD>.jsonl \
  --source-checkpoints runtime/aixion_trade_intelligence/reports/<SESSION_ID>/source_checkpoints.json \
  --policy /absolute/path/elite_policy.json \
  --baseline runtime/aixion_trade_intelligence/ranking_baseline.json \
  --certification /absolute/path/current_certification.json \
  --output-dir runtime/aixion_trade_intelligence/reports/<SESSION_ID>/elite
```

### Step 5 — Join causal outcomes and counterfactuals

Diagnosis remains blocked until every relevant candidate has a causal, executable outcome label using observed quote sides, explicit costs and evidence references.

### Step 6 — Add the session to the campaign

Keep expiry and non-expiry sessions separate. Do not use one successful session as strategy evidence.

## Promotion boundary

The elite analytics layer may surface that ranking is compressed, contaminated, unstable or poorly correlated with outcomes. That evidence supports investigation. It does not authorize an automatic fix.

A strategy or ranking change remains a separate governed change with:

- a stated causal hypothesis;
- frozen feature and strategy versions;
- purged/embargoed validation;
- negative controls;
- cost and fill realism;
- holdout evidence;
- capacity evidence;
- risk-of-ruin evidence;
- live-shadow consistency;
- human approval.

## Final operational rule

```text
GREEN OBSERVABILITY != GREEN EDGE
GREEN DIAGNOSIS != AUTOMATIC STRATEGY CHANGE
GREEN STRATEGY CERTIFICATION != AUTOMATIC LIVE AUTHORITY
```
