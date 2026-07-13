# Feed async descriptor control audit

Base checkpoint:

`81b13139289f5c972396c08169e8ed6047e5c3da`

Commit message:

`test: prove bounded feed descriptor recovery`

Branch:

`ram/feed-fd-diagnosis-main-sync`

Worktree:

`/Users/madhuram/tradebot-feed-fd-diagnosis-main-sync`

Dirty files in scope while this note was created:

- `core/tick_store.py`
- `scripts/run_feed_robustness_replay.py`
- `tests/test_feed_robustness_replay_runner.py`
- `docs/agent_reviews/feed_async_descriptor_control_audit.md`

Current checkpoint state:

- sync 10k control: `SYNC_CONTROL_PASS_BOUNDED_BURST`
- async 10k control: `ASYNC_CONTROL_PASS_BOUNDED_BURST`

Current diff SHA-256 at capture time:

`48d5565a407630762deb9425c641583da22076e3da29ddb1c676e3e9607342fb`

Scope proved:

- 10,000 rows
- normal-speed scenario
- one iteration
- offline replay
- synchronous path
- real async queue / worker path
- worker starts, drains, joins, and terminates
- rows enqueued equal rows dequeued
- pending writes return to zero
- queue returns to zero
- semantic output matches sync
- no feed-side EMFILE

This note does not prove 20k / 100k robustness, live websocket/reconnect behaviour, or tracing as a feed-performance metric.

Exact verification commands:

```bash
cd /Users/madhuram/tradebot-feed-fd-diagnosis-main-sync
git branch --show-current
git rev-parse HEAD
git status --short --untracked-files=all
git diff --check

/Users/madhuram/tradebot/.venv/bin/python -m pytest -q \
  tests/test_feed_robustness_replay_runner.py \
  tests/test_kite_depth_ws_stability.py \
  tests/test_feed_fd_trace.py \
  tests/test_ws_tick_ingestion_updates_tick_store.py \
  tests/test_tick_store.py \
  --tb=long

git diff --check
git diff --name-status
git diff --stat
git diff | shasum -a 256
```

Exact replay commands:

```bash
PYTHONUNBUFFERED=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/main-sync-10k-normal-baseline-v6 \
  --iterations 1 \
  --max-rows 10000 \
  --session-cycles 0 \
  --scenario normal_speed

PYTHONUNBUFFERED=1 TRADEBOT_FEED_FD_TRACE=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/main-sync-10k-normal-traced-v6 \
  --iterations 1 \
  --max-rows 10000 \
  --session-cycles 0 \
  --scenario normal_speed

PYTHONUNBUFFERED=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/async-10k-normal-baseline-clean \
  --iterations 1 \
  --max-rows 10000 \
  --session-cycles 0 \
  --scenario normal_speed \
  --persistence-mode async_queue

PYTHONUNBUFFERED=1 TRADEBOT_FEED_FD_TRACE=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/async-10k-normal-traced-clean \
  --iterations 1 \
  --max-rows 10000 \
  --session-cycles 0 \
  --scenario normal_speed \
  --persistence-mode async_queue
```

Artifact paths:

- `.runtime/feed_robustness_audit/main-sync-10k-normal-baseline-v6`
- `.runtime/feed_robustness_audit/main-sync-10k-normal-traced-v6`
- `.runtime/feed_robustness_audit/async-10k-normal-baseline-clean`
- `.runtime/feed_robustness_audit/async-10k-normal-traced-clean`

Artifact SHA-256s:

