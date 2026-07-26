mode: RESEARCH_ONLY_LOCAL_SOURCE_AUDIT_HARNESS
candidate_id: local_unresolved_source_audit_v1
decision: LOCAL_AUDIT_HARNESS_READY_REAL_INPUT_EXECUTION_NOT_PERFORMED
reason: PR #713 resolved the tracked replay archive, leaving one Mac-local execution trace and 27 declared local roots. This change creates a deterministic fail-closed harness for those inputs without claiming that inaccessible files were inspected.
timestamp: 2026-07-26T08:15:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
source: merged PR #713 at 49beef400c39d45a69c7fd587172032cf0a650e1; unresolved source authority summary; core execution-entry trace writer contract

# Local Unresolved Source Audit v1

## Agent Work Contract

- source_agent: ChatGPT
- action: GENERATE_PATCH
- title: Prepare a fail-closed audit for the remaining Mac-local source gaps
- scope: Streamed execution-trace inspection, exact non-overlapping declared-root census, candidate hashing, outcome/P&L metadata-only handling, frozen operational-directory exclusions, duplicate grouping, independent oracle, deterministic evidence publication, and synthetic negative controls
- allowed_paths: Focused research package, focused tests, this review, and changed-scope Code Excellence input
- forbidden_paths: Runtime strategy behaviour, broker, orders, execution decisions, feed, risk, dashboard, live configuration, paper configuration, outcome evaluation, P&L evaluation, replay execution, WFA, and holdout analysis
- expected_tests: Trace schema and safety controls, root-count enforcement, no candidate limit, in-scope symlink failure, operational-tree exclusion, deny-boundary non-open proof, root-overlap rejection, output isolation and cleanliness, duplicate grouping, primary/oracle agreement, deterministic evidence, and non-authority guarantees
- acceptance_proof: Synthetic tests pass and permanent PR checks pass; real Mac-local execution remains a separate evidence step

## Scope Guard

This PR creates only the audit mechanism. It does not read `/Users/madhuram/tradebot/.runtime/logs/execution_entry_trace.jsonl`, discover the current local worktree registry, or scan the 27 declared roots because those inputs are not available to the GitHub connector or hosted runner. No generated real-input evidence is committed.

The CLI requires exactly 27 unique, non-overlapping `ROOT_ID=PATH` bindings by default and performs an exhaustive sorted in-scope walk with `candidate_limit=null`. It fails closed when a declared root is absent or unreadable, when physical roots are duplicated or nested, or when in-scope symlinks and special filesystem entries prevent exhaustive inspection. Every permitted source-authority candidate selected by the frozen policy is content-hashed.

The only excluded directory names are `.git`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, and `node_modules`. These operational trees are not descended into. Their encountered relative paths and counts are independently manifest-hashed so the exclusion application remains auditable.

A source-authority path carrying outcome, P&L, holdout-result, forward-return, or post-trade markers is recorded by identity and size only. Its content is never opened, its SHA-256 remains null, and the final authority-source status remains incomplete pending a separate approved review.

Evidence output is required to live outside every declared root and to begin absent or empty. The builder validates both boundaries before writing, preventing Run A artifacts or stale files from contaminating a later census.

## Grill Me Review

A parser can create false confidence if it merely counts lines. The trace lane therefore verifies the physical SHA-256, bounds line size, requires UTF-8 object JSONL, validates timestamp/module/stage fields, computes a canonical semantic stream hash, recursively checks key names against an outcome/P&L deny boundary, and publishes only aggregates rather than trade IDs or row values.

A root scanner can also create false confidence if it truncates, follows aliases, double-counts nested roots, silently ignores environment trees, or writes evidence into its own input corpus. This implementation has no candidate limit, rejects duplicate and overlapping physical roots, records every applied directory exclusion, does not follow in-scope symlinks, inventories every in-scope regular file by relative path and size, hashes every permitted candidate selected by the frozen source policy, and blocks self-referential or stale output directories.

## Hermes Review

The primary implementation owns detailed trace aggregates, per-root inventories, permitted candidate content hashes, metadata-only denied records, exclusion manifests, and exact-duplicate groups. A separately implemented oracle re-parses the trace and independently walks the roots, then reconciles physical trace hash, semantic stream, timestamp range, key manifest, root/file/directory counts, exclusion names/counts/path manifest, the complete file-identity manifest, candidate content identities, denied-candidate counts, completion flags, and safety flags.

