# H1 Shadow Adapters V1

## Status

`H1_SHADOW_ADAPTERS_PR_READY_NO_ORDER` candidate implementation.

This work turns `H1_TRAPPED_PUSH_SNAPBACK` from a manually-operated research observer into a repeatable no-order shadow adapter path. It does **not** modify the frozen H1 predicate, thresholds, target, WFA evidence, or registry status.

## Strategy Boundary

Frozen candidate:

```text
candidate_id = H1_TRAPPED_PUSH_SNAPBACK
frozen_predicate = (range_bps[t-1] > 12.0) & (upper_wick_bps[t-1] > 4.0) & (body_bps[t] < -2.0)
support_scope = OPENING_WINDOW_5MIN_OHLC_INDEX_BPS
```

Allowed use:

```text
NO_ORDER_SHADOW_OBSERVATION_ONLY
```

Forbidden use:

```text
Do not trade.
Do not create paper orders.
Do not route broker writes.
Do not claim execution viability.
Do not claim structural edge certification.
Do not add constituent breadth or options filters into the trigger path without creating a new candidate and re-validating historically.
```

## Added Components

### `scripts/research/hypothesis_factory/h1_shadow_adapter.py`

Pure adapter utilities:

- convert raw Kite intraday CSV output to the V19 H1 completed-bar schema;
- merge already-normalised H1 completed-bar CSVs;
- enforce all no-order authority flags false;
- emit manifests that record `predicate_changed=false`, `orders_created=0`, and `broker_writes_created=0`.

### `scripts/research/hypothesis_factory/run_h1_shadow_daily_adapter.py`

Daily no-order wrapper:

1. accepts one or more raw Kite CSVs and/or existing H1 completed-bar CSVs;
2. writes the canonical H1 completed-bar CSV;
3. runs `validate_h1_forward_bar_intake_v18.py`;
4. runs `run_trapped_push_snapback_v14_prospective_observer.py` only if validation passes;
5. writes `H1_SHADOW_ADAPTER_RUN_AUDIT.json`.

### `tests/test_h1_shadow_adapter.py`

Focused tests cover:

- UTC Kite timestamps converting to Asia/Kolkata completed-bar timestamps;
- no-order authority guard rejecting any enabled authority flag;
- completed-bar merge deduplication and latest-value precedence.

## Example Usage

```bash
python3 scripts/research/hypothesis_factory/run_h1_shadow_daily_adapter.py \
  --observation-date 2026-08-10 \
  --raw-kite-csv research/evidence/trapped_push_snapback_kite_full_opening_20260810/raw_kite_remaining/NIFTY_50_intraday.csv \
  --completed-h1-csv research/evidence/trapped_push_snapback_v18_today_readonly_fetch/input_bars/NIFTY_5MIN_2026-08-10_COMPLETED.csv \
  --evidence-root research/evidence/h1_shadow_daily_adapter_v1/20260810 \
  --run-id KITE_H1_SHADOW_20260810 \
  --evidence-commit 477aadf34e09c097c1c3774954000bc62356b5fc \
  --registry-commit b57197b5643b0e99087dbfac091eb9a2054a5e1b
```

## Expected Controlled Interpretation

```text
H1_SHADOW_ADAPTERS_PR_READY_NO_ORDER = true
PREDICATE_CHANGED = false
ORDERS_CREATED = 0
BROKER_WRITES_CREATED = 0
PAPER_AUTHORIZED = false
LIVE_AUTHORIZED = false
ORDER_AUTHORITY = false
BROKER_WRITE_AUTHORITY = false
PROSPECTIVE_SUPPORTED = false
EXECUTION_VIABLE = false
STRUCTURAL_EDGE_CERTIFIED = false
EDGE_CLAIMED = false
```

## Validation Note

A focused standalone adapter unit-test check was run against these adapter files in an isolated temp copy:

```text
python -m pytest -q tests/test_h1_shadow_adapter.py
3 passed
```

This is not a substitute for full repository CI or forward-market evidence.

## Sealed Live-Capture Export Contract

`export_h1_live_capture_bars.py` is a read-only bridge for a sealed TradeBot
capture. It accepts either a SQLite `ticks` database or `price_trace.jsonl`,
selects only the explicitly configured NIFTY token (`256265` by default), and
emits deterministic five-minute OHLC with the exact columns:

```text
datetime,open,high,low,close
```

SQLite is opened with `mode=ro`; the source is never migrated, checkpointed,
vacuumed, or written. Events are ordered by timestamp and then SQLite `rowid`
(or JSONL line number). Missing bars are reported and never filled. The
governed path fails closed unless all 27 starts from `09:15` through `11:25`
IST are present, making the `09:15–11:30 IST` opening-window gate complete and
leaving at least the seven sequential bars required by the H1 observer.

Example, after the source database is sealed:

```bash
python3 scripts/research/hypothesis_factory/export_h1_live_capture_bars.py \
  --sqlite /sealed/session/db/DEFAULT.sqlite \
  --observation-date 2026-08-17 \
  --output-csv /sealed/session/observers/h1/finalized_h1_completed_bars_20260817.csv \
  --manifest /sealed/session/observers/h1/finalized_h1_completed_bars_20260817.manifest.json
```

`--allow-incomplete` is diagnostic-only and must not be used as replay
authority. It writes a manifest with `h1_replay_input_valid=false` when the
opening-window gate fails. This exporter does not alter the frozen predicate,
create orders, call broker APIs, or authorize paper/live execution.
