from __future__ import annotations

from pathlib import Path


def load_historical_implementation_candidates(repo_root: Path) -> list[dict[str, object]]:
    return [{"path": str(path)} for path in (repo_root / "research" / "option_e2e_recertification_v4").rglob("*v4_1*") if path.is_file()]
