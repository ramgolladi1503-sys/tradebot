# MEG live-observation readiness runbook

This runbook is read-only and does not authorize orders, paper trading, or live trading.

After controlled shutdown and writer drain:

```bash
python3 scripts/seal_pr763_read_only_evidence.py --evidence-root <SEALED_SESSION_ROOT>
python3 scripts/verify_meg_request_scoped_causality_v1.py --evidence-root <SEALED_SESSION_ROOT>
```

The #803 verifier returns `0` only for `PASS_MEG_REQUEST_SCOPED_CAUSALITY`,
`1` for FAIL, and `2` for incomplete evidence. The root argument is explicit;
there is no implicit latest-session selection.

The repository currently has no canonical #786, #782, or #783 post-market CLI
in this checkout. Those commands must be added or identified before a final
READY freeze; this document intentionally does not invent them.
