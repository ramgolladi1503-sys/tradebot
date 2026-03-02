# Feed Health State Machine

This module provides per-group market data health state for runtime safety gating.

## States

- `OK`: feed quality is healthy enough for execution.
- `DEGRADED`: feed is partially unhealthy; execution should be blocked (advisory can continue).
- `DOWN`: feed is unhealthy/unavailable; execution must be blocked.

## Per-Group Ownership

State is tracked independently by feed group key, for example:

- `INDEX:NIFTY`
- `INDEX:BANKNIFTY`
- `INDEX:SENSEX`
- `OPT:NIFTY`
- `OPT:BANKNIFTY`
- `OPT:SENSEX`

A degradation in one group must not force another group to degrade.

## Hysteresis Rules

The machine uses time windows to avoid noisy transitions:

- Downgrade requires sustained bad conditions for `downgrade_window_sec`.
- Upgrade requires sustained good conditions for `upgrade_window_sec`.
- Every transition also respects `min_hold_sec`.
- `DOWN -> DEGRADED` requires sustained recovery (`30s`) before allowing gradual return.

## Flap Lock

If transitions are too frequent within `flap_window_sec`:

- state is forced to `DEGRADED` (unless already `DOWN`),
- upgrades are blocked until `flap_lock_sec` expires,
- further deterioration to `DOWN` is still allowed.

## Running Tests

```bash
cd /Users/madhuram/tradebot
PYTHONPATH=. pytest -q tests/feed/test_feed_health_machine.py
```