Oracle agreement is necessary but not sufficient for source authority. The output always retains canonical signal and dataset source counts at zero and requires human authority review for every discovered candidate.

## GSD Review

The implementation is deliberately narrow and uses the existing option-E2E research namespace. It does not introduce a second runtime census service, database, scheduler, or generic filesystem framework. The package consists of a trace inspector, a declared-root scanner, an independent oracle, and one deterministic evidence builder.

The first real local run should use two independent clean output directories outside all scanned roots and a recursive byte comparison before any compact publication or authority-closure update is considered.

## QA / Safety Review

Negative controls cover malformed JSONL, oversized records, trace outcome/P&L field rejection, root candidate metadata-only deny behaviour, in-scope symlink rejection, virtual-environment exclusion, exact root-count enforcement, overlapping-root rejection, self-referential output rejection, non-empty output rejection, duplicate-content grouping, absolute-path non-publication, primary/oracle agreement, byte-identical builds, sidecar binding, and permanent zero execution authority.

Safety invariants:

- `research_only=true`
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `outcomes_read=false`
- `pnl_read=false`
- `holdout_outcomes_read=false`
- trace record values are not published
- absolute local paths are not published
- denied candidate content is not opened
- frozen operational exclusions are manifest-bound
- nested declared roots are rejected
- evidence output cannot be placed inside an audited root
- evidence output cannot contain pre-existing files
- canonical authority is never granted automatically

## Acceptance Proof

Local synthetic validation before publication:

- focused tests: `15 passed`
- Python compilation: passed
- trace values absent from published aggregate evidence: passed
- denied root candidate content-open guard: passed
- operational-directory exclusion with internal symlink: passed
- overlapping declared-root rejection: passed
- output-inside-root rejection before mutation: passed
- non-empty output rejection without mutation: passed
- exact duplicate grouping: passed
- candidate limit: `null`
- deterministic two-directory evidence: passed
- independent oracle: `AGREEMENT`
- independent exclusion manifest: reconciled
- independent candidate-content manifest: reconciled
- independent complete file-identity manifest: reconciled
- denied-candidate count and non-read flags: reconciled

Repository CI and Code Excellence must still pass on the exact PR head. The real trace and all 27 roots must be supplied on the Mac before source-search completion can change from incomplete.

## Runtime Proof Required After Merge

Run the harness from a dedicated campaign worktree with the real trace and exactly 27 unique, non-overlapping declared roots. Keep evidence output outside every audited root and delete any prior output directories before starting:

```bash
rm -rf /tmp/tradebot-local-source-audit-v1/run-a /tmp/tradebot-local-source-audit-v1/run-b
python -m research.option_e2e_recertification_v4.local_unresolved_source_audit_v1.build_evidence \
  --trace /Users/madhuram/tradebot/.runtime/logs/execution_entry_trace.jsonl \
  --root CURRENT_WORKTREE=/path/to/dedicated/campaign-worktree \
  --root MAIN_TRADEBOT=/Users/madhuram/tradebot \
  --root TRADEBOT_DATA=/path/to/tradebot-data \
  --root TRADEBOT_ML_EVIDENCE=/Users/madhuram/tradebot-ml-evidence \
  --root REGISTERED_WORKTREE_001=/path/to/worktree-001 \
  ... \
  --root REGISTERED_WORKTREE_025=/path/to/worktree-025 \
  --expected-root-count 27 \
  --output-dir /tmp/tradebot-local-source-audit-v1/run-a
```

Repeat into `/tmp/tradebot-local-source-audit-v1/run-b`, compare the directories byte-for-byte, independently review all discovered candidates, and only then copy an approved compact, hash-bound publication into durable evidence storage. Any metadata-only denied record keeps authority-source completion blocked until separately reviewed under an approved outcome boundary.

## What This PR Does Not Prove

This work does not prove that the remaining trace is non-canonical, that the 27 roots contain no additional signal or dataset sources, that source search is complete, that a replacement signal ledger exists, or that any strategy is correct, profitable, replay-valid, WFA-valid, paper-ready, or live-ready.

It also does not implement the separate UI ranking and fallback-execution changes described in the UI issue note; those production-facing concerns remain outside this research-only source-audit lane.

## Human Approval

Human review remains required after the real local run because candidate discovery and exact duplicate grouping do not establish strategy ownership, implementation binding, parameter authority, dataset-version authority, causal timing, pre-outcome freeze, split identity, or contamination clearance.
