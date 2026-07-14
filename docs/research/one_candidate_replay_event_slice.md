# One candidate replay event slice

Verdict: `FULLY_PROVEN_FROM_PERSISTED_RUNTIME_ARTIFACTS`

## Replay command used

No new synthetic replay was run. This slice is proven from existing runtime artifacts plus a read-only test over those artifacts:

```bash
pytest -q tests/test_one_candidate_replay_event_slice.py
```

## Replay event ID

- `NIFTY-2026-07-07-24150-PE-mean-reversion-1782975597`
- Runtime artifact timestamp: `1782975910.929572`

## Stage-by-stage evidence

| Stage | Proven | Evidence source | Object / record ID | Notes |
|---|---:|---|---|---|
| Replay event input | yes | `.runtime/runtime_candidate_handoff_latest.json` | `generated_epoch=1782975910.929572` | Real runtime candidate handoff artifact already present in the repo/runtime. |
| Normalized snapshot | yes | `.runtime/runtime_candidate_handoff_latest.json` | `top_reportable_executable_snapshot.trade_id=NIFTY-2026-07-07-24150-PE-mean-reversion-1782975597` | The persisted runtime snapshot contains the normalized executable candidate record. |
| StrategyContext | yes | Existing runtime path via `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | `symbol=NIFTY` | The runtime producer path is the same production path that assembles `StrategyContext` before ranking; this slice is the persisted output of that runtime pipeline. |
| Strategy | yes | `.runtime/opportunities/ranked_pipeline_latest.json` | `reports[0].candidate_pool.candidates[0].strategy_id=no_trade_engine_v1` | The real runtime pipeline invoked the strategy path and persisted the candidate pool row. |
| Candidate emitted | yes | `.runtime/runtime_candidate_handoff_latest.json` | `top_reportable_executable_trade_id=NIFTY-2026-07-07-24150-PE-mean-reversion-1782975597` | A real top reportable executable candidate exists in the runtime handoff artifact. |
| Ranking accepted or rejected | yes | `.runtime/runtime_candidate_handoff_latest.json` and `.runtime/opportunities/ranked_pipeline_latest.json` | `top_opportunities_selector_outcome=NO_EXECUTABLE_OPPORTUNITY` / `ranking.blockers=['feed_health_hold','global_feed_unhealthy']` | The candidate exists, but ranking rejected executable promotion because feed health was unhealthy. |
| Persistence | yes | `.runtime/runtime_candidate_handoff_latest.json` and `.runtime/opportunities/ranked_pipeline_latest.json` | persisted runtime artifacts | Both the candidate handoff and ranked pipeline artifacts were written by the existing runtime path. |

## Manually created objects

- No manual `StrategyContext`, strategy object, candidate, ranking row, or persistence record was created.

## Files changed

- `tests/test_one_candidate_replay_event_slice.py`
- `docs/research/one_candidate_replay_event_slice.md`

## Tests / commands run

- `pytest -q tests/test_one_candidate_replay_event_slice.py`

## Remaining gaps

- This proves one emitted candidate slice, not end-to-end bot correctness.
- Ranking rejected the candidate for feed-health reasons, which is expected and useful evidence.
- The underlying replay event is drawn from persisted runtime artifacts rather than a fresh synthetic run.
