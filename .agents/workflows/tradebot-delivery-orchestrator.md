# TradeBot Delivery Orchestrator

Use this workflow for every TradeBot repository task, including engineering, research, documentation, analytics, review, planning, troubleshooting, and read-only investigation. Small or read-only tasks still assemble the full team; tailor each role's scope to the request instead of waiving the seat.

## 0. Assemble the role team

Before substantive work, the lead agent must assemble eight distinct delegated agents. The lead coordinates and integrates; it does not count as a team member. A role label written by the lead is not a substitute for a real delegated agent.

The eight required core seats are:

1. **Business Analyst** — translate the request into current behavior, expected behavior, scope, dependencies, and acceptance criteria.
2. **Product Owner** — confirm the requested outcome, priority where known, scope boundaries, and product acceptance criteria.
3. **Grill Me** — separately challenge assumptions, safety impact, causal/leakage risks where applicable, and fake-progress risks. Review only; do not implement.
4. **Hermes** — define architecture, contracts, invariants, interfaces, and proof gates. Do not implement.
5. **GSD** — execute the approved task within its assigned scope. For read-only tasks, gather the requested evidence without changing files.
6. **QA** — separately execute or inspect behavior against acceptance criteria, report defects, and retest fixes. Must not test its own implementation.
7. **Senior QA** — separately review QA coverage, defect closure, regressions, unsafe fallbacks, scope, and evidence quality. This is a distinct agent from QA and GSD.
8. **Technical & Quant Analyst** — separately challenge the completed implementation and its technical/quantitative assumptions, where applicable; require evidence-backed Hermes responses, track each question to disposition, and verify closure of accepted findings. Must not implement or close its own findings.

Each agent holds exactly one role. Do not combine the QA and Senior QA seats or count one agent for two seats. The Technical & Quant Analyst must be distinct from GSD and Hermes. For tasks with no quantitative behavior or claims, this analyst still returns `NOT_APPLICABLE` for the quant portion and explains why; the technical review remains required. When user acceptance, release, or production verification is in scope, add distinct delegated **UAT**, **Release Manager**, and/or **Production SRE** agents as needed; these are additional seats, not aliases for a core agent. When a gate does not apply, the coordinator records it as `NOT_APPLICABLE` with a task-specific reason. UAT, Release, and Production SRE may not be marked N/A merely because their agent is unavailable. A release or production action remains outside scope unless explicitly authorized.

Use the collaboration/subagent mechanism to create actual agents. Each seat must be a separate delegated agent instance; the coordinator is not a seat, and one agent cannot fill multiple seats. Distinct instances prove separate assignment and attribution, not independent cognition. Give reviewers distinct questions and evidence to inspect, and describe their outputs as separately produced; do not claim that separate agents guarantee independent reasoning. Give each agent the user request, relevant repository instructions, its single role, allowed and forbidden actions/paths, expected output, and acceptance criteria. Each assignment must include the repository's required task contract (`source_agent`, `action`, `title`, `scope`, `requested_paths`, `allowed_paths`, `forbidden_paths`, `expected_tests`, `acceptance_proof`). Keep write ownership explicit: normally only GSD edits implementation files; other agents review or validate.

Use only source/action pairs supported by `core/agent_scope_guard.py`'s `SOURCE_ALLOWED_ACTIONS` mapping:

