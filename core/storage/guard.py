from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

MODE_NORMAL = "NORMAL"
MODE_SNAPSHOTS_DISABLED = "SNAPSHOTS_DISABLED"
MODE_CRITICAL_MINIMAL = "CRITICAL_MINIMAL"


@dataclass
class DiskState:
    free_pct: float
    mode: str


class DiskGuard:
    """Disk-pressure guard with fail-safe behavior.

    The guard never raises. On failures, it falls back to MODE_NORMAL with 100% free.
    """

    def __init__(
        self,
        base_dir: str | Path,
        *,
        min_free_pct: float = 10.0,
        critical_free_pct: float = 5.0,
    ) -> None:
        self.base_dir = Path(base_dir).expanduser()
        self.min_free_pct = float(min_free_pct)
        self.critical_free_pct = float(critical_free_pct)
        self._state = DiskState(free_pct=100.0, mode=MODE_NORMAL)
        self._disk_critical_emitted = False

    def refresh(self) -> DiskState:
        try:
            free_pct = disk_free_pct(self.base_dir)
            mode = _mode_for_free_pct(
                free_pct,
                min_free_pct=self.min_free_pct,
                critical_free_pct=self.critical_free_pct,
            )
            self._state = DiskState(free_pct=free_pct, mode=mode)
            return self._state
        except Exception:
            self._state = DiskState(free_pct=100.0, mode=MODE_NORMAL)
            return self._state

    @property
    def mode(self) -> str:
        return self._state.mode

    @property
    def free_pct(self) -> float:
        return self._state.free_pct

    def allow_snapshots(self) -> bool:
        state = self.refresh()
        return state.mode == MODE_NORMAL

    def allow_features_blob(self) -> bool:
        state = self.refresh()
        return state.mode != MODE_CRITICAL_MINIMAL

    def should_emit_disk_critical(self) -> bool:
        state = self.refresh()
        if state.mode != MODE_CRITICAL_MINIMAL:
            return False
        if self._disk_critical_emitted:
            return False
        self._disk_critical_emitted = True
        return True


def _mode_for_free_pct(free_pct: float, *, min_free_pct: float, critical_free_pct: float) -> str:
    if free_pct < float(critical_free_pct):
        return MODE_CRITICAL_MINIMAL
    if free_pct < float(min_free_pct):
        return MODE_SNAPSHOTS_DISABLED
    return MODE_NORMAL


def disk_free_pct(path: str | Path) -> float:
    target = Path(path).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target)
    total = float(getattr(usage, "total", 0.0) or 0.0)
    free = float(getattr(usage, "free", 0.0) or 0.0)
    if total <= 0.0:
        return 100.0
    return max(0.0, min(100.0, (free / total) * 100.0))
