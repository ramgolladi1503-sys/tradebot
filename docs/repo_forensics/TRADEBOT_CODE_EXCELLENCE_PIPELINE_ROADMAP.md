# TradeBot Code Excellence Pipeline Roadmap

## Purpose

This roadmap extends the TradeBot post-code repo forensics roadmap.

The existing GSD-FOR roadmap answers:

> What is real, fake, unsafe, unused, weakly tested, or unproven in the repo?

This roadmap answers the next question:

> Once a report finds problems, how do we identify the real root cause, plan the correct fix, harden the code, and prove the result without creating another PR loop?

This is not an auto-fix system. It is a strict, local/manual code-quality pipeline that forces every improvement through root-cause analysis, scoped remediation, production hardening, tests, safety review, and evidence.

## Non-Negotiable Boundaries

- No broad rewrite requests.
- No agent may change code without a scoped contract.
- No auto-fix in MVP.
- No auto-PR generation.
- No dashboard/webhook/agent automation.
- No broker calls.
- No live behavior.
- No target runtime execution by the audit tool.
- No weakening tests to make a patch pass.
- No hiding failures.
- No unrelated refactors.
- `UNKNOWN` is not `PASS`.

## Strict 3-Gate Model

Every PR in this roadmap must pass these three gates.

### Gate 1 — Scope and Intent Gate

Purpose: stop bad work before coding starts.

Required evidence:

- Agent Work Contract
- Grill Me review
- Hermes scope/safety review
- GSD plan/review
- Scope Guard

Gate 1 blocks the PR if:

- scope is vague
- files to touch are unclear
- files not to touch are missing
- broker/live/runtime/dashboard behavior is accidentally included
- tests/evidence expectations are undefined

### Gate 2 — Truth and Root-Cause Gate

Purpose: prevent fixing symptoms instead of the real cause.

Required evidence:

- Repo-forensics finding or test/CI failure input
- Ariadne root-cause investigation when multiple findings/failures are related
- Daedalus remediation contract
- confidence level: CONFIRMED / LIKELY / POSSIBLE / UNKNOWN
- blast radius
- proof required

Gate 2 blocks the PR if:

- root cause is guessed without evidence
- multiple symptoms are patched independently without clustering
- remediation plan is broader than the finding
- `UNKNOWN` is treated as safe

### Gate 3 — Hardening and Proof Gate

Purpose: ensure the code change is production-grade and proven.

Required evidence:

- Vulcan hardening summary
- Minerva test reality review
- Cerberus safety review
- Hermes final scope check
- GSD final evidence approval
- test commands and results
- committed evidence file

Gate 3 blocks the PR if:

- tests are shape-only
- negative tests are missing
- safety boundaries are unclear
- evidence does not prove behavior
- patch changes unrelated behavior
- runtime/broker/live behavior becomes reachable unexpectedly

## Final Agent Responsibilities

| Agent | Responsibility | Writes Code? |
|---|---|---|
| Grill Me | Challenges weak assumptions, fake confidence, and wishful thinking. | No |
| Hermes | Guards scope, safety boundaries, and product constraints. | No |
| GSD | Verifies delivery, evidence, and next-action discipline. | No |
| Argus | Scans repo structure, dead code, duplicate modules, and unused paths. | No |
| Atlas | Audits runtime wiring and caller chains. | No |
| Minerva | Classifies tests and rejects fake proof. | No |
| Cerberus | Audits SIM/PAPER/LIVE and broker boundaries. | No |
| Ariadne | Finds root causes behind grouped findings/failures. | No |
| Daedalus | Converts root cause into scoped remediation PR contracts. | No |
| Vulcan | Hardens the scoped code into production-grade implementation. | Yes, but only from a Daedalus contract |

## Operating Flow

```text
1. Forensics report or failure appears
2. Ariadne clusters related findings and identifies root cause
3. Daedalus creates a scoped remediation contract
4. Hermes checks scope and safety
5. Vulcan implements the exact hardening patch
6. Minerva validates tests are real proof
7. Cerberus validates safety boundaries
8. GSD approves evidence
9. PR summary records all gates
```

## Planned PR Count

This roadmap is planned as **12 PRs**.

The first six build the root-cause-to-remediation pipeline.
The next four build the hardening/proof gates.
The final two integrate the pipeline into future TradeBot PRs.

## PR Roadmap

### CE-01 — Code Excellence Architecture Contract

Purpose:
Define the final architecture, strict 3-gate model, agent roles, and required evidence.

Deliverables:

- `docs/repo_forensics/TRADEBOT_CODE_EXCELLENCE_PIPELINE_ROADMAP.md`
- `docs/agent_reviews/templates/CODE_EXCELLENCE_GATE_TEMPLATE.md`
- Gate 1 / Gate 2 / Gate 3 definitions
- Agent role matrix

Acceptance proof:

- Document clearly states that code changes require a Daedalus contract before Vulcan implementation.
- Document defines what blocks each gate.

