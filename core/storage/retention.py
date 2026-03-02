from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from config import config as cfg

_EVENT_GZ_RE = re.compile(r"^events_(\d{4}-\d{2}-\d{2})\.jsonl\.gz$")
_EVENT_RAW_RE = re.compile(r"^events_(\d{4}-\d{2}-\d{2})\.jsonl$")
_SNAPSHOT_GZ_RE = re.compile(r"^snapshots_(\d{4}-\d{2}-\d{2})\.jsonl\.gz$")
_SNAPSHOT_RAW_RE = re.compile(r"^snapshots_(\d{4}-\d{2}-\d{2})\.jsonl$")


@dataclass
class RetentionResult:
    compressed: int = 0
    deleted_events: int = 0
    deleted_snapshots: int = 0
    deleted_temp_fragments: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "compressed": int(self.compressed),
            "deleted_events": int(self.deleted_events),
            "deleted_snapshots": int(self.deleted_snapshots),
            "deleted_temp_fragments": int(self.deleted_temp_fragments),
        }


class RetentionManager:
    def __init__(
        self,
        base_dir: str | Path,
        *,
        keep_events_days: int = 30,
        keep_snapshots_days: int = 7,
    ) -> None:
        self.base_dir = Path(base_dir).expanduser()
        self.events_dir = self.base_dir / "events"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.keep_events_days = int(keep_events_days)
        self.keep_snapshots_days = int(keep_snapshots_days)

    def run(self, *, dry_run: bool = True) -> dict[str, Any]:
        result = RetentionResult()
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        result.compressed += self._compress_raw_daily(self.events_dir, _EVENT_RAW_RE, dry_run=dry_run)
        result.compressed += self._compress_raw_daily(self.snapshots_dir, _SNAPSHOT_RAW_RE, dry_run=dry_run)

        result.deleted_temp_fragments += self._delete_temp_fragments(self.events_dir, dry_run=dry_run)
        result.deleted_temp_fragments += self._delete_temp_fragments(self.snapshots_dir, dry_run=dry_run)

        result.deleted_events += self._delete_old(self.events_dir, _EVENT_GZ_RE, keep_days=self.keep_events_days, dry_run=dry_run)
        result.deleted_snapshots += self._delete_old(
            self.snapshots_dir,
            _SNAPSHOT_GZ_RE,
            keep_days=self.keep_snapshots_days,
            dry_run=dry_run,
        )
        return result.to_dict()

    def _compress_raw_daily(self, directory: Path, pattern: re.Pattern[str], *, dry_run: bool) -> int:
        compressed = 0
        for path in sorted(directory.glob("*.jsonl")):
            match = pattern.match(path.name)
            if not match:
                continue
            gz_path = path.with_suffix(path.suffix + ".gz")
            if gz_path.exists():
                if not dry_run:
                    try:
                        path.unlink()
                    except Exception:
                        pass
                compressed += 1
                continue
            if not dry_run:
                tmp_path = directory / f".{gz_path.name}.tmp"
                try:
                    with path.open("rb") as src, tmp_path.open("wb") as raw_dst:
                        with gzip.GzipFile(fileobj=raw_dst, mode="wb", compresslevel=6, mtime=0) as dst:
                            shutil.copyfileobj(src, dst, length=1024 * 1024)
                    os.replace(tmp_path, gz_path)
                    path.unlink(missing_ok=True)
                finally:
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
            compressed += 1
        return compressed

    def _delete_temp_fragments(self, directory: Path, *, dry_run: bool) -> int:
        removed = 0
        for path in directory.glob("*"):
            name = path.name
            if not any(token in name for token in (".tmp", ".part", ".fragment")):
                continue
            if path.is_dir():
                continue
            if not dry_run:
                try:
                    path.unlink()
                except Exception:
                    continue
            removed += 1
        return removed

    def _delete_old(self, directory: Path, pattern: re.Pattern[str], *, keep_days: int, dry_run: bool) -> int:
        removed = 0
        today = datetime.now(timezone.utc).date()
        for path in sorted(directory.glob("*.jsonl.gz")):
            match = pattern.match(path.name)
            if not match:
                continue
            try:
                file_date = datetime.fromisoformat(match.group(1)).date()
            except Exception:
                continue
            age_days = (today - file_date).days
            if age_days <= int(keep_days):
                continue
            if not dry_run:
                try:
                    path.unlink()
                except Exception:
                    continue
            removed += 1
        return removed


def _resolve_base_dir() -> Path:
    raw = str(getattr(cfg, "STORAGE_BASE_DIR", "~/.trading_bot/data") or "~/.trading_bot/data")
    return Path(raw).expanduser()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Storage retention/compaction runner")
    parser.add_argument("--run", action="store_true", help="Apply retention and compaction")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without modifying files")
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    dry_run = True
    if args.run:
        dry_run = False
    elif args.dry_run:
        dry_run = True

    manager = RetentionManager(
        _resolve_base_dir(),
        keep_events_days=int(getattr(cfg, "STORAGE_KEEP_EVENTS_DAYS", 30)),
        keep_snapshots_days=int(getattr(cfg, "STORAGE_KEEP_SNAPSHOTS_DAYS", 7)),
    )
    result = manager.run(dry_run=dry_run)
    result["mode"] = "dry_run" if dry_run else "run"
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
