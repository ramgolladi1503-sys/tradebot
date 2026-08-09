# MEG live-observation readiness runbook

This runbook is read-only and does not authorize orders, paper trading, or live trading.

Post-market authority is one session root and one producer SHA:
`ONE_SESSION_ROOT`, `ONE_PRODUCER_SHA`, `NO_MIXED_EVIDENCE`.

After controlled shutdown and writer drain:

```bash
python3 scripts/seal_pr763_read_only_evidence.py --evidence-root <SEALED_SESSION_ROOT>
python3 scripts/verify_meg_request_scoped_causality_v1.py --evidence-root <SEALED_SESSION_ROOT>
python3 scripts/run_ai_reliability_pr763_session.py \
  --evidence-root <SEALED_SESSION_ROOT> \
  --authority-snapshot <AUTHORITY_SNAPSHOT_PATH> \
  --output-dir <PR782_OUTPUT_DIR>
python3 scripts/assemble_meg_shadow_system_certificate.py \
  --offline-report <OFFLINE_REPORT.json> \
  --post-market-certificate <PR782_OUTPUT_DIR>/pr763_post_market_reliability_certificate.json \
  --output-dir <PR783_OUTPUT_DIR>
```

The #803 verifier returns `0` only for `PASS_MEG_REQUEST_SCOPED_CAUSALITY`,
`1` for FAIL, and `2` for incomplete evidence. The root argument is explicit;
there is no implicit latest-session selection.

PR #786 has no distinct verifier authority. Its evidence obligations are the
canonical seal markers, authority snapshots, and append-only MEG ledgers. They
are consumed by the #782 reliability verifier and the #783 certificate
assembler; no `POSTMARKET_786_VERIFY_COMMAND` is valid.

Authoritative order:

1. controlled shutdown and writer drain;
2. `seal_pr763_read_only_evidence.py`;
3. #803 request-scoped causality verifier;
4. #782 reliability verifier;
5. #783 certificate assembler.

The live-session entrypoint is:

```bash
python3 scripts/run_market_event_graph_live_session_v1.py \
  --session-date <YYYY-MM-DD> \
  --output-root <EVIDENCE_ROOT> \
  --kite-instruments-file runtime/reference/market_event_graph/kite_instruments/kite_nse_instruments_828c0c378e493972.json
```

The preflight-only form adds `--preflight-only`; status is obtained from the
session evidence/status files under the explicit output root. Controlled
shutdown is the runtime's governed stop path, followed by the seal command
above. No minimum duration is defined by the repository; stop normally after
the required observation interval evidence is complete, or immediately on a
read-only safety/feed/space violation. Stop if free space drops below 10 GiB.
