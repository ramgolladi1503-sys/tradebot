# S002 Repair Evidence — Response to Independent Review

Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S002
Branch: `research/mros-program-v1`
Authority: `Research / R`
Runtime authority: `NONE`
Decision: `IN_PROGRESS`

## Repair source

Independent review artifact:

`research/evidence/sprints/S002/S002_INDEPENDENT_REVIEW.md`

Review commit:

`2852e9c06c9c2d5e2c9c43052b0935825842c614`

Reviewed pre-repair HEAD:

`ac3429b88709f313037c0f124fc1545e51d2b36c`

Review verdict:

`S002_INDEPENDENT_REVIEW_REPAIR_REQUIRED`

Finding counts:

- MINOR: 0
- MAJOR: 5
- CRITICAL: 0
- UNKNOWN: 0

The prior native validation (`23/23 PASS`, Python 3.12.2, exit 0) is preserved as valid evidence for the pre-repair reviewed head only. It is not reused as evidence for this repair.

## Repair commits

- `cf757f23cefde81ecd9786c6d3397ce27e83d7ce` — validator fail-closed repair.
- `ea08742c346d0d24004ea8686bdb10fb66c2d162` — fixture corpus expanded from 23 to 39 adversarial/positive cases.
- `31180e65fd85119aab29f2186cfcc0e1a8429919` — S002 contract-implementation documentation updated to describe repaired semantics.
- `3b7e3782c71038e5ff121b15d10fd3c02ba0eed3` — program state updated; S002 remains blocked pending native validation and fresh independent re-review.
- `f06504af051d666bb13f9c70d664404193eb9c3f` — Sprint Ledger updated; decision remains `IN_PROGRESS`.

## Finding-to-repair trace

### F-001 — Empty constitutional action silently PASS

Repair:

- a constitutional request must contain a recognizable governed decision surface;
- incomplete causal-time/runtime/scope field pairs fail closed;
- empty/indeterminate requests return `INVALID_INPUT` + `MROS-S001-E001-MISSING_REQUIRED_FIELD`.

New evidence cases include `S002-C024` and `S002-C038`.

### F-002 — Strong-grade gates were caller-optional

Repair:

Mandatory gate evidence is derived from requested authority:

- Grade B requires independent attack/replication plus calibration;
- Grade A additionally requires scientific/economic certification references;
- Grade A+ requires live/forward and monitoring evidence in addition to strong-grade gates.

Caller omission of `requires_*` flags cannot suppress these grade-derived requirements.

New evidence cases include `S002-C025`, `C026`, `C033`, `C034`, `C035`, `C036`, and `C037`.

### F-003 — `Rejected` / `Unknown` bypassed stage validation

Repair:

Promotion uses an explicit legal-transition map. `Rejected` and `Unknown` have no implicit promotion transition. Any undeclared transition fails closed with E004 / RC-002.

New evidence cases include `S002-C027` and `S002-C028`.

### F-004 — Observed fact could be manufactured without provenance

Repair:

`OBSERVED_FACT` and `INFERENCE` require evidence references. Missing provenance returns `INVALID_INPUT` + E015 rather than PASS.

New evidence cases include `S002-C029` and `S002-C039`.

### F-005 — RC-009 relied on a self-declared laundering boolean

Repair:

Confirmatory and exploratory post-hoc denominator checks now require frozen/current denominator-contract metadata and compare those contracts directly. The minimum metadata includes denominator definition, exclusion rules, population identity, horizon, regimes, symbols, dates identity, and search-family identity.

A changed confirmatory contract after outcomes fails E008/E009 / RC-009.

A preregistered data-quality exclusion whose frozen/current contract is unchanged remains valid.

A changed exploratory post-hoc analysis is permitted only when the original result is preserved, a new analysis identity and rationale exist, multiplicity is accounted for, and authority is reduced.

Updated/new evidence cases include `S002-C010`, `C030`, `C031`, and `C032`.

## Frozen S001 compatibility

The repair does not rename or weaken S001 E001–E017. S002 additive enum codes E018–E020 remain fail-closed and unchanged.

The repair strengthens enforcement of S001 invariants I-001 through I-010; it does not modify the frozen S001 contract.

## Scope

Changed repair paths are limited to:

- `scripts/mros/validate_s002_fixtures.py`
- `research/evidence/sprints/S002/S002_FIXTURES.json`
- `research/evidence/sprints/S002/S002_CONTRACT_IMPLEMENTATION.md`
- `research/evidence/sprints/S002/S002_REPAIR_EVIDENCE.md`
- `research/program/MROS_PROGRAM_STATE.yaml`
- `research/program/SPRINT_LEDGER.jsonl`

No S003, runtime, strategy, broker, risk, execution, M2, or M9 implementation is authorized or intentionally changed.

## Required validation

The repaired fixture schema is:

`mros-s002-fixtures-v3`

Required case count:

`39`

Required command:

```bash
python3 scripts/mros/validate_s002_fixtures.py
```

A valid acceptance-path run must preserve exact checked-out HEAD, Python version, exact command, stdout, stderr, summary, and exit code.

## Current status

`REPAIR_IMPLEMENTED_PENDING_NATIVE_VALIDATION`

No native result is claimed by this artifact.

## Next gate

1. Native exact-checkout validation of the final repaired S002 branch head.
2. Fresh independent re-review by a session that did not implement or direct this repair.
3. Only after a passing re-review may the primary MROS session accept S002 and activate S003.
