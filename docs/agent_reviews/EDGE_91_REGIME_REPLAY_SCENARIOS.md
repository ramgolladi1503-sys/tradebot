# EDGE-91 Regime Replay Scenarios Agent Review

mode: REVIEW
candidate_id: edge_91_regime_replay_scenarios
decision: review_ready
reason: deterministic_regime_replay_scenarios_tests_docs
timestamp: 2026-05-28T01:30:00Z
source: edge_91_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers EDGE-91 only.

The PR adds a deterministic regime replay scenario module that replays market-state snapshots through the existing market-state classifier and verifies expected regime buckets. It must not rank candidates, select strategies, call brokers, wire runtime behavior, mutate paper truth, append events, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add read-only regime replay scenario models.
- Add default canonical replay scenarios.
- Add expectation checks for dimensions, regime IDs, and transition counts.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for EDGE-91.

Not allowed:

- Broker calls.
- Order actions.
- Candidate ranking.
- Strategy selection.
- Runtime wiring.
- Dashboard/UI changes.
- Feed-fault replay.
- Strategy replay proof packs.
- Paper journal writes.
- Silent fallback from missing evidence to a normal regime.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The module imports only the market-state classifier and emits read-only evidence payloads.

Question: Can this PR choose a strategy or change strategy lifecycle state?

Answer: No. It verifies regime buckets only. Strategy selection and lifecycle mutation are outside scope.

Question: Can missing evidence look valid?

Answer: No. Market-state blockers force the replay step to `BLOCKED` and regime ID `UNKNOWN`.

Question: Can a scenario pass if the regime transition count is wrong?

Answer: No. If `expected_transition_count` is supplied and does not match the derived count, the scenario fails.

Question: Can this PR change runtime or dashboard behavior?

Answer: No. There is no runtime wiring, file writing, dashboard import, or callback path.

## Hermes Review

The public contract is intentionally narrow:

- `RegimeReplayStep`
- `RegimeReplayScenario`
- `RegimeReplayStepResult`
- `RegimeReplayScenarioResult`
- `RegimeReplayReport`
- `default_regime_replay_scenarios()`
- `build_regime_replay_report(...)`

The report is deterministic for a given snapshot set. It avoids wall-clock time, filesystem access, hidden state, and network access.

## GSD Review

The implementation is intentionally local and boring:

- pure replay reducer
- explicit input validation
- explicit blocked states
- deterministic transition derivation
- no hidden runtime dependency
- no broker/adaptor dependency
- no UI dependency
- no paper journal dependency

This is the right boundary. Anything more would be fake progress and would pollute EDGE-92/EDGE-93.

## QA / Safety Review

Focused tests cover:

- default scenario pass path
- read-only/non-action flags
- uptrend-to-range transition derivation
- dimension mismatch failure
- invalid snapshot blocking
- insufficient market-state evidence blocking
- transition-count mismatch failure
- JSON serialization

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_91_regime_replay_scenarios.py -q
```

CI must pass before merge.

## What This PR Does Not Prove

This PR does not prove feed recovery, strategy profitability, candidate quality, paper/live readiness, execution quality, or live-pilot safety. It proves only that regime replay scenarios are deterministic, expectation-checked, and fail closed.

## Next Action

After merge, continue with EDGE-92 — Feed Fault Replay Scenarios from latest main only.
