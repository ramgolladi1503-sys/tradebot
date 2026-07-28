# Security Audit Report

## Execution Time
2026-07-27T02:37:00Z

## Target Scope
Worktree: /Users/madhuram/tradebot-upstox-expired-option-fetch-v1
Evidence Root: /Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1

## Credential Leakage Scan
**Command 1:** `git grep -n -E 'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'`
```text
No matches found.
```

**Command 2:** `git log -p --all | grep -n -E 'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'`
```text
No matches found.
```

**Command 3:** `grep -RIlE 'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+' /Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1`
```text
No matches found.
```

## Verdict
STATUS: PASS
CREDENTIAL_REVOCATION_STATUS=USER_CONFIRMATION_NOT_AVAILABLE
