# TEP v1 — Migration and Boundary Validation

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

Repairs Phase-0 findings F-008, F-009 and F-010 together with the human taxonomy in `11_CAPABILITY_AUTHORITY_CATALOGUE.md`.

## 1. Migration dispositions

Every existing orchestrator/service/script proposed for TEP adoption receives exactly one disposition.

### REUSE_VERIFIED
Allowed only when all are proven:
- exact source artifact and SHA/hash are available;
- provenance is known;
- behavior maps to frozen TEP requirement/interface IDs;
- required tests can execute against the exact artifact;
- no conflicting authority/safety semantics exist;
- dependency/licensing/runtime assumptions are acceptable;
- independent equivalence review records limitations.

REUSE_VERIFIED does not mean the artifact is globally certified; only mapped contracts are reusable.

### REIMPLEMENT_REQUIRED
Used when the desired behavior is known but the existing artifact cannot safely become implementation authority because source is missing, provenance is insufficient, architecture conflicts, tests are inseparable, or migration would be riskier than bounded reimplementation.

Required evidence: source/provenance inventory, reason reuse failed, behavior/contracts to preserve, evidence that must not be lost, and explicit non-equivalence caveats.

### UNKNOWN_PROVENANCE
Default when exact implementation/provenance cannot be established. It is a preservation/research state, not permission to delete or copy behavior blindly.

UNKNOWN_PROVENANCE cannot become REUSE_VERIFIED from summaries alone.

## 2. Existing Weekend Orchestrator rule

The prior weekend-orchestrator audit/evidence directories may contain valuable behavioral evidence, tests and state examples. They are not automatically reusable source implementation. Exact source must be located and hash/provenance established before REUSE_VERIFIED. If only evidence remains, use it as requirements/test-fixture input and classify implementation as REIMPLEMENT_REQUIRED or UNKNOWN_PROVENANCE as evidence dictates.

## 3. Migration evidence record

Each migration candidate records:
- candidate ID/path/ref;
- exact SHA/hash;
- provenance source;
- current runtime/process role;
- mapped REQ/IF/ADR IDs;
- tests/evidence available;
- unique local state/data;
- disposition;
- reviewer/validator;
- rollback/preservation action.

No source deletion follows directly from migration classification; Cleanup Service separately evaluates deletion.

## 4. Mechanical architecture boundary acceptance

REQ-ARCH-001 passes only when implementation contains automated checks covering at minimum:

1. application modules cannot import external mutation drivers directly;
2. TBOS scheduler/runtime cannot import GitHub-, broker-, strategy- or research-domain policy implementations;
3. drivers cannot import application or Mission Engine modules;
4. workers cannot write authoritative state-store tables through a direct persistence dependency;
5. GitHub/Git/CI/Merge/Cleanup ownership boundaries have no prohibited reverse dependency;
6. read-only live-observation modules cannot import/order-call execution capability except through explicitly separate future interfaces rejected by default authority;
7. architecture dependency graph is acyclic across defined ownership layers, excluding event/interface abstractions explicitly designed to invert control.

Minimum implementation gate: automated architecture test command returns zero prohibited edges and emits a machine-readable edge report. Critical boundary tests are required CI once their modules exist. A manual code-review statement alone is FAIL.

## 5. Human escalation contract

Human escalation uses the taxonomy in `11_CAPABILITY_AUTHORITY_CATALOGUE.md`. A handler may emit TRUE_HUMAN_APPROVAL_REQUIRED only when it references the governing capability/policy that requires human action.

Invalid human escalations include:
- ordinary merge conflict repair;
- candidate-caused test failure within authorized scope;
- waiting for CI;
- known transient external retry within budget;
- choosing the next runnable independent task;
- summarizing evidence already available to validators.

Valid examples include:
- request to grant live/order authority;
- architecture constitution freeze approval;
- decision to accept an explicit unresolved safety/model-validation risk when policy forbids automation.

## 6. Escalation fail-safe

If a human-only decision is unanswered, the mission follows the recorded safe default. Absence of approval never becomes approval by timeout.

## 7. Phase-0 evidence expectations

For Phase-0, this document is the frozen migration/boundary contract. Actual migration inventories and mechanical import tests are M1+ evidence because implementation modules do not yet exist. Phase-0 review must verify that no roadmap milestone can claim migration or architecture-boundary PASS without these artifacts.