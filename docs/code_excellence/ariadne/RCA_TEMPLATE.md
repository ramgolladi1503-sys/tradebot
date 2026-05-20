# Ariadne RCA Template

## Purpose

Ariadne is the root-cause analysis layer for TradeBot Code Excellence.

It turns symptoms, failed checks, logs, test failures, and repo-forensics findings into a disciplined root-cause record before any remediation plan is written.

Ariadne does not patch code.

Ariadne does not auto-fix.

Ariadne does not approve broad rewrites.

## RCA Record Template

```yaml
rca_id: CE-RCA-YYYY-NNN
status: draft | reviewed | accepted | rejected | superseded
owner: TBD
created_at: YYYY-MM-DD
source_pr: TBD
related_prs: []

symptom:
  title: ""
  description: ""
  observed_in:
    - ci
    - runtime_log
    - repo_forensics
    - unit_test
    - live_read_only_observation
    - manual_review
  first_seen: ""
  frequency: unknown | once | intermittent | repeated | constant
  severity: low | medium | high | critical

source_evidence:
  logs: []
  tests: []
  reports: []
  files: []
  prs: []

impact:
  product_risk: ""
  safety_risk: ""
  evidence_risk: ""
  user_or_operator_risk: ""

scope_boundary:
  in_scope: []
  out_of_scope: []
  must_not_change: []

related_modules:
  production: []
  tests: []
  docs_or_reports: []

finding_map:
  normalized_findings: []
  duplicate_or_related_findings: []
  ruled_out_findings: []

root_cause_hypotheses:
  - id: H1
    statement: ""
    supporting_evidence: []
    contradicting_evidence: []
    confidence: low | medium | high

selected_root_cause:
  hypothesis_id: H1
  cause: ""
  why_this_is_root_cause: ""
  why_not_just_symptom: ""

unknowns:
  - ""

deferred_questions:
  - question: ""
    reason_deferred: ""
    required_future_evidence: ""

remediation_requirements:
  required_behavior_change: ""
  required_tests: []
  required_evidence: []
  forbidden_shortcuts: []

ariadne_verdict:
  result: pass | needs_more_evidence | blocked
  reason: ""
```

## Required Sections

### 1. Symptom

Describe what was observed, not what you assume caused it.

Bad:

```text
The readiness logic is broken.
```

Good:

```text
A candidate with fallback contract resolution reached an executable-looking trace even though fallback resolution should force queue-only behavior.
```

### 2. Source Evidence

Every RCA must cite concrete evidence.

Acceptable evidence:

- failing test name
- CI job failure
- runtime log line
- repo-forensics report section
- baseline delta
- product reality finding
- source file and function
- PR discussion or evidence file

Unacceptable evidence:

- intuition
- vague memory
- broad claim that code is messy
- generic statement that tests are weak

### 3. Impact

Classify impact honestly.

Examples:

- product risk: executable candidate truth is unreliable
- safety risk: queue-only candidate may appear actionable
- evidence risk: operator cannot trust logs
- user/operator risk: wrong manual decision due to misleading signal

### 4. Related Modules

Separate production code, tests, and evidence files.

Do not call tests the root cause. Tests expose or fail to expose behavior; the root cause belongs in product code, contract design, or evidence propagation.

### 5. Hypotheses

Ariadne must consider more than one explanation when ambiguity exists.

Example hypotheses:

```text
H1: fallback resolution is not propagated into candidate finalization
H2: final emit logger uses stale candidate status
H3: validator incorrectly classifies queue-only traces as executable
```

### 6. Selected Root Cause

The selected root cause must explain the observed symptom better than alternatives.

It must state why it is not merely a symptom.

### 7. Remediation Requirements

Ariadne does not design the full fix, but it must define what the fix must prove.

Example:

```text
Any fallback-resolved contract must force execution_allowed=false, selected_for_execution=false, and final_action=QUEUE_ONLY before final emission.
```

## Verdict Rules

### PASS

Use when:

- symptom is concrete
- evidence is sufficient
- root cause is supported
- remediation requirements are clear

### NEEDS_MORE_EVIDENCE

Use when:

- symptom is real but root cause is not proven
- logs are incomplete
- multiple hypotheses remain equally likely
- reproduction is missing

### BLOCKED

Use when:

- evidence contradicts the selected root cause
- proposed fix targets only a symptom
- scope is too broad
- safety impact is unknown

## Hard Rules

- Never patch before RCA for non-trivial bugs.
- Never treat a failing test as root cause by itself.
- Never use RCA to justify broad cleanup.
- Never hide uncertainty.
- Never downgrade safety risk without evidence.
- Never claim profitability impact from static RCA.
