# Opening Range Retest Causal Replay Phase 1

Scope:
`opening_range_retest_v1` signal-generation replay only.

Current status:
`AUDIT_INVALID`

Reason:
authoritative corpus replay and evidence generation not completed.

What changed:
- Added a research-only replay package under `research/opening_range_retest/`.
- The replay directly calls `strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates`.
- Source selection fails closed by default when the manifest-linked inventory file is unavailable.
- A bounded audit path validates the tracked JSON artifacts without rerunning the full corpus.

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

Tests added:
- `tests/test_opening_range_retest_causal_replay.py`

Run instructions:
```bash
cd /Users/madhuram/tradebot-opening-range-retest-causal-replay
pytest -q tests/test_opening_range_retest_causal_replay.py
python scripts/generate_opening_range_retest_causal_replay.py --limit-sessions 5 --allow-manifest-without-inventory
python scripts/audit_opening_range_retest_causal_replay.py
```

Rollout steps:
1. Run the targeted tests.
2. Run a bounded smoke replay with `--limit-sessions`.
3. If the smoke run is stable, run the full replay.
4. Audit the generated tracked artifacts.
5. Review the verdict and claim boundary before any follow-on Phase 2 work.

Migration notes:
- The current checked-in manifest records stale provenance paths from an older worktree.
- The authoritative inventory artifact for this task is the checked-in repository-relative file `docs/agent_reviews/upstox_corpus_inventory_v2.json` after sidecar and manifest-hash verification.
- Diagnostic fallback scanning is non-authoritative and cannot produce `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`.

Claim boundary:
- Phase 1 proves deterministic, causal signal generation over approved underlying-candle sources.
- Phase 1 does not prove execution truth, exact VWAP truth, option quote/depth truth, slippage, fills, profitability, paper readiness, or live readiness.
