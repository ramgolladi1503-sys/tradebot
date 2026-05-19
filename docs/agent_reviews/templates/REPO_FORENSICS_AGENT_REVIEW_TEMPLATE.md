# Repo Forensics Agent Review Template

Use this template for PRs that introduce or run repo-forensics checks.

## Agent Work Contract

### Scope

```text
What this PR is allowed to change.
```

### Files Changed

- TBD

### Files Not To Touch

- broker adapters
- live execution paths
- dashboard runtime behavior unless explicitly scoped
- unrelated strategy logic
- unrelated tests

### Expected Proof

- docs updated
- scanner/checker tests if implementation PR
- report evidence if audit run PR
- no live/broker/runtime execution

## Grill Me Review

### Challenge

```text
What assumption could be wrong?
```

### Weaknesses Found

- TBD

### Verdict

PASS / BLOCKED / NEEDS FIX

## Hermes Review

### Scope Check

- [ ] No unrelated behavior changed.
- [ ] No broker calls introduced.
- [ ] No live behavior introduced.
- [ ] No dashboard behavior introduced unless scoped.
- [ ] No target runtime execution.
- [ ] `UNKNOWN` is not treated as safe.

### Verdict

PASS / BLOCKED / NEEDS FIX

## GSD Review

### Delivery Check

- [ ] Purpose is clear.
- [ ] Scope is narrow.
- [ ] Evidence exists.
- [ ] Tests exist if code was added.
- [ ] Report output exists if audit was run.
- [ ] Next action is clear.

### Verdict

PASS / BLOCKED / NEEDS FIX

## Scope Guard

### In Scope

- TBD

### Out of Scope

- TBD

### Boundary Verification

- [ ] No broker calls.
- [ ] No live runtime execution.
- [ ] No target repo mutation by scanner.
- [ ] No auto-fix.
- [ ] No auto-PR.
- [ ] No external agent automation.

## Evidence

### Commands Run

```bash
# TBD
```

### Reports / Files Produced

- TBD

### Final Verdict

PASS / BLOCKED / NEEDS FIX