| Role | `source_agent` | Allowed `action` value(s) |
| --- | --- | --- |
| Business Analyst | `codex` | `PLAN_PR` |
| Product Owner | `codex` | `PLAN_PR` |
| Grill Me | `grill_me` | `AUDIT_RISK`, `CRITIQUE_SCOPE` |
| Hermes | `hermes` | `DEFINE_CONTRACT`, `DESIGN_ARCHITECTURE` |
| GSD | `gsd` | `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `UPDATE_DOCS` |
| QA | `codex` | `REVIEW_PR` |
| Senior QA | `codex` | `REVIEW_PR` |
| Technical & Quant Analyst | `codex` | `REVIEW_PR` |
| UAT (when applicable) | `codex` | `REVIEW_PR` |
| Release Manager (when applicable) | `codex` | `REVIEW_PR` |
| Production SRE (when applicable) | `codex` | `REVIEW_PR` |

`source_agent` identifies the supported agent/tool source, not the business role. Put the role name and task-specific responsibility in `title` and `scope`; select exactly one listed action per task packet, and never pair an action with a source that does not allow it. Keep the other required task-contract fields populated. The mapping is not permission to perform an action forbidden by this workflow or `AGENTS.md`.

Run all core and applicable additional role assignments in waves of no more than three concurrent child agents (or a lower platform limit); the limit does not reduce the required roster. First create each of the eight distinct agent identities in waves and obtain an assignment-acceptance/availability acknowledgment from each; this setup acknowledgment is not the role's substantive review result. Substantive role work then follows the sequence below, and later-stage agents may be reactivated for their assigned handoff when needed. The minimum sequence is: (1) Product Owner and Business Analyst define the outcome and requirements; (2) Grill Me and Hermes provide separately produced risk and architecture reviews; (3) resolve all blocking Grill Me concerns and make Hermes contracts/acceptance gates explicit; (4) only then dispatch GSD for implementation; (5) QA verifies and reports defects; (6) GSD fixes in-scope defects; (7) QA retests; (8) Technical & Quant Analyst issues separately produced post-development technical and applicable quantitative challenge questions; (9) Hermes answers each question with separate evidence; (10) the analyst assigns a defined disposition to every question; (11) for an in-scope `CHANGE_REQUIRED` finding, GSD performs the authorized remediation with tests or documented validation, QA retests, and the analyst verifies closure with evidence; (12) Senior QA performs its separate review; (13) applicable UAT, Release Manager, and Production SRE reviews follow their gates. Do not dispatch GSD to make a patch while Grill Me has an unresolved blocker or Hermes has not produced an explicit design/gate decision. Do not treat unanswered analyst questions as resolved. Before a remediation that changes approved scope, architecture/contracts, or touches a high-risk path, return to Hermes and Grill Me for revised design and risk gates; do not implement until those gates are explicit and any required human authorization is present. A `CHANGE_REQUIRED` finding on a read-only task produces a proposed follow-up only: make no edits unless the user explicitly authorizes the expanded implementation scope. Start dependent roles only after inputs are available and preserve each role's distinct output across waves.

If a subagent creation attempt fails transiently, allow one bounded retry or replacement attempt for that role. Do not retry indefinitely. Do no dependent work while any required seat is incomplete; if the retry/replacement also fails, or an agent returns no evidence or the task is interrupted, record that role as `UNSATISFIED` with the reason. Do not claim all eight agents are assembled until every creation wave has returned an assignment-acceptance/availability acknowledgment. If creation or acknowledgment fails in a later wave, stop immediately at that wave, report the team as `UNSATISFIED`, and do no dependent work. Outputs from earlier waves remain preliminary and cannot authorize GSD implementation, acceptance, or completion. Once all eight distinct agents have acknowledged their role assignments, substantive role findings can progress through the sequence above; implementation still requires all pre-development gates. If an agent fails during substantive work, stop dependent work and apply the same `UNSATISFIED` rule. If any applicable additional role cannot be assembled, stop the dependent UAT/release/production step and report it `UNSATISFIED`. Do not claim completion/readiness while team assembly or a required gate is `UNSATISFIED`. Never claim that an unrun role participated.

Every role must return a concise artifact or finding, including `NOT_APPLICABLE` with a reason when a check does not fit the task. The coordinator records each agent identity, role, dispatch wave, status, and evidence summary in the task response or a scoped task artifact. Do not invent tests, gates, telemetry, approvals, or release evidence. The lead reconciles conflicting findings, checks that all eight core roles reported, and presents one consolidated result with any unsatisfied roles clearly identified.

The repository's root `AGENTS.md` must load and invoke this workflow for every TradeBot task; until that activation link is present, the automatic-team policy is not wired and must be reported `UNSATISFIED`. When loaded, this workflow governs TradeBot repository work. If the agent platform does not expose real delegation in the current task, report assembly as `UNSATISFIED`; do not imply that documentation itself launched or completed a team.

Neither agreement among agents nor approval by the Product Owner, Hermes, QA, Senior QA, UAT, or the coordinator grants human authorization. No consensus, `PASS`, `ACCEPTED`, or resolved finding permits a forbidden broker API call, order action, LIVE action, credential change, or weakening/bypass of risk, kill-switch, or feed-freshness controls. Follow explicit human-approval requirements in `AGENTS.md`; if authorization is absent, stop the action and report the gate `BLOCKED`.

## 1. Classify

Classify the request as:

`EPIC | FEATURE | STORY | BUG | TASK`

Identify the affected product area and parent work item when known.

## 2. Business Analyst pass

Produce:

- business goal
- current behavior
- expected behavior
- in/out scope
- dependencies
- unresolved requirement gaps
- draft acceptance criteria

If the requirement is unsafe or materially incomplete, stop at `BLOCKED_REQUIREMENT`.

## 3. Product Owner pass

Confirm:

- product value
- priority
- scope boundaries
- measurable acceptance criteria
- whether UI/runtime/research work is actually required

Do not permit architecture expansion without product need.

## 3a. Grill Me adversarial scope and risk pass

Before implementation, Grill Me separately challenges:

- unstated assumptions and scope creep;
- safety and operational impact;
- causal, lookahead, or leakage risks where applicable;
- fake progress and unsupported claims;
- whether the acceptance criteria can fail closed.

Record findings and resolve or explicitly carry blockers into architecture. Grill Me does not implement the proposed change.

## 4. Architecture pass

Hermes-compatible architecture roles review:

- reuse of current infrastructure
- interfaces/contracts
- data/state ownership
- concurrency/runtime impact
- high-risk paths
- safety invariants
- test/acceptance proof

State becomes `DESIGN_READY` only when architecture and acceptance gates are explicit.

## 5. Development pass

GSD-compatible developer role:

- implements only approved scope;
- touches only allowed paths;
- writes/updates tests;
- records exact validation;
- does not self-approve QA.

State: `IN_DEVELOPMENT -> DEV_VERIFIED`.

## 6. QA pass

QA attacks the implementation using the work item's QA plan plus `docs/tradebot_delivery/QA_PLAYBOOK.md`.

Any defect causes:

`QA_FAILED -> Development fix -> DEV_VERIFIED -> QA_IN_PROGRESS`

After retest, QA performs a new adversarial pass.

For material claims, record the claim-level G1 source and assumptions, G2
correctness, G3 adversarial comparison, and G4 independent evidence in the
existing work-item evidence contract. Follow the evidence record in
`governance/evidence/POLICY.md`. G2/G3/G4 reviewer identities must be distinct
from the developer and from one another. The report-only CI artifact is a
coverage diagnostic and never substitutes for QA, UAT, product acceptance, or
research certification.

## 7. Technical & Quant Analyst challenge and closure

After development and QA retest, the Technical & Quant Analyst, as a separately assigned reviewer, examines the changed behavior and raises specific, task-tailored questions. Mark individual checklist items `NOT_APPLICABLE` with a reason when they do not fit the change; do not omit applicable checks or invent quantitative claims for non-quantitative work.

Technical systems checklist (apply relevant items):

- Does the diff stay within the approved paths and preserve stated interfaces, schemas, invariants, and SIM/PAPER/LIVE boundaries?
- Are external and persisted inputs validated at the boundary, including missing, malformed, stale, duplicate, out-of-order, and extreme values where relevant?
- Do errors fail closed without silent fallback, dropped evidence, unsafe defaults, or promotion of diagnostics into authority?
- Are authorization, secrets, sensitive data, and high-risk operations protected by the existing least-privilege and explicit-approval rules?
- Are concurrency, ordering, cancellation, retries, timeouts, circuit breaking, and idempotency safe for the touched path?
- Are state changes durable and recoverable across crashes, partial writes, replay, and restart; are migrations/backward compatibility addressed?
- Do tests exercise success, rejection, failure, boundary, and recovery behavior without mocking away the safety decision?
- Can operators observe the new behavior and distinguish healthy, degraded, blocked, and unknown states?
- Are resource limits and degraded-mode behavior bounded, and is the rollback or containment path clear when applicable?

Quant/research checklist (apply when data, statistical claims, candidate evaluation, or trading performance is affected):

- Is the source, version, time zone, event/ingest timestamp, revision history, and data lineage known and reproducible?
- Are universe membership, survivorship, exclusions, missingness, duplicates, and denominator construction explicit and consistent?
- Are features, labels, joins, and outcome windows causal at decision time, with no lookahead, leakage, or post-selection contamination?
- Are train/tune/validation/holdout periods chronologically separated and protected from iterative reuse; are embargoes/gaps appropriate?
- Are all trials, variants, filters, and selection steps counted; are multiple-testing and winner's-curse risks addressed?
- Are baselines, controls, placebos, and relevant negative controls specified, with hypotheses stated before evaluating outcomes where feasible?
- Do uncertainty intervals, sample sizes, effective independent observations, and sensitivity checks support the strength of the claim?
- Are fees, spread, slippage, latency, market impact, liquidity, fill assumptions, and other execution costs realistic for the claimed use?
- Are regime, instrument, expiry, session, and temporal transfer limits disclosed, including contradictory or adverse slices?
- Are results reproducible from frozen inputs/code/config with hashes or equivalent provenance, and do reports preserve `UNKNOWN` or negative outcomes?

Hermes answers every question separately with cited code, tests, artifacts, data manifests, calculations, or other available evidence; a bare assertion is not an answer. For each finding, keep a record containing: finding ID; question; targeted failure; severity; affected behavior, paths, and data; Hermes answer, owner, and evidence; analyst disposition and rationale; remediation owner; required change/test or validation; acceptance proof; closure evidence; and remaining risk. The analyst records one current disposition per question: `RESOLVED_WITH_EVIDENCE` when cited evidence answers the challenge and the separately assigned analyst verifies closure; `CHANGE_REQUIRED` when a scoped correction or additional proof is needed; `UNRESOLVED` when available evidence cannot settle the question; or `DEFERRED` with an owner and explicit future gate. Record Hermes's response separately from the disposition and cite the evidence used for each.

For an authorized, in-scope `CHANGE_REQUIRED`, GSD makes only the approved, scoped code/test changes (or appropriate documented validation for documentation-only work); QA retests; then the Technical & Quant Analyst checks the original question and new evidence and records closure as `RESOLVED_WITH_EVIDENCE`. For a read-only task or any remediation outside explicitly authorized scope, record a proposed follow-up and make no edits. Before remediation that changes approved scope, design/contracts, or touches a high-risk path, Hermes and Grill Me must review the revised scope and gates, and any required human approval must be present before GSD acts. GSD cannot self-close a finding. `UNRESOLVED` and `DEFERRED` are never closed statuses; on an implementation task they block acceptance and completion. For a requested read-only audit, the report may be described as complete at the report/task level when its evidence and findings are fully reported, even if some findings remain `UNRESOLVED` or `DEFERRED`; this does not pass readiness or acceptance, which must remain separately `BLOCKED`, and it never authorizes unrelated code edits. Do not invent or persist a delivery state for this report-level completion. A `CHANGE_REQUIRED` item remains open until the authorized change, QA retest, and analyst closure are evidenced. A `RESOLVED_WITH_EVIDENCE` disposition records only that finding's evidence-based closure; it grants no trading, broker, PAPER, or LIVE execution authority. The question cycle follows development and QA retest and must finish before implementation-task acceptance or completion. Unanswered questions have status `UNRESOLVED`.

Limit remediation to three cycles per finding across all review roles. One cycle is one authorized GSD correction or validation attempt, followed by the required QA retest and the finding owner's closure decision. If the finding remains open after three cycles, stop remediation for this task and record the finding disposition as `UNRESOLVED`, with a note that remediation is blocked at the task level; do not use plain `BLOCKED` as a persisted delivery state. Do not start a fourth cycle without genuinely new evidence or explicit user authorization for a revised scope and a documented re-plan. Never silently reset the cycle count. Read-only audit findings do not trigger code-remediation cycles; report them and keep readiness/acceptance blocked under the applicable documented delivery gate.

## 8. Senior QA review

Senior QA returns exactly one final outcome: `PASS` or `BLOCK`. It reviews as a separate role:

- defect closure;
- regression coverage;
- unsafe fallbacks;
- test weakening;
- scope creep;
- evidence quality.

The distinct Senior QA agent owns this review. It must not be the QA agent or GSD agent for this task.

Any blocking defect, unsafe fallback, weakened check, scope violation, evidence gap, or unverified QA closure results in `BLOCK` and prevents acceptance/completion. Record each blocking finding with its affected behavior/path, evidence, severity, required correction, and acceptance proof. GSD fixes only within authorized scope; QA retests as a distinct role; Senior QA then verifies the specific finding is closed against its original evidence and acceptance proof. If the correction changes approved scope, architecture/contracts, or touches a high-risk path, return to Hermes and Grill Me for revised gates first. Senior QA cannot waive missing evidence or self-approve GSD's change. Only a clear separate review with cited closure evidence can return `PASS`; separate assignment alone does not guarantee independent cognition.

## 9. UAT

UAT applies whenever the task changes user-visible behavior, documentation/workflow artifacts, interfaces/contracts that shape user outcomes, or acceptance criteria. A separately delegated UAT agent validates the outcome from the user's perspective and checks it against the original requirements. It is not the Product Owner, QA, or Senior QA agent. UAT returns `PASS` or `BLOCK`; use `NOT_APPLICABLE` only when there is truly no product acceptance surface (for example, a strictly read-only evidence lookup with no changed artifact or behavior), and state the reason. Backend-only work may use contract/report-based UAT, but the UAT agent must still assess the proof.

Any unmet acceptance criterion, user-visible defect, or unsupported claim results in `BLOCK` and stops acceptance/completion. Record the failing criterion, affected behavior/artifact, evidence, and required correction. GSD fixes only within authorized scope; QA retests as a distinct role; UAT then retests the original criterion and records its separately produced, evidence-based outcome. If the correction changes approved scope, architecture/contracts, or touches a high-risk path, return to Hermes and Grill Me for revised gates first. A `BLOCK` remains in force until UAT records `PASS` after retest. For this workflow-document change, UAT applies: after the text is finalized, a separately delegated UAT agent must confirm that the user's requirement for automatic, role-based team work is clear and fully represented.

## 10. Product acceptance

Product Owner checks the delivered behavior against the original work item and returns `ACCEPTED` or `REJECTED` with evidence and rationale. `REJECTED` blocks acceptance and implementation-task completion. Record the unmet original criterion and required correction; GSD fixes only within authorized scope, QA retests as a distinct role, and the Product Owner revalidates against the same requirement before changing the outcome to `ACCEPTED`. If the original requirement needs revision, obtain explicit user/product-owner authorization for the revision, preserve the prior requirement and rationale, then repeat the relevant design/safety gates and validation against the revised requirement before acceptance. The Product Owner cannot silently add requirements, treat a new requirement as accepted scope, or bypass safety gates, required evidence, or role decisions. A requested read-only audit may still be described as complete at the report/task level when its evidence is delivered, even if a separate readiness or product-acceptance verdict is `REJECTED` or `BLOCKED`; report-level completion does not turn that gate into `ACCEPTED` or create a persisted workflow state.

## 11. Release

When release preparation is in scope, a separately delegated Release Manager:

- ensures PR and agent-review evidence exist;
- confirms required tests/gates;
- records limitations/rollback;
- waits for CI;
- marks `MERGE_APPROVED` only when required gates are green.

If release preparation is outside scope, mark the Release gate `NOT_APPLICABLE` with a reason. Do not present that as release approval.

## 12. Production verification

When a deployed runtime or production state is in scope and its verification is authorized, a separately delegated Production SRE verifies applicable runtime health/smoke checks. Otherwise mark the Production gate `NOT_APPLICABLE` with the scope-based reason. No SRE check authorizes restarting or changing protected live processes absent explicit authorization.

Only then mark `DONE`.

## Required response for every orchestrated task

Report:

1. work-item identity and state;
2. all eight core role assignments (plus any applicable additional roles), each real agent identity, dispatch wave, status, and output;
3. evidence produced;
4. each Technical & Quant Analyst challenge question, separate Hermes evidence-backed answer, current disposition, evidence, and closure status;
5. blockers/failures, including any `UNSATISFIED` roles and preliminary outputs from incomplete waves;
6. next allowed transition.

Never claim a gate passed without evidence.
