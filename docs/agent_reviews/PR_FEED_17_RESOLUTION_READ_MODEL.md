# PR-FEED-17 Resolution Read Model Agent Review

mode: REVIEW
candidate_id: pr_feed_17_resolution_read_model
decision: review_ready
reason: resolution_read_model_tests_docs
timestamp: 2026-05-27T19:02:00Z
source: pr_feed_17_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers PR-FEED-17 only.

The PR adds pure, deterministic read-model helpers for feed selection evidence. It must not wire live websocket runtime behavior, write files, execute trades, place or modify orders, call broker APIs, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add pure read-model helper functions.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Runtime file writes.
- Instrument-cache reads.
- Live websocket callback rewiring.
- Hidden config or time calls inside the helper module.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The changed helper module has no broker imports, no execution imports, and no order-facing functions.

Question: Can this PR change live subscription behavior?

Answer: No. `core/kite_depth_ws.py` is not rewired in this PR. The helper surface is created first for deterministic testing.

Question: Can this PR call a broker or read instrument caches?

Answer: No. Callers must pass already-resolved observations explicitly. The helper only builds read-model payloads.

Question: Can invalid input silently become unsafe runtime state?

Answer: No. Invalid identifiers, exchange text, expiry values, ATM values, and option metadata normalize to deterministic defaults or explicit failure reasons.

## Hermes Review

The public helper contract is intentionally narrow:

- `OptionInstrumentMeta`
- `SymbolResolutionInput`
- `SymbolResolutionReadModel`
- `TokenResolutionReadModel`
- `normalize_symbol(...)`
- `normalize_exchange(...)`
- `expiry_key(...)`
- `infer_atm_strike(...)`
- `option_distance_rank(...)`
- `normalize_and_rank_option_tokens(...)`
- `option_fail_reason(...)`
- `selected_option_strikes(...)`
- `build_symbol_resolution_read_model(...)`
- `combine_symbol_resolution_models(...)`

These helpers are pure value transforms. Callers must pass observations explicitly.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No filesystem writes.
- No logging side effects.
- No runtime mutation.
- Invalid optional values normalize to deterministic defaults.

## QA / Safety Review

Focused test coverage includes:

- symbol normalization
- exchange defaults
- expiry parsing
- ATM inference
- option rank ordering
- selected strike evidence
- two-sided strike evidence
- explicit failure reasons
- under-min option behavior
- index preservation
- per-symbol row construction
- global model combination
- count maps and payload shape

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_17_resolution_read_model.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire these helpers into `core/kite_depth_ws.py` only if explicitly scoped. That later PR must prove:

- existing per-symbol resolution rows remain backward-compatible
- existing option count fields remain backward-compatible
- underlying identifier mapping remains preserved
- exchange hints remain preserved
- failure reasons remain compatible
- no broker/order side effects are introduced

## What This PR Does Not Prove

This PR does not prove live discovery, subscription correctness, websocket recovery, broker connectivity, execution quality, or profitability. It only proves a deterministic read-model surface for future feed refactors.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with PR-FEED-18 only from the latest merged main commit.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
