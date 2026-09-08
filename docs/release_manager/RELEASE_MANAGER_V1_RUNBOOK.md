# Release Manager V1 runbook

The live release is a separately stored exact commit. `main` may advance while
the current certified pointer remains unchanged.

1. Initialize a new external release store only from independently verified
   historical evidence:
   `python3 scripts/release_manager.py init --state-root <external-state-root> --certified-sha <sha> --evidence-sha256 <sha256>`.
   This does not modify the frozen source checkout or prior evidence.
2. After a merge, certify the exact candidate SHA:
   `python3 scripts/release_manager.py certify --repo <repo> --state-root <external-state-root> --candidate <sha> --dependency-graph docs/release_manager/RELEASE_DEPENDENCY_GRAPH.json --gates <gate-results.json> --output <certification.json>`.
   Gate results are explicit booleans from separately reviewed evidence, not
   self-certified status.
3. Inspect the impact class, required gates, primitive evidence, and the
   independent verifier output. A failed or blocked candidate leaves the
   current certified SHA unchanged.
4. Promotion is a separate, explicit operation:
   `python3 scripts/release_manager.py promote --state-root <external-state-root> --certification <certification.json>`.
   Promotion requires an exact candidate SHA, matching current base, matching
   fallback, complete required gate pass set, and no failed gates. Never promote
   `main` implicitly.
5. Verify the pointer and optional certification result independently:
   `python3 scripts/release_manager.py verify --state-root <external-state-root> --repo <repo> --certification <certification.json>`.
6. At EOD, verify the session seal, then prepare the next-session artifact:
   `python3 scripts/release_manager_prepare_next_session.py --state-root <external-state-root> --session-date <date> --authority-artifact <authority.json> --output <next-session.json>`.
   A missing or non-PASS authority artifact blocks next-session readiness. A
   material instrument-authority change remains `INSUFFICIENT_EVIDENCE` until
   the required human review is recorded.
7. At morning launch, use
   `python3 scripts/morning_readiness_cli.py preflight --release-store-root <external-state-root> ...`
   or the existing explicit `--release <sha>` compatibility path. The launcher
   fails closed if release authority is absent, conflicting, or invalid.
8. Run the RM-specific mutation campaign:
   `python3 scripts/release_manager_mutation_campaign.py --output <artifact.json>`.
   This campaign covers Release Manager governance failures. It does not replace
   the existing Morning Readiness 18/18 mutation campaign.

This V1 task is offline and read-only. It does not launch a broker observer,
change credentials, grant order authority, or promote an operational release.
