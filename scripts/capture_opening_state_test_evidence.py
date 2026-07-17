import subprocess
import json
from pathlib import Path

def run_cmd(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result

def main():
    repo_root = Path(__file__).parent.parent
    out_file = repo_root / "docs" / "agent_reviews" / "opening_state_momentum" / "strategy_test_coverage.md"
    
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    head_rev = run_cmd(["git", "rev-parse", "HEAD"], cwd=str(repo_root)).stdout.strip()
    
    cmd1 = ["pytest", "--collect-only", "-q", "tests/research/opening_state_momentum/"]
    res1 = run_cmd(cmd1, cwd=str(repo_root))
    
    cmd2 = ["pytest", "-q", "tests/research/opening_state_momentum/"]
    res2 = run_cmd(cmd2, cwd=str(repo_root))
    
    cmd3 = ["pytest", "-q", "tests/research/opening_state_momentum/", "-k", "universe or instrument or partition or threshold or oracle or holdout or cutoff or mutation or reconciliation or determinism"]
    res3 = run_cmd(cmd3, cwd=str(repo_root))
    
    # We can parse simple numbers from res3, but since it's asked in markdown, we can just print the outputs
    # and provide the metadata requested.
    
    content = f"""# Strategy Test Coverage Evidence

**Git HEAD**: `{head_rev}`

## 1. Pytest Collect Only
**Command**: `{' '.join(cmd1)}`
**Exit Code**: {res1.returncode}
**STDOUT**:
```text
{res1.stdout}
```
**STDERR**:
```text
{res1.stderr}
```

## 2. Pytest Quiet Run
**Command**: `{' '.join(cmd2)}`
**Exit Code**: {res2.returncode}
**STDOUT**:
```text
{res2.stdout}
```
**STDERR**:
```text
{res2.stderr}
```

## 3. Pytest Keyword Run
**Command**: `{' '.join(cmd3)}`
**Exit Code**: {res3.returncode}
**STDOUT**:
```text
{res3.stdout}
```
**STDERR**:
```text
{res3.stderr}
```
"""
    with open(out_file, "w") as f:
        f.write(content)
        
    print(f"Test evidence captured to {out_file}")
    
if __name__ == "__main__":
    main()