- `main-sync-10k-normal-baseline-v6/run_manifest.json`: `bd4016afeb2c53bd44469b609b3b0e2962e7bf81eb4f91fbe3dca3979bf4d7a6`
- `main-sync-10k-normal-baseline-v6/checksums.json`: `a8205a100c8a416870f908cd84bf59625134d161a43e2ce23750493baa6686a2`
- `main-sync-10k-normal-baseline-v6/feed_verdict.json`: `b699df99876be8a9755847cccce3a08975b56308222d09cba89513b49a7f6e5d`
- `main-sync-10k-normal-traced-v6/run_manifest.json`: `d29b2df46bf764a94d4e9cdcd27a72efc0cfeae2f6026e8207597b413e3281d2`
- `main-sync-10k-normal-traced-v6/checksums.json`: `5334214d0bbacc20dffe9b5a63eb3585b050321f248111dcaa1261e0e2c8e897`
- `main-sync-10k-normal-traced-v6/feed_verdict.json`: `b699df99876be8a9755847cccce3a08975b56308222d09cba89513b49a7f6e5d`
- `async-10k-normal-baseline-clean/run_manifest.json`: `dbdc6caaed2c74f5a7354c3a7f78f7c046d6c9d8d46f817ac27b44e8a0fe86f4`
- `async-10k-normal-baseline-clean/checksums.json`: `d0f1b84c02a9ab1affe8712c2786bd93fd1abe08817fa573546366262a038b69`
- `async-10k-normal-baseline-clean/feed_verdict.json`: `b699df99876be8a9755847cccce3a08975b56308222d09cba89513b49a7f6e5d`
- `async-10k-normal-traced-clean/run_manifest.json`: `8259b597197c75f25db88c070bf7f143f2a9e36947c1af800923e1293d814a11`
- `async-10k-normal-traced-clean/checksums.json`: `411c8e8700d9bba8f685ac97fee59861e7d57fc37ee4501a68a9a387dd6748bf`
- `async-10k-normal-traced-clean/feed_verdict.json`: `b699df99876be8a9755847cccce3a08975b56308222d09cba89513b49a7f6e5d`

Deterministic hashes:

- input source order: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- callback order: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- normalization order: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- persistence order: `0e9b838554106bb5d5ce9fba0a2eafafd6e7abcaff84da1c01a5424f27149a77`
- canonical semantic output: `8e4e94bb76ea84a179cc7765c211bcab06bf599bf9fd5e028de6466a9b1accd1`
- final per-token state: `ce8313a1e8fd96c9b33c05fd53ccbacfefa6fe7cc9e0a86cb391cb1305d49073`

Sync-versus-async comparison:

| Evidence | Sync untraced | Sync traced | Async untraced | Async traced |
| --- | ---: | ---: | ---: | ---: |
| Exit code | 0 | 0 | 0 | 0 |
| Hard failures | [] | [] | [] | [] |
| Rows | 10000 | 10000 | 10000 | 10000 |
| Canonical semantic hash | identical | identical | identical | identical |
| Final token-state hash | identical | identical | identical | identical |
| Reconciliation deltas | 0 | 0 | 0 | 0 |
| Timestamp fidelity | pass | pass | pass | pass |
| Worker started | 0 | 0 | 1 | 1 |
| Worker terminated | null | null | true | true |
| Worker join completed | null | null | true | true |
| Worker failures | 0 | 0 | 0 | 0 |
| Rows enqueued | 0 | 0 | 10000 | 10000 |
| Rows dequeued | 0 | 0 | 10000 | 10000 |
| Queue depth at shutdown | 0 | 0 | 0 | 0 |
| Pending writes at shutdown | 0 | 0 | 0 | 0 |
| Baseline FD | 79 | 8 | 71 | 49 |
| High-water FD | null | 83 | null | 85 |
| Final FD | 79 | 8 | 71 | 49 |
| Semantic equivalence across trace/no-trace | pass | pass | pass | pass |

Worker lifecycle evidence:

- async worker thread name: `tick-store-flush`
- async worker start count: `1`
- async worker thread id recorded in artifact
- async worker terminated cleanly: `true`
- async worker join completed: `true`
- async worker failures: `0`

Queue evidence:

- rows enqueued: `10000`
- rows dequeued: `10000`
- committed rows: `10000`
- committed batches: `10000`
- queue depth initial: `0`
- queue depth high-water: `1`
- queue depth at shutdown: `0`
- pending writes at shutdown: `0`

Descriptor evidence:

- sync untraced FD returned to its own baseline: `79 → 79`
- sync traced FD returned to its own baseline: `8 → 8`
- async untraced FD returned to its own baseline: `71 → 71`
- async traced FD returned to its own baseline: `49 → 49`
- traced async high-water FD: `85`
- traced async callback-exit FD range: `15–73`

Limitations:

- only the 10k normal-speed offline path is proved here
- 20k and 100k remain unproven
- this does not prove live websocket or reconnect behavior
- this does not make tracing a valid feed-performance benchmark

Strict verdict:

`ASYNC_CONTROL_PASS_BOUNDED_BURST`
