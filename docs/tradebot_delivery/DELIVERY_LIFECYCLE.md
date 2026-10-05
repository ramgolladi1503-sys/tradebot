# TradeBot Delivery Lifecycle

## State machine

Every Story/Bug must move through the applicable states:

```text
BACKLOG
-> REQUIREMENT_READY
-> DESIGN_READY
-> IN_DEVELOPMENT
-> DEV_VERIFIED
-> QA_IN_PROGRESS
-> QA_FAILED / QA_PASSED
-> SENIOR_QA
-> UAT
-> PRODUCT_ACCEPTED
-> RELEASE_READY
-> PR_OPEN
-> CI_GREEN
-> MERGE_APPROVED
-> MERGED
-> PRODUCTION_VERIFIED
-> DONE
```

Allowed blocking/failure states:

```text
BLOCKED_REQUIREMENT
BLOCKED_DATA
BLOCKED_RESEARCH
FAILED_VERIFICATION
QA_FAILED
UAT_FAILED
CI_FAILED
RELEASE_BLOCKED
```

Direct transitions such as `IN_DEVELOPMENT -> MERGED` are forbidden.

## Definition of Ready

A work item may enter development only when it has:

- work-item ID
- Epic/Feature mapping
- business goal
- current behavior
- expected behavior
- in-scope
- out-of-scope
- dependencies
- acceptance criteria
- safety/risk constraints
- data requirements where applicable
- test requirements
- rollback considerations where applicable

Missing requirements move the item to `BLOCKED_REQUIREMENT`. Agents must not invent missing business requirements.

## Development phase

Developer responsibilities:

1. implement only approved scope;
2. write/update unit and integration tests;
3. run targeted validation;
4. document what changed and what did not;
5. hand off to QA as `DEV_VERIFIED`.

Developer self-test is not QA acceptance.

## QA defect loop

```text
DEVELOPMENT
   |
   v
QA ATTACK
   |
BUG FOUND?
  |      |
 YES     NO
  |      |
  v      v
DEFECT  SENIOR_QA
  |
  v
DEV FIX
  |
  v
DEV RETEST
  |
  v
QA RETEST
  |
  v
NEW ADVERSARIAL ATTACK
  |
  +---- repeat until QA satisfied
```

Fixing reported defects alone is insufficient. QA must attack the changed area again using different failure modes.

## UAT and product acceptance

UAT verifies expected business behavior. Product Owner verifies the original acceptance criteria.

Engineering success must never be mislabeled as research success or a certified trading edge.

## Release

Release Manager opens/prepares the PR, confirms required evidence, and waits for all required CI and review gates.

No merge while required gates are red.

## Production verification

After merge/deployment, Production/SRE verifies runtime health and required smoke checks before `DONE`.
