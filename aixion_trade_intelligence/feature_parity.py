from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence


def _normalize_values(values: Mapping[str, object]) -> dict[str, object]:
    try:
        encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("feature_values_not_json_safe") from exc
    return json.loads(encoded)


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name}_must_be_timezone_aware")
    return value


@dataclass(frozen=True)
class FeatureRecord:
    entity_id: str
    feature_set_id: str
    feature_version: str
    mode: str
    event_time: datetime
    available_time: datetime
    input_hash: str
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.feature_set_id.strip() or not self.feature_version.strip():
            raise ValueError("feature_identity_missing")
        mode = self.mode.strip().upper()
        if mode not in {"LIVE", "REPLAY", "BACKTEST", "RESEARCH"}:
            raise ValueError(f"unsupported_feature_mode={mode}")
        event_time = _aware(self.event_time, name="event_time")
        available_time = _aware(self.available_time, name="available_time")
        if available_time > event_time:
            raise ValueError("feature_available_after_event_time")
        if not self.input_hash.strip():
            raise ValueError("feature_input_hash_missing")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "event_time", event_time)
        object.__setattr__(self, "available_time", available_time)
        object.__setattr__(self, "values", _normalize_values(self.values))

    @property
    def output_hash(self) -> str:
        payload = {
            "entity_id": self.entity_id,
            "feature_set_id": self.feature_set_id,
            "feature_version": self.feature_version,
            "event_time": self.event_time.isoformat(),
            "available_time": self.available_time.isoformat(),
            "input_hash": self.input_hash,
            "values": self.values,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def parity_key(self) -> tuple[str, str, str, str]:
        return (self.entity_id, self.feature_set_id, self.feature_version, self.event_time.isoformat())


@dataclass(frozen=True)
class FeatureParityReport:
    left_mode: str
    right_mode: str
    compared: int
    matching: int
    missing_left: tuple[tuple[str, str, str, str], ...]
    missing_right: tuple[tuple[str, str, str, str], ...]
    input_hash_mismatches: tuple[tuple[str, str, str, str], ...]
    output_hash_mismatches: tuple[tuple[str, str, str, str], ...]

    @property
    def valid(self) -> bool:
        return not (self.missing_left or self.missing_right or self.input_hash_mismatches or self.output_hash_mismatches)

    def to_record(self) -> dict[str, object]:
        return {
            "left_mode": self.left_mode,
            "right_mode": self.right_mode,
            "compared": self.compared,
            "matching": self.matching,
            "missing_left": [list(key) for key in self.missing_left],
            "missing_right": [list(key) for key in self.missing_right],
            "input_hash_mismatches": [list(key) for key in self.input_hash_mismatches],
            "output_hash_mismatches": [list(key) for key in self.output_hash_mismatches],
            "valid": self.valid,
        }


def compare_feature_modes(left: Sequence[FeatureRecord], right: Sequence[FeatureRecord]) -> FeatureParityReport:
    if not left or not right:
        raise ValueError("feature_parity_inputs_empty")
    left_modes = {record.mode for record in left}
    right_modes = {record.mode for record in right}
    if len(left_modes) != 1 or len(right_modes) != 1:
        raise ValueError("feature_parity_each_side_requires_one_mode")
    left_map = {record.parity_key: record for record in left}
    right_map = {record.parity_key: record for record in right}
    if len(left_map) != len(left) or len(right_map) != len(right):
        raise ValueError("duplicate_feature_parity_key")
    keys = sorted(set(left_map) | set(right_map))
    missing_left = tuple(key for key in keys if key not in left_map)
    missing_right = tuple(key for key in keys if key not in right_map)
    input_mismatches = []
    output_mismatches = []
    matching = 0
    for key in sorted(set(left_map) & set(right_map)):
        left_record = left_map[key]
        right_record = right_map[key]
        if left_record.input_hash != right_record.input_hash:
            input_mismatches.append(key)
        elif left_record.output_hash != right_record.output_hash:
            output_mismatches.append(key)
        else:
            matching += 1
    return FeatureParityReport(next(iter(left_modes)), next(iter(right_modes)), len(set(left_map) & set(right_map)), matching, missing_left, missing_right, tuple(input_mismatches), tuple(output_mismatches))


def hash_feature_inputs(values: Mapping[str, object]) -> str:
    normalized = _normalize_values(values)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
