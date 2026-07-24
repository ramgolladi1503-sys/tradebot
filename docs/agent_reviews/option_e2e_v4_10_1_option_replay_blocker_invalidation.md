# v4.10.1 Option Replay Blocker Invalidation

Verdict: `INVALID_OPTION_REPLAY_BLOCKER_AS_SIGNAL_SOURCE_BLOCKER`

The v4.10.1 checkpoint correctly split blocker domains, but it still treated the legacy blocker-only slice as current execution evidence. That is not a real VWAP signal execution outcome.

Preserved:
- lane-scoped discovery
- worktree inventory and git commands
- no fake signal rows
- research-only and fail-closed behavior

Invalidated:
- using option replay blockers as signal-source blockers
- reusing `NO_SIGNAL_LEDGER_SOURCE` for current evidence
- tautological `SOURCE_BLOCKED` reconciliation as a proof of execution
- blocker records being treated as signal ledger rows
