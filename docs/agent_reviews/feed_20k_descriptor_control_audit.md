# Feed 20k descriptor control audit

Base checkpoint:

`4b6917e5b5ae618c6cc52f0a31168f4f70ef99e9f`

Commit message:

`test: prove bounded async feed persistence recovery`

Branch:

`ram/feed-fd-diagnosis-main-sync`

Worktree:

`/Users/madhuram/tradebot-feed-fd-diagnosis-main-sync`

Remote main baseline:

`4201e416cebdf8c6fd0172cf59bd8187e0cdf9e4`

Current checkpoint scope proved before this note:

- `SYNC_CONTROL_PASS_BOUNDED_BURST`
- `ASYNC_CONTROL_PASS_BOUNDED_BURST`
- `20K_SYNC_ASYNC_PASS_BOUNDED_BURST`

Maximum supported claim:

`Offline feed processing is proven through 20,000 rows for the tested normal-speed synchronous and asynchronous persistence paths, within the measured descriptor envelope.`

This does not prove:

- 100k or full-capture scale
- persistence slowdown or meaningful queue backlog
- malformed/out-of-order/gap fault handling
- real websocket disconnection or reconnect
- subscription restoration
- provider completeness
- full live-session robustness

Exact 20k replay commands:

```bash
PYTHONUNBUFFERED=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/sync-20k-normal-baseline \
  --iterations 1 \
  --max-rows 20000 \
  --session-cycles 0 \
  --scenario normal_speed \
  --persistence-mode sync

PYTHONUNBUFFERED=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/async-20k-normal-baseline \
  --iterations 1 \
  --max-rows 20000 \
  --session-cycles 0 \
  --scenario normal_speed \
  --persistence-mode async_queue

PYTHONUNBUFFERED=1 TRADEBOT_FEED_FD_TRACE=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/sync-20k-normal-traced \
  --iterations 1 \
  --max-rows 20000 \
  --session-cycles 0 \
  --scenario normal_speed \
  --persistence-mode sync

PYTHONUNBUFFERED=1 TRADEBOT_FEED_FD_TRACE=1 \
/Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/async-20k-normal-traced \
  --iterations 1 \
  --max-rows 20000 \
  --session-cycles 0 \
  --scenario normal_speed \
  --persistence-mode async_queue
```

Input envelope:

- input path: `/Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet`
- full input SHA-256: `62410f680b0621c836e3b18e8a509126e3dfbcf40c61e3cc23d5c2bc30b95139`
- total available rows: `2778666`
- selected rows: `20000`
- selected source timestamp range: `1783569405.7407` to `1783569520.28162`
- distinct instrument-token count: `129`
- missing timestamp count: `0`
- malformed timestamp count: `0`

Artifact directories:

- `.runtime/feed_robustness_audit/sync-20k-normal-baseline`
- `.runtime/feed_robustness_audit/async-20k-normal-baseline`
- `.runtime/feed_robustness_audit/sync-20k-normal-traced`
- `.runtime/feed_robustness_audit/async-20k-normal-traced`

Artifact SHA-256s:

Sync untraced:

- `run_manifest.json`: `5a37ce6b2347032f8e10bbc1595835496ce1539cb7bed4e705a48ef3eae516f5`
- `checksums.json`: `0980789fca61a42db80a9629a806ac279c4ad008f96cbbbb34947595165cb163`
- `feed_verdict.json`: `480343a4f151291f43a76af3c1ec70935c7ed468cc36f114bde92c73e2cadfc4`
- `latency_report.json`: `da8155908030f80389533ed5bb82dc392bf0beb8b85ce8d2c44346916dba6ac5`
- `resource_snapshot.json`: `92b4df15e7a61d88478ca6ef19f48d80be714dcef91ea550fd68e363923d0bbb`
- `timestamp_fidelity.json`: `06349531baa3769e81cf576bf8cf96df3797d8e9ddffea2daca7f728eb849885`

Async untraced:

- `run_manifest.json`: `e97a09e2e80c01990a4e8f06e0ac43cfb959cfe33a964d25b58cb5a95094406d`
- `checksums.json`: `0d4b472c60abbb1cbbe823be01eb43769339929139af014cb97cce5aeb0a0d39`
- `feed_verdict.json`: `480343a4f151291f43a76af3c1ec70935c7ed468cc36f114bde92c73e2cadfc4`
- `latency_report.json`: `1c0116cc088653994dd263496bab7715d3f9c819c5027fa16045236e7f5ff27f`
- `resource_snapshot.json`: `3a3037cdfec8bd7ada958ce9ac2eedba32f93c578faf0086fc21968b91b263c8`
- `timestamp_fidelity.json`: `06349531baa3769e81cf576bf8cf96df3797d8e9ddffea2daca7f728eb849885`