Do not touch:

- product code
- tests
- runtime scripts
- dashboard
- broker integrations

---

### CE-02 — Ariadne RCA Template and Contract

Purpose:
Add the root-cause investigation template and standard output contract.

Deliverables:

- `docs/agent_reviews/templates/ARIADNE_RCA_TEMPLATE.md`
- `docs/repo_forensics/ROOT_CAUSE_INVESTIGATION_TEMPLATE.md`

Ariadne output must include:

- finding cluster
- symptoms
- suspected root cause
- confidence level
- proof
- blast radius
- files implicated
- tests/logs/evidence referenced
- recommended remediation direction
- unresolved unknowns

Acceptance proof:

- Template forces confidence levels: CONFIRMED / LIKELY / POSSIBLE / UNKNOWN.
- Template blocks root-cause claims without evidence.

Do not touch:

- scanner implementation
- product code

---

### CE-03 — Finding Normalization Contract

Purpose:
Normalize findings from repo forensics, tests, CI, and evidence reports so Ariadne can group them.

Deliverables:

- `docs/repo_forensics/FINDING_NORMALIZATION_CONTRACT.md`
- optional model design for future implementation

Finding fields:

- finding_id
- source
- severity
- file_path
- symbol/function/class if known
- evidence
- suspected_area
- impact
- recommendation
- proof_required
- confidence

Acceptance proof:

- Each finding type can be mapped into one common shape.
- UNKNOWN findings remain explicit.

Do not touch:

- runtime code
- scanner code unless explicitly scoped later

---

### CE-04 — Ariadne Root-Cause Clustering Engine

Purpose:
Implement deterministic clustering of related findings/failures.

Deliverables:

- `tools/repo_forensics/root_cause_cluster.py`
- tests with fixture findings
- report section for root-cause clusters

Clustering signals:

- same file/module
- shared runtime flow step
- shared error text
- shared missing field
- shared evidence path
- shared safety boundary
- shared candidate/ranking/data-quality concept

Acceptance proof:

- Multiple fallback-related findings cluster into one root-cause candidate.
- Unrelated findings remain separate.
- Clusters include confidence level and unknowns.

Do not touch:

- product code
- broker/live/runtime behavior

---

### CE-05 — Daedalus Remediation Template and Contract

Purpose:
Define how a root-cause cluster becomes a scoped PR plan.

Deliverables:

- `docs/agent_reviews/templates/DAEDALUS_REMEDIATION_TEMPLATE.md`
- `docs/repo_forensics/REMEDIATION_PLAN_TEMPLATE.md`

Daedalus output must include:

- root cause
- decision: FIX_NOW / BACKLOG / DEFER / FALSE_POSITIVE / ACCEPTED_UNKNOWN
- files to change
- files not to touch
- patch behavior
- tests required
- negative tests required
- evidence required
- regression risks
- done means

Acceptance proof:

- Template prevents broad fixes.
- Template requires explicit non-touch list.

Do not touch:

- product code

---

### CE-06 — Remediation Planner Implementation

Purpose:
Generate a remediation plan from root-cause clusters.

Deliverables:

- `tools/repo_forensics/remediation_planner.py`
- tests for root-cause-to-plan conversion
- `docs/repo_forensics/reports/remediation_plan_latest.md`

Acceptance proof:

- A clustered fallback issue becomes one remediation item, not five unrelated fixes.
- Safety issues are marked blocking.
- UNKNOWN items require explanation before code changes.

Do not touch:

- product trading logic
- dashboard
- broker/live paths

---

### CE-07 — Vulcan Production Hardening Template

Purpose:
Add the code-hardening template that Vulcan must follow before any implementation.

Deliverables:

- `docs/agent_reviews/templates/VULCAN_HARDENING_TEMPLATE.md`
- `docs/repo_forensics/PRODUCTION_HARDENING_TEMPLATE.md`

Vulcan must include:

- Daedalus contract reference
- maturity level: BASIC / MEDIUM / PRODUCTION_GRADE / DANGEROUS
- exact behavior to implement
- files changed
- files not touched
- tests added
- negative tests added
- evidence added
- regression risks

Acceptance proof:

- Template prohibits broad rewrite.
- Template requires negative tests and evidence.

Do not touch:

- production code in this PR

---

### CE-08 — Minerva Test Reality Hardening Gate

Purpose:
Ensure every Vulcan patch is backed by meaningful tests, not shape-only tests.

Deliverables:

- `docs/agent_reviews/templates/MINERVA_TEST_REALITY_TEMPLATE.md`
- extension to test-reality report expectations

Minerva must classify tests as:

- SHAPE_ONLY
- UNIT_BEHAVIOR
- INTEGRATION_WIRING
- SAFETY_REGRESSION
- RUNTIME_COMMAND
- EVIDENCE_CONTRACT
- FAKE_CONFIDENCE
- UNKNOWN

Acceptance proof:

