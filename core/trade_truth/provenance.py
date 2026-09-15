"""Process-cached provenance capture and redaction for Trade Truth records.

Guarantees:
- Subprocess (git) calls are executed ONCE at initialization, never in the hot path.
- Redaction scrubs all secrets recursively.
- Config hash hashes decision-relevant public settings.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from typing import Any, Mapping

from config import config as cfg
from core.trade_truth.models import ProvenanceTruth, TRUTH_SCHEMA_VERSION

_SENSITIVE_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
]

_CACHED_GIT_SHA: str | None = None
_CACHED_DIRTY_TREE: bool | None = None
_CACHED_CONFIG_HASH: str | None = None


def redact_sensitive_dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively scrub sensitive keys from dictionaries."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        key_str = str(k)
        if any(p.search(key_str) for p in _SENSITIVE_PATTERNS):
            out[key_str] = "[REDACTED]"
        elif isinstance(v, Mapping):
            out[key_str] = redact_sensitive_dict(v)
        elif isinstance(v, (list, tuple)):
            out[key_str] = [
                redact_sensitive_dict(item) if isinstance(item, Mapping) else item
                for item in v
            ]
        else:
            out[key_str] = v
    return out


def _init_git_info() -> tuple[str, bool]:
    global _CACHED_GIT_SHA, _CACHED_DIRTY_TREE
    if _CACHED_GIT_SHA is not None and _CACHED_DIRTY_TREE is not None:
        return _CACHED_GIT_SHA, _CACHED_DIRTY_TREE

    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, timeout=2.0
        ).decode().strip()
    except Exception:
        sha = "UNKNOWN_GIT_SHA"

    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, timeout=2.0
        ).decode().strip()
        dirty = bool(status)
    except Exception:
        dirty = True

    _CACHED_GIT_SHA = sha
    _CACHED_DIRTY_TREE = dirty
    return sha, dirty


def compute_config_hash() -> str:
    """Compute deterministic SHA-256 hash of public trading config parameters."""
    global _CACHED_CONFIG_HASH
    if _CACHED_CONFIG_HASH is not None:
        return _CACHED_CONFIG_HASH

    public_keys = [
        "EXECUTION_MODE",
        "DEFAULT_SEGMENT",
        "REQUIRE_LIVE_QUOTES",
        "MAX_OPTION_QUOTE_AGE_SEC",
        "MAX_QUOTE_AGE_SEC",
        "MAX_SPREAD_PCT",
        "ML_MIN_PROBA",
        "MAX_DAILY_LOSS_PCT",
        "MAX_DRAWDOWN_PCT",
        "MAX_RISK_PER_TRADE_PCT",
        "RISK_PROFILE",
        "LIVE_PILOT_MODE",
        "LOT_SIZES",
        "SLIPPAGE_PCT",
    ]
    snap: dict[str, Any] = {}
    for key in sorted(public_keys):
        val = getattr(cfg, key, None)
        if isinstance(val, (dict, list, tuple, str, int, float, bool)) or val is None:
            snap[key] = val
        else:
            snap[key] = str(val)

    clean_snap = redact_sensitive_dict(snap)
    raw = json.dumps(clean_snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _CACHED_CONFIG_HASH = hashlib.sha256(raw).hexdigest()
    return _CACHED_CONFIG_HASH


def build_provenance_truth(
    *,
    model_hash: str | None = None,
    model_version: str | None = None,
    strategy_version: str = "1.0.0",
    build_id: str | None = None,
) -> ProvenanceTruth:
    git_sha, dirty_tree = _init_git_info()
    config_hash = compute_config_hash()
    return ProvenanceTruth(
        git_sha=git_sha,
        dirty_tree=dirty_tree,
        config_hash=config_hash,
        model_hash=model_hash,
        model_version=model_version,
        feature_schema_version=1,
        strategy_version=strategy_version,
        truth_schema_version=TRUTH_SCHEMA_VERSION,
        runtime_version="1.0.0",
        build_id=build_id,
    )
