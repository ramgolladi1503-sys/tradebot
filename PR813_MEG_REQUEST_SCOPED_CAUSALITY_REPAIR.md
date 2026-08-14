# MEG request-scoped causality repair

Base: `2dfaac69937f2de173130327e09a976e015af0bd`.

Repaired `core/meg_request_scoped_causality.py` so `wrong_generation_ticks` remains diagnostic but no longer participates in `PASS_MEG_REQUEST_SCOPED_CAUSALITY`. Canonical session, lineage, integrity, symbol, causal-timestamp, and persistence checks remain authoritative.

Pre-repair defect reproduced: mismatched `selected_tick_reconnect_generation` produced `wrong_generation_ticks=1` and blocked PASS.

Post-repair attacks:

- legacy veto: passes with mismatched generation;
- legacy rescue: stale canonical evidence still rejects;
- forged legacy value: canonical result unchanged;
- cross-session protection: preserved by existing canonical/session checks;
- future generation: cannot authorize provenance.

No live, broker, order, or main-merge activity.
