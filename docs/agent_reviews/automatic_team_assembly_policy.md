# Agent Review Evidence: Automatic TradeBot Team Assembly

## Agent Work Contract

| Field | Value |
| --- | --- |
| `source_agent` | `gsd` for the documentation patch; each reviewer used the repository-supported source/action pair listed below |
| `action` | `UPDATE_DOCS` |
| `title` | Require the TradeBot delivery organization and post-development Technical & Quant challenge for every repository task |
| `scope` | Root task activation and the documented eight-role delivery workflow, including evidence-backed question, answer, remediation, retest, and closure handling |
| `requested_paths` | `AGENTS.md`; `.agents/workflows/tradebot-delivery-orchestrator.md`; this review evidence |
| `allowed_paths` | `AGENTS.md`; `.agents/workflows/tradebot-delivery-orchestrator.md`; `docs/agent_reviews/automatic_team_assembly_policy.md` |
| `forbidden_paths` | Runtime, broker, order, strategy, feed, risk, credential, and live-process paths; unrelated files |
| `expected_tests` | Documentation consistency and whitespace validation; application behavior tests are not applicable to this documentation-only change |
| `acceptance_proof` | Root instructions activate the workflow for all TradeBot tasks; eight real distinct roles and failure behavior are explicit; Technical & Quant challenges receive separate Hermes evidence responses and close through authorized remediation, QA retest, and analyst verification; role/action pairs match `SOURCE_ALLOWED_ACTIONS`; no trading authority is granted |

## Scope Guard

The change modifies only `AGENTS.md`, `.agents/workflows/tradebot-delivery-orchestrator.md`, and this evidence record. It documents orchestration policy; it adds no runtime wiring and changes no broker, order, execution, strategy, feed, risk, credential, or live behavior. The primary checkout's unrelated dirty files were not included. No PR approval, merge, push beyond this PR branch, or human authorization for protected runtime actions is claimed by the reviews.

The eight distinct core roles are Business Analyst, Product Owner, Grill Me, Hermes, GSD, QA, Senior QA, and Technical & Quant Analyst. The coordinator is not a seat. UAT, Release Manager, and Production SRE are additional seats when applicable. The workflow explicitly reports unavailable delegation as `UNSATISFIED`; documentation does not claim the platform is forced to instantiate agents. Distinct assignment is described as attribution, not proof of independent cognition.

## Grill Me Review

**Verdict: PASS.** The reviewer challenged universal activation, roster completeness, role/source/action validity, transient failures, and whether separate agent instances prove independent reasoning. Root `AGENTS.md` now activates the workflow for questions, PR lookups, engineering, research, documentation, review, planning, troubleshooting, and read-only investigations. The workflow requires eight distinct instances, bounded retry, `UNSATISFIED` on incomplete delegation, and makes no independence claim. The reviewer confirmed the role/source/action table uses supported pairs. No outstanding blocker was reported.

## Hermes Review

**Verdict: PASS.** The architecture review confirmed the required entrypoint, role separation, task contract, staged handoffs, and safety/authorization boundaries. The Technical & Quant post-development challenge is tied to separate Hermes answers, per-question evidence and disposition, and authorized GSD remediation followed by QA retest and analyst closure. Scope or high-risk changes return through design and risk gates. Platform inability to delegate remains an explicit limitation and must be reported as `UNSATISFIED`.

## GSD Review

**Verdict: PASS.** The scoped change updated only the root activation and orchestrator workflow. The source/action mapping was corrected to use allowed pairs from `core/agent_scope_guard.py::SOURCE_ALLOWED_ACTIONS`. Lifecycle wording was reviewed against `docs/tradebot_delivery/DELIVERY_LIFECYCLE.md`; after three unsuccessful remediation cycles, an open finding is recorded as `UNRESOLVED` and remediation is stopped at task level, without inventing a persisted `BLOCKED` delivery state. `git diff --check` passed. No application tests were run locally because the change is documentation-only.

## QA / Safety Review

