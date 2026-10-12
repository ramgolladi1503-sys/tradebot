import json
from datetime import datetime, timezone

import pytest

from core.feed.tick_callback_transaction import (
    CallbackPreparationError,
    prepare_tick_callback,
)


def test_prepared_envelope_is_independent_of_later_mutations_to_input():
    tick = {
        "instrument_token": 101,
        "last_price": 123.5,
        "depth": {"buy": [{"price": 123.0, "quantity": 7}]},
        "_audit_source_row_index": 9,
    }
    batch = [tick]

    prepared = prepare_tick_callback(
        batch,
        socket_generation=4,
        callback_sequence=12,
        receive_timestamp_epoch=1_792_000_000.25,
    )
    payload_before = prepared.canonical_payload

    tick["last_price"] = 0
    tick["depth"]["buy"][0]["quantity"] = 0
    tick["new_field"] = "late mutation"
    batch.append({"instrument_token": 202})

    assert prepared.socket_generation == 4
    assert prepared.callback_sequence == 12
    assert prepared.receive_timestamp_epoch == 1_792_000_000.25
    assert len(prepared.ticks) == 1
    assert prepared.ticks[0]["last_price"] == 123.5
    assert prepared.ticks[0]["depth"]["buy"][0]["quantity"] == 7
    assert "new_field" not in prepared.ticks[0]
    assert prepared.canonical_payload == payload_before
    with pytest.raises(TypeError):
        prepared.ticks[0]["last_price"] = 1


def test_preparation_preserves_row_order_timestamp_provenance_and_identity_fields():
    first_timestamp = datetime(2026, 10, 12, 9, 15, tzinfo=timezone.utc)
    rows = [
        {
            "instrument_token": 202,
            "last_price": 20.0,
            "exchange_timestamp": first_timestamp,
            "_audit_source_row_index": 17,
            "_audit_source_timestamp": "source-ts-17",
        },
        {
            "instrument_token": 101,
            "last_price": 10.0,
            "last_trade_time": "2026-10-12T09:15:01+05:30",
            "_audit_source_row_index": 18,
            "_audit_source_timestamp": "source-ts-18",
        },
    ]

    prepared = prepare_tick_callback(
        rows,
        socket_generation=8,
        callback_sequence=31,
        receive_timestamp_epoch=1_792_000_001.0,
    )
    decoded = json.loads(prepared.canonical_payload)

    assert [row["instrument_token"] for row in prepared.ticks] == [202, 101]
    assert [row["_audit_source_row_index"] for row in prepared.ticks] == [17, 18]
    assert prepared.ticks[0]["exchange_timestamp"] == first_timestamp
    assert prepared.ticks[1]["last_trade_time"] == "2026-10-12T09:15:01+05:30"
    assert [row["_audit_source_timestamp"] for row in decoded["ticks"]] == [
        "source-ts-17",
        "source-ts-18",
    ]
    assert [row["instrument_token"] for row in decoded["ticks"]] == [202, 101]
    assert decoded["socket_generation"] == 8
    assert decoded["callback_sequence"] == 31
    assert decoded["ticks"][0]["exchange_timestamp"] == {
        "__tick_callback_temporal_type__": "datetime",
        "isoformat": "2026-10-12T09:15:00+00:00",
    }


def test_equal_inputs_produce_equal_canonical_payloads():
    kwargs = {
        "socket_generation": 2,
        "callback_sequence": 3,
        "receive_timestamp_epoch": 1_792_000_000.0,
    }
    one = prepare_tick_callback([{"b": 2, "a": [1, 3]}], **kwargs)
    two = prepare_tick_callback([{"a": [1, 3], "b": 2}], **kwargs)

    assert one.canonical_payload == two.canonical_payload


@pytest.mark.parametrize(
    "ticks",
    [
        None,
        [None],
        [dict(token=1), object()],
        [{1: "non-string key"}],
        [{"bad": float("nan")}],
        [{"bad": float("inf")}],
    ],
)
def test_malformed_batches_fail_closed(ticks):
    with pytest.raises(CallbackPreparationError):
        prepare_tick_callback(
            ticks,
            socket_generation=1,
            callback_sequence=1,
            receive_timestamp_epoch=1.0,
        )


def test_non_copyable_custom_value_is_rejected_without_calling_copy_hook():
    class NonCopyable:
        copy_hook_called = False

        def __deepcopy__(self, _memo):
            self.copy_hook_called = True
            raise RuntimeError("must not be invoked")

    value = NonCopyable()
    with pytest.raises(CallbackPreparationError, match="unsupported value type"):
        prepare_tick_callback(
            [{"opaque": value}],
            socket_generation=1,
            callback_sequence=1,
            receive_timestamp_epoch=1.0,
        )
    assert value.copy_hook_called is False


def test_cyclic_input_and_invalid_envelope_metadata_fail_closed():
    cyclic = {}
    cyclic["self"] = cyclic
    with pytest.raises(CallbackPreparationError, match="cyclic"):
        prepare_tick_callback(
            [cyclic],
            socket_generation=1,
            callback_sequence=1,
            receive_timestamp_epoch=1.0,
        )

    with pytest.raises(CallbackPreparationError, match="socket_generation"):
        prepare_tick_callback(
            [],
            socket_generation=-1,
            callback_sequence=1,
            receive_timestamp_epoch=1.0,
        )
    with pytest.raises(CallbackPreparationError, match="callback_sequence"):
        prepare_tick_callback(
            [],
            socket_generation=1,
            callback_sequence=0,
            receive_timestamp_epoch=1.0,
        )
    with pytest.raises(CallbackPreparationError, match="receive_timestamp_epoch"):
        prepare_tick_callback(
            [],
            socket_generation=1,
            callback_sequence=1,
            receive_timestamp_epoch=float("nan"),
        )