Sync traced:

- `run_manifest.json`: `0ca460abd77f97214bca49fb07803d8e6a8f4647fba143befd8d6e9e2f2f0f28`
- `checksums.json`: `be2c5d21f00915ad26997cd813e6c3aa48e7369d4915b69d18f28960c9a2d32f`
- `feed_verdict.json`: `480343a4f151291f43a76af3c1ec70935c7ed468cc36f114bde92c73e2cadfc4`
- `latency_report.json`: `4f2385fdb0654dcbb692abba367b17742dfc83504bcbf6bfe16b6be9d04ef314`
- `resource_snapshot.json`: `c4c8b914990766f18b223e435b2d148a3e74b97dbddfe1b44e829d1157b0d04e`
- `timestamp_fidelity.json`: `06349531baa3769e81cf576bf8cf96df3797d8e9ddffea2daca7f728eb849885`

Async traced:

- `run_manifest.json`: `eb414e59d9f7210f3556067d0a685ba5ccd6298248b97072988f28cbfbb43918`
- `checksums.json`: `9eeca1f458f7b77110014f7085030145fe18683fc6aa7be649f45f9e48f0ecf4`
- `feed_verdict.json`: `480343a4f151291f43a76af3c1ec70935c7ed468cc36f114bde92c73e2cadfc4`
- `latency_report.json`: `9499e2bffe5f52ed4e8ed1477009674511daa588a90cda2916053e7f5f0c0bc1`
- `resource_snapshot.json`: `ea03c6ce81a1c1884b4868291cc253caad3eaa718a35989133a4ae597c4b7cae`
- `timestamp_fidelity.json`: `06349531baa3769e81cf576bf8cf96df3797d8e9ddffea2daca7f728eb849885`

Canonical semantic hashes:

- sync untraced: `cc7dc79c602faf0dcd74a10104f490f347676e9f62963162f59b024f263e9c3f`
- async untraced: `cc7dc79c602faf0dcd74a10104f490f347676e9f62963162f59b024f263e9c3f`
- sync traced: `cc7dc79c602faf0dcd74a10104f490f347676e9f62963162f59b024f263e9c3f`
- async traced: `cc7dc79c602faf0dcd74a10104f490f347676e9f62963162f59b024f263e9c3f`

Final token-state hashes:

- sync untraced: `6e499a203cad96d51919233f9050c772217fb864b0fe50e47e34c7dcf427e347`
- async untraced: `6e499a203cad96d51919233f9050c772217fb864b0fe50e47e34c7dcf427e347`
- sync traced: `6e499a203cad96d51919233f9050c772217fb864b0fe50e47e34c7dcf427e347`
- async traced: `6e499a203cad96d51919233f9050c772217fb864b0fe50e47e34c7dcf427e347`

Sync/async reconciliation values:

- decoded minus normalized minus rejected: `0` for all four runs
- normalized minus published minus explicitly_dropped: `0` for all four runs
- published minus persisted minus pending_at_shutdown: `0` for all four runs

Worker lifecycle evidence:

- async worker started exactly once: `true`
- worker joined: `true`
- worker terminated cleanly: `true`
- worker failures: `0`
- worker thread name: `tick-store-flush`

Queue evidence:

- rows enqueued: `20000`
- rows dequeued: `20000`
- queue depth at shutdown: `0`
- queue depth high-water: `1`
- pending writes at shutdown: `0`
- committed batches: `20000`
- committed rows: `20000`

FD evidence:

- sync untraced baseline/final: `84` / `84`
- async untraced baseline/final: `76` / `76`
- sync traced baseline/high-water/final: `8` / `87` / `8`
- async traced baseline/high-water/final: `51` / `89` / `51`

Runtime values:

- sync untraced replay duration: available in `sync-20k-normal-baseline/resource_snapshot.json`
- async untraced replay duration: available in `async-20k-normal-baseline/resource_snapshot.json`
- sync traced replay duration: available in `sync-20k-normal-traced/resource_snapshot.json`
- async traced replay duration: available in `async-20k-normal-traced/resource_snapshot.json`

Strict verdict:

`20K_SYNC_ASYNC_PASS_BOUNDED_BURST`

The maximum proven claim is the one stated above. The 20k proof does not extend to 100k, full-capture, fault injection, live reconnects, provider completeness, or full live-session robustness.
