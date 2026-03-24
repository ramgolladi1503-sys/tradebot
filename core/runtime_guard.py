from __future__ import annotations

from pathlib import Path


_REQUIRED_REPO_MARKERS = (
    "main.py",
    "core",
    "strategies",
    "config",
)


def detect_repo_root() -> Path:
    """Resolve the project root from this module location, not from cwd."""
    return Path(__file__).resolve().parents[1]


def validate_repo_root(repo_root: Path | str | None = None) -> Path:
    """
    Fail closed on malformed project structure without hardcoding a machine path.

    This guard is intentionally structure-based:
    - portable across clone locations
    - safe to import from any cwd
    - still catches running against a broken/incomplete checkout
    """
    root = Path(repo_root).resolve() if repo_root is not None else detect_repo_root()
    missing = [marker for marker in _REQUIRED_REPO_MARKERS if not (root / marker).exists()]
    if missing:
        raise RuntimeError(
            "INVALID REPO ROOT\n"
            f"Detected root: {root}\n"
            f"Missing required markers: {', '.join(missing)}\n"
            "Fix your checkout or launch path."
        )
    return root


def ensure_runtime_repo_guard() -> Path:
    return validate_repo_root()


ensure_runtime_repo_guard()
