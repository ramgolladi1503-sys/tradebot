# Failed Discovery H1 V1 — DEV Corpus Runbook

## Authority

This runbook executes the already frozen `VWAP_FAILED_DISCOVERY_RETURN_TO_VALUE_H1_V1` detector. It does not authorize formula changes or strategy design.

## Known partial futures corpus

The preserved acquisition evidence identifies:

```text
instrument_key = NSE_FO|61093
symbol         = NIFTY FUT 28 JUL 26
date_span      = 2026-05-12 .. 2026-07-21
rows           = 18,375
sessions       = 49
LFS size       = 467,857 bytes
SHA-256        = 8120d53a270ef2d5ebe1e94e800c8cd289df6e4081d7fa019e7c9ca0bd5bd92b
```

The acquisition coverage report marks this corpus **partial** and says its minimum historical target was not met. Therefore it is DEV/preliminary evidence only. It must not be labeled OOS, holdout, robust certification, or commercialization evidence.

## Required local precondition

The Git LFS object must be materialized as the real parquet bytes. A text LFS pointer is not valid input.

Verify before running:

```bash
FILE=/path/to/NSE_FO_61093.parquet
shasum -a 256 "$FILE"
wc -c "$FILE"
```

Expected:

```text
8120d53a270ef2d5ebe1e94e800c8cd289df6e4081d7fa019e7c9ca0bd5bd92b
467857 bytes
```

Install parquet readers in the isolated research environment if missing:

```bash
python -m pip install pandas pyarrow
```

## Exact DEV command

From the repository root on PR #865 / branch `research/vwap-failed-discovery-hypothesis-v1`:

```bash
python -m research.vwap_failed_discovery_hypothesis_v1.run_corpus \
  --input "$FILE" \
  --output runtime/research/vwap_failed_discovery_h1_v1/dev_partial_20260512_20260721.json \
  --expected-sha256 8120d53a270ef2d5ebe1e94e800c8cd289df6e4081d7fa019e7c9ca0bd5bd92b \
  --partition DEV \
  --known-partial-corpus
```

The runner independently verifies SHA-256, byte size, 49-session identity, and date span. Any mismatch fails closed.

## Report contents

The JSON report records:

- exact input path, SHA-256 and size;
- session/date identity;
- frozen detector parameters;
- unmatched failed-discovery event count;
- deterministic matched event/control count;
- event and control primary success rates;
- primary risk difference;
- 1/3/5/10/15/30-minute directional-return medians and uplift;
- MFE and MAE summaries;
- month concentration;
- preliminary hypothesis verdict.

## Interpretation

`INCONCLUSIVE`
: Not enough matched support. Do not loosen thresholds to manufacture events.

`REJECTED`
: The frozen effect fails on sufficient DEV evidence. Preserve the negative result; do not turn it into a strategy.

`SUPPORTED`
: DEV clears the frozen support gate. This still does **not** authorize a strategy. Continue with negative controls, parameter-neighborhood robustness, chronology/regime analysis, walk-forward OOS, independent oracle and untouched holdout.

The DEV runner can never emit `ROBUSTLY_SUPPORTED`.

## Prohibited reaction to results

After this file is evaluated, do not alter `band_sigma`, acceptance count, efficiency threshold, slope threshold, failure lookback, re-entry zone, primary horizon, control definition, or +5 percentage-point support threshold and rerun under the V1 name. Any such change creates V2 and requires a new research boundary.
