# Aixion Trade Intelligence — Read-Only Shadow Runbook

## Authority boundary

This runbook is for `PAPER` or `SHADOW` evidence collection only.

```text
NO LIVE ORDER AUTHORITY
NO STRATEGY MUTATION
NO RANKING MUTATION
NO RISK OVERRIDE
NO AUTOMATIC PROMOTION
```

## 1. Prepare point-in-time inputs

The canary configuration must reference non-empty, locally available versions of:

- instrument master;
- expiry calendar;
- constituent membership and weights;
- exchange-rule snapshot;
- transaction-cost schedule.

Storage requirements must be derived from a measured prior capture, not a generic constant.

## 2. Run readiness

```bash
python scripts/check_aixion_trade_intelligence_canary.py \
  --config /absolute/path/aixion_canary.json \
  --output runtime/aixion_trade_intelligence/canary_readiness.json
```

Required verdict:

```text
READY_FOR_READ_ONLY_CANARY
```

Any other verdict blocks the sidecar.

## 3. Sidecar configuration

```json
{
  "session_id": "20260805-NIFTY-SHADOW-001",
  "run_id": "run-001",
  "mode": "SHADOW",
  "poll_interval_seconds": 0.25,
  "sources": [
    {
      "path": "runtime/candidate_lineage/candidate_funnel_20260805.jsonl",
      "source_type": "candidate_lineage",
      "source_component": "core.candidate_lineage_ledger"
    },
    {
      "path": "runtime/feed_truth/feed_truth_20260805.jsonl",
      "source_type": "truth",
      "source_component": "core.feed_truth",
      "event_type": "FEED_TRUTH_UPDATED"
    }
  ]
}
```

Only configure sources that are authoritative and actually produced by the current TradeBot runtime.

## 4. Start the separate process

```bash
EXECUTION_MODE=SHADOW \
python scripts/run_aixion_trade_intelligence_sidecar.py \
  --config /absolute/path/sidecar.json \
  --evidence-root runtime/aixion_trade_intelligence/evidence
```

The sidecar tails append-only JSONL files. It does not import or call broker order methods.

## 5. Stop and finalize

Stop the process normally so it writes `SESSION_ENDED`.

Then run:

```bash
python scripts/run_aixion_trade_intelligence_offline.py \
  --event-log runtime/aixion_trade_intelligence/evidence/<SESSION_ID>/events.jsonl \
  --output-dir runtime/aixion_trade_intelligence/reports/<SESSION_ID>
```

Required evidence files:

```text
session_analysis.json
session_report.md
```

## 6. Certification interpretation

A valid session proves only that evidence capture and lineage were internally consistent.

It does not prove:

- strategy edge;
- profitable execution;
- calibrated queue probability;
- sufficient capacity;
- holdout profitability;
- stable drift;
- acceptable risk of ruin.

Those gates remain `INSUFFICIENT_EVIDENCE` until their required real observations exist.

## 7. Fail-closed conditions

Do not use the session for research certification when any of the following occurs:

- missing `SESSION_ENDED`;
- payload-hash failure;
- producer-sequence gap;
- stale or invalid authority events;
- missing point-in-time metadata;
- incomplete candidate outcome coverage;
- analytics evidence loss;
- sidecar configured in `LIVE` mode.
