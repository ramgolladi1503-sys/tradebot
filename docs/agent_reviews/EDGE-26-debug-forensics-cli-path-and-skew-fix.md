# EDGE-26 — Debug Forensics CLI Path and Timestamp Skew Fix

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-26-debug-forensics-cli-path-and-skew-fix
- decision: FIX_DEBUG_FORENSICS_CLI_PATH_AND_MINOR_TIMESTAMP_SKEW
- reason: The first post-merge debug forensics run exposed two tool-readiness defects: direct CLI execution could not import project modules, and sub-second timestamp jitter invalidated otherwise useful startup evidence.
- timestamp: 2026-05-21T19:30:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-26-debug-forensics-cli-path-and-skew-fix.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: #183
- Branch: edge26-debug-forensics-cli-path-fix
- Scope: fix debug forensics CLI execution and evidence-reader tolerance for tiny timestamp skew.
- Allowed files:
  - scripts/debug_forensics.py
  - core/debug_forensics/evidence_reader.py
  - docs/agent_reviews/EDGE-26-debug-forensics-cli-path-and-skew-fix.md
- Forbidden files:
  - strategies/
  - dashboard/
  - core/execution_engine.py
  - core/order_reconciliation_daemon.py
  - core/kite_depth_ws.py
  - config/
- Forbidden behaviors:
  - No strategy changes.
  - No feed/WebSocket changes.
  - No dashboard changes.
  - No broker/session changes.
  - No runtime trading behavior changes.
  - No evidence schema rewrite.
  - No architecture rewrite.

## Scope Guard

Verdict: PASS

Checked:

- CLI change only adds repository-root import bootstrap.
- Evidence-reader change only downgrades tiny timestamp skew to warnings.
- Existing report contract remains intact.
- Existing profile behavior remains intact.
- Existing run_id, boot_epoch, schema-version, malformed JSON, and unsafe evidence checks remain intact.

Blocking issues: none.

## Grill Me Review

Verdict: PASS_WITH_LIMITATION

Hard challenge:

1. The first CLI command failed because the script depended on caller environment. That is bad tooling.
   - Fix: insert repo root into sys.path before project imports.
2. The evidence validator treated a half-millisecond timestamp jitter as fatal. That is unrealistic for real runtime logs.
   - Fix: downgrade tiny skew to warning while preserving hard failure for larger ordering corruption.
3. The tool still reports the same real boundary: market-data warmup seed started but seed completion is not proven.
   - Constraint: this PR must not diagnose or fix warmup itself.

Remaining limitation:

- The next diagnostic PR still needs to inspect market-data warmup seed completion. This PR only fixes the forensics tool quality.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. CLI bootstrap is local to the script and does not affect package modules.
2. Timestamp tolerance is centralized in the evidence reader.
3. Minor timestamp skew becomes a validation warning, so the report remains useful.
4. Major timestamp reversal remains a validation error.
5. No new profile system or alternate report format is introduced.

Why this is not overengineering:

- A script advertised as runnable must run without manual PYTHONPATH setup.
- A forensics reader must handle tiny real-world timestamp jitter without throwing away all evidence.

## GSD Review

Verdict: PASS

Execution plan:

1. Add repository-root bootstrap in scripts/debug_forensics.py.
2. Add minor timestamp skew threshold in core/debug_forensics/evidence_reader.py.
3. Preserve hard validation for major ordering corruption.
4. Add mandatory agent review evidence for this fix PR.
5. Let CI verify agent evidence, code excellence, repo forensics, and unit checks.

## QA / Safety Review

Tests/commands required:

```bash
python scripts/debug_forensics.py --profile startup
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected behavior:

1. CLI runs from repo root without PYTHONPATH.
2. Sub-second timestamp skew appears as a warning, not an evidence validation error.
3. The report still includes the first missing startup boundary.
4. Unsafe evidence still fails closed.
5. Mixed run identity and mixed boot epoch still fail closed.

## Acceptance Proof

Acceptance criteria:

1. Agent Review Evidence Gate passes.
2. Code Excellence Gates pass.
3. Existing CI checks pass.
4. Local command works after merge:

```bash
python scripts/debug_forensics.py --profile startup
```

5. Report continues to identify the real startup boundary instead of failing only because of tiny timestamp jitter.

## Runtime Proof Required After Merge

After merge, run:

```bash
git checkout main
git pull --ff-only origin main
python scripts/debug_forensics.py --profile startup
```

Expected result:

```text
No ModuleNotFoundError for core.
Tiny timestamp skew does not invalidate evidence.
Report still shows last_confirmed_event and first_missing_event.
```

The expected current diagnostic boundary remains:

```text
last_confirmed_event = MARKET_DATA_WARMUP_SEED_STARTED
first_missing_event = MARKET_DATA_WARMUP_SEED_COMPLETED
```

## What This PR Does Not Prove

1. It does not prove market-data warmup is healthy.
2. It does not fix market-data warmup seed completion.
3. It does not change strategy, feed, dashboard, broker, or risk behavior.
4. It does not prove profitability.
5. It does not add new runtime probes.
6. It does not replace the planned architecture documentation PR.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
