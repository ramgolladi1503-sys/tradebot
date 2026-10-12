"""Pure, immutable preparation of one socket callback's tick batch.

This module intentionally does not publish callback effects.  It snapshots a
caller-owned batch and prepares a deterministic representation that a later
generation-fenced commit path can consume.  Callers must supply the socket
generation, callback sequence, and receipt time they observed; this module
does not read process state or consult a clock.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time
from types import MappingProxyType
from typing import Any, Mapping


class CallbackPreparationError(ValueError):
    """The callback batch cannot be safely snapshotted; publish nothing."""


def _validated_counter(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CallbackPreparationError(f"{name} must be an integer >= {minimum}")
    return value


def _snapshot_value(value: Any, active_containers: set[int], path: str) -> Any:
    """Copy supported tick values into recursively immutable built-in values.

    Restricting accepted types avoids invoking arbitrary ``__deepcopy__``,
    iteration, or mapping hooks on values supplied to the callback. Cycles and
    non-finite floats are rejected rather than partially copied.
    """
    value_type = type(value)
    if value is None or value_type in (str, bool, int):
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise CallbackPreparationError(f"{path} contains a non-finite float")
        return value
    if value_type in (datetime, date, datetime_time):
        # These standard-library values are immutable and preserve timestamp
        # provenance/type in the prepared row.
        return value
    if value_type not in (dict, list, tuple):
        raise CallbackPreparationError(
            f"{path} has unsupported value type {value_type.__name__}"
        )

    identity = id(value)
    if identity in active_containers:
        raise CallbackPreparationError(f"{path} contains a cyclic value")
    active_containers.add(identity)
    try:
        if value_type is dict:
            copied: dict[str, Any] = {}
            for key, child in value.items():
                if type(key) is not str:
                    raise CallbackPreparationError(f"{path} has a non-string mapping key")
                copied[key] = _snapshot_value(child, active_containers, f"{path}.{key}")
            return MappingProxyType(copied)
        return tuple(
            _snapshot_value(child, active_containers, f"{path}[{index}]")
            for index, child in enumerate(value)
        )
    finally:
        active_containers.remove(identity)


def _canonical_value(value: Any) -> Any:
    """Convert an immutable snapshot into a deterministic JSON value."""
    if isinstance(value, Mapping):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_canonical_value(child) for child in value]
    if type(value) in (datetime, date, datetime_time):
        return {
            "__tick_callback_temporal_type__": type(value).__name__,
            "isoformat": value.isoformat(),
        }
    return value


@dataclass(frozen=True, slots=True)
class TickCallbackEnvelope:
    """Immutable snapshot and deterministic payload for a single callback."""

    socket_generation: int
    callback_sequence: int
    receive_timestamp_epoch: float
    ticks: tuple[Mapping[str, Any], ...]
    canonical_payload: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        generation = _validated_counter(self.socket_generation, "socket_generation", minimum=0)
        sequence = _validated_counter(self.callback_sequence, "callback_sequence", minimum=1)
        if isinstance(self.receive_timestamp_epoch, bool) or not isinstance(
            self.receive_timestamp_epoch, (int, float)
        ):
            raise CallbackPreparationError("receive_timestamp_epoch must be a finite non-negative number")
        received = float(self.receive_timestamp_epoch)
        if not math.isfinite(received) or received < 0.0:
            raise CallbackPreparationError("receive_timestamp_epoch must be a finite non-negative number")
        if type(self.ticks) not in (list, tuple):
            raise CallbackPreparationError("ticks must be a list or tuple of tick mappings")

        rows: list[Mapping[str, Any]] = []
        for index, row in enumerate(self.ticks):
            if type(row) is not dict:
                raise CallbackPreparationError(f"ticks[{index}] must be a plain dict")
            prepared = _snapshot_value(row, set(), f"ticks[{index}]")
            # The outer contract is a mapping, and the recursive copier returns
            # a mapping proxy for plain dictionaries.
            rows.append(prepared)

        immutable_rows = tuple(rows)
        payload_object = {
            "callback_sequence": sequence,
            "receive_timestamp_epoch": received,
            "schema_version": 1,
            "socket_generation": generation,
            "ticks": [_canonical_value(row) for row in immutable_rows],
        }
        try:
            canonical = json.dumps(
                payload_object,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise CallbackPreparationError("callback batch cannot be canonically encoded") from exc

        object.__setattr__(self, "socket_generation", generation)
        object.__setattr__(self, "callback_sequence", sequence)
        object.__setattr__(self, "receive_timestamp_epoch", received)
        object.__setattr__(self, "ticks", immutable_rows)
        object.__setattr__(self, "canonical_payload", canonical)


def prepare_tick_callback(
    ticks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    socket_generation: int,
    callback_sequence: int,
    receive_timestamp_epoch: float,
) -> TickCallbackEnvelope:
    """Snapshot and prepare a callback batch, raising before any publication.

    This function is deterministic for equal inputs and has no process-state,
    clock, I/O, logging, queue, or publication dependencies. Any invalid row
    rejects the complete batch by raising :class:`CallbackPreparationError`.
    """
    return TickCallbackEnvelope(
        socket_generation=socket_generation,
        callback_sequence=callback_sequence,
        receive_timestamp_epoch=receive_timestamp_epoch,
        ticks=ticks,
    )
