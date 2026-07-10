#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import config as cfg
from core.events import write_json_atomic
from core.feed_health_duration import build_feed_health_duration_artifact
from core.paths import logs_dir, runtime_dir


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _default_snapshot_paths() -> list[Path]:
    return [
        logs_dir() / "feed_runtime_latest.json",
        runtime_dir() / "feed_runtime_latest.json",
    ]


def _load_snapshot(paths: list[Path]) -> tuple[dict[str, Any] | None, Path | None]:
    for path in paths:
        payload = _read_json(path)
        if payload is not None:
            return payload, path
    return None, None


def run_once(
    *,
    snapshot_paths: list[Path] | None = None,
    output_path: Path | None = None,
    target_window_sec: float | None = None,
    max_snapshot_age_sec: float | None = None,
) -> dict[str, Any]:
    paths = list(snapshot_paths or _default_snapshot_paths())
    output = output_path or (logs_dir() / "feed_health_duration_latest.json")
    previous = _read_json(output)
    snapshot, source_path = _load_snapshot(paths)
    observed_epoch = time.time()
    if snapshot is None:
        snapshot = {"ts_epoch": observed_epoch, "feed_ok": False, "ws_connected": False, "runtime_state": "MISSING"}
    else:
        max_age_sec = float(
            max_snapshot_age_sec
            if max_snapshot_age_sec is not None
            else getattr(cfg, "FEED_HEALTH_DURATION_MAX_SNAPSHOT_AGE_SEC", 15.0)
        )
        try:
            snapshot_age_sec = max(0.0, observed_epoch - float(snapshot.get("ts_epoch") or 0.0))
        except Exception:
            snapshot_age_sec = max_age_sec + 1.0
        if snapshot_age_sec > max_age_sec:
            snapshot = dict(snapshot)
            snapshot["feed_ok"] = False
            snapshot["feed_truth_reason_code"] = "runtime_snapshot_stale"
            snapshot["feed_truth_reasons"] = ["runtime_snapshot_stale"]
    artifact = build_feed_health_duration_artifact(
        snapshot,
        previous=previous,
        target_window_sec=float(
            target_window_sec
            if target_window_sec is not None
            else getattr(cfg, "FEED_HEALTH_DURATION_TARGET_SEC", 3600.0)
        ),
        observed_epoch=observed_epoch,
    )
    artifact["snapshot_path"] = str(source_path) if source_path is not None else None
    write_json_atomic(output, artifact)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor feed healthy-duration from runtime snapshots.")
    parser.add_argument("--snapshot", action="append", default=None, help="Runtime snapshot path. May be repeated.")
    parser.add_argument("--out", default=None, help="Output artifact path.")
    parser.add_argument("--target-sec", type=float, default=None, help="Healthy window target in seconds.")
    parser.add_argument("--max-snapshot-age-sec", type=float, default=None, help="Fail closed when snapshot age exceeds this.")
    parser.add_argument("--interval-sec", type=float, default=5.0, help="Polling interval when not using --once.")
    parser.add_argument("--duration-sec", type=float, default=0.0, help="Stop after this many seconds; 0 means run until interrupted.")
    parser.add_argument("--once", action="store_true", help="Write one artifact and exit.")
    args = parser.parse_args()

    snapshot_paths = [Path(item).expanduser() for item in args.snapshot] if args.snapshot else None
    output_path = Path(args.out).expanduser() if args.out else None
    deadline = time.time() + float(args.duration_sec) if float(args.duration_sec or 0.0) > 0.0 else None

    while True:
        artifact = run_once(
            snapshot_paths=snapshot_paths,
            output_path=output_path,
            target_window_sec=args.target_sec,
            max_snapshot_age_sec=args.max_snapshot_age_sec,
        )
        print(
            json.dumps(
                {
                    "healthy": artifact.get("healthy"),
                    "current_healthy_duration_sec": artifact.get("current_healthy_duration_sec"),
                    "target_met": artifact.get("target_met"),
                    "health_reason": artifact.get("health_reason"),
                    "snapshot_path": artifact.get("snapshot_path"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if args.once:
            return 0 if bool(artifact.get("healthy")) else 1
        if deadline is not None and time.time() >= deadline:
            return 0 if bool(artifact.get("target_met")) else 2
        time.sleep(max(1.0, float(args.interval_sec or 5.0)))


if __name__ == "__main__":
    raise SystemExit(main())
