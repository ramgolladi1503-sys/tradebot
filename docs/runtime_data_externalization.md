# Runtime Data Externalization

TradeBot worktrees must stay lightweight. Source code, tests, schemas, scripts, templates, and small deterministic fixtures belong in Git. Historical market data, Parquet corpora, broker captures, replay datasets, and generated runtime evidence belong outside Git.

## Shared Data Root

Default local root:

```bash
export TRADEBOT_DATA_ROOT="$HOME/tradebot-shared-data"
```

Supported layout:

```text
$TRADEBOT_DATA_ROOT/
  historical/
  replay/
  market_data/
  research_inputs/
  archived_live_evidence/
```

Purpose-specific overrides are available when one category lives elsewhere:

```bash
export TRADEBOT_HISTORICAL_DATA_ROOT=/path/to/historical
export TRADEBOT_REPLAY_DATA_ROOT=/path/to/replay
export TRADEBOT_MARKET_DATA_ROOT=/path/to/market_data
export TRADEBOT_RESEARCH_INPUTS_ROOT=/path/to/research_inputs
export TRADEBOT_ARCHIVED_LIVE_EVIDENCE_ROOT=/path/to/archived_live_evidence
```

Live runtime state remains controlled by the existing `DATA_ROOT` contract and defaults to `.runtime`. Live startup must not require the shared historical corpus unless a live module explicitly documents that dependency.

## Minimal Runtime Requirements

Kite live observation requires credentials/token paths, launch-plan inputs, writable live output/log roots, lock roots, and DB/runtime state under `DATA_ROOT`. It does not require the historical Parquet corpus.

Upstox live capture requires Upstox credentials, the configured capture output root, writable runtime/log roots, and instrument metadata needed by the capture command. It does not require the full replay corpus.

Offline replay, backtests, and research campaigns must read large data from `TRADEBOT_HISTORICAL_DATA_ROOT`, `TRADEBOT_REPLAY_DATA_ROOT`, or `TRADEBOT_MARKET_DATA_ROOT`. Tests must use small fixtures under `tests/fixtures`.

## Cleanup Gates

Before deleting any existing copy:

1. Confirm no process is writing to the path.
2. Record path, branch, HEAD, and `git status`.
3. Classify data as historical, replay, generated evidence, cache, fixture, source, config, schema, secret, or unknown.
4. Preserve one canonical shared copy.
5. Verify byte identity with hashes or trusted LFS object ids.
6. Preserve active campaign evidence, credentials, unique untracked evidence, and uncommitted source changes.
7. Prefer `git worktree remove <exact-path>` for obsolete clean worktrees.

Do not run `git lfs prune` until remote LFS availability and branch/tag preservation have been verified.
