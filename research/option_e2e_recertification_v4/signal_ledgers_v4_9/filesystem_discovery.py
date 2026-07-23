from __future__ import annotations

import subprocess
from pathlib import Path


def run_filesystem_discovery() -> dict[str, object]:
    roots = [
        Path("/Users/madhuram/tradebot-data"),
        Path("/Users/madhuram/tradebot-ml-evidence"),
        Path("/Users/madhuram"),
    ]
    results = []
    for root in roots:
        if not root.exists():
            continue
        proc = subprocess.run(["find", str(root), "-maxdepth", "2"], capture_output=True, text=True, timeout=60, check=False)
        results.append({"root": str(root), "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    return {"roots": results}
