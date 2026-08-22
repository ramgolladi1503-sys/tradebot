# Raj Arora / HYP_B1 Intersection V11 — Execution Blocker & Exact Local Handoff

Status: `READY_TO_EXECUTE_BLOCKED_ONLY_ON_SHA_BOUND_LOCAL_INPUT_BYTES`

## What is complete

V11 is no longer an informal research idea. The following are frozen on branch:

`research/raj-arora-hyp-b1-intersection-v11`

- hypothesis/passport freeze:
  `research/strategy_certification/passports/RAJ_ARORA_HYP_B1_INTERSECTION_V11_FREEZE.json`
- execution/null semantics:
  `research/evidence/strategy_certification/RAJ_ARORA_HYP_B1_INTERSECTION_V11_EXECUTION_SPEC.md`
- fail-closed runner:
  `scripts/research/hypothesis_factory/run_raj_arora_hyp_b1_intersection_v11.py`
- contract tests:
  `tests/research/test_raj_arora_hyp_b1_intersection_v11.py`

Latest runner authority commit at handoff:

`5af18a7c5151b0224851e0a64c558e310cae88e2`

The runner includes a semantic parity guard that must reproduce the already-frozen V3 base event before any futures information is joined:

```text
expected V3 30m development trades = 33
expected V3 mean net @5bps = +3.620837288 bps/trade
```

If either parity value fails, V11 stops fail-closed.

Synthetic contract tests were executed in the research sandbox after the parity patch and passed `5/5`. These tests cover downside-first ordering, upside-first rejection, the two-bar reclaim boundary, reclaim-end 1-minute futures alignment, and profit-concentration semantics. This is implementation-contract evidence only; it is not a market result.

## Exact required local inputs

### Canonical NIFTY 5-minute corpus

Historical expected path:

`/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv`

Required SHA-256:

`6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`

Required structural authority:

```text
rows=36849
sessions=493
development_sessions=295
development_end=2025-09-15
validation_sessions_reserved=98
holdout_sessions_reserved=100
```

### Causally aligned NIFTY spot/futures panel

Historical expected path:

`/Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet`

Required SHA-256:

`2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9`

Historical alignment authority records:

```text
rows=185681
frozen roll rule=NEAREST_UNEXPIRED_EXPIRY_ON_SESSION_START_V1
selection discrepancies=0
roll transitions=20
```

Do not rebuild or substitute this panel and then call it the same authority unless its final SHA exactly matches the required hash.

## Why execution did not occur in the current research environment

The connected evidence surfaces expose the alignment report, HYP_B1 reports, exact reconstruction logic and historical paths/hashes, but they do not expose the binary aligned Parquet itself. The data path was local to the TradeBot Mac and the file was not committed to GitHub.

The historical HYP_B1 event tape is also documented at:

`/Users/madhuram/tradebot/research/evidence/hyp_b1_path_to_strategy_options_v1/HYP_B1_EVENT_TAPE.parquet`

with recorded architecture:

```text
all HYP_B1 trigger events=18012
primary non-overlapping events=4498
first events/session=495
```

but those binary rows are likewise not exposed through the connected surfaces. No V11 market outcome has therefore been inferred from summaries or fabricated from aggregate statistics.

## Exact local execution procedure

Do not switch or dirty `main` merely to run this experiment.

1. Create or reuse an isolated worktree checked out at exactly:

   `research/raj-arora-hyp-b1-intersection-v11`

2. Before running, print and record:

```bash
git -C <V11_WORKTREE> rev-parse HEAD
git -C <V11_WORKTREE> status --short
shasum -a 256 /Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv
shasum -a 256 /Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet
```

3. Both input hashes must match the exact values above. If either does not match, stop. Do not search for a similar file and continue silently.

4. Run contract tests first:

```bash
python3 -m pytest -q \
  <V11_WORKTREE>/tests/research/test_raj_arora_hyp_b1_intersection_v11.py
```

5. Run the frozen development experiment only:

```bash
python3 \
  <V11_WORKTREE>/scripts/research/hypothesis_factory/run_raj_arora_hyp_b1_intersection_v11.py \
  --repo-root <V11_WORKTREE> \
  --nifty-dataset /Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv \
  --aligned-panel /Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet \
  --output research/evidence/strategy_certification/RAJ_ARORA_HYP_B1_INTERSECTION_V11_DEVELOPMENT.json
```

6. Verify the output explicitly contains:

```text
validation_accessed=false
holdout_accessed=false
v3_base_parity_30m_trades=33
v3_base_parity_mean_net_5bps_30m≈3.620837288
```

7. If `status != DEVELOPMENT_COMPLETE`, preserve the fail-closed output and stop.

8. If `DEVELOPMENT_COMPLETE`, inspect the frozen ACTIVE/INACTIVE metrics and gates. Do not edit any gate or input rule after seeing them.

9. Null controls run automatically only if all pre-null development gates pass.

10. Validation remains unopened unless V11 returns:

`V11_INCREMENTAL_MECHANISM_CANDIDATE`

Even then, do not open validation automatically in the same command. Freeze the development artifact and make a separate validation decision under the kernel.

## Explicit prohibited actions

Do not:

- touch or merge `main` for this research run;
- use a different basis threshold;
- refit the 90th percentile;
- change the 15-minute basis window;
- use basis at breakout instead of the frozen reclaim-end decision time;
- alter the 10-minute opening range, 5-bps break, first-break ordering, or two-bar reclaim window;
- reduce the minimum ACTIVE trade count;
- relax the 80% top-five concentration cap;
- alter the +2-bps ACTIVE-vs-INACTIVE separation gate;
- run nearby thresholds after seeing V11 results;
- access current Raj validation or holdout if V11 fails development;
- infer options profitability from an underlying V11 result;
- grant paper/live/broker authority.

## Current controlled status

```text
V11_SPEC_FROZEN=true
V11_RUNNER_IMPLEMENTED=true
V11_V3_SEMANTIC_PARITY_GUARD=true
V11_CONTRACT_TESTS=5_OF_5_PASS_SYNTHETIC
V11_REAL_MARKET_DEVELOPMENT_EXECUTED=false
CURRENT_BLOCKER=EXACT_ALIGNED_FUTURES_PANEL_BYTES_NOT_EXPOSED_TO_CURRENT_ENVIRONMENT
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
STRATEGY_CERTIFIED=false
STRUCTURAL_EDGE_CERTIFIED=false
RUNTIME_AUTHORITY=NONE
BROKER_ACTIONS_PERMITTED=false
```

The scientifically correct next action is to execute this exact V11 runner against the SHA-bound local Mac inputs. If V11 fails, close the Raj-Arora-derived line rather than create a nearby V12 filter search. If V11 passes, freeze the development evidence before considering the reserved validation partition.
