from __future__ import annotations

import subprocess
from pathlib import Path


def run_archive_discovery(repo_root: Path) -> dict[str, object]:
    archives = list(repo_root.rglob("*.zip"))[:10] + list(repo_root.rglob("*.tar"))[:10] + list(repo_root.rglob("*.tgz"))[:10]
    results = []
    for archive in archives:
        cmd = ["unzip", "-l", str(archive)] if archive.suffix == ".zip" else ["tar", "-tf", str(archive)]
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=60, check=False)
        results.append({"archive": str(archive), "command": " ".join(cmd), "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    return {"archives": results}
