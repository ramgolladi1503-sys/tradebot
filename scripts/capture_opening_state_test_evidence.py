import subprocess
from pathlib import Path

def main():
    repo_root = Path(__file__).parent.parent
    out_file = repo_root / "docs" / "agent_reviews" / "opening_state_momentum" / "strategy_test_coverage.md"
    
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "pytest",
        "tests/research/opening_state_momentum/",
        "-v",
        "--cov=research/opening_state_momentum",
        "--cov-report=term-missing"
    ]
    
    result = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    
    content = f"""# Strategy Test Coverage Evidence

Generated automatically via `capture_opening_state_test_evidence.py`.

```text
{result.stdout}
```

```text
{result.stderr}
```
"""
    with open(out_file, "w") as f:
        f.write(content)
        
    print(f"Test evidence captured to {out_file}")
    
if __name__ == "__main__":
    main()
