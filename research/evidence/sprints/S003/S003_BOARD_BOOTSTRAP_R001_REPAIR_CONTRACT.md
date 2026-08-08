# MROS S003 — Review/Audit Board Bootstrap R001 Repair Contract

Status: REPAIR_REQUIRED
Authority: Research / R
Runtime authority: NONE
M9: NOT_STARTED

## Frozen failed candidate

`5c7c0d6a75e6b8b56362011fb89b66efa29a64b3`

Native calibration evidence for that candidate was 24/24 PASS, Python 3.12.2, exit 0. The independent bootstrap review round nevertheless found material fail-open paths. Native green did not override review findings.

## Independent population

Ten isolated Mac Git-mailbox Codex jobs R01–R10 were launched against the exact failed candidate. R07 and R09 returned PASS. The remaining reviews contained blocking findings.

Aggregate blocker counts from the preserved R001 artifacts:

- CRITICAL: 10
- MAJOR: 17
- MINOR: 0
- mandatory UNKNOWN: 0

Any single CRITICAL or MAJOR is sufficient to block; simple majority is forbidden.

## Blocking classes and mandatory repair

1. Calibration/native circularity and exact-head anchoring
   - deterministic calibration must not manufacture certifying native/review/audit authority;
   - calibration requires an externally supplied expected HEAD and fails on mismatch;
   - exact native execution remains a separate Mac-bridge evidence step.

2. Native evidence integrity
   - strict typed schema;
   - exact repository/branch/HEAD/validator/command binding;
   - exact check/pass/fail/exit counts;
   - content-addressed source output SHA-256;
   - execution-job and receipt references;
   - runtime authority NONE and broker actions NONE.

3. Majority masking / dissent preservation
   - any non-PASS verdict blocks or requires adjudication;
   - verdict-only UNKNOWN remains blocking;
   - CRITICAL/MAJOR cannot be outvoted;
   - all valid dissent artifacts remain in aggregates.

4. Genuine isolated execution evidence
   - review/audit schema binds execution_role_id, execution_job_id, packet/output paths and Mac Git-mailbox transport;
   - matching successful worker receipt is mandatory;
   - job/head/role/output/packet/boundary/timestamp consistency is checked mechanically.

5. Denominator integrity
   - a frozen pre-execution population manifest is mandatory;
   - expected/submitted/valid/invalid/omitted/extra denominators are explicit;
   - omitted or undeclared extra artifacts block;
   - duplicate roles/artifacts/jobs do not satisfy quorum;
   - post-hoc exclusion is forbidden.

6. Repair-head invalidation and causal order
   - candidate-head changes invalidate predecessor native/review/audit/aggregate authority;
   - bridge receipt timestamps must be monotonic;
   - stale/wrong-head evidence is rejected.

7. Acceptance/state authority
   - caller-supplied acceptance/state booleans are removed from the authority path;
   - candidate-bound acceptance trace is required;
   - canonical MROS state and Sprint Ledger are validated;
   - future sprint advancement and state/ledger mismatch block.

8. M9/runtime boundary
   - current and next sprint are validated;
   - transitions must be exactly sequential;
   - S111+ is hard-blocked;
   - runtime authority remains NONE in native, review, audit, acceptance and program-state layers.

9. Cross-board independence
   - reviewer and auditor execution job IDs cannot be reused across boards;
   - audit coverage must collectively cover the frozen acceptance criteria;
   - audit native-evidence reference must match the candidate evidence.

10. Calibration completeness
    - frozen `CALIBRATION_CASES.json` defines 32 mandatory labeled controls;
    - denominator conservation is mandatory;
    - known-bad detection must equal 1.0;
    - false acceptance must equal 0.0;
    - known-good acceptance must equal 1.0;
    - false rejection must equal 0.0;
    - frozen `S003_ACCEPTANCE_CONTRACT.json` defines 12 acceptance criteria.

## Repair implementation surface

Governance-only / S003 bootstrap files and scripts were changed. No strategy, broker, risk, execution, runtime, M2 or M9 implementation is authorized by this repair contract.

Key repaired artifacts include:

- `scripts/mros/native_evidence.py`
- `scripts/mros/bridge_receipt.py`
- `scripts/mros/population_manifest.py`
- `scripts/mros/program_context.py`
- `scripts/mros/validate_review.py`
- `scripts/mros/validate_audit.py`
- `scripts/mros/aggregate_reviews.py`
- `scripts/mros/aggregate_audits.py`
- `scripts/mros/advance_program.py`
- `scripts/mros/board_calibration_fixtures.py`
- `scripts/mros/calibrate_review_audit_board_v2.py`
- `scripts/mros/calibrate_review_audit_board.py`
- `research/review_board/REVIEW_SCHEMA.json`
- `research/review_board/AUDIT_SCHEMA.json`
- `research/review_board/REVIEW_POLICY.yaml`
- `research/review_board/AUDIT_POLICY.yaml`
- `research/review_board/CALIBRATION_POLICY.yaml`
- `research/review_board/CALIBRATION_CASES.json`
- `research/evidence/sprints/S003/S003_ACCEPTANCE_CONTRACT.json`

## Required next gate

1. Freeze the repaired exact candidate HEAD.
2. Run the 32-case calibration natively through the Mac bridge against that exact HEAD.
3. Preserve exact Python/command/output/counts/exit and content-addressed source evidence.
4. If and only if calibration passes, freeze a new R002 population manifest before execution.
5. Launch an entirely fresh 10+ reviewer population with the v3 receipt-bound schema.
6. Do not reuse R001 PASS artifacts.
7. If review is non-blocking, launch a fresh 10+ auditor population.
8. Authorize normal Board use only if both aggregates are non-blocking and all S003 acceptance criteria are evidenced.