- Every code-hardening PR must include at least one negative test when behavior can fail.
- Shape-only tests cannot be the only proof.

Do not touch:

- test implementation unless scoped in a later PR

---

### CE-09 — Cerberus Safety Regression Gate

Purpose:
Ensure every hardening patch preserves SIM/PAPER/LIVE and broker boundaries.

Deliverables:

- `docs/agent_reviews/templates/CERBERUS_SAFETY_TEMPLATE.md`
- safety review requirements for code-hardening PRs

Cerberus must check:

- no broker calls introduced
- no live behavior introduced
- no paper-to-live leakage
- no dashboard order action introduced
- read-only remains read-only
- `is_order_action=false` where applicable
- `broker_api_called=false` where applicable

Acceptance proof:

- Template forces explicit safety review for every Vulcan patch.

Do not touch:

- broker adapters
- live execution paths

---

### CE-10 — Code Excellence Evidence Bundle

Purpose:
Require every code-excellence PR to commit a single evidence file.

Deliverables:

- `docs/agent_reviews/templates/CODE_EXCELLENCE_EVIDENCE_TEMPLATE.md`
- PR summary section for Code Excellence Gate

Evidence file must include:

- Gate 1 result
- Gate 2 result
- Gate 3 result
- forensics finding reference
- Ariadne RCA reference if used
- Daedalus contract
- Vulcan summary
- Minerva review
- Cerberus review
- GSD approval
- commands run

Acceptance proof:

- Future PRs have one standard evidence format.

Do not touch:

- product code

---

### CE-11 — First Code Excellence Baseline Review

Purpose:
Run the full Code Excellence process on the latest TradeBot forensics report or a selected known weak area.

Deliverables:

- `docs/repo_forensics/reports/code_excellence_baseline_YYYY_MM_DD.md`
- `docs/repo_forensics/reports/root_cause_clusters_YYYY_MM_DD.md`
- `docs/repo_forensics/reports/remediation_plan_YYYY_MM_DD.md`
- `docs/agent_reviews/CE11_CODE_EXCELLENCE_BASELINE.md`

Acceptance proof:

- Top root-cause clusters listed.
- Top 5 remediation items listed.
- First recommended Vulcan patch contract created.
- No product code changed in this PR.

Do not touch:

- product code
- tests
- runtime scripts

---

### CE-12 — Future PR Code Excellence Gate

Purpose:
Integrate the Code Excellence pipeline into all future TradeBot PRs.

Deliverables:

- update PR template
- update agent review README/process docs
- add Code Excellence Gate requirement

Every future PR with code changes must include:

- Gate 1 Scope and Intent result
- Gate 2 Truth and Root-Cause result
- Gate 3 Hardening and Proof result
- Ariadne RCA if multiple findings/failures exist
- Daedalus contract if remediation is performed
- Vulcan summary if code is hardened
- Minerva/Cerberus/GSD evidence

Acceptance proof:

- Future PR template includes Code Excellence Gate.
- Process doc explains when Ariadne/Daedalus/Vulcan are mandatory.

Do not touch:

- product code
- scanner behavior unless explicitly scoped

## How This Roadmap Connects to the Existing GSD-FOR Roadmap

This roadmap depends on the post-code repo-forensics foundation.

Minimum dependency before real implementation:

- GSD-FOR-01 Architecture Contract
- GSD-FOR-02 TradeBot Profile
- GSD-FOR-03 Repo Cartographer
- GSD-FOR-04 Runtime Wiring Audit
- GSD-FOR-05 Critical Module Caller Check

Full integration point:

- GSD-FOR-12 First TradeBot Baseline Audit
- GSD-FOR-13 Forensics Gate for Future PRs
- GSD-FOR-14 Product Reality Audit Layer

## Trade Quality Flywheel Is Later

This Code Excellence roadmap still does not directly make TradeBot profitable.

It improves the quality of fixes and prevents random symptom-patching.

The later Trade Quality Flywheel should be a separate roadmap:

- INTEL-01 Data Quality Firewall
- INTEL-02 Canonical Candidate Pool
- INTEL-03 Fallback Cannot Be Executable
- INTEL-04 Ranking Score v2
- INTEL-05 Regime-Aware Scoring
- INTEL-06 Paper Truth Journal
- INTEL-07 Execution Realism Layer
- INTEL-08 Outcome Labeling

Do not start the Trade Quality Flywheel until repo-forensics and Code Excellence gates are usable.

## Final Operating Rule

No code hardening happens from vibes.

Every serious code change must flow through:

```text
finding or failure
  -> Ariadne root cause
  -> Daedalus scoped PR contract
  -> Hermes scope check
  -> Vulcan hardening patch
  -> Minerva test review
  -> Cerberus safety review
  -> GSD evidence approval
```

This is how TradeBot avoids the PR loop:

```text
report found problems
  -> root cause identified
  -> scoped fix designed
  -> code hardened
  -> tests prove behavior
  -> evidence committed
```
