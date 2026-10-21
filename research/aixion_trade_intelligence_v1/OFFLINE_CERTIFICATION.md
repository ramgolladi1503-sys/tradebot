# Aixion Trade Intelligence V1 Offline Certification

## Verdict

```text
PIPELINE_OFFLINE_CERTIFIED
STRATEGY_EDGE_CERTIFIED=false
```

This is a pipeline certification, not a profitability or live-readiness certification.

## Deterministic fixture

The fixture proves:

- canonical event validation;
- append and load integrity;
- deterministic replay;
- exact producer reconciliation;
- candidate-to-fill lineage;
- causal underlying and option outcomes;
- complete declared outcome evidence;
- explicit refusal to certify strategy edge.

Result:

```text
45 focused tests passed
fixture events SHA-256:
35ff2f3e118af570d31901b762c1411c4e551a7fec9bbe77077b145f04a92250
fixture certification SHA-256:
6f926689a96476f5c71cbdd094b36a411cc001f5639bb93db305304ca5895c6e
fixture report SHA-256:
cad71e7f6a6b6c4e1200b16d355c01d0ee5d69b66c990d6cacb05191fae3da78
```

## Real captured corpus

Source evidence: six August 3, 2026 Upstox late-session Parquet chunks plus the point-in-time instrument master used for exact contract resolution.

Canonical result:

```text
18,014 events
18,009 quote events
12,987 exact NIFTY index rows
5,022 exact selected-option rows
0 look-ahead violations
1 candidate lineage
2 fully supported causal horizons
```

The research-only smoke direction was derived from the last distinct pre-decision NIFTY movement, and the selected option was the nearest strike at the decision timestamp. No profitable direction or strike was selected from future outcomes.

Both supported horizons were classified:

```text
UNDERLYING_WRONG
```

This is a required negative result: the pipeline reports the failed hypothesis rather than optimizing or relabeling it.

Hashes:

```text
real canonical events:
feda2a03f01eee87d4e296c543b7d3bfd888d2971479e24a4b2b4dec2f7578e2

real certification:
8e13446337afbb5def72efb48bcf8a8d6214a778e969c0775fd71a8dd901d01a

real report:
852d20acedbb5e6836d9c35a6cf21c5b2b10f4f7b51f875816932dc214e6b902

replay hash:
810be6487959e58a0bde8263288476f7dbc6fb30a07360b5e30872ebb5882575
```

## Certification gates passed

- `SESSION_MANIFEST_VALID`
- `DETERMINISTIC_REPLAY`
- `LINEAGE_CALCULATION_VALID`
- `OUTCOME_CALCULATION_VALID`
- `ANALYTICS_CALCULATION_VALID`
- `DECLARED_ANALYTICS_COMPLETE`
- `NO_LOOKAHEAD`
- `OUTCOME_LABEL_TIME_INTEGRITY`
- `CANDIDATE_OUTCOME_CONTRACT_COVERAGE`
- `OUTCOME_CONTRACT_COVERAGE`
- `OUTCOME_EVIDENCE_COMPLETE`

## Negative tests

Focused tests prove rejection or safe behavior for:

- future feature timestamps;
- malformed outcome contracts;
- missing outcome contracts;
- missing executable outcome evidence;
- conflicting duplicate events;
- missing expected instruments;
- producer sequence gaps;
- JSONL truncation/rotation/rewrite;
- partial source lines;
- source JSON errors;
- false option identity fallback;
- LTP-only quote preservation;
- duplicate finalization;
- non-empty output reuse.

## Residual live gap

No offline test proves the exact callback, filesystem, timing, and lifecycle behavior of tomorrow's live session. A read-only market-session canary remains mandatory before any production-readiness claim.
