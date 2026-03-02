from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import gzip
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Mapping

from config import config as cfg

from .guard import DiskGuard, MODE_CRITICAL_MINIMAL
from .schema import build_config_version, build_event_record


def _ensure_secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except Exception:
        pass


def _ensure_secure_file(path: Path) -> None:
    if not path.exists():
        path.touch(exist_ok=True)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


@contextmanager
def _file_lock(lock_path: Path):
    _ensure_secure_dir(lock_path.parent)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            os.chmod(lock_path, 0o600)
        except Exception:
            pass
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(fd)


def _append_gzip_jsonl_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _ensure_secure_dir(path.parent)
    lock_path = path.parent / f".{path.name}.lock"
    payload_line = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    payload_bytes = gzip.compress((payload_line + "\n").encode("utf-8"), mtime=0)

    with _file_lock(lock_path):
        tmp_path = path.parent / f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}"
        try:
            with tmp_path.open("wb") as dst:
                if path.exists():
                    with path.open("rb") as src:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                dst.write(payload_bytes)
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(tmp_path, path)
            _ensure_secure_file(path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass


class EventStore:
    def __init__(
        self,
        base_dir: str | Path,
        *,
        guard: DiskGuard | None = None,
        snapshot_store: Any | None = None,
    ) -> None:
        self.base_dir = Path(base_dir).expanduser()
        self.events_dir = self.base_dir / "events"
        self.guard = guard or DiskGuard(
            self.base_dir,
            min_free_pct=float(getattr(cfg, "STORAGE_MIN_FREE_PCT", 10.0)),
            critical_free_pct=float(getattr(cfg, "STORAGE_CRITICAL_FREE_PCT", 5.0)),
        )
        self.snapshot_store = snapshot_store
        self._events_written_by_day: dict[str, int] = {}

    def _daily_path(self, ts_utc: str | None = None) -> Path:
        if ts_utc:
            try:
                dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
                day = dt.date().isoformat()
            except Exception:
                day = datetime.now(timezone.utc).date().isoformat()
        else:
            day = datetime.now(timezone.utc).date().isoformat()
        return self.events_dir / f"events_{day}.jsonl.gz"

    def _bump_counter(self, ts_utc: str) -> None:
        day = ts_utc[:10]
        self._events_written_by_day[day] = int(self._events_written_by_day.get(day, 0)) + 1

    def events_written_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return int(self._events_written_by_day.get(today, 0))

    def store_event(self, payload: Mapping[str, Any], *, capture_snapshots: bool = True) -> dict[str, Any] | None:
        raw = dict(payload or {})
        if not raw:
            return None

        if str(raw.get("event_type") or "").strip().lower() != "disk_critical" and self.guard.should_emit_disk_critical():
            self._store_disk_critical_event()

        if not self.guard.allow_features_blob():
            raw["features_summary"] = None

        raw.setdefault("config_version", build_config_version(cfg))
        try:
            record = build_event_record(
                raw,
                config_version=str(raw.get("config_version") or ""),
                features_max_bytes=int(getattr(cfg, "STORAGE_FEATURES_SUMMARY_MAX_BYTES", 2048)),
                features_max_keys=int(getattr(cfg, "STORAGE_FEATURES_SUMMARY_MAX_KEYS", 96)),
            )
        except Exception:
            return None
        payload_out = record.to_dict()
        path = self._daily_path(record.ts_utc)

        try:
            _append_gzip_jsonl_atomic(path, payload_out)
            self._bump_counter(record.ts_utc)
            print(
                f"[Storage] stored event_type={record.event_type} count_today={self.events_written_today()}"
            )
        except Exception:
            return None

        if capture_snapshots and self.snapshot_store is not None:
            try:
                self.snapshot_store.capture_around_event(payload_out)
            except Exception:
                pass
        return payload_out

    def _store_disk_critical_event(self) -> None:
        # Direct write to avoid recursion through disk guard logic.
        free_pct = self.guard.free_pct
        payload = {
            "event_type": "disk_critical",
            "desk": str(getattr(cfg, "DESK_ID", "DEFAULT")),
            "mode": str(getattr(cfg, "TRADING_MODE", getattr(cfg, "EXECUTION_MODE", "PAPER"))).upper(),
            "symbols": [],
            "reason_code": f"disk_free_pct:{free_pct:.2f}",
            "features_summary": None,
            "data_source": "derived",
            "missing_fields": [],
            "config_version": build_config_version(cfg),
        }
        try:
            record = build_event_record(
                payload,
                config_version=str(payload["config_version"]),
                features_max_bytes=256,
                features_max_keys=16,
            )
            _append_gzip_jsonl_atomic(self._daily_path(record.ts_utc), record.to_dict())
            self._bump_counter(record.ts_utc)
        except Exception:
            return

    def metrics(self) -> dict[str, Any]:
        state = self.guard.refresh()
        return {
            "events_written_today": self.events_written_today(),
            "disk_free_pct": float(state.free_pct),
            "storage_mode": str(state.mode),
            "features_enabled": state.mode != MODE_CRITICAL_MINIMAL,
        }
