# Finding Deduplication Rules

## Purpose

Deduplication prevents the same underlying issue from creating five disconnected fixes.

TradeBot can show the same root problem through multiple sources:

- CI failure
- runtime log contradiction
- repo-forensics finding
- product reality classification
- manual review concern
- failing regression test

These should become related normalized findings, not random independent work.

## Deduplication Levels

### Exact Duplicate

Two findings are exact duplicates when they share:

- same source type
- same file/function or same report section
- same observed behavior
- same expected behavior

Action:

```text
Mark later finding duplicate_of earlier finding.
```

### Same Symptom, Different Source

Two findings are related when they describe the same symptom from different sources.

Example:

```text
runtime log shows queue-only/executable contradiction
pytest regression test fails for queue-only executable contradiction
```

Action:

```text
Link as related_findings.
Cluster under same RCA.
```

### Same Root-Cause Family

Two findings are related when they share a root-cause family but not the same symptom.

Example:

```text
fallback contract propagation gap
stale feed propagation gap
```

Action:

```text
Do not mark duplicate.
Cluster under same root-cause family for Ariadne review.
```

### Same File, Different Behavior

Two findings touching the same file are not duplicates unless behavior overlaps.

Example:

```text
core/review_queue.py final emit wording issue
core/review_queue.py missing evidence field issue
```

Action:

```text
Keep separate unless RCA proves shared cause.
```

## Duplicate Decision Rules

### Rule 1 — Do Not Deduplicate By Filename Alone

Same file does not mean same issue.

### Rule 2 — Do Not Deduplicate By Severity Alone

Two critical findings can be unrelated.

### Rule 3 — Prefer Related Over Duplicate When Unsure

If evidence is incomplete, mark as related instead of duplicate.

### Rule 4 — Preserve the Strongest Evidence

When duplicates are merged, preserve the finding with:

1. direct runtime evidence
2. failing safety/contract test
3. repo-forensics hard finding
4. manual review evidence
5. weak or indirect evidence

### Rule 5 — Keep Safety Findings Visible

Do not hide safety findings behind broad duplicates.

If a duplicate touches broker/live/order/actionability boundary, keep safety risk visible in the primary finding.

## Deduplication Key

A deterministic deduplication key should be built from:

```text
finding_type
root_cause_family
normalized_observed_behavior
normalized_expected_behavior
affected_contract_or_module
```

Do not include timestamp in the key unless the issue is time-specific.

## Relationship Fields

Use these fields:

```yaml
relationships:
  duplicate_of: CE-FINDING-YYYY-NNN | null
  related_findings:
    - CE-FINDING-YYYY-NNN
  blocked_by:
    - CE-FINDING-YYYY-NNN
  blocks:
    - CE-FINDING-YYYY-NNN
```

## Examples

### Example 1 — Exact Duplicate

Finding A:

```text
repo-forensics evidence_high: decision record missing reason field in runtime/events.jsonl
```

Finding B:

```text
manual review: runtime/events.jsonl decision record has no reason
```

Decision:

```text
related or duplicate depending on exact record path and event identity
```

### Example 2 — Same Symptom, Different Source

Finding A:

```text
runtime log: FINAL_EMIT says executable for queue-only candidate
```

Finding B:

```text
test failure: queue-only final emit test expected FINAL_EMIT_QUEUE_ONLY
```

Decision:

```text
related_findings under same RCA
```

### Example 3 — Same Root-Cause Family, Not Duplicate

Finding A:

```text
fallback contract truth not propagated into readiness
```

Finding B:

```text
stale feed blocker not propagated into readiness
```

Decision:

```text
same root_cause_family=PROPAGATION_GAP, but not duplicate
```

## RCA Interaction

Ariadne may change duplicate decisions after root-cause analysis.

Before RCA:

```text
related_findings
```

After RCA proves same cause:

```text
duplicate_of or same RCA cluster
```

## Anti-Patterns

Do not deduplicate:

- all findings in one file
- all findings with same severity
- all repo-forensics findings
- all test failures from one CI job
- all evidence gaps

That hides real work.

## Output Requirement

Every deduplication decision must explain:

- why duplicate or related
- what evidence was preserved
- what evidence was discarded or superseded
- whether safety risk remains visible
