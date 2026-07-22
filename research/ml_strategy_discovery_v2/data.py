from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .contracts import (
    DEVELOPMENT,
    FRESH_CONSUMED,
    FRESH_LOCKED,
    HOLDOUT_LOCKED,
    VALIDATION_CONSUMED,
    canonical_hash,
)


class DatasetRegistryViolation(ValueError):
    """Raised when a locked dataset partition is accessed."""


class ConfirmationAuthorizationError(ValueError):
    """Raised when confirmation authorization is invalid."""


class TokenReplayViolation(ConfirmationAuthorizationError):
    """Raised when a one-time confirmation token is reused."""


@dataclass(frozen=True)
class RegistryRange:
    name: str
    start: str | None
    end: str | None
    status: str | None = None

    def contains(self, session_date: str) -> bool:
        parsed = date.fromisoformat(str(session_date))
        if self.start is not None and parsed < date.fromisoformat(self.start):
            return False
        if self.end is not None and parsed > date.fromisoformat(self.end):
            return False
        return True


@dataclass(frozen=True)
class DatasetRegistry:
    ranges: tuple[RegistryRange, ...]
    source_hash: str

    def classify(self, session_date: str) -> str:
        matches = [item.name for item in self.ranges if item.contains(session_date)]
        if len(matches) != 1:
            raise DatasetRegistryViolation(
                f"session date must map to exactly one registry range: {session_date} -> {matches}"
            )
        return matches[0]


_EXPECTED_RANGES = (
    (DEVELOPMENT, None, "2025-09-05"),
    (VALIDATION_CONSUMED, "2025-09-08", "2026-02-05"),
    (HOLDOUT_LOCKED, "2026-02-06", "2026-07-10"),
    (FRESH_CONSUMED, "2026-07-11", "2026-07-21"),
    (FRESH_LOCKED, "2026-07-22", None),
)


def default_registry() -> DatasetRegistry:
    payload = {
        "ranges": [
            {"name": name, "start": start, "end": end}
            for name, start, end in _EXPECTED_RANGES
        ]
    }
    return DatasetRegistry(
        ranges=tuple(RegistryRange(**item) for item in payload["ranges"]),
        source_hash=canonical_hash(payload),
    )


def load_registry(path: str | Path | None = None) -> DatasetRegistry:
    if path is None:
        return default_registry()
    registry_path = Path(path)
    if not registry_path.is_file():
        raise DatasetRegistryViolation(f"registry file is missing: {registry_path}")
    raw = registry_path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetRegistryViolation("registry JSON is malformed") from exc
    entries = payload.get("ranges")
    if not isinstance(entries, list):
        raise DatasetRegistryViolation("registry ranges are required")
    try:
        ranges = tuple(RegistryRange(**entry) for entry in entries)
    except (TypeError, ValueError) as exc:
        raise DatasetRegistryViolation("registry range entry is invalid") from exc
    normalized = tuple((item.name, item.start, item.end) for item in ranges)
    if normalized != _EXPECTED_RANGES:
        raise DatasetRegistryViolation(
            "registry partition boundaries differ from the frozen V2 contract"
        )
    registry = DatasetRegistry(
        ranges=ranges,
        source_hash=hashlib.sha256(raw).hexdigest(),
    )
    for boundary in (
        "2025-09-05",
        "2025-09-08",
        "2026-02-05",
        "2026-02-06",
        "2026-07-10",
        "2026-07-11",
        "2026-07-21",
        "2026-07-22",
    ):
        registry.classify(boundary)
    return registry


def classify_sessions(
    session_dates: Iterable[str], registry: DatasetRegistry, *, index: pd.Index | None = None
) -> pd.Series:
    values = [registry.classify(str(item)) for item in session_dates]
    return pd.Series(values, index=index, dtype="object")


def select_development_bars(
    bars: pd.DataFrame,
    *,
    registry: DatasetRegistry,
    timestamp_column: str = "timestamp",
) -> pd.DataFrame:
    """Select raw DEVELOPMENT bars before feature and outcome generation."""
    if timestamp_column not in bars.columns:
        raise DatasetRegistryViolation(f"missing timestamp column: {timestamp_column}")
    frame = bars.copy()
    parsed = pd.to_datetime(frame[timestamp_column], errors="raise")
    timezone = getattr(parsed.dt, "tz", None)
    if timezone is not None:
        parsed = parsed.dt.tz_convert("Asia/Kolkata")
    session_dates = pd.Series(parsed.dt.date.astype(str), index=frame.index)
    classifications = classify_sessions(session_dates, registry, index=frame.index)
    mask = classifications.eq(DEVELOPMENT)
    selected = frame.loc[mask].copy()
    if selected.empty:
        raise DatasetRegistryViolation("registry selected no DEVELOPMENT_V1 bars")
    selected["session_date"] = session_dates.loc[mask].to_numpy()
    if any(
        registry.classify(value) != DEVELOPMENT
        for value in selected["session_date"].astype(str).unique()
    ):
        raise AssertionError("development selection invariant failed")
    return selected.reset_index(drop=True)


