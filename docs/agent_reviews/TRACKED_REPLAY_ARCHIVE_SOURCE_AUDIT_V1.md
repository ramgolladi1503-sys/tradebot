mode: RESEARCH_ONLY_SOURCE_AUDIT
candidate_id: tracked_replay_archive_source_audit_v1
decision: TRACKED_REPLAY_ARCHIVE_INSPECTED_NON_CANONICAL
reason: The exact tracked replay ZIP is a valid replay-input archive with 1,150 content parquet files and 661 source manifests, but it contains no signal-like member and does not establish canonical signal or dataset authority; local trace and root inspection remain incomplete.
timestamp: 2026-07-25T23:50:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: runtime/upstox_candidate_replay.zip at SHA-256 4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707; workflow run 30170593227; artifact 8622806227; compact and oracle evidence with verified SHA-256 sidecars

# Tracked Replay Archive Source Audit v1

## Agent Work Contract

- source_agent: ChatGPT
- action: GENERATE_PATCH
- title: Audit the tracked Upstox replay archive as one unique source
- scope: Research-only ZIP integrity, member inventory, deny-boundary enforcement, independent oracle, deterministic evidence, and compact publication
- allowed_paths: Focused archive-audit package, focused tests, this review, generated evidence, changed-scope reports, and temporary workflows removed before publication
- forbidden_paths: Strategy runtime, broker, order, execution, feed, risk, dashboard, outcomes, P&L, replay execution, WFA, holdout evaluation, and live or paper configuration
- expected_tests: Focused archive security tests plus repository-required exact-head checks
- acceptance_proof: Exact archive hash, safe member inventory, AppleDouble separation, primary-oracle agreement, two byte-identical builds, matching sidecars, and zero execution authority

## Scope Guard

This work audits only the repository-tracked `runtime/upstox_candidate_replay.zip`, previously represented by 23 exact-content copies in the source census. It does not inspect the Mac-only execution trace or claim that the 27 declared local roots have been exhausted. It does not extract archive members into the repository or execute the replay.

## Grill Me Review

Archive validity and deterministic bytes are not authority. A replay bundle can be useful input while still lacking dataset-version ownership, strategy ownership, implementation and parameter binding, causal timestamps, split/fold identity, pre-outcome freeze, and contamination clearance. The audit therefore rejects any promotion based on filenames, member count, parseability, or provider labels alone.

## Hermes Review

The primary inspector owns member safety, deny-boundary enforcement, content classification, and compact publication. A separate oracle independently recomputes the archive hash, physical size, ZIP validity, name uniqueness, metadata/content partition, file/directory counts, and safety flags. The evidence builder refuses publication on disagreement.

## GSD Review

The implementation remains narrow: one frozen archive, one focused audit package, one focused test file, one compact evidence set, and temporary workflows removed before final publication. It does not create a generic source framework, alter the existing authority closure, or introduce runtime behavior.

## Frozen Input

- archive path: `runtime/upstox_candidate_replay.zip`
- physical SHA-256: `4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707`
- physical size: `33,892,991` bytes
- prior exact-copy count: `23`
- unique archive source count: `1`

## Archive Safety

The archive is a valid ZIP. The audit found no duplicate member names, case-colliding names, traversal paths, absolute paths, backslash paths, symlinks, special files, or encrypted members. No member was extracted into a worktree.

Outcome- and P&L-bearing member names are denied before content open. The audited archive contained zero denied outcome members. Safety fields remain `outcomes_read=false`, `pnl_read=false`, and `holdout_outcomes_read=false`.

## AppleDouble Metadata Separation

The first evidence run exposed that macOS `__MACOSX` and `._*` entries could double-count source content. Publication was stopped and the implementation repaired before evidence was committed.

Final member accounting:

- total ZIP members: `8,402`
- AppleDouble/archive metadata members: `4,201`
- content-tree members: `4,201`
- content files: `1,811`
- content directories: `2,390`
- content members opened read-only: `1,811`
- archive metadata members opened: `0`

The independent oracle recomputed these counts without consuming the primary decision object.

## Content Inventory

The content tree contains:

- market-data parquet members: `1,150`
- option-like parquet members: `126`
- source manifest members: `661`
- represented date directories: `661`
- dates with parquet members: `521`
- signal-like members: `0`
- denied outcome-bearing members: `0`

