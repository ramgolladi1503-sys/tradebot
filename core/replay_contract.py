from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.replay_engine import ReplayEngine

CANONICAL_REPLAY_ENGINE = "core.replay_engine.ReplayEngine"
DEPRECATED_REPLAY_ENGINES = {
    "core.replay_backtest_v2.ReplayBacktestEngineV2",
    "core.replay_backtest_v3.ReplayBacktestEngineV3",
}


def canonical_replay_contract() -> dict[str, Any]:
    return {
        "canonical_engine": CANONICAL_REPLAY_ENGINE,
        "determinism_rule": "same_input_same_output",
        "deprecated_engines": sorted(DEPRECATED_REPLAY_ENGINES),
        "supported_modes": ["runtime_artifact_replay", "db_day_replay"],
    }


def stable_payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def replay_runtime_artifacts_once(*, runtime_root: str | Path | None = None, symbol: str | None = None, start: str | float | int | None = None, end: str | float | int | None = None) -> dict[str, Any]:
    payload = ReplayEngine.replay_runtime_artifacts(
        runtime_root=Path(runtime_root).expanduser() if runtime_root else None,
        symbol=symbol,
        start=start,
        end=end,
    )
    payload.setdefault("contract", canonical_replay_contract())
    payload["replay_hash"] = stable_payload_hash(payload)
    return payload


def assert_deterministic_runtime_replay(*, runtime_root: str | Path | None = None, symbol: str | None = None, start: str | float | int | None = None, end: str | float | int | None = None) -> dict[str, Any]:
    first = replay_runtime_artifacts_once(runtime_root=runtime_root, symbol=symbol, start=start, end=end)
    second = replay_runtime_artifacts_once(runtime_root=runtime_root, symbol=symbol, start=start, end=end)
    first_hash = stable_payload_hash({k: v for k, v in first.items() if k != "replay_hash"})
    second_hash = stable_payload_hash({k: v for k, v in second.items() if k != "replay_hash"})
    return {
        "ok": first_hash == second_hash,
        "canonical_engine": CANONICAL_REPLAY_ENGINE,
        "first_hash": first_hash,
        "second_hash": second_hash,
        "summary": first.get("summary", {}),
        "missing_artifacts": first.get("missing_artifacts", []),
        "notes": first.get("notes", []),
    }
