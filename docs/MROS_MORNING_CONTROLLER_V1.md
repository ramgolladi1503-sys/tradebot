# MROS Morning Controller V1

Run the read-only controller with an exact source SHA and frozen config and
instrument hashes:

```bash
python scripts/morning_controller.py --session-date YYYY-MM-DD
```

State is stored at `<state-root>/<session-date>/morning_controller_state.json`.
Optional configuration keys are `--state-root`, `--source-sha`,
`--config-sha`, `--instrument-sha`, and `--stage-evidence`; when omitted,
source/config identity is derived locally and missing instrument authority is
represented as `UNKNOWN_NO_CURRENT_INSTRUMENT_AUTHORITY`.
The command never invokes broker write, order, paper, or live-execution code.
It records `broker_api_called=false`, zero order counters, and remains
`live_authorized=false`.

Missing authentication evidence returns `WAITING_HUMAN_AUTH`; an operator must
complete the normal human authentication flow and rerun with independent stage
evidence. A missing market-data stage returns a partial session, not FULL.
Unchanged frozen inputs reuse completed stages. Changing source, configuration,
or instrument hashes invalidates the prior state and requires the dependent
evidence again. The controller does not turn static metadata into live proof.

Release certification is separate: use `scripts/release_manager.py certify`
with a one-to-one primitive manifest, then `verify`, then `promote`. Legacy
`pass:true` JSON and generic shared primitive files are rejected.

For an actual read-only readiness pass, add `--governor` plus the existing
governor's external-root/release-store/instrument options. The controller maps
that repository-owned plan into stages, but deliberately still blocks
`BROKER_READ`, websocket, market-data, and observer arming until their separate
runtime evidence artifacts exist. Readiness metadata is never promoted to live
verification.
