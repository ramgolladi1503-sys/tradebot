# Strategy Replay Foundation

## Scope

- `research/strategy_replay/__init__.py`
- `research/strategy_replay/common.py`
- `research/strategy_replay/git_state.py`
- `research/strategy_replay/merge.py`
- `tests/test_strategy_replay_common.py`
- `tests/test_strategy_replay_merge.py`

## Why

The ORB replay branch proved deterministic replay semantics, but those helpers remained strategy-specific. This foundation extracts the reusable research-only spine needed by later strategy replay lanes without modifying the certified ORB package.

## What changed

- Added canonical JSON and SHA-256 helpers for deterministic artifact and ledger hashing.
- Added canonical session-key and shard-assignment helpers using `sha256(canonical_session_key) mod shard_count`.
- Added clean-worktree capture with fail-closed rejection for dirty checkouts.
- Added artifact bundle writing/loading with `.sha256` sidecars and evidence-envelope validation.
- Added strict shard merge validation for shard coverage, duplicate detection, mixed code/profile/manifest identity rejection, source-universe recomputation, and candidate-hash recomputation.

## Safety boundary

- Research-only code path.
- No broker imports.
- No order actions.
- No runtime strategy wiring.
- No strategy parameter or threshold changes.

## Tests

- `pytest -q tests/test_strategy_replay_common.py tests/test_strategy_replay_merge.py`

## Remaining gaps

- This checkpoint does not yet wire any strategy to the new foundation.
- Artifact field naming still needs strategy-local adaptation in downstream replay lanes.