The archive is therefore classified `ARCHIVE_REPLAY_INPUT_ONLY`.

## Authority Decision

- canonical signal source count: `0`
- canonical dataset source count: `0`
- replacement signal ledger required: `true`
- source-search completion: `INCOMPLETE_LOCAL_ROOTS_NOT_INSPECTED`

Parseability, archive determinism, and replay utility do not establish source ownership, dataset-version authority, strategy ownership, implementation binding, parameter binding, causal timestamps, split/fold identity, pre-outcome freeze, or contamination clearance.

## Primary and Oracle Agreement

The independent oracle agrees on:

- archive hash
- physical size
- ZIP validity
- total member count
- archive metadata count
- content-tree count
- content-file count
- content-directory count
- safety flags

Final status: `AGREEMENT`.

Member-name manifest SHA-256:

`ecc246569e2bb9c3b5a645bb6c1674f1f53ee29ab2e8e97f871a857f808f34ec`

## Determinism and Evidence

Workflow run `30170593227` built the evidence twice and required a recursive byte-for-byte directory diff to pass.

Workflow artifact:

- artifact ID: `8622806227`
- artifact digest: `sha256:0a38e20e54e4c18b7f5353aa96c25f534f8e538aef5f59dee1b0ca61333675b3`

Evidence hashes:

- full member audit: `f9c4d7b92deb45bae64fb3b9bc3eabdfef516864a9eb6988c5a5042fc65aa2d9`
- compact audit: `d31b5b4b0b350892f2438c9d7a130ca9469cc3f8011986fa12ad0e32ef728a49`
- independent oracle: `d12ab40cb77a18e8f14915fa00ba7359b5ca67a4e254a5f91d9b7952ea4a65ea`
- summary: `0242860bf1c090a19db0b9c103ad8fd3e315427e88f1b41fda14dbfd4df3c4d4`
- external manifest: `fe9078f4692b0911a260b13352f492d4a1a48e7a68f0a4cd129f33402377bae0`
- full member-registry semantic hash: `ee7ca7e9ef6e00114baca84fdf1f6e60a40aabb02583bc027eed641c7fdc7b43`
- content-path manifest hash: `c32a57ec1c4201045c48025cdd96d713c24f29df0f74b18626240a16ea8dd0d4`

Every committed JSON sidecar was independently rehashed before publication.

## Negative Controls

Ten focused tests cover conservative classification, wrong physical hash, traversal, symlink members, outcome/P&L deny behavior, AppleDouble non-open behavior, option-file de-duplication, primary/oracle reconciliation, semantic determinism, and compact hash-bound publication.

## QA / Safety Review

- `research_only=true`
- `read_only=true`
- `broker_api_called=false`
- `is_order_action=false`
- `allowed_for_live_execution=false`
- `outcomes_read=false`
- `pnl_read=false`
- `holdout_outcomes_read=false`

No runtime, broker, order, feed, risk, dashboard, outcome, P&L, replay, WFA, holdout, paper, or live behavior changed.

## Acceptance Proof

- exact archive physical hash: verified
- safe ZIP and member-name contract: passed
- focused tests: `10 passed`
- two evidence builds: byte-identical
- primary/oracle: `AGREEMENT`
- compact/full cryptographic binding: passed
- committed sidecars: passed
- canonical signal sources: `0`
- canonical dataset sources: `0`
- final disposition: `ARCHIVE_REPLAY_INPUT_ONLY`

Permanent exact-head repository checks must pass after all temporary workflows are removed. Temporary diagnostic or evidence workflows are not treated as the final branch gate.

## Runtime Proof Required After Merge

None. This audit creates no runtime path and grants no execution authority.

## Remaining Source Gaps

The remaining known unique source is:

`MAIN_TRADEBOT:.runtime/logs/execution_entry_trace.jsonl`

The 27 declared local roots also remain unexhausted. Those inputs are not accessible from the GitHub runner and were not inspected here. Full source-search completion remains blocked.

## What This PR Does Not Prove

This work does not prove a canonical signal source, canonical dataset source, strategy correctness, dataset-version authority, parameter authority, contamination clearance, profitability, replay validity, WFA validity, paper readiness, or live readiness. It does not complete the local source search.

## Human Approval

Human approval remains required before replacement-ledger generation or any later authority decision. The archive result narrows one unique source; it does not authorize execution or remove the remaining local-source gaps.
