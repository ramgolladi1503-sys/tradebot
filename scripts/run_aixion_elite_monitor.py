#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aixion_trade_intelligence.elite_monitor import (
    atomic_write_json,
    build_elite_monitor_iteration,
)
from aixion_trade_intelligence.source_checkpoint_builder import SourceFileSpec


def _read_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"monitor_json_root_must_be_object path={path}")
    return payload


def _source_specs(path: Path) -> list[SourceFileSpec]:
    payload = _read_json(path)
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("monitor_source_config_sources_missing")
    specs: list[SourceFileSpec] = []
    for value in sources:
        if not isinstance(value, Mapping):
            raise ValueError("monitor_source_config_row_not_object")
        specs.append(SourceFileSpec.from_mapping(value))
    return specs


def _append_history(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the continuous read-only Aixion elite analytics monitor.")
    parser.add_argument("--event-log", required=True, type=Path)
    parser.add_argument("--candidate-lineage", required=True, type=Path)
    parser.add_argument("--source-config", required=True, type=Path)
    parser.add_argument("--canary-readiness", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--certification", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--history-jsonl", type=Path)
    parser.add_argument("--interval-seconds", required=True, type=float)
    parser.add_argument("--iterations", type=int, default=1, help="Use 0 for continuous monitoring.")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()
    if args.interval_seconds <= 0:
        raise ValueError("monitor_interval_seconds_must_be_positive")
    if args.iterations < 0:
        raise ValueError("monitor_iterations_must_be_nonnegative")

    source_specs = _source_specs(args.source_config)
    last_exit = 0
    iteration_index = 0
    try:
        while args.iterations == 0 or iteration_index < args.iterations:
            iteration_index += 1
            evaluated_at = datetime.now(tz=timezone.utc)
            try:
                canary = _read_json(args.canary_readiness)
                policy = _read_json(args.policy)
                baseline = _read_json(args.baseline) if args.baseline is not None else None
                certification = _read_json(args.certification) if args.certification is not None else None
                iteration = build_elite_monitor_iteration(
                    event_log_path=args.event_log,
                    candidate_lineage_path=args.candidate_lineage,
                    source_specs=source_specs,
                    canary_readiness=canary,
                    policy=policy,
                    evaluation_time=evaluated_at,
                    baseline=baseline,
                    certification=certification,
                    evidence_refs=(
                        args.source_config.as_posix(),
                        args.canary_readiness.as_posix(),
                        args.policy.as_posix(),
                        args.baseline.as_posix() if args.baseline else "",
                        args.certification.as_posix() if args.certification else "",
                    ),
                )
                record = iteration.to_record()
                args.output_dir.mkdir(parents=True, exist_ok=True)
                atomic_write_json(args.output_dir / "elite_monitor_latest.json", record)
                atomic_write_json(args.output_dir / "elite_cockpit_latest.json", iteration.cockpit.to_record())
                atomic_write_json(args.output_dir / "live_snapshot_latest.json", iteration.live_snapshot.to_record())
                atomic_write_json(args.output_dir / "source_checkpoints_latest.json", iteration.source_checkpoints.to_record())
                if args.history_jsonl is not None:
                    _append_history(args.history_jsonl, record)
                observation_allowed = iteration.cockpit.observation.passed
                monitoring_valid = iteration.live_snapshot.monitoring_valid
                last_exit = 0 if observation_allowed and monitoring_valid else 3
                print(
                    json.dumps(
                        {
                            "iteration": iteration_index,
                            "evaluated_at": iteration.evaluated_at,
                            "monitoring_verdict": iteration.live_snapshot.monitoring_verdict,
                            "observation_verdict": iteration.cockpit.observation.verdict,
                            "diagnosis_verdict": iteration.cockpit.diagnosis.verdict,
                            "profitability_verdict": iteration.cockpit.profitability_claim.verdict,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            except Exception as exc:
                last_exit = 3
                error_record = {
                    "evaluated_at": evaluated_at.isoformat(),
                    "iteration": iteration_index,
                    "verdict": "ELITE_MONITOR_ITERATION_FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                atomic_write_json(args.output_dir / "elite_monitor_error_latest.json", error_record)
                if args.history_jsonl is not None:
                    _append_history(args.history_jsonl, error_record)
                print(json.dumps(error_record, sort_keys=True), file=sys.stderr, flush=True)
                if args.stop_on_error:
                    return last_exit
            if args.iterations == 0 or iteration_index < args.iterations:
                time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        return last_exit
    return last_exit


if __name__ == "__main__":
    raise SystemExit(main())
