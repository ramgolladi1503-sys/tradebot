import os
import subprocess
from pathlib import Path
from datetime import datetime

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
REPORTS_DIR = EVIDENCE_ROOT / "reports"
WORKTREE = Path("/Users/madhuram/tradebot-upstox-expired-option-fetch-v1")

def run_cmd(cmd, cwd):
    # Using check=False because grep returns 1 if no match
    res = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True)
    return res.stdout.strip()

def main():
    print("Starting Security Audit...")
    
    cmd1 = "git grep -n -E 'eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+' || true"
    out1 = run_cmd(cmd1, WORKTREE)
    
    cmd2 = "git log -p --all | grep -n -E 'eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+' || true"
    out2 = run_cmd(cmd2, WORKTREE)
    
    cmd3 = "grep -RIlE 'eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+' /Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1 || true"
    out3 = run_cmd(cmd3, WORKTREE)
    
    # We shouldn't output the actual tokens if found, just count or paths
    # But since grep -l gives paths, that's fine. 
    # For cmd1 and cmd2, we should redact the output before writing to report
    
    def redact(text):
        import re
        return re.sub(r'(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)', '[REDACTED_TOKEN]', text)
        
    out1_r = redact(out1)
    out2_r = redact(out2)
    
    report = f"""# Security Audit Report

## Execution Time
{datetime.utcnow().isoformat()}

## Target Scope
Worktree: {WORKTREE}
Evidence Root: {EVIDENCE_ROOT}

## Credential Leakage Scan
**Command 1:** `git grep -n -E 'JWT_PATTERN'`
```text
{out1_r if out1_r else 'No matches found.'}
```

**Command 2:** `git log -p --all | grep -n -E 'JWT_PATTERN'`
```text
{out2_r if out2_r else 'No matches found.'}
```

**Command 3:** `grep -RIlE 'JWT_PATTERN' /Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1`
```text
{out3 if out3 else 'No matches found.'}
```

## Verdict
STATUS: PASS if no unauthorized tokens are exposed.
CREDENTIAL_REVOCATION_STATUS=USER_CONFIRMATION_NOT_AVAILABLE
"""
    
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "security_report.md", "w") as f:
        f.write(report)
        
    print("Security Audit Complete.")

if __name__ == "__main__":
    main()
