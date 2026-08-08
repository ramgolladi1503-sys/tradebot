# TradeBot Strategy Certification Kernel v0.1

This kernel is a fast research triage layer for generating, screening, ranking, and passporting strategy hypotheses before any MROS certification or TradeBot adapter integration.

It is deliberately conservative:

- it does not certify strategies;
- it does not grant runtime authority;
- it does not place, modify, or cancel orders;
- fallback/recovered data is excluded from executable screen trades;
- every output remains `NOT_CERTIFIED` until later robustness and MROS review.

## Pipeline

```text
hypothesis JSON -> cheap proxy screen -> leaderboard -> NOT_CERTIFIED passport -> later robustness/MROS gate
```

## Quick start

Generate hypotheses:

```bash
python3 scripts/research/hypothesis_factory/hypothesis_factory.py generate \
  --output research/hypotheses/generated/hypotheses.json
```

Screen against a CSV containing at least `timestamp,instrument,open,high,low,close`:

```bash
python3 scripts/research/hypothesis_factory/hypothesis_factory.py screen \
  --hypotheses research/hypotheses/generated/hypotheses.json \
  --data path/to/history.csv \
  --output-json research/hypotheses/screen_results/results.json \
  --output-csv research/hypotheses/leaderboard.csv
```

Emit research-only passports for the top ranked rows:

```bash
python3 scripts/research/hypothesis_factory/hypothesis_factory.py passports \
  --hypotheses research/hypotheses/generated/hypotheses.json \
  --screen-results research/hypotheses/screen_results/results.json \
  --top 5
```

## Corpus runner

Use the corpus runner when the data is already checked out locally or synchronized from Google Drive.

It auto-searches these known local roots when present:

```text
/Users/madhuram/tradebot/runtime/upstox_candidate_replay
/Users/madhuram/tradebot/runtime
/Users/madhuram/tradebot/.runtime/market_data
/Users/madhuram/tradebot-ml-evidence
/Users/madhuram/tradebot-research-corpus
Google Drive CloudStorage folders matching tradebot_market_data/upstox_market_data/market_data/kite_candidate_replay
```

Run:

```bash
python3 scripts/research/hypothesis_factory/run_corpus_screen.py \
  --output-dir research/hypotheses/corpus_runs \
  --instrument NIFTY \
  --instrument BANKNIFTY \
  --max-files 200 \
  --max-rows-total 250000
```

Or force one corpus root:

```bash
python3 scripts/research/hypothesis_factory/run_corpus_screen.py \
  --no-known-roots \
  --no-gdrive-discovery \
  --corpus-root /Users/madhuram/tradebot/runtime/upstox_candidate_replay \
  --output-dir research/hypotheses/corpus_runs
```

The runner writes a timestamped run folder containing:

```text
generated_hypotheses.json
screen_results.json
leaderboard.csv
strategy_passports.json
run_manifest.json
```

Parquet files require local `pandas`/`pyarrow`. CSV files use the Python standard library.

## Status meanings

- `GENERATED`: template hypothesis only.
- `REJECTED`: failed cheap proxy screen.
- `PROMISING_NOT_CERTIFIED`: survived cheap proxy screen only.
- `NOT_CERTIFIED`: no TradeBot integration authority.

A `PROMISING_NOT_CERTIFIED` candidate is not an edge claim. It only deserves robustness validation.
