from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any


_TARGET_STRATEGIES = {
    "COMPRESSION_BREAKOUT",
    "EVENT_VOLATILITY_EXPANSION",
    "EXHAUSTION_REVERSAL",
    "FAILED_BREAKOUT_TRAP",
    "HTF_OPENING_DRIVE_CONT",
    "LATE_DAY_MOMENTUM",
    "MEAN_REVERSION_EXTENSION",
    "NO_TRADE_CHOP",
    "OPENING_DRIVE",
    "OPENING_RANGE_BREAKOUT",
    "OPTION_PRESSURE",
    "PAIRS_ARBITRAGE",
    "SIMPLE_ORB",
    "TREND_PULLBACK",
    "VOLATILITY_TREND",
    "VWAP_ORB",
    "VWAP_RECLAIM",
    "ZERO_HERO",
}

_HISTORICAL_HYPOTHESES = {
    "Residual Mean Reversion",
    "Opening-State Momentum",
    "Constituent Lead-Lag weighted",
    "Constituent Breadth unweighted",
    "RSI2 research",
    "ML-discovered campaigns",
}


def load_canonical_strategy_registry(repo_root: Path) -> dict[str, dict[str, Any]]:
    path = repo_root / "research" / "option_e2e_recertification_v4" / "inventory" / "canonical_strategy_registry_v4.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for entry in obj.get("entries", []):
        if entry.get("strategy_id") in _TARGET_STRATEGIES:
            out[str(entry["strategy_id"])] = dict(entry)
    return out


def load_historical_claim_map(repo_root: Path) -> dict[str, dict[str, Any]]:
    path = repo_root / "research" / "option_e2e_recertification_v4" / "inventory" / "historical_claim_map_v4.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    claims: dict[str, dict[str, Any]] = {}
    for claim in obj.get("claims", []):
        claims[str(claim["path"])] = dict(claim)
    return claims


def discover_strategy_files(repo_root: Path, module_path: str) -> tuple[str, str]:
    path = repo_root / module_path
    if not path.exists():
        return "", ""
    return str(path), _sha256(path)


def git_commit_for_path(repo_root: Path, module_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", module_path],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def historical_hypotheses(repo_root: Path) -> dict[str, dict[str, Any]]:
    claims = load_historical_claim_map(repo_root)
    return {
        claim["path"]: claim
        for claim in claims.values()
        if claim.get("path") and (
            any(mention in _HISTORICAL_HYPOTHESES for mention in claim.get("strategy_mentions", []))
            or "claim" in str(claim.get("verdict_label_from_text") or "").lower()
        )
    }