def load_development_for_selection(
    dataset: pd.DataFrame,
    *,
    registry: DatasetRegistry | None = None,
) -> pd.DataFrame:
    registry = registry or default_registry()
    if "session_date" not in dataset.columns:
        raise DatasetRegistryViolation("session_date is required")
    frame = dataset.copy()
    frame["v2_dataset"] = [
        registry.classify(value) for value in frame["session_date"].astype(str)
    ]
    violating = sorted(set(frame.loc[frame["v2_dataset"] != DEVELOPMENT, "v2_dataset"]))
    if violating:
        raise DatasetRegistryViolation(
            f"selection input contains forbidden partitions: {violating}"
        )
    return frame.reset_index(drop=True)


_OUTCOME_PREFIXES = ("label_", "future_", "target_", "outcome_", "terminal_")
_OUTCOME_EXACT = {
    "barrier_outcome",
    "bars_to_event",
    "mfe_atr",
    "mae_atr",
    "expectancy",
    "profit_factor",
    "base_rate",
    "total_r",
    "pnl",
    "return_r",
}
_METADATA_ALLOWLIST = {
    "session_date",
    "v2_dataset",
    "instrument",
    "symbol",
    "source_logical_path",
    "source_sha256",
    "source_manifest_record_id",
    "row_count",
    "byte_size",
}


def locked_confirmation_metadata(
    frame: pd.DataFrame,
    *,
    registry: DatasetRegistry | None = None,
) -> pd.DataFrame:
    """Return only non-outcome metadata for fresh locked/consumed sessions."""
    registry = registry or default_registry()
    if "session_date" not in frame.columns:
        raise DatasetRegistryViolation("session_date is required")
    classified = frame.copy()
    classified["v2_dataset"] = [
        registry.classify(value) for value in classified["session_date"].astype(str)
    ]
    fresh = classified[
        classified["v2_dataset"].isin({FRESH_LOCKED, FRESH_CONSUMED})
    ].copy()
    forbidden = {
        column
        for column in fresh.columns
        if column.lower() in _OUTCOME_EXACT
        or column.lower().startswith(_OUTCOME_PREFIXES)
    }
    allowed = [
        column
        for column in fresh.columns
        if column in _METADATA_ALLOWLIST and column not in forbidden
    ]
    if not allowed:
        return pd.DataFrame(index=pd.RangeIndex(0))
    return (
        fresh[allowed]
        .drop_duplicates()
        .sort_values(allowed, kind="mergesort")
        .reset_index(drop=True)
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _require_digest(name: str, value: str, lengths: set[int]) -> None:
    if len(value) not in lengths or any(c not in "0123456789abcdef" for c in value):
        raise ConfirmationAuthorizationError(f"{name} has invalid hexadecimal identity")


def issue_confirmation_authorization(
    *,
    candidate_bundle_hash: str,
    fresh_manifest_hash: str,
    code_sha: str,
    side: str,
    evaluation_id: str,
    state_path: str | Path,
) -> str:
    if side not in {"LONG", "SHORT"}:
        raise ConfirmationAuthorizationError("side must be LONG or SHORT")
    _require_digest("candidate_bundle_hash", candidate_bundle_hash, {64})
    _require_digest("fresh_manifest_hash", fresh_manifest_hash, {64})
    _require_digest("code_sha", code_sha, {40, 64})
    if not evaluation_id.strip():
        raise ConfirmationAuthorizationError("evaluation_id is required")
    state_file = Path(state_path)
    if state_file.exists():
        raise ConfirmationAuthorizationError("confirmation authorization already exists")
    nonce = secrets.token_hex(32)
    binding = {
        "candidate_bundle_hash": candidate_bundle_hash,
        "fresh_manifest_hash": fresh_manifest_hash,
        "code_sha": code_sha,
        "side": side,
        "evaluation_id": evaluation_id,
    }
    token = canonical_hash({"binding": binding, "nonce": nonce})
    _atomic_write_json(
        state_file,
        {
            "binding": binding,
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "consumed": False,
        },
    )
    return token


def consume_confirmation_authorization(
    *,
    token: str,
    candidate_bundle_hash: str,
    fresh_manifest_hash: str,
    code_sha: str,
    side: str,
    evaluation_id: str,
    state_path: str | Path,
) -> None:
    state_file = Path(state_path)
    if not state_file.is_file():
        raise ConfirmationAuthorizationError("confirmation authorization is missing")
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    if payload.get("consumed"):
        raise TokenReplayViolation("confirmation authorization was already consumed")
    expected = {
        "candidate_bundle_hash": candidate_bundle_hash,
        "fresh_manifest_hash": fresh_manifest_hash,
        "code_sha": code_sha,
        "side": side,
        "evaluation_id": evaluation_id,
    }
    if payload.get("binding") != expected:
        raise ConfirmationAuthorizationError("confirmation binding mismatch")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(str(payload.get("token_sha256")), token_hash):
        raise ConfirmationAuthorizationError("confirmation token mismatch")
    payload["consumed"] = True
    _atomic_write_json(state_file, payload)
