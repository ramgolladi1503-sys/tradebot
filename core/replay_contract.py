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
VOLATILE_HASH_KEYS = {"replay_hash"}


def canonical_replay_contract() -> dict[str, Any]:
    return {
        "canonical_engine": CANONICAL_REPLAY_ENGINE,
        "determinism_rule": "same_input_same_output",
        "deprecated_engines": sorted(DEPRECATED_REPLAY_ENGINES),
        "supported_modes": ["runtime_artifact_replay", "db_day_replay"],
    }


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in VOLATILE_HASH_KEYS
        }
    if isinstance(value, list):
        canonical_items = [_canonicalize(item) for item in value]
        # Runtime artifact rows are set-like for validation purposes. Sorting prevents
        # harmless traversal-order drift from failing the canonical replay contract.
        return sorted(
            canonical_items,
            key=lambda item: json.dumps(item, sort_keys=True, default=str, separators=(",", ":")),
        )
    return value


def stable_payload_hash(payload: Any) -> str:
    canonical = _canonicalize(payload)
    encoded = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def replay_runtime_artifacts_once(
    *,
    runtime_root: str | Path | None = None,
    symbol: str | None = None,
    start: str | float | int | None = None,
    end: str | float | int | None = None,
) -> dict[str, Any]:
    payload = ReplayEngine.replay_runtime_artifacts(
        runtime_root=Path(runtime_root).expanduser() if runtime_root else None,
        symbol=symbol,
        start=start,
        end=end,
    )
    payload.setdefault("contract", canonical_replay_contract())
    payload["replay_hash"] = stable_payload_hash(payload)
    return payload


def assert_deterministic_runtime_replay(
    *,
    runtime_root: str | Path | None = None,
    symbol: str | None = None,
    start: str | float | int | None = None,
    end: str | float | int | None = None,
) -> dict[str, Any]:
    first = replay_runtime_artifacts_once(runtime_root=runtime_root, symbol=symbol, start=start, end=end)
    second = replay_runtime_artifacts_once(runtime_root=runtime_root, symbol=symbol, start=start, end=end)
    first_hash = stable_payload_hash(first)
    second_hash = stable_payload_hash(second)
    return {
        "ok": first_hash == second_hash,
        "canonical_engine": CANONICAL_REPLAY_ENGINE,
        "first_hash": first_hash,
        "second_hash": second_hash,
        "summary": first.get("summary", {}),
        "missing_artifacts": first.get("missing_artifacts", []),
        "notes": first.get("notes", []),
    }
