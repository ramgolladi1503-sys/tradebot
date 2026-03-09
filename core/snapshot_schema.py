from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, TypedDict


class TokenCoverageV1(TypedDict):
    index_token: int
    option_tokens_count: int
    option_tokens: list[int]
    strike_window: dict[str, Any]


class FreshnessV1(TypedDict):
    sla_threshold_sec: float
    max_tick_age_sec: float
    stale_tokens_count: int


class TicksV1(TypedDict):
    index: dict[str, Any]
    options: dict[str, dict[str, Any]]


class ExpiryV1(TypedDict):
    is_expiry_day: bool
    expiry_date: str | None


class RegimeV1(TypedDict):
    state: str
    confidence: float | None


class HealthV1(TypedDict):
    ok: bool
    blockers: list[dict[str, Any]]


class DataSourcesV1(TypedDict):
    ticks: Literal["sqlite"]
    token_resolution: str


@dataclass(frozen=True)
class MarketSnapshotV1:
    snapshot_id: str
    timestamp_epoch: float
    symbol: str
    token_coverage: TokenCoverageV1
    freshness: FreshnessV1
    ticks: TicksV1
    expiry: ExpiryV1
    regime: RegimeV1
    health: HealthV1
    data_sources: DataSourcesV1
    schema_version: Literal["1.0"] = field(default="1.0")

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError("MarketSnapshotV1.schema_version must be '1.0'")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Keep the outward shape stable and explicit for downstream contracts.
        return {
            "schema_version": payload["schema_version"],
            "snapshot_id": payload["snapshot_id"],
            "timestamp_epoch": payload["timestamp_epoch"],
            "symbol": payload["symbol"],
            "token_coverage": payload["token_coverage"],
            "freshness": payload["freshness"],
            "ticks": payload["ticks"],
            "expiry": payload["expiry"],
            "regime": payload["regime"],
            "health": payload["health"],
            "data_sources": payload["data_sources"],
        }


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _as_mutable_dict(snapshot: Mapping[str, Any] | MarketSnapshotV1) -> dict[str, Any]:
    if isinstance(snapshot, MarketSnapshotV1):
        return snapshot.to_dict()
    return dict(snapshot)


def compute_snapshot_id(snapshot_dict: Mapping[str, Any] | MarketSnapshotV1) -> str:
    payload = _as_mutable_dict(snapshot_dict)
    # snapshot_id must never participate in its own digest.
    payload.pop("snapshot_id", None)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
