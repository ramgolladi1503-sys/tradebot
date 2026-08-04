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


def _record_boot_boundary(root: Path) -> None:
    """Best-effort evidence that main.py import-side startup reached repo guard."""

    try:
        from core.runtime_startup_lifecycle import record_runtime_startup_event

        record_runtime_startup_event(
            "MAIN_BOOT_STARTED",
            source="core.runtime_guard.ensure_runtime_repo_guard",
            details={"repo_root": str(root), "is_order_action": False},
        )
    except Exception:
        # Runtime guard must remain a guard, not a startup dependency.
        pass


def _start_aixion_intelligence_boundary(root: Path) -> None:
    """Start the opt-in read-only evidence tailer without affecting startup."""

    try:
        from aixion_trade_intelligence.runtime_tailer import (
            start_runtime_tailer_if_enabled,
        )

        start_runtime_tailer_if_enabled(root)
    except Exception as exc:
        # The analytics sidecar is never allowed to abort or alter TradeBot.
        try:
            from core.runtime_startup_lifecycle import record_runtime_startup_event

            record_runtime_startup_event(
                "AIXION_INTELLIGENCE_START_FAILED",
                source="core.runtime_guard",
                details={
                    "repo_root": str(root),
                    "error": f"{type(exc).__name__}:{exc}",
                    "is_order_action": False,
                    "read_only": True,
                },
            )
        except Exception:
            pass


_repo_root = ensure_runtime_repo_guard()
_record_boot_boundary(_repo_root)
_start_aixion_intelligence_boundary(_repo_root)
