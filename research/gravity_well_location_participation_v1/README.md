# Gravity-Well Location + Participation Research V1

## Objective

Falsify whether a causal sequence of higher-timeframe location, movement away from a volume-weighted fair-value centre, centre acceleration, and NIFTY constituent participation contains incremental forecasting information for buy-only NIFTY options.

This is a semantic mechanism study. It is not an exact copy of the public Pine implementation and it does not treat an indicator description as evidence of profitability.

## Final verdict

```text
DATA_BLOCKED_INSUFFICIENT_SESSIONS_AND_MISSING_UNDERLYING_VOLUME_AND_MISSING_CONSTITUENTS
```

The Drive data inspected contains real NIFTY index and option ticks, including bid/ask quotes. It does **not** contain the two inputs required to test the primary mechanism honestly:

1. positive causal volume for the cash NIFTY index; and
2. NIFTY constituent rows from which participation breadth can be built.

Only one evaluated session was complete, versus the frozen minimum of thirty independent sessions. No structural-edge claim was made and no holdout was opened.

## Frozen primary families

### `GW_ESCAPE_ACCEPTANCE`

Two completed five-minute closes remain outside the ATR-normalized gravity band, the volume-weighted centre is moving and accelerating in the same direction, and at least forty constituents show aligned participation.

### `GW_FAILED_ESCAPE`

A completed bar escapes the gravity band, the next completed state returns inside it, centre movement stops supporting the escape, and constituent participation confirms the reversal direction.

### `GW_CLUSTER_BREAK_ACCEPTANCE`

A completed bar breaks a prior completed 15-minute location level, a second completed bar holds beyond the same level, the gravity centre confirms direction, and constituent participation expands.

The implementation returns zero primary events when volume or constituent participation is unavailable. It does not substitute tick count, option volume, option OI, or synthetic breadth.

## Causal controls

- five-minute completed event bars;
- prior completed 15-minute levels only;
- current HTF extremes cannot rewrite the level used at the same timestamp;
- trailing-only ATR and gravity-centre calculations;
- option entry strictly after the completed underlying signal;
- real ask for entry and real bid for exit;
- exact-ATM and nearest-strike proxy identities remain explicit;
- missing or zero bid/ask produces no option trade;
- no cross-session or fallback quote construction.

## Data inspected

The evaluated analysis extracts were derived from two immutable local Drive parquet files:

- July 1, 2026 partial session: raw SHA-256 `53341f21db27ab3f20e7a4ed8f183ab2b4aca03fae446779af04fe4987579243`;
- July 9, 2026 complete session: raw SHA-256 `62410f680b0621c836e3b18e8a509126e3dfbcf40c61e3cc23d5c2bc30b95139`.

Two additional Drive files were schema/symbol inspected:

- July 15 ten-minute partition: `NSE_INDEX` and `NSE_FO` only;
- July 16 file: NIFTY index and derivatives, no constituent rows.

The durable source details and hashes are in:

```text
schema_inspection_manifest.json
data_manifest.json
```

## Evaluated support

```text
analysis input rows:        1,910,118
NIFTY index rows:             128,876
NIFTY option rows:          1,781,242
NIFTY constituent rows:             0
positive index-volume rows:         0
independent sessions:               2
complete sessions:                  1
five-minute index bars:            92
primary event rows:                 0
```

The input row count above refers to bounded analysis extracts, not the complete raw parquet row total.

## Diagnostic controls

Price-only and location-only controls were allowed solely to verify the causal plumbing. They cannot certify the Gravity-Well mechanism.

Observed diagnostic events:

- price-only escape: 10;
- price-only failed escape: 4;
- location-only cluster break: 3.

Only one diagnostic event reconciled to an exact-ATM option trade using valid post-signal ask/bid quotes. Its net return after the primary friction was `-5.3005%`. One trade has no statistical meaning and was not used as evidence for or against structural edge.

## Relationship to existing Market Event Graph work

The existing Market Event Graph reversal is based on causal constituent breadth sequences and has a frozen, reproduced underlying discovery. This study was designed to test incremental information from gravity-centre state and higher-timeframe location—not to rename that breadth mechanism.

Because the available Drive corpus lacks constituent rows, a legitimate incremental comparison against the existing frozen Market Event Graph mechanism cannot be run from this corpus.

## Required next evidence

The next valid input is an immutable, multi-session NIFTY corpus containing:

- completed NIFTY five-minute bars;
- at least forty timestamp-aligned constituent bars;
- actual constituent volume or an explicitly governed participation measure;
- real expired-option bid/ask or audited option OHLC reconstruction;
- at least thirty independent complete sessions.

Until that exists, further threshold changes would be theatre, not research.

## Safety boundary

Research only. No strategy registration, TradeBuilder, ranking, dashboard, risk, approval, broker, order, execution, or live-launcher code is changed.