**Verdict: PASS.** Independent QA reviewed activation coverage, the eight-role roster, role/action mapping, Technical & Quant finding fields, Hermes response evidence, remediation authorization, QA retesting, analyst closure, and fail-closed behavior. QA found no remaining concrete issue after the mapping and lifecycle wording were corrected. Safety review confirms the workflow grants no order, broker, LIVE, credential, risk-gate, kill-switch, or feed-freshness authority and prohibits edits outside explicit scope. The workflow also makes no claim that repository text can force platform delegation.

## Acceptance Proof

- All eight core seats are enumerated and explicitly required for every TradeBot repository task.
- Root `AGENTS.md` names the workflow entrypoint and requires its invocation before substantive work.
- Agent creation uses distinct delegated instances, waves of at most three, one bounded retry, and `UNSATISFIED` on failure; incomplete roles cannot authorize dependent work or completion.
- Every role packet includes the repository-required contract fields.
- The source/action mapping is checked against `core/agent_scope_guard.py::SOURCE_ALLOWED_ACTIONS` and uses supported values.
- The Technical & Quant Analyst asks post-development questions; Hermes answers each with evidence; dispositions and remediation/closure evidence are tracked; authorized changes receive QA retest and analyst closure.
- `git diff --check` passed after the final documentation edit.
- Application behavior tests are not applicable to the documentation-only patch and were not run locally. GitHub Actions checks are tracked separately on PR #969; this evidence does not claim they passed.

## Runtime Proof Required After Merge

On subsequent TradeBot tasks, verify from the actual coordinator transcript that it loaded this root instruction, created eight distinct delegated role agents, received each availability acknowledgment, retained role-specific outputs, and reported `UNSATISFIED` if any required delegation or review failed. For an implementation task, verify the Technical & Quant challenge, separate evidence-backed Hermes answers, disposition of every question, authorized GSD remediation where required, QA retest, and analyst closure. A documentation merge alone does not prove platform behavior or runtime readiness.

## What This PR Does Not Prove

- It does not force the Codex or other agent platform to create subagents.
- It does not prove that future tasks will load repository instructions in every interface or context.
- It does not prove independent cognition merely because outputs come from separate instances.
- It does not change runtime behavior, certify quantitative or trading claims, establish paper/live readiness, or authorize broker/order/LIVE actions.
- It does not claim required CI checks have passed; the exact PR head must satisfy GitHub's required checks before merge.

## Human Approval

The user explicitly requested merging this policy to `main`. That instruction authorizes pursuing the PR and merge through required repository gates; it does not waive failing checks, grant unrelated runtime authority, or authorize bypassing branch protection. No additional approval for a high-risk code path is applicable because no high-risk code path is changed. Merge remains blocked until repository-required checks and reviews pass.

## Technical & Quant Analyst Review

**Verdict: PASS after correction.** The analyst verified the role/action mapping, per-question evidence/disposition/closure fields, technical and quantitative review checklists, and read-only/safety boundaries. The analyst raised a nomenclature issue because plain `BLOCKED` is not a canonical delivery state. The workflow was corrected to keep the finding `UNRESOLVED` and describe remediation as stopped at task level. Quantitative claims and behavior are not changed by this documentation patch; quant assessment of runtime/trading behavior is not applicable.

## Senior QA Review

**Verdict: PASS.** Senior QA confirmed separate QA and Senior QA seats, explicit UAT `PASS`/`BLOCK` behavior with fix/retest, and Product Owner `ACCEPTED`/`REJECTED` behavior with revalidation. The process artifact is covered by UAT as the workflow itself requires. No release or production verification is claimed for this documentation-only PR.

## Product Owner Review

**Verdict: ACCEPTED.** The Product Owner initially identified the need for root-level activation and explicit supported source/action mappings. Both were added. The final review accepted the universal activation and the role mapping against the repository scope guard.

## UAT Review

**Verdict: PASS.** The separately assigned UAT reviewer confirmed from the user's perspective that TradeBot tasks are directed to the automatic role-based organization, incomplete delegation is reported rather than simulated, and post-development questions flow to evidence-backed answers and code direction when authorized.

## Release Manager Review

**Verdict: READY WITH LIMITATIONS.** The Release Manager confirmed that only the two intended policy documents were changed before this evidence file, that root activation and role/action mappings are explicit, and that actual delegation remains platform-dependent. The review does not approve merge while required checks are failing or pending. The release gate remains subject to exact-head CI and repository branch protection.
