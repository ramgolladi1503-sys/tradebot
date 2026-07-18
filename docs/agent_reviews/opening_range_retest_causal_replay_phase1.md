# Opening Range Retest Causal Replay Phase 1

Scope:
`opening_range_retest_v1` signal-generation replay only.

Current status:
`OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`

Reason:
authoritative corpus replay completed over 1512 approved sessions, bounded artifacts were published, and two independent full-corpus shard ensembles converged on the same candidate and canonical summary hashes.

What changed:
- Added a research-only replay package under `research/opening_range_retest/`.
- The replay directly calls `strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates`.
- Source selection fails closed by default when the manifest-linked inventory file is unavailable.
- A bounded audit path validates the tracked JSON artifacts without rerunning the full corpus.
- Deterministic sharding and shard-merge support were added for bounded parallel full-corpus execution.
- The shared manifest hash was repaired to match the checked-in authoritative inventory artifact after sidecar verification.

What did not change:
- No production strategy logic.
- No shared runtime architecture.
- No thresholds, constants, setup identity inputs, or direction semantics.
- No execution, broker, paper/live, or profitability behavior.

New config and runtime switches:
- Runner flag: `--allow-manifest-without-inventory`
  Use only when the linked inventory file is unavailable in the current checkout and you want the fallback fail-closed scan over the approved roots.
- Runner flag: `--limit-sessions`
  Use for deterministic smoke runs only.
- Runner flags: `--shard-count` and `--shard-index`
  Use for deterministic sharded authoritative replay.
- Runner flag: `--merge-shard-dir`
  Use to merge previously audited shard directories into one bounded artifact set.

Tests added:
- `tests/test_opening_range_retest_causal_replay.py`

Run instructions:
```bash
cd /Users/madhuram/tradebot-opening-range-retest-causal-replay
pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_four_strategy_contract_freeze.py tests/test_opening_movement_strategies.py tests/test_opening_range_retest_causal_replay.py
python scripts/generate_opening_range_retest_causal_replay.py --output-dir /tmp/opening-range-retest-ensemble-a-merged --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-00 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-01 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-02 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-03 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-04 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-05 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-06 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-07 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-08 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-09 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-10 --merge-shard-dir /tmp/opening-range-retest-ensemble-a/shard-11
python scripts/audit_opening_range_retest_causal_replay.py --artifact-dir docs/agent_reviews
```

Rollout steps:
1. Run the targeted tests.
2. Verify manifest hash consistency against the checked-in inventory sidecar.
3. Run bounded sharded smoke replay and compare merged versus non-sharded hashes.
4. Run the full authoritative shard ensembles and confirm ensemble A/B hash convergence.
5. Publish and audit the tracked bounded artifacts.
6. Review the verdict and claim boundary before any follow-on Phase 2 work.

Migration notes:
- The current checked-in manifest records stale provenance paths from an older worktree.
- The authoritative inventory artifact for this task is the checked-in repository-relative file `docs/agent_reviews/upstox_corpus_inventory_v2.json` after sidecar and manifest-hash verification.
- Diagnostic fallback scanning is non-authoritative and cannot produce `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`.

Final verified artifact summary:
- `phase1_verdict`: `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`
- `candidate_semantic_hash`: `53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24`
- `canonical_summary_semantic_hash`: `0cdb2a65c0bc0a1d567db1ad27d0c0254cfd85206eed85e5cfbb58f64329c404`
- `selected_file_count`: `1512`
- `ensemble_convergence`: full 12-shard and 13-shard merged runs matched on candidate and canonical summary hashes.

Claim boundary:
- Phase 1 proves deterministic, causal signal generation over approved underlying-candle sources.
- Phase 1 does not prove execution truth, exact VWAP truth, option quote/depth truth, slippage, fills, profitability, paper readiness, or live readiness.
