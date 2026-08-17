# Agent Review Candidate-Blob Hotfix

## Agent Work Contract

- source_agent: ChatGPT/GitHub connector
- action: narrow governance validator repair
- scope: make the base-branch `pull_request_target` validator read review evidence from the exact candidate ref instead of the base checkout
- requested_paths: `scripts/validate_agent_review_evidence.py`, this review document
- forbidden_paths: execution, broker, feed/WebSocket, strategy, risk, runtime launch, credentials, live authority

## Scope Guard

This hotfix changes only review-evidence discovery. It does not change trading code, runtime authority, order routing, feed handling, or any live execution capability.

## Grill Me Review

The previous validator correctly found candidate review filenames and could read candidate text for required-section validation, but its high-risk aggregation re-read only files physically present in the base checkout. A PR-added review document was therefore omitted from the `High-Risk Path Review` check. The repair uses `git show <candidate_ref>:<path>` consistently for candidate review evidence.

## Hermes Review

The validator continues to execute trusted base-branch code under `pull_request_target`. It does not execute candidate Python. Candidate content is treated only as text evidence read by Git, preserving the trust boundary.

## GSD Review

The change is minimal: one helper reads the exact candidate blob and the same text is reused for required-section and high-risk-heading validation. No acceptance criteria are removed or weakened.

## QA / Safety Review

Expected negative behavior is unchanged: missing review docs, missing mandatory sections, review evidence that declares an outstanding stop condition, and missing `High-Risk Path Review` for high-risk diffs still fail closed.

## Acceptance Proof

The fix is accepted only if a PR-added review document containing the mandatory sections and `High-Risk Path Review` is recognized by the base-branch gate, while missing or incomplete evidence still fails.

## Runtime Proof Required After Merge

After this hotfix merges, rerun PR827's `agent-review-evidence` check against the new `main` base and verify it reads the exact PR827 candidate review blob. No live runtime proof is implied by this governance hotfix.

## What This PR Does Not Prove

This hotfix does not prove PR827's code-excellence gate, live readiness, broker connectivity, feed health, order safety beyond PR827's separate evidence, or structural trading edge.

## Human Approval

Merge requires normal repository branch protection and required checks. No direct main update or bypass is authorized by this document.
